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


# PHASE 3 规划：能力评估器与任务调度器

## 一、目标
实现 **智能任务分配**，超越 Phase 2 的 FIFO 队列，实现：
- 动态能力评估（多维度、可配置权重）
- 智能任务调度（多种策略）
- 房主（Manager）完整分派逻辑
- 负载感知与自动均衡
- 任务类型与节点特长的亲和性匹配

## 二、现状缺口
1. **能力评估**：Phase 2 使用固定排行榜（MODEL_RANKINGS），无法动态更新
2. **调度策略**：Phase 2 是先进先出（FIFO），无优先级、无匹配
3. **Manager 角色**：仅有 TCP 服务器，无任务分派逻辑
4. **负载均衡**：未实现，忙碌节点仍可能被分配任务
5. **亲和性**：任务类型与节点模型无关联

## 三、架构设计

### 3.1 能力评估器（CapabilityAssessor）
**文件**: `evolution/cluster/capability.py`

**评估维度与权重**（可配置）：
- 模型基准分 40%（动态排行榜）
- 硬件算力 20%（GPU 显存、CPU 核心）
- 实时负载 15%（CPU、内存）
- 历史表现 15%（成功率、平均耗时）
- 网络质量 10%（RTT，可选）

**核心方法**：
- `assess(node_info) -> float`：计算综合能力分 (0.0-1.0)
- `record_task_outcome(node_id, success, duration)`：更新历史表现
- `update_model_rankings(new_rankings)`：动态更新排行榜

### 3.2 任务调度器（TaskScheduler）
**文件**: `evolution/cluster/scheduler.py`

**调度策略**（可切换）：
1. `capability`：能力分最高优先
2. `load_balance`：负载最低优先
3. `affinity`：亲和性匹配后能力最优
4. `round_robin`：轮询

**任务亲和性规则**：
```python
TASK_AFFINITY = {
    "code_generation": ["qwen2.5-coder"],
    "text_writing": ["qwen2.5", "mistral"],
    "default": []
}
```

### 3.3 Manager 扩展（ClusterManager）
**扩展位置**: `evolution/cluster/connection.py`

**新增方法**：
- `set_scheduler(assessor, scheduler)`：注入评估器与调度器
- `assign_task(task_type, description, parameters)`：选择节点并发送分配消息
- `monitor_tasks()`：后台监控，超时重派
- `handle_node_failure(node_id)`：节点失效处理

**任务分派流程**：
1. 接收任务（来自 API 或 Web）
2. 调用 scheduler 选择最优节点
3. 发送 TaskAssignment 消息（TCP）
4. 记录分配关系与超时时间
5. 监控线程定期检查，失败则重派（最多 SCHEDULER_MAX_RETRIES 次）

### 3.4 ClusterNode 扩展（Worker）
**新增字段**：
- `load_cpu: float`  # 最新 CPU 负载 (0.0-1.0)
- `load_memory: float`  # 内存使用率
- `queue_length: int`  # 本地待执行任务数
- `task_start_time: Dict[str, float]`  # 任务开始时间戳

**新增行为**：
- 心跳中上报负载信息（`load_cpu`, `load_memory`, `queue_length`）
- 负载 >80% 时可返回 NACK，拒绝新任务分配

## 四、实施方案（白虎细则）

