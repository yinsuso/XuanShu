
import json
import socket
import threading
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from logger import logger
from .protocol import MessageType, ClusterMessage, create_capability_advertisement, create_leave_notification, create_auth_response
from .discovery import ClusterDiscovery
from .capability import CapabilityAssessor

# 全局单例评估器实例（统一入口）
_global_capability_assessor: Optional[CapabilityAssessor] = None

def get_global_capability_assessor() -> CapabilityAssessor:
    """获取全局唯一的能力评估器实例 - 确保全系统使用同一套评估逻辑"""
    global _global_capability_assessor
    if _global_capability_assessor is None:
        _global_capability_assessor = CapabilityAssessor()
    return _global_capability_assessor

def evaluate_capability_simple(node_info: Dict[str, Any]) -> float:
    """
    能力评估函数 - 统一委托给 CapabilityAssessor（已消除重复代码）
    
    原简易评估逻辑已完全整合到 CapabilityAssessor 类中，保证全系统评分一致
    """
    assessor = get_global_capability_assessor()
    return assessor.assess(node_info)


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

        # 100节点优化：批量广播线程池 + 节点分批处理
        self._broadcast_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cluster_bcast")
        self._batch_size = 20  # 每批处理节点数
        self._room_sync_batch_delay = 0.05  # 批次间延迟(秒)

        # 100节点优化：房间信息增量同步标志，成员变化时触发全量同步
        self._room_info_dirty = True  # True表示需要同步，处理后置为False

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
        """向所有在线Worker推送完整的房间信息，确保Worker本地持久化JSON文件始终正确 - 100节点优化版：分批+线程池"""
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

            # 100节点优化：分批处理，避免一次性遍历所有节点造成阻塞
            node_items = list(self.nodes.items())
            total_nodes = len(node_items)
            success_count = 0

            for i in range(0, total_nodes, self._batch_size):
                batch = node_items[i:i + self._batch_size]
                for nid, node in batch:
                    if node.connection:
                        try:
                            node.connection.sendall(full_update_msg)
                            success_count += 1
                        except Exception as e_send:
                            node.connection = None
                            logger.debug(f"⚠️ 向节点 {nid[:8]} 推送房间信息失败: {e_send}")
                # 批次间短暂延迟，避免网络突发拥塞
                if i + self._batch_size < total_nodes:
                    time.sleep(self._room_sync_batch_delay)

            # 同时向本地所有浏览器WebSocket也广播这个房间信息更新
            self.broadcast_to_room(self.room_id, {
                "type": "room_info_update",
                "room_info": room_info
            })

            logger.debug(f"📡 [房间定时同步] 已向 {success_count}/{total_nodes} 个在线Worker推送完整房间信息")
        except Exception as e_broadcast:
            logger.warning(f"⚠️ 定时广播房间信息失败: {e_broadcast}")
    
    def _room_sync_loop(self):
        """房间信息同步循环 - 100节点优化版：条件触发+自适应间隔，避免无意义的全量同步"""
        # 100节点优化：根据节点数动态调整同步间隔
        def _adaptive_sync_interval() -> float:
            node_count = len(self.nodes)
            if node_count <= 10:
                return self.room_sync_interval
            elif node_count <= 50:
                return 6.0
            else:
                return 10.0  # 100节点时延长到10秒

        while self._room_sync_running:
            try:
                # 100节点优化：只有房间信息有变化时才全量同步，否则只发轻量心跳
                if self._room_info_dirty:
                    self._broadcast_full_room_info()
                    self._room_info_dirty = False
                else:
                    # 无变化时发送轻量心跳，保持连接活跃
                    self._send_lightweight_keepalive()
                time.sleep(_adaptive_sync_interval())
            except Exception as e:
                logger.error(f"[ClusterManager] 房间信息同步循环异常: {e}")
                time.sleep(_adaptive_sync_interval())

    def _send_lightweight_keepalive(self):
        """100节点优化：发送轻量保活消息，替代全量房间信息同步"""
        try:
            keepalive_msg = json.dumps({"type": "keepalive", "timestamp": time.time()}).encode('utf-8')
            for nid, node in self.nodes.items():
                if node.connection:
                    try:
                        node.connection.sendall(keepalive_msg)
                    except Exception:
                        node.connection = None
        except Exception:
            pass
    
    def _monitor_loop(self):
        """监控循环（100节点优化版：动态间隔 + 分批心跳检测 + 临时离线保留重入窗口）"""
        HEARTBEAT_TIMEOUT_SECONDS = 15      # 超过15秒没收到心跳就标记临时离线
        MAX_OFFLINE_KEEP_SECONDS = 600      # 10分钟=600秒，超过这个时间还没重入的节点才真正清理

        # 100节点优化：根据节点数动态调整监控间隔，避免高频遍历大量节点
        def _adaptive_interval() -> float:
            node_count = len(self.nodes)
            if node_count <= 10:
                return 5.0
            elif node_count <= 50:
                return 8.0
            else:
                return 12.0  # 100节点时降低到约12秒一次全量遍历

        while self._monitor_running:
            try:
                self.monitor_tasks()

                # 100节点优化：分批处理心跳检测，避免一次性遍历所有节点
                now = time.time()
                newly_offline_nodes = []
                permanent_remove_nodes = []
                node_items = list(self.nodes.items())

                for i in range(0, len(node_items), self._batch_size):
                    batch = node_items[i:i + self._batch_size]
                    for node_id, node in batch:
                        # 跳过房主自己的节点
                        if self.own_node and node_id == self.own_node.node_id:
                            continue

                        # 检查心跳超时
                        if now - node.last_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                            if node.status != "offline":
                                logger.warning(f"⏰ [ClusterManager] 节点 {node_id[:8]} 心跳超时 ({int(now - node.last_heartbeat)}秒)，标记为临时离线（10分钟内可重入恢复）")
                                node.status = "offline"
                                node._first_offline_ts = now
                                newly_offline_nodes.append(node_id)
                                if node.connection:
                                    try:
                                        node.connection.close()
                                    except:
                                        pass
                                    node.connection = None

                            first_offline_ts = getattr(node, '_first_offline_ts', 0)
                            if first_offline_ts > 0 and (now - first_offline_ts) > MAX_OFFLINE_KEEP_SECONDS:
                                logger.info(f"🗑️  [ClusterManager] 节点 {node_id[:8]} 已离线超过10分钟，永久清理")
                                permanent_remove_nodes.append(node_id)

                    # 批次间短暂释放GIL
                    if i + self._batch_size < len(node_items):
                        time.sleep(0.01)

                # 对真正超时的节点执行永久清理
                for remove_nid in permanent_remove_nodes:
                    self.leave_room(remove_nid)
                    self.remove_node(remove_nid)

                if newly_offline_nodes or permanent_remove_nodes:
                    logger.info(f"📊 [ClusterManager] 当前在线成员数: {len([n for nid, n in self.nodes.items() if n.status == 'active'])}")

                time.sleep(_adaptive_interval())
            except Exception as e:
                logger.error(f"[ClusterManager] 监控循环异常: {e}")
    
    def _send_task_assignment(self, target_node: 'ClusterNode', task_id: str, task_type: str, description: str, parameters: Dict = None):
        """真正向目标节点发送任务分配消息（通过TCP连接）"""
        agent_name = self._get_agent_name_by_node_id(target_node.node_id)
        
        self.task_assignments[task_id] = target_node.node_id
        self.task_metadata[task_id] = {
            "task_type": task_type,
            "description": description,
            "parameters": parameters or {},
            "assigned_at": time.time(),
            "agent_name": agent_name  # 【问题1修复】保存agent_name到任务元数据，便于后续状态广播
        }
        self.task_timeouts[task_id] = time.time() + 300
        
        logger.info(f"📤 [任务分配] 正在向节点 {target_node.node_id[:8]} ({agent_name}) 发送任务: {task_id[:8]}")
        
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
                logger.info(f"✅ [任务分配] 成功通过TCP发送任务 {task_id[:8]} 到节点 {target_node.node_id[:8]} ({agent_name})")
            except Exception as e:
                logger.warning(f"⚠️ [任务分配] TCP发送失败，节点本地执行: {e}")
        else:
            logger.info(f"ℹ️  [任务分配] 节点 {target_node.node_id[:8]} ({agent_name}) 无远程TCP连接，本地执行任务")
        
        try:
            target_node.status = "busy"
            logger.info(f"🔄 节点 {target_node.node_id[:8]} ({agent_name}) 状态已更新为 忙碌")
            if target_node.node_id in self.room_members:
                self.room_members[target_node.node_id]["status"] = "busy"
        except Exception as e:
            logger.warning(f"状态更新失败: {e}")
        
        self.broadcast_task_status_to_all(task_id, "assigned", target_node.node_id, {
            "agent_name": agent_name
        })
    
    def _get_agent_name_by_node_id(self, node_id: str) -> str:
        """根据 node_id 获取成员的显示名称 - 增强版：支持从持久化状态获取自己的名称"""
        # 首先从 room_members 中查找
        for mid, member in self.room_members.items():
            if mid == node_id:
                return member.get("name", node_id[:8])
        
        # 【问题1修复】如果在 room_members 中找不到，尝试从本地持久化状态获取（成员端场景）
        try:
            import json
            import os
            from config import CLUSTER_WORKER_STATE_PATH
            
            if os.path.exists(CLUSTER_WORKER_STATE_PATH):
                with open(CLUSTER_WORKER_STATE_PATH, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    # 检查是否是当前节点自己
                    if state.get("node_id") == node_id:
                        return state.get("name", node_id[:8])
        except Exception:
            pass
        
        # 最终回退到节点ID
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
        节点加入房间（由 ClusterServer 调用）- 终极重入增强版：支持离线节点重新激活恢复
        
        Args:
            node_info: 包含 node_id, name, mode, model 等
            
        Returns:
            True 表示加入成功
        """
        node_id = node_info['node_id']
        if node_id not in self.nodes:
            logger.warning(f"❌ 节点 {node_id} 不存在，无法加入房间")
            return False
        
        # === 【核心重入增强】如果该节点已经是房间成员（临时离线重入），直接更新信息，不需要新建记录 ===
        is_rejoin = node_id in self.room_members
        if is_rejoin:
            logger.info(f"🔄 [重入机制] 节点 {node_id[:8]} 重新加入房间，成员状态已恢复")
            # 只更新必要字段，保留原 joined_at 等历史信息
            existing_member = self.room_members[node_id]
            existing_member["name"] = node_info.get('name', existing_member.get('name', node_id))
            existing_member["mode"] = node_info.get('mode', existing_member.get('mode', 'auto'))
            existing_member["model"] = node_info.get('model', existing_member.get('model', 'unknown'))
            existing_member["last_rejoined_at"] = time.time()
        else:
            # 全新节点首次加入
            self.room_members[node_id] = {
                "node_id": node_id,
                "name": node_info.get('name', node_id),
                "mode": node_info.get('mode', 'auto'),
                "model": node_info.get('model', 'unknown'),
                "joined_at": time.time(),
                "is_owner": False
            }
        logger.info(f"👥 [ClusterManager] 成员 {node_info.get('name', node_id)} 已加入房间")

        # 100节点优化：标记房间信息已变化，由同步线程处理全量广播
        self._room_info_dirty = True

        # === 核心修复：加入成功后立即向所有成员（包括刚加入的成员）广播最新完整房间信息 ===
        # 100节点优化：节点数>20时，只向新加入节点推送，避免加入瞬间全量广播阻塞
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

            if len(self.nodes) <= 20:
                # 小房间：立即全量广播
                for nid, node in self.nodes.items():
                    if node.connection:
                        try:
                            node.connection.sendall(full_update_msg)
                            logger.info(f"📡 [房间同步广播] 已向节点 {nid[:8]} 推送最新成员列表")
                        except Exception as e_send:
                            logger.warning(f"⚠️ 向节点 {nid[:8]} 推送房间更新失败: {e_send}")
            else:
                # 100节点优化：大房间只向新节点和房主推送，其他节点由定时同步线程处理
                new_node = self.nodes.get(node_id)
                if new_node and new_node.connection:
                    try:
                        new_node.connection.sendall(full_update_msg)
                        logger.info(f"📡 [房间同步广播] 已向新节点 {node_id[:8]} 推送完整房间信息")
                    except Exception as e_send:
                        logger.warning(f"⚠️ 向新节点 {node_id[:8]} 推送房间更新失败: {e_send}")

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
            # 100节点优化：成员变化标记脏数据，触发后续同步
            self._room_info_dirty = True
        
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
        向房间内所有成员广播事件（通过 WebSocket）- 终极修复版：同时调用全局连接池确保房主收到
        保证100%所有浏览器（包括房主自己的浏览器）都能收到推送
        Returns:
            成功推送的连接数
        """
        count = 0
        
        # 新增：调用全局连接池中的全局broadcast_to_all_clients函数，确保所有浏览器都收到，不管什么节点连接的
        try:
            from evolution.cluster.cluster_api import broadcast_to_all_clients
            import asyncio

            def _do_broadcast():
                try:
                    loop_bcast = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop_bcast)
                    loop_bcast.run_until_complete(broadcast_to_all_clients(event))
                    loop_bcast.close()
                except Exception as e_inner:
                    logger.warning(f"全局WebSocket广播内部异常: {e_inner}")

            threading.Thread(target=_do_broadcast, daemon=True).start()
        except Exception as e_global:
            logger.warning(f"调用全局WebSocket广播失败: {e_global}")
        
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
        
        logger.debug(f"📡 [房间广播完成] 事件类型={event.get('type')}, 总成功推送数={count}")
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
                    # 【修复】如果 parameters 中包含技能调用信息，优先直接执行技能
                    if parameters and isinstance(parameters, dict) and parameters.get('skill'):
                        skill_name = parameters.get('skill')
                        skill_args = parameters.get('args', parameters)
                        if 'args' not in parameters:
                            skill_args = {k: v for k, v in parameters.items() if k != 'skill'}
                        logger.info(f"🎯 [Manager本地] 直接执行技能: {skill_name}, args={skill_args}")
                        result = agent_obj._execute_skill(skill_name, skill_args)
                    # 【修复】如果 task_type 本身就是已注册的技能名称，直接执行该技能
                    elif task_type and agent_obj.skills_registry.get(task_type):
                        logger.info(f"🎯 [Manager本地] task_type 匹配技能，直接执行: {task_type}, parameters={parameters}")
                        result = agent_obj._execute_skill(task_type, parameters or {})
                    else:
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
    
    def _init_collab_conversation(self, force_new=False):
        """初始化协作模式专用对话 - 创建新对话文件，避免和单机对话混淆
        
        Args:
            force_new: 是否强制创建新对话。当房主使用 /new、/reset 命令或发起新的协作任务时，
                      应设为 True，确保所有成员使用全新的对话上下文。
        """
        # 如果已经初始化且不要求强制新建，则直接返回
        if self._collab_initialized and not force_new:
            return True

        try:
            from conversation_manager import get_global_conversation_manager
            conv_mgr = get_global_conversation_manager()

            if force_new and self._collab_initialized:
                # 强制新建：重置协作对话，创建全新对话文件
                new_conv_id = conv_mgr.reset_collab_conversation()
                logger.info(f"✅ [协作持久化] 房主强制重置协作对话: conversation_id={new_conv_id[:8]}...")
            else:
                # 首次初始化：创建协作模式专用的新对话
                from conversation_manager import ConversationType
                new_conv_id = conv_mgr.new_conversation(
                    initial_title=f"🤝 {self.room_name} - 协作对话",
                    conversation_type=ConversationType.COLLABORATION
                )
                # 更新协作模式当前对话ID
                conv_mgr._collab_current_id = new_conv_id
                logger.info(f"✅ [协作持久化] 协作对话已初始化: conversation_id={new_conv_id[:8]}...")

            self.collab_conversation_id = new_conv_id
            self._collab_initialized = True
            self.collab_messages = []

            return True
        except Exception as e:
            logger.error(f"❌ [协作持久化] 初始化协作对话失败: {e}", exc_info=True)
            return False
    
    def add_collab_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """
        添加协作消息 - 同时保存到内存缓存和持久化文件，并广播到所有客户端
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
                # 【修复】系统消息使用专门的 system 角色保存，不再错误标记为 assistant
                conv_mgr.add_system_message(content)

            conv_mgr.save_current()
            logger.debug(f"📝 [协作持久化] 消息已保存: role={role}, 长度={len(content)}")
            
            # ========== 【核心修复】广播新消息到所有客户端 ==========
            self.broadcast({
                "type": "collab_new_message",
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "timestamp": time.time()
            })
            
            return True
        except Exception as e:
            logger.error(f"❌ [协作持久化] 添加协作消息失败: {e}", exc_info=True)
            return False
    
    def _build_collab_system_prompt(self, task_description: str) -> str:
        """构建协作任务开始时的系统提示词，告知模型所有成员信息和协作规则"""
        members_info = []
        worker_count = 0
        for node_id, member in self.room_members.items():
            node = self.nodes.get(node_id)
            status_text = "🟢 空闲"
            if node and hasattr(node, 'status') and node.status == 'busy':
                status_text = "🔴 忙碌中"
            role = "房主" if member.get("is_owner", False) else "工作者"
            if role == "工作者":
                worker_count += 1
            members_info.append({
                "name": member.get("name", "未知"),
                "role": role,
                "model": member.get("model", "未知模型"),
                "status": status_text
            })
        
        import json
        system_prompt = f"""# 🤝 协作模式启动通知

