
import json
import asyncio
from typing import Dict, Any, Optional
from logger import logger

class ClusterNode:
    """集群节点定义"""
    def __init__(self, node_id: str, ip: str, model: str, role: str, mode: str):
        self.node_id = node_id
        self.ip = ip
        self.model = model
        self.role = role # 如: 架构师, 文案, 工程师
        self.mode = mode # auto 或 manual (人工干预)
        self.status = "online"
        self.capabilities = [] # 待通过接口获取

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "ip": self.ip,
            "model": self.model,
            "role": self.role,
            "mode": self.mode,
            "status": self.status
        }

class ClusterManager:
    """集群管理中心 (房主端)"""
    def __init__(self):
        self.nodes: Dict[str, ClusterNode] = {}
        self.current_project = "Unnamed Project"

    def add_node(self, node_info: Dict[str, Any]):
        node = ClusterNode(
            node_id=node_info['node_id'],
            ip=node_info['ip'],
            model=node_info['model'],
            role=node_info['role'],
            mode=node_info['mode']
        )
        self.nodes[node.node_id] = node
        logger.info(f"🤝 [Cluster] 节点 {node.node_id} ({node.role}) 已加入集群")

    def remove_node(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"💔 [Cluster] 节点 {node_id} 已离开")

    def get_cluster_map(self):
        return {nid: n.to_dict() for nid, n in self.nodes.items()}
