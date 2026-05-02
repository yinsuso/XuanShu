import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from .config import PROJECT_ROOT
from .logger import logger

CONVERSATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "conversations")
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    timestamp: datetime
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "tool_args": self.tool_args
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args")
        )


@dataclass
class Conversation:
    conversation_id: str
    title: str
    messages: List[Message]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def add_message(self, role: MessageRole, content: str, tool_name: str = None, tool_args: Dict[str, Any] = None):
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            tool_name=tool_name,
            tool_args=tool_args
        )
        self.messages.append(message)
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
            "metadata": self.metadata
        }

    def save(self):
        filepath = os.path.join(CONVERSATIONS_DIR, f"{self.conversation_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.debug(f"对话已保存: {filepath}")

    @classmethod
    def load(cls, conversation_id: str) -> Optional['Conversation']:
        filepath = os.path.join(CONVERSATIONS_DIR, f"{conversation_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        return cls(
            conversation_id=data["conversation_id"],
            title=data["title"],
            messages=[Message.from_dict(m) for m in data["messages"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {})
        )

    def get_history(self, limit: int = 20) -> List[Message]:
        return self.messages[-limit:]

    def get_history_as_text(self, limit: int = 20) -> str:
        history = []
        for msg in self.get_history(limit):
            if msg.role == MessageRole.USER:
                history.append(f"用户: {msg.content}")
            elif msg.role == MessageRole.ASSISTANT:
                history.append(f"助手: {msg.content}")
            elif msg.role == MessageRole.TOOL:
                history.append(f"工具[{msg.tool_name}]: {msg.content}")
        return "\n".join(history)


class ConversationManager:
    def __init__(self, conversation_id: Optional[str] = None):
        self.current_conversation: Optional[Conversation] = None
        self.conversations: Dict[str, Conversation] = {}
        if conversation_id:
            self.load_conversation(conversation_id)
        else:
            self.new_conversation()

    def new_conversation(self, initial_title: str = "新对话") -> str:
        conversation_id = str(uuid.uuid4())
        self.current_conversation = Conversation(
            conversation_id=conversation_id,
            title=initial_title,
            messages=[],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        self.conversations[conversation_id] = self.current_conversation
        logger.info(f"创建新对话: {conversation_id}")
        return conversation_id

    def load_conversation(self, conversation_id: str) -> bool:
        filepath = os.path.join(CONVERSATIONS_DIR, f"{conversation_id}.json")
        logger.debug(f"尝试加载对话: {conversation_id}, 文件路径: {filepath}")
        
        if os.path.exists(filepath):
            logger.debug(f"对话文件存在")
            conversation = Conversation.load(conversation_id)
            if conversation:
                message_count = len(conversation.messages)
                self.current_conversation = conversation
                self.conversations[conversation_id] = conversation
                logger.info(f"✅ 成功加载对话: {conversation_id}, 消息数: {message_count}")
                return True
        
        logger.info(f"❌ 对话文件不存在或加载失败，创建新对话: {conversation_id}")
        self.current_conversation = Conversation(
            conversation_id=conversation_id,
            title="新对话",
            messages=[],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        self.conversations[conversation_id] = self.current_conversation
        return True

    def save_current(self):
        if self.current_conversation:
            self.current_conversation.save()
            logger.debug(f"对话已保存: {self.current_conversation.conversation_id}")

    def add_user_message(self, content: str):
        if self.current_conversation:
            self.current_conversation.add_message(MessageRole.USER, content)
            self.update_title()

    def add_assistant_message(self, content: str):
        if self.current_conversation:
            self.current_conversation.add_message(MessageRole.ASSISTANT, content)

    def add_tool_message(self, content: str, tool_name: str, tool_args: Dict[str, Any] = None):
        if self.current_conversation:
            self.current_conversation.add_message(MessageRole.TOOL, content, tool_name, tool_args)

    def update_title(self):
        if self.current_conversation and len(self.current_conversation.messages) > 0:
            first_user_msg = next(
                (m for m in self.current_conversation.messages if m.role == MessageRole.USER),
                None
            )
            if first_user_msg:
                title = first_user_msg.content[:50]
                if len(first_user_msg.content) > 50:
                    title += "..."
                self.current_conversation.title = title

    def get_history_text(self, limit: int = 20) -> str:
        if self.current_conversation:
            return self.current_conversation.get_history_as_text(limit)
        return ""

    def list_conversations(self, limit: int = 20) -> List[Dict[str, Any]]:
        files = sorted(
            [f for f in os.listdir(CONVERSATIONS_DIR) if f.endswith('.json')],
            key=lambda x: os.path.getmtime(os.path.join(CONVERSATIONS_DIR, x)),
            reverse=True
        )
        result = []
        for f in files[:limit]:
            filepath = os.path.join(CONVERSATIONS_DIR, f)
            try:
                with open(filepath, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    result.append({
                        "conversation_id": data["conversation_id"],
                        "title": data["title"],
                        "updated_at": data["updated_at"],
                        "message_count": len(data.get("messages", []))
                    })
            except:
                pass
        return result

    def delete_conversation(self, conversation_id: str):
        filepath = os.path.join(CONVERSATIONS_DIR, f"{conversation_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            if conversation_id in self.conversations:
                del self.conversations[conversation_id]
            if self.current_conversation and self.current_conversation.conversation_id == conversation_id:
                self.current_conversation = None
            logger.info(f"删除对话: {conversation_id}")

    def clear_conversation(self) -> str:
        """
        清空当前对话：创建新对话文件，保留旧文件。
        返回新对话 ID。
        """
        if self.current_conversation:
            # 1. 保存旧对话（可选：标记为归档）
            # self.current_conversation.metadata['archived'] = True
            # self.save_current()
            
            # 2. 创建新对话
            new_id = self.new_conversation(initial_title="新对话")
            
            # 3. 切换当前会话
            self.current_conversation = self.conversations[new_id]
            
            logger.info(f"✅ 已创建新对话并清空：{new_id[:8]}...")
            return new_id
        return None

    def try_load_last_conversation(self) -> bool:
        """尝试加载最近的对话，如果存在的话"""
        convs = self.list_conversations(limit=1)
        if convs:
            last_conv_id = convs[0]["conversation_id"]
            if self.load_conversation(last_conv_id):
                logger.info(f"自动加载最近对话: {last_conv_id[:8]}...")
                return True
        return False


# 保持向后兼容的全局单例实例
_global_conversation_manager = None

def get_global_conversation_manager() -> ConversationManager:
    global _global_conversation_manager
    if _global_conversation_manager is None:
        _global_conversation_manager = ConversationManager()
        _global_conversation_manager.try_load_last_conversation()
    return _global_conversation_manager

# 保持向后兼容的别名
conversation_manager = get_global_conversation_manager()