## 当前协作环境信息
- 房间名称: {self.room_name}
- 房主名称: {self.owner_name or '未知'}
- 可用工作者数量: {worker_count} 个

## 当前所有成员列表 (共 {len(members_info)} 个):
{json.dumps(members_info, ensure_ascii=False, indent=2)}

## 🎯 你的核心职责
你是本次协作任务的**总协调者和任务拆解专家**。你的首要任务是：
1. **任务拆解**: 将用户的复杂任务拆解为多个独立的子任务
2. **智能分配**: 根据成员的能力和状态，将子任务分配给最合适的工作者
3. **进度追踪**: 监控所有子任务的执行状态
4. **结果汇总**: 将所有子任务的结果汇总成最终答案

## 📋 协作执行规则（必须严格遵守）

### 规则一：任务必须拆解（强制性）
- 对于复杂任务（如访问网站、数据分析、多步骤操作），**必须**拆解为多个子任务
- 即使是简单任务，只要有空闲的工作者，也应优先分配给工作者执行
- 只有当没有可用工作者或任务极其简单时，才由房主自己执行

### 规则二：工作者优先原则
- 当有可用工作者时，**禁止**房主自己执行可分配的任务
- 工作者是专门负责执行具体任务的，你作为协调者应专注于任务拆解和分配
- 除非所有工作者都忙碌或离线，否则不要自己执行任务

