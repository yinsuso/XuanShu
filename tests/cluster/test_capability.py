"""
能力评估器单元测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolution.cluster.capability import CapabilityAssessor

def test_assessor_initialization():
    assessor = CapabilityAssessor()
    assert assessor.weights["model"] == 0.4
    assert assessor.weights["hardware"] == 0.2
    assert assessor.weights["load"] == 0.15
    assert assessor.weights["history"] == 0.15
    assert assessor.weights["network"] == 0.1
    print("✅ 评估器初始化正确")

def test_assess_high_end_gpu():
    assessor = CapabilityAssessor()
    node_info = {
        "node_id": "test-node-1",
        "model": "qwen2.5-coder:7b",
        "gpu_memory": 24,
        "cpu_cores": 16,
        "load_cpu": 0.1,
        "load_memory": 0.1
    }
    score = assessor.assess(node_info)
    assert 0.9 <= score <= 1.0, f"高端配置得分应在0.9-1.0之间，实际: {score}"
    print(f"✅ 高端配置评估正确: {score:.3f}")

def test_assess_low_end():
    assessor = CapabilityAssessor()
    node_info = {
        "node_id": "test-node-2",
        "model": "unknown",
        "gpu_memory": 0,
        "cpu_cores": 2,
        "load_cpu": 0.9,
        "load_memory": 0.9
    }
    score = assessor.assess(node_info)
    assert 0.0 <= score <= 0.6, f"低端配置得分应在0.0-0.6之间，实际: {score}"
    print(f"✅ 低端配置评估正确: {score:.3f}")

def test_record_task_outcome():
    assessor = CapabilityAssessor()
    node_id = "test-node"
    # 初始应无记录
    assert node_id not in assessor.history
    # 记录一次成功
    assessor.record_task_outcome(node_id, True, 1.5)
    assert node_id in assessor.history
    history = assessor.history[node_id]
    assert history["success_rate"] == 0.8 * 0.9 + 1.0 * 0.1  # 0.82
    assert history["samples"] == 1
    print("✅ 任务结果记录正确")

def test_update_model_rankings():
    assessor = CapabilityAssessor()
    new_rankings = {"test-model:1b": 0.3}
    assessor.update_model_rankings(new_rankings)
    assert assessor.model_rankings["test-model:1b"] == 0.3
    print("✅ 模型排行榜更新正确")

def run_tests():
    test_assessor_initialization()
    test_assess_high_end_gpu()
    test_assess_low_end()
    test_record_task_outcome()
    test_update_model_rankings()
    print("\n🎉 所有能力评估器测试通过")

if __name__ == "__main__":
    run_tests()