### 4.1 创建 `evolution/cluster/capability.py`
```python
"""
能力评估器 - 动态计算节点综合能力分
"""
from typing import Dict, Any
from logger import logger

class CapabilityAssessor:
    def __init__(self, model_rankings=None):
        self.model_rankings = model_rankings or {
            "qwen2.5-coder:7b": 0.95,
            "qwen2.5:7b": 0.85,
            "llama3:8b": 0.80
        }
        self.history: Dict[str, Dict[str, float]] = {}
        self.weights = {
            "model": 0.4,
            "hardware": 0.2,
            "load": 0.15,
            "history": 0.15,
            "network": 0.1
        }
    
    def assess(self, node_info: Dict[str, Any]) -> float:
        """计算综合能力分 0.0-1.0"""
        score = 0.0
        
        # 1 模型基准分
        model = node_info.get("model", "unknown")
        model_score = self.model_rankings.get(model, 0.5)
        score += model_score * self.weights["model"]
        
        # 2 硬件分（GPU 显存 + CPU）
        hardware_score = self._calc_hardware_score(node_info)
        score += hardware_score * self.weights["hardware"]
        
        # 3 实时负载分（负载越高分越低）
        load_score = 1.0 - min(node_info.get("load_cpu", 0.0), 1.0)
        score += load_score * self.weights["load"]
        
        # 4 历史表现分
        node_id = node_info.get("node_id")
        if node_id in self.history:
            history_score = self.history[node_id].get("success_rate", 0.8)
        else:
            history_score = 0.8  # 默认
        score += history_score * self.weights["history"]
        
        # 5 网络分（暂为 1.0）
        score += 1.0 * self.weights["network"]
        
        return max(0.0, min(1.0, score))
    
    def _calc_hardware_score(self, node_info: Dict[str, Any]) -> float:
        score = 0.5
        gpu_mem = node_info.get("gpu_memory", 0)
        if gpu_mem >= 24:
            score = 1.0
        elif gpu_mem >= 16:
            score = 0.9
        elif gpu_mem >= 8:
            score = 0.7
        elif gpu_mem >= 4:
            score = 0.5
        else:
            score = 0.3
        
        cpu_cores = node_info.get("cpu_cores", 4)
        if cpu_cores >= 16:
            score = min(1.0, score + 0.1)
        elif cpu_cores >= 8:
            score = min(1.0, score + 0.05)
        
        return score
    
    def record_task_outcome(self, node_id: str, success: bool, duration: float):
        if node_id not in self.history:
            self.history[node_id] = {"success_rate": 0.8, "avg_duration": 2.0, "samples": 0}
        
        hist = self.history[node_id]
        samples = hist["samples"]
        old_success = hist["success_rate"]
        old_duration = hist["avg_duration"]
        
        alpha = 0.1
        new_success = old_success * (1 - alpha) + (1.0 if success else 0.0) * alpha
        new_duration = old_duration * (1 - alpha) + duration * alpha
        
        self.history[node_id] = {
            "success_rate": new_success,
            "avg_duration": new_duration,
            "samples": samples + 1
        }
    
    def update_model_rankings(self, new_rankings: Dict[str, float]):
        self.model_rankings.update(new_rankings)
        logger.info("模型排行榜已更新", rankings=self.model_rankings)
```

### 4.2 创建 `evolution/cluster/scheduler.py`
```python
"""
任务调度器 - 基于策略选择最优执行节点
"""
from typing import List, Dict, Any, Optional
from evolution.cluster.connection import ClusterNode
from .capability import CapabilityAssessor

class TaskScheduler:
    def __init__(self, assessor: CapabilityAssessor, strategy: str = "capability"):
        self.assessor = assessor
        self.strategy = strategy
        self.node_pool: Dict[str, ClusterNode] = {}
        self.round_robin_index = 0
        
        # 任务亲和性规则（可配置）
        self.affinity_rules: Dict[str, List[str]] = {
            "code_generation": ["qwen2.5-coder"],
            "text_writing": ["qwen2.5", "mistral"],
            "default": []
        }
    
    def update_node_pool(self, nodes: List[ClusterNode]):
        self.node_pool = {n.node_id: n for n in nodes}
    
    def schedule(self, task: Dict[str, Any]) -> Optional[ClusterNode]:
        task_type = task.get("task_type", "default")
        candidates = self._filter_candidates()
        if not candidates:
            logger.warning("无可用候选节点")
            return None
        
        if self.strategy == "capability":
            return self._schedule_by_capability(candidates, task_type)
        elif self.strategy == "load_balance":
            return self._schedule_by_load(candidates)
        elif self.strategy == "affinity":
            return self._schedule_by_affinity(candidates, task_type)
        elif self.strategy == "round_robin":
            return self._schedule_round_robin(candidates)
        else:
            return self._schedule_by_capability(candidates, task_type)
    
    def _filter_candidates(self) -> List[ClusterNode]:
        """过滤出可接受任务的节点（在线、未满载、负载<80%）"""
        candidates = []
        for node in self.node_pool.values():
            if (node.status == "online" and 
                len(node.pending_tasks) < 5 and 
                getattr(node, "load_cpu", 0.0) < 0.8):
                candidates.append(node)
        return candidates
    
    def _schedule_by_capability(self, candidates: List[ClusterNode], task_type: str) -> Optional[ClusterNode]:
        scored = []
        for node in candidates:
            score = self.assessor.assess({
                "node_id": node.node_id,
                "model": node.model,
                "gpu_memory": getattr(node, "gpu_memory", 0),
                "cpu_cores": getattr(node, "cpu_cores", 4),
                "load_cpu": getattr(node, "load_cpu", 0.0),
                "load_memory": getattr(node, "load_memory", 0.0)
            })
            scored.append((score, node))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None
    
    def _schedule_by_affinity(self, candidates: List[ClusterNode], task_type: str) -> Optional[ClusterNode]:
        preferred_models = self.affinity_rules.get(task_type, [])
        if not preferred_models:
            return self._schedule_by_capability(candidates, task_type)
        
        affinity_candidates = [n for n in candidates if n.model in preferred_models]
        if not affinity_candidates:
            affinity_candidates = candidates  # 降级
        
        return self._schedule_by_capability(affinity_candidates, task_type)
    
    def _schedule_by_load(self, candidates: List[ClusterNode]) -> Optional[ClusterNode]:
        if not candidates:
            return None
        return min(candidates, key=lambda n: getattr(n, "load_cpu", 0.0) + getattr(n, "load_memory", 0.0))
    
    def _schedule_round_robin(self, candidates: List[ClusterNode]) -> Optional[ClusterNode]:
        if not candidates:
            return None
        node = candidates[self.round_robin_index % len(candidates)]
        self.round_robin_index += 1
        return node
```

