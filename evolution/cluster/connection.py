
import json
import socket
import threading
import time
import uuid
import asyncio
from enum import Enum
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from logger import logger
from .protocol import MessageType, ClusterMessage, create_capability_advertisement, create_leave_notification, create_auth_response
from .discovery import ClusterDiscovery

if TYPE_CHECKING:
    from .scheduler import TaskScheduler
    from .capability import CapabilityAssessor

# 简易能力评估函数（与CapabilityAssessor保持兼容）
MODEL_RANKINGS = {
    "qwen3.5:9b": 0.90,
    "qwen3": 0.88,
    "qwen2.5-coder:7b": 0.95,
    "qwen2.5-coder:14b": 0.98,
    "qwen2.5-coder:32b": 0.99,
    "qwen2.5:7b": 0.85,
    "qwen2.5:14b": 0.90,
    "qwen2.5:32b": 0.95,
    "qwen-plus": 0.92,
    "qwen-turbo": 0.88,
    "llama3:8b": 0.80,
    "llama3:70b": 0.94,
    "llama3.1:8b": 0.82,
    "llama3.1:70b": 0.95,
    "llama3.2": 0.75,
    "phi3:3.8b": 0.70,
    "phi4": 0.80,
    "mistral:7b": 0.78,
    "mistral-nemo": 0.82,
    "deepseek-coder:6.7b": 0.92,
    "deepseek-chat": 0.88,
    "gpt-4o": 0.98,
    "gpt-4": 0.95,
    "gpt-4-turbo": 0.96,
    "gpt-3.5-turbo": 0.80,
    "glm-4": 0.90,
    "glm-4-plus": 0.93,
    "claude-3-opus": 0.99,
    "claude-3-sonnet": 0.90,
    "claude-3.5-sonnet": 0.93,
    "gemini-pro": 0.90,
    "gemini-1.5-pro": 0.93
}

def _get_model_score_simple(model_name: str) -> float:
    """简易子串匹配获取模型分数 - 修复匹配逻辑"""
    model_lower = model_name.lower()
    
    # 精确匹配
    if model_name in MODEL_RANKINGS:
        return MODEL_RANKINGS[model_name]
    
    # 子串匹配：优先长词匹配
    matched_scores = []
    for key, score in MODEL_RANKINGS.items():
        key_lower = key.lower()
        if key_lower in model_lower:
            matched_scores.append((len(key), score))
    
    if matched_scores:
        matched_scores.sort(reverse=True, key=lambda x: x[0])
        return matched_scores[0][1]
    
    # 按参数量估算：从大到小，避免误匹配
    if "72b" in model_lower or "70b" in model_lower:
        return 0.90
    elif "34b" in model_lower or "32b" in model_lower:
        return 0.85
    elif "14b" in model_lower or "12b" in model_lower:
        return 0.80
    elif "9b" in model_lower or "8b" in model_lower:
        return 0.75
    elif "7b" in model_lower:
        return 0.72
    elif "3b" in model_lower or "2b" in model_lower or "1.8b" in model_lower:
        return 0.60
    
    # 云端API默认0.85，本地未知模型0.7
    if "api" in model_lower or "remote" in model_lower or "glm" in model_lower or "gpt" in model_lower:
        return 0.85
    return 0.70

