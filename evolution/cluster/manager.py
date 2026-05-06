#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集群管理器（自包含简化版）
"""
import threading
import time
import uuid
from typing import Dict, List, Any
from config import SCHEDULER_STRATEGY

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

    def _heartbeat_loop(self):
        while True:
            time.sleep(5)
            pass

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "online_nodes": sum(1 for n in self.nodes.values() if n.status == "online"),
            "total_rooms": len(self.rooms),
            "scheduler": self.scheduler.get_stats()
        }

__all__ = ['ClusterManager']
