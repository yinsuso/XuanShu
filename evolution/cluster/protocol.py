"""
集群协作协议定义 - 玄枢 XuanShu
统一消息格式、序列化与反序列化机制
"""

import json
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


class MessageType(Enum):
    """集群消息类型枚举"""
    CAPABILITY_ADV = "capability_advertisement"   # 能力广播（成员加入时）
    TASK_ASSIGN = "task_assignment"               # 任务分配（房主→成员）
    TASK_UPDATE = "task_update"                   # 进度更新（成员→房主）
    AUTH_REQUEST = "authorization_request"        # 授权请求（自动模式）
    AUTH_RESPONSE = "authorization_response"      # 授权响应（房主→成员）
    HEARTBEAT = "heartbeat"                       # 心跳
    LEAVE = "leave"                               # 退出通知
    ROOM_INFO = "room_info"                       # 房间信息查询


@dataclass
class ClusterMessage:
    """集群消息基类"""
    type: MessageType
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    seq_id: Optional[int] = None

    def __post_init__(self):
        if self.seq_id is None:
            # 使用时间戳微秒部分作为简单序列号
            self.seq_id = int(time.time() * 1000000) % (2**32)

    def serialize(self) -> bytes:
        """
        序列化为字节流

        Returns:
            bytes: JSON格式的UTF-8编码字节
        """
        data = {
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "seq_id": self.seq_id
        }
        return json.dumps(data, ensure_ascii=False).encode('utf-8')

    @classmethod
    def deserialize(cls, data: bytes) -> 'ClusterMessage':
        """
        从字节流反序列化为消息对象

        Args:
            data: JSON格式的UTF-8编码字节

        Returns:
            ClusterMessage: 解析后的消息对象

        Raises:
            json.JSONDecodeError: JSON格式错误
            ValueError: 缺少必要字段或类型无效
        """
        try:
            obj = json.loads(data.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise ValueError(f"无效的JSON数据: {e}") from e

        # 验证必需字段
        required = ["type", "payload"]
        for field in required:
            if field not in obj:
                raise ValueError(f"缺少必需字段: {field}")

        # 类型转换
        try:
            msg_type = MessageType(obj["type"])
        except ValueError as e:
            raise ValueError(f"无效的消息类型: {obj['type']}") from e

        return cls(
            type=msg_type,
            payload=obj["payload"],
            timestamp=obj.get("timestamp", time.time()),
            seq_id=obj.get("seq_id")
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（便于日志记录）"""
        return {
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "seq_id": self.seq_id
        }


# 便捷构造函数 =============================================================

def create_capability_advertisement(node_info: Dict[str, Any]) -> ClusterMessage:
    """
    创建能力广播消息

    Args:
        node_info: 节点信息字典，应包含：
            - node_id: 节点唯一标识
            - model: 当前模型名称
            - gpu: GPU型号（可选）
            - vram: 显存大小GB（可选）
            - mode: "auto" 或 "manual"
            - nickname: 花名/显示名称

    Returns:
        ClusterMessage: 能力广播消息
    """
    return ClusterMessage(
        type=MessageType.CAPABILITY_ADV,
        payload={
            "node_id": node_info["node_id"],
            "model": node_info.get("model", "unknown"),
            "gpu": node_info.get("gpu"),
            "vram": node_info.get("vram"),
            "mode": node_info.get("mode", "auto"),
            "nickname": node_info.get("nickname", "Unnamed"),
            "capability_score": node_info.get("capability_score", 0.5)
        }
    )


def create_task_assignment(task_id: str, task_type: str, description: str,
                          parameters: Dict[str, Any] = None) -> ClusterMessage:
    """
    创建任务分配消息 - 简化版

    Args:
        task_id: 任务唯一标识
        task_type: 任务类型（如 "run_code", "read_file"）
        description: 任务描述
        parameters: 任务参数（可选）

    Returns:
        ClusterMessage: 任务分配消息
    """
    return ClusterMessage(
        type=MessageType.TASK_ASSIGN,
        payload={
            "task_id": task_id,
            "task_type": task_type,
            "description": description,
            "parameters": parameters or {},
            "assigned_at": time.time()
        }
    )


def create_auth_request(skill_name: str, args: Dict[str, Any],
                       risk_level: str, task_id: str = None) -> ClusterMessage:
    """
    创建授权请求消息（自动模式成员 → 房主）

    Args:
        skill_name: 技能名称
        args: 技能参数
        risk_level: 风险等级 ("low", "medium", "high", "critical")
        task_id: 关联任务ID（可选）

    Returns:
        ClusterMessage: 授权请求消息
    """
    return ClusterMessage(
        type=MessageType.AUTH_REQUEST,
        payload={
            "skill_name": skill_name,
            "args": args,
            "risk_level": risk_level,
            "task_id": task_id,
            "requested_at": time.time()
        }
    )


def create_auth_response(request_seq_id: int, decision: str,
                        reason: str = None) -> ClusterMessage:
    """
    创建授权响应消息（房主 → 成员）

    Args:
        request_seq_id: 原始请求的消息seq_id（用于关联）
        decision: "approve" 或 "reject"
        reason: 决策原因（可选）

    Returns:
        ClusterMessage: 授权响应消息
    """
    return ClusterMessage(
        type=MessageType.AUTH_RESPONSE,
        payload={
            "original_seq": request_seq_id,
            "decision": decision,
            "reason": reason,
            "decided_at": time.time()
        }
    )


def create_leave_notification(node_id: str, reason: str = "user_request") -> ClusterMessage:
    """
    创建退出通知消息

    Args:
        node_id: 退出节点ID
        reason: 退出原因

    Returns:
        ClusterMessage: 退出通知
    """
    return ClusterMessage(
        type=MessageType.LEAVE,
        payload={
            "node_id": node_id,
            "reason": reason,
            "left_at": time.time()
        }
    )


def create_heartbeat(node_id: str,负载信息: Dict[str, Any] = None) -> ClusterMessage:
    """
    创建心跳消息

    Args:
        node_id: 节点ID
        负载信息: 当前负载信息（如任务数、CPU使用率等，可选）

    Returns:
        ClusterMessage: 心跳消息
    """
    return ClusterMessage(
        type=MessageType.HEARTBEAT,
        payload={
            "node_id": node_id,
            "load": 负载信息 or {},
            "sent_at": time.time()
        }
    )


def create_task_update(task_id: str, status: str, result: Any = None, error: str = None) -> ClusterMessage:
    """
    创建任务状态更新消息

    Args:
        task_id: 任务ID
        status: 任务状态 ("completed", "failed", 等)
        result: 执行结果（可选）
        error: 错误信息（可选）

    Returns:
        ClusterMessage: 任务状态更新消息
    """
    return ClusterMessage(
        type=MessageType.TASK_UPDATE,
        payload={
            "task_id": task_id,
            "status": status,
            "result": result,
            "error": error,
            "reported_at": time.time()
        }
    )


# 工具函数 =============================================================

def generate_node_id() -> str:
    """生成唯一节点ID"""
    return str(uuid.uuid4())


def validate_capability_payload(payload: Dict[str, Any]) -> bool:
    """
    验证能力广播载荷的完整性

    Args:
        payload: CAPABILITY_ADV 消息的 payload

    Returns:
        bool: 验证是否通过
    """
    required = ["node_id", "model", "mode", "nickname"]
    return all(k in payload for k in required)


def validate_task_assignment_payload(payload: Dict[str, Any]) -> bool:
    """
    验证任务分配载荷的完整性

    Args:
        payload: TASK_ASSIGN 消息的 payload

    Returns:
        bool: 验证是否通过
    """
    required = ["task_id", "task_type", "target_node", "description"]
    return all(k in payload for k in required)
