"""
能力评估器 - 动态计算节点综合能力分
"""
from typing import Dict, Any
from logger import logger


class CapabilityAssessor:
    """
    多维度能力评估器
    评估维度与权重（可配置）：
    - 模型基准分 40%（动态排行榜，支持子串匹配）
    - 硬件算力 20%（GPU 显存、CPU 核心）
    - 实时负载 15%（CPU、内存）
    - 历史表现 15%（成功率、平均耗时）
    - 网络质量 10%（RTT，可选）
    """
    
    def __init__(self, model_rankings=None):
        self.model_rankings = model_rankings or {
            "qwen3.5:9b": 0.90,
            "qwen3": 0.88,
            "qwen2.5-coder:7b": 0.95,
            "qwen2.5-coder:14b": 0.98,
            "qwen2.5-coder:32b": 0.99,
            "qwen2.5:7b": 0.85,
            "qwen2.5:14b": 0.90,
            "qwen2.5:32b": 0.95,
            "qwen-plus": 0.92,
            "qwen-turbo": 0.88,
            "llama3:8b": 0.80,
            "llama3:70b": 0.94,
            "llama3.1:8b": 0.82,
            "llama3.1:70b": 0.95,
            "llama3.2": 0.75,
            "phi3:3.8b": 0.70,
            "phi4": 0.80,
            "mistral:7b": 0.78,
            "mistral-nemo": 0.82,
            "deepseek-coder:6.7b": 0.92,
            "deepseek-chat": 0.88,
            "gpt-4o": 0.98,
            "gpt-4": 0.95,
            "gpt-4-turbo": 0.96,
            "gpt-3.5-turbo": 0.80,
            "glm-4": 0.90,
            "glm-4-plus": 0.93,
            "claude-3-opus": 0.99,
            "claude-3-sonnet": 0.90,
            "claude-3.5-sonnet": 0.93,
            "gemini-pro": 0.90,
            "gemini-1.5-pro": 0.93,
            "gemma:7b": 0.75,
            "gemma2:9b": 0.80,
            "codellama": 0.82,
            "starcoder2": 0.85,
            "starcoder": 0.80
        }
        self.history: Dict[str, Dict[str, float]] = {}
        self.weights = {
            "model": 0.4,
            "hardware": 0.2,
            "load": 0.15,
            "history": 0.15,
            "network": 0.1
        }
    
    def _get_model_score(self, model_name: str) -> float:
        """通过精确匹配或智能子串匹配获取模型分数"""
        model_lower = model_name.lower()
        
        # 1. 精确匹配
        if model_name in self.model_rankings:
            return self.model_rankings[model_name]
        
        # 2. 子串匹配（优先最长匹配）
        matched_scores = []
        for key, score in self.model_rankings.items():
            key_lower = key.lower()
            if key_lower in model_lower:
                matched_scores.append((len(key), score))
        
        if matched_scores:
            matched_scores.sort(reverse=True, key=lambda x: x[0])
            return matched_scores[0][1]
        
        # 3. 基于模型名称智能估算分数
        if "72b" in model_lower or "70b" in model_lower:
            return 0.90
        elif "34b" in model_lower or "32b" in model_lower:
            return 0.85
        elif "14b" in model_lower or "12b" in model_lower:
            return 0.80
        elif "9b" in model_lower or "8b" in model_lower or "7b" in model_lower:
            return 0.75
        elif "7b" in model_lower:
            return 0.72
        elif "6b" in model_lower or "5b" in model_lower or "4b" in model_lower:
            return 0.68
        elif "3b" in model_lower or "2b" in model_lower:
            return 0.60
        
        # 4. 通用大模型默认分数（云端API默认0.85，本地未知模型0.7）
        if "api" in model_lower or "remote" in model_lower or "openai" in model_lower or "dashscope" in model_lower:
            return 0.85
        else:
            return 0.70
    
    def assess(self, node_info: Dict[str, Any]) -> float:
        """
        计算综合能力分 0.0-1.0
        """
        score = 0.0
        
        # 1. 模型基准分
        model = node_info.get("model", "unknown")
        model_score = self._get_model_score(model)
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
        
        final_score = max(0.0, min(1.0, score))
        logger.debug(f"能力评估完成: model={model}, model_score={model_score:.2f}, total={final_score:.2f}")
        return final_score
    
    def _calc_hardware_score(self, node_info: Dict[str, Any]) -> float:
        """计算硬件分数"""
        score = 0.5
        gpu_mem = node_info.get("gpu_memory", 0)
        if gpu_mem >= 40:
            score = 1.0
        elif gpu_mem >= 24:
            score = 0.95
        elif gpu_mem >= 16:
            score = 0.9
        elif gpu_mem >= 12:
            score = 0.8
        elif gpu_mem >= 8:
            score = 0.7
        elif gpu_mem >= 6:
            score = 0.6
        elif gpu_mem >= 4:
            score = 0.5
        else:
            score = 0.35
        
        cpu_cores = node_info.get("cpu_cores", 4)
        if cpu_cores >= 32:
            score = min(1.0, score + 0.15)
        elif cpu_cores >= 16:
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
