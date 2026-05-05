
import json
import socket
import threading
import time
import uuid
import asyncio
from enum import Enum
from typing import Dict, Any, Optional
from logger import logger
from .protocol import MessageType, ClusterMessage, create_capability_advertisement, create_leave_notification
from .discovery import ClusterDiscovery

# 临时能力评估（Phase 1简易版）
# Phase 3 将被 capability.py 替代
MODEL_RANKINGS = {
    "qwen2.5-coder:7b": 0.95,
    "qwen2.5:7b": 0.85,
    "llama3:8b": 0.80,
    "phi3:3.8b": 0.60,
    "mistral:7b": 0.70
}

def evaluate_capability_simple(node_info: Dict[str, Any]) -> float:
    """
    简易能力评估（Phase 1原型）
    
    评估维度：
    - 模型分（基于排行榜）
    - GPU分（如果提供）
    
    Returns:
        0.0-1.0 的能力分
    """
    model = node_info.get("model", "unknown")
    model_score = MODEL_RANKINGS.get(model, 0.5)
    
    # GPU加成（如果有显存信息）
    gpu_bonus = 0.0
    if "gpu" in node_info:
        gpu_name = node_info["gpu"].lower()
        if "rtx 4090" in gpu_name or "rtx 40" in gpu_name:
            gpu_bonus = 0.1
        elif "rtx 30" in gpu_name or "rtx 20" in gpu_name:
            gpu_bonus = 0.05
    
    total = model_score + gpu_bonus
    return min(total, 1.0)


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ClusterNode:
    """集群节点定义"""
    def __init__(self, node_id: str, ip: str, model: str, role: str, mode: str, capability_score: float = 0.5):
        self.node_id = node_id
        self.ip = ip
        self.model = model
        self.role = role # 如: 架构师, 文案, 工程师
        self.mode = mode # auto 或 manual (人工干预)
        self.status = "online"
        self.capability_score = capability_score  # 能力评估分 (0.0-1.0)
        self.last_heartbeat = time.time()
        self.connection: Optional[socket.socket] = None  # 持久TCP连接
        self.pending_tasks = []  # 待处理任务队列
        self.tasks = {}
        self._task_lock = threading.Lock()
        self.ws_connections = []
        self.capabilities = [] # 待通过接口获取
        
        # Phase 3 扩展：负载监控字段
        self.load_cpu: float = 0.0        # CPU 负载 (0.0-1.0)
        self.load_memory: float = 0.0     # 内存使用率 (0.0-1.0)
        self.gpu_memory: float = 0.0      # GPU 显存 (GB)
        self.cpu_cores: int = 4           # CPU 核心数
        self.queue_length: int = 0        # 本地队列长度（可用 len(pending_tasks) 替代）
        self.task_start_time: Dict[str, float] = {}  # 任务开始时间戳

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "ip": self.ip,
            "model": self.model,
            "role": self.role,
            "mode": self.mode,
            "status": self.status,
            "capability_score": round(self.capability_score, 3),
            "last_heartbeat": self.last_heartbeat
        }


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
            self.pending_tasks.append(task_id)
        return task_id

    def start_task(self, task_id: str):
        with self._task_lock:
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = TaskStatus.RUNNING.value
                self.tasks[task_id]["started_at"] = time.time()
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

    def notify_status_change(self, task_id: str):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            event = {"task_id": task_id, "status": task["status"]}
            if task["status"] == TaskStatus.COMPLETED.value:
                event["result"] = task["result"]
            elif task["status"] == TaskStatus.FAILED.value:
                event["error"] = task["error"]
            try:
                asyncio.create_task(self._broadcast_event(event))
            except RuntimeError:
                pass

    def receive_assignment(self, task_id: str, task_type: str, description: str, parameters: Dict[str, Any] = None):
        """接收来自 manager 的任务分配"""
        with self._task_lock:
            if task_id not in self.tasks:
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
                self.pending_tasks.append(task_id)

    def send_task_result(self, task_id: str, status: str, result=None, error=None):
        """向 manager 发送任务执行结果"""
        if not self.connection:
            return
        try:
            from .protocol import create_task_update
            msg = create_task_update(
                task_id=task_id,
                status=status,
                result=result,
                error=error
            )
            self.connection.sendall(msg.serialize())
        except Exception as e:
            logger.error(f"发送任务结果失败: {e}")

    async def _broadcast_event(self, event: dict):
        for ws in self.ws_connections:
            try:
                await ws.send_json(event)
            except:
                pass


