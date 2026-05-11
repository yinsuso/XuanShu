"""
任务调度器 - 基于策略选择最优执行节点
"""
from typing import List, Dict, Any, Optional
from .connection import ClusterNode
from .capability import CapabilityAssessor
from logger import logger


class TaskScheduler:
    """
    支持多种调度策略的任务调度器
    """
    
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
        """更新节点池"""
        self.node_pool = {n.node_id: n for n in nodes}
    
    def schedule(self, task: Dict[str, Any]) -> Optional[ClusterNode]:
        """
        根据策略调度任务
        """
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
        """
        过滤出可接受任务的节点
        条件：在线、未满载、负载<80%
        """
        candidates = []
        for node in self.node_pool.values():
            # 注意：ClusterNode 可能有不同的属性名，根据实际实现调整
            if (getattr(node, "status", "online") == "online" and 
                len(getattr(node, "pending_tasks", [])) < 5 and 
                getattr(node, "load_cpu", 0.0) < 0.8):
                candidates.append(node)
        return candidates
    
    def _schedule_by_capability(self, candidates: List[ClusterNode], task_type: str) -> Optional[ClusterNode]:
        """能力优先策略：选择评估分最高的节点"""
        scored = []
        for node in candidates:
            # 构建节点信息字典供评估器使用
            node_info = {
                "node_id": node.node_id,
                "model": getattr(node, "model", "unknown"),
                "gpu_memory": getattr(node, "gpu_memory", 0),
                "cpu_cores": getattr(node, "cpu_cores", 4),
                "load_cpu": getattr(node, "load_cpu", 0.0),
                "load_memory": getattr(node, "load_memory", 0.0)
            }
            score = self.assessor.assess(node_info)
            scored.append((score, node))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None
    
    def _schedule_by_affinity(self, candidates: List[ClusterNode], task_type: str) -> Optional[ClusterNode]:
        """亲和性匹配策略：优先选择匹配任务类型的模型"""
        preferred_models = self.affinity_rules.get(task_type, [])
        if not preferred_models:
            return self._schedule_by_capability(candidates, task_type)
        
        affinity_candidates = [n for n in candidates if getattr(n, "model", "") in preferred_models]
        if not affinity_candidates:
            affinity_candidates = candidates  # 降级为能力优先
        
        return self._schedule_by_capability(affinity_candidates, task_type)
    
    def _schedule_by_load(self, candidates: List[ClusterNode]) -> Optional[ClusterNode]:
        """负载均衡策略：选择负载最低的节点"""
        if not candidates:
            return None
        return min(candidates, key=lambda n: getattr(n, "load_cpu", 0.0) + getattr(n, "load_memory", 0.0))
    
    def _schedule_round_robin(self, candidates: List[ClusterNode]) -> Optional[ClusterNode]:
        """轮询策略：依次分配"""
        if not candidates:
            return None
        node = candidates[self.round_robin_index % len(candidates)]
        self.round_robin_index += 1
        return node

    def select(self, nodes: List) -> Optional[ClusterNode]:
        """
        从节点池中选择最优节点（兼容旧接口）
        
        Args:
            nodes: 节点列表
        
        Returns:
            选中的ClusterNode对象
        """
        self.update_node_pool(nodes)
        task = {"task_type": "default"}
        return self.schedule(task)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        stats = {
            "strategy": self.strategy,
            "node_pool_size": len(self.node_pool),
            "round_robin_index": self.round_robin_index,
            "affinity_rules": self.affinity_rules
        }
        # 统计候选节点数量
        candidates = self._filter_candidates()
        stats["available_nodes"] = len(candidates)
        return stats
