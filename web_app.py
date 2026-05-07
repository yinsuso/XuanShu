
import os

# === 安全审批模块（SQLite 持久化 + API 扩展） ===
import sqlite3
import json
import time
from threading import Lock
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import WEB_APP_URL,  APPROVAL_API_TOKEN,  APPROVAL_DB_PATH,  PROJECT_ROOT, CAPABILITY_MODEL_RANKINGS, SCHEDULER_STRATEGY, MANAGER_MONITOR_INTERVAL, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT
from evolution.cluster.capability import CapabilityAssessor
from evolution.cluster.scheduler import TaskScheduler

# ==================== 新增依赖：模型管理与对话历史 ====================
from fastapi import Form
from model_providers import config_manager, ModelConfig, ProviderType
from conversation_manager import get_global_conversation_manager

# 全局对话管理器实例（用于 API 处理）
conv_manager = get_global_conversation_manager()


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
    logger.info("🚀 玄枢 Web 服务启动中...")
    yield
    # 关闭时：执行清理工作（如有）
    logger.info("🛑 玄枢 Web 服务关闭中...")

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
app.include_router(cluster_api.router, prefix='/cluster')

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
        db_path = Path(APPROVAL_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(APPROVAL_DB_PATH, check_same_thread=False)
        self.lock = Lock()
        self._init_db()

    def _init_db(self):
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
import uuid
import time
import threading
from agent import UniversalAgent
from config import CLUSTER_ENABLED, CLUSTER_ROLE, CLUSTER_NODE_ID, CLUSTER_NODE_NICKNAME, MODEL_NAME
from evolution.cluster.connection import ClusterNode, ClusterManager, ClusterClient
from evolution.cluster.cluster_api import verify_token, get_cluster_node
import asyncio

@app.get("/api/info")
async def get_info():
    """获取当前节点角色与状态"""
    if not CLUSTER_ENABLED:
        return {"role": "standalone", "message": "Cluster disabled"}
    role = CLUSTER_ROLE
    node = getattr(app.state, "cluster_node", None)
    if role == "manager":
        manager = getattr(app.state, "cluster_manager", None)
        if manager:
            room = manager.get_room_info()
            return {"role": "manager", "room": room}
        else:
            return {"role": "manager", "room": None}
    else:  # worker
        if node:
            return {
                "role": "worker",
                "node_id": node.node_id,
                "connected": node.connection is not None,
                "mode": node.mode,
                "model": node.model
            }
        else:
            return {"role": "worker", "connected": False}

@app.post("/api/rooms/create")
async def create_room(request: Request):
    """创建房间（仅 Manager）"""
    verify_token(request)
    if CLUSTER_ROLE != "manager":
        raise HTTPException(status_code=403, detail="仅 Manager 可创建房间")

    # 懒加载集群组件
    if CLUSTER_ENABLED:
        success = await ensure_cluster_initialized()
        if not success:
            raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    data = await request.json()
    room_name = data.get("room_name")
    owner_name = data.get("owner_name")
    model = data.get("model")
    password = data.get("password", "")  # 可选密码，默认空字符串
    if len(password) > 32:
        raise HTTPException(status_code=400, detail="密码长度不能超过32字符")
    if not all([room_name, owner_name, model]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    manager = app.state.cluster_manager
    node = getattr(app.state, "cluster_node", None)
    owner_node_id = node.node_id if node else None
    # 存储密码哈希（简化：内存存储，实际应加盐哈希）
    import hashlib
    password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
    room_id = manager.create_room(room_name, owner_name, model, owner_node_id=owner_node_id, password_hash=password_hash)
    return {"success": True, "room_id": room_id, "room_name": room_name}

@app.get("/api/rooms/current")
async def get_current_room(request: Request):
    """获取当前房间信息（仅 Manager）"""
    verify_token(request)
    if CLUSTER_ROLE != "manager":
        raise HTTPException(status_code=403, detail="仅 Manager 可查看")

    # 懒加载集群组件
    if CLUSTER_ENABLED:
        success = await ensure_cluster_initialized()
        if not success:
            raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    manager = app.state.cluster_manager
    info = manager.get_room_info()
    info["members_detail"] = manager.get_member_info()
    return info

@app.post("/api/rooms/join")
async def join_room(request: Request):
    """Worker 加入房间（触发 ClusterClient 连接）"""

    # 懒加载集群组件
    if CLUSTER_ENABLED:
        success = await ensure_cluster_initialized()
        if not success:
            raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    data = await request.json()
    host = data.get("host")
    port = data.get("port", 30001)
    name = data.get("name")
    mode = data.get("mode", "auto")
    model = data.get("model")
    if not all([host, name, model]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
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
                        logger.debug("Worker 监听线程收到其他消息", type=msg_type)
                except Exception as e:
                    logger.error("Worker 监听线程异常", error=str(e))
                    break
        threading.Thread(target=listener, daemon=True).start()
        def heartbeat_loop():
            while True:
                try:
                    if node.connection:
                        from evolution.cluster.protocol import create_heartbeat
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
                    logger.error("心跳发送失败", error=str(e))
                    break
                time.sleep(5)
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        return {"success": True, "message": "已加入房间"}
    else:
        raise HTTPException(status_code=500, detail="加入房间失败")

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

@app.post("/api/rooms/start_task")
async def start_task(request: Request):
    """Manager 开启协作任务（广播给所有成员）"""
    verify_token(request)
    if CLUSTER_ROLE != "manager":
        raise HTTPException(status_code=403, detail="仅 Manager 可")

    # 懒加载集群组件
    if CLUSTER_ENABLED:
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
    task_id = manager.start_collaborative_task(task_type, description, parameters)
    return {"success": True, "task_id": task_id}

async def ensure_cluster_initialized():
    """
    懒加载初始化集群组件。
    根据 CLUSTER_ROLE 执行 manager 或 worker 的初始化。
    返回 True 表示成功， False 表示失败（但不会阻塞启动）。
    """
    global _cluster_initialized
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
            logger.info("✅ [ClusterManager] 集群管理器已启动（懒加载）")
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
                                    logger.error("发送任务完成状态失败", error=str(e))
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
                                    logger.error("发送任务失败状态失败", error=str(e2))
                        node.notify_status_change(task_id)
                    else:
                        await asyncio.sleep(0.2)
            asyncio.create_task(task_worker())
            client = ClusterClient()
            node_info = {{
                "node_id": node.node_id,
                "model": MODEL_NAME,
                "role": "worker",
                "mode": "auto"
            }}
            try:
                loop = asyncio.get_event_loop()
                success = await asyncio.wait_for(
                    loop.run_in_executor(None, client.join, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT, node_info),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                success = False
                logger.warning("Worker 连接 manager 超时（5秒），集群功能不可用，将运行在单机模式")
            except Exception as e:
                success = False
                logger.error(f"Worker 连接 manager 失败: {e}")
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
                                payload = msg.get("payload", {{}})
                                node.receive_assignment(
                                    task_id=payload["task_id"],
                                    task_type=payload["task_type"],
                                    description=payload["description"],
                                    parameters=payload.get("parameters")
                                )
                            else:
                                logger.debug("Worker 收到其他消息类型", type=msg_type)
                        except Exception as e:
                            logger.error("Worker 监听线程异常", error=str(e))
                            break
                threading.Thread(target=listener, daemon=True).start()
                def heartbeat_loop():
                    while True:
                        try:
                            if node.connection:
                                hb = create_heartbeat(
                                    node.node_id,
                                    {{
                                        "load_cpu": node.load_cpu,
                                        "load_memory": node.load_memory,
                                        "queue_length": len(node.pending_tasks)
                                    }}
                                )
                                node.connection.sendall(hb.serialize())
                        except Exception as e:
                            logger.error("心跳发送失败", error=str(e))
                            break
                        time.sleep(5)
                threading.Thread(target=heartbeat_loop, daemon=True).start()
                logger.info("✅ Worker 已加入集群（懒加载）")
            else:
                logger.error("Worker 加入集群失败（懒加载），将运行在单机模式")
            _cluster_initialized = True
            return success
        else:
            _cluster_initialized = True
            return True
    finally:
        lock.release()


@app.get("/api/models")
async def list_models():
    """列出所有模型配置"""
    try:
        configs = config_manager.configs
        current = config_manager.current_config
        return {
            "success": True,
            "models": [cfg.to_dict() for cfg in configs],
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
    api_key: str = Form("")
):
    """新增或更新模型配置"""
    try:
        provider_type = ProviderType(provider) if isinstance(provider, str) else provider
        config = ModelConfig(
            provider=provider_type,
            name=name,
            model_name=model_name,
            api_base=api_base,
            api_key=api_key
        )
        existing = config_manager.get_config(name)
        if existing:
            config_manager.update_config(config)
        else:
            config_manager.add_config(config)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/switch_model")
async def switch_model(name: str = Form(...)):
    """切换当前模型"""
    try:
        config = config_manager.get_config(name)
        if not config:
            raise HTTPException(status_code=404, detail="配置不存在")
        config_manager.set_current(name)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
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
        conv = conv_manager.load_conversation(conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="对话不存在")
        return {"success": True, "conversation": conv.to_dict()}
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
            conv = conv_manager.load_conversation(conversation_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            return {"success": True, "conversation": conv.to_dict(), "action": "loaded"}
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