class ClusterManager:
    """集群管理中心 (房主端)"
    
    # Phase 3 扩展：智能调度能力
    """
    def __init__(self):
        self.nodes: Dict[str, ClusterNode] = {}
        self.current_project = "Unnamed Project"
        self.room_id = str(uuid.uuid4())
        self.room_name = "Default-Room"
        self.discovery = None
        self._server: Optional["ClusterServer"] = None
        
        # 调度器与评估器（Phase 3 动态注入）
        self.scheduler: Optional[TaskScheduler] = None
        self.assessor: Optional[CapabilityAssessor] = None
        
        # 任务分配追踪
        self.task_assignments: Dict[str, str] = {}   # task_id -> node_id
        self.task_timeouts: Dict[str, float] = {}    # task_id -> 超时时间戳
        self.task_metadata: Dict[str, Dict] = {}     # task_id -> {type, description, parameters}
        
        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        
        # 配置参数（可从 config.py 读取）
        self.max_retries = 3
        self.monitor_interval = 5  # 秒

    def add_node(self, node_info: Dict[str, Any]):
        """
        添加节点到集群
        
        Args:
            node_info: 节点信息字典，应包含:
                - node_id
                - ip
                - model
                - role
                - mode
                - capability_score (可选，默认为0.5)
        """
        node = ClusterNode(
            node_id=node_info['node_id'],
            ip=node_info['ip'],
            model=node_info.get('model', 'unknown'),
            role=node_info.get('role', 'worker'),
            mode=node_info.get('mode', 'auto'),
            capability_score=node_info.get('capability_score', 0.5)
        )
        self.nodes[node.node_id] = node
        logger.info(f"🤝 [Cluster] 节点 {node.node_id} ({node.role}, 能力分: {node.capability_score:.2f}) 已加入集群")

    def remove_node(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"💔 [Cluster] 节点 {node_id} 已离开")

    def get_cluster_map(self):
        return {nid: n.to_dict() for nid, n in self.nodes.items()}
    
    # ============================================
    # Phase 3: 调度器管理
    # ============================================
    def set_scheduler(self, scheduler: TaskScheduler, assessor: CapabilityAssessor):
        """
        注入调度器和评估器（由 web_app.py startup 调用）
        
        Args:
            scheduler: TaskScheduler 实例
            assessor: CapabilityAssessor 实例
        """
        self.scheduler = scheduler
        self.assessor = assessor
        logger.info("✅ [ClusterManager] 调度器与评估器已注入", strategy=scheduler.strategy)
    
    def start_monitoring(self, interval: int = 5):
        """启动后台任务监控线程"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("[ClusterManager] 监控线程已在运行")
            return
        
        self.monitor_interval = interval
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("✅ [ClusterManager] 任务监控线程已启动", interval=interval)
    
    def stop_monitoring(self):
        """停止监控线程"""
        self._monitor_running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
    
    def _monitor_loop(self):
        """监控循环：检查任务超时与节点状态"""
        while self._monitor_running:
            try:
                self.monitor_tasks()
                time.sleep(self.monitor_interval)
            except Exception as e:
                logger.error("[ClusterManager] 监控循环异常", error=str(e))
    
    def assign_task(self, task_type: str, description: str, parameters: Dict[str, Any] = None) -> Optional[str]:
        """
        Manager 分配任务给最优节点（核心调度逻辑）
        
        流程：
        1. 调用 scheduler 选择最优节点
        2. 发送 TaskAssignment 消息（通过 TCP）
        3. 记录任务分配关系与超时
        4. 记录任务元数据备用
        
        Returns:
            task_id 或 None（若无可用节点）
        """
        if not self.scheduler:
            logger.error("❌ [ClusterManager] Scheduler 未初始化，无法分配任务")
            return None
        
        # 生成任务 ID
        task_id = str(uuid.uuid4())
        parameters = parameters or {}
        
        # 选择节点
        task = {
            "task_type": task_type,
            "description": description,
            "parameters": parameters
        }
        node = self.scheduler.schedule(task)
        
        if not node:
            logger.error("❌ [ClusterManager] 无可用节点接受任务", task_type=task_type)
            return None
        
        # 发送 TaskAssignment 消息（通过节点的连接）
        try:
            from .protocol import create_task_assignment
            message = create_task_assignment(
                sender_id=self.current_project or "manager",
                target_id=node.node_id,
                task_id=task_id,
                task_type=task_type,
                description=description,
                parameters=parameters
            )
            # 通过节点连接发送（假设 node.connection 已建立）
            if node.connection:
                node.connection.sendall(message.to_json().encode('utf-8'))
                logger.info(
                    "📨 [ClusterManager] 任务已分配",
                    task_id=task_id,
                    node=node.node_id,
                    model=node.model,
                    task_type=task_type
                )
            else:
                logger.error(f"❌ [ClusterManager] 节点 {node.node_id} 无活跃连接，无法发送任务")
                return None
        except Exception as e:
            logger.error("❌ [ClusterManager] 发送任务分配消息失败", task_id=task_id, error=str(e))
            return None
        
        # 记录分配关系
        self.task_assignments[task_id] = node.node_id
        self.task_timeouts[task_id] = time.time() + 300  # 5 分钟超时
        self.task_metadata[task_id] = {
            "task_type": task_type,
            "description": description,
            "parameters": parameters
        }
        
        logger.info(
            "✅ [ClusterManager] 任务分配完成",
            task_id=task_id,
            node=node.node_id,
            timeout=300
        )
        return task_id
    
    def monitor_tasks(self):
        """
        后台监控：检查任务超时与失败状态
        
        逻辑：
        - 扫描 task_timeouts，对超时任务触发重派
        - 检查节点健康状况（可选）
        """
        now = time.time()
        timeout_count = 0
        
        for task_id, deadline in list(self.task_timeouts.items()):
            if now > deadline:
                node_id = self.task_assignments.get(task_id)
                if node_id and node_id in self.nodes:
                    logger.warning(
                        "⏰ [ClusterManager] 任务超时，触发重派",
                        task_id=task_id,
                        original_node=node_id,
                        timeout=now - deadline
                    )
                    self._reassign_task(task_id)
                    timeout_count += 1
                else:
                    # 节点已失效，清理记录
                    self._cleanup_task(task_id)
        
        if timeout_count > 0:
            logger.info("[ClusterManager] 本轮重派完成", count=timeout_count)
    
    def _reassign_task(self, task_id: str):
        """
        重派任务（由于超时或失败）
        
        流程：
        1. 从 task_metadata 恢复任务信息
        2. 重新调度（可能选择不同节点）
        3. 更新分配记录
        """
        if task_id not in self.task_metadata:
            logger.error(f"❌ [ClusterManager] 无法重派任务：元数据丢失 task_id={task_id}")
            self._cleanup_task(task_id)
            return
        
        meta = self.task_metadata[task_id]
        
        # 可选：限制重试次数（检查原分配节点）
        # TODO: 实现重试计数逻辑
        
        logger.info("🔄 [ClusterManager] 正在重派任务", task_id=task_id, **meta)
        
        # 重新分配（相当于新任务）
        new_task_id = self.assign_task(
            task_type=meta["task_type"],
            description=meta["description"],
            parameters=meta["parameters"]
        )
        
        if new_task_id:
            # 原任务记录清理（新任务已生成新 ID）
            self._cleanup_task(task_id)
            logger.info("✅ [ClusterManager] 重派成功", old_task_id=task_id, new_task_id=new_task_id)
        else:
            logger.error("❌ [ClusterManager] 重派失败，无可用节点", task_id=task_id)
            # 保留原 task_id，稍后再次重试
    
    def _cleanup_task(self, task_id: str):
        """清理任务记录"""
        self.task_assignments.pop(task_id, None)
        self.task_timeouts.pop(task_id, None)
        self.task_metadata.pop(task_id, None)
    
    def handle_node_failure(self, node_id: str):
        """
        处理节点失效：将该节点上所有任务重新分配
        
        Args:
            node_id: 失效的节点 ID
        """
        logger.warning("🚨 [ClusterManager] 节点失效，重新分配其任务", node_id=node_id)
        
        # 找出该节点上的所有任务
        affected_tasks = [
            tid for tid, nid in self.task_assignments.items()
            if nid == node_id
        ]
        
        for task_id in affected_tasks:
            self._reassign_task(task_id)
        
        # 移除失效节点
        self.remove_node(node_id)
    
    def get_node_load_info(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有节点的负载信息（用于监控展示）
        
        Returns:
            {node_id: {load_cpu, load_memory, pending_tasks_count, ...}}
        """
        load_info = {}
        for nid, node in self.nodes.items():
            load_info[nid] = {
                "load_cpu": getattr(node, "load_cpu", 0.0),
                "load_memory": getattr(node, "load_memory", 0.0),
                "pending_tasks": len(getattr(node, "pending_tasks", [])),
                "status": node.status,
                "model": node.model,
                "capability_score": node.capability_score
            }
        return load_info
    
    def get_scheduler_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        if self.scheduler:
            return self.scheduler.get_stats()
        return {"error": "Scheduler not initialized"}

    
    # ============================================
    # 原有方法保持不变
    # ============================================
    
    

    def handle_heartbeat(self, node_id: str, load_info: Dict[str, Any]):
        node = self.nodes.get(node_id)
        if node:
            node.load_cpu = load_info.get("load_cpu", 0.0)
            node.load_memory = load_info.get("load_memory", 0.0)
            node.queue_length = load_info.get("queue_length", 0)
            node.last_heartbeat = time.time()
        else:
            logger.warning("心跳来自未知节点", node_id=node_id)

    def handle_task_update(self, node_id: str, task_id: str, status: str, result=None, error=None):
        node = self.nodes.get(node_id)
        if node:
            if status == "completed":
                node.complete_task(task_id, result)
            elif status == "failed":
                node.fail_task(task_id, error)
            # 清理追踪记录
            self.task_assignments.pop(task_id, None)
            self.task_timeouts.pop(task_id, None)
            self.task_metadata.pop(task_id, None)
            # 通知前端
            node.notify_status_change(task_id)
        else:
            logger.warning("任务状态更新来自未知节点", node_id=node_id, task_id=task_id)

    def start_server(self, host: str = "0.0.0.0", port: int = 30001):
        """启动房主端 TCP 服务器，监听节点加入请求"""
        if self._server is None:
            self._server = ClusterServer(self, host, port)
            self._server.start()
            # 启动房间广播服务
            if not self.discovery:
                self.discovery = ClusterDiscovery(room_name=self.room_name, host_port=port)
            self.discovery.start_hosting()
            logger.info(f"🌐 [Cluster] 房主服务器已启动: {host}:{port}")
        else:
            logger.warning("[Cluster] 房主服务器已在运行")

    def stop_server(self):
        """停止房主端服务器"""
        if self._server:
            self._server.stop()
            self._server = None


