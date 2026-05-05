#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
能力评估器 - 动态计算节点的综合能力分
"""
from typing import Dict, Any, Optional
from logger import logger


class CapabilityAssessor:
    """
    多维度能力评估器

    评估维度（权重可配置）：
    - 模型基准分 40%：基于模型能力排行榜
    - 硬件算力 20%：GPU 显存、CPU 核心数
    - 实时负载 15%：CPU 使用率、内存占用
    - 历史表现 15%：任务成功率、平均完成时间
    - 网络质量 10%：RTT（可选，暂未实现）
    """

    def __init__(self, model_rankings: Optional[Dict[str, float]] = None):
        # 默认模型排行榜（可从 config.py 或配置文件加载）
        self.model_rankings = model_rankings or {
            "qwen2.5-coder:7b": 0.95,
            "qwen2.5:7b": 0.85,
            "llama3:8b": 0.80,
            "phi3:3.8b": 0.60,
            "mistral:7b": 0.70
        }

        # 历史表现存储：node_id -> {"success_rate": 0.9, "avg_duration": 2.5, "samples": 10}
        self.history: Dict[str, Dict[str, float]] = {}

        # 权重配置（可从 config.py 扩展）
        self.weights = {
            "model": 0.4,
            "hardware": 0.2,
            "load": 0.15,
            "history": 0.15,
            "network": 0.1
        }

    def assess(self, node_info: Dict[str, Any]) -> float:
        """
        计算综合能力分（0.0-1.0）

        Args:
            node_info: 节点信息字典，包含以下字段：
                - node_id: 节点唯一标识
                - model: 模型名称
                - gpu_memory: GPU 显存（GB）
                - cpu_cores: CPU 核心数
                - load_cpu: CPU 负载（0.0-1.0）
                - load_memory: 内存使用率（0.0-1.0）

        Returns:
            0.0-1.0 的能力分
        """
        score = 0.0

        # 1. 模型基准分
        model = node_info.get("model", "unknown")
        model_score = self.model_rankings.get(model, 0.5)
        score += model_score * self.weights["model"]

        # 2. 硬件分（GPU 显存 + CPU 核心）
        hardware_score = self._calc_hardware_score(node_info)
        score += hardware_score * self.weights["hardware"]

        # 3. 实时负载分（负载越高，分越低）
        load_cpu = node_info.get("load_cpu", 0.0)
        load_score = 1.0 - min(load_cpu, 1.0)
        score += load_score * self.weights["load"]

        # 4. 历史表现分（任务成功率）
        node_id = node_info.get("node_id")
        if node_id in self.history:
            history_score = self.history[node_id].get("success_rate", 0.8)
        else:
            history_score = 0.8  # 新节点默认 80% 成功率
        score += history_score * self.weights["history"]

        # 5. 网络分（暂未实现，暂时给 1.0）
        score += 1.0 * self.weights["network"]

        return max(0.0, min(1.0, score))

    def _calc_hardware_score(self, node_info: Dict[str, Any]) -> float:
        """
        计算硬件能力分

        基于 GPU 显存和 CPU 核心数综合评分
        """
        score = 0.5  # 默认中等

        gpu_mem = node_info.get("gpu_memory", 0)  # GB
        if gpu_mem >= 24:
            score = 1.0
        elif gpu_mem >= 16:
            score = 0.9
        elif gpu_mem >= 8:
            score = 0.7
        elif gpu_mem >= 4:
            score = 0.5
        else:
            score = 0.3

        cpu_cores = node_info.get("cpu_cores", 4)
        if cpu_cores >= 16:
            score = min(1.0, score + 0.1)
        elif cpu_cores >= 8:
            score = min(1.0, score + 0.05)
        elif cpu_cores < 4:
            score = max(0.0, score - 0.1)

        return score

    def record_task_outcome(self, node_id: str, success: bool, duration: float):
        """
        记录任务执行结果，更新历史表现

        使用指数移动平均（EMA）平滑更新

        Args:
            node_id: 节点标识
            success: 是否成功
            duration: 执行耗时（秒）
        """
        if node_id not in self.history:
            self.history[node_id] = {
                "success_rate": 0.8,
                "avg_duration": 2.0,
                "samples": 0
            }

        hist = self.history[node_id]
        samples = hist["samples"]
        old_success = hist["success_rate"]
        old_duration = hist["avg_duration"]

        # EMA 平滑系数（0.1 表示新数据占 10%）
        alpha = 0.1
        new_success = old_success * (1 - alpha) + (1.0 if success else 0.0) * alpha
        new_duration = old_duration * (1 - alpha) + duration * alpha

        self.history[node_id] = {
            "success_rate": new_success,
            "avg_duration": new_duration,
            "samples": samples + 1
        }

        logger.debug(
            "任务执行记录已更新",
            node_id=node_id,
            success=success,
            duration=duration,
            new_success_rate=new_success
        )

    def update_model_rankings(self, new_rankings: Dict[str, float]):
        """
        动态更新模型排行榜

        Args:
            new_rankings: 新的模型评分字典（部分或全部）
        """
        self.model_rankings.update(new_rankings)
        logger.info("模型排行榜已更新", rankings=self.model_rankings)

    def get_node_score_details(self, node_info: Dict[str, Any]) -> Dict[str, float]:
        """
        获取能力分的详细维度（用于调试和展示）

        Returns:
            包含各维度得分的字典
        """
        details = {}

        # 模型分
        model = node_info.get("model", "unknown")
        model_score = self.model_rankings.get(model, 0.5)
        details["model"] = model_score * self.weights["model"]

        # 硬件分
        hardware_score = self._calc_hardware_score(node_info)
        details["hardware"] = hardware_score * self.weights["hardware"]

        # 负载分
        load_cpu = node_info.get("load_cpu", 0.0)
        load_score = 1.0 - min(load_cpu, 1.0)
        details["load"] = load_score * self.weights["load"]

        # 历史分
        node_id = node_info.get("node_id")
        if node_id in self.history:
            history_score = self.history[node_id].get("success_rate", 0.8)
        else:
            history_score = 0.8
        details["history"] = history_score * self.weights["history"]

        # 网络分（暂为固定值）
        details["network"] = 1.0 * self.weights["network"]

        # 总分
        details["total"] = sum(details.values())

        return details