### 4.3 扩展 ClusterManager（在 connection.py 中）
```python
class ClusterManager(ClusterNode):
    def __init__(self, host: str, port: int):
        super().__init__(...)
        self.scheduler: Optional[TaskScheduler] = None
        self.assessor: Optional[CapabilityAssessor] = None
        self.task_assignments: Dict[str, str] = {}  # task_id -> node_id
        self.task_timeouts: Dict[str, float] = {}   # task_id -> 超时时间戳
    
    def set_scheduler(self, scheduler: TaskScheduler, assessor: CapabilityAssessor):
        self.scheduler = scheduler
        self.assessor = assessor
    
    def assign_task(self, task_type: str, description: str, parameters: Dict[str, Any] = None) -> Optional[str]:
        """Manager 分配任务给最优节点"""
        if not self.scheduler:
            logger.error("Scheduler 未初始化")
            return None
        
        task_id = str(uuid.uuid4())
        task = {
            "task_type": task_type,
            "description": description,
            "parameters": parameters or {}
        }
        
        node = self.scheduler.schedule(task)
        if not node:
            logger.error("无可用节点接受任务")
            return None
        
        # 发送 TaskAssignment 消息
        message = create_task_assignment(
            sender_id=self.node_id,
            target_id=node.node_id,
            task_id=task_id,
            task_type=task_type,
            description=description,
            parameters=parameters or {}
        )
        self.connection.send(message.to_json())
        
        self.task_assignments[task_id] = node.node_id
        self.task_timeouts[task_id] = time.time() + 300  # 5 分钟超时
        
        logger.info("任务已分配", task_id=task_id, node=node.node_id)
        return task_id
    
    def monitor_tasks(self):
        """后台监控：检查超时和失败，触发重派"""
        now = time.time()
        for task_id, deadline in list(self.task_timeouts.items()):
            if now > deadline:
                node_id = self.task_assignments.get(task_id)
                if node_id:
                    logger.warning("任务超时，重派", task_id=task_id, original_node=node_id)
                    self._reassign_task(task_id)
    
    def _reassign_task(self, task_id: str):
        """重派任务（需恢复 task_type, description, parameters）"""
        # TODO: 从任务记录中恢复参数并重新分配
        pass
```

### 4.4 修改 `config.py` 扩展配置
```python
# 能力评估器配置
CAPABILITY_WEIGHTS = {
    "model": 0.4,
    "hardware": 0.2,
    "load": 0.15,
    "history": 0.15,
    "network": 0.1
}
CAPABILITY_MODEL_RANKINGS = {
    "qwen2.5-coder:7b": 0.95,
    "qwen2.5:7b": 0.85,
    "llama3:8b": 0.80
}

# 调度器配置
SCHEDULER_STRATEGY = os.getenv("SCHEDULER_STRATEGY", "affinity")
SCHEDULER_MAX_TASKS_PER_NODE = 5
SCHEDULER_TASK_TIMEOUT = 300

# Manager 监控配置
MANAGER_MONITOR_INTERVAL = 5
MANAGER_MAX_RETRIES = 3
```

