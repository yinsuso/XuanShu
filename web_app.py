import os
import sys
import asyncio

# ==================== Windows asyncio Proactor 事件循环修复 ====================
# Python 3.13+ 在 Windows 上使用默认的 ProactorEventLoop 时存在已知问题：
# Exception in callback _ProactorBaseWritePipeTransport._loop_writing()
# AssertionError: assert f is self._write_fut
# 解决方案：强制使用 SelectorEventLoop（必须在其他模块导入前设置）
if sys.platform == 'win32':
    try:
        import asyncio
        from asyncio import SelectorEventLoop
        selector_loop = SelectorEventLoop()
        asyncio.set_event_loop(selector_loop)
        print("Windows平台：已强制切换到 SelectorEventLoop，避免 Proactor 事件循环问题")
    except Exception as e:
        print("设置 SelectorEventLoop 失败，可能仍会遇到 Proactor 问题: %s" % str(e))

import uuid
import json
import time
import queue
from threading import Lock
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum

from agent import UniversalAgent
import threading
from fastapi import Response
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import WEB_APP_URL,  APPROVAL_API_TOKEN,  APPROVAL_DB_PATH,  PROJECT_ROOT, CAPABILITY_MODEL_RANKINGS, SCHEDULER_STRATEGY, MANAGER_MONITOR_INTERVAL, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT, CLUSTER_WORKER_STATE_PATH
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

# ==================== Worker 房间状态持久化管理 ====================
def _ensure_data_dir_exists():
    """确保 data 目录存在"""
    data_dir = os.path.dirname(CLUSTER_WORKER_STATE_PATH)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

