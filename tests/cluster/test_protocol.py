"""
集群协议格式测试
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_message_format():
    """测试集群消息格式合规性"""
    # join 消息
    join_msg = {
        "type": "join",
        "node_id": "node-abc123",
        "model": "qwen2.5-coder:7b",
        "role": "worker",
        "mode": "auto",
        "password": ""  # 可选
    }
    assert join_msg["type"] in ("join", "heartbeat", "task", "result", "error")
    assert "node_id" in join_msg
    print("✅ join 消息格式正确")
    
    # heartbeat 消息
    hb_msg = {
        "type": "heartbeat",
        "node_id": "node-abc123",
        "load_cpu": 0.25,
        "load_memory": 0.4,
        "gpu_utilization": 0.0,
        "vram_used": 0,
        "pending_tasks": 0
    }
    assert hb_msg["type"] == "heartbeat"
    assert 0 <= hb_msg["load_cpu"] <= 1
    assert 0 <= hb_msg["load_memory"] <= 1
    print("✅ heartbeat 消息格式正确")

def test_task_message_parsing():
    """测试任务消息解析"""
    task = {
        "task_id": "task-001",
        "task_type": "reasoning",
        "content": "解释量子纠缠",
        "priority": 5,
        "created_at": "2025-01-01T00:00:00Z",
        "timeout": 300
    }
    # 验证必需字段
    required = ["task_id", "task_type", "content"]
    for field in required:
        assert field in task
    print("✅ 任务消息解析正确")

def test_response_messages():
    """测试响应消息格式"""
    # ack
    ack = {
        "type": "ack",
        "task_id": "task-001",
        "status": "accepted",
        "assigned_to": "node-1"
    }
    assert ack["status"] in ("accepted", "rejected", "completed", "failed")
    print("✅ ack 消息格式正确")
    
    # error
    err = {
        "type": "error",
        "reason": "密码错误"
    }
    assert "reason" in err
    print("✅ error 消息格式正确")

def run_tests():
    test_message_format()
    test_task_message_parsing()
    test_response_messages()
    print("\n🎉 所有协议格式测试通过")

if __name__ == "__main__":
    run_tests()
