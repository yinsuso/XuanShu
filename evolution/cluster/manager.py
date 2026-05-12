#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集群管理器（自包含简化版）
增强版：真实心跳、负载采集、任务重试次数限制
"""
import threading
import time
import uuid
import sys
from typing import Dict, List, Any
from config import SCHEDULER_STRATEGY, MANAGER_MAX_RETRIES
from logger import get_logger

logger = get_logger("evolution.cluster.manager")

class SimpleNode:
    def __init__(self, node_id: str, model: str = "qwen2.5-coder:7b", host: str = "127.0.0.1", port: int = 30001):
        self.node_id = node_id
        self.model = model
        self.host = host
        self.port = port
        self.status = "online"
        self.load_cpu: float = 0.0
        self.load_memory: float = 0.0
        self.pending_tasks: List[Any] = []
        self.metadata: Dict[str, Any] = {}
        self.last_heartbeat: float = time.time()
        self.task_retry_count: Dict[str, int] = {}  # task_id -> retry count

class SimpleScheduler:
    def __init__(self, manager):
        self.manager = manager
        self.index = 0
    def schedule(self, task: Dict[str, Any]):
        nodes = [n for n in self.manager.nodes.values() if n.status == "online"]
        if not nodes:
            raise RuntimeError("No available nodes")
        node = nodes[self.index % len(nodes)]
        self.index += 1
        return node
    def get_stats(self) -> Dict[str, Any]:
        return {"strategy": "round_robin", "total_nodes": len(self.manager.nodes)}

class ClusterManager:
    def __init__(self):
        self.nodes: Dict[str, SimpleNode] = {}
        self.rooms: Dict[str, Dict] = {}
        self.tasks: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.scheduler = SimpleScheduler(self)
        self._add_local_node()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _add_local_node(self):
        node_id = f"node_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        model = "qwen2.5-coder:7b"
        node = SimpleNode(node_id, model)
        self.nodes[node_id] = node

    # 房间管理
    def create_room(self, name: str, owner: str) -> str:
        with self.lock:
            room_id = f"room_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            self.rooms[room_id] = {
                "id": room_id,
                "name": name,
                "owner": owner,
                "members": {},
                "tasks": [],
                "created_at": time.time(),
            }
            return room_id

    def list_rooms(self) -> List[Dict]:
        with self.lock:
            return list(self.rooms.values())

    def get_room(self, room_id: str) -> Dict | None:
        return self.rooms.get(room_id)

    # 成员管理
    def join_room(self, room_id: str, member_name: str, mode: str, model: str) -> bool:
        with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                return False
            room["members"][member_name] = {
                "name": member_name,
                "mode": mode,
                "model": model,
                "status": "online"
            }
            return True

    def leave_room(self, room_id: str, member_name: str):
        with self.lock:
            room = self.rooms.get(room_id)
            if room and member_name in room["members"]:
                del room["members"][member_name]

    def get_room_members(self, room_id: str) -> List[Dict]:
        with self.lock:
            room = self.rooms.get(room_id)
            return list(room["members"].values()) if room else []

    # 任务管理
    def submit_task(self, room_id: str, task: Dict[str, Any]) -> str:
        with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                raise ValueError("Room not found")
            task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            task["task_id"] = task_id
            task["room_id"] = room_id
            task["status"] = "pending"
            room["tasks"].append(task)
            self.tasks[task_id] = task
            return task_id

    def schedule_task(self, task: Dict[str, Any]):
        return self.scheduler.schedule(task)

    def get_room_tasks(self, room_id: str) -> List[Dict]:
        with self.lock:
            room = self.rooms.get(room_id)
            return room["tasks"] if room else []

    def _collect_system_load(self):
        """采集本机CPU和内存负载（跨平台兼容）"""
        cpu_load = 0.0
        mem_load = 0.0
        try:
            import psutil
            cpu_load = psutil.cpu_percent(interval=0.5) / 100.0
            mem = psutil.virtual_memory()
            mem_load = mem.percent / 100.0
        except ImportError:
            # psutil未安装时用简化估算
            cpu_load = 0.3
            mem_load = 0.5
        return (cpu_load, mem_load)

    def _reassign_task_with_limit(self, node_id: str, task_id: str, max_retries: int = None):
        """带次数限制的任务重派，超过max_retries后标记失败"""
        if max_retries is None:
            max_retries = MANAGER_MAX_RETRIES
        node = self.nodes.get(node_id)
        if not node:
            return False
        
        # 增加重试计数
        if task_id not in node.task_retry_count:
            node.task_retry_count[task_id] = 0
        node.task_retry_count[task_id] += 1
        
        current_retry = node.task_retry_count[task_id]
        logger.info(
            "任务重派中",
            details={
                "task_id": task_id,
                "node_id": node_id,
                "retry": current_retry,
                "max_retries": max_retries,
            }
        )
        
        if current_retry >= max_retries:
            logger.error(
                "任务超过最大重试次数，标记为失败",
                details={
                    "task_id": task_id,
                    "max_retries": max_retries,
                }
            )
            task = self.tasks.get(task_id)
            if task:
                task["status"] = "failed"
                task["error"] = f"超过最大重试次数 {max_retries}"
            node.status = "suspect"  # 标记节点异常
            return False
        return True

    def _heartbeat_loop(self):
        """增强版心跳循环：采集负载、更新节点存活状态、清理超时节点"""
        logger.info("集群心跳循环已启动")
        while True:
            try:
                # 采集本机系统负载
                cpu, mem = self._collect_system_load()
                local_nodes = [n for n in self.nodes.values() if hasattr(n, 'host') and n.host in ("127.0.0.1", "localhost")]
                for node in local_nodes:
                    node.load_cpu = cpu
                    node.load_memory = mem
                    node.last_heartbeat = time.time()

                # 检查其他节点是否超时（超过30秒无心跳）
                now = time.time()
                with self.lock:
                    for nid, node in list(self.nodes.items()):
                        if now - node.last_heartbeat > 30 and node.host not in ("127.0.0.1", "localhost"):
                            if node.status != "offline":
                                logger.warning(
                                    "节点心跳超时，标记为离线",
                                    details={"node_id": nid, "elapsed": round(now - node.last_heartbeat, 1)}
                                )
                                node.status = "offline"

                # 每5秒执行一次
                time.sleep(5)
            except Exception as e:
                logger.exception("心跳循环异常")
                time.sleep(5)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "online_nodes": sum(1 for n in self.nodes.values() if n.status == "online"),
            "total_rooms": len(self.rooms),
            "scheduler": self.scheduler.get_stats()
        }

__all__ = ['ClusterManager']