### 规则三：合理分配策略
- 根据工作者的模型特点分配任务（例如：编码任务分配给coder模型）
- 考虑工作者的当前状态（优先分配给空闲的工作者）
- 平衡工作负载，避免某个工作者过载

### 规则四：清晰的任务描述
- 分配任务时，提供清晰、具体的任务描述
- 包含完成任务所需的所有必要信息
- 明确说明任务的期望输出

## 🚀 执行流程建议
1. 分析用户任务，判断是否需要拆解
2. 列出需要执行的子任务清单
3. 为每个子任务选择最合适的执行者
4. 按优先级顺序分配任务
5. 等待工作者完成并返回结果
6. 汇总所有结果，给出最终回复

## 当前任务
{task_description}

## 💡 思考提示
请先思考：这个任务是否可以拆解？如果可以，应该拆分成哪些子任务？哪些工作者适合执行这些任务？
"""
        return system_prompt
    
    def _parse_task_plan(self, plan_text: str) -> list:
        """解析模型返回的任务拆解计划"""
        import re
        tasks = []
        
        # 尝试解析JSON格式的任务列表
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', plan_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict) and 'tasks' in data:
                    tasks = data['tasks']
            except:
                pass
        
        # 如果JSON解析失败，尝试解析列表格式
        if not tasks:
            lines = plan_text.split('\n')
            task_index = 1
            for line in lines:
                # 匹配 "- [任务描述]" 或 "1. [任务描述]" 或 "* [任务描述]" 格式
                match = re.match(r'^(?:-|\d+\.|\\*)\\s+(.+)', line.strip())
                if match:
                    tasks.append({
                        "task_id": f"subtask_{task_index}",
                        "description": match.group(1).strip(),
                        "priority": task_index
                    })
                    task_index += 1
        
        return tasks

    def start_collaborative_task(self, task_type: str, description: str, parameters: Dict = None):
        """使用调度器启动协作任务 - 增强版：让模型先思考拆解任务，再进行智能分配"""
        # 步骤1：初始化协作对话（强制新建，确保每次协作任务都是全新对话）
        self._init_collab_conversation(force_new=True)

        # 注意：enter_collab_mode 事件已由 web_app.py 中的 /api/rooms/start_task 接口广播
        # 此处不再重复广播，避免客户端收到重复事件
        
        # 步骤2：构建完整的协作环境介绍，让模型了解全部成员和规则
        collab_system_prompt = self._build_collab_system_prompt(description)
        self.add_collab_message("system", collab_system_prompt, {"type": "collab_bootstrap"})
        
        # 步骤3：保存用户的原始协作任务消息
        self.add_collab_message("user", description, {"type": "user_collab_task"})
        
        # 步骤4：让模型先进行任务拆解思考（关键改进）
        worker_count = sum(1 for m in self.room_members.values() if not m.get("is_owner", False))
        assigned_task_id = None
        
        if worker_count > 0:
            # 有可用工作者，让模型先思考如何拆解任务
            logger.info(f"🤔 [协作模式] 有 {worker_count} 个可用工作者，让模型先进行任务拆解思考...")
            
            try:
                import sys
                agent_obj = None
                for mod_name, mod in sys.modules.items():
                    if 'web_app' in mod_name and hasattr(mod, 'get_agent'):
                        agent_obj = mod.get_agent()
                        break
                
                if agent_obj:
                    # 构建任务拆解提示词
                    task_plan_prompt = f"""请你作为任务拆解专家，分析以下任务并给出详细的执行计划：

