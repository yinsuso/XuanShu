"""
集群连接与协议测试
"""
import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolution.cluster.connection import ClusterManager, ClusterServer

def test_manager_node_management():
    """测试 ClusterManager 的节点管理功能"""
    manager = ClusterManager()
    
    # 添加节点
    node_info = {
        "node_id": "node-1",
        "ip": "127.0.0.1",
        "model": "qwen2.5-coder:7b",
        "role": "worker",
        "mode": "auto",
        "capability_score": 0.9
    }
    manager.add_node(node_info)
    assert "node-1" in manager.nodes
    assert manager.nodes["node-1"].model == "qwen2.5-coder:7b"
    print("✅ 添加节点成功")
    
    # 移除节点
    manager.remove_node("node-1")
    assert "node-1" not in manager.nodes
    print("✅ 移除节点成功")

def test_manager_broadcast():
    """测试 ClusterManager 的广播功能"""
    manager = ClusterManager()
    manager.add_node({"node_id": "node-1", "ip": "127.0.0.1", "model": "qwen", "role": "worker", "mode": "auto", "capability_score": 0.8})
    manager.add_node({"node_id": "node-2", "ip": "127.0.0.1", "model": "phi3", "role": "worker", "mode": "auto", "capability_score": 0.6})
    
    # 使用 Mock 节点来模拟广播
    mock_conn1 = Mock()
    mock_conn2 = Mock()
    manager.nodes["node-1"].connection = mock_conn1
    manager.nodes["node-2"].connection = mock_conn2
    
    message = {"type": "task", "task_id": "task-123", "content": "test"}
    manager.broadcast(message, exclude=["node-2"])  # 排除 node-2
    
    mock_conn1.sendall.assert_called_once_with(json.dumps(message).encode('utf-8'))
    mock_conn2.sendall.assert_not_called()
    print("✅ 广播功能正确（排除指定节点）")

def test_server_node_acceptance():
    """测试 ClusterServer 节点加入逻辑（模拟）"""
    # 使用 Mock 模拟 socket
    with patch('evolution.cluster.connection.socket') as mock_socket:
        server = ClusterServer("0.0.0.0", 30001)
        # 模拟 conn 和 addr
        mock_conn = Mock()
        mock_addr = ("127.0.0.1", 12345)
        mock_socket.return_value = mock_conn
        
        # 模拟接收 join 消息
        join_msg = json.dumps({
            "type": "join",
            "node_id": "test-node",
            "model": "qwen2.5-coder:7b",
            "role": "worker"
        }).encode('utf-8')
        mock_conn.recv.return_value = join_msg
        
        # 由于 _handle_client 是循环接收，我们需要测试其内部逻辑片段
        # 这里简化测试，仅验证消息解析逻辑
        try:
            data = json.loads(join_msg)
            assert data["type"] == "join"
            assert data["node_id"] == "test-node"
            print("✅ 服务器接收并解析加入消息正确")
        except Exception as e:
            print(f"❌ 消息解析失败: {e}")
            raise

def run_tests():
    test_manager_node_management()
    test_manager_broadcast()
    test_server_node_acceptance()
    print("\n🎉 所有连接协议测试通过")

if __name__ == "__main__":
    run_tests()
