#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务调度器 - 基于策略选择最优执行节点
"""
from typing import List, Dict, Any, Optional
from evolution.cluster.connection import ClusterNode
from .capability import CapabilityAssessor
from logger import logger


class TaskScheduler:
    """
    智能任务调度器

    支持多种调度策略：
    - capability: 按能力分最高优先
    - load_balance: 按负载最低优先
    - affinity: 按任务类型亲和性匹配后能力最优
    - round_robin: 轮询分配
    """

    def __init__(
        self,
        assessor: CapabilityAssessor,
        strategy: str = "affinity"
    ):
        """
        初始化调度器

        Args:
            assessor: 能力评估器实例
            strategy: 调度策略，支持 "capability", "load_balance", "affinity", "round_robin"
        """
        self.assessor = assessor
        self.strategy = strategy
        self.node_pool: Dict[str, ClusterNode] = {}
        self.round_robin_index = 0

        # 任务亲和性规则（可配置）
        # 说明：当任务类型匹配时，优先使用对应模型列表中的节点
        self.affinity_rules: Dict[str, List[str]] = {
            "code_generation": ["qwen2.5-coder", "qwen2.5-coder:7b"],
            "text_writing": ["qwen2.5", "mistral", "llama3"],
            "code_review": ["qwen2.5-coder"],
            "data_analysis": ["llama3", "phi3"],
            "default": []
        }

    def update_node_pool(self, nodes: List[ClusterNode]):
        """
        更新可用节点池

        通常由 Manager 定期调用（如每 5 秒扫描一次）

        Args:
            nodes: 当前在线的节点列表
        """
        self.node_pool = {n.node_id: n for n in nodes}

    def schedule(self, task: Dict[str, Any]) -> Optional[ClusterNode]:
        """
        根据当前策略选择一个节点执行任务

        Args:
            task: 任务字典，至少包含 task_type 字段

        Returns:
            选中的节点对象，若无可用节点则返回 None
        """
        task_type = task.get("task_type", "default")

        # 过滤候选节点（在线、未过载、负载 < 80%）
        candidates = self._filter_candidates()
        if not candidates:
            logger.warning("调度失败：无可用候选节点", task_type=task_type)
            return None

        logger.debug(
            "调度候选节点",
            task_type=task_type,
            total_nodes=len(self.node_pool),
            candidates=len(candidates)
        )

        # 按策略选择
        if self.strategy == "capability":
            return self._schedule_by_capability(candidates, task_type)
        elif self.strategy == "load_balance":
            return self._schedule_by_load(candidates)
        elif self.strategy == "affinity":
            return self._schedule_by_affinity(candidates, task_type)
        elif self.strategy == "round_robin":
            return self._schedule_round_robin(candidates)
        else:
            logger.warning("未知调度策略，降级到 capability", strategy=self.strategy)
            return self._schedule_by_capability(candidates, task_type)

    def _filter_candidates(self) -> List[ClusterNode]:
        """
        过滤出可接受新任务的节点

        条件：
        1. 状态为 online
        2. 当前 pending_tasks 数量小于阈值（默认 5）
        3. CPU 负载 < 80%
        """
        candidates = []
        max_pending = 5  # TODO: 从配置读取

        for node in self.node_pool.values():
            if node.status != "online":
                continue

            pending_count = len(getattr(node, "pending_tasks", []))
            if pending_count >= max_pending:
                continue

            load_cpu = getattr(node, "load_cpu", 0.0)
            if load_cpu >= 0.8:
                continue

            candidates.append(node)

        return candidates

    def _schedule_by_capability(
        self,
        candidates: List[ClusterNode],
        task_type: str
    ) -> Optional[ClusterNode]:
        """
        能力优先策略：选择评估分最高的节点

        综合所有维度（模型、硬件、负载、历史）
        """
        scored = []
        for node in candidates:
            node_info = {
                "node_id": node.node_id,
                "model": node.model,
                "gpu_memory": getattr(node, "gpu_memory", 0),
                "cpu_cores": getattr(node, "cpu_cores", 4),
                "load_cpu": getattr(node, "load_cpu", 0.0),
                "load_memory": getattr(node, "load_memory", 0.0)
            }
            score = self.assessor.assess(node_info)
            scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[0][1] if scored else None

        if selected:
            logger.debug(
                "能力优先调度",
                task_type=task_type,
                selected_node=selected.node_id,
                model=selected.model,
                score=scored[0][0]
            )

        return selected

    def _schedule_by_affinity(
        self,
        candidates: List[ClusterNode],
        task_type: str
    ) -> Optional[ClusterNode]:
        """
        亲和性调度：先按任务类型筛选匹配的模型，再按能力排序

        例如：code_generation 任务优先选择 qwen2.5-coder 模型
        """
        preferred_models = self.affinity_rules.get(task_type, [])
        if not preferred_models:
            # 无亲和性规则，降级到能力优先
            return self._schedule_by_capability(candidates, task_type)

        affinity_candidates = [
            n for n in candidates
            if any(pref in n.model for pref in preferred_models)
        ]

        if not affinity_candidates:
            # 无亲和节点，降级到全候选
            logger.debug(
                "亲和性调度的候选节点为空，降级到全候选",
                task_type=task_type,
                preferred_models=preferred_models,
                total_candidates=len(candidates)
            )
            affinity_candidates = candidates

        # 在亲和节点中按能力排序
        return self._schedule_by_capability(affinity_candidates, task_type)

    def _schedule_by_load(self, candidates: List[ClusterNode]) -> Optional[ClusterNode]:
        """
        负载均衡策略：选择负载最低的节点（CPU + 内存）
        """
        if not candidates:
            return None

        def load_key(node):
            return getattr(node, "load_cpu", 0.0) + getattr(node, "load_memory", 0.0)

        selected = min(candidates, key=load_key)
        load = load_key(selected)

        logger.debug(
            "负载均衡调度",
            selected_node=selected.node_id,
            load=load
        )

        return selected

    def _schedule_round_robin(self, candidates: List[ClusterNode]) -> Optional[ClusterNode]:
        """
        轮询调度：依次轮流分配
        """
        if not candidates:
            return None

        node = candidates[self.round_robin_index % len(candidates)]
        self.round_robin_index += 1

        logger.debug(
            "轮询调度",
            selected_node=node.node_id,
            index=self.round_robin_index
        )

        return node

    def get_stats(self) -> Dict[str, Any]:
        """
        获取调度器统计信息（用于监控）
        """
        stats = {
            "strategy": self.strategy,
            "total_nodes": len(self.node_pool),
            "affinity_rules": self.affinity_rules
        }

        # 统计各节点状态
        online = sum(1 for n in self.node_pool.values() if n.status == "online")
        stats["online_nodes"] = online

        # 任务分布
        total_pending = sum(len(getattr(n, "pending_tasks", [])) for n in self.node_pool.values())
        stats["total_pending_tasks"] = total_pending

        return stats
