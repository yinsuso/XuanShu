
# === 安全审批模块（SQLite 持久化 + API 扩展） ===
import sqlite3
import json
import time
from threading import Lock
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import WEB_APP_URL,  APPROVAL_API_TOKEN,  APPROVAL_DB_PATH,  PROJECT_ROOT, CAPABILITY_MODEL_RANKINGS, SCHEDULER_STRATEGY, MANAGER_MONITOR_INTERVAL, CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT
from evolution.cluster.capability import CapabilityAssessor
from evolution.cluster.scheduler import TaskScheduler

app = FastAPI(title="玄枢智能体", version="5.1.0")

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
app.include_router(cluster_api.router, prefix='/api')

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
import asyncio

@app.on_event("startup")
async def startup_cluster():
    if not CLUSTER_ENABLED:
        return
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
                    result = await loop.run_in_executor(None, lambda: agent._execute_skill(task["task_type"], task["parameters"]))
                    node.complete_task(task_id, result)
                    # 发送完成状态给 manager
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

    if CLUSTER_ROLE == "worker":
        client = ClusterClient()
        node_info = {
            "node_id": node.node_id,
            "model": MODEL_NAME,
            "role": "worker",
            "mode": "auto"
        }
        success = client.join(CLUSTER_MANAGER_HOST, CLUSTER_MANAGER_PORT, node_info)
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
        else:
            logger.error("Worker 加入集群失败")

    if CLUSTER_ROLE == "manager":
        manager = ClusterManager()
        # 初始化调度器与能力评估器
        assessor = CapabilityAssessor(CAPABILITY_MODEL_RANKINGS)
        scheduler = TaskScheduler(assessor, strategy=SCHEDULER_STRATEGY)
        manager.set_scheduler(scheduler, assessor)
        manager.start_monitoring(interval=MANAGER_MONITOR_INTERVAL)
        logger.info("✅ [ClusterManager] 调度器已就绪", strategy=SCHEDULER_STRATEGY, assessor_model_rankings=CAPABILITY_MODEL_RANKINGS)
        mgr_thread = threading.Thread(target=manager.start_server, kwargs={"host":"0.0.0.0", "port":30001}, daemon=True)
        mgr_thread.start()
        app.state.cluster_manager = manager
