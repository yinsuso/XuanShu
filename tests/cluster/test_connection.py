"""
测试 cluster/connection.py 模块

覆盖范围：
- evaluate_capability_simple()
"""

import pytest
from evolution.cluster.connection import evaluate_capability_simple


class TestEvaluateCapabilitySimple:
    """测试简易能力评估函数"""
    
    def test_unknown_model_returns_mid(self):
        node_info = {"model": "unknown-model"}
        score = evaluate_capability_simple(node_info)
        assert score == 0.5
    
    def test_ranked_model_scores(self):
        test_cases = [
            ("qwen2.5-coder:7b", 0.95),
            ("qwen2.5:7b", 0.85),
            ("llama3:8b", 0.80),
            ("phi3:3.8b", 0.60),
            ("mistral:7b", 0.70)
        ]
        for model, expected in test_cases:
            node_info = {"model": model}
            score = evaluate_capability_simple(node_info)
            assert score == expected, f"模型 {model} 应为 {expected}, 得到 {score}"
    
    def test_gpu_bonus_rtx_40_series(self):
        node_info = {"model": "qwen2.5-coder:7b", "gpu": "NVIDIA RTX 4090"}
        score = evaluate_capability_simple(node_info)
        assert score == 1.0  # capped at 1.0
    
    def test_gpu_bonus_rtx_30_20_series(self):
        # RTX 3070 -> 基础分0.95 + 0.05
        node_info = {"model": "qwen2.5-coder:7b", "gpu": "RTX 3070"}
        score = evaluate_capability_simple(node_info)
        assert score == 1.0  # capped at 1.0? 0.95+0.05=1.0 exactly
        
        # RTX 2060 -> 基础0.95 + 0.05 = 1.0
        node_info = {"model": "qwen2.5-coder:7b", "gpu": "RTX 2060"}
        score = evaluate_capability_simple(node_info)
        assert score == 1.0
    
    def test_no_gpu_no_bonus(self):
        node_info = {"model": "qwen2.5-coder:7b"}
        score = evaluate_capability_simple(node_info)
        assert score == 0.95
    
    def test_cap_score_capped_at_one(self):
        # 极端情况测试：顶级模型 + 最好GPU
        node_info = {"model": "qwen2.5-coder:7b", "gpu": "RTX 4090"}
        score = evaluate_capability_simple(node_info)
        assert score <= 1.0
