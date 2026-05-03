"""
增强记忆系统 (Enhanced Memory System) - 适配统一架构版
本模块现在作为 MemoryCore 的高层封装，负责处理意识层(MD/JSON)与潜意识层(DB)的同步。
"""

import os
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from logger import logger
from config import PROJECT_ROOT, MAX_HISTORY_LENGTH
from memory_core import memory_core

# 意识层文件路径
CORE_MEMORY_FILE = os.path.join(PROJECT_ROOT, "data", "core_memory.json")
USER_PROFILE_FILE = os.path.join(PROJECT_ROOT, "data", "user_profile.json")
SOUL_FILE = os.path.join(PROJECT_ROOT, "SOUL.md")
MEMORY_FILE = os.path.join(PROJECT_ROOT, "MEMORY.md")

os.makedirs(os.path.dirname(CORE_MEMORY_FILE), exist_ok=True)

def parse_markdown_section(content: str, section_title: str) -> str:
    pattern = rf"##\\s*{re.escape(section_title)}[\\s\\S]*?(?=##\\s|\\Z)"
    match = re.search(pattern, content)
    if match:
        result = match.group(0).split('\\n', 1)[1].strip()
        return result
    return ""

class EnhancedMemorySystem:
    def __init__(self):
        # 意识层数据缓存（文件内容缓存，避免重复读取）
        self.soul_data = None
        self.memory_data = None
        self.user_profile = None
        self._soul_mtime = None
        self._memory_mtime = None
        
        # 加载意识层数据（带缓存）
        self._load_soul_file()
        self._load_memory_file()
        self._load_user_profile()
        
        # 潜意识层由 memory_core 单例管理
        self.db = memory_core

    def _load_soul_file(self) -> Dict[str, str]:
        """加载 SOUL.md 文件，支持缓存（按修改时间判断）"""
        if not os.path.exists(SOUL_FILE): 
            return {}
        
        # 检查缓存是否有效
        current_mtime = os.path.getmtime(SOUL_FILE)
        if self.soul_data is not None and self._soul_mtime == current_mtime:
            return self.soul_data
        
        try:
            with open(SOUL_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.soul_data = {
                "identity": parse_markdown_section(content, "1. 身份认同"),
                "instructions": parse_markdown_section(content, "2. 核心指令"),
                "capabilities": parse_markdown_section(content, "3. 能力边界"),
                "preferences": parse_markdown_section(content, "4. 输出格式偏好"),
                "workflow": parse_markdown_section(content, "5. 工作流程")
            }
            self._soul_mtime = current_mtime
            logger.debug(f"✅ SOUL.md 已加载（缓存更新）")
            return self.soul_data
        except Exception as e:
            logger.error(f"加载 SOUL.md 失败: {e}")
            return {}

    def _load_memory_file(self) -> Dict[str, str]:
        """加载 MEMORY.md 文件，支持缓存（按修改时间判断）"""
        if not os.path.exists(MEMORY_FILE): 
            return {}
        
        # 检查缓存是否有效
        current_mtime = os.path.getmtime(MEMORY_FILE)
        if self.memory_data is not None and self._memory_mtime == current_mtime:
            return self.memory_data
        
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.memory_data = {
                "system_context": parse_markdown_section(content, "1. 系统背景"),
                "key_facts": parse_markdown_section(content, "2. 关键事实"),
                "historical_knowledge": parse_markdown_section(content, "3. 历史经验"),
                "user_preferences": parse_markdown_section(content, "4. 用户偏好"),
            }
            self._memory_mtime = current_mtime
            logger.debug(f"✅ MEMORY.md 已加载（缓存更新）")
            return self.memory_data
        except Exception as e:
            logger.error(f"加载 MEMORY.md 失败: {e}")
            return {}

    def _load_user_profile(self) -> Dict[str, Any]:
        if os.path.exists(USER_PROFILE_FILE):
            try:
                with open(USER_PROFILE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {"preferences": {}, "interaction_style": "friendly", "history": []}

    def _save_user_profile(self):
        try:
            with open(USER_PROFILE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.user_profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户画像失败: {e}")

    def get_full_context(self, query: str, limit: int = 20) -> str:
        """
        构建完整的认知上下文：
        1. 意识层 (SOUL/MEMORY) -> 决定 "我是谁"
        2. 潜意识层 (DB) -> 提供 "我记得什么"
        """
        parts = []
        
        # 意识层：身份与核心禁令
        if self.soul_data.get("identity"):
            parts.append(f"【身份认同】\\n{self.soul_data['identity']}")
        
        # 潜意识层：核心记忆
        core_mem = self.db.get_all_core_memory()
        if core_mem:
            facts = "\\n".join([f"- {k}: {v}" for k, v in core_mem.items()])
            parts.append(f"【核心记忆】\\n{facts}")

        # 潜意识层：近期相关对话
        # 这里简化处理，直接获取最近历史
        history = self.db.get_conversation_history("current", limit=limit)
        if history:
            hist_text = "\\n".join([f"{h['role']}: {h['content']}" for h in history])
            parts.append(f"【近期对话】\\n{hist_text}")

        return "\\n\\n---\\n\\n".join(parts)

    def add_core_fact(self, key: str, value: str):
        """向潜意识写入关键事实"""
        self.db.add_core_memory(key, value)

    def set_user_preference(self, key: str, value: Any):
        """更新意识层的用户偏好"""
        self.user_profile["preferences"][key] = value
        self._save_user_profile()

    def clear_conversation(self, conversation_id: str = "current"):
        # SQLite 中通过删除记录实现
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM conversation_history WHERE conversation_id = ?", (conversation_id,))
            conn.commit()
