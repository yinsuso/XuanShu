"""
测试集群协作协议模块 (test_protocol.py)

覆盖范围：
- ClusterMessage 序列化/反序列化
- MessageType 枚举
- 便捷构造函数
- 能力评估简易函数
"""

import pytest
import time
import json
from evolution.cluster.protocol import (
    MessageType, ClusterMessage,
    create_capability_advertisement, create_task_assignment,
    create_auth_request, create_auth_response, create_leave_notification,
    create_heartbeat, validate_capability_payload, validate_task_assignment_payload,
)


class TestMessageType:
    """测试消息类型枚举"""
    def test_enum_values(self):
        assert MessageType.CAPABILITY_ADV.value == "capability_advertisement"
        assert MessageType.TASK_ASSIGN.value == "task_assignment"
        assert MessageType.AUTH_REQUEST.value == "authorization_request"
        assert MessageType.HEARTBEAT.value == "heartbeat"
        assert MessageType.LEAVE.value == "leave"


class TestClusterMessage:
    """测试消息基类"""
    
    def test_create_message(self):
        msg = ClusterMessage(
            type=MessageType.HEARTBEAT,
            payload={"node_id": "test-123"},
            timestamp=1234567890.0,
            seq_id=1
        )
        assert msg.type == MessageType.HEARTBEAT
        assert msg.payload["node_id"] == "test-123"
        assert msg.timestamp == 1234567890.0
        assert msg.seq_id == 1
    
    def test_serialize_deserialize_roundtrip(self):
        original = ClusterMessage(
            type=MessageType.CAPABILITY_ADV,
            payload={
                "node_id": "node-abc",
                "model": "qwen2.5-coder:7b",
                "gpu": "RTX 3080",
                "vram": 10,
                "mode": "auto",
                "nickname": "居士"
            }
        )
        serialized = original.serialize()
        recovered = ClusterMessage.deserialize(serialized)
        
        assert recovered.type == original.type
        assert recovered.payload == original.payload
        assert recovered.seq_id == original.seq_id
        # 时间戳可能有微小差异，但不应该差太多
        assert abs(recovered.timestamp - original.timestamp) < 1.0
    
    def test_serialize_produces_valid_json(self):
        msg = ClusterMessage(type=MessageType.TASK_ASSIGN, payload={"task_id": "t1"})
        serialized = msg.serialize()
        # 应该能解析回JSON
        parsed = json.loads(serialized)
        assert "type" in parsed
        assert "payload" in parsed
        assert parsed["type"] == "task_assignment"
    
    def test_deserialize_invalid_json(self):
        with pytest.raises(ValueError):
            ClusterMessage.deserialize(b"invalid json")
    
    def test_deserialize_missing_fields(self):
        data = json.dumps({"payload": {}}).encode('utf-8')
        with pytest.raises(ValueError):
            ClusterMessage.deserialize(data)
    
    def test_deserialize_invalid_type(self):
        data = json.dumps({"type": "invalid_type", "payload": {}}).encode('utf-8')
        with pytest.raises(ValueError):
            ClusterMessage.deserialize(data)


class TestConvenienceConstructors:
    """测试便捷构造函数"""
    
    def test_create_capability_advertisement(self):
        node_info = {
            "node_id": "node-1",
            "model": "qwen2.5:7b",
            "gpu": "GTX 1080",
            "vram": 8,
            "mode": "auto",
            "nickname": "居士"
        }
        msg = create_capability_advertisement(node_info)
        assert msg.type == MessageType.CAPABILITY_ADV
        payload = msg.payload
        assert payload["node_id"] == "node-1"
        assert payload["model"] == "qwen2.5:7b"
        assert payload["gpu"] == "GTX 1080"
        assert payload["vram"] == 8
        assert payload["mode"] == "auto"
        assert payload["nickname"] == "居士"
        assert "capability_score" in payload
    
    def test_create_task_assignment(self):
        msg = create_task_assignment(
            task_id="task-123",
            task_type="run_code",
            description="执行Python脚本",
            target_node_id="node-1",
            parameters={"code": "print('hello')"}
        )
        assert msg.type == MessageType.TASK_ASSIGN
        p = msg.payload
        assert p["task_id"] == "task-123"
        assert p["task_type"] == "run_code"
        assert p["description"] == "执行Python脚本"
        assert p["target_node"] == "node-1"
        assert p["parameters"]["code"] == "print('hello')"
    
    def test_create_auth_request(self):
        msg = create_auth_request(
            skill_name="delete_file",
            args={"path": "/tmp/test.txt"},
            risk_level="high",
            task_id="task-1"
        )
        assert msg.type == MessageType.AUTH_REQUEST
        p = msg.payload
        assert p["skill_name"] == "delete_file"
        assert p["args"]["path"] == "/tmp/test.txt"
        assert p["risk_level"] == "high"
        assert p["task_id"] == "task-1"
    
    def test_create_auth_response(self):
        msg = create_auth_response(
            request_seq_id=12345,
            decision="approve",
            reason="低风险操作"
        )
        assert msg.type == MessageType.AUTH_RESPONSE
        p = msg.payload
        assert p["original_seq"] == 12345
        assert p["decision"] == "approve"
        assert p["reason"] == "低风险操作"
    
    def test_create_leave_notification(self):
        msg = create_leave_notification(node_id="node-1", reason="user_request")
        assert msg.type == MessageType.LEAVE
        assert msg.payload["node_id"] == "node-1"
        assert msg.payload["reason"] == "user_request"
    
    def test_create_heartbeat(self):
        msg = create_heartbeat(node_id="node-1", 负载信息={"tasks": 2, "cpu": 0.3})
        assert msg.type == MessageType.HEARTBEAT
        assert msg.payload["node_id"] == "node-1"
        assert msg.payload["load"]["tasks"] == 2
        assert msg.payload["load"]["cpu"] == 0.3


class TestPayloadValidation:
    """测试载荷验证函数"""
    
    def test_validate_capability_payload_valid(self):
        payload = {
            "node_id": "n1",
            "model": "qwen2.5",
            "mode": "auto",
            "nickname": "居士"
        }
        assert validate_capability_payload(payload) is True
    
    def test_validate_capability_payload_missing(self):
        payload = {"node_id": "n1", "model": "qwen"}
        assert validate_capability_payload(payload) is False
    
    def test_validate_task_assignment_valid(self):
        payload = {
            "task_id": "t1",
            "task_type": "read_file",
            "target_node": "n1",
            "description": "读文件"
        }
        assert validate_task_assignment_payload(payload) is True
    
    def test_validate_task_assignment_missing(self):
        payload = {"task_id": "t1", "task_type": "read_file"}
        assert validate_task_assignment_payload(payload) is False