def save_worker_state(state: dict):
    """保存 Worker 房间连接状态到本地 JSON 文件"""
    try:
        _ensure_data_dir_exists()
        with open(CLUSTER_WORKER_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 [Worker持久化] 状态已保存到: {CLUSTER_WORKER_STATE_PATH}")
        return True
    except Exception as e:
        logger.error(f"❌ [Worker持久化] 保存失败: {e}")
        return False

def load_worker_state() -> dict:
    """从本地 JSON 文件加载 Worker 状态 - 智能分层机制：区分临时过渡状态和完全无效状态"""
    try:
        if not os.path.exists(CLUSTER_WORKER_STATE_PATH):
            return {}
        # 先读取文件内容，检查是否为空
        with open(CLUSTER_WORKER_STATE_PATH, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            logger.info(f"📂 [Worker持久化] 状态文件为空，返回空状态")
            return {}
        # 解析JSON
        state = json.loads(content)
        
        # ============== 智能分层校验逻辑 ==============
        # 第一层：完全无效状态 → 必须清空
        # 条件：既没有 host/port，又没有 in_room 标记 → 说明是完全无效的残留
        is_completely_invalid = (
            not state.get("host") and
            not state.get("port") and
            not state.get("in_room")
        )
        if is_completely_invalid:
            logger.info(f"📂 [Worker持久化] 检测到完全无效的残留状态，自动清理")
            clear_worker_state()
            return {}
        
        # 第二层：临时过渡状态 → 允许保留，成员刚加入房间还在等房主推送完整信息
        # 条件：有 host、port、in_room=True，即使 room_id 是 pending-fetch 也允许
        is_transition_state = (
            state.get("in_room") is True and
            state.get("host") and
            state.get("port") and
            state.get("name")  # 成员有自己的花名
        )
        if is_transition_state:
            logger.info(f"📂 [Worker持久化] 检测到临时过渡状态，保留等待房主同步完整信息")
            return state
        
        # 第三层：完全有效完整状态 → 正常使用
        logger.info(f"📂 [Worker持久化] 已加载状态，room_name={state.get('room_name', '未命名')}")
        return state
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ [Worker持久化] JSON解析失败，自动清理无效文件: {e}")
        clear_worker_state()
        return {}
    except Exception as e:
        logger.warning(f"⚠️ [Worker持久化] 加载失败，自动清理状态文件: {e}")
        clear_worker_state()
        return {}

def clear_worker_state():
    """清除 Worker 状态（退出房间时调用）"""
    try:
        if os.path.exists(CLUSTER_WORKER_STATE_PATH):
            os.remove(CLUSTER_WORKER_STATE_PATH)
            logger.info("🗑️ [Worker持久化] 房间连接状态已清除")
    except Exception as e:
        logger.warning(f"⚠️ [Worker持久化] 清除失败: {e}")

# ==================== 推拉结合混合架构：Worker端轻量级轮询兜底机制 ====================
_worker_polling_thread = None
_worker_polling_running = False
_worker_poll_fail_count = 0  # 连续失败计数器
_WORKER_POLL_MAX_FAILURES = 6  # 最大连续失败次数（每次间隔10-15秒，6次约60-90秒）
_WORKER_POLL_TIMEOUT = 10.0  # 单次请求超时时间（秒）

def _handle_room_dismissed_on_worker():
    """
    Worker端检测到房间已解散的处理函数 - 完整清理逻辑
    1. 清除本地持久化状态文件
    2. 重置内存中的协作模式标记
    3. 向WebSocket广播退出事件，通知前端跳转
    """
    logger.info("🏠 [Worker兜底轮询] 检测到房间已解散，触发自动退出协作模式")
    
    # 清除本地持久化状态
    clear_worker_state()
    
    # 重置内存中的协作模式标记
    node = getattr(app.state, "cluster_node", None)
    if node:
        if hasattr(node, 'connection') and node.connection:
            try:
                node.connection.close()
            except Exception:
                pass
            node.connection = None
        if hasattr(node, 'in_collab_mode'):
            node.in_collab_mode = False
        if hasattr(node, 'status'):
            node.status = "idle"
    
    # 向WebSocket广播房间解散事件，通知前端跳转回房间列表
    try:
        from evolution.cluster.cluster_api import broadcast_to_all_clients
        import asyncio
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(broadcast_to_all_clients({
            "type": "room_dismissed",
            "message": "与房主失去连接，已自动退出协作模式",
            "timestamp": time.time()
        }))
        new_loop.close()
        logger.info("✅ [Worker兜底轮询] 已向前端广播房间解散事件")
    except Exception as e_broadcast:
        logger.warning(f"⚠️ [Worker兜底轮询] 广播房间解散事件失败: {e_broadcast}")
    
    # 重置失败计数器
    global _worker_poll_fail_count
    _worker_poll_fail_count = 0
    
    logger.info("🏁 [Worker兜底轮询] 已完全退出协作模式，所有状态已清理")

def _is_room_valid(room_data: dict) -> bool:
    """
    检查房间信息是否有效（判断房主是否已解散房间）
    返回 True 表示房间有效，False 表示房间已解散或无效
    """
    if not room_data:
        logger.warning(f"[Worker兜底轮询] 房间数据为空")
        return False
    
    # 检查房间名称是否为默认值（房主解散后会重置为Default-Room）
    room_name = room_data.get("room_name", "")
    if room_name == "Default-Room" or room_name == "":
        logger.warning(f"[Worker兜底轮询] 检测到无效房间名称: {room_name}")
        return False
    
    # 检查房主名称是否存在
    owner_name = room_data.get("owner_name")
    if not owner_name or owner_name == "Unknown" or owner_name is None:
        logger.warning(f"[Worker兜底轮询] 检测到无效房主名称: {owner_name}")
        return False
    
    # 检查是否处于协作模式
    if not room_data.get("is_collab_mode", False):
        logger.warning(f"[Worker兜底轮询] 房主已退出协作模式: is_collab_mode={room_data.get('is_collab_mode')}")
        return False
    
    # 检查房间是否准备就绪
    if not room_data.get("room_ready", False):
        logger.warning(f"[Worker兜底轮询] 房间未就绪: room_ready={room_data.get('room_ready')}")
        return False
    
    return True

def _worker_room_info_polling_loop():
    """
    Worker端后台兜底轮询线程 - 推拉结合架构核心（增强版）
    
    核心功能：
    1. 每10秒尝试从房主拉取最新房间信息
    2. 检测房间是否已解散（通过房间名称、房主信息、协作模式状态判断）
    3. 连续失败计数机制：超过阈值自动退出协作模式
    4. 确保本地持久化文件与房主100%同步
    
    触发自动退出的条件（任一满足）：
    - 连续6次轮询失败（约60秒）
    - 收到HTTP 200但房间信息无效（Default-Room、无房主名等）
    - HTTP连接超时、拒绝或其他网络异常累计超过阈值
    
    这是TCP房主推送机制的双重保险，即使TCP丢包/延迟也不会丢失房间解散信息
    严格使用成员加入房间时用户输入的房主真实内网IP，绝不使用默认127.0.0.1
    """
    import requests
    global _worker_poll_fail_count
    
    logger.info("✅ [Worker兜底轮询] 增强版轮询线程已启动，每10秒检测一次房间状态")
    
    while _worker_polling_running:
        try:
            # 先从本地加载当前持久化状态，检查是否在协作模式
            current_state = load_worker_state()
            if not current_state or not current_state.get("in_room"):
                # 当前不在协作模式，直接等待下一轮，重置失败计数
                _worker_poll_fail_count = 0
                # 使用与正常轮询相同的间隔，保持一致性
                time.sleep(10)
                continue
            
            # 从状态获取房主的连接信息 - 100%使用用户加入房间时输入的真实内网IP
            host = current_state.get("host")
            port = current_state.get("port")
            current_room_name = current_state.get("room_name", "")
            
            # 严格校验：host和port必须都存在，跳过无效状态
            if not host or not port:
                logger.debug(f"[Worker兜底轮询] 房主host/port信息不完整，跳过本次轮询")
                # 注意：这里只是跳过，不增加失败计数（因为还没有真正尝试连接）
                # 失败计数只应该在真正尝试连接但失败时才增加
                time.sleep(5)
                continue
            
            # 构建房主的API地址 - 完全使用用户输入的真实IP，绝不篡改
            # 注意：HTTP API运行在Web端口，不是TCP端口
            http_port = port - 1  # TCP端口-1 = HTTP端口（30001 → 30000）
            manager_base_url = f"http://{host}:{http_port}"
            
            # 尝试调用房主的 /api/rooms/current API 获取最新完整房间信息
            try:
                poll_url = f"{manager_base_url}/api/rooms/current"
                logger.debug(f"[Worker兜底轮询] 正在调用房主API: {poll_url}")
                resp = requests.get(poll_url, timeout=_WORKER_POLL_TIMEOUT)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        logger.debug(f"[Worker兜底轮询] 收到房主响应: room_name={data.get('room_name')}, is_collab_mode={data.get('is_collab_mode')}, room_ready={data.get('room_ready')}")
                        
                        # 检查房间信息是否有效（房主是否已解散房间）
                        if not _is_room_valid(data):
                            logger.warning(f"⚠️ [Worker兜底轮询] 检测到房间已解散: room_name={data.get('room_name')}, owner_name={data.get('owner_name')}")
                            _handle_room_dismissed_on_worker()
                            time.sleep(10)
                            continue
                        
                        # 获取到房主最新房间信息，更新本地持久化文件
                        updated_state = current_state.copy()
                        updated_state.update({
                            "in_room": True,
                            "room_name": data.get("room_name", updated_state.get("room_name", "")),
                            "room_id": data.get("room_id", updated_state.get("room_id", "")),
                            "owner_name": data.get("owner_name", updated_state.get("owner_name", "")),
                            "owner_model": data.get("owner_model", updated_state.get("owner_model", "")),
                            "members_detail": data.get("members_detail", updated_state.get("members_detail", [])),
                            "polled_at": time.time()
                        })
                        save_worker_state(updated_state)
                        
                        # 重置失败计数器（轮询成功）
                        _worker_poll_fail_count = 0
                        logger.debug(f"🔄 [Worker兜底轮询] 成功同步房间信息: {data.get('room_name', 'unknown')}")
                        
                    except json.JSONDecodeError as e_json:
                        logger.warning(f"⚠️ [Worker兜底轮询] 解析房主响应失败: {e_json}")
                        _worker_poll_fail_count += 1
                else:
                    # HTTP状态码不为200，可能房主已关闭或状态异常
                    logger.warning(f"⚠️ [Worker兜底轮询] 房主返回异常状态码: {resp.status_code}")
                    _worker_poll_fail_count += 1
                    
            except requests.exceptions.RequestException as e_req:
                # 网络异常（房主不可达、超时、拒绝连接等）
                _worker_poll_fail_count += 1
                logger.warning(f"⏳ [Worker兜底轮询] 房主 {host}:{port} 暂时不可达 ({_worker_poll_fail_count}/{_WORKER_POLL_MAX_FAILURES}): {type(e_req).__name__}: {str(e_req)[:50]}")
            
            # 检查连续失败次数是否超过阈值
            if _worker_poll_fail_count >= _WORKER_POLL_MAX_FAILURES:
                # 智能判定：先检查TCP连接是否仍然活跃
                node = getattr(app.state, "cluster_node", None)
                tcp_connected = False
                if node and hasattr(node, 'connection') and node.connection:
                    try:
                        # 尝试发送一个空探测包来检查连接是否活跃
                        node.connection.send(b'')
                        tcp_connected = True
                    except Exception:
                        # TCP连接已断开
                        tcp_connected = False
                
                if tcp_connected:
                    # TCP连接仍然活跃，只是HTTP轮询失败，不应该退出
                    logger.warning(f"⚠️ [Worker兜底轮询] HTTP轮询连续失败 {_WORKER_POLL_MAX_FAILURES} 次，但TCP连接仍活跃，继续保持协作模式")
                    _worker_poll_fail_count = 0  # 重置计数器，继续尝试
                else:
                    # TCP连接也断开了，才真正判定失去连接
                    logger.warning(f"❌ [Worker兜底轮询] 连续失败 {_WORKER_POLL_MAX_FAILURES} 次，且TCP连接已断开，判定与房主失去连接 (当前计数: {_worker_poll_fail_count})")
                    _handle_room_dismissed_on_worker()
                    _worker_poll_fail_count = 0
            
        except Exception as e_global:
            logger.error(f"❌ [Worker兜底轮询] 循环异常: {e_global}", exc_info=True)
            _worker_poll_fail_count += 1
            
            # 异常情况下也检查失败次数（同样遵循智能判定）
            if _worker_poll_fail_count >= _WORKER_POLL_MAX_FAILURES:
                node = getattr(app.state, "cluster_node", None)
                tcp_connected = False
                if node and hasattr(node, 'connection') and node.connection:
                    try:
                        node.connection.send(b'')
                        tcp_connected = True
                    except Exception:
                        tcp_connected = False
                
                if tcp_connected:
                    logger.warning(f"⚠️ [Worker兜底轮询] 循环连续异常 {_WORKER_POLL_MAX_FAILURES} 次，但TCP连接仍活跃，继续保持协作模式")
                    _worker_poll_fail_count = 0
                else:
                    logger.warning(f"❌ [Worker兜底轮询] 连续异常 {_WORKER_POLL_MAX_FAILURES} 次，且TCP连接已断开，触发自动退出")
                    _handle_room_dismissed_on_worker()
                    _worker_poll_fail_count = 0
        
        # 等待10秒再进行下一次轮询（轻量级，不占用资源）
        time.sleep(10)

def start_worker_polling():
    """启动Worker端轻量级兜底轮询线程"""
    global _worker_polling_thread, _worker_polling_running
    if _worker_polling_thread and _worker_polling_thread.is_alive():
        logger.warning("[Worker兜底轮询] 线程已在运行，跳过重复启动")
        return
    _worker_polling_running = True
    _worker_polling_thread = threading.Thread(target=_worker_room_info_polling_loop, daemon=True)
    _worker_polling_thread.start()
    logger.info("✅ [推拉混合架构] Worker端轻量级兜底轮询线程已启动，每10秒同步一次房主房间信息")

def stop_worker_polling():
    """停止Worker端兜底轮询线程"""
    global _worker_polling_running
    _worker_polling_running = False
    logger.info("🛑 [推拉混合架构] Worker端兜底轮询线程已停止")

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
    """FastAPI 生命周期管理器：推拉混合架构完整版 + 异步对话系统"""
    print("🚀 玄枢 Web 服务启动中...")
    try:
        # ===== 修复：启动时绝对不清空持久化状态！ =====
        # 成员agent刷新web页面后需要从worker_room_state.json读取状态识别协作模式
        old_state = load_worker_state()
        if old_state and old_state.get("in_room"):
            logger.info(f"💾 [启动状态恢复] 检测到历史协作状态: room_name={old_state.get('room_name')}")
        else:
            logger.info("📂 无历史协作状态，正常启动")
    except Exception as e_clean:
        logger.warning(f"启动时加载协作状态失败: {e_clean}")
    
    # ===== 推拉混合架构：启动Worker端轻量级兜底轮询线程 =====
    start_worker_polling()
    
    # ===== 核心增强：启动异步对话后台工作线程 =====
    start_async_chat_worker()
    
    yield
    
    # ===== 关闭时：停止异步对话后台工作线程 =====
    stop_async_chat_worker()
    
    # ===== 关闭时：停止Worker端兜底轮询线程 =====
    stop_worker_polling()
    
    # 关闭时：不清空持久化状态，让用户下次启动/刷新还能恢复协作模式
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
from config import CLUSTER_ENABLED, CLUSTER_ROLE, CLUSTER_NODE_ID, CLUSTER_NODE_NICKNAME, MODEL_NAME, CLUSTER_API_TOKEN
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
    
    # 加载本地持久化状态
    saved_state = load_worker_state()
    
    # 基础响应对象，包含集群API Token（用于前端调用需要认证的API）
    base_response = {
        "cluster_token": CLUSTER_API_TOKEN if CLUSTER_API_TOKEN and CLUSTER_API_TOKEN != "please-change-me-to-a-secure-random-token-32-chars-min" else "",
        "current_model_name": current_model_name
    }
    
    if not CLUSTER_ENABLED:
        return {
            "role": "standalone", 
            "message": "Cluster disabled",
            **base_response
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
                **base_response
            }
        else:
            return {"role": "manager", "room": None, **base_response}
    else:  # worker
        # 核心修复：即使TCP连接断开，只要持久化状态表明已加入房间，就显示协作模式
        is_connected = False
        if node:
            is_connected = node.connection is not None
            # 从持久化状态补充信息
            if not saved_state.get("in_room", False):
                if hasattr(node, 'in_collab_mode') and node.in_collab_mode:
                    pass  # 内存已标记
                else:
                    node.in_collab_mode = False
            else:
                # 持久化状态有值，直接标记
                node.in_collab_mode = True
        else:
            # 没有node对象时也根据持久化状态判断
            pass
        
        # 关键判断：如果持久化状态表明已加入房间，则视为connected，确保前端协作模式显示
        if saved_state.get("in_room", False):
            return {
                "role": "worker",
                "node_id": saved_state.get("node_id", "") or (node.node_id if node else ""),
                "connected": True,  # 持久化有值，强制标记为已连接
                "mode": saved_state.get("mode", "auto"),
                "model": saved_state.get("model", "") or (node.model if node else ""),
                "host": saved_state.get("host", ""),
                "port": saved_state.get("port", 30001),
                "room_name": saved_state.get("room_name", ""),
                "room_id": saved_state.get("room_id", ""),
                "owner_name": saved_state.get("owner_name", ""),
                "owner_model": saved_state.get("owner_model", ""),
                "members_detail": saved_state.get("members_detail", []),
                "room_ready": True,
                **base_response
            }
        
        # 正常无持久化状态时返回原有逻辑
        if node:
            return {
                "role": "worker",
                "node_id": node.node_id,
                "connected": is_connected,
                "mode": node.mode,
                "model": node.model,
                **base_response
            }
        else:
            return {"role": "worker", "connected": False, **base_response}

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
        
        # 创建房间后启动房主UDP广播 - 优化流程：合并所有必要信息
        discovery = getattr(manager, 'discovery', None) or globals().get('_discovery_instance')
        if discovery:
            # 准备所有要广播的关键信息
            extra_info = {
                "owner_name": owner_name,
                "owner_model": model,
                "password_required": password_hash is not None
            }
            # 更新discovery的房间信息 - 合并到持久化字典
            discovery.update_room_info(room_name=room_name, room_id=room_id, extra_info=extra_info)
            # 如果广播还没启动，再启动
            if not discovery.broadcasting:
                discovery.start_hosting(extra_info=extra_info)
            logger.info(f"📢 UDP广播已启动，房间信息: {room_name}, 房主模型: {model}, 需要密码: {password_hash is not None}")
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
    """获取当前房间信息 - 增强版：Worker节点主动向房主同步完整房间信息"""
    
    saved_state = load_worker_state()
    is_in_collab_mode = saved_state.get("in_room", False)
    
    if is_in_collab_mode:
        is_transition_state = (
            not saved_state.get("room_id") or 
            saved_state.get("room_id") == "pending-fetch" or
            not saved_state.get("room_name") or 
            saved_state.get("room_name") == "协作房间" or
            saved_state.get("room_name") == "Default-Room" or
            not saved_state.get("owner_model") or
            saved_state.get("owner_model") == "unknown"
        )
        
        if is_transition_state:
            host = saved_state.get("host")
            port = saved_state.get("port")
            if host and port:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    async def _async_poll():
                        try:
                            import aiohttp
                            timeout = aiohttp.ClientTimeout(total=5)
                            async with aiohttp.ClientSession(timeout=timeout) as session:
                                http_port = port - 1  # TCP端口-1 = HTTP端口
                                poll_url = f"http://{host}:{http_port}/api/rooms/current"
                                async with session.get(poll_url) as resp:
                                    if resp.status == 200:
                                        return await resp.json()
                        except Exception:
                            pass
                        return None
                    master_info = await _async_poll()
                    if master_info and master_info.get("is_collab_mode"):
                        updated_state = saved_state.copy()
                        updated_state.update({
                            "in_room": True,
                            "room_name": master_info.get("room_name", updated_state.get("room_name", "")),
                            "room_id": master_info.get("room_id", updated_state.get("room_id", "")),
                            "owner_name": master_info.get("owner_name", updated_state.get("owner_name", "")),
                            "owner_model": master_info.get("owner_model", updated_state.get("owner_model", "")),
                            "members_detail": master_info.get("members_detail", updated_state.get("members_detail", [])),
                            "synced_at": time.time()
                        })
                        save_worker_state(updated_state)
                        logger.info(f"🔄 [Worker主动同步] 成功从房主拉取完整房间信息")
                        saved_state = updated_state
                except ImportError:
                    logger.debug("aiohttp不可用，跳过异步同步")
                except Exception as e_poll:
                    logger.debug(f"⏳ [Worker主动同步] 房主暂时不可达: {str(e_poll)[:50]}")
        
        # 最终返回信息（同步过或没同步过都至少有可用值）
        info = {
            "room_id": saved_state.get("room_id", ""),
            "room_name": saved_state.get("room_name", "协作房间"),
            "owner_name": saved_state.get("owner_name", "房主"),
            "owner_model": saved_state.get("owner_model", "unknown"),
            "members": saved_state.get("members_detail", []),
            "members_detail": saved_state.get("members_detail", []),
            "has_password": False,
            "total_members": len(saved_state.get("members_detail", [])),
            "room_ready": True,
            "is_collab_mode": True,
            "my_node_id": saved_state.get("node_id", ""),
            "my_name": saved_state.get("name", ""),
            "my_model": saved_state.get("model", "")
        }
        logger.info(f"📤 [Worker房间信息API] 返回协作房间信息: room_name={info.get('room_name')}")
    else:
        # 不是协作模式，走 Manager 的正常逻辑
        await ensure_cluster_initialized()
        manager = getattr(app.state, "cluster_manager", None)

        if not manager:
            return {"success": False, "error": "房间管理器未初始化"}

        info = manager.get_room_info()
        info["members_detail"] = manager.get_member_info()
        info["is_collab_mode"] = info.get("room_ready", False) and info.get("room_name", "") != "Default-Room"
        info["success"] = True  # 总是返回 success，即使房间是 Default-Room
    
    # 从 model_config.json 中读取所有模型配置，返回给前端下拉框
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
    # 补充 Ollama 模型到列表 - 静默模式
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
        pass  # 静默忽略所有Ollama相关错误
    
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
                        "has_password": r.get('password_required', False),
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
    from evolution.cluster.cluster_api import broadcast_to_all_clients

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
    
    # 【关键修复】先检查本地持久化状态：如果状态不完整或已有无效TCP连接，先全部清除干净
    saved_state = load_worker_state()
    if saved_state and not (node and node.connection):
        # 有残留持久化状态但没有有效的TCP连接，说明之前的状态是不完整的，直接清空
        logger.info("🔧 [JoinRoom] 检测到残留无效状态，正在清理...")
        clear_worker_state()
        if node:
            node.connection = None
            if hasattr(node, 'in_collab_mode'):
                node.in_collab_mode = False
    
    # 现在再检查：只有真正建立了有效TCP连接时才禁止重连
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
    join_success = False
    join_reason = "未知错误"
    try:
        loop = asyncio.get_event_loop()
        # 传递密码参数给 client.join()
        join_result = await asyncio.wait_for(
            loop.run_in_executor(None, client.join, host, port, node_info, password),
            timeout=8.0
        )
        if isinstance(join_result, tuple):
            join_success, join_reason = join_result
        else:
            join_success = join_result
            join_reason = "已加入" if join_success else "加入失败"
    except asyncio.TimeoutError:
        join_success = False
        join_reason = "连接超时"
        logger.error(f"❌ 连接房间 {host}:{port} 超时（8秒），请确认房主房间是否创建成功且网络可访问")
    except ConnectionRefusedError:
        join_success = False
        join_reason = "连接被拒绝"
        logger.error(f"❌ [ClusterClient] 连接被拒绝: {host}:{port}，请确认房主的房间已经创建成功")
    except Exception as e:
        join_success = False
        join_reason = str(e)
        logger.error(f"❌ Worker 连接 manager 失败: {e}")
    
    success = join_success

    if success:
        global _worker_poll_fail_count
        _worker_poll_fail_count = 0
        if node:
            node.connection = client.socket
            node.model = model
            node.status = "active"
            node.mode = mode
            # 在节点上标记已加入协作房间状态
            setattr(node, "in_collab_mode", True)
        
        # ==================== 核心修复1：立即保存完整的 Worker 状态到本地文件 ====================
        # 连接成功后，先把所有关键信息保存到持久化状态，防止在房主推送房间信息前闪退回加入房间页
        try:
            from model_providers import config_manager
            current_model_name = ""
            if config_manager and config_manager.current_config:
                current_model_name = config_manager.current_config.model_name
            saved_state = {
                "in_room": True,
                "node_id": node.node_id if node else "",
                "name": name,
                "mode": mode,
                "model": model or current_model_name,
                "host": host,
                "port": port,
                # 预填充初始值（后续房主会推送真实信息覆盖）
                "room_name": "协作房间",
                "room_id": "pending-fetch",
                "owner_name": "房主",
                "owner_model": "unknown",
                "members_detail": [],
                "saved_at": time.time()
            }
            save_worker_state(saved_state)
        except Exception as e_save:
            logger.warning(f"持久化状态保存警告: {e_save}")
        # =============================================================================
        
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
                    
                    logger.info(f"📩 [Worker TCP] 从房主收到事件: {msg_type}")
                    
                    # 核心：收到房主解散房间通知 - 第一时间清空本地状态
                    if msg_type == "room_dismissed":
                        logger.info(f"🏠 [Worker处理] 房主已解散房间，立即清空所有本地状态")
                        clear_worker_state()
                        if node:
                            try:
                                if client and client.socket:
                                    client.socket.close()
                            except:
                                pass
                            node.connection = None
                            if hasattr(node, "in_collab_mode"):
                                node.in_collab_mode = False
                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            new_loop.run_until_complete(broadcast_to_all_clients({
                                "type": "room_dismissed",
                                "message": "房主已解散房间，协作会话结束",
                                "timestamp": time.time()
                            }))
                            new_loop.close()
                        except:
                            pass
                        logger.info("✅ [Worker状态清理] 解散通知处理完成，已完全退出协作模式")
                        break
                    
                    # 核心：收到协作结束通知 - 第一时间清空本地状态
                    if msg_type == "collaboration_ended":
                        logger.info(f"🏁 [Worker处理] 协作会话结束，立即清空所有本地状态")
                        clear_worker_state()
                        if node:
                            try:
                                if client and client.socket:
                                    client.socket.close()
                            except:
                                pass
                            node.connection = None
                            if hasattr(node, "in_collab_mode"):
                                node.in_collab_mode = False
                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            new_loop.run_until_complete(broadcast_to_all_clients({
                                "type": "collaboration_ended",
                                "message": "所有成员已离开，协作会话结束",
                                "timestamp": time.time()
                            }))
                            new_loop.close()
                        except:
                            pass
                        logger.info("✅ [Worker状态清理] 协作结束通知处理完成，已完全退出协作模式")
                        break
                    
                    # 当收到房主推送的房间状态更新时，更新本地持久化状态，强制标记为 in_room=True
                    if msg_type == "room_info_update":
                        try:
                            room_info = msg.get("room_info", {})
                            updated_saved_state = load_worker_state()
                            updated_saved_state.update({
                                "in_room": True,
                                "room_name": room_info.get("room_name", ""),
                                "room_id": room_info.get("room_id", ""),
                                "owner_name": room_info.get("owner_name", ""),
                                "owner_model": room_info.get("owner_model", ""),
                                "members_detail": room_info.get("members_detail", []),
                                "saved_at": time.time()
                            })
                            save_worker_state(updated_saved_state)
                            logger.info(f"✅ [WebApp持久化] 房主推送房间信息更新成功，强制标记 in_room=True")
                            
                            # 【问题2修复】立即通过WebSocket向前端推送房间信息更新，避免等待轮询
                            asyncio.run_coroutine_threadsafe(
                                broadcast_to_all_clients({
                                    "type": "room_info_update",
                                    "room_info": room_info
                                }),
                                asyncio.get_event_loop()
                            )
                        except Exception as e_update:
                            logger.warning(f"更新房间状态持久化失败: {e_update}")
                    
                    # 【关键功能】任何从房主通过TCP发来的事件，直接通过本地WebSocket转发给Worker的浏览器
                    try:
                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                        import asyncio
                        # 在事件循环中执行，推送事件给当前Worker自己的浏览器
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(broadcast_to_all_clients(msg))
                            else:
                                loop.run_until_complete(broadcast_to_all_clients(msg))
                        except Exception:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            new_loop.run_until_complete(broadcast_to_all_clients(msg))
                            new_loop.close()
                        logger.info(f"📡 [Worker本地转发] 已将房主事件推送到本地浏览器")
                    except Exception as e:
                        logger.warning(f"转发房主事件到本地浏览器失败: {e}")
                    
                    if msg_type == "task_assignment":
                        payload = msg.get("payload", {})
                        if node:
                            node.receive_assignment(
                                task_id=payload["task_id"],
                                task_type=payload["task_type"],
                                description=payload["description"],
                                parameters=payload.get("parameters")
                            )
                    elif msg_type == "enter_collab_mode":
                        logger.info(f"🤝 [协作模式] 从房主收到进入协作模式广播，自动跳转协作对话页面")
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
        
        # 向本地浏览器客户端广播：成员成功进入房间，进入协作模式准备状态
        await broadcast_to_all_clients({
            "type": "joined_room_success",
            "name": name,
            "mode": mode,
            "model": model,
            "timestamp": time.time()
        })
            
        return {"success": True, "message": "已加入房间，进入协作模式", "in_collab_mode": True}
    else:
        # 根据join_reason判断抛出明确的错误
        if join_reason == "密码错误":
            raise HTTPException(status_code=401, detail="密码错误")
        else:
            raise HTTPException(status_code=500, detail=f"加入房间失败: {join_reason}")

@app.post("/api/rooms/leave")
async def leave_room(request: Request):
    """Worker 离开房间，退出协作模式 - 100% 彻底清理版本"""
    from evolution.cluster.cluster_api import broadcast_to_all_clients

    # 懒加载集群组件
    if CLUSTER_ENABLED:
        success = await ensure_cluster_initialized()
        if not success:
            raise HTTPException(status_code=500, detail="集群未就绪，无法执行操作")
    
    node = getattr(app.state, "cluster_node", None)
    
    # 【核心强化1】无论如何都要彻底清除本地持久化状态文件
    clear_worker_state()
    
    # 【核心强化2】彻底重置内存中的所有相关标记
    if node:
        # 关闭并清除连接
        if hasattr(node, 'connection') and node.connection:
            try:
                node.connection.close()
            except Exception:
                pass
            node.connection = None
        
        # 重置所有协作模式相关属性
        if hasattr(node, 'in_collab_mode'):
            node.in_collab_mode = False
        if hasattr(node, 'status'):
            node.status = "idle"
        if hasattr(node, 'pending_tasks'):
            node.pending_tasks = []
        
        logger.info("🧹 [LeaveRoom] 内存中所有协作状态已彻底重置")
    
    # 【核心强化3】广播通知浏览器已成功退出
    await broadcast_to_all_clients({
        "type": "left_room_success",
        "timestamp": time.time()
    })
    
    logger.info("🚪 已完全退出协作房间，所有状态已彻底清理")
    return {"success": True, "message": "已退出房间，所有协作状态已完全清理"}

@app.post("/api/rooms/dismiss")
async def dismiss_room(request: Request):
    """房主解散房间 - 完整功能API端点：通知所有成员并重置房主自身状态"""
    from evolution.cluster.cluster_api import verify_token
    
    # 懒加载集群组件
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    if not manager:
        logger.error("解散房间失败：集群管理器未初始化")
        raise HTTPException(status_code=500, detail="集群管理器未初始化")
    
    # 调用ClusterManager的dismiss_room方法
    success = manager.dismiss_room()
    
    # 房主自己也要清空本地的任何可能残留的状态（虽然房主本身是Manager角色，没有worker状态文件）
    clear_worker_state()
    
    logger.info("🏠 房主解散房间操作已完成")
    return {
        "success": success, 
        "message": "房间已成功解散，所有成员已收到通知，房主状态已重置"
    }

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
    """Manager 开启协作任务（双保险广播给所有成员，让全体自动进入协作对话模式）- 协作持久化增强版"""
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
    
    # 双保险推送：第一步通过 manager.broadcast() 同时向远程TCP节点和本地浏览器WebSocket推送事件
    manager.broadcast({
        "type": "enter_collab_mode",
        "task_type": task_type,
        "description": description,
        "timestamp": time.time()
    })
    
    # 第二步：调用调度分配任务（会自动初始化协作对话并持久化所有消息）
    task_id = manager.start_collaborative_task(task_type, description, parameters)
    
    logger.info(f"🤝 [协作模式] 房主发起协作任务: task_id={task_id}, 描述={description}")
    
    # 第三步：返回协作对话ID，前端保存用于后续导出
    return {
        "success": True, 
        "task_id": task_id, 
        "message": "已向所有成员广播协作任务，全体自动进入协作对话模式",
        "collab_conversation_id": manager.collab_conversation_id
    }

@app.get("/api/rooms/collab/conversation")
async def get_collab_conversation():
    """获取当前协作对话信息（用于导出和加载）"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    
    if not manager:
        return {"success": False, "error": "集群未初始化"}
    
    return {
        "success": True,
        "collab_conversation_id": manager.collab_conversation_id,
        "collab_initialized": manager._collab_initialized,
        "message_count": len(manager.collab_messages)
    }

@app.post("/api/rooms/collab/add_message")
async def add_collab_message_api(request: Request):
    """外部API：手动添加一条协作消息（可选用于房主直接发送消息）"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    
    if not manager:
        return {"success": False, "error": "集群未初始化"}
    
    data = await request.json()
    role = data.get("role", "user")
    content = data.get("content", "")
    metadata = data.get("metadata", {})
    
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    success = manager.add_collab_message(role, content, metadata)
    return {"success": success}

# 导出协作对话专用版本 - 增强错误处理版
@app.get("/api/rooms/collab/export")
async def api_collab_export():
    """导出当前协作对话为 Markdown - 协作模式专用，直接导出本次协作内容"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    
    try:
        # 如果没有活跃协作对话但有collab_messages缓存，先生成一个虚拟导出
        if not manager:
            raise HTTPException(status_code=404, detail="集群管理器未初始化")
        
        # 如果没有协作对话ID，自动初始化它
        if not manager._collab_initialized or not manager.collab_conversation_id:
            manager._init_collab_conversation()
        
        # 确保 conv_mgr 加载的是协作对话
        collab_conv_id = manager.collab_conversation_id
        success_load = conv_manager.load_conversation(collab_conv_id)
        
        if not success_load or not conv_manager.current_conversation:
            # 对话不存在，重新创建一个新的协作对话
            from conversation_manager import ConversationType
            new_conv_id = conv_manager.new_conversation(
                initial_title=f"🤝 {manager.room_name or '协作房间'} - 协作对话",
                conversation_type=ConversationType.COLLABORATION
            )
            conv_manager._collab_current_id = new_conv_id
            manager.collab_conversation_id = new_conv_id
            manager._collab_initialized = True
            
            # 把已有的 collab_messages 恢复到新对话里
            for msg in manager.collab_messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    conv_manager.add_user_message(content)
                elif role == "assistant":
                    conv_manager.add_assistant_message(content)
            
            conv_manager.save_current()
        
        content = conv_manager.current_conversation.export_as_markdown()
        
        safe_room_name = "collab"
        if manager.room_name:
            safe_room_name = "".join([c for c in manager.room_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={safe_room_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"}
        )
    except Exception as e:
        logger.error(f"导出Markdown失败: {e}", exc_info=True)
        # 降级导出：直接从内存collab_messages生成markdown
        try:
            lines = []
            lines.append(f"# 协作对话记录")
            lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            lines.append("---")
            lines.append("")
            
            if manager and hasattr(manager, 'collab_messages'):
                for msg in manager.collab_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    ts = msg.get("timestamp", time.time())
                    time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S') if isinstance(ts, (int, float)) else str(ts)
                    
                    if role == "user":
                        lines.append(f"## 🧑 用户 ({time_str})")
                        lines.append("")
                        lines.append(content)
                        lines.append("")
                    elif role == "assistant":
                        lines.append(f"## 🤖 助手 ({time_str})")
                        lines.append("")
                        lines.append(content)
                        lines.append("")
                    elif role == "system":
                        lines.append(f"## 🔧 系统通知 ({time_str})")
                        lines.append("")
                        lines.append(content)
                        lines.append("")
            
            fallback_content = "\n".join(lines)
            return Response(
                content=fallback_content,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=collab-fallback-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"}
            )
        except Exception as e2:
            logger.error(f"降级导出Markdown也失败: {e2}")
            raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

@app.get("/api/rooms/collab/export/json")
async def api_collab_export_json():
    """导出当前协作对话为 JSON - 协作模式专用，直接导出本次协作内容"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    
    try:
        # 如果没有活跃协作对话但有collab_messages缓存，先生成
        if not manager:
            raise HTTPException(status_code=404, detail="集群管理器未初始化")
        
        # 如果没有协作对话ID，自动初始化它
        if not manager._collab_initialized or not manager.collab_conversation_id:
            manager._init_collab_conversation()
        
        # 确保 conv_mgr 加载的是协作对话
        collab_conv_id = manager.collab_conversation_id
        success_load = conv_manager.load_conversation(collab_conv_id)
        
        if not success_load or not conv_manager.current_conversation:
            # 对话不存在，重新创建一个新的协作对话
            from conversation_manager import ConversationType
            new_conv_id = conv_manager.new_conversation(
                initial_title=f"🤝 {manager.room_name or '协作房间'} - 协作对话",
                conversation_type=ConversationType.COLLABORATION
            )
            conv_manager._collab_current_id = new_conv_id
            manager.collab_conversation_id = new_conv_id
            manager._collab_initialized = True
            
            # 把已有的 collab_messages 恢复到新对话里
            for msg in manager.collab_messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    conv_manager.add_user_message(content)
                elif role == "assistant":
                    conv_manager.add_assistant_message(content)
            
            conv_manager.save_current()
        
        json_content = conv_manager.current_conversation.export_as_json()
        
        safe_room_name = "collab"
        if manager.room_name:
            safe_room_name = "".join([c for c in manager.room_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        
        return Response(
            content=json_content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={safe_room_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"}
        )
    except Exception as e:
        logger.error(f"导出JSON失败: {e}", exc_info=True)
        # 降级导出：直接从内存collab_messages生成JSON
        try:
            fallback_data = {
                "conversation_id": "fallback-collab",
                "title": "协作对话 (降级导出)",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "messages": [
                    {
                        "role": m.get("role"),
                        "content": m.get("content", ""),
                        "timestamp": datetime.fromtimestamp(m.get("timestamp", time.time())).isoformat() if isinstance(m.get("timestamp"), (int, float)) else str(m.get("timestamp", ""))
                    } for m in (manager.collab_messages if hasattr(manager, 'collab_messages') else [])
                ],
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "fallback": True
                }
            }
            
            fallback_json_str = json.dumps(fallback_data, ensure_ascii=False, indent=2)
            
            return Response(
                content=fallback_json_str,
                media_type="application/json; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=collab-fallback-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"}
            )
        except Exception as e2:
            logger.error(f"降级导出JSON也失败: {e2}")
            raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

@app.get("/api/rooms/collab/messages")
async def get_collab_messages_api():
    """获取当前协作对话的所有历史消息（前端刷新后恢复用）"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    
    if not manager or not manager._collab_initialized:
        return {
            "success": True,
            "messages": [],
            "message_count": 0
        }
    
    return {
        "success": True,
        "messages": manager.collab_messages,
        "collab_conversation_id": manager.collab_conversation_id,
        "message_count": len(manager.collab_messages)
    }

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
        # 第0步：在断开连接前，先向所有在线Worker发送房间解散通知，让Worker优雅地退出协作模式
        try:
            import json
            dismiss_msg = json.dumps({
                "type": "room_dismissed",
                "message": "房主已解散房间，协作会话结束",
                "timestamp": time.time()
            }).encode('utf-8')
            owner_node_id = manager.own_node.node_id if hasattr(manager, 'own_node') and manager.own_node else None
            sent_count = 0
            for nid, node in manager.nodes.items():
                if nid != owner_node_id and node.connection:
                    try:
                        node.connection.sendall(dismiss_msg)
                        sent_count += 1
                        logger.info(f"📢 [解散通知] 已通知成员节点 {nid[:8]} 房间即将解散")
                    except Exception as e_send:
                        logger.debug(f"向节点 {nid[:8]} 发送解散通知失败: {e_send}")
            logger.info(f"📢 已向 {sent_count} 个在线Worker发送房间解散通知")
            
            # 同时向本地浏览器WebSocket也广播房间解散事件
            from evolution.cluster.cluster_api import broadcast_to_all_clients
            await broadcast_to_all_clients({
                "type": "room_dismissed",
                "message": "房主已解散房间，协作会话结束",
                "timestamp": time.time()
            })
        except Exception as e_notify:
            logger.warning(f"广播房间解散通知时遇到问题: {e_notify}")
        
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
            manager.start_room_sync(interval=3)
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
            manager.start_room_sync(interval=3)
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
            global _global_cluster_client
            # 核心修复：Worker启动时优先从本地持久化状态恢复！
            saved_state = load_worker_state()
            logger.info(f"📂 [Worker启动恢复] 检测到持久化状态: in_room={saved_state.get('in_room', False)}")
            
            # 优先使用持久化状态中保存的node_id，避免每次重启生成完全不同的新节点ID
            saved_node_id = saved_state.get("node_id", "")
            if saved_node_id:
                logger.info(f"🔑 [Worker恢复] 使用历史节点ID: {saved_node_id[:8]}...")
                node = ClusterNode(
                    node_id=saved_node_id,
                    ip="0.0.0.0",
                    model=saved_state.get("model", MODEL_NAME),
                    role=CLUSTER_ROLE,
                    mode=saved_state.get("mode", "auto")
                )
            else:
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
            
            join_success = False
            
            # === 核心修复：如果持久化状态表明之前已加入房间，启动时自动尝试重连房主 ===
            if saved_state.get("in_room", False):
                try:
                    # 使用持久化保存的host和port信息
                    restore_host = saved_state.get("host", CLUSTER_MANAGER_HOST)
                    restore_port = saved_state.get("port", CLUSTER_MANAGER_PORT)
                    restore_name = saved_state.get("name", "未命名工作者")
                    restore_model = saved_state.get("model", MODEL_NAME)
                    
                    logger.info(f"🔄 [Worker自动重连] 正在从持久化状态恢复: {restore_host}:{restore_port}, 花名={restore_name}")
                    
                    from evolution.cluster.connection import ClusterClient
                    global _global_cluster_client
                    _global_cluster_client = ClusterClient(timeout=10.0)
                    
                    node_info = {
                        "node_id": node.node_id,
                        "name": restore_name,
                        "model": restore_model,
                        "role": "worker",
                        "mode": saved_state.get("mode", "auto")
                    }
                    
                    loop = asyncio.get_event_loop()
                    join_result = await asyncio.wait_for(
                        loop.run_in_executor(None, _global_cluster_client.join, restore_host, restore_port, node_info),
                        timeout=8.0
                    )
                    
                    if isinstance(join_result, tuple):
                        join_success, _ = join_result
                    else:
                        join_success = join_result
                    
                    if join_success:
                        node.connection = _global_cluster_client.socket
                        node.model = restore_model
                        node.status = "active"
                        node.mode = saved_state.get("mode", "auto")
                        setattr(node, "in_collab_mode", True)
                        
                        # 启动持久化状态恢复后的监听线程
                        def restore_listener():
                            while True:
                                try:
                                    if not _global_cluster_client or not _global_cluster_client.socket:
                                        break
                                    data = _global_cluster_client.socket.recv(8192)
                                    if not data:
                                        break
                                    msg = json.loads(data.decode('utf-8'))
                                    msg_type = msg.get("type")
                                    logger.debug(f"📩 [Worker恢复监听] 收到房主消息: {msg_type}")
                                    
                                    # 和手动加入房间完全一样的处理逻辑
                                    if msg_type == "room_info_update":
                                        try:
                                            room_info = msg.get("room_info", {})
                                            updated_saved_state = load_worker_state()
                                            updated_saved_state.update({
                                                "room_name": room_info.get("room_name", ""),
                                                "room_id": room_info.get("room_id", ""),
                                                "owner_name": room_info.get("owner_name", ""),
                                                "owner_model": room_info.get("owner_model", ""),
                                                "members_detail": room_info.get("members_detail", []),
                                                "saved_at": time.time()
                                            })
                                            save_worker_state(updated_saved_state)
                                            logger.info(f"✅ [Worker恢复] 已从房主收到最新房间信息并更新本地状态")
                                        except Exception as e_update:
                                            logger.warning(f"更新房间持久化状态失败: {e_update}")
                                    
                                    # 转发所有房主事件到本地浏览器WebSocket
                                    try:
                                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                                        import asyncio as aio
                                        try:
                                            current_loop = aio.get_event_loop()
                                            if current_loop.is_running():
                                                aio.create_task(broadcast_to_all_clients(msg))
                                            else:
                                                new_loop2 = aio.new_event_loop()
                                                aio.set_event_loop(new_loop2)
                                                new_loop2.run_until_complete(broadcast_to_all_clients(msg))
                                                new_loop2.close()
                                        except Exception:
                                            new_loop2 = aio.new_event_loop()
                                            aio.set_event_loop(new_loop2)
                                            new_loop2.run_until_complete(broadcast_to_all_clients(msg))
                                            new_loop2.close()
                                    except Exception as e_forward:
                                        logger.warning(f"转发房主事件失败: {e_forward}")
                                    
                                    if msg_type == "task_assignment":
                                        payload = msg.get("payload", {})
                                        node.receive_assignment(
                                            task_id=payload["task_id"],
                                            task_type=payload["task_type"],
                                            description=payload["description"],
                                            parameters=payload.get("parameters")
                                        )
                                except Exception as e_listen:
                                    logger.debug(f"Worker恢复监听线程异常: {e_listen}")
                                    break
                        
                        threading.Thread(target=restore_listener, daemon=True).start()
                        
                        # 启动恢复后的心跳线程
                        def restore_heartbeat_loop():
                            while True:
                                try:
                                    if _global_cluster_client and _global_cluster_client.socket:
                                        hb = create_heartbeat(
                                            node.node_id,
                                            {
                                                "load_cpu": 0.5,
                                                "load_memory": 0.5,
                                                "queue_length": 0
                                            }
                                        )
                                        _global_cluster_client.socket.sendall(hb.serialize())
                                except Exception as e_hb:
                                    logger.debug(f"恢复心跳发送失败: {e_hb}")
                                    break
                                time.sleep(5)
                        
                        threading.Thread(target=restore_heartbeat_loop, daemon=True).start()
                        
                        logger.info(f"✅ [Worker自动重连成功] 刷新页面后成功恢复协作模式！")
                        
                        # 向本地浏览器广播：恢复成功
                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                        try:
                            import asyncio as aio
                            new_loop3 = aio.new_event_loop()
                            aio.set_event_loop(new_loop3)
                            new_loop3.run_until_complete(broadcast_to_all_clients({
                                "type": "restored_room_success",
                                "room_name": saved_state.get("room_name", "协作房间"),
                                "timestamp": time.time()
                            }))
                            new_loop3.close()
                        except: pass
                        
                except Exception as e_restore:
                    logger.warning(f"⚠️ [Worker自动重连失败] 房主当前不可访问，继续保留持久化状态让UI显示协作模式: {e_restore}")
                    join_success = True  # 标记为成功，即使TCP连接暂时不可用，UI仍正常显示为协作模式
        
            # 如果持久化状态没有历史记录，走全新首次加入逻辑
            else:
                from evolution.cluster.connection import ClusterClient
                _global_cluster_client = ClusterClient()
                node_info = {
                    "node_id": node.node_id,
                    "model": MODEL_NAME,
                    "role": "worker",
                    "mode": "auto"
                }
                try:
                    loop = asyncio.get_event_loop()
                    success = await asyncio.wait_for(
                        loop.run_in_executor(None, _global_cluster_client.join, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT, node_info),
                        timeout=5.0
                    )
                    if isinstance(success, tuple):
                        join_success, _ = success
                    else:
                        join_success = success
                except asyncio.TimeoutError:
                    join_success = False
                    print("Worker 连接 manager 超时（5秒），集群功能不可用，将运行在单机模式")
                except Exception as e:
                    join_success = False
                    print(f"Worker 连接 manager 失败: {e}")
                
                if join_success:
                    node.connection = _global_cluster_client.socket
                    def listener():
                        while True:
                            try:
                                if not _global_cluster_client or not _global_cluster_client.socket: break
                                data = _global_cluster_client.socket.recv(4096)
                                if not data: break
                                msg = json.loads(data.decode('utf-8'))
                                msg_type = msg.get("type")
                                logger.debug(f"Worker 收到其他消息类型: {msg_type}")
                                if msg_type == "task_assignment":
                                    payload = msg.get("payload", {})
                                    node.receive_assignment(
                                        task_id=payload["task_id"],
                                        task_type=payload["task_type"],
                                        description=payload["description"],
                                        parameters=payload.get("parameters")
                                    )
                            except Exception as e:
                                print(f"Worker 监听线程异常: {e}")
                                break
                    threading.Thread(target=listener, daemon=True).start()
                    def heartbeat_loop():
                        while True:
                            try:
                                if node.connection and _global_cluster_client and _global_cluster_client.socket:
                                    hb = create_heartbeat(node.node_id, {"load_cpu": 0.3, "load_memory": 0.4, "queue_length": 0})
                                    _global_cluster_client.socket.sendall(hb.serialize())
                            except Exception as e:
                                print(f"心跳发送失败: {e}")
                                break
                            time.sleep(5)
                    threading.Thread(target=heartbeat_loop, daemon=True).start()
                    print("✅ Worker 已加入集群（懒加载）")
            
            if not join_success:
                print("Worker 加入集群失败（懒加载），将运行在单机模式")
            
            _cluster_initialized = True
            return join_success
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
    """获取Ollama中已下载的模型列表 - 异步非阻塞版，绝不卡主事件循环"""
    import requests
    ollama_url = "http://localhost:11434/api/tags"
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        # 把耗时的同步网络IO扔到线程池后台，绝不阻塞主事件循环
        def _do_request():
            response = requests.get(ollama_url, timeout=3)
            response.raise_for_status()
            return response.json()
        data = await loop.run_in_executor(None, _do_request)
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
async def list_conversations(limit: int = 20, conversation_type: Optional[str] = None):
    """列出对话历史，支持按模式过滤"""
    try:
        from conversation_manager import ConversationType
        filter_type = None
        if conversation_type:
            filter_type = ConversationType(conversation_type)
        convs = conv_manager.list_conversations(limit=limit, conversation_type=filter_type)
        return {"success": True, "conversations": convs}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/conversations/switch-mode")
async def switch_conversation_mode_api(request: Request):
    """切换对话模式（单机模式/协作模式），两套对话完全隔离"""
    try:
        data = await request.json()
        mode = data.get("mode")  # "standalone" 或 "collaboration"
        from conversation_manager import ConversationType
        conv_type = ConversationType(mode)
        conv_manager.switch_mode(conv_type)
        return {"success": True, "message": f"已切换到{mode}模式对话"}
    except Exception as e:
        logger.error(f"切换对话模式失败: {e}", exc_info=True)
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


# ==================== API：局域网发现管理 ====================
@app.post("/api/discovery/start_scan")
async def discovery_start_scan():
    """启动局域网房间扫描（无论是什么角色，都可以调用）"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    discovery = getattr(manager, 'discovery', None) or globals().get('_discovery_instance')
    if discovery and not discovery.scanning:
        discovery.start_scanning()
        logger.info("🔍 /api/discovery/start_scan 已成功启动扫描")
        return {"success": True, "message": "扫描已启动"}
    elif discovery and discovery.scanning:
        return {"success": True, "message": "扫描已在运行"}
    else:
        return {"success": False, "error": "discovery未初始化"}

@app.get("/api/discovery/rooms")
async def discovery_list_rooms():
    """直接从discovery获取已发现的远程房间列表"""
    await ensure_cluster_initialized()
    manager = getattr(app.state, "cluster_manager", None)
    discovery = getattr(manager, 'discovery', None) or globals().get('_discovery_instance')
    if discovery:
        return {"success": True, "rooms": discovery.get_available_rooms()}
    return {"success": True, "rooms": []}

@app.post("/api/discovery/stop")
async def discovery_stop():
    """停止发现服务"""
    manager = getattr(app.state, "cluster_manager", None)
    discovery = getattr(manager, 'discovery', None) or globals().get('_discovery_instance')
    if discovery:
        discovery.stop()
        return {"success": True, "message": "发现服务已停止"}
    return {"success": True, "message": "发现服务未运行"}

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
    """获取已加载的技能列表 - 全异步非阻塞版"""
    import asyncio
    loop = asyncio.get_event_loop()
    def _fetch_skills():
        agent = get_agent()
        skills = []
        if hasattr(agent, 'skills_registry') and agent.skills_registry:
            if hasattr(agent.skills_registry, 'list_skills'):
                for name, func in agent.skills_registry.list_skills().items():
                    desc = func.__doc__ or ""
                    skills.append({"name": name, "description": desc.strip()})
            else:
                schemas = agent.skills_registry.get_openai_schemas()
                for s in schemas:
                    skills.append({
                        "name": s["function"]["name"],
                        "description": s["function"]["description"]
                    })
        return skills
    skills = await loop.run_in_executor(None, _fetch_skills)
    return {"success": True, "skills": skills}

# ==================== 异步对话任务管理系统 ====================

class AsyncTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class AsyncChatTask:
    task_id: str
    message: str
    conversation_id: Optional[str]
    status: AsyncTaskStatus = AsyncTaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

# 全局异步任务状态存储与任务队列
_async_chat_tasks: Dict[str, AsyncChatTask] = {}
_async_chat_task_queue: queue.Queue = queue.Queue()
_async_chat_worker_running: bool = False
_async_chat_worker_thread: Optional[threading.Thread] = None
_async_chat_lock = threading.Lock()

def _async_chat_worker_loop():
    """
    后台异步对话任务处理循环 - 核心：在模型思考时，所有其他API完全可用
    不会阻塞 FastAPI 的事件循环
    """
    global _async_chat_worker_running
    logger.info("🚀 [异步对话系统] 后台任务工作线程已启动")
    
    while _async_chat_worker_running:
        try:
            # 从队列中获取任务，带超时避免无限阻塞
            try:
                task = _async_chat_task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            logger.info(f"⚡ [异步对话任务] 开始处理任务: {task.task_id}")
            
            # 更新任务状态为处理中
            with _async_chat_lock:
                task.status = AsyncTaskStatus.PROCESSING
                task.started_at = time.time()
            
            # 实际调用Agent进行处理
            try:
                agent = get_agent()
                final_response = agent.process_adaptive(task.message)
                with _async_chat_lock:
                    task.status = AsyncTaskStatus.COMPLETED
                    task.result = final_response
                    task.completed_at = time.time()
                logger.info(f"✅ [异步对话任务] 任务 {task.task_id} 完成，响应长度: {len(final_response)}")
            except Exception as e:
                with _async_chat_lock:
                    task.status = AsyncTaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = time.time()
                logger.error(f"❌ [异步对话任务] 任务 {task.task_id} 失败: {e}", exc_info=True)
            
            # 标记任务完成
            _async_chat_task_queue.task_done()
            
            # 通过WebSocket向所有浏览器广播任务完成事件
            try:
                from evolution.cluster.cluster_api import broadcast_to_all_clients
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(broadcast_to_all_clients({
                        "type": "async_chat_task_updated",
                        "task_id": task.task_id,
                        "status": task.status,
                        "timestamp": time.time()
                    }))
            except Exception:
                pass  # WebSocket广播失败不影响任务本身
            
        except Exception as loop_err:
            logger.error(f"[异步对话系统] 工作循环异常: {loop_err}", exc_info=True)
            time.sleep(0.5)
    
    logger.info("🛑 [异步对话系统] 后台任务工作线程已停止")

def start_async_chat_worker():
    """启动异步对话后台工作线程"""
    global _async_chat_worker_running, _async_chat_worker_thread
    if _async_chat_worker_thread and _async_chat_worker_thread.is_alive():
        logger.warning("[异步对话系统] 工作线程已在运行，跳过重复启动")
        return
    _async_chat_worker_running = True
    _async_chat_worker_thread = threading.Thread(target=_async_chat_worker_loop, daemon=True)
    _async_chat_worker_thread.start()

def stop_async_chat_worker():
    """停止异步对话后台工作线程"""
    global _async_chat_worker_running
    _async_chat_worker_running = False

@app.post("/api/chat/async-submit")
async def api_chat_async_submit(request: Request):
    """
    异步对话提交 - 立即返回任务ID，完全不阻塞
    单机对话模式下，发送信息后模型没有回复时所有其他功能依然可用！
    """
    try:
        data = await request.json()
        message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        if not message:
            raise HTTPException(status_code=400, detail="消息不能为空")
        
        # 1. 确保对话管理器状态完整，先立即记录用户消息
        if conversation_id:
            conv_manager.load_conversation_or_create(conversation_id)
        if not conv_manager.current_conversation:
            conv_manager.new_conversation()
        conv_manager.add_user_message(message)
        conv_manager.save_current()
        
        # 2. 生成唯一任务ID并创建任务对象
        task_id = str(uuid.uuid4())
        task = AsyncChatTask(
            task_id=task_id,
            message=message,
            conversation_id=conv_manager.current_conversation.conversation_id
        )
        
        # 3. 保存任务到状态存储，并放入队列
        with _async_chat_lock:
            _async_chat_tasks[task_id] = task
        _async_chat_task_queue.put(task)
        
        logger.info(f"📤 [异步对话提交] 新任务已提交，task_id={task_id}，当前队列大小={_async_chat_task_queue.qsize()}")
        
        # 4. 立即返回响应，不等待模型处理！
        return {
            "success": True,
            "task_id": task_id,
            "conversation_id": conv_manager.current_conversation.conversation_id,
            "status": "pending",
            "message": "任务已提交，正在后台处理，您可以继续使用其他功能！"
        }
    except Exception as e:
        logger.error(f"API async chat submit error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/api/chat/task/{task_id}")
async def api_chat_get_task_status(task_id: str):
    """查询异步对话任务状态 - 前端轮询此接口获取结果"""
    try:
        with _async_chat_lock:
            task = _async_chat_tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return {
            "success": True,
            "task_id": task.task_id,
            "status": task.status,
            "result": task.result,
            "error": task.error,
            "conversation_id": task.conversation_id,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API get task status error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/api/chat/tasks")
async def api_chat_list_tasks(limit: int = 20):
    """列出最近的异步对话任务"""
    try:
        with _async_chat_lock:
            sorted_tasks = sorted(
                _async_chat_tasks.values(),
                key=lambda t: t.created_at,
                reverse=True
            )[:limit]
        return {
            "success": True,
            "total": len(sorted_tasks),
            "tasks": [
                {
                    "task_id": t.task_id,
                    "status": t.status,
                    "message_preview": t.message[:50] + "..." if len(t.message) > 50 else t.message,
                    "created_at": t.created_at
                }
                for t in sorted_tasks
            ]
        }
    except Exception as e:
        logger.error(f"API list tasks error: {e}", exc_info=True)
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
    """获取核心记忆列表 - 全异步非阻塞版"""
    import asyncio
    loop = asyncio.get_event_loop()
    def _fetch_memories():
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
        return memories
    memories = await loop.run_in_executor(None, _fetch_memories)
    return {"success": True, "memories": memories}

@app.get("/api/token-stats")
async def api_token_stats():
    """获取 token 使用统计 - 修复版直接访问全局实例"""
    try:
        from token_tracker import token_tracker
        stats_data = token_tracker.get_stats()
        return {"success": True, "data": stats_data}
    except Exception as e:
        logger.error(f"获取token统计失败: {e}", exc_info=True)
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
