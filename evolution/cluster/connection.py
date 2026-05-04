
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

    async def _broadcast_event(self, event: dict):
        for ws in self.ws_connections:
            try:
                await ws.send_json(event)
            except:
                pass


class ClusterManager:
    """集群管理中心 (房主端)"""
    def __init__(self):
        self.nodes: Dict[str, ClusterNode] = {}
        self.current_project = "Unnamed Project"
        self._server: Optional["ClusterServer"] = None

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

    def start_server(self, host: str = "0.0.0.0", port: int = 30001):
        """启动房主端 TCP 服务器，监听节点加入请求"""
        if self._server is None:
            self._server = ClusterServer(self, host, port)
            self._server.start()
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
        """处理客户端加入请求"""
        try:
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
            response = {"type": "ack", "status": "ok", "reason": "加入成功"}
            conn.sendall(json.dumps(response).encode('utf-8'))
        except json.JSONDecodeError:
            logger.error(f"[ClusterServer] 收到无效JSON: {data}")
            response = {"type": "ack", "status": "error", "reason": "无效的消息格式"}
            conn.sendall(json.dumps(response).encode('utf-8'))
        except Exception as e:
            logger.error(f"[ClusterServer] 处理客户端异常: {e}")
        finally:
            conn.close()

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

    def join(self, host: str, port: int, node_info: Dict[str, Any]) -> bool:
        """
        连接到房主服务器并发送加入请求
        
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
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
