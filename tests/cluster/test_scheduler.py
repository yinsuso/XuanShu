"""
任务调度器单元测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolution.cluster.capability import CapabilityAssessor
from evolution.cluster.scheduler import TaskScheduler
from evolution.cluster.connection import ClusterNode

class MockNode:
    """模拟 ClusterNode 用于测试"""
    def __init__(self, node_id, model, load_cpu=0.0, load_memory=0.0, gpu_memory=0, cpu_cores=4):
        self.node_id = node_id
        self.model = model
        self.load_cpu = load_cpu
        self.load_memory = load_memory
        self.gpu_memory = gpu_memory
        self.cpu_cores = cpu_cores
        self.status = "online"
        self.pending_tasks = []

def test_scheduler_initialization():
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="capability")
    assert scheduler.strategy == "capability"
    assert scheduler.assessor == assessor
    print("✅ 调度器初始化正确")

def test_schedule_by_capability():
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="capability")
    
    nodes = [
        MockNode("node1", "qwen2.5-coder:7b", load_cpu=0.1, gpu_memory=24),
        MockNode("node2", "phi3:3.8b", load_cpu=0.2, gpu_memory=8),
    ]
    scheduler.update_node_pool(nodes)
    
    task = {"task_type": "code_generation", "description": "test"}
    selected = scheduler.schedule(task)
    
    assert selected is not None
    assert selected.node_id == "node1"  # 应选高分节点
    print(f"✅ 能力优先策略正确: 选择 {selected.node_id}")

def test_schedule_by_load_balance():
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="load_balance")
    
    nodes = [
        MockNode("node1", "qwen2.5-coder:7b", load_cpu=0.8, load_memory=0.7),
        MockNode("node2", "phi3:3.8b", load_cpu=0.2, load_memory=0.3),
    ]
    scheduler.update_node_pool(nodes)
    
    task = {"task_type": "text_writing", "description": "test"}
    selected = scheduler.schedule(task)
    
    assert selected is not None
    assert selected.node_id == "node2"  # 应选负载低的节点
    print(f"✅ 负载均衡策略正确: 选择 {selected.node_id}")

def test_schedule_by_affinity():
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="affinity")
    
    nodes = [
        MockNode("node1", "qwen2.5-coder:7b", load_cpu=0.3),
        MockNode("node2", "qwen2.5:7b", load_cpu=0.3),
    ]
    scheduler.update_node_pool(nodes)
    
    # code_generation 类型应优先选择 qwen2.5-coder
    task = {"task_type": "code_generation", "description": "test"}
    selected = scheduler.schedule(task)
    assert selected.node_id == "node1"
    print(f"✅ 亲和性策略正确: code_generation → qwen2.5-coder")
    
    # 未知类型应降级为能力优先
    task = {"task_type": "unknown_task", "description": "test"}
    selected = scheduler.schedule(task)
    assert selected is not None
    print(f"✅ 亲和性降级正常: 未知类型使用能力优先")

def test_filter_candidates():
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="capability")
    
    nodes = [
        MockNode("node1", "qwen2.5-coder:7b", load_cpu=0.9),  # 负载过高
        MockNode("node2", "phi3:3.8b", load_cpu=0.4),       # 正常
        MockNode("node3", "qwen2.5:7b", load_cpu=0.4),      # 正常
    ]
    scheduler.update_node_pool(nodes)
    
    candidates = scheduler._filter_candidates()
    assert len(candidates) == 2
    assert all(n.load_cpu < 0.8 for n in candidates)
    print(f"✅ 候选节点过滤正确: {len(candidates)} 个节点")

def test_get_stats():
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="capability")
    nodes = [MockNode("node1", "qwen2.5-coder:7b")]
    scheduler.update_node_pool(nodes)
    
    stats = scheduler.get_stats()
    assert "strategy" in stats
    assert "node_pool_size" in stats
    assert "available_nodes" in stats
    print(f"✅ 调度器统计信息正确: {stats}")

def run_tests():
    test_scheduler_initialization()
    test_schedule_by_capability()
    test_schedule_by_load_balance()
    test_schedule_by_affinity()
    test_filter_candidates()
    test_get_stats()
    print("\n🎉 所有调度器测试通过")

if __name__ == "__main__":
    run_tests()