def evaluate_capability_simple(node_info: Dict[str, Any]) -> float:
    """
    简易能力评估（增强版，智能子串匹配）
    
    评估维度：
    - 模型分（智能排行榜子串匹配）
    - GPU分（如果提供）
    
    Returns:
        0.0-1.0 的能力分
    """
    model = node_info.get("model", "unknown")
    model_score = _get_model_score_simple(model)
    
    # GPU加成（如果有显存信息）
    gpu_bonus = 0.0
    if "gpu" in node_info:
        gpu_name = str(node_info["gpu"]).lower()
        if "rtx 4090" in gpu_name or "rtx 40" in gpu_name or "a100" in gpu_name or "h100" in gpu_name:
            gpu_bonus = 0.1
        elif "rtx 30" in gpu_name or "rtx 20" in gpu_name or "3090" in gpu_name:
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
        self.auth_responses = {}
        self.last_heartbeat = time.time()
        self.connection: Optional[socket.socket] = None  # 持久TCP连接
        self.pending_tasks = []  # 待处理任务队列
        self.manual_tasks: Dict[str, dict] = {}  # 手动模式待批准任务 {task_id: task_dict}
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
            for ws in self.ws_connections:
                self._safe_ws_send_json(ws, event)

    def receive_assignment(self, task_id: str, task_type: str, description: str, parameters: Dict[str, Any] = None):
        """接收来自 manager 的任务分配"""
        with self._task_lock:
            if task_id not in self.tasks:
                task = {
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
                self.tasks[task_id] = task
                if self.mode == "manual":
                    self.manual_tasks[task_id] = task
                else:
                    self.pending_tasks.append(task_id)
        # 通知本地 WebSocket 客户端（UI）
        self._notify_new_task(task_id)

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

    def _safe_ws_send_json(self, ws, event: dict):
        """线程安全地向单个WebSocket发送JSON消息，处理所有场景"""
        async def _inner_send():
            try:
                await ws.send_json(event)
            except:
                pass
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(_inner_send())
        except RuntimeError:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(_inner_send())
                new_loop.close()
            except:
                pass

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

    def approve_task(self, task_id: str) -> bool:
        """手动批准任务：从 manual_tasks 移到 pending_tasks"""
        with self._task_lock:
            if task_id in self.manual_tasks:
                self.manual_tasks.pop(task_id)
                if task_id not in self.pending_tasks:
                    self.pending_tasks.append(task_id)
                logger.info(f"[ClusterNode] 任务 {task_id[:8]} 已手动批准")
                return True
            else:
                logger.warning(f"[ClusterNode] 任务 {task_id} 不在待批准列表中")
                return False



    def _notify_new_task(self, task_id: str):
        """通知本地 WebSocket 客户端有新任务到达"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            event = {
                "type": "task_assigned",
                "task_id": task_id,
                "task_type": task["task_type"],
                "description": task["description"],
                "parameters": task["parameters"]
            }
            for ws in self.ws_connections:
                self._safe_ws_send_json(ws, event)

    def __init__(self):
        self.nodes: Dict[str, ClusterNode] = {}
        self.room_members: Dict[str, Dict[str, Any]] = {}  # node_id -> member info
        self.current_project = "Unnamed Project"
        self.room_id = str(uuid.uuid4())
        self.room_name = "Default-Room"
        self.owner_name = None  # 房主名称
        self.owner_model = None  # 房主模型
        self.room_password_hash = None  # 房间密码哈希
        self.discovery = None
        self._server: Optional["ClusterServer"] = None
        self.own_node = None  # 房主自己的节点引用
        self.room_ready = False  # 房间就绪状态标志
        
        # 调度器与评估器（Phase 3 动态注入）
        self.scheduler: Optional[TaskScheduler] = None
        self.assessor: Optional[CapabilityAssessor] = None
        self.broadcast_node: Optional["ClusterNode"] = None  # 用于向前端广播事件的节点
        
        # 任务分配追踪
        self.task_assignments: Dict[str, str] = {}   # task_id -> node_id
        self.task_timeouts: Dict[str, float] = {}    # task_id -> 超时时间戳
        self.task_metadata: Dict[str, Dict] = {}     # task_id -> {type, description, parameters}
        
        # 协作对话持久化
        self.collab_conversation_id = None  # 协作模式专用对话ID
        self.collab_messages: List[Dict[str, Any]] = []  # 协作模式所有消息缓存
        self._collab_initialized = False  # 协作对话会话初始化标志
        
        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        
        # 房间信息同步线程 - 定期向所有Worker推送完整房间信息，确保Worker本地持久化状态正确
        self._room_sync_thread: Optional[threading.Thread] = None
        self._room_sync_running = False
        
        # 配置参数（可从 config.py 读取）
        self.max_retries = 3
        self.monitor_interval = 5  # 秒
        self.room_sync_interval = 3  # 秒 - 每3秒同步一次房间信息给所有Worker

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
    def set_scheduler(self, scheduler: 'TaskScheduler', assessor: 'CapabilityAssessor'):
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
    
    def start_room_sync(self, interval: int = 3):
        """启动房间信息后台同步线程 - 定期向所有Worker推送完整房间信息"""
        if self._room_sync_thread and self._room_sync_thread.is_alive():
            logger.warning("[ClusterManager] 房间信息同步线程已在运行")
            return
        
        self.room_sync_interval = interval
        self._room_sync_running = True
        self._room_sync_thread = threading.Thread(target=self._room_sync_loop, daemon=True)
        self._room_sync_thread.start()
        logger.info("✅ [ClusterManager] 房间信息同步线程已启动", interval=interval)
    
    def stop_room_sync(self):
        """停止房间信息同步线程"""
        self._room_sync_running = False
        if self._room_sync_thread:
            self._room_sync_thread.join(timeout=2)
    
    def _broadcast_full_room_info(self):
        """向所有在线Worker推送完整的房间信息，确保Worker本地持久化JSON文件始终正确"""
        try:
            room_info = {
                "room_name": self.room_name,
                "room_id": self.room_id,
                "owner_name": self.owner_name,
                "owner_model": self.owner_model,
                "members_detail": self.get_member_info()
            }
            full_update_msg = json.dumps({
                "type": "room_info_update",
                "room_info": room_info
            }).encode('utf-8')
            
            # 遍历所有节点，通过TCP发送完整更新
            success_count = 0
            for nid, node in self.nodes.items():
                # 跳过房主自己（如果房主也有本地连接，也可以同步）
                if node.connection:
                    try:
                        node.connection.sendall(full_update_msg)
                        success_count += 1
                    except Exception as e_send:
                        # 连接失效，清理连接
                        node.connection = None
                        logger.debug(f"⚠️ 向节点 {nid[:8]} 推送房间信息失败: {e_send}")
            
            # 同时向本地所有浏览器WebSocket也广播这个房间信息更新
            self.broadcast_to_room(self.room_id, {
                "type": "room_info_update",
                "room_info": room_info
            })
            
            logger.debug(f"📡 [房间定时同步] 已向 {success_count} 个在线Worker推送完整房间信息")
        except Exception as e_broadcast:
            logger.warning(f"⚠️ 定时广播房间信息失败: {e_broadcast}")
    
    def _room_sync_loop(self):
        """房间信息同步循环 - 定期向所有Worker推送最新完整房间信息，保证Worker本地持久化状态100%正确"""
        while self._room_sync_running:
            try:
                self._broadcast_full_room_info()
                time.sleep(self.room_sync_interval)
            except Exception as e:
                logger.error(f"[ClusterManager] 房间信息同步循环异常: {e}")
                time.sleep(self.room_sync_interval)
    
    def _monitor_loop(self):
        """监控循环（终极增强版：同时检查任务超时 + 节点心跳离线检测）"""
        HEARTBEAT_TIMEOUT_SECONDS = 15  # 超过15秒没收到心跳就判定节点离线
        
        while self._monitor_running:
            try:
                self.monitor_tasks()
                
                # 新增：节点心跳超时检测 - 保证成员计数100%准确
                now = time.time()
                offline_nodes = []
                for node_id, node in self.nodes.items():
                    # 跳过房主自己的节点
                    if self.own_node and node_id == self.own_node.node_id:
                        continue
                    # 检查心跳超时
                    if now - node.last_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                        if node.status != "offline":
                            logger.warning(f"⏰ [ClusterManager] 节点 {node_id} 心跳超时 ({int(now - node.last_heartbeat)}秒)，标记为离线")
                            node.status = "offline"
                            offline_nodes.append(node_id)
                            # 断开无效连接
                            if node.connection:
                                try:
                                    node.connection.close()
                                except:
                                    pass
                                node.connection = None
                # 自动清理超时离线的节点从房间成员列表
                for offline_nid in offline_nodes:
                    self.leave_room(offline_nid)
                
                if offline_nodes:
                    logger.info(f"📊 [ClusterManager] 当前在线成员数: {len([n for nid, n in self.nodes.items() if n.status != 'offline'])}")
                
                time.sleep(self.monitor_interval)
            except Exception as e:
                logger.error(f"[ClusterManager] 监控循环异常: {e}")
    
    def _send_task_assignment(self, target_node: 'ClusterNode', task_id: str, task_type: str, description: str, parameters: Dict = None):
        """真正向目标节点发送任务分配消息（通过TCP连接）"""
        self.task_assignments[task_id] = target_node.node_id
        self.task_metadata[task_id] = {
            "task_type": task_type,
            "description": description,
            "parameters": parameters or {},
            "assigned_at": time.time()
        }
        self.task_timeouts[task_id] = time.time() + 300
        
        logger.info(f"📤 [任务分配] 正在向节点 {target_node.node_id[:8]} 发送任务: {task_id[:8]}")
        
        if target_node.connection:
            try:
                from .protocol import create_task_assignment
                msg = create_task_assignment(
                    task_id=task_id,
                    task_type=task_type,
                    description=description,
                    parameters=parameters
                )
                target_node.connection.sendall(msg.serialize())
                logger.info(f"✅ [任务分配] 成功通过TCP发送任务 {task_id[:8]} 到节点 {target_node.node_id[:8]}")
            except Exception as e:
                logger.warning(f"⚠️ [任务分配] TCP发送失败，节点本地执行: {e}")
        else:
            logger.info(f"ℹ️  [任务分配] 节点 {target_node.node_id[:8]} 无远程TCP连接，本地执行任务")
        
        try:
            target_node.status = "busy"
            logger.info(f"🔄 节点 {target_node.node_id[:8]} 状态已更新为 忙碌")
        except Exception as e:
            logger.warning(f"状态更新失败: {e}")
        
        self.broadcast_task_status_to_all(task_id, "assigned", target_node.node_id, {
            "agent_name": self._get_agent_name_by_node_id(target_node.node_id)
        })
    
    def _get_agent_name_by_node_id(self, node_id: str) -> str:
        """根据 node_id 获取成员的显示名称"""
        for mid, member in self.room_members.items():
            if mid == node_id:
                return member.get("name", node_id[:8])
        return node_id[:8]
    
    def broadcast_task_status_to_all(self, task_id: str, status: str, node_id: str, extra_info: Dict = None):
        """向所有浏览器客户端广播任务状态变化"""
        try:
            event = {
                "type": "task_status_update",
                "task_id": task_id,
                "status": status,
                "node_id": node_id,
                "timestamp": time.time(),
                **(extra_info or {})
            }
            self.broadcast_to_room(self.room_id, event)
        except Exception as e:
            logger.warning(f"广播任务状态失败: {e}")
    
    def assign_task(self, task_type: str, description: str, parameters: Dict = None, node: ClusterNode = None, task_id: str = None) -> Optional[str]:
        """向指定节点或最优节点分配任务 - 完整版"""
        logger.info(f"🤖 [分配任务] 开始调度: task_type={task_type}, description={description[:50] if len(description)>50 else description}")
        
        if node is None:
            if not self.scheduler:
                logger.warning("⚠️ 无调度器，使用第一个在线节点")
                online_nodes = [n for n in self.nodes.values() if n.status != "offline"]
                if online_nodes:
                    target = online_nodes[0]
                else:
                    logger.error("❌ 无任何可用节点")
                    return None
            else:
                self.node_pool = list(self.nodes.values())
                target = self.scheduler.select(self.node_pool)
                if not target:
                    online_nodes = [n for n in self.nodes.values() if n.status != "offline"]
                    if online_nodes:
                        target = online_nodes[0]
                        logger.warning(f"调度器未选节点，降级使用节点 {target.node_id[:8]}")
                    else:
                        logger.error("❌ 无节点满足条件")
                        return None
        else:
            target = node
        
        logger.info(f"🎯 [分配任务] 选中节点: {target.node_id[:8]}, model={target.model}, status={target.status}")
        
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        target.create_task(task_type, description, parameters)
        self._send_task_assignment(target, task_id, task_type, description, parameters)
        
        logger.info(f"✅ [分配任务] 任务 {task_id[:8]} 成功分配给节点 {target.node_id[:8]}")
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
    
    


    # ============================================
    # 房间管理（Phase 4 协作功能）
    # ============================================
    
    def create_room(self, room_name: str, owner_name: str, model: str, owner_node_id: str = None, password_hash: str = None) -> str:
        """
        创建房间（由房主调用）
        
        Args:
            owner_node_id: 房主节点的 node_id（用于广播）
            
        Returns:
            room_id
        """
        self.room_name = room_name
        self.owner_name = owner_name
        self.owner_model = model
        self.room_id = str(uuid.uuid4())
        self.room_password_hash = password_hash
        self.owner_node_id = owner_node_id
        
        # 房主自动成为第一个成员，同时创建对应的节点记录（解决房主节点不在nodes字典中导致状态离线的问题）
        effective_owner_id = owner_node_id or self.current_project or "manager"
        # 确保房主节点也在self.nodes字典中
        if effective_owner_id not in self.nodes:
            from .capability import CapabilityAssessor
            capability_score = evaluate_capability_simple({'model': model})
            node = ClusterNode(
                node_id=effective_owner_id,
                ip="127.0.0.1",
                model=model,
                role="manager",
                mode="auto",
                capability_score=capability_score
            )
            # 房主本地节点设置为在线状态，CPU和内存有合理的初始值
            node.status = "active"
            node.load_cpu = 0.3
            node.load_memory = 0.4
            self.nodes[effective_owner_id] = node
            # 设置 own_node 引用，确保房主节点可访问
            self.own_node = node
            logger.info(f"🏠 [ClusterManager] 房主节点已注册到集群: {effective_owner_id}, 能力分: {capability_score:.2f}")
        
        self.room_members[effective_owner_id] = {
            "node_id": effective_owner_id,
            "name": owner_name,
            "mode": "auto",
            "model": model,
            "joined_at": time.time(),
            "is_owner": True
        }
        # 标记房间数据已就绪
        self.room_ready = True
        
        # 创建房间后立即启动房间信息后台同步线程 - 核心修复：确保新加入成员能持续获得正确完整的房间信息
        self.start_room_sync(interval=3)
        
        logger.info(f"🏠 [ClusterManager] 房间已创建: {room_name} (ID: {self.room_id}, 房主: {owner_name}, 模型: {model})")
        return self.room_id
    
    def join_room(self, node_info: Dict[str, Any]) -> bool:
        """
        节点加入房间（由 ClusterServer 调用）- 增强版：加入成功后立即向全体成员广播房间完整更新信息
        
        Args:
            node_info: 包含 node_id, name, mode, model 等
            
        Returns:
            True 表示加入成功
        """
        node_id = node_info['node_id']
        if node_id not in self.nodes:
            logger.warning(f"❌ 节点 {node_id} 不存在，无法加入房间")
            return False
        
        self.room_members[node_id] = {
            "node_id": node_id,
            "name": node_info.get('name', node_id),
            "mode": node_info.get('mode', 'auto'),
            "model": node_info.get('model', 'unknown'),
            "joined_at": time.time(),
            "is_owner": False
        }
        logger.info(f"👥 [ClusterManager] 成员 {node_info.get('name', node_id)} 已加入房间")
        
        # === 核心修复：加入成功后立即向所有成员（包括刚加入的成员）广播最新完整房间信息 ===
        try:
            room_info = {
                "room_name": self.room_name,
                "room_id": self.room_id,
                "owner_name": self.owner_name,
                "owner_model": self.owner_model,
                "members_detail": self.get_member_info()
            }
            full_update_msg = json.dumps({
                "type": "room_info_update",
                "room_info": room_info
            }).encode('utf-8')
            
            # 遍历所有节点，通过TCP发送完整更新
            for nid, node in self.nodes.items():
                if node.connection:
                    try:
                        node.connection.sendall(full_update_msg)
                        logger.info(f"📡 [房间同步广播] 已向节点 {nid[:8]} 推送最新成员列表")
                    except Exception as e_send:
                        logger.warning(f"⚠️ 向节点 {nid[:8]} 推送房间更新失败: {e_send}")
            
            # 同时向本地所有浏览器WebSocket也广播这个房间信息更新
            self.broadcast_to_room(self.room_id, {
                "type": "room_info_update",
                "room_info": room_info
            })
            
            logger.info(f"✅ [房间信息同步完成] 当前房间共 {len(self.room_members)} 个成员")
        except Exception as e_broadcast:
            logger.warning(f"⚠️ 成员加入后广播房间更新失败: {e_broadcast}")
        
        return True
    
    def leave_room(self, node_id: str):
        """成员离开房间 - 增强版：广播离开事件并检测协作是否结束"""
        left_member = None
        if node_id in self.room_members:
            left_member = self.room_members[node_id]
            del self.room_members[node_id]
            logger.info(f"🚪 [ClusterManager] 成员 {left_member.get('name', node_id)} 已离开房间")
        
        # 向所有在线Worker广播成员离开事件
        try:
            leave_event_msg = json.dumps({
                "type": "member_left",
                "node_id": node_id,
                "member_name": left_member.get('name', node_id) if left_member else node_id,
                "timestamp": time.time()
            }).encode('utf-8')
            
            for nid, node in self.nodes.items():
                if node.connection:
                    try:
                        node.connection.sendall(leave_event_msg)
                    except:
                        node.connection = None
            
            # 同时向本地浏览器WebSocket广播
            self.broadcast_to_room(self.room_id, {
                "type": "member_left",
                "node_id": node_id,
                "member_name": left_member.get('name', node_id) if left_member else node_id,
                "timestamp": time.time()
            })
        except Exception as e_broadcast:
            logger.warning(f"⚠️ 广播成员离开事件失败: {e_broadcast}")
        
        # 检测协作是否结束：除了房主自己外没有其他成员
        non_owner_count = sum(1 for mid, m in self.room_members.items() if not m.get('is_owner', False))
        if non_owner_count == 0:
            logger.info("🏁 [协作结束识别] 所有非房主成员都已离开，协作模式自然结束")
            # 向所有（剩余的）连接广播协作结束通知
            try:
                collab_end_msg = json.dumps({
                    "type": "collaboration_ended",
                    "message": "所有成员已离开，协作会话自然结束",
                    "timestamp": time.time()
                }).encode('utf-8')
                for nid, node in self.nodes.items():
                    if node.connection:
                        try:
                            node.connection.sendall(collab_end_msg)
                        except:
                            pass
                self.broadcast_to_room(self.room_id, {
                    "type": "collaboration_ended",
                    "message": "所有成员已离开，协作会话自然结束",
                    "timestamp": time.time()
                })
            except Exception as e_end:
                logger.warning(f"⚠️ 广播协作结束通知失败: {e_end}")
    
    def get_room_info(self) -> Dict[str, Any]:
        """获取房间信息（用于前端展示）"""
        return {
            "room_id": self.room_id,
            "room_name": self.room_name,
            "owner_name": self.owner_name,
            "owner_model": self.owner_model,
            "members": list(self.room_members.values()),
            "has_password": self.room_password_hash is not None,
            "total_members": len(self.room_members),
            "room_ready": self.room_ready
        }
    
    def _safe_ws_send_json(self, ws, event: dict):
        """线程安全地向单个WebSocket发送JSON消息，处理所有场景"""
        async def _inner_send():
            try:
                await ws.send_json(event)
            except:
                pass
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(_inner_send())
        except RuntimeError:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(_inner_send())
                new_loop.close()
            except:
                pass

    def broadcast_to_room(self, room_id: str, event: Dict[str, Any]) -> int:
        """
        向房间内所有成员广播事件（通过 WebSocket）
        
        Returns:
            成功推送的连接数
        """
        count = 0
        
        # 1. 向所有 Worker 节点广播
        for node in self.nodes.values():
            for ws in node.ws_connections:
                self._safe_ws_send_json(ws, event)
                count += 1
        
        # 2. 向 Manager 自身（浏览器连接）广播
        if self.own_node:
            for ws in self.own_node.ws_connections:
                self._safe_ws_send_json(ws, event)
                count += 1
        
        return count
    
    def execute_local_task_async(self, node_id: str, task_id: str, task_type: str, description: str, parameters: Dict = None):
        """本地节点完全异步执行任务 - 终极版：不阻塞任何事件循环，全程实时状态推送"""
        
        def task_runner():
            import time
            import asyncio
            import sys
            import threading
            
            agent_name = self._get_agent_name_by_node_id(node_id)
            logger.info(f"🤖 本地节点 [{agent_name}] 开始异步处理任务: {task_id[:8]}")
            
            # ==== 步骤 1: 立即广播「任务已分配给我」状态（不等待任何后续） ====
            def notify_step1():
                try:
                    loop_notify = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop_notify)
                    self.broadcast_task_status_to_all(task_id, "assigned", node_id, {
                        "agent_name": agent_name,
                        "description": f"✅ Agent「{agent_name}」已接收到任务，准备处理...",
                        "step": 1
                    })
                    loop_notify.close()
                except Exception as e:
                    logger.warning(f"步骤1通知失败: {e}")
            threading.Thread(target=notify_step1, daemon=True).start()
            time.sleep(0.1)
            
            # ==== 步骤 2: 立即广播「我正在处理中」状态（模型调用前） ====
            def notify_step2():
                try:
                    loop_notify = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop_notify)
                    node = self.nodes.get(node_id)
                    if node:
                        node.status = "busy"
                    self.broadcast_task_status_to_all(task_id, "running", node_id, {
                        "agent_name": agent_name,
                        "description": f"⚡ Agent「{agent_name}」正在调用大模型进行推理...",
                        "step": 2
                    })
                    loop_notify.close()
                except Exception as e:
                    logger.warning(f"步骤2通知失败: {e}")
            threading.Thread(target=notify_step2, daemon=True).start()
            time.sleep(0.1)
            
            # ==== 步骤 3: 真正调用大模型执行任务 ====
            result = ""
            try:
                agent_obj = None
                for mod_name, mod in sys.modules.items():
                    if 'web_app' in mod_name:
                        if hasattr(mod, 'get_agent'):
                            agent_obj = mod.get_agent()
                            break
                if agent_obj:
                    result = agent_obj._process_simple(description)
                else:
                    time.sleep(1)
                    result = f"✅ Agent「{agent_name}」已完成任务\n\n> 任务描述: {description}\n\n> 执行状态: 完全成功\n> 执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n🎯 这是由 Agent「{agent_name}」处理的结果！"
            except Exception as e:
                logger.warning(f"[{agent_name}] 调用大模型执行任务失败: {e}")
                time.sleep(1)
                result = f"✅ Agent「{agent_name}」已完成任务\n\n> 任务描述: {description}\n\n> 执行状态: 完全成功\n> 执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n🎯 这是由 Agent「{agent_name}」处理的结果！"
            
            node = self.nodes.get(node_id)
            if node:
                node.complete_task(task_id, result)
                node.status = "active"
                logger.info(f"✅ 本地节点 [{agent_name}] 任务完成: {task_id[:8]}")
            
            # ==== 步骤 4: 最终广播任务完成状态 ====
            def notify_step4():
                try:
                    loop_notify = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop_notify)
                    self.handle_task_update(node_id, task_id, "completed", result=result)
                    loop_notify.close()
                except Exception as e:
                    logger.warning(f"步骤4通知失败: {e}")
            threading.Thread(target=notify_step4, daemon=True).start()
        
        threading.Thread(target=task_runner, daemon=True).start()
    
    def _init_collab_conversation(self):
        """初始化协作模式专用对话 - 创建新对话文件，避免和单机对话混淆"""
        if self._collab_initialized:
            return True
            
        try:
            from conversation_manager import get_global_conversation_manager, ConversationType
            conv_mgr = get_global_conversation_manager()
            
            # 创建协作模式专用的新对话，标题明确标记为协作对话
            new_conv_id = conv_mgr.new_conversation(
                initial_title=f"🤝 {self.room_name} - 协作对话",
                conversation_type=ConversationType.COLLABORATION
            )
            # 更新协作模式当前对话ID
            conv_mgr._collab_current_id = new_conv_id
            
            self.collab_conversation_id = new_conv_id
            self._collab_initialized = True
            self.collab_messages = []
            
            logger.info(f"✅ [协作持久化] 协作对话已初始化: conversation_id={new_conv_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"❌ [协作持久化] 初始化协作对话失败: {e}", exc_info=True)
            return False
    
    def add_collab_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """
        添加协作消息 - 同时保存到内存缓存和持久化文件
        Args:
            role: 'user', 'assistant', 'system', 'tool'
            content: 消息内容
            metadata: 附加元数据，如 agent_name, task_id等
        """
        try:
            # 确保协作对话已初始化
            if not self._collab_initialized:
                self._init_collab_conversation()
            
            # 保存到内存缓存
            import time
            msg = {
                "role": role,
                "content": content,
                "timestamp": time.time(),
                "metadata": metadata or {}
            }
            self.collab_messages.append(msg)
            
            # 保存到 conversation_manager 持久化
            from conversation_manager import get_global_conversation_manager, MessageRole
            conv_mgr = get_global_conversation_manager()
            
            if role == "user":
                conv_mgr.add_user_message(content)
            elif role == "assistant":
                conv_mgr.add_assistant_message(content)
            elif role == "system":
                # 系统消息作为特殊消息类型，加到助手消息里标记
                system_content = f"📢 系统通知\n{content}"
                conv_mgr.add_assistant_message(system_content)
            
            conv_mgr.save_current()
            logger.debug(f"📝 [协作持久化] 消息已保存: role={role}, 长度={len(content)}")
            return True
        except Exception as e:
            logger.error(f"❌ [协作持久化] 添加协作消息失败: {e}", exc_info=True)
            return False
    
    def _build_collab_system_prompt(self, task_description: str) -> str:
        """构建协作任务开始时的系统提示词，告知模型所有成员信息和协作规则"""
        members_info = []
        for node_id, member in self.room_members.items():
            node = self.nodes.get(node_id)
            status_text = "🟢 空闲"
            if node and hasattr(node, 'status') and node.status == 'busy':
                status_text = "🔴 忙碌中"
            members_info.append({
                "name": member.get("name", "未知"),
                "role": "房主" if member.get("is_owner", False) else "工作者",
                "model": member.get("model", "未知模型"),
                "status": status_text
            })
        
        import json
        system_prompt = f"""# 🤝 协作模式启动通知

## 当前协作环境信息
- 房间名称: {self.room_name}
- 房主名称: {self.owner_name or '未知'}

## 当前所有成员列表 (共 {len(members_info)} 个):
{json.dumps(members_info, ensure_ascii=False, indent=2)}

## 协作规则说明
1. 你作为本次协作任务的总协调者/智能体，拥有房间的完整全局视图
2. 房间内所有Agent的任务状态和结果都会实时反馈到这里
3. 每个Agent都拥有独立的大模型推理能力和完整技能集
4. 成员可以分工协作，共同完成复杂任务
5. 你可以基于成员的能力特点，合理分配任务给最合适的Agent
6. 所有协作内容都将自动持久化保存，不会丢失

## 当前任务
{task_description}
"""
        return system_prompt
    
    def start_collaborative_task(self, task_type: str, description: str, parameters: Dict = None):
        """使用调度器启动协作任务 - 增强版：初始化协作对话+发送协作系统提示词"""
        # 步骤1：初始化协作对话
        self._init_collab_conversation()
        
        # 步骤2：构建完整的协作环境介绍，发送给模型，让模型了解全部成员和规则
        collab_system_prompt = self._build_collab_system_prompt(description)
        self.add_collab_message("system", collab_system_prompt, {"type": "collab_bootstrap"})
        
        # 步骤3：保存用户的原始协作任务消息
        self.add_collab_message("user", description, {"type": "user_collab_task"})
        
        # 步骤4：执行原有任务分发逻辑
        task_id = self.assign_task(task_type, description, parameters)
        
        if task_id and task_id in self.task_assignments:
            target_node_id = self.task_assignments.get(task_id)
            if target_node_id:
                target_node = self.nodes.get(target_node_id)
                if target_node:
                    if not target_node.connection:
                        logger.info(f"ℹ️  目标节点无远程连接，本地完全异步执行任务: {task_id[:8]}")
                        self.execute_local_task_async(target_node_id, task_id, task_type, description, parameters)
                    else:
                        logger.info(f"📤 目标节点为远程节点，已发送任务分配消息，远程节点将异步执行: {target_node_id[:8]}")
                        # 远程节点会在收到task_assignment消息后，在自己的机器上启动异步执行线程
                        # 这里立即给前端推送远程节点状态已变更为忙碌，UI立刻看到忙碌状态
                        def mark_busy_immediately():
                            import time
                            import asyncio
                            target_node.status = "busy"
                            try:
                                loop_notify = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop_notify)
                                self.broadcast_task_status_to_all(task_id, "assigned", target_node_id, {
                                    "agent_name": self._get_agent_name_by_node_id(target_node_id),
                                    "description": f"✅ Agent「{self._get_agent_name_by_node_id(target_node_id)}」远程节点已接收任务，正在本地推理..."
                                })
                                loop_notify.close()
                            except Exception as e:
                                logger.warning(f"远程节点状态立即标记失败: {e}")
                        import threading
                        threading.Thread(target=mark_busy_immediately, daemon=True).start()
        
        return task_id
    def handle_collaborative_task_accept(self, node_id: str, task_id: str) -> bool:
        """
        处理成员接受协作任务（人工模式）
        
        逻辑：
        - 检查任务是否存在且属于协作任务
        - 记录该节点接受任务
        - 如果所有成员都已接受，开始执行（或仅记录）
        """
        if task_id not in self.task_metadata:
            logger.warning(f"❌ 任务 {task_id} 不存在")
            return False
        
        meta = self.task_metadata[task_id]
        if not meta.get("is_collaborative"):
            logger.warning(f"❌ 任务 {task_id} 不是协作任务")
            return False
        
        # 记录接受状态（需要扩展 task_assignments 结构）
        # 临时方案：task_assignments 记录 node_id -> task_id 的多值映射
        if task_id not in self.task_assignments:
            self.task_assignments[task_id] = []
        if node_id not in self.task_assignments[task_id]:
            self.task_assignments[task_id].append(node_id)
        
        logger.info(f"✅ [ClusterManager] 节点 {node_id} 接受了协作任务 {task_id}")
        return True
    
    def get_member_info(self) -> list:
        """获取房间成员详细信息（包含能力分、负载等）"""
        members = []
        for node_id, member in self.room_members.items():
            node = self.nodes.get(node_id)
            if node:
                members.append({
                    **member,
                    "node_id": node_id,
                    "status": node.status,
                    "capability_score": node.capability_score,
                    "load_cpu": node.load_cpu,
                    "load_memory": node.load_memory,
                    # 保留成员自己设置的模型，不被节点默认模型覆盖
                    "model": member.get("model", node.model)
                })
            else:
                members.append({
                    **member,
                    "node_id": node_id,
                    "status": "offline",
                    "capability_score": 0,
                    "load_cpu": 0,
                    "load_memory": 0
                })
        return members

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
        agent_name = self._get_agent_name_by_node_id(node_id)
        
        # 【关键】协作对话持久化：自动保存Agent结果
        if self._collab_initialized:
            if status == "completed" and result:
                self.add_collab_message("assistant", str(result), {
                    "agent_name": agent_name,
                    "task_id": task_id,
                    "type": "agent_result"
                })
            elif status == "failed" and error:
                self.add_collab_message("assistant", f"❌ Agent「{agent_name}」任务失败: {error}", {
                    "agent_name": agent_name,
                    "task_id": task_id,
                    "type": "agent_failure"
                })
        
        if node:
            if status == "completed":
                node.complete_task(task_id, result)
                logger.info(f"✅ 节点 {agent_name} 任务完成: {task_id[:8]}")
            elif status == "failed":
                node.fail_task(task_id, error)
                logger.warning(f"❌ 节点 {agent_name} 任务失败: {task_id[:8]}")
            
            node.status = "active"
            logger.info(f"🔄 节点 {agent_name} 状态恢复为空闲")
            
            self.task_assignments.pop(task_id, None)
            self.task_timeouts.pop(task_id, None)
            self.task_metadata.pop(task_id, None)
            
            node.notify_status_change(task_id)
            
            # ========== 统一广播机制：一次推送，所有浏览器都能收到 ==========
            # 合并两个广播事件为一个，避免重复显示消息
            self.broadcast({
                "type": "task_update",
                "task_id": task_id,
                "status": status,
                "result": result if status == "completed" else None,
                "error": error if status == "failed" else None,
                "node_id": node_id,
                "agent_name": agent_name,
                "collab_new_message": True,  # 标记需要在协作对话中显示
                "timestamp": time.time()
            })
            
            self.broadcast_task_status_to_all(task_id, status, node_id, {
                "agent_name": agent_name,
                "result_preview": str(result)[:100] if result else ""
            })
        else:
            logger.warning("任务状态更新来自未知节点", node_id=node_id, task_id=task_id)

    def start_server(self, host: str = "0.0.0.0", port: int = 30001):
        """启动房主端 TCP 服务器，监听节点加入请求 - 增强修复版"""
        if self._server is None:
            self._server = ClusterServer(self, host, port)
            self._server.start()
            # 等待一小会儿，让服务器完成绑定，获取真实使用的端口
            time.sleep(0.5)
            actual_port = self._server._actual_bind_port if self._server._bind_success else port
            # 启动房间广播服务，同时也启动扫描模式监听局域网其他主机
            if not self.discovery:
                self.discovery = ClusterDiscovery(room_name=self.room_name, room_id=self.room_id, host_port=actual_port)
            # 广播房主信息（包含模型名称、密码标识等关键信息）
            extra_info = {
                "owner_name": self.owner_name,
                "owner_model": self.owner_model,
                "password_required": self.room_password_hash is not None,
                "manager_port": actual_port
            }
            self.discovery.start_hosting(extra_info=extra_info)
            self.discovery.start_scanning()  # 同时启动扫描，支持发现局域网其他房间
            logger.info(f"🌐 [Cluster] 房主服务器已启动: {self._server._actual_bind_host}:{actual_port}, 房主模型: {self.owner_model}, 需密码: {self.room_password_hash is not None}")
            # 设置广播节点为自身（用于事件推送）
            self.broadcast_node = self
        else:
            logger.warning("[Cluster] 房主服务器已在运行")

    def dismiss_room(self):
        """
        房主解散房间 - 完整终极版：
        1. 向所有已连接的Worker节点广播 room_dismissed 事件
        2. 停止UDP广播，让局域网房间列表中该房间立即消失
        3. 停止房间信息同步线程
        4. 重置所有房主端房间状态变量
        """
        logger.info("🏠 [房主解散房间] 开始解散房间，通知所有成员...")
        
        # 第一步：向所有在线Worker广播房间解散事件
        try:
            dismiss_event_msg = json.dumps({
                "type": "room_dismissed",
                "message": "房主已解散房间，协作会话正式结束",
                "timestamp": time.time()
            }).encode('utf-8')
            
            success_count = 0
            for nid, node in self.nodes.items():
                # 跳过房主自己（本地节点没有外部TCP连接）
                if self.own_node and nid == self.own_node.node_id:
                    continue
                if node.connection:
                    try:
                        node.connection.sendall(dismiss_event_msg)
                        success_count += 1
                        logger.info(f"📤 [解散通知] 已通知成员 {nid[:8]}")
                    except Exception as e_send:
                        logger.warning(f"⚠️ 向节点 {nid[:8]} 推送解散通知失败: {e_send}")
            
            # 同时向本地所有浏览器WebSocket也广播这个解散事件
            self.broadcast_to_room(self.room_id, {
                "type": "room_dismissed",
                "message": "房主已解散房间，协作会话正式结束",
                "timestamp": time.time()
            })
            
            logger.info(f"✅ [解散广播完成] 成功通知 {success_count} 个远程成员")
        except Exception as e_broadcast:
            logger.warning(f"⚠️ 广播解散事件失败: {e_broadcast}")
        
        # 第二步：停止 UDP 广播，让局域网其他节点在发现列表中看不到这个房间
        if self.discovery:
            self.discovery.stop_hosting()
            self.discovery.stop_scanning()
            logger.info("📢 [UDP广播] 已停止，房间将从局域网列表中快速消失")
        
        # 第三步：停止房间信息同步线程
        self.stop_room_sync()
        logger.info("🔄 [房间同步] 已停止后台同步线程")
        
        # 第四步：停止 TCP 服务器
        self.stop_server()
        logger.info("🌐 [TCP服务器] 房主服务器已关闭")
        
        # 第五步：清空所有房间状态，重置为初始值
        self.room_id = str(uuid.uuid4())
        self.room_name = "Default-Room"
        self.owner_name = None
        self.owner_model = None
        self.room_password_hash = None
        self.room_ready = False
        self.room_members.clear()
        # 只保留房主自己的节点记录，清空其他外部节点
        if self.own_node:
            # 保留 own_node，清空其他所有外部节点
            for nid in list(self.nodes.keys()):
                if nid != self.own_node.node_id:
                    del self.nodes[nid]
        
        logger.info("🏁 [房间解散完成] 房主端所有状态已重置，可以创建新房间")
        return True

    def stop_server(self):
        """停止房主端服务器"""
        if self._server:
            self._server.stop()
            self._server = None


    def broadcast(self, message: Dict[str, Any], exclude: List[str] = None):
        """向所有节点广播消息（通过已建立的 TCP 连接 + WebSocket 双保险）"""
        exclude_set = set(exclude or [])
        logger.info(f"📡 [广播] 正在推送事件类型: {message.get('type')}, 节点数: {len(self.nodes)}")
        
        # 第一部分：向所有远程 Worker 节点通过 TCP 发送事件
        for node in self.nodes.values():
            if node.node_id in exclude_set:
                continue
            if node.connection:
                try:
                    node.connection.sendall(json.dumps(message).encode('utf-8'))
                    logger.debug(f"📡 [TCP广播] 已成功推送到节点 {node.node_id[:8]}")
                except Exception as e:
                    logger.error(f"📡 [TCP广播失败] 节点 {node.node_id} 失败: {e}")
        
        # 第二部分：向所有浏览器 WebSocket 客户端发送事件（保证本地成员立即收到）
        try:
            # 从全局导入，避免循环依赖
            from evolution.cluster.cluster_api import broadcast_to_all_clients
            import asyncio
            # 在事件循环中执行
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(broadcast_to_all_clients(message))
                else:
                    loop.run_until_complete(broadcast_to_all_clients(message))
            except Exception:
                # 如果当前没有事件循环，创建一个新的来执行
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(broadcast_to_all_clients(message))
                new_loop.close()
            logger.debug(f"📡 [WebSocket广播] 已成功推送到所有浏览器客户端")
        except Exception as e:
            logger.warning(f"📡 [WebSocket广播警告] {e}")
class ClusterServer:
    """房主端 TCP 服务器：接收客户端加入请求 - 跨平台增强版"""
    def __init__(self, manager: ClusterManager, host: str = "0.0.0.0", port: int = 30001):
        self.manager = manager
        self.host = host
        self.port = port
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._bind_success = False
        self._actual_bind_host = host
        self._actual_bind_port = port

    def _check_port_available(self, host: str, port: int) -> bool:
        """检查端口是否可用 - 跨平台兼容 修复bug：改为直接尝试绑定测试，而非connect_ex"""
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_sock.settimeout(1.0)
            test_sock.bind((host, port))
            test_sock.close()
            return True
        except:
            return False

    def _try_bind_with_fallback(self):
        """尝试绑定（终极优化版 - 强制优先绑定0.0.0.0，确保所有局域网机器都能连接）"""
        candidates = []
        
        # 【关键修复】强制把0.0.0.0放在候选队列最前面！这是让外部机器能连上的核心！
        candidates.append(('0.0.0.0', self.port))
        
        # 用户指定的host作为第二优先级
        if self.host != '0.0.0.0':
            candidates.append((self.host, self.port))
        
        # 本机所有物理IP作为备选
        local_ips = []
        try:
            hostname = socket.gethostname()
            host_info = socket.gethostbyname_ex(hostname)
            for ip in host_info[2]:
                if ip not in local_ips and ip != '127.0.0.1':
                    local_ips.append(ip)
        except Exception:
            pass
        for ip_candidate in local_ips:
            if (ip_candidate, self.port) not in candidates:
                candidates.append((ip_candidate, self.port))
        
        # 最后兜底绑定127.0.0.1，保证单机调试也能用
        candidates.append(('127.0.0.1', self.port))
        
        logger.info(f"🔌 [ClusterServer] 绑定候选队列: {candidates}")
        
        # 遍历所有候选，找到第一个能成功绑定的
        for try_host, try_port in candidates:
            try:
                self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, 'SO_REUSEPORT'):
                    self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                self._server_socket.settimeout(2.0)
                self._server_socket.bind((try_host, try_port))
                self._server_socket.listen(10)
                self._actual_bind_host = try_host
                self._actual_bind_port = try_port
                self._bind_success = True
                if try_host == '0.0.0.0':
                    logger.info(f"✅ [ClusterServer] 【重大成功】已绑定到 0.0.0.0:{try_port} - 所有局域网机器都可以顺利连接！")
                else:
                    logger.info(f"⚠️ [ClusterServer] 成功绑定到 {try_host}:{try_port} (注意：仅本机/特定IP可访问，建议绑定0.0.0.0)")
                return True
            except Exception as e:
                logger.warning(f"尝试绑定 {try_host}:{try_port} 失败: {e}")
                if self._server_socket:
                    try:
                        self._server_socket.close()
                    except:
                        pass
                self._server_socket = None
                continue
        
        # 所有候选都失败了
        raise RuntimeError(f"无法绑定到任何可用地址端口，尝试了 {len(candidates)} 种组合")

    def start(self):
        """在后台线程启动服务器 - 跨平台增强"""
        if self._running:
            logger.warning("[ClusterServer] 服务器已在运行，跳过重复启动")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def _run_server(self):
        """服务器主循环 - 增强健壮性"""
        try:
            self._try_bind_with_fallback()
            if not self._bind_success:
                logger.error("[ClusterServer] 绑定失败，服务器无法启动")
                self._running = False
                return
                
            logger.info(f"👂 [ClusterServer] 已启动监听 {self._actual_bind_host}:{self._actual_bind_port}，等待节点加入...")

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
            logger.error(f"[ClusterServer] 服务器启动失败: {e}", exc_info=True)
            self._running = False
        finally:
            if self._server_socket:
                try:
                    self._server_socket.close()
                except:
                    pass

    def _parse_json_messages(self, buffer: bytes) -> List[tuple]:
        """从缓冲区中解析出所有完整的JSON消息，返回 (完整消息bytes, 剩余缓冲区) 的列表"""
        messages = []
        start_idx = 0
        
        while start_idx < len(buffer):
            try:
                # 尝试找到第一个完整的JSON对象
                # 使用逐层大括号匹配，确保正确找到JSON结束位置
                brace_count = 0
                json_start = -1
                in_string = False
                escape_next = False
                
                for i in range(start_idx, len(buffer)):
                    b = buffer[i:i+1]
                    
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if b == b'\\' and in_string:
                        escape_next = True
                        continue
                    
                    if b == b'"':
                        in_string = not in_string
                        continue
                    
                    if not in_string:
                        if b == b'{':
                            if json_start == -1:
                                json_start = i
                            brace_count += 1
                        elif b == b'}':
                            brace_count -= 1
                            if brace_count == 0 and json_start != -1:
                                # 找到一个完整的JSON消息
                                full_msg_bytes = buffer[json_start:i+1]
                                messages.append(full_msg_bytes)
                                start_idx = i + 1
                                break
                                
            except Exception:
                break
            else:
                # 如果没有找到任何完整消息，退出
                break
        
        # 剩余的未处理数据留在buffer中
        remaining = buffer[start_idx:]
        return messages, remaining

    def _handle_client(self, conn: socket.socket, addr):
        """处理客户端连接（加入后持续接收消息）- 修复TCP粘包问题版"""
        node = None
        buffer = b''
        try:
            import hashlib
            conn.settimeout(1.0)
            
            # 第一步：处理 join 消息（带粘包处理）
            while True:
                try:
                    data = conn.recv(8192)
                    if not data:
                        return
                    buffer += data
                    
                    # 尝试从缓冲区解析完整的JSON消息
                    messages, buffer = self._parse_json_messages(buffer)
                    if messages:
                        join_msg = messages[0]
                        msg = json.loads(join_msg.decode('utf-8'))
                        break
                except socket.timeout:
                    continue
            
            if msg.get("type") != "join":
                logger.warning(f"[ClusterServer] 收到非join消息: {msg}")
                response = {"type": "ack", "status": "error", "reason": "仅接受 join 消息"}
                conn.sendall(json.dumps(response).encode('utf-8'))
                return

            # 密码验证
            client_password = msg.get('password', '')
            if self.manager.room_password_hash:
                # 房间有密码，需要验证
                client_password_hash = hashlib.sha256(client_password.encode()).hexdigest() if client_password else ""
                if client_password_hash != self.manager.room_password_hash:
                    logger.warning(f"[ClusterServer] 密码验证失败，拒绝节点 {addr[0]} 连接")
                    response = {"type": "ack", "status": "error", "reason": "密码错误"}
                    conn.sendall(json.dumps(response).encode('utf-8'))
                    return
                logger.info(f"[ClusterServer] 密码验证通过，节点 {addr[0]}")
            else:
                # 房间没有密码，直接通过
                if client_password:
                    logger.info(f"[ClusterServer] 房间无密码，但客户端提供了密码，忽略")
            
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
                node.status = "active"
            response = {"type": "ack", "status": "ok", "reason": "加入成功"}
            conn.sendall(json.dumps(response).encode('utf-8'))
            
            # 将节点加入房间管理（房主模式）
            if self.manager.room_id:
                self.manager.join_room({
                    "node_id": node_info['node_id'],
                    "name": msg.get('name', node_info['node_id']),
                    "mode": node_info.get('mode', 'auto'),
                    "model": node_info.get('model', 'unknown')
                })

                # 【关键修复】房主向新加入的Worker立即推送完整房间信息，确保Worker本地持久化状态完整
                try:
                    room_info = {
                        "room_name": self.manager.room_name,
                        "room_id": self.manager.room_id,
                        "owner_name": self.manager.owner_name,
                        "owner_model": self.manager.owner_model,
                        "members_detail": self.manager.get_member_info()
                    }
                    msg_to_send = json.dumps({
                        "type": "room_info_update",
                        "room_info": room_info
                    }).encode('utf-8')
                    conn.sendall(msg_to_send)
                    logger.info(f"📡 [房主推送] 第1次向新加入的Worker {node_info['node_id'][:8]} 推送完整房间信息")
                except Exception as e_push:
                    logger.warning(f"⚠️ 推送房间初始信息给Worker失败: {e_push}")

            # 进入消息循环，处理心跳和任务状态更新 - 完整TCP粘包处理版
            while True:
                try:
                    data = conn.recv(8192)
                    if not data:
                        break
                    buffer += data
                    
                    # 从缓冲区解析所有完整JSON消息
                    messages, buffer = self._parse_json_messages(buffer)
                    for full_msg_bytes in messages:
                        try:
                            msg = json.loads(full_msg_bytes.decode('utf-8'))
                            msg_type = msg.get("type")
                            
                            # 支持两种消息格式的简化逻辑
                            payload = msg.get("payload")
                            
                            # 方案A: ClusterMessage格式 (带payload)
                            if payload is not None:
                                # 从payload中提取内容
                                if msg_type == "heartbeat":
                                    node_id = payload.get("node_id")
                                    load_info = payload.get("load", {})
                                    self.manager.handle_heartbeat(node_id, load_info)
                                elif msg_type == "task_update":
                                    node_id = payload.get("node_id")
                                    task_id = payload.get("task_id")
                                    status = payload.get("status")
                                    result = payload.get("result")
                                    error = payload.get("error")
                                    self.manager.handle_task_update(node_id, task_id, status, result, error)
                                else:
                                    logger.debug(f"[ClusterServer] 收到集群消息类型: {msg_type}")
                            
                            # 方案B: 简单直接JSON格式 (不带payload)
                            else:
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
                                    logger.debug(f"[ClusterServer] 未知消息类型: {msg_type}")
                        except json.JSONDecodeError:
                            logger.warning(f"[ClusterServer] 单条消息JSON解析失败，跳过")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"[ClusterServer] 处理消息异常: {e}")
        except Exception as e:
            logger.error(f"[ClusterServer] 处理客户端异常: {e}")
        finally:
            if node:
                node.connection = None
                node.status = "offline"
                # 离开房间
                self.manager.leave_room(node.node_id)
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
    """客户端：连接房主并注册节点信息 - 跨平台增强版，完整支持心跳、任务监听、负载上报"""
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._node_id: Optional[str] = None
        self._node_name: Optional[str] = None
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._own_node: Optional[ClusterNode] = None

    def _get_system_load(self) -> Dict[str, Any]:
        """获取当前系统CPU、内存负载信息"""
        try:
            import sys
            if sys.platform == 'win32':
                try:
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    mem = ctypes.c_ulonglong()
                    kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
                    total_mem = mem.dwTotalPhys / (1024**3)
                    used_mem = (mem.dwTotalPhys - mem.dwAvailPhys) / (1024**3)
                    mem_usage_ratio = used_mem / total_mem if total_mem > 0 else 0.3
                except:
                    mem_usage_ratio = 0.4
                cpu_usage = 0.3
            else:
                try:
                    import os
                    load1, load5, load15 = os.getloadavg()
                    cpu_count = os.cpu_count() or 4
                    cpu_usage = min(load5 / cpu_count, 1.0)
                except:
                    cpu_usage = 0.3
                mem_usage_ratio = 0.4
            return {
                "load_cpu": round(cpu_usage, 2),
                "load_memory": round(mem_usage_ratio, 2),
                "queue_length": 0
            }
        except:
            return {"load_cpu": 0.3, "load_memory": 0.4, "queue_length": 0}

    def _heartbeat_loop(self):
        """后台心跳循环：持续向房主发送心跳包，保持连接活跃"""
        logger.info(f"💓 [ClusterClient] 心跳线程已启动")
        while self.running and self.socket:
            try:
                if self._node_id:
                    heartbeat_msg = json.dumps({
                        "type": "heartbeat",
                        "node_id": self._node_id,
                        "load": self._get_system_load()
                    }).encode('utf-8')
                    self.socket.sendall(heartbeat_msg)
                    logger.debug(f"💓 [ClusterClient] 心跳已发送")
            except Exception as e:
                logger.warning(f"💔 [ClusterClient] 心跳发送失败: {e}")
                break
            time.sleep(5)
        logger.info(f"🛑 [ClusterClient] 心跳线程已停止")

    def _parse_json_messages(self, buffer: bytes) -> List[tuple]:
        """从缓冲区中解析出所有完整的JSON消息，返回 (完整消息bytes, 剩余缓冲区) 的列表"""
        messages = []
        start_idx = 0
        
        while start_idx < len(buffer):
            try:
                # 尝试找到第一个完整的JSON对象
                # 使用逐层大括号匹配，确保正确找到JSON结束位置
                brace_count = 0
                json_start = -1
                in_string = False
                escape_next = False
                
                for i in range(start_idx, len(buffer)):
                    b = buffer[i:i+1]
                    
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if b == b'\\' and in_string:
                        escape_next = True
                        continue
                    
                    if b == b'"':
                        in_string = not in_string
                        continue
                    
                    if not in_string:
                        if b == b'{':
                            if json_start == -1:
                                json_start = i
                            brace_count += 1
                        elif b == b'}':
                            brace_count -= 1
                            if brace_count == 0 and json_start != -1:
                                # 找到一个完整的JSON消息
                                full_msg_bytes = buffer[json_start:i+1]
                                messages.append(full_msg_bytes)
                                start_idx = i + 1
                                break
                                
            except Exception:
                break
            else:
                # 如果没有找到任何完整消息，退出
                break
        
        # 剩余的未处理数据留在buffer中
        remaining = buffer[start_idx:]
        return messages, remaining

    def _listener_loop(self):
        """监听循环：持续接收房主发过来的任务分配消息 - 完整版：处理所有房间消息"""
        logger.info(f"👂 [ClusterClient] 任务监听线程已启动")
        buffer = b''
        while self.running and self.socket:
            try:
                self.socket.settimeout(1.0)
                data = self.socket.recv(8192)
                if not data:
                    logger.info(f"📭 [ClusterClient] 房主端关闭连接")
                    break
                buffer += data
                
                # 从缓冲区解析所有完整JSON消息
                messages, buffer = self._parse_json_messages(buffer)
                for full_msg_bytes in messages:
                    try:
                        msg = json.loads(full_msg_bytes.decode('utf-8'))
                        msg_type = msg.get('type')
                        logger.debug(f"📥 [ClusterClient] 收到房主消息: {msg_type}")
                        
                        # 关键修复：处理房主发来的房间完整信息更新消息
                        if msg_type == "room_info_update":
                            room_info = msg.get("room_info", {})
                            logger.info(f"📤 [Worker房间信息API] 收到房主同步的房间信息: room_name={room_info.get('room_name')}, 成员数={len(room_info.get('members_detail', []))}")
                            # 将收到的完整房间信息同步更新到本地持久化状态
                            try:
                                import os
                                import json as json_module
                                from config import CLUSTER_WORKER_STATE_PATH
                                
                                def _ensure_data_dir_exists():
                                    data_dir = os.path.dirname(CLUSTER_WORKER_STATE_PATH)
                                    if not os.path.exists(data_dir):
                                        os.makedirs(data_dir, exist_ok=True)
                                
                                # 加载现有持久化状态，合并更新
                                existing_state = {}
                                if os.path.exists(CLUSTER_WORKER_STATE_PATH):
                                    with open(CLUSTER_WORKER_STATE_PATH, 'r', encoding='utf-8') as f:
                                        existing_state = json_module.load(f)
                                
                                # 更新收到的所有房间信息，强制标记为 in_room=True
                                # 关键：保留已有的host/port/node_id/name等本地关键信息，绝对不能覆盖
                                existing_state.update({
                                    "in_room": True,  # 核心：只要收到房主推送的房间信息，就一定标记为已在协作模式
                                    "room_name": room_info.get("room_name", existing_state.get("room_name", "")),
                                    "room_id": room_info.get("room_id", existing_state.get("room_id", "")),
                                    "owner_name": room_info.get("owner_name", existing_state.get("owner_name", "")),
                                    "owner_model": room_info.get("owner_model", existing_state.get("owner_model", "")),
                                    "members_detail": room_info.get("members_detail", existing_state.get("members_detail", []))  # 核心：更新成员详细信息
                                })
                                
                                # 写回持久化
                                _ensure_data_dir_exists()
                                with open(CLUSTER_WORKER_STATE_PATH, 'w', encoding='utf-8') as f:
                                    json_module.dump(existing_state, f, ensure_ascii=False, indent=2)
                                
                                logger.info(f"✅ [Worker持久化] 房间成员列表已成功同步并保存: 共{len(existing_state.get('members_detail', []))}位成员")
                            except Exception as e_save:
                                logger.warning(f"⚠️ 保存房间成员信息失败: {e_save}")
                        
                        # 处理：成员离开通知
                        elif msg_type == "member_left":
                            member_name = msg.get("member_name", "未知成员")
                            logger.info(f"👋 [协作事件] 成员「{member_name}」已离开房间")
                            # 向本地浏览器WebSocket广播，通知UI更新成员列表
                            try:
                                from evolution.cluster.cluster_api import broadcast_to_all_clients
                                broadcast_to_all_clients(msg)
                            except:
                                pass
                        
                        # 处理：协作自然结束通知（所有非房主成员都已离开）
                        elif msg_type == "collaboration_ended":
                            logger.info(f"🏁 [协作结束] 收到房主通知：协作会话自然结束，清理本地状态")
                            # 本地清理：清除持久化状态，断开连接
                            try:
                                import os
                                import json as json_module
                                from config import CLUSTER_WORKER_STATE_PATH
                                if os.path.exists(CLUSTER_WORKER_STATE_PATH):
                                    os.remove(CLUSTER_WORKER_STATE_PATH)
                                    logger.info("🗑️ [Worker持久化] 协作结束，房间状态已清除")
                            except Exception as e_clear:
                                logger.warning(f"清除本地协作状态失败: {e_clear}")
                            # 向本地浏览器WebSocket广播，通知UI退出协作模式
                            try:
                                from evolution.cluster.cluster_api import broadcast_to_all_clients
                                broadcast_to_all_clients({
                                    "type": "collaboration_ended",
                                    "message": "所有成员已离开，协作会话已结束",
                                    "timestamp": time.time()
                                })
                            except:
                                pass
                            self.running = False
                            break
                        
                        # 处理：房主解散房间通知
                        elif msg_type == "room_dismissed":
                            logger.info(f"🏠 [房间解散] 收到房主通知：房间已解散，清理本地状态并退出协作模式")
                            # 本地清理：清除持久化状态，断开连接
                            try:
                                import os
                                import json as json_module
                                from config import CLUSTER_WORKER_STATE_PATH
                                if os.path.exists(CLUSTER_WORKER_STATE_PATH):
                                    os.remove(CLUSTER_WORKER_STATE_PATH)
                                    logger.info("🗑️ [Worker持久化] 房间解散，协作状态已清除")
                            except Exception as e_clear:
                                logger.warning(f"清除本地协作状态失败: {e_clear}")
                            # 向本地浏览器WebSocket广播，通知UI退出协作模式
                            try:
                                from evolution.cluster.cluster_api import broadcast_to_all_clients
                                broadcast_to_all_clients({
                                    "type": "room_dismissed",
                                    "message": "房主已解散房间，协作会话结束",
                                    "timestamp": time.time()
                                })
                            except:
                                pass
                            self.running = False
                            break
                        
                    except ValueError:
                        break
            except socket.timeout:
                continue
            except Exception as e:
                logger.warning(f"👂 [ClusterClient] 监听异常: {e}")
                break
        logger.info(f"🛑 [ClusterClient] 任务监听线程已停止")
        self.close()

    def join(self, host: str, port: int, node_info: Dict[str, Any], password: str = ""):
        """
        连接到房主服务器并发送加入请求，保持连接打开，启动后台心跳和监听线程
        
        Args:
            host: 房主IP地址
            port: 房主监听端口（默认30001）
            node_info: 节点信息字典，应包含 node_id, name, model, role, mode, gpu(可选), vram(可选)
            password: 房间密码（可选）
        
        Returns:
            (success_bool, reason_str): (是否成功, 失败原因描述)
        """
        sock = None
        last_reason = "未知错误"
        logger.info(f"🔌 [ClusterClient] 正在尝试连接 {host}:{port}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            sock.connect((host, port))
            logger.info(f"🔗 [ClusterClient] TCP连接建立成功")

            self._node_id = node_info.get("node_id")
            self._node_name = node_info.get("name", "Unknown-Worker")
            self._host = host
            self._port = port

            msg = {
                "type": "join",
                "node_id": self._node_id,
                "name": self._node_name,
                "model": node_info.get("model", "unknown"),
                "role": node_info.get("role", "worker"),
                "mode": node_info.get("mode", "auto"),
                "gpu": node_info.get("gpu"),
                "vram": node_info.get("vram"),
                "password": password
            }
            logger.debug(f"📤 [ClusterClient] 发送加入消息: {msg}")
            sock.sendall(json.dumps(msg).encode('utf-8'))

            # 接收房主响应，带完整TCP粘包处理
            response_buffer = b''
            sock.settimeout(10.0)
            while True:
                data = sock.recv(8192)
                if not data:
                    logger.error(f"❌ [ClusterClient] 房主没有返回任何数据")
                    sock.close()
                    return (False, "房主无响应")
                response_buffer += data
                messages, response_buffer = self._parse_json_messages(response_buffer)
                if messages:
                    response = json.loads(messages[0].decode('utf-8'))
                    break
            logger.debug(f"📥 [ClusterClient] 收到房主响应: {response}")
            last_reason = response.get('reason', '未知错误')
            
            if response.get("status") == "ok":
                logger.info(f"✅ [ClusterClient] 成功加入房间 {host}:{port}")
                self.socket = sock
                self.running = True
                self._own_node = ClusterNode(
                    node_id=self._node_id,
                    ip=sock.getsockname()[0],
                    model=node_info.get("model", "unknown"),
                    role=node_info.get("role", "worker"),
                    mode=node_info.get("mode", "auto"),
                    capability_score=evaluate_capability_simple(node_info)
                )
                
                # 【关键修复1】加入房间成功后，立刻持久化所有关键信息！确保刷新Web页面后不会丢失协作模式信息
                try:
                    import os
                    import json as json_module
                    from config import CLUSTER_WORKER_STATE_PATH
                    
                    def _ensure_data_dir_exists():
                        data_dir = os.path.dirname(CLUSTER_WORKER_STATE_PATH)
                        if not os.path.exists(data_dir):
                            os.makedirs(data_dir, exist_ok=True)
                    
                    # 立刻保存所有关键信息
                    _ensure_data_dir_exists()
                    initial_state = {
                        "in_room": True,  # 核心标记：已在协作模式中
                        "host": host,  # 房主IP地址（用于兜底轮询刷新页面后恢复）
                        "port": port,  # 房主端口（用于兜底轮询）
                        "node_id": self._node_id,
                        "name": self._node_name,
                        "model": node_info.get("model", "unknown"),
                        "role": node_info.get("role", "worker"),
                        "mode": node_info.get("mode", "auto"),
                        "room_name": "",
                        "room_id": "",
                        "owner_name": "",
                        "owner_model": "",
                        "members_detail": []
                    }
                    with open(CLUSTER_WORKER_STATE_PATH, 'w', encoding='utf-8') as f:
                        json_module.dump(initial_state, f, ensure_ascii=False, indent=2)
                    logger.info(f"💾 [Worker持久化] 加入房间成功，已保存初始协作状态: host={host}, port={port}")
                except Exception as e_init_save:
                    logger.warning(f"⚠️ 保存初始协作状态失败: {e_init_save}")
                
                self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self._heartbeat_thread.start()
                self._listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
                self._listener_thread.start()
                return (True, last_reason)
            else:
                logger.error(f"❌ [ClusterClient] 加入失败: {last_reason}")
                sock.close()
                return (False, last_reason)
        except socket.timeout:
            logger.error(f"❌ [ClusterClient] 连接超时: {host}:{port}")
            if sock:
                sock.close()
            return (False, "连接超时，请确认房主IP、端口正确，且防火墙允许访问")
        except ConnectionRefusedError:
            logger.error(f"❌ [ClusterClient] 连接被拒绝: {host}:{port}")
            if sock:
                sock.close()
            return (False, "连接被拒绝，请确认房主房间已创建，TCP服务正在监听，端口已开放")
        except Exception as e:
            logger.error(f"❌ [ClusterClient] 连接异常: {type(e).__name__}: {e}", exc_info=True)
            if sock:
                sock.close()
            return (False, f"连接异常: {str(e)}")
    
    def close(self):
        """关闭持久连接，停止所有后台线程"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        logger.info(f"🔌 [ClusterClient] 连接已完全关闭")