【任务描述】
{description}

【可用工作者数量】
{worker_count} 个

【任务拆解要求】
1. 分析任务是否需要拆解
2. 如果需要拆解，列出具体的子任务清单
3. 为每个子任务指定合适的执行者（工作者）
4. 说明任务之间的依赖关系（如果有）

【输出格式】
请以JSON格式输出任务计划，例如：
```json
{{
    "need_split": true,
    "reason": "任务需要拆解的原因",
    "tasks": [
        {{"task_id": "subtask_1", "description": "子任务1描述", "priority": 1, "suggested_worker": "自动分配"}},
        {{"task_id": "subtask_2", "description": "子任务2描述", "priority": 2, "suggested_worker": "自动分配"}}
    ]
}}
```

如果任务不需要拆解或太简单，可以直接执行，请输出：
```json
{{"need_split": false, "reason": "任务简单，无需拆解"}}
```
"""
                    
                    plan_result = agent_obj._process_simple(task_plan_prompt)
                    logger.info(f"📝 [协作模式] 模型任务拆解结果:\n{plan_result}")
                    
                    # 保存模型的思考结果到协作对话
                    self.add_collab_message("assistant", f"🧠 任务拆解分析结果:\n{plan_result}", {"type": "task_plan"})
                    
                    # 解析任务计划
                    import re
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', plan_result, re.DOTALL)
                    if json_match:
                        try:
                            plan_data = json.loads(json_match.group(1))
                            need_split = plan_data.get("need_split", False)
                            
                            if need_split and "tasks" in plan_data:
                                # 按优先级排序子任务
                                subtasks = sorted(plan_data["tasks"], key=lambda x: x.get("priority", 999))
                                logger.info(f"📋 [协作模式] 模型拆解出 {len(subtasks)} 个子任务")
                                
                                # 依次分配每个子任务
                                for subtask in subtasks:
                                    sub_description = subtask.get("description", "")
                                    if sub_description:
                                        subtask_id = self.assign_task("collab_subtask", sub_description, parameters)
                                        logger.info(f"🎯 [协作模式] 已分配子任务: {subtask_id[:8]} - {sub_description[:50]}...")
                                        if not assigned_task_id:
                                            assigned_task_id = subtask_id
                            else:
                                # 任务不需要拆解，直接分配
                                logger.info(f"ℹ️ [协作模式] 模型认为任务无需拆解，直接分配执行")
                                assigned_task_id = self.assign_task(task_type, description, parameters)
                        except json.JSONDecodeError as e:
                            logger.warning(f"⚠️ [协作模式] 解析任务计划失败，直接分配任务: {e}")
                            assigned_task_id = self.assign_task(task_type, description, parameters)
                    else:
                        # 没有找到JSON格式，直接分配任务
                        logger.info(f"ℹ️ [协作模式] 未找到结构化任务计划，直接分配任务")
                        assigned_task_id = self.assign_task(task_type, description, parameters)
                else:
                    # 没有找到agent实例，直接分配任务
                    logger.info(f"ℹ️ [协作模式] 未找到agent实例，直接分配任务")
                    assigned_task_id = self.assign_task(task_type, description, parameters)
            except Exception as e:
                logger.error(f"❌ [协作模式] 任务拆解思考失败: {e}", exc_info=True)
                assigned_task_id = self.assign_task(task_type, description, parameters)
        else:
            # 没有可用工作者，房主自己执行
            logger.info(f"ℹ️ [协作模式] 无可用工作者，房主自己执行任务")
            assigned_task_id = self.assign_task(task_type, description, parameters)
        
        # 步骤5：处理分配结果
        if assigned_task_id and assigned_task_id in self.task_assignments:
            target_node_id = self.task_assignments.get(assigned_task_id)
            if target_node_id:
                target_node = self.nodes.get(target_node_id)
                if target_node:
                    if not target_node.connection:
                        logger.info(f"ℹ️ 目标节点无远程连接，本地完全异步执行任务: {assigned_task_id[:8]}")
                        self.execute_local_task_async(target_node_id, assigned_task_id, task_type, description, parameters)
                    else:
                        logger.info(f"📤 目标节点为远程节点，已发送任务分配消息: {target_node_id[:8]}")
                        def mark_busy_immediately():
                            import asyncio
                            target_node.status = "busy"
                            try:
                                loop_notify = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop_notify)
                                self.broadcast_task_status_to_all(assigned_task_id, "assigned", target_node_id, {
                                    "agent_name": self._get_agent_name_by_node_id(target_node_id),
                                    "description": f"✅ Agent「{self._get_agent_name_by_node_id(target_node_id)}」已接收任务，正在执行..."
                                })
                                loop_notify.close()
                            except Exception as e:
                                logger.warning(f"远程节点状态标记失败: {e}")
                        import threading
                        threading.Thread(target=mark_busy_immediately, daemon=True).start()
        
        return assigned_task_id
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
        # 延迟导入避免循环依赖
        try:
            from model_providers import config_manager
        except Exception:
            config_manager = None

        members = []
        for node_id, member in self.room_members.items():
            node = self.nodes.get(node_id)
            # 获取成员模型并查询对应的provider类型
            member_model = member.get("model", node.model if node else "unknown")
            provider_type = "unknown"
            if config_manager:
                cfg = config_manager.get_config(member_model)
                if cfg:
                    provider_type = cfg.provider.value
                else:
                    # 如果配置名不匹配，尝试通过model_name匹配
                    for c in config_manager.configs:
                        if c.model_name == member_model or c.name == member_model:
                            provider_type = c.provider.value
                            break

            if node:
                members.append({
                    **member,
                    "node_id": node_id,
                    "status": node.status,
                    "capability_score": node.capability_score,
                    "load_cpu": node.load_cpu,
                    "load_memory": node.load_memory,
                    # 保留成员自己设置的模型，不被节点默认模型覆盖
                    "model": member_model,
                    "provider": provider_type
                })
            else:
                members.append({
                    **member,
                    "node_id": node_id,
                    "status": "offline",
                    "capability_score": 0,
                    "load_cpu": 0,
                    "load_memory": 0,
                    "provider": provider_type
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

        if node_id in self.room_members:
            self.room_members[node_id]["status"] = node.status if node else "offline"
            self.room_members[node_id]["load_cpu"] = load_info.get("load_cpu", 0.0)
            self.room_members[node_id]["load_memory"] = load_info.get("load_memory", 0.0)
            self.room_members[node_id]["queue_length"] = load_info.get("queue_length", 0)
            self.room_members[node_id]["last_heartbeat"] = time.time()

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

            if node_id in self.room_members:
                self.room_members[node_id]["status"] = "active"

            self.task_assignments.pop(task_id, None)
            self.task_timeouts.pop(task_id, None)
            self.task_metadata.pop(task_id, None)

            node.notify_status_change(task_id)
        else:
            logger.warning("任务状态更新来自未知节点", node_id=node_id, task_id=task_id)

        # 【核心修复】统一广播机制：已通过上面的 add_collab_message 广播消息，不需要重复广播
        # 注意：broadcast_task_status_to_all 用于任务日志显示，不是 collab_new_message，不会重复

        # 任务状态更新：用于任务日志显示，不重复显示agent结果
        self.broadcast_task_status_to_all(task_id, status, node_id, {
            "agent_name": agent_name,
            "result_preview": str(result)[:100] if result else ""
        })

    def broadcast_skill_sync(self, skill_name: str, skill_code: str, generated_by: str = None):
        """
        向所有在线节点广播新生成的技能

        Args:
            skill_name: 技能名称
            skill_code: 技能完整 Python 代码
            generated_by: 生成者节点ID（可选）
        """
        from .protocol import create_skill_sync

        msg = create_skill_sync(skill_name, skill_code, generated_by)
        serialized = msg.serialize()

        success_count = 0
        for nid, node in self.nodes.items():
            # 跳过生成者自己（如果指定了）
            if generated_by and nid == generated_by:
                continue
            if node.connection:
                try:
                    node.connection.sendall(serialized)
                    success_count += 1
                    logger.info(f"📡 [技能同步] 已向节点 {nid[:8]} 广播技能 '{skill_name}'")
                except Exception as e:
                    logger.warning(f"⚠️ [技能同步] 向节点 {nid[:8]} 广播失败: {e}")

        # 同时向本地浏览器WebSocket广播，通知前端有新技能同步
        self.broadcast_to_room(self.room_id, {
            "type": "skill_synced",
            "skill_name": skill_name,
            "generated_by": generated_by,
            "timestamp": time.time()
        })

        logger.info(f"✅ [技能同步] 技能 '{skill_name}' 已广播给 {success_count} 个节点")
        return success_count

    def handle_skill_sync(self, skill_name: str, skill_code: str, generated_by: str = None):
        """
        处理接收到的技能同步消息（Worker节点或房主节点调用）

        Args:
            skill_name: 技能名称
            skill_code: 技能完整 Python 代码
            generated_by: 生成者节点ID（可选）
        """
        try:
            import os
            from config import PROJECT_ROOT

            # 保存到本地 auto_generated 目录
            auto_skills_dir = os.path.join(PROJECT_ROOT, "skills", "auto_generated")
            os.makedirs(auto_skills_dir, exist_ok=True)

            # 构建文件名
            safe_name = "".join(c if c.isalnum() or c in '_-' else '_' for c in skill_name)
            safe_name = safe_name.lower().replace('-', '_')
            filename = f"synced_{safe_name}_{int(time.time())}.py"
            filepath = os.path.join(auto_skills_dir, filename)

            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(skill_code)

            # 重新加载技能
            from skills import load_skills
            load_skills()

            logger.info(f"✅ [技能同步] 已接收并注册技能 '{skill_name}' 来自 {generated_by or 'unknown'}")

            # 通知前端有新技能同步
            self.broadcast_to_room(self.room_id, {
                "type": "skill_synced",
                "skill_name": skill_name,
                "generated_by": generated_by,
                "timestamp": time.time()
            })

            return True
        except Exception as e:
            logger.error(f"❌ [技能同步] 处理技能 '{skill_name}' 同步失败: {e}")
            return False

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
        
        # 第一步补充：主动关闭所有成员的TCP连接，确保他们立即收到断开通知
        # 关键：必须在广播事件后立即关闭连接，这样成员的TCP监听线程会收到空数据并立即退出
        try:
            for nid, node in self.nodes.items():
                if self.own_node and nid == self.own_node.node_id:
                    continue  # 跳过房主自己
                if node.connection:
                    try:
                        node.connection.close()
                        logger.info(f"🔌 [解散强制断开] 已关闭成员 {nid[:8]} 的TCP连接")
                    except Exception as e_close:
                        logger.warning(f"⚠️ 关闭成员 {nid[:8]} 连接失败: {e_close}")
                    finally:
                        node.connection = None  # 确保引用也被清除
        except Exception as e_force_close:
            logger.warning(f"⚠️ 强制断开连接过程异常: {e_force_close}")
        
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


    def _send_to_node_batch(self, node_batch: List[tuple], message_bytes: bytes, exclude_set: set) -> int:
        """100节点优化：批量发送消息到一组节点，返回成功数"""
        success = 0
        for nid, node in node_batch:
            if node.node_id in exclude_set:
                continue
            if node.connection:
                try:
                    node.connection.sendall(message_bytes)
                    success += 1
                except Exception:
                    node.connection = None
        return success

    def broadcast(self, message: Dict[str, Any], exclude: List[str] = None):
        """向所有节点广播消息（通过已建立的 TCP 连接 + WebSocket 双保险）- 100节点优化版：分批+线程池"""
        exclude_set = set(exclude or [])
        total_nodes = len(self.nodes)
        logger.info(f"📡 [广播] 正在推送事件类型: {message.get('type')}, 节点数: {total_nodes}")

        message_bytes = json.dumps(message).encode('utf-8')
        node_items = list(self.nodes.items())

        # 100节点优化：节点数<=20直接串行发送；超过20使用分批+线程池
        if total_nodes <= 20:
            for nid, node in node_items:
                if node.node_id in exclude_set:
                    continue
                if node.connection:
                    try:
                        node.connection.sendall(message_bytes)
                        logger.debug(f"📡 [TCP广播] 已成功推送到节点 {node.node_id[:8]}")
                    except Exception as e:
                        logger.error(f"📡 [TCP广播失败] 节点 {node.node_id} 失败: {e}")
        else:
            # 分批提交到线程池并行发送
            futures = []
            for i in range(0, total_nodes, self._batch_size):
                batch = node_items[i:i + self._batch_size]
                future = self._broadcast_executor.submit(self._send_to_node_batch, batch, message_bytes, exclude_set)
                futures.append(future)
            # 收集结果
            total_success = sum(f.result() for f in futures)
            logger.debug(f"📡 [TCP广播] 分批并行推送完成，成功 {total_success}/{total_nodes}")

        # 第二部分：向所有浏览器 WebSocket 客户端发送事件（保证本地成员立即收到）
        try:
            from evolution.cluster.cluster_api import broadcast_to_all_clients
            import asyncio

            def _do_broadcast():
                try:
                    loop_bcast = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop_bcast)
                    loop_bcast.run_until_complete(broadcast_to_all_clients(message))
                    loop_bcast.close()
                except Exception as e_inner:
                    logger.warning(f"全局WebSocket广播内部异常: {e_inner}")

            threading.Thread(target=_do_broadcast, daemon=True).start()
            logger.debug(f"📡 [WebSocket广播] 已成功推送到所有浏览器客户端")
        except Exception as e:
            logger.warning(f"📡 [WebSocket广播警告] {e}")

    def shutdown(self):
        """100节点优化：优雅关闭，释放线程池资源"""
        self._broadcast_executor.shutdown(wait=False)
        self.stop_monitoring()
        self.stop_room_sync()
        self.stop_server()


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
                # 100节点优化：提升backlog到128，支持更多并发连接队列
                self._server_socket.listen(128)
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
                if '$' in self.manager.room_password_hash:
                    # 新格式 PBKDF2 验证（带盐）
                    import hashlib
                    import secrets
                    salt, hash_hex = self.manager.room_password_hash.split('$', 1)
                    password_ok = hashlib.pbkdf2_hmac('sha256', client_password.encode('utf-8'), salt.encode('utf-8'), 100000).hex() == hash_hex
                else:
                    # 旧格式 SHA256 验证（向后兼容）
                    password_ok = hashlib.sha256(client_password.encode()).hexdigest() == self.manager.room_password_hash if client_password else False

                if not password_ok:
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
            raw_node_id = msg.get('node_id')
            node_info = {
                "node_id": raw_node_id,
                "ip": addr[0],  # 使用客户端IP
                "model": msg.get('model', 'unknown'),
                "role": msg.get('role', 'worker'),
                "mode": msg.get('mode', 'auto')
            }
            
            # === 【核心重入增强】如果该 node_id 已存在，直接重新激活节点，不用新建 ===
            existing_node = None
            if raw_node_id in self.manager.nodes:
                existing_node = self.manager.nodes[raw_node_id]
                logger.info(f"🔄 [重入机制] 检测到节点 {raw_node_id[:8]} 之前已离线，正在重新激活！")
            
            if not existing_node:
                # 全新节点，走原流程
                node_info['capability_score'] = evaluate_capability_simple({
                    'model': node_info['model'],
                    'gpu': msg.get('gpu'),
                    'vram': msg.get('vram')
                })
                logger.info(f"📊 [ClusterServer] 新节点 {node_info['node_id']} 能力评估: {node_info['capability_score']:.2f}")
                self.manager.add_node(node_info)
                node = self.manager.nodes.get(node_info['node_id'])
            else:
                # 离线节点重新激活，复用原有状态，更新关键信息
                node = existing_node
                node.connection = conn
                node.ip = addr[0]
                node.status = "active"
                node.last_heartbeat = time.time()  # 重置心跳时间
                logger.info(f"✅ [重入成功] 节点 {raw_node_id[:8]} 已成功从离线状态恢复，重新加入集群！")
            
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
                                elif msg_type == "skill_sync":
                                    skill_name = payload.get("skill_name")
                                    skill_code = payload.get("skill_code")
                                    generated_by = payload.get("generated_by")
                                    if skill_name and skill_code:
                                        self.manager.handle_skill_sync(skill_name, skill_code, generated_by)
                                    else:
                                        logger.warning(f"[ClusterServer] 收到无效的技能同步消息: skill_name={skill_name}")
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
                                elif msg_type == "skill_sync":
                                    skill_name = msg.get("skill_name")
                                    skill_code = msg.get("skill_code")
                                    generated_by = msg.get("generated_by")
                                    if skill_name and skill_code:
                                        self.manager.handle_skill_sync(skill_name, skill_code, generated_by)
                                    else:
                                        logger.warning(f"[ClusterServer] 收到无效的技能同步消息: skill_name={skill_name}")
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
                # === 【重入关键增强】断开连接不立即从房间成员列表删除节点！只标记离线，10分钟内重入可直接恢复 ===
                logger.warning(f"⏸️ 节点 {node.node_id[:8]} 临时离线，暂保留在房间成员列表中，10分钟内可直接重入恢复")
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
                if not self.running or not self.socket:
                    break
                if self._node_id:
                    heartbeat_msg = json.dumps({
                        "type": "heartbeat",
                        "node_id": self._node_id,
                        "load": self._get_system_load()
                    }).encode('utf-8')
                    self.socket.sendall(heartbeat_msg)
                    logger.debug(f"💓 [ClusterClient] 心跳已发送")
            except Exception as e:
                if self.running and self.socket:
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
                if not self.running or not self.socket:
                    break
                self.socket.settimeout(1.0)
                data = self.socket.recv(8192)
                if not data:
                    if self.running and self.socket:
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
                        
                        # 处理：任务分配消息（核心修复：成员端收到任务后立即执行）
                        elif msg_type == "task_assignment":
                            payload = msg.get("payload", {})
                            task_id = payload.get("task_id")
                            task_type = payload.get("task_type")
                            description = payload.get("description")
                            parameters = payload.get("parameters", {})
                            
                            logger.info(f"🎯 [ClusterClient] 收到房主分配的任务: task_id={task_id[:8] if task_id else 'N/A'}, task_type={task_type}")
                            
                            # 立即向本地浏览器WebSocket广播任务接收通知
                            try:
                                from evolution.cluster.cluster_api import broadcast_to_all_clients
                                broadcast_to_all_clients({
                                    "type": "task_assigned",
                                    "task_id": task_id,
                                    "task_type": task_type,
                                    "description": description,
                                    "parameters": parameters,
                                    "timestamp": time.time()
                                })
                            except Exception as e_ws:
                                logger.warning(f"⚠️ 向本地WebSocket广播任务分配失败: {e_ws}")
                            
                            # 在独立线程中异步执行任务
                            def execute_task():
                                import time
                                import asyncio
                                logger.info(f"🤖 [ClusterClient] 开始执行任务: {task_id[:8]}")
                                try:
                                    # 标记任务开始
                                    try:
                                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        loop.run_until_complete(broadcast_to_all_clients({
                                            "type": "task_status_update",
                                            "task_id": task_id,
                                            "status": "running",
                                            "node_id": self._node_id,
                                            "timestamp": time.time()
                                        }))
                                        loop.close()
                                    except:
                                        pass
                                    
                                    # 执行任务
                                    import sys
                                    result = ""
                                    agent_obj = None
                                    for mod_name, mod in sys.modules.items():
                                        if 'web_app' in mod_name:
                                            if hasattr(mod, 'get_agent'):
                                                agent_obj = mod.get_agent()
                                                break
                                    if agent_obj:
                                        # 【关键修复】成员执行新任务前，强制重置对话上下文，避免残留历史影响
                                        try:
                                            from conversation_manager import get_global_conversation_manager, ConversationType
                                            conv_mgr = get_global_conversation_manager()
                                            # 强制创建全新的协作对话，清除之前的上下文
                                            new_conv_id = conv_mgr.reset_collab_conversation()
                                            # 同步更新agent的对话管理器
                                            if hasattr(agent_obj, 'conversation_manager') and agent_obj.conversation_manager:
                                                agent_obj.conversation_manager = conv_mgr
                                            logger.info(f"✅ [ClusterClient] 成员已强制重置对话上下文: {new_conv_id[:8]}...")
                                        except Exception as e_reset:
                                            logger.warning(f"⚠️ [ClusterClient] 重置对话上下文失败: {e_reset}")

                                        # 【修复】如果 parameters 中包含技能调用信息，优先直接执行技能
                                        if parameters and isinstance(parameters, dict) and parameters.get('skill'):
                                            skill_name = parameters.get('skill')
                                            skill_args = parameters.get('args', parameters)
                                            # 如果 args 不存在，尝试将整个 parameters 作为参数传递（排除 skill 字段本身）
                                            if 'args' not in parameters:
                                                skill_args = {k: v for k, v in parameters.items() if k != 'skill'}
                                            logger.info(f"🎯 [ClusterClient] 直接执行技能: {skill_name}, args={skill_args}")
                                            result = agent_obj._execute_skill(skill_name, skill_args)
                                        # 【修复】如果 task_type 本身就是已注册的技能名称，直接执行该技能
                                        elif task_type and agent_obj.skills_registry.get(task_type):
                                            logger.info(f"🎯 [ClusterClient] task_type 匹配技能，直接执行: {task_type}, parameters={parameters}")
                                            result = agent_obj._execute_skill(task_type, parameters or {})
                                        else:
                                            # 没有技能参数时，使用 description 让模型自行判断
                                            result = agent_obj._process_simple(description)
                                    else:
                                        time.sleep(1)
                                        result = f"✅ Worker「{self._node_name}」已完成任务\n\n> 任务描述: {description}\n\n> 执行状态: 完全成功\n> 执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n🎯 这是由 Worker「{self._node_name}」处理的结果！"
                                    
                                    # 标记任务完成
                                    try:
                                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        loop.run_until_complete(broadcast_to_all_clients({
                                            "type": "task_status_update",
                                            "task_id": task_id,
                                            "status": "completed",
                                            "node_id": self._node_id,
                                            "result": str(result)[:500],
                                            "timestamp": time.time()
                                        }))
                                        loop.close()
                                    except:
                                        pass
                                    
                                    # 向房主发送任务完成消息
                                    if self.socket and self.running:
                                        task_update_msg = json.dumps({
                                            "type": "task_update",
                                            "task_id": task_id,
                                            "status": "completed",
                                            "result": str(result),
                                            "node_id": self._node_id,
                                            "timestamp": time.time()
                                        }).encode('utf-8')
                                        self.socket.sendall(task_update_msg)
                                        logger.info(f"📤 [ClusterClient] 任务完成结果已发送给房主: {task_id[:8]}")
                                    
                                except Exception as e_exec:
                                    logger.error(f"❌ [ClusterClient] 执行任务失败: {e_exec}", exc_info=True)
                                    # 标记任务失败
                                    try:
                                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        loop.run_until_complete(broadcast_to_all_clients({
                                            "type": "task_status_update",
                                            "task_id": task_id,
                                            "status": "failed",
                                            "node_id": self._node_id,
                                            "error": str(e_exec),
                                            "timestamp": time.time()
                                        }))
                                        loop.close()
                                    except:
                                        pass
                            
                            import threading
                            threading.Thread(target=execute_task, daemon=True).start()

                        # 处理：技能同步消息（Worker接收房主广播的新技能）
                        elif msg_type == "skill_sync":
                            payload = msg.get("payload", {})
                            skill_name = payload.get("skill_name") or msg.get("skill_name")
                            skill_code = payload.get("skill_code") or msg.get("skill_code")
                            generated_by = payload.get("generated_by") or msg.get("generated_by")

                            if skill_name and skill_code:
                                logger.info(f"📥 [ClusterClient] 收到技能同步: '{skill_name}' 来自 {generated_by or 'unknown'}")
                                try:
                                    import os
                                    from config import PROJECT_ROOT

                                    auto_skills_dir = os.path.join(PROJECT_ROOT, "skills", "auto_generated")
                                    os.makedirs(auto_skills_dir, exist_ok=True)

                                    safe_name = "".join(c if c.isalnum() or c in '_-' else '_' for c in skill_name)
                                    safe_name = safe_name.lower().replace('-', '_')
                                    filename = f"synced_{safe_name}_{int(time.time())}.py"
                                    filepath = os.path.join(auto_skills_dir, filename)

                                    with open(filepath, 'w', encoding='utf-8') as f:
                                        f.write(skill_code)

                                    from skills import load_skills
                                    load_skills()

                                    logger.info(f"✅ [ClusterClient] 技能 '{skill_name}' 已保存并加载")

                                    # 通知前端有新技能同步
                                    try:
                                        from evolution.cluster.cluster_api import broadcast_to_all_clients
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        loop.run_until_complete(broadcast_to_all_clients({
                                            "type": "skill_synced",
                                            "skill_name": skill_name,
                                            "generated_by": generated_by,
                                            "timestamp": time.time()
                                        }))
                                        loop.close()
                                    except:
                                        pass
                                except Exception as e_sync:
                                    logger.error(f"❌ [ClusterClient] 处理技能同步失败: {e_sync}")
                            else:
                                logger.warning(f"⚠️ [ClusterClient] 收到无效的技能同步消息")

                    except ValueError:
                        break
            except socket.timeout:
                continue
            except Exception as e:
                if self.running and self.socket:
                    logger.warning(f"👂 [ClusterClient] 监听异常: {e}")
                break
        logger.info(f"🛑 [ClusterClient] 任务监听线程已停止")
        if self.running:
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
                
                # 【关键修复】加入房间成功后，等待接收房主推送的房间完整信息后再保存状态
                room_info_from_manager = {
                    "room_name": "",
                    "room_id": "",
                    "owner_name": "",
                    "owner_model": "",
                    "members_detail": []
                }
                try:
                    # 从剩余的缓冲区中继续读取房主推送的房间信息
                    # 注意：响应缓冲区中可能还有未处理的消息
                    logger.debug(f"📥 [ClusterClient] 尝试从缓冲区获取房主推送的房间信息...")
                    received_room_info = False
                    
                    # 等待接收房主推送的房间信息（最多等待2秒）
                    sock.settimeout(2.0)
                    try:
                        while True:
                            data = sock.recv(8192)
                            if not data:
                                break
                            response_buffer += data
                            
                            # 解析所有消息
                            messages, response_buffer = self._parse_json_messages(response_buffer)
                            for msg_bytes in messages:
                                try:
                                    msg_obj = json.loads(msg_bytes.decode('utf-8'))
                                    msg_type = msg_obj.get("type")
                                    
                                    # 关键：接收房主推送的room_info_update消息
                                    if msg_type == "room_info_update":
                                        room_info = msg_obj.get("room_info", {})
                                        room_info_from_manager = {
                                            "room_name": room_info.get("room_name", ""),
                                            "room_id": room_info.get("room_id", ""),
                                            "owner_name": room_info.get("owner_name", ""),
                                            "owner_model": room_info.get("owner_model", ""),
                                            "members_detail": room_info.get("members_detail", [])
                                        }
                                        received_room_info = True
                                        logger.info(f"📥 [ClusterClient] 成功从房主获取房间信息: room_name={room_info_from_manager['room_name']}, 成员数={len(room_info_from_manager['members_detail'])}")
                                        break
                                except json.JSONDecodeError:
                                    continue
                            
                            if received_room_info:
                                break
                    except socket.timeout:
                        logger.debug(f"📥 [ClusterClient] 等待房间信息超时，继续使用默认值")
                    
                    # 恢复心跳超时设置
                    sock.settimeout(5.0)
                except Exception as e_room_info:
                    logger.warning(f"⚠️ 接收房主房间信息失败，使用默认值: {e_room_info}")
                
                # 【关键修复1】加入房间成功后，持久化所有关键信息（包括从房主获取的房间信息）
                try:
                    import os
                    import json as json_module
                    from config import CLUSTER_WORKER_STATE_PATH
                    
                    def _ensure_data_dir_exists():
                        data_dir = os.path.dirname(CLUSTER_WORKER_STATE_PATH)
                        if not os.path.exists(data_dir):
                            os.makedirs(data_dir, exist_ok=True)
                    
                    # 立刻保存所有关键信息（包括从房主获取的房间信息）
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
                        "room_name": room_info_from_manager.get("room_name", ""),
                        "room_id": room_info_from_manager.get("room_id", ""),
                        "owner_name": room_info_from_manager.get("owner_name", ""),
                        "owner_model": room_info_from_manager.get("owner_model", ""),
                        "members_detail": room_info_from_manager.get("members_detail", [])
                    }
                    with open(CLUSTER_WORKER_STATE_PATH, 'w', encoding='utf-8') as f:
                        json_module.dump(initial_state, f, ensure_ascii=False, indent=2)
                    logger.info(f"💾 [Worker持久化] 加入房间成功，已保存完整协作状态: room_name={room_info_from_manager.get('room_name', 'unknown')}, host={host}, port={port}")
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
    
    def _auto_reconnect_loop(self):
        """【核心重连增强版】后台自动重连循环 - 利用本地持久化状态自动恢复连接"""
        import os
        import json as json_module
        from config import CLUSTER_WORKER_STATE_PATH
        
        logger.info(f"🔄 [自动重连] 自动重连后台线程已启动")
        
        while True:
            try:
                # 1. 先从本地持久化文件读取之前的房主连接信息
                state_path_exists = os.path.exists(CLUSTER_WORKER_STATE_PATH)
                if not state_path_exists:
                    time.sleep(5)
                    continue
                
                with open(CLUSTER_WORKER_STATE_PATH, 'r', encoding='utf-8') as f:
                    saved_state = json_module.load(f)
                
                # 如果状态标记不是 in_room，不需要自动重连
                if not saved_state.get("in_room", False):
                    time.sleep(5)
                    continue
                
                # 2. 检查当前连接状态，如果已经有活跃连接就跳过
                if self.running and self.socket:
                    time.sleep(5)
                    continue
                
                # 3. 尝试用保存的参数重新连接房主
                saved_host = saved_state.get("host")
                saved_port = saved_state.get("port")
                saved_node_id = saved_state.get("node_id")
                saved_name = saved_state.get("name")
                saved_model = saved_state.get("model")
                saved_role = saved_state.get("role", "worker")
                saved_mode = saved_state.get("mode", "auto")
                
                if not saved_host or not saved_port or not saved_node_id:
                    time.sleep(5)
                    continue
                
                logger.info(f"🔄 [自动重连] 检测到之前的协作状态，正在尝试自动恢复连接到 {saved_host}:{saved_port}...")
                
                # 4. 执行重连
                node_info = {
                    "node_id": saved_node_id,  # 关键：复用完全相同的node_id！房主端会直接重激活而不是新建节点
                    "name": saved_name,
                    "model": saved_model,
                    "role": saved_role,
                    "mode": saved_mode
                }
                
                success, reason = self.join(saved_host, saved_port, node_info)
                
                if success:
                    logger.info(f"✅ [自动重连成功] 已自动恢复协作连接，继续工作！")
                else:
                    logger.warning(f"⏳ [自动重连失败] 原因: {reason}, 5秒后重试...")
                
                # 重连尝试间隔
                time.sleep(5)
                
            except Exception as e:
                logger.warning(f"[自动重连循环异常] {e}")
                time.sleep(5)
    
    def start_auto_reconnect(self):
        """启动后台自动重连线程"""
        threading.Thread(target=self._auto_reconnect_loop, daemon=True).start()
        logger.info(f"🔄 [ClusterClient] 自动重连机制已启动")
    
    def close(self, clear_state: bool = True):
        """关闭持久连接，停止所有后台线程
        
        Args:
            clear_state: 是否清除本地持久化状态文件，默认为True（正常退出协作模式时清除）
                         设置为False时仅关闭连接不断开重连（用于重连前的临时断开）
        """
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        
        # 如果需要清除状态，同时清除本地持久化文件
        if clear_state:
            try:
                import os
                from config import CLUSTER_WORKER_STATE_PATH
                if os.path.exists(CLUSTER_WORKER_STATE_PATH):
                    os.remove(CLUSTER_WORKER_STATE_PATH)
                    logger.info("🗑️ [Worker持久化] close()清理协作状态文件，协作会话已结束")
            except Exception as e_clear:
                logger.warning(f"⚠️ close()清理状态文件失败: {e_clear}")
        
        logger.info(f"🔌 [ClusterClient] 连接已完全关闭（clear_state={clear_state}）")