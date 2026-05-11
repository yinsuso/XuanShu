import os
import sys
import uuid
import asyncio
import json
import time
from threading import Lock
from pathlib import Path
from contextlib import asynccontextmanager
from agent import UniversalAgent
import threading
from fastapi import Response
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import WEB_APP_URL,  APPROVAL_API_TOKEN,  APPROVAL_DB_PATH,  PROJECT_ROOT, CAPABILITY_MODEL_RANKINGS, SCHEDULER_STRATEGY, MANAGER_MONITOR_INTERVAL, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT
from logger import logger
from evolution.cluster.capability import CapabilityAssessor
from evolution.cluster.scheduler import TaskScheduler
from evolution.cluster.discovery import ClusterDiscovery

# === 安全审批模块：sqlite3 兼容层 ===
_SQLITE_AVAILABLE = False
try:
    import sqlite3
    _SQLITE_AVAILABLE = True
    logger.info("✅ web_app.py: sqlite3 模块可用")
except ImportError as e:
    logger.warning(f"⚠️ web_app.py: sqlite3 模块不可用 ({e})，使用 JSON 文件存储审批数据")

# ==================== 新增依赖：模型管理与对话历史 ====================
from fastapi import Form
from model_providers import config_manager, ModelConfig, ProviderType
from conversation_manager import get_global_conversation_manager

# 全局对话管理器实例（用于 API 处理）
conv_manager = get_global_conversation_manager()

# 全局 UniversalAgent 实例（懒加载）
_agent = None
_agent_lock = threading.Lock()
_discovery_instance = None

def get_agent():
    """获取全局 UniversalAgent 实例（线程安全懒加载）"""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = UniversalAgent()
    return _agent



