"""
上下文清理工具
负责在角色切换时，清理历史消息，只保留必要的摘要。
"""
from typing import List, Dict, Any, Optional
from logger import logger


class ContextCleaner:
    """
    上下文清理器
    用于在角色切换时，清理历史消息，只保留必要的摘要。
    """
    
    def __init__(self, max_summary_tokens: int = 500):
        """
        :param max_summary_tokens: 摘要最大 token 数（用于截断）
        """
        self.max_summary_tokens = max_summary_tokens
    
    def clean_and_summarize(
        self, 
        history: List[Dict[str, Any]], 
        keep_last_n: int = 2
    ) -> List[Dict[str, Any]]:
        """
        清理历史消息，只保留最后 N 条，并生成摘要。
        :param history: 历史消息列表
        :param keep_last_n: 保留最后 N 条消息
        :return: 清理后的消息列表（包含摘要）
        """
        if not history:
            return []
        
        # 1. 保留最后 N 条消息
        kept_messages = history[-keep_last_n:] if len(history) > keep_last_n else history
        
        # 2. 生成摘要（若历史过长）
        if len(history) > keep_last_n:
            summary = self._generate_summary(history[:-keep_last_n])
            # 在开头插入摘要消息
            summary_msg = {
                "role": "system",
                "content": f"[上下文摘要] 之前对话摘要：{summary}",
                "timestamp": history[0].get("timestamp")
            }
            kept_messages = [summary_msg] + kept_messages
        
        logger.debug(f"🧹 上下文已清理：原{len(history)}条 → 现{len(kept_messages)}条")
        return kept_messages
    
    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        生成历史消息摘要（简化版：仅提取关键信息）。
        实际应用中，可调用模型生成更智能的摘要。
        """
        parts = []
        for msg in messages[-5:]:  # 只取最后 5 条生成摘要
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]  # 截断
            parts.append(f"{role}: {content}...")
        
        return " | ".join(parts)
    
    def truncate_to_tokens(self, text: str, max_tokens: int = 500) -> str:
        """
        简单截断文本到指定 token 数（近似：1 token ≈ 4 字符）。
        """
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."