class ClusterServer:
    """房主端 TCP 服务器：接收客户端加入请求"""
    def __init__(self, manager: ClusterManager, host: str = "0.0.0.0", port: int = 30001):
        self.manager = manager
        self.host = host
        self.port = port
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """在后台线程启动服务器"""
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def _run_server(self):
        """服务器主循环"""
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)
            logger.info(f"👂 [ClusterServer] 监听 {self.host}:{self.port}，等待节点加入...")

            while self._running:
                try:
                    conn, addr = self._server_socket.accept()
                    # 为每个客户端创建独立线程处理
                    threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error(f"[ClusterServer] 接受连接出错: {e}")
        except Exception as e:
            logger.error(f"[ClusterServer] 服务器启动失败: {e}")
        finally:
            if self._server_socket:
                self._server_socket.close()

    def _handle_client(self, conn: socket.socket, addr):
        """处理客户端连接（加入后持续接收消息）"""
        node = None
        try:
            # 第一步：处理 join 消息
            data = conn.recv(4096)
            if not data:
                return
            msg = json.loads(data.decode('utf-8'))
            if msg.get("type") != "join":
                logger.warning(f"[ClusterServer] 收到非join消息: {msg}")
                response = {"type": "ack", "status": "error", "reason": "仅接受 join 消息"}
                conn.sendall(json.dumps(response).encode('utf-8'))
                return

            # 构建节点信息，并进行能力评估
            node_info = {
                "node_id": msg.get('node_id'),
                "ip": addr[0],  # 使用客户端IP
                "model": msg.get('model', 'unknown'),
                "role": msg.get('role', 'worker'),
                "mode": msg.get('mode', 'auto')
            }
            # 能力评估（Phase 1简易版）
            node_info['capability_score'] = evaluate_capability_simple({
                'model': node_info['model'],
                'gpu': msg.get('gpu'),
                'vram': msg.get('vram')
            })
            logger.info(f"📊 [ClusterServer] 节点 {node_info['node_id']} 能力评估: {node_info['capability_score']:.2f}")

            self.manager.add_node(node_info)
            node = self.manager.nodes.get(node_info['node_id'])
            if node:
                node.connection = conn
                node.ip = addr[0]
            response = {"type": "ack", "status": "ok", "reason": "加入成功"}
            conn.sendall(json.dumps(response).encode('utf-8'))

            # 进入消息循环，处理心跳和任务状态更新
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                try:
                    msg = json.loads(data.decode('utf-8'))
                    msg_type = msg.get("type")
                    if msg_type == "heartbeat":
                        node_id = msg.get("node_id")
                        load_info = msg.get("load", {})
                        self.manager.handle_heartbeat(node_id, load_info)
                    elif msg_type == "task_update":
                        node_id = msg.get("node_id")
                        task_id = msg.get("task_id")
                        status = msg.get("status")
                        result = msg.get("result")
                        error = msg.get("error")
                        self.manager.handle_task_update(node_id, task_id, status, result, error)
                    else:
                        logger.warning(f"[ClusterServer] 未知消息类型: {msg_type}")
                except json.JSONDecodeError:
                    logger.error(f"[ClusterServer] 解析消息失败")
                except Exception as e:
                    logger.error(f"[ClusterServer] 处理消息异常: {e}")
        except Exception as e:
            logger.error(f"[ClusterServer] 处理客户端异常: {e}")
        finally:
            if node:
                node.connection = None
                node.status = "offline"
            try:
                conn.close()
            except:
                pass

    def stop(self):
        """停止服务器"""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass


