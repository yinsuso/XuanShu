"""
能力评估器 - 动态计算节点综合能力分
"""
from typing import Dict, Any
from logger import logger


class CapabilityAssessor:
    """
    多维度能力评估器
    评估维度与权重（可配置）：
    - 模型基准分 40%（动态排行榜）
    - 硬件算力 20%（GPU 显存、CPU 核心）
    - 实时负载 15%（CPU、内存）
    - 历史表现 15%（成功率、平均耗时）
    - 网络质量 10%（RTT，可选）
    """
    
    def __init__(self, model_rankings=None):
        self.model_rankings = model_rankings or {
            "qwen2.5-coder:7b": 0.95,
            "qwen2.5:7b": 0.85,
            "llama3:8b": 0.80,
            "phi3:3.8b": 0.75,
            "mistral:7b": 0.78
        }
        self.history: Dict[str, Dict[str, float]] = {}
        self.weights = {
            "model": 0.4,
            "hardware": 0.2,
            "load": 0.15,
            "history": 0.15,
            "network": 0.1
        }
    
    def assess(self, node_info: Dict[str, Any]) -> float:
        """
        计算综合能力分 0.0-1.0
        """
        score = 0.0
        
        # 1. 模型基准分
        model = node_info.get("model", "unknown")
        model_score = self.model_rankings.get(model, 0.5)
        score += model_score * self.weights["model"]
        
        # 2. 硬件分（GPU 显存 + CPU）
        hardware_score = self._calc_hardware_score(node_info)
        score += hardware_score * self.weights["hardware"]
        
        # 3. 实时负载分（负载越高分越低）
        load_score = 1.0 - min(node_info.get("load_cpu", 0.0), 1.0)
        score += load_score * self.weights["load"]
        
        # 4. 历史表现分
        node_id = node_info.get("node_id")
        if node_id in self.history:
            history_score = self.history[node_id].get("success_rate", 0.8)
        else:
            history_score = 0.8  # 默认
        score += history_score * self.weights["history"]
        
        # 5. 网络分（暂为 1.0）
        score += 1.0 * self.weights["network"]
        
        return max(0.0, min(1.0, score))
    
    def _calc_hardware_score(self, node_info: Dict[str, Any]) -> float:
        """计算硬件分数"""
        score = 0.5
        gpu_mem = node_info.get("gpu_memory", 0)
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
        
        return score
    
    def record_task_outcome(self, node_id: str, success: bool, duration: float):
        """记录任务执行结果，更新历史表现"""
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
        
        alpha = 0.1
        new_success = old_success * (1 - alpha) + (1.0 if success else 0.0) * alpha
        new_duration = old_duration * (1 - alpha) + duration * alpha
        
        self.history[node_id] = {
            "success_rate": new_success,
            "avg_duration": new_duration,
            "samples": samples + 1
        }
    
    def update_model_rankings(self, new_rankings: Dict[str, float]):
        """动态更新模型排行榜"""
        self.model_rankings.update(new_rankings)
        logger.info("模型排行榜已更新", rankings=self.model_rankings)


def default_assessor() -> CapabilityAssessor:
    """创建默认评估器实例"""
    return CapabilityAssessor()
