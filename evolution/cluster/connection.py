     1|
     2|import json
     3|import asyncio
     4|from typing import Dict, Any, Optional
     5|from logger import logger
     6|
     7|class ClusterNode:
     8|    """集群节点定义"""
     9|    def __init__(self, node_id: str, ip: str, model: str, role: str, mode: str):
    10|        self.node_id = node_id
    11|        self.ip = ip
    12|        self.model = model
    13|        self.role = role # 如: 架构师, 文案, 工程师
    14|        self.mode = mode # auto 或 manual (人工干预)
    15|        self.status = "online"
    16|        self.capabilities = [] # 待通过接口获取
    17|
    18|    def to_dict(self):
    19|        return {
    20|            "node_id": self.node_id,
    21|            "ip": self.ip,
    22|            "model": self.model,
    23|            "role": self.role,
    24|            "mode": self.mode,
    25|            "status": self.status
    26|        }
    27|
    28|class ClusterManager:
    29|    """集群管理中心 (房主端)"""
    30|    def __init__(self):
    31|        self.nodes: Dict[str, ClusterNode] = {}
    32|        self.current_project = "Unnamed Project"
    33|
    34|    def add_node(self, node_info: Dict[str, Any]):
    35|        node = ClusterNode(
    36|            node_id=node_info['node_id'],
    37|            ip=node_info['ip'],
    38|            model=node_info['model'],
    39|            role=node_info['role'],
    40|            mode=node_info['mode']
    41|        )
    42|        self.nodes[node.node_id] = node
    43|        logger.info(f"🤝 [Cluster] 节点 {node.node_id} ({node.role}) 已加入集群")
    44|
    45|    def remove_node(self, node_id: str):
    46|        if node_id in self.nodes:
    47|            del self.nodes[node_id]
    48|            logger.info(f"💔 [Cluster] 节点 {node_id} 已离开")
    49|
    50|    def get_cluster_map(self):
    51|        return {nid: n.to_dict() for nid, n in self.nodes.items()}
    52|