# ============ 版本统一管理 ============
def _get_app_version():
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION')
    try:
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"
_APP_VERSION = _get_app_version()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理器：替代废弃的 on_event"""
    # 启动时：执行初始化（目前为空，因为集群已改为懒加载）
    print("🚀 玄枢 Web 服务启动中...")
    yield
    # 关闭时：执行清理工作（如有）
    print("🛑 玄枢 Web 服务关闭中...")

app = FastAPI(title="玄枢智能体", version=_APP_VERSION, lifespan=lifespan)

# CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 集群 API 挂载
from evolution.cluster import cluster_api
from evolution.cluster.protocol import create_heartbeat, create_task_update
app.include_router(cluster_api.router, prefix='/api/cluster')

# 静态文件服务 - 挂载前端页面
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

static_dir = os.path.join(PROJECT_ROOT, "web/static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url="/static/index.html")

class ApprovalStore:
    def __init__(self):
        self._use_json_mode = not _SQLITE_AVAILABLE
        self.lock = Lock()
        if not self._use_json_mode:
            db_path = Path(APPROVAL_DB_PATH)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(APPROVAL_DB_PATH, check_same_thread=False)
            self._init_sqlite_db()
            logger.info("✅ ApprovalStore: 使用 SQLite 模式")
        else:
            json_dir = os.path.join(os.path.dirname(APPROVAL_DB_PATH), "approval_json")
            os.makedirs(json_dir, exist_ok=True)
            self.json_file = os.path.join(json_dir, "approvals.json")
            self._init_json_store()
            logger.info("✅ ApprovalStore: 使用 JSON 文件模式")

    # --- SQLite 模式 ---
    if _SQLITE_AVAILABLE:
        def _init_sqlite_db(self):
            with self.lock:
                self.conn.execute('CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY AUTOINCREMENT, skill TEXT NOT NULL, args TEXT NOT NULL, risk TEXT NOT NULL, status TEXT NOT NULL DEFAULT "pending", created_at REAL NOT NULL, decided_at REAL, decision TEXT)')
                self.conn.commit()

        def create_request(self, skill_name, args, risk_level):
            with self.lock:
                cur = self.conn.execute(
                    "INSERT INTO approvals (skill, args, risk, status, created_at) VALUES (?, ?, ?, ?, ?)",
                    (skill_name, json.dumps(args), risk_level, 'pending', time.time())
                )
                self.conn.commit()
                return cur.lastrowid

        def get_status(self, approval_id):
            with self.lock:
                cur = self.conn.execute(
                    "SELECT status, decision, decided_at FROM approvals WHERE id = ?",
                    (approval_id,)
                )
                row = cur.fetchone()
                if row is None:
                    return None
                status, decision, decided_at = row
                return {"status": status, "decision": decision, "decided_at": decided_at}

        def get_all_pending(self):
            with self.lock:
                cur = self.conn.execute(
                    "SELECT id, skill, args, risk, created_at FROM approvals WHERE status = 'pending'"
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    rid, skill, args, risk, created_at = row
                    result.append({
                        "id": rid,
                        "skill": skill,
                        "args": json.loads(args),
                        "risk": risk,
                        "timestamp": created_at
                    })
                return result

        def set_decision(self, approval_id, decision):
            with self.lock:
                cur = self.conn.execute(
                    "UPDATE approvals SET status = 'decided', decision = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                    (decision, time.time(), approval_id)
                )
                self.conn.commit()
                return cur.rowcount > 0

    # --- JSON 文件模式 ---
    else:
        def _init_json_store(self):
            if not os.path.exists(self.json_file):
                with open(self.json_file, 'w', encoding='utf-8') as f:
                    json.dump({"next_id": 1, "approvals": []}, f, ensure_ascii=False)

        def _load_data(self):
            with open(self.json_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        def _save_data(self, data):
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        def create_request(self, skill_name, args, risk_level):
            with self.lock:
                data = self._load_data()
                new_id = data["next_id"]
                data["approvals"].append({
                    "id": new_id,
                    "skill": skill_name,
                    "args": args,
                    "risk": risk_level,
                    "status": "pending",
                    "created_at": time.time(),
                    "decided_at": None,
                    "decision": None
                })
                data["next_id"] = new_id + 1
                self._save_data(data)
                return new_id

        def get_status(self, approval_id):
            with self.lock:
                data = self._load_data()
                for app in data["approvals"]:
                    if app["id"] == approval_id:
                        return {
                            "status": app["status"],
                            "decision": app["decision"],
                            "decided_at": app["decided_at"]
                        }
                return None

        def get_all_pending(self):
            with self.lock:
                data = self._load_data()
                result = []
                for app in data["approvals"]:
                    if app["status"] == "pending":
                        result.append({
                            "id": app["id"],
                            "skill": app["skill"],
                            "args": app["args"],
                            "risk": app["risk"],
                            "timestamp": app["created_at"]
                        })
                return result

        def set_decision(self, approval_id, decision):
            with self.lock:
                data = self._load_data()
                for app in data["approvals"]:
                    if app["id"] == approval_id and app["status"] == "pending":
                        app["status"] = "decided"
                        app["decision"] = decision
                        app["decided_at"] = time.time()
                        self._save_data(data)
                        return True
                return False

# 全局存储实例
approval_store = ApprovalStore()

def verify_approval_token(request: Request):
    # 若未配置 API Token，则允许所有请求
    if not APPROVAL_API_TOKEN:
        return True
    token = request.headers.get("X-Approval-Token")
    return token == APPROVAL_API_TOKEN

@app.get("/api/approvals/pending")
async def api_approvals_pending(request: Request):
    if not verify_approval_token(request):
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    return {"approvals": approval_store.get_all_pending()}

@app.post("/api/approvals/decide")
async def api_approvals_decide(request: Request):
    if not verify_approval_token(request):
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    data = await request.json()
    aid = data.get("approval_id")
    decision = data.get("decision")
    if decision not in ("approve", "reject"):
        return {"success": False, "error": "无效的决策值"}
    if approval_store.set_decision(aid, decision):
        return {"success": True, "message": "已处理"}
    else:
        return {"success": False, "error": "未找到对应审批请求"}

@app.get("/api/approvals/{approval_id}/status")
async def api_approval_status(approval_id: int, request: Request):
    if not verify_approval_token(request):
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    status_info = approval_store.get_status(approval_id)
    if status_info is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "未找到审批请求"})
    return {"status": status_info["status"], "decision": status_info.get("decision")}

@app.post("/api/approvals/create")
async def api_approvals_create(request: Request):
    if not verify_approval_token(request):
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    data = await request.json()
    skill = data.get("skill_name")
    args = data.get("args")
    risk = data.get("risk_level")
    if not all([skill, args, risk]):
        return {"success": False, "error": "缺少必要参数"}
    aid = approval_store.create_request(skill, args, risk)
    return {"approval_id": aid}

# =============================================================================
# 集群协作启动事件（Phase 2 新增）
# =============================================================================
from config import CLUSTER_ENABLED, CLUSTER_ROLE, CLUSTER_NODE_ID, CLUSTER_NODE_NICKNAME, MODEL_NAME
from evolution.cluster.connection import ClusterNode, ClusterManager, ClusterClient
from evolution.cluster.cluster_api import verify_token, get_cluster_node

@app.get("/api/info")
async def get_info():
    """获取当前节点角色与状态，同时返回当前从model_config.json读取的模型配置"""
    from model_providers import config_manager
    current_model = None
    current_model_name = None
    if config_manager and config_manager.current_config:
        current_model = config_manager.current_config
        current_model_name = current_model.model_name
    if not CLUSTER_ENABLED:
        return {
            "role": "standalone", 
            "message": "Cluster disabled",
            "current_model_name": current_model_name
        }
    role = CLUSTER_ROLE
    node = getattr(app.state, "cluster_node", None)
    if role == "manager":
        manager = getattr(app.state, "cluster_manager", None)
        if manager:
            room = manager.get_room_info()
            return {
                "role": "manager", 
                "room": room,
                "current_model_name": current_model_name
            }
        else:
            return {"role": "manager", "room": None, "current_model_name": current_model_name}
    else:  # worker
        if node:
            return {
                "role": "worker",
                "node_id": node.node_id,
                "connected": node.connection is not None,
                "mode": node.mode,
                "model": node.model,
                "current_model_name": current_model_name
            }
        else:
            return {"role": "worker", "connected": False, "current_model_name": current_model_name}

@app.post("/api/rooms/create")
async def create_room(request: Request):
    """创建房间（Manager 或单机模式）"""
    try:
        # 在单机模式下允许创建房间，集群模式下需要 manager 角色
        if CLUSTER_ENABLED and CLUSTER_ROLE != "manager":
            raise HTTPException(status_code=403, detail="仅 Manager 可创建房间")

        # 懒加载集群组件
        success = await ensure_cluster_initialized()
        if not success:
            raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
        
        data = await request.json()
        room_name = data.get("room_name")
        owner_name = data.get("owner_name")
        model = data.get("model")
        password = data.get("password", "")  # 可选密码，默认空字符串
        
        # 参数验证
        if not room_name or not isinstance(room_name, str) or len(room_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="房间名称不能为空")
        if not owner_name or not isinstance(owner_name, str) or len(owner_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="房主名称不能为空")
        if not model or not isinstance(model, str) or len(model.strip()) == 0:
            raise HTTPException(status_code=400, detail="模型名称不能为空")
        if len(password) > 32:
            raise HTTPException(status_code=400, detail="密码长度不能超过32字符")
        
        manager = getattr(app.state, "cluster_manager", None)
        if not manager:
            logger.error("创建房间失败：集群管理器未初始化")
            raise HTTPException(status_code=500, detail="集群管理器未初始化")
        
        node = getattr(app.state, "cluster_node", None)
        owner_node_id = node.node_id if node else None
        
        # 存储密码哈希（使用 sha256）
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
        
        room_id = manager.create_room(room_name, owner_name, model, owner_node_id=owner_node_id, password_hash=password_hash)
        
        # 单机模式下也启动房主的TCP服务器，让其他agent可以通过局域网连接进来
        try:
            from config import CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT
            manager.start_server(host=CLUSTER_MANAGER_HOST, port=CLUSTER_MANAGER_PORT)
            logger.info(f"🌐 房主TCP服务器已启动在 {CLUSTER_MANAGER_HOST}:{CLUSTER_MANAGER_PORT}")
        except Exception as e:
            logger.warning(f"启动TCP服务器时遇到问题（可能已在运行）: {e}")
        
        # 创建房间后启动房主UDP广播（单机模式下的关键）
        discovery = getattr(manager, 'discovery', None) or globals().get('_discovery_instance')
        if discovery:
            # 更新discovery的房间信息
            discovery.update_room_info(room_name=room_name, room_id=room_id, extra_info={
                "owner_name": owner_name,
                "owner_model": model
            })
            # 启动广播
            discovery.start_hosting(extra_info={
                "owner_name": owner_name,
                "owner_model": model
            })
            logger.info(f"📢 UDP广播已启动，房间信息: {room_name}, 房主模型: {model}")
        else:
            logger.warning("⚠️ discovery实例未找到，UDP广播未启动")
        
        logger.info(f"房间创建成功: room_id={room_id}, room_name={room_name}, owner={owner_name}, model={model}, has_password={password_hash is not None}")
        return {"success": True, "room_id": room_id, "room_name": room_name}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建房间失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建房间失败: {str(e)}")

@app.get("/api/rooms/current")
async def get_current_room(request: Request):
    """获取当前房间信息（Manager 或 standalone 模式）"""
    if CLUSTER_ROLE not in ("manager", "") and CLUSTER_ENABLED:
        raise HTTPException(status_code=403, detail="仅 Manager 可查看")

    # 懒加载集群组件
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)

    if not manager:
        return {"success": False, "error": "房间管理器未初始化"}

    info = manager.get_room_info()
    info["members_detail"] = manager.get_member_info()
    info["success"] = True  # 总是返回 success，即使房间是 Default-Room
    
    # 【问题1修复】从 model_config.json 中读取所有模型配置，返回给前端下拉框
    from model_providers import config_manager
    all_models = []
    configs = config_manager.list_configs()
    for cfg in configs:
        suffix = " (当前)" if cfg.get('is_current') else ""
        type_label = " (本地)" if cfg.get('provider') == 'ollama' else " (云端)"
        all_models.append({
            "name": cfg["name"],
            "model": cfg["model"],
            "desc": f"{cfg['model']}{suffix}{type_label}"
        })
    # 补充 Ollama 模型到列表 - 静默模式（完全不输出警告）
    try:
        ollama_models_res = await list_ollama_models()
        if ollama_models_res.get("success"):
            existing_names = {m["model"] for m in all_models}
            for m in ollama_models_res.get("models", []):
                if m["name"] not in existing_names:
                    all_models.append({
                        "name": m["name"],
                        "model": m["model"],
                        "desc": f"{m['name']} (Ollama)"
                    })
    except Exception:
        pass  # 静默忽略所有Ollama相关错误，完全不打扰用户
    info["available_models"] = all_models
    info["current_model"] = config_manager.current_config.model_name if config_manager.current_config else None
    
    logger.info(f"房间信息: owner_name={info.get('owner_name')}, room_name={info.get('room_name')}, members_detail={info['members_detail']}")
    return info

@app.get("/api/rooms/list")
async def list_rooms(request: Request):
    """获取房间列表（支持单机模式和集群模式，包含扫描到的局域网其他主机房间）"""
    try:
        # 确保集群组件已初始化
        await ensure_cluster_initialized()
        manager = getattr(app.state, "cluster_manager", None)

        final_rooms = []
        if not manager:
            return {"success": True, "rooms": []}

        # 1. 把本地房间加入列表 - 【问题4修复】严格检查房间是否真实创建
        room_info = manager.get_room_info()
        is_real_local_room = (
            room_info["room_name"] != "Default-Room" and 
            room_info.get("owner_name") is not None and 
            room_info.get("room_ready", False)
        )
        if is_real_local_room:
            room_info["members_detail"] = manager.get_member_info()
            room_info["status"] = "active" if len(room_info["members"]) > 0 else "waiting"
            room_info["is_local"] = True
            final_rooms.append(room_info)

        # 2. 把通过 UDP 广播发现的局域网其他主机房间也加入列表
        discovery = getattr(manager, "discovery", None) or globals().get('_discovery_instance')
        if discovery:
            found = discovery.get_available_rooms()
            for r in found:
                # 【问题4修复】严格过滤无效的/未准备好的远程房间
                remote_room_name = r.get('room_name', '')
                if (not remote_room_name or 
                    remote_room_name == "Default-Room" or 
                    remote_room_name == "Default-Agent-Room" or
                    not r.get('owner_name') or 
                    r.get('owner_name') == 'Unknown'):
                    # 无效房间跳过
                    continue
                # 排除本地房间（通过 room_id 比对）
                local_room_id = getattr(manager, 'room_id', None)
                if r.get('room_id') != local_room_id:
                    final_rooms.append({
                        "room_id": r.get('room_id'),
                        "room_name": r.get('room_name', 'Unnamed-Room'),
                        "owner_name": r.get('owner_name', 'Unknown'),
                        "owner_model": r.get('owner_model', 'unknown'),
                        "ip": r.get('ip'),
                        "manager_port": r.get('manager_port', 30001),
                        "members": [],
                        "members_detail": [],
                        "has_password": False,
                        "total_members": 0,
                        "is_local": False,
                        "status": "remote"
                    })

        return {"success": True, "rooms": final_rooms}
    except Exception as e:
        logger.error(f"获取房间列表失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "rooms": []}

@app.post("/api/rooms/join")
async def join_room(request: Request):
    """Worker 加入房间（触发 ClusterClient 连接）"""
    import socket

    # 懒加载集群组件 - 问题2优化：无论CLUSTER_ENABLED与否都确保初始化完成
    success = await ensure_cluster_initialized()
    if not success:
        raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    data = await request.json()
    host = data.get("host")
    port = data.get("port", 30001)
    name = data.get("name")
    mode = data.get("mode", "auto")
    model = data.get("model")
    password = data.get("password", "")
    if not all([host, name, model]):
        raise HTTPException(status_code=400, detail="缺少必要参数")

    node = getattr(app.state, "cluster_node", None)
    if node and node.connection:
        return {"success": False, "error": "已经连接到一个房间，请先退出当前房间"}

    # 解析 host:port
    if ":" in host:
        host_parts = host.split(":")
        host = host_parts[0]
        port = int(host_parts[1])
    
    # 【关键修复】有效性检查：不允许尝试连接无意义主机或无效端口
    # 先获取本机所有IP做过滤
    try:
        hostname = socket.gethostname()
        local_ips = ['127.0.0.1']
        try:
            host_info = socket.gethostbyname_ex(hostname)
            for local_ip_candidate in host_info[2]:
                if local_ip_candidate not in local_ips:
                    local_ips.append(local_ip_candidate)
        except Exception:
            pass
        
        # 关键优化：不再禁止本机IP连接，允许单机多角色调试场景（房主和Worker在同一台机器）
        # 这样用户可以在同一台机器上通过 127.0.0.1 或局域网IP连接自己的TCP服务器进行调试
        logger.info(f"🔌 准备连接到主机 {host}，支持单机多角色调试场景")
        
        # 端口范围安全检查：防止无效端口
        if not (1024 <= port <= 65535):
            logger.warning(f"⚠️ 无效端口号: {port}")
            raise HTTPException(status_code=400, detail=f"无效端口号: {port}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"⚠️ 连接前有效性检查失败: {e}，继续尝试...")

    from evolution.cluster.connection import ClusterClient
    client = ClusterClient()
    node_info = {
        "node_id": node.node_id if node else str(uuid.uuid4()),
        "model": model,
        "role": "worker",
        "mode": mode,
        "name": name
    }
    try:
        loop = asyncio.get_event_loop()
        # 传递密码参数给 client.join()
        success = await asyncio.wait_for(
            loop.run_in_executor(None, client.join, host, port, node_info, password),
            timeout=8.0
        )
    except asyncio.TimeoutError:
        success = False
        logger.error(f"❌ 连接房间 {host}:{port} 超时（8秒），请确认房主房间是否创建成功且网络可访问")
    except ConnectionRefusedError:
        success = False
        logger.error(f"❌ [ClusterClient] 连接被拒绝: {host}:{port}，请确认房主的房间已经创建成功")
    except Exception as e:
        success = False
        logger.error(f"❌ Worker 连接 manager 失败: {e}")

    if success:
        if node:
            node.connection = client.socket
            node.model = model
            node.status = "active"
        def listener():
            while True:
                try:
                    if not client.socket:
                        break
                    data = client.socket.recv(4096)
                    if not data:
                        break
                    msg = json.loads(data.decode('utf-8'))
                    msg_type = msg.get("type")
                    if msg_type == "task_assignment":
                        payload = msg.get("payload", {})
                        if node:
                            node.receive_assignment(
                                task_id=payload["task_id"],
                                task_type=payload["task_type"],
                                description=payload["description"],
                                parameters=payload.get("parameters")
                            )
                    else:
                        logger.debug(f"Worker 监听线程收到其他消息: {msg_type}")
                except Exception as e:
                    logger.debug(f"Worker 监听线程异常: {e}")
                    break
            threading.Thread(target=listener, daemon=True).start()

        def heartbeat_loop():
            while True:
                try:
                    if client.socket:
                        from evolution.cluster.protocol import create_heartbeat
                        hb = create_heartbeat(
                            node_info["node_id"],
                            {
                                "load_cpu": 0.5,
                                "load_memory": 0.5,
                                "queue_length": 0
                            }
                        )
                        client.socket.sendall(hb.serialize())
                except Exception as e:
                    logger.debug(f"心跳发送失败: {e}")
                    break
                time.sleep(5)
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        return {"success": True, "message": "已加入房间"}
    else:
        raise HTTPException(status_code=500, detail="加入房间失败，请确认房主房间已创建成功、网络可达，且密码正确")

@app.post("/api/rooms/leave")
async def leave_room(request: Request):
    """Worker 离开房间"""

    # 懒加载集群组件
    if CLUSTER_ENABLED:
        success = await ensure_cluster_initialized()
        if not success:
            raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    node = getattr(app.state, "cluster_node", None)
    if node and node.connection:
        try:
            node.connection.close()
        except:
            pass
        node.connection = None
        return {"success": True}
    return {"success": False, "error": "未连接"}

@app.post("/api/rooms/update_member")
async def update_member(request: Request):
    """更新成员信息（花名、模型）"""
    data = await request.json()
    nickname = data.get("nickname")
    model = data.get("model")
    
    if not nickname:
        raise HTTPException(status_code=400, detail="花名不能为空")

    manager = getattr(app.state, "cluster_manager", None)
    node = getattr(app.state, "cluster_node", None)
    
    if manager:
        # 更新房间成员信息 - 尝试多种可能的成员ID
        member_id = None
        if node and node.node_id in manager.room_members:
            member_id = node.node_id
        elif "manager" in manager.room_members:
            member_id = "manager"
        elif manager.current_project in manager.room_members:
            member_id = manager.current_project
        
        if member_id:
            manager.room_members[member_id]["name"] = nickname
            if model:
                manager.room_members[member_id]["model"] = model
            logger.info(f"成员信息已更新: {member_id} -> {nickname}")
        else:
            logger.warning(f"未找到当前用户的成员记录")
    
    return {"success": True, "message": "信息已更新"}

@app.post("/api/rooms/start_task")
async def start_task(request: Request):
    """Manager 开启协作任务（广播给所有成员，让全体自动进入协作对话模式）"""
    from evolution.cluster.cluster_api import broadcast_to_all_clients
    
    verify_token(request)
    
    # 懒加载集群组件
    success = await ensure_cluster_initialized()
    if not success:
        raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    
    data = await request.json()
    task_type = data.get("task_type")
    description = data.get("description")
    parameters = data.get("parameters", {})
    if not all([task_type, description]):
        raise HTTPException(status_code=400, detail="缺少任务类型或描述")
    manager = app.state.cluster_manager
    
    # 第一步：向所有浏览器客户端广播「进入协作模式」事件
    await broadcast_to_all_clients({
        "type": "enter_collab_mode",
        "task_type": task_type,
        "description": description,
        "timestamp": time.time()
    })
    
    # 第二步：调用调度分配任务
    task_id = manager.start_collaborative_task(task_type, description, parameters)
    
    logger.info(f"🤝 [协作模式] 房主发起协作任务: task_id={task_id}, 描述={description}")
    return {"success": True, "task_id": task_id, "message": "已向所有成员广播协作任务"}

@app.post("/api/rooms/dismiss")
async def dismiss_room(request: Request):
    """解散房间（Manager 或 standalone 模式）"""
    # 支持 standalone 模式和解散房间
    if CLUSTER_ENABLED and CLUSTER_ROLE != "manager":
        raise HTTPException(status_code=403, detail="仅 Manager 可解散房间")

    manager = getattr(app.state, "cluster_manager", None)
    if not manager:
        raise HTTPException(status_code=500, detail="集群管理器未初始化")

    try:
        # 第一步：停止房主UDP广播，这样其他agent的扫描器就不会再收到旧房间信息了
        discovery = getattr(manager, 'discovery', None) or globals().get('_discovery_instance')
        if discovery:
            discovery.stop_hosting()
            logger.info("📢 房主UDP广播已停止，其他Agent将很快看不到这个房间")
        
        # 第二步：停止房主TCP服务器，断开所有已连接的成员
        try:
            manager.stop_server()
        except Exception as e:
            logger.warning(f"停止TCP服务器时遇到问题: {e}")
        
        # 第三步：重置房间信息
        manager.room_id = str(uuid.uuid4())
        manager.room_name = "Default-Room"
        manager.owner_name = None
        manager.owner_model = None
        manager.room_password_hash = None
        manager.room_members.clear()
        # 同时清理 nodes 字典中的成员节点（房主节点保留）
        owner_node_id = manager.own_node.node_id if hasattr(manager, 'own_node') and manager.own_node else None
        nodes_to_remove = []
        for nid in manager.nodes.keys():
            if nid != owner_node_id:
                nodes_to_remove.append(nid)
        for nid in nodes_to_remove:
            del manager.nodes[nid]
        
        logger.info("✅ 房间已完整解散，UDP广播和TCP服务已停止")
        return {"success": True, "message": "房间已解散"}
    except Exception as e:
        logger.error(f"解散房间失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"解散房间失败: {str(e)}")

@app.post("/api/cluster/tasks/{task_id}/error")
async def report_task_error(task_id: str, request: Request):
    """成员报告任务执行中的问题（转发给 Manager）"""
    data = await request.json()
    error_msg = data.get("error", "未知错误")
    node = getattr(app.state, "cluster_node", None)
    if not node:
        raise HTTPException(status_code=503, detail="节点未初始化")

    manager = getattr(app.state, "cluster_manager", None)
    if manager:
        logger.warning(f"任务 {task_id} 执行遇到问题: {error_msg}")
        # 记录错误信息到任务日志
        if task_id in manager.task_metadata:
            manager.task_metadata[task_id]["error"] = error_msg
            manager.task_metadata[task_id]["error_reported_at"] = time.time()
        # 广播错误信息给所有成员
        manager.broadcast_to_room(manager.room_id, {
            "type": "task_error",
            "task_id": task_id,
            "error": error_msg,
            "node_id": node.node_id
        })
        return {"success": True, "message": "问题已反馈"}
    return {"success": False, "error": "Manager 未就绪"}

async def ensure_cluster_initialized():
    """
    懒加载初始化集群组件。
    根据 CLUSTER_ROLE 执行 manager 或 worker 的初始化。
    返回 True 表示成功， False 表示失败（但不会阻塞启动）。
    """
    global _cluster_initialized, _discovery_instance
    if '_cluster_initialized' not in globals():
        globals()['_cluster_initialized'] = False
        globals()['_cluster_lock'] = threading.Lock()
    if globals()['_cluster_initialized']:
        return True
    lock = globals()['_cluster_lock']
    if not lock.acquire(blocking=False):
        import asyncio
        await asyncio.sleep(0.2)
        return await ensure_cluster_initialized()
    try:
        if not CLUSTER_ENABLED:
            # 单机模式下也需要初始化集群管理器用于房间功能
            # 从 model_providers 获取当前模型配置，保证模型正确性
            from model_providers import config_manager
            current_model_name = MODEL_NAME or "qwen2.5-coder:7b"
            current_cfg = config_manager.current_config
            if current_cfg:
                current_model_name = current_cfg.model_name
                logger.info(f"🔍 [单机初始化] 从配置管理器获取当前模型: {current_model_name}")
            else:
                logger.info(f"🔍 [单机初始化] 使用默认模型: {current_model_name}")
            
            node = ClusterNode(
                node_id=str(uuid.uuid4()),
                ip="127.0.0.1",
                model=current_model_name,
                role="manager",
                mode="auto"
            )
            app.state.cluster_node = node
            manager = ClusterManager()
            manager.own_node = node
            manager.broadcast_node = node
            # 确保初始时node.model与从配置管理器获取的模型一致
            node.model = current_model_name
            assessor = CapabilityAssessor(CAPABILITY_MODEL_RANKINGS)
            scheduler = TaskScheduler(assessor, strategy=SCHEDULER_STRATEGY)
            manager.set_scheduler(scheduler, assessor)
            manager.start_monitoring(interval=MANAGER_MONITOR_INTERVAL)
            # 【关键修复1】单机模式下只启动扫描模式，绝对不启动默认房间的UDP广播！
            # 等用户手动调用创建房间API后，再广播真实的自定义房间信息
            if not globals().get('_discovery_instance'):
                globals()['_discovery_instance'] = ClusterDiscovery()
                globals()['_discovery_instance'].start_scanning()  # 仅启动扫描，只发现别人的房间
                manager.discovery = globals()['_discovery_instance']
                logger.info("✅ [ClusterDiscovery] 单机模式局域网扫描已启动（仅扫描，未广播，等待用户创建房间）")
            # 【关键修复2】单机模式下：不要提前启动TCP服务器，用户创建房间时再启动！
            # 这样不会有未创建房间时TCP端口就被占用但没有真实房间的情况
            app.state.cluster_manager = manager
            logger.info("✅ [ClusterManager] 单机模式集群管理器已初始化")
            _cluster_initialized = True
            return True
        if CLUSTER_ROLE == "manager":
            node = ClusterNode(
                node_id=CLUSTER_NODE_ID or str(uuid.uuid4()),
                ip="0.0.0.0",
                model=MODEL_NAME,
                role=CLUSTER_ROLE,
                mode="auto"
            )
            app.state.cluster_node = node
            manager = ClusterManager()
            manager.own_node = node
            manager.broadcast_node = node
            assessor = CapabilityAssessor(CAPABILITY_MODEL_RANKINGS)
            scheduler = TaskScheduler(assessor, strategy=SCHEDULER_STRATEGY)
            manager.set_scheduler(scheduler, assessor)
            manager.start_monitoring(interval=MANAGER_MONITOR_INTERVAL)
            mgr_thread = threading.Thread(
                target=manager.start_server,
                kwargs={"host": "0.0.0.0", "port": CLUSTER_MANAGER_PORT},
                daemon=True
            )
            mgr_thread.start()
            app.state.cluster_manager = manager
            print("✅ [ClusterManager] 集群管理器已启动（懒加载）")
            _cluster_initialized = True
            return True
        elif CLUSTER_ROLE == "worker":
            node = ClusterNode(
                node_id=CLUSTER_NODE_ID or str(uuid.uuid4()),
                ip="0.0.0.0",
                model=MODEL_NAME,
                role=CLUSTER_ROLE,
                mode="auto"
            )
            app.state.cluster_node = node
            agent = UniversalAgent(auto_load_skills=True, enable_evolution=False)
            app.state.agent = agent
            async def task_worker():
                while True:
                    if node.pending_tasks:
                        task_id = node.pending_tasks.pop(0)
                        node.start_task(task_id)
                        task = node.tasks[task_id]
                        try:
                            loop = asyncio.get_running_loop()
                            result = await loop.run_in_executor(
                                None,
                                lambda: agent._execute_skill(task["task_type"], task["parameters"])
                            )
                            node.complete_task(task_id, result)
                            if node.connection:
                                try:
                                    update_msg = create_task_update(
                                        task_id=task_id,
                                        status="completed",
                                        result=result
                                    )
                                    node.connection.sendall(update_msg.serialize())
                                except Exception as e:
                                    print(f"发送任务完成状态失败: {e}")
                        except Exception as e:
                            node.fail_task(task_id, str(e))
                            if node.connection:
                                try:
                                    update_msg = create_task_update(
                                        task_id=task_id,
                                        status="failed",
                                        error=str(e)
                                    )
                                    node.connection.sendall(update_msg.serialize())
                                except Exception as e2:
                                    print(f"发送任务失败状态失败: {e2}")
                        node.notify_status_change(task_id)
                    else:
                        await asyncio.sleep(0.2)
            asyncio.create_task(task_worker())
            client = ClusterClient()
            node_info = {
                "node_id": node.node_id,
                "model": MODEL_NAME,
                "role": "worker",
                "mode": "auto"
            }
            try:
                loop = asyncio.get_event_loop()
                success = await asyncio.wait_for(
                    loop.run_in_executor(None, client.join, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT, node_info),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                success = False
                print("Worker 连接 manager 超时（5秒），集群功能不可用，将运行在单机模式")
            except Exception as e:
                success = False
                print(f"Worker 连接 manager 失败: {e}")
            if success:
                node.connection = client.socket
                def listener():
                    while True:
                        try:
                            data = node.connection.recv(4096)
                            if not data:
                                break
                            msg = json.loads(data.decode('utf-8'))
                            msg_type = msg.get("type")
                            if msg_type == "task_assignment":
                                payload = msg.get("payload", {})
                                node.receive_assignment(
                                    task_id=payload["task_id"],
                                    task_type=payload["task_type"],
                                    description=payload["description"],
                                    parameters=payload.get("parameters")
                                )
                            else:
                                print(f"Worker 收到其他消息类型: {msg_type}")
                        except Exception as e:
                            print(f"Worker 监听线程异常: {e}")
                            break
                threading.Thread(target=listener, daemon=True).start()
                def heartbeat_loop():
                    while True:
                        try:
                            if node.connection:
                                hb = create_heartbeat(
                                    node.node_id,
                                    {
                                        "load_cpu": node.load_cpu,
                                        "load_memory": node.load_memory,
                                        "queue_length": len(node.pending_tasks)
                                    }
                                )
                                node.connection.sendall(hb.serialize())
                        except Exception as e:
                            print(f"心跳发送失败: {e}")
                            break
                        time.sleep(5)
                threading.Thread(target=heartbeat_loop, daemon=True).start()
                print("✅ Worker 已加入集群（懒加载）")
            else:
                print("Worker 加入集群失败（懒加载），将运行在单机模式")
            _cluster_initialized = True
            return success
        else:
            _cluster_initialized = True
            return True
    finally:
        lock.release()


@app.get("/api/models")
async def list_models(force_reload: bool = False):
    """列出所有模型配置"""
    try:
        if force_reload:
            config_manager.load_configs()
        filtered_configs = []
        for cfg in config_manager.configs:
            cfg_dict = cfg.to_dict()
            cfg_dict['is_current'] = config_manager.current_config and config_manager.current_config.name == cfg.name
            cfg_dict['has_api_key'] = bool(cfg.api_key)
            filtered_configs.append(cfg_dict)
        current = config_manager.current_config
        return {
            "success": True,
            "models": filtered_configs,
            "current_config": current.name if current else None
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/save_model")
async def save_model(
    name: str = Form(...),
    provider: str = Form(...),
    model_name: str = Form(...),
    api_base: str = Form(...),
    api_key: str = Form(""),
    original_name: str = Form("")
):
    """新增或更新模型配置"""
    try:
        name = name.strip()
        original_name = original_name.strip()
        provider_type = ProviderType(provider) if isinstance(provider, str) else provider
        config = ModelConfig(
            provider=provider_type,
            name=name,
            model_name=model_name.strip(),
            api_base=api_base.strip(),
            api_key=api_key.strip()
        )
        
        # 如果提供了原始名称，先用原始名称查找现有配置
        if original_name:
            existing = config_manager.get_config(original_name)
            if existing:
                # 如果名称变了，先删除旧的，再添加新的
                if original_name != name:
                    config_manager.delete_config(original_name)
                    config_manager.add_config(config)
                else:
                    config_manager.update_config(config)
            else:
                config_manager.add_config(config)
        else:
            # 没有原始名称，用新名称查找
            existing = config_manager.get_config(name)
            if existing:
                config_manager.update_config(config)
            else:
                config_manager.add_config(config)
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/switch_model")
async def switch_model(request: Request):
    """切换当前模型 - 同步更新cluster相关的所有模型信息"""
    try:
        data = await request.json()
        name = data.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="缺少配置名称")
        config = config_manager.get_config(name)
        if not config:
            raise HTTPException(status_code=404, detail="配置不存在")
        config_manager.set_current(name)
        
        # 同步更新Cluster相关模型信息，确保房间内模型正确调用
        manager = getattr(app.state, "cluster_manager", None)
        node = getattr(app.state, "cluster_node", None)
        new_model_name = config.model_name
        
        if node:
            node.model = new_model_name
            logger.info(f"🔄 节点模型已同步更新为: {new_model_name}")
        
        if manager:
            manager.owner_model = new_model_name
            # 更新房主节点模型
            if manager.own_node:
                manager.own_node.model = new_model_name
            # 更新房主在room_members中的模型信息
            for member_id, member_info in manager.room_members.items():
                if member_info.get("is_owner"):
                    manager.room_members[member_id]["model"] = new_model_name
                    logger.info(f"🔄 房主成员模型已同步更新为: {new_model_name}")
                    break
            # 更新UDP广播中的房主模型信息
            if manager.discovery:
                manager.discovery.update_room_info(
                    room_name=manager.room_name,
                    room_id=manager.room_id,
                    extra_info={
                        "owner_name": manager.owner_name,
                        "owner_model": new_model_name
                    }
                )
                logger.info(f"🔄 UDP广播房主模型已同步更新为: {new_model_name}")
        
        logger.info(f"✅ 模型切换完成，全部相关信息已同步: {name} -> {new_model_name}")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换模型时出错: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.post("/api/delete_model")
async def delete_model(request: Request):
    """删除模型配置"""
    try:
        data = await request.json()
        name = data.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="缺少配置名称")
        configs = config_manager.configs
        new_configs = [cfg for cfg in configs if cfg.name != name]
        if len(new_configs) == len(configs):
            raise HTTPException(status_code=404, detail="配置不存在")
        config_manager.configs = new_configs
        config_manager.save_configs()
        if config_manager.current_config and config_manager.current_config.name == name:
            if new_configs:
                config_manager.set_current(new_configs[0].name)
            else:
                config_manager.current_config = None
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/ollama_models")
async def list_ollama_models():
    """获取Ollama中已下载的模型列表 - 静默失败模式，无警告"""
    import requests
    ollama_url = "http://localhost:11434/api/tags"
    try:
        response = requests.get(ollama_url, timeout=3)
        response.raise_for_status()
        data = response.json()
        models = [{"name": m["name"], "model": m["name"], "modified_at": m.get("modified_at"), "size": m.get("size")} for m in data.get("models", [])]
        return {"success": True, "models": models}
    except Exception:
        # 静默失败，完全不输出警告，因为很多用户根本不使用本地Ollama服务
        return {"success": False, "models": []}

@app.get("/api/all_models")
async def list_all_models():
    """获取所有可用的模型选项（优先从model_config.json读取，包括Ollama本地模型）"""
    try:
        all_models = []
        
        # 优先读取已配置的所有模型（包括Ollama和API，无论是否有api_key）
        configs = config_manager.list_configs()
        for cfg in configs:
            all_models.append({
                "name": cfg["name"],
                "model": cfg["model"],
                "type": "config",
                "provider": cfg["provider"],
                "has_api_key": cfg.get("has_api_key", False),
                "size": None,
                "modified_at": None
            })
        
        # 获取Ollama本地模型，补充到列表中（避免重复）
        ollama_models = await list_ollama_models()
        existing_model_names = {m["model"] for m in all_models}
        if ollama_models.get("success"):
            for m in ollama_models["models"]:
                if m["name"] not in existing_model_names:
                    all_models.append({
                        "name": m["name"],
                        "model": m["model"],
                        "type": "ollama",
                        "provider": "ollama",
                        "has_api_key": False,
                        "size": m.get("size"),
                        "modified_at": m.get("modified_at")
                    })
        
        # 获取当前配置
        current = config_manager.current_config
        current_model_name = current.model_name if current else None
        
        return {
            "success": True,
            "models": all_models,
            "current_model": current_model_name,
            "total_count": len(all_models)
        }
    except Exception as e:
        logger.error(f"获取所有模型列表失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "models": []}

# ==================== API：对话历史管理 ====================
@app.get("/api/conversations")
async def list_conversations(limit: int = 20):
    """列出对话历史"""
    try:
        convs = conv_manager.list_conversations(limit=limit)
        return {"success": True, "conversations": convs}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """获取对话详情"""
    try:
        success = conv_manager.load_conversation(conversation_id)
        if not success or conv_manager.current_conversation is None:
            raise HTTPException(status_code=404, detail="对话不存在")
        return {"success": True, "conversation": conv_manager.current_conversation.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/conversation")
async def create_or_load_conversation(request: Request):
    """创建新对话或加载现有对话"""
    try:
        data = await request.json()
        conversation_id = data.get("conversation_id")
        if conversation_id:
            success = conv_manager.load_conversation(conversation_id)
            if not success or conv_manager.current_conversation is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            return {"success": True, "conversation": conv_manager.current_conversation.to_dict(), "action": "loaded"}
        else:
            new_id = conv_manager.new_conversation()
            conv = conv_manager.current_conversation
            return {"success": True, "conversation": conv.to_dict(), "action": "created", "conversation_id": new_id}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/conversation/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: str):
    """删除整个对话"""
    try:
        conv_manager.delete_conversation(conversation_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/conversation/clear")
async def clear_current_conversation():
    """清空当前对话（创建新对话）"""
    try:
        new_id = conv_manager.clear_conversation()
        return {"success": True, "conversation_id": new_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== API：Token数据统计（协作模式可用） ====================
@app.get("/api/stats/tokens")
async def get_token_stats():
    """获取token使用统计 - 协作模式下数据统计功能"""
    try:
        from token_tracker import token_tracker
        stats = token_tracker.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"获取token统计失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# ==================== API：核心功能（新增） ====================

@app.get("/api/skills")
async def api_skills():
    """获取已加载的技能列表"""
    try:
        agent = get_agent()
        skills = []
        if hasattr(agent, 'skills_registry') and agent.skills_registry:
            if hasattr(agent.skills_registry, 'list_skills'):
                for name, func in agent.skills_registry.list_skills().items():
                    desc = func.__doc__ or ""
                    skills.append({"name": name, "description": desc.strip()})
            else:
                # 回退：使用 get_openai_schemas
                schemas = agent.skills_registry.get_openai_schemas()
                for s in schemas:
                    skills.append({
                        "name": s["function"]["name"],
                        "description": s["function"]["description"]
                    })
        return {"success": True, "skills": skills}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/chat")
async def api_chat(request: Request):
    """处理用户消息，返回回复 - 增强容错版：即使模型无回复也保证后续功能可用"""
    try:
        data = await request.json()
        message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        if not message:
            raise HTTPException(status_code=400, detail="消息不能为空")
        
        # 1. 确保对话管理器状态完整，避免后续导出/历史功能异常
        if conversation_id:
            conv_manager.load_conversation_or_create(conversation_id)
        # 确保当前对话对象一定存在
        if not conv_manager.current_conversation:
            conv_manager.new_conversation()
        
        # 2. 记录用户消息（无论后续模型调用成功与否，都先存下来）
        conv_manager.add_user_message(message)
        
        response = ""
        agent = get_agent()
        # 3. 使用异步执行模型调用，带完整容错
        try:
            import asyncio
            response = await asyncio.to_thread(agent._process_simple, message)
        except Exception as model_error:
            logger.warning(f"⚠️ 模型调用出现异常: {model_error}，但对话仍可正常保存")
            # 生成友好的空回复提示，避免完全没有助手消息
            response = f"【模型暂时无法回复】\n错误信息: {str(model_error)}"
        
        # 4. 确保助手消息无论如何都添加，保证导出/统计/历史功能不会失败
        conv_manager.add_assistant_message(response)
        conv_manager.save_current()
        
        return {"success": True, "response": response, "conversation_id": conv_manager.current_conversation.conversation_id}
    except Exception as e:
        logger.error(f"API chat error: {e}", exc_info=True)
        # 极端场景下的保底：确保API返回格式正确
        return {"success": False, "error": str(e)}

@app.get("/api/memory")
async def api_memory():
    """获取核心记忆列表"""
    try:
        agent = get_agent()
        memories = []
        if hasattr(agent, 'memory'):
            if hasattr(agent.memory, 'get_all_core_memory'):
                raw_memories = agent.memory.get_all_core_memory()
                for key, value in raw_memories.items():
                    memories.append({"key": key, "value": value})
            elif hasattr(agent.memory, 'get_core_memory'):
                raw = agent.memory.get_core_memory()
                if isinstance(raw, dict):
                    for key, value in raw.items():
                        memories.append({"key": key, "value": value})
        return {"success": True, "memories": memories}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/token-stats")
async def api_token_stats():
    """获取 token 使用统计"""
    try:
        stats = {
            "total": {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0},
            "by_model": [],
            "by_date": []
        }
        agent = get_agent()
        if hasattr(agent, 'token_tracker'):
            tracker = agent.token_tracker
            if hasattr(tracker, 'get_total_usage'):
                total = tracker.get_total_usage()
                stats["total"] = {
                    "total_tokens": total.get("total_tokens", 0),
                    "prompt_tokens": total.get("prompt_tokens", 0),
                    "completion_tokens": total.get("completion_tokens", 0)
                }
            if hasattr(tracker, 'get_usage_by_model'):
                stats["by_model"] = tracker.get_usage_by_model()
        return {"success": True, "data": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/export")
async def api_export():
    """导出当前对话为 Markdown - 修复版"""
    try:
        conv = conv_manager.current_conversation
        if not conv:
            raise HTTPException(status_code=404, detail="当前无对话")

        # 使用Conversation类内置的导出方法，确保兼容性和完整性
        content = conv.export_as_markdown()

        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=conversation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"}
        )
    except Exception as e:
        logger.error(f"Markdown导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

@app.get("/api/export/json")
async def api_export_json():
    """导出当前对话为 JSON - 修复版"""
    try:
        conv = conv_manager.current_conversation
        if not conv:
            raise HTTPException(status_code=404, detail="当前无对话")

        # 使用Conversation类内置的导出方法，彻底解决序列化问题
        json_content = conv.export_as_json()

        return Response(
            content=json_content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=conversation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"}
        )
    except Exception as e:
        logger.error(f"JSON导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

# API 统计类
class ApiStatistics:
    def __init__(self):
        self.start_time = datetime.now()
        self.requests = {}
        self.total_requests = 0
        self.total_errors = 0
        self.response_times = {}
        self.model_calls = {}
    
    def record_request(self, endpoint, status_code, response_time):
        self.total_requests += 1
        if endpoint not in self.requests:
            self.requests[endpoint] = {"success": 0, "error": 0, "total_time": 0, "count": 0}
        if status_code >= 200 and status_code < 400:
            self.requests[endpoint]["success"] += 1
        else:
            self.requests[endpoint]["error"] += 1
            self.total_errors += 1
        self.requests[endpoint]["total_time"] += response_time
        self.requests[endpoint]["count"] += 1
    
    def record_model_call(self, model_name, success, response_time):
        if model_name not in self.model_calls:
            self.model_calls[model_name] = {"success": 0, "error": 0, "total_time": 0, "count": 0}
        if success:
            self.model_calls[model_name]["success"] += 1
        else:
            self.model_calls[model_name]["error"] += 1
        self.model_calls[model_name]["total_time"] += response_time
        self.model_calls[model_name]["count"] += 1
    
    def get_stats(self):
        uptime = (datetime.now() - self.start_time).total_seconds()
        stats = {
            "uptime": uptime,
            "uptime_formatted": self.format_uptime(uptime),
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "success_rate": (self.total_requests - self.total_errors) / max(self.total_requests, 1) * 100,
            "requests_by_endpoint": {},
            "model_calls": {}
        }
        
        for endpoint, data in self.requests.items():
            avg_time = data["total_time"] / max(data["count"], 1)
            stats["requests_by_endpoint"][endpoint] = {
                "count": data["count"],
                "success": data["success"],
                "error": data["error"],
                "success_rate": data["success"] / max(data["count"], 1) * 100,
                "avg_response_time_ms": avg_time * 1000
            }
        
        for model, data in self.model_calls.items():
            avg_time = data["total_time"] / max(data["count"], 1)
            stats["model_calls"][model] = {
                "count": data["count"],
                "success": data["success"],
                "error": data["error"],
                "success_rate": data["success"] / max(data["count"], 1) * 100,
                "avg_response_time_ms": avg_time * 1000
            }
        
        return stats
    
    def format_uptime(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}小时{minutes}分钟{secs}秒"

api_stats = ApiStatistics()

@app.get("/api/stats")
async def get_api_stats():
    """获取API统计数据"""
    return {"success": True, "data": api_stats.get_stats()}

# ============================================
# 局域网房间发现 API
# ============================================
@app.post("/api/discovery/start_scan")
async def start_discovery_scan():
    """启动局域网房间扫描"""
    global _discovery_instance
    try:
        if not _discovery_instance:
            _discovery_instance = ClusterDiscovery(port=50005)
        _discovery_instance.start_scanning()
        return {"success": True, "message": "扫描已启动"}
    except Exception as e:
        logger.error(f"启动扫描失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/api/discovery/rooms")
async def get_discovered_rooms():
    """获取局域网中发现的所有房间"""
    global _discovery_instance
    try:
        if not _discovery_instance:
            return {"success": True, "rooms": []}
        rooms = _discovery_instance.get_available_rooms()
        return {"success": True, "rooms": rooms}
    except Exception as e:
        logger.error(f"获取发现房间失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "rooms": []}

@app.post("/api/discovery/stop")
async def stop_discovery():
    """停止发现服务"""
    global _discovery_instance
    try:
        if _discovery_instance:
            _discovery_instance.stop()
        return {"success": True, "message": "发现服务已停止"}
    except Exception as e:
        logger.error(f"停止发现失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def find_available_port(start_port: int, max_attempts: int = 10, host: str = "0.0.0.0") -> int:
    """查找可用端口"""
    import socket
    for i in range(max_attempts):
        port = start_port + i
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except socket.error:
                continue
    return start_port

if __name__ == "__main__":
    import uvicorn
    from config import WEB_HOST, WEB_PORT

    available_port = find_available_port(WEB_PORT, host=WEB_HOST)
    if available_port != WEB_PORT:
        print(f"⚠️ 端口 {WEB_PORT} 已被占用，自动切换到端口 {available_port}")

    print(f"🚀 启动玄枢 Web 服务：http://{WEB_HOST}:{available_port}")
    try:
        uvicorn.run("web_app:app", host=WEB_HOST, port=available_port, reload=False)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
