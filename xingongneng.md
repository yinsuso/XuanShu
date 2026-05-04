# 新功能规划文档 (xingongneng.md)

## 一、目标
明确 Phase 2 (Cluster API 开发) 的详细实施方案，满足以下核心需求：
- 成员节点能够通过 HTTP API 接收上级任务
- 实现任务状态机（PENDING → ASSIGNED → RUNNING → COMPLETED/FAILED）
- 成员节点能够实时反馈状态（空闲/忙碌）并推送变更
- 与现有的集群底层协议和连接层对接
- 遵循四象协作流程（青龙规划→白虎实施→朱雀验证→玄武交付）

## 二、现状分析（Phase 1 成果）
### 2.1 现有代码结构
- `evolution/cluster/protocol.py`：定义了 MessageType 枚举、ClusterMessage 类及便捷构造函数。
- `evolution/cluster/connection.py`：定义了 `ClusterNode`（基础节点类）、`ClusterManager`（房主服务器）、`ClusterClient`（客户端加入流程）；实现了简易能力评估（MODEL_RANKINGS）和 TCP 握手。
- `evolution/cluster/discovery.py`：UDP 广播房间发现机制（未在本次任务中直接使用但保留）。
- `web_app.py`：目前仅包含安全审批 API（/api/approvals/*），缺少 FastAPI 实例化，无法直接运行。
- `agent.py`：UniversalAgent，负责核心推理与技能执行，尚未集成集群功能。
- `config.py`：存放全局配置（模型、Web 服务地址等），目前无集群相关配置。
- `launcher.py`：启动器，负责环境检测、Ollama 启动、提供商选择，最终会启动 Web UI 和/或 CLI。

### 2.2 识别缺口
- `web_app.py` 没有 `app = FastAPI()`，路由装饰器 `@app` 实际未定义，需修复。
- 集群节点 (ClusterNode) 没有任务管理数据结构，暂无任务状态跟踪。
- 集群节点与 Agent 执行引擎之间缺乏连接：任务如何由 API 接收后驱动 Agent 执行。
- 缺乏 WebSocket 推送机制用于状态实时反馈。
- 配置缺失：集群开关、角色、管理器地址、端口等。

## 三、整体设计
### 3.1 架构决策
- **部署模式**：Worker 节点将作为一个 FastAPI 服务运行，同时内置 UniversalAgent 实例用于执行技能。Web 前端（三栏布局）将通过此 API 与后端交互。
- **ClusterNode 扩展**：为 `ClusterNode` 增加任务登记簿、状态锁、事件回调等能力。
- **API 层**：新增 `evolution/cluster/cluster_api.py`，使用 `APIRouter`，前缀 `/cluster`。
- **启动集成**：在 `web_app.py` 的 FastAPI `startup` 事件中初始化 ClusterNode 和 Agent，并启动后台任务处理线程。

### 3.2 任务状态机定义
```python
class TaskStatus(Enum):
    PENDING = "pending"      # 已接收但未开始
    ASSIGNED = "assigned"    # 已分配给本节点（可简化合并到 PENDING）
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 成功完成
    FAILED = "failed"        # 执行失败
```
状态转换：
- 接收 → PENDING
- 开始执行 → RUNNING
- 执行成功 → COMPLETED
- 执行异常 → FAILED

## 四、详细实施方案（白虎实施细则）
### 4.1 配置扩展 (`config.py`)
新增配置项：
```python
# 集群功能总开关
CLUSTER_ENABLED = False
# 集群角色: "worker" 或 "manager"
CLUSTER_ROLE = "worker"
# 管理器地址（仅 worker 需要）
CLUSTER_MANAGER_HOST = "127.0.0.1"
CLUSTER_MANAGER_PORT = 30001
# 本节点对外 API 端口（FastAPI 服务）
CLUSTER_API_PORT = 30002
# 节点身份（不指定则自动生成）
CLUSTER_NODE_ID = None
CLUSTER_NODE_NICKNAME = "玄枢成员"
# 任务处理并发数（未来可扩展）
CLUSTER_WORKER_THREADS = 1
```

### 4.2 增强 ClusterNode (`evolution/cluster/connection.py`)
在 `ClusterNode.__init__` 中增加：
```python
self.tasks: Dict[str, Dict] = {}          # task_id -> {status, parameters, result, error, timestamps}
self._task_lock = threading.Lock()        # 保护 tasks 和 pending_tasks 的并发访问
self.ws_connections: List[WebSocket] = [] # 可选: 简化版 WebSocket 推送
```
新增方法：
```python
def create_task(self, task_type: str, description: str, parameters: Dict[str, Any] = None) -> str:
    """创建新任务，返回 task_id"""
    task_id = str(uuid.uuid4())
    with self._task_lock:
        self.tasks[task_id] = {
            "task_id": task_id,
            "task_type": task_type,
            "description": description,
            "parameters": parameters or {},
            "status": TaskStatus.PENDING.value,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None
        }
        self.pending_tasks.append(task_id)  # 保留原本的 pending 列表用于执行顺序
    return task_id

def start_task(self, task_id: str):
    with self._task_lock:
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = TaskStatus.RUNNING.value
            self.tasks[task_id]["started_at"] = time.time()
            # 从 pending 中移除（如果pending是待执行队列）
            if task_id in self.pending_tasks:
                self.pending_tasks.remove(task_id)

def complete_task(self, task_id: str, result: Any):
    with self._task_lock:
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = TaskStatus.COMPLETED.value
            self.tasks[task_id]["completed_at"] = time.time()
            self.tasks[task_id]["result"] = result

def fail_task(self, task_id: str, error: str):
    with self._task_lock:
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = TaskStatus.FAILED.value
            self.tasks[task_id]["completed_at"] = time.time()
            self.tasks[task_id]["error"] = error
```

### 4.3 新增 Cluster API (`evolution/cluster/cluster_api.py`)
```python
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import uuid
import json

from ..connection import ClusterNode, TaskStatus
from config import CLUSTER_API_TOKEN  # 可选 API 鉴权

router = APIRouter(prefix="/cluster", tags=["Cluster"])

def get_cluster_node(request: Request) -> ClusterNode:
    """依赖注入函数，从 FastAPI app.state 获取 node"""
    return request.app.state.cluster_node

# 1. POST /tasks
@router.post("/tasks")
async def receive_task(request: Request, node: ClusterNode = Depends(get_cluster_node)):
    if not node:
        return JSONResponse(status_code=503, content={"error": "Cluster node not initialized"})
    data = await request.json()
    # 验证必需字段
    required = ["task_type", "description"]
    if not all(k in data for k in required):
        return JSONResponse(status_code=400, content={"error": "Missing required fields"})
    task_id = data.get("task_id") or str(uuid.uuid4())
    task_type = data["task_type"]
    description = data["description"]
    parameters = data.get("parameters", {})
    # 创建任务
    tid = node.create_task(task_type, description, parameters)
    # 立即返回 Accepted 但不等待执行
    return {"success": True, "task_id": tid, "status": "accepted"}

# 2. POST /tasks/batch
@router.post("/tasks/batch")
async def receive_task_batch(request: Request, node: ClusterNode = Depends(get_cluster_node)):
    if not node:
        return JSONResponse(status_code=503, content={"error": "Cluster node not initialized"})
    data = await request.json()
    tasks = data.get("tasks", [])
    results = []
    for task in tasks:
        # 简化处理，逐个创建
        if "task_type" not in task or "description" not in task:
            results.append({"status": "error", "error": "missing fields"})
            continue
        task_id = task.get("task_id") or str(uuid.uuid4())
        tid = node.create_task(task["task_type"], task["description"], task.get("parameters", {}))
        results.append({"task_id": tid, "status": "accepted"})
    return {"results": results}

# 3. GET /status
@router.get("/status")
async def cluster_status(node: ClusterNode = Depends(get_cluster_node)):
    if not node:
        return JSONResponse(status_code=503, content={"error": "Cluster node not initialized"})
    # 计算忙碌状态：存在任何非完成/失败任务即为忙碌
    busy = False
    with node._task_lock:
        for t in node.tasks.values():
            if t["status"] in (TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value, TaskStatus.RUNNING.value):
                busy = True
                break
    return {
        "node_id": node.node_id,
        "role": node.role,
        "capability_score": node.capability_score,
        "last_heartbeat": node.last_heartbeat,
        "state": "busy" if busy else "idle",
        "tasks_count": {
            "total": len(node.tasks),
            "pending": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.PENDING.value),
            "running": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.RUNNING.value),
            "completed": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.COMPLETED.value),
            "failed": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.FAILED.value),
        }
    }

# 4. WebSocket /ws/updates（简化版）
@router.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket, node: ClusterNode = Depends(get_cluster_node)):
    await websocket.accept()
    # 注册连接
    node.ws_connections.append(websocket)
    try:
        while True:
            # 保持连接，等待客户端断开；实际事件由其他线程推送
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        if websocket in node.ws_connections:
            node.ws_connections.remove(websocket)
```

推送逻辑（在任务状态变更时）：
```python
# 在 ClusterNode 中新增
import asyncio

async def _broadcast_event(self, event: Dict):
    """广播事件给所有已连接的 WebSocket 客户端"""
    for ws in self.ws_connections:
        try:
            await ws.send_json(event)
        except:
            pass  # 连接可能已断开

def notify_status_change(self, task_id: str):
    """外部调用（通常由任务处理器）以触发状态推送"""
    if task_id in self.tasks:
        task = self.tasks[task_id]
        event = {"task_id": task_id, "status": task["status"]}
        if task["status"] == TaskStatus.COMPLETED.value:
            event["result"] = task["result"]
        elif task["status"] == TaskStatus.FAILED.value:
            event["error"] = task["error"]
        # 异步广播
        asyncio.create_task(self._broadcast_event(event))
```
### 4.4 修改 `web_app.py` 
1. 为顶部添加：
```python
from fastapi import FastAPI
app = FastAPI(title="玄枢智能体", version="5.1.0")
```
2. 引入 cluster_api 并挂载：
```python
from evolution.cluster import cluster_api
app.include_router(cluster_api.router)
```
3. 新增 startup 事件（需与 agent 集成）：
```python
from agent import UniversalAgent
from config import CLUSTER_ENABLED, CLUSTER_ROLE, CLUSTER_NODE_ID, CLUSTER_NODE_NICKNAME, MODEL_NAME
from evolution.cluster.connection import ClusterNode, ClusterManager, ClusterClient
import threading

@app.on_event("startup")
def startup_event():
    if not CLUSTER_ENABLED:
        return
    # 创建 ClusterNode
    node = ClusterNode(
        node_id=CLUSTER_NODE_ID or ClusterNode.generate_node_id(),
        ip="0.0.0.0",          # 实际应获取本机IP
        model=MODEL_NAME,
        role=CLUSTER_ROLE,
        mode="auto"
    )
    app.state.cluster_node = node
    # 启动 Agent 实例（供任务执行使用）
    agent = UniversalAgent(auto_load_skills=True, enable_evolution=False)
    app.state.agent = agent
    # 启动任务处理器
    def task_worker():
        while True:
            if node.pending_tasks:
                # 取出优先级最高的任务（简单起见取第一个）
                task_id = node.pending_tasks.pop(0)
                # 标记开始执行
                node.start_task(task_id)
                task = node.tasks[task_id]
                try:
                    # 调用 Agent 执行技能
                    result = agent._execute_skill(task["task_type"], task["parameters"])
                    node.complete_task(task_id, result)
                except Exception as e:
                    node.fail_task(task_id, str(e))
                # 通知状态变化（可选 WebSocket 推送）
                node.notify_status_change(task_id)
            else:
                time.sleep(0.2)  # 避免忙等
    
    t = threading.Thread(target=task_worker, daemon=True)
    t.start()
    
    # 如果 role 是 manager，启动 ClusterManager TLS 服务器（Phase 3+）
    if CLUSTER_ROLE == "manager":
        manager = ClusterManager()
        manager.start_server(host="0.0.0.0", port=30001)
        # 可保存 manager 到 app.state 以备后续
```
4. 新增 CORS 支持（若前端跨域）：
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4.5 修改 `config.py`
扩展配置，添加 4.1 中列出的所有 `CLUSTER_*` 项。默认全部为关闭/空，避免影响现有功能。

### 4.6 依赖调整 (`requirements.txt`)
确保 FastAPI、uvicorn 已包含：
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
```
若未包含，添加这些行。

## 五、四象协作流程安排
- **青龙（规划）**：本文档（已完成）。
- **白虎（实施）**：
  1. 创建 `evolution/cluster/cluster_api.py` 并实现所有端点。
  2. 扩展 `ClusterNode` 类（任务字典、锁、方法、WebSocket 管理）。
  3. 修复 `web_app.py`：添加 `FastAPI` 实例、挂载路由、编写 startup_event、CORS。
  4. 扩充 `config.py` 集群配置项。
  5. 更新 `requirements.txt`（如必要）。
- **朱雀（验证）**：
  - 单元测试：`tests/cluster/test_cluster_api.py`、`tests/cluster/test_task_state_machine.py`。
  - 手工测试：启动 worker，使用 `curl` 发送任务，查询状态，用 WebSocket 客户端接收推送。
- **玄武（交付）**：
  - 输出最终审核报告，检查代码覆盖率、安全性（API鉴权）、线程安全。
  - 更新 `CHANGELOG.md` 和 `TECH_ROUTE.md`，标记 Phase 2 完成。
  - 确保所有新增代码遵循 PEP8，并有必要的中文注释。

## 六、验收标准
- 能够在配置文件启用 `CLUSTER_ENABLED=True`、`CLUSTER_ROLE="worker"` 后启动服务。
- `curl -X POST http://localhost:30002/cluster/tasks -d '{"task_type":"test","description":"测试"}'` 返回 `{"task_id":"...","status":"accepted"}`。
- 调用 `GET /cluster/status` 返回 `"state":"idle"`（无任务时）或 `"busy"`（有任务进行中）。
- WebSocket `ws://localhost:30002/cluster/ws/updates` 能收到任务状态变更事件。
- 任务从接收到完成的状态流转符合预设状态机。

## 七、风险与缓解
- **线程安全**：ClusterNode 的 `tasks` 和 `pending_tasks` 被多个线程读写，已使用 `Lock` 保护。
- **Agent 共享**：UniversalAgent 可能非线程安全，初期仅使用单一后台线程处理任务，避免并发调用。
- **WebSocket 推送**：简化实现可能在异常连接下导致内存泄漏，需定期清理失效连接。
- **配置错误**：未正确配置 `CLUSTER_MANAGER_HOST/PORT` 会导致 worker 无法连接；在 startup 中应有日志提示。

## 八、后续展望
- Phase 3: 引入更精细的能力评估器、任务调度策略。
- Phase 4: 完善 Web 前端三栏布局，实时显示集群节点状态与任务流。
- Phase 5: 加入安全审批流与权限控制。

---
**文档生成时间**: 2025-05-04
**负责**: 破执 (Hermes Agent)
