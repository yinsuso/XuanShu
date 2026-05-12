import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from config import PROJECT_ROOT
from logger import logger

CONVERSATIONS_DIR = os.path.join(PROJECT_ROOT, "data", "conversations")
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)


class ConversationType(Enum):
    STANDALONE = "standalone"
    COLLABORATION = "collaboration"


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
    conversation_type: ConversationType = ConversationType.STANDALONE

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
            "metadata": self.metadata,
            "conversation_type": self.conversation_type.value
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
        conv_type = ConversationType(data.get("conversation_type", ConversationType.STANDALONE.value))
        return cls(
            conversation_id=data["conversation_id"],
            title=data["title"],
            messages=[Message.from_dict(m) for m in data["messages"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
            conversation_type=conv_type
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

    def export_as_markdown(self) -> str:
        """导出为Markdown格式，即使某些消息模型没有回复也能完整导出"""
        lines = []
        lines.append(f"# {self.title}")
        lines.append(f"> 对话ID: {self.conversation_id}")
        lines.append(f"> 创建时间: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 更新时间: {self.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        for msg in self.messages:
            time_str = msg.timestamp.strftime('%H:%M:%S')
            if msg.role == MessageRole.USER:
                lines.append(f"## 🧑 用户 ({time_str})")
                lines.append("")
                lines.append(msg.content)
                lines.append("")
            elif msg.role == MessageRole.ASSISTANT:
                lines.append(f"## 🤖 助手 ({time_str})")
                lines.append("")
                lines.append(msg.content)
                lines.append("")
            elif msg.role == MessageRole.TOOL:
                lines.append(f"## 🔧 工具 `{msg.tool_name}` ({time_str})")
                lines.append("")
                if msg.content and len(msg.content) > 0:
                    lines.append("```")
                    lines.append(msg.content)
                    lines.append("```")
                else:
                    lines.append("(空输出)")
                lines.append("")
        
        return "\n".join(lines)

    def export_as_json(self) -> str:
        """导出为JSON格式，包含完整元数据和所有消息"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class ConversationManager:
    def __init__(self, conversation_id: Optional[str] = None):
        self.current_conversation: Optional[Conversation] = None
        self.conversations: Dict[str, Conversation] = {}
        self._standalone_current_id: Optional[str] = None
        self._collab_current_id: Optional[str] = None
        if conversation_id:
            self.load_conversation(conversation_id)
        else:
            self.new_conversation()

    def new_conversation(self, initial_title: str = "新对话", conversation_type: ConversationType = ConversationType.STANDALONE) -> str:
        conversation_id = str(uuid.uuid4())
        self.current_conversation = Conversation(
            conversation_id=conversation_id,
            title=initial_title,
            messages=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            conversation_type=conversation_type
        )
        self.conversations[conversation_id] = self.current_conversation
        
        if conversation_type == ConversationType.STANDALONE:
            self._standalone_current_id = conversation_id
            logger.info(f"创建单机模式新对话: {conversation_id}")
        else:
            self._collab_current_id = conversation_id
            logger.info(f"创建协作模式新对话: {conversation_id}")
        
        return conversation_id

    def switch_mode(self, conversation_type: ConversationType):
        """切换到指定模式的对话，两套对话完全隔离"""
        if conversation_type == ConversationType.STANDALONE:
            if self._standalone_current_id and self.load_conversation(self._standalone_current_id):
                logger.info(f"切换到单机模式对话: {self._standalone_current_id[:8]}...")
            else:
                self.new_conversation(initial_title="单机对话", conversation_type=ConversationType.STANDALONE)
        else:
            if self._collab_current_id and self.load_conversation(self._collab_current_id):
                logger.info(f"切换到协作模式对话: {self._collab_current_id[:8]}...")
            else:
                self.new_conversation(initial_title="协作对话", conversation_type=ConversationType.COLLABORATION)

    def load_conversation(self, conversation_id: str) -> bool:
        filepath = os.path.join(CONVERSATIONS_DIR, f"{conversation_id}.json")
        logger.debug(f"尝试加载对话: {conversation_id}, 文件路径: {filepath}")
        
        if os.path.exists(filepath):
            logger.debug(f"对话文件存在")
            try:
                conversation = Conversation.load(conversation_id)
                if conversation:
                    message_count = len(conversation.messages)
                    self.current_conversation = conversation
                    self.conversations[conversation_id] = conversation
                    logger.info(f"✅ 成功加载对话: {conversation_id}, 消息数: {message_count}")
                    return True
            except Exception as e:
                logger.error(f"加载对话失败: {e}", exc_info=True)
        
        logger.info(f"❌ 对话文件不存在或加载失败")
        self.current_conversation = None
        return False

    def load_conversation_or_create(self, conversation_id: str) -> bool:
        """加载对话，如果不存在则创建新对话"""
        if not self.load_conversation(conversation_id):
            logger.info(f"创建新对话: {conversation_id}")
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
            self.update_title()

    def add_tool_message(self, content: str, tool_name: str, tool_args: Dict[str, Any] = None):
        if self.current_conversation:
            self.current_conversation.add_message(MessageRole.TOOL, content, tool_name, tool_args)

    def _generate_title_by_model(self):
        """调用模型生成对话标题"""
        try:
            from model_providers import config_manager, call_model
            
            config = config_manager.current_config
            if not config:
                config_manager.load_configs()
                config = config_manager.current_config
                if not config:
                    return None
            
            history_text = self.current_conversation.get_history_as_text(limit=10)
            prompt = f"""请为以下对话生成一个简洁的中文标题（不超过20个字符）：

{history_text}

标题："""
            
            response = call_model(config=config, prompt=prompt, system_prompt="你是一个专业的标题生成器，擅长为对话生成简洁准确的标题。")
            title = response.strip()
            
            if title and len(title) > 0:
                if len(title) > 30:
                    title = title[:30] + "..."
                return title
        except Exception as e:
            logger.error(f"生成对话标题失败: {e}")
        
        return None

    def update_title(self):
        if self.current_conversation and len(self.current_conversation.messages) > 0:
            messages = self.current_conversation.messages
            user_count = sum(1 for m in messages if m.role == MessageRole.USER)
            
            # 对话进行3轮后（用户消息达到3条），尝试使用模型生成标题
            if user_count >= 3:
                generated_title = self._generate_title_by_model()
                if generated_title and generated_title != "新对话":
                    self.current_conversation.title = generated_title
                    return
            
            # 回退：使用第一条用户消息作为标题
            first_user_msg = next(
                (m for m in messages if m.role == MessageRole.USER),
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

    def list_conversations(self, limit: int = 20, conversation_type: Optional[ConversationType] = None) -> List[Dict[str, Any]]:
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
                    conv_type_str = data.get("conversation_type", ConversationType.STANDALONE.value)
                    
                    if conversation_type:
                        if conv_type_str != conversation_type.value:
                            continue
                    
                    result.append({
                        "conversation_id": data["conversation_id"],
                        "title": data["title"],
                        "updated_at": data["updated_at"],
                        "message_count": len(data.get("messages", [])),
                        "conversation_type": conv_type_str
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
        
        standalone_list = _global_conversation_manager.list_conversations(limit=1, conversation_type=ConversationType.STANDALONE)
        collab_list = _global_conversation_manager.list_conversations(limit=1, conversation_type=ConversationType.COLLABORATION)
        
        if standalone_list:
            _global_conversation_manager._standalone_current_id = standalone_list[0]["conversation_id"]
        if collab_list:
            _global_conversation_manager._collab_current_id = collab_list[0]["conversation_id"]
        
        _global_conversation_manager.try_load_last_conversation()
    return _global_conversation_manager

# 保持向后兼容的别名
conversation_manager = get_global_conversation_manager()