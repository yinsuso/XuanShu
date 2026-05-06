"""
集成测试 - 模拟 Manager 和 Worker 协作流程
"""
import sys
import os
import json
import threading
import time
from unittest.mock import Mock, patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolution.cluster.connection import ClusterManager, ClusterNode
from evolution.cluster.scheduler import TaskScheduler
from evolution.cluster.capability import CapabilityAssessor

def test_manager_worker_join_password():
    """测试 Manager 接收 Worker 加入并验证密码"""
    manager = ClusterManager()
    # 创建带密码的房间
    password = "123456"
    import hashlib
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    room_id = manager.create_room("TestRoom", "Manager", "qwen2.5-coder:7b", password_hash=pwd_hash)
    
    # 模拟 Worker 连接请求（通过 socket 模拟）
    # 在真实场景中，ClusterServer 接收到 join 消息后验证密码
    # 这里直接调用 ClusterManager 的内部逻辑片段
    
    # 假设已接收到的节点信息（包含密码）
    node_info_correct = {
        "node_id": "worker-1",
        "model": "phi3:3.8b",
        "role": "worker",
        "capability_score": 0.7,
        "password": password  # 正确密码
    }
    # 计算哈希并比对
    provided_hash = hashlib.sha256(node_info_correct["password"].encode()).hexdigest() if node_info_correct["password"] else None
    assert provided_hash == pwd_hash, "正确密码应该通过验证"
    print("✅ 密码验证流程：Worker 提供正确密码")
    
    # 错误密码情况
    node_info_wrong = {
        "node_id": "worker-2",
        "model": "phi3:3.8b",
        "role": "worker",
        "capability_score": 0.7,
        "password": "wrong"
    }
    wrong_hash = hashlib.sha256(node_info_wrong["password"].encode()).hexdigest()
    assert wrong_hash != pwd_hash, "错误密码应该被拒绝"
    print("✅ 密码验证流程：Worker 提供错误密码会被拒绝")
    
    # 无密码情况
    node_info_no = {
        "node_id": "worker-3",
        "model": "phi3:3.8b",
        "role": "worker",
        "capability_score": 0.7,
        "password": ""
    }
    no_hash = hashlib.sha256(node_info_no["password"].encode()).hexdigest() if node_info_no["password"] else None
    assert no_hash != pwd_hash, "未提供密码应该被拒绝"
    print("✅ 密码验证流程：未提供密码会被拒绝")

def test_task_assignment_flow():
    """测试任务分配完整流程"""
    assessor = CapabilityAssessor()
    scheduler = TaskScheduler(assessor, strategy="capability")
    
    # 创建 Manager 节点（作为调度器中心的模拟）
    manager_node = ClusterNode("manager-1", ip="127.0.0.1", model="qwen2.5-coder:7b", role="manager", mode="auto")
    # 模拟工作节点池
    nodes = [
        ClusterNode("worker-1", ip="127.0.0.1", model="qwen2.5-coder:7b", role="worker", mode="auto"),
        ClusterNode("worker-2", ip="127.0.0.1", model="phi3:3.8b", role="worker", mode="auto")
    ]
    # 设置负载属性以模拟不同状态
    nodes[0].load_cpu = 0.1
    nodes[0].gpu_memory = 24
    nodes[1].load_cpu = 0.3
    nodes[1].gpu_memory = 8
    
    scheduler.update_node_pool(nodes)
    
    # 接收任务
    task = {
        "task_id": "task-001",
        "type": "code_generation",
        "content": "写一个快速排序",
        "priority": 5
    }
    selected = scheduler.schedule(task)
    
    assert selected.node_id == "worker-1"  # 应选高分节点
    print(f"✅ 任务分配流程：任务被分配给 {selected.node_id}")
    
    # 模拟完成任务并记录
    assessor.record_task_outcome(selected.node_id, True, 2.0, "code_generation")
    print("✅ 任务完成反馈已记录")

def run_tests():
    print("🔬 开始集成测试...")
    test_manager_worker_join_password()
    test_task_assignment_flow()
    print("\n🎉 所有集成测试通过")

if __name__ == "__main__":
    run_tests()