class ClusterClient:
    """客户端：连接房主并注册节点信息"""
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None  # 保存持久连接

    def join(self, host: str, port: int, node_info: Dict[str, Any]) -> bool:
        """
        连接到房主服务器并发送加入请求，保持连接打开
        
        Args:
            host: 房主IP地址
            port: 房主监听端口（默认30001）
            node_info: 节点信息字典，应包含 node_id, model, role, mode, gpu(可选), vram(可选)
        
        Returns:
            True 表示加入成功，False 表示失败
        """
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port))

            msg = {
                "type": "join",
                "node_id": node_info.get("node_id"),
                "model": node_info.get("model", "unknown"),
                "role": node_info.get("role", "worker"),
                "mode": node_info.get("mode", "auto"),
                "gpu": node_info.get("gpu"),  # 可选
                "vram": node_info.get("vram")   # 可选 GB
            }
            sock.sendall(json.dumps(msg).encode('utf-8'))

            response_data = sock.recv(4096)
            response = json.loads(response_data.decode('utf-8'))
            if response.get("status") == "ok":
                logger.info(f"✅ [ClusterClient] 成功加入房间 {host}:{port}")
                # 保持连接，不关闭
                self.socket = sock
                return True
            else:
                logger.error(f"❌ [ClusterClient] 加入失败: {response.get('reason', '未知错误')}")
                return False
        except socket.timeout:
            logger.error(f"❌ [ClusterClient] 连接超时: {host}:{port}")
            return False
        except ConnectionRefusedError:
            logger.error(f"❌ [ClusterClient] 连接被拒绝: {host}:{port}")
            return False
        except Exception as e:
            logger.error(f"❌ [ClusterClient] 连接异常: {e}")
            return False
        # 不再关闭 socket
    
    def close(self):
        """关闭持久连接"""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