### 4.5 修改 `web_app.py` 集成调度器
```python
from evolution.cluster.capability import CapabilityAssessor
from evolution.cluster.scheduler import TaskScheduler

@app.on_event("startup")
def startup_event():
    # ... 原有 ClusterNode 创建 ...
    
    if CLUSTER_ROLE == "manager":
        assessor = CapabilityAssessor()
        scheduler = TaskScheduler(assessor, strategy=SCHEDULER_STRATEGY)
        
        manager = ClusterManager(...)
        manager.set_scheduler(scheduler, assessor)
        app.state.manager = manager
        
        def monitor_loop():
            while True:
                manager.monitor_tasks()
                time.sleep(MANAGER_MONITOR_INTERVAL)
        threading.Thread(target=monitor_loop, daemon=True).start()
```

### 4.6 扩展 Cluster API（可选）
在 `cluster_api.py` 添加 Manager 专用端点：
- `POST /manager/schedule`：手动调度任务
- `GET /manager/nodes/status`：查看所有节点状态与负载

（需权限验证：仅 manager 角色可访问）

## 五、四象协作流程
- **青龙（规划）**：本文档（已完成）
- **白虎（实施）**：7 个实施步骤（4.1-4.6）
- **朱雀（验证）**：单元测试 + 集成测试
- **玄武（交付）**：审核报告 + 文档更新 + 提交

## 六、验收标准
- [ ] CapabilityAssessor.assess() 返回 0.0-1.0 分数
- [ ] TaskScheduler 按策略正确选择节点
- [ ] Manager 角色启动后能自动分派任务
- [ ] 负载 >80% 的节点不再接收新任务
- [ ] 任务亲和性规则生效（如 code_generation → qwen2.5-coder）
- [ ] 动态更新排行榜后评估分实时变化
- [ ] 调度延迟 < 10ms
- [ ] 支持 50+ 节点池快速筛选
- [ ] 线程安全（评估器与调度器支持并发访问）
- [ ] 向后兼容：Phase 2 Worker 可与 Phase 3 Manager 互通

## 七、风险与缓解
| 风险 | 影响 | 缓解 |
|------|------|------|
| 评估维度过多导致性能下降 | 调度决策慢 | 缓存、增量更新、权重可配置 |
| 节点上报负载增加网络开销 | 网络拥堵 | 复用现有心跳，5s 一次 |
| 调度策略复杂难调试 | 问题定位难 | 详细日志 + Web 界面展示 |
| Manager 单点故障 | 集群瘫痪 | Phase 4 实现主备高可用 |
| 亲和性规则维护成本高 | 需频繁调整 | 提供默认规则，支持配置文件扩展 |

## 八、后续展望
- **Phase 4**: Web 前端三栏布局，实时展示集群状态、任务流、节点负载 heatmap
- **Phase 5**: 授权机制增强（任务类型和节点能力的动态授权）
- **Phase 6**: CLI 简化版（快速命令行集群管理）
- **Phase 7**: 性能优化与文档完善

---
**文档生成时间**: 2026-05-05 06:50:00
**负责**: 破执 (Hermes Agent)
**状态**: 白虎实施完成，待朱雀验证

---
## 📌 最新进展 (v5.2.0)

### ✅ 已完成功能
- 集群协作核心协议扩展：`create_auth_response` 支持 `task_id` 字段
- 连接层转发与审批队列：`ClusterManager.pending_auth`、`handle_auth_request`、`respond_auth`
- 风险等级映射：`RISK_LEVEL_MAP`（run_code/execute_code/execute_command=3；write_file/delete_file=2；read_file/search_files/list_directory=1）
- Web 审批 API：`GET /api/cluster/auth/pending`、`POST /api/cluster/auth/respond`
- 前端 UI：待审批面板、批准/拒绝按钮、自动轮询
- 环境变量控制：`CLUSTER_AUTO_APPROVE`（默认 true，设为 false 启用手动审批）
- 版本号升级至 5.2.0


### 📝 后续任务 (待白虎/朱雀)
1. **端口冲突处理**：修改 `CLUSTER_MANAGER_PORT` 为 30002 并同步所有相关配置
2. **端到端验证**：
   - 启动 manager 与 worker 实例
   - 发布任务触发授权请求
   - 在 UI 完成手动批准/拒绝
   - 检查任务状态流转
3. **单元/集成测试**：为核心流程编写自动化测试
4. **风险策略细化**：扩展 `RISK_LEVEL_MAP`，支持可配置规则
5. **审计与日志**：增加授权决策的持久化与操作审计
6. **文档同步**：更新 README、部署指南、API 文档（OpenAPI）
