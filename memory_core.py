"""
统一记忆核心模块 (Unified Memory Core)
优先使用 SQLite，当 _sqlite3 模块不可用时自动降级到 JSON 文件存储。
兼容 Windows/Linux/Mac 全平台，无需依赖系统级 SQLite 库。
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

from config import MEMORY_DB_PATH, PROJECT_ROOT
from logger import logger

# 检测 sqlite3 可用性
_SQLITE_AVAILABLE = False
try:
    import sqlite3
    _SQLITE_AVAILABLE = True
    logger.info("✅ sqlite3 模块可用，使用 SQLite 模式")
except ImportError as e:
    logger.warning(f"⚠️ sqlite3 模块不可用 ({e})，自动降级到 JSON 文件存储模式")


class MemoryCore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MemoryCore, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = MEMORY_DB_PATH):
        if hasattr(self, 'initialized'):
            return
            
        self.db_path = db_path
        self._use_json_mode = not _SQLITE_AVAILABLE
        
        if not self._use_json_mode:
            self._init_sqlite_db()
            logger.info(f"✅ 统一记忆系统已初始化 (SQLite WAL 模式): {self.db_path}")
        else:
            self._init_json_store()
            logger.info(f"✅ 统一记忆系统已初始化 (JSON 文件模式): {self.json_store_dir}")
            
        self.initialized = True

    # ==================== SQLite 模式实现 ====================
    if _SQLITE_AVAILABLE:
        @contextmanager
        def _get_connection(self):
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                conn.execute('PRAGMA journal_mode=WAL;')
                conn.execute('PRAGMA synchronous=NORMAL;')
                conn.row_factory = sqlite3.Row
                yield conn
            except sqlite3.Error as e:
                logger.error(f"数据库连接异常: {e}")
                raise
            finally:
                conn.close()

        def _init_sqlite_db(self):
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS core_memory (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT,
                        role TEXT,
                        content TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reflections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_summary TEXT,
                        reflection_text TEXT,
                        success BOOLEAN,
                        tools_used TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()

        def get_core_memory(self, key: str) -> Optional[str]:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM core_memory WHERE key = ?", (key,))
                    row = cursor.fetchone()
                    return row['value'] if row else None
            except Exception as e:
                logger.error(f"读取核心记忆失败 [{key}]: {e}")
                return None

        def add_core_memory(self, key: str, value: str):
            try:
                with self._get_connection() as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO core_memory (key, value, updated_at)
                        VALUES (?, ?, ?)
                    ''', (key, value, datetime.now()))
                    conn.commit()
            except Exception as e:
                logger.error(f"写入核心记忆失败 [{key}]: {e}")

        def get_all_core_memory(self) -> Dict[str, str]:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT key, value FROM core_memory")
                    return {row['key']: row['value'] for row in cursor.fetchall()}
            except Exception as e:
                logger.error(f"获取全量核心记忆失败: {e}")
                return {}

        def add_conversation(self, conversation_id: str, role: str, content: str):
            try:
                with self._get_connection() as conn:
                    conn.execute('''
                        INSERT INTO conversation_history (conversation_id, role, content)
                        VALUES (?, ?, ?)
                    ''', (conversation_id, role, content))
                    conn.commit()
            except Exception as e:
                logger.error(f"存储对话记录失败: {e}")

        def get_conversation_history(self, conversation_id: str, limit: int = 10) -> List[Dict]:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT role, content, timestamp FROM conversation_history
                        WHERE conversation_id = ?
                        ORDER BY id DESC LIMIT ?
                    ''', (conversation_id, limit))
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows][::-1]
            except Exception as e:
                logger.error(f"读取对话历史失败: {e}")
                return []

        def add_reflection(self, task_summary: str, reflection_text: str, success: bool, tools_used: List[str]):
            try:
                tools_json = json.dumps(tools_used, ensure_ascii=False)
                with self._get_connection() as conn:
                    conn.execute('''
                        INSERT INTO reflections (task_summary, reflection_text, success, tools_used)
                        VALUES (?, ?, ?, ?)
                    ''', (task_summary, reflection_text, success, tools_json))
                    conn.commit()
            except Exception as e:
                logger.error(f"存储反思记录失败: {e}")

        def get_recent_reflections(self, limit: int = 10) -> List[Dict]:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT task_summary, reflection_text, success, tools_used, created_at
                        FROM reflections
                        ORDER BY id DESC LIMIT ?
                    ''', (limit,))
                    rows = cursor.fetchall()
                    results = []
                    for row in rows:
                        try:
                            tools = json.loads(row['tools_used']) if row['tools_used'] else []
                        except (json.JSONDecodeError, TypeError):
                            tools = []
                        results.append({
                            "task_summary": row['task_summary'],
                            "reflection_text": row['reflection_text'],
                            "success": bool(row['success']),
                            "tools_used": tools,
                            "created_at": row['created_at']
                        })
                    return results[::-1]
            except Exception as e:
                logger.error(f"读取反思记录失败: {e}")
                return []

    # ==================== JSON 模式 Fallback 实现 ====================
    else:
        def _init_json_store(self):
            self.json_store_dir = os.path.join(os.path.dirname(self.db_path), "memory_json")
            os.makedirs(self.json_store_dir, exist_ok=True)
            self._core_memory_path = os.path.join(self.json_store_dir, "core_memory.json")
            self._conv_history_path = os.path.join(self.json_store_dir, "conversation_history.json")
            self._reflections_path = os.path.join(self.json_store_dir, "reflections.json")
            
            for p in [self._core_memory_path, self._conv_history_path, self._reflections_path]:
                if not os.path.exists(p):
                    with open(p, 'w', encoding='utf-8') as f:
                        json.dump({}, f, ensure_ascii=False)

        def get_core_memory(self, key: str) -> Optional[str]:
            try:
                with open(self._core_memory_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get(key)
            except Exception as e:
                logger.error(f"读取核心记忆失败 [{key}]: {e}")
                return None

        def add_core_memory(self, key: str, value: str):
            try:
                with open(self._core_memory_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data[key] = value
                with open(self._core_memory_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"写入核心记忆失败 [{key}]: {e}")

        def get_all_core_memory(self) -> Dict[str, str]:
            try:
                with open(self._core_memory_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"获取全量核心记忆失败: {e}")
                return {}

        def add_conversation(self, conversation_id: str, role: str, content: str):
            try:
                with open(self._conv_history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if conversation_id not in data:
                    data[conversation_id] = []
                data[conversation_id].append({
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                })
                with open(self._conv_history_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"存储对话记录失败: {e}")

        def get_conversation_history(self, conversation_id: str, limit: int = 10) -> List[Dict]:
            try:
                with open(self._conv_history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                history = data.get(conversation_id, [])
                history = history[-limit:] if limit else history
                return list(reversed(history))
            except Exception as e:
                logger.error(f"读取对话历史失败: {e}")
                return []

        def add_reflection(self, task_summary: str, reflection_text: str, success: bool, tools_used: List[str]):
            try:
                with open(self._reflections_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                reflections = data.get("list", [])
                reflections.append({
                    "task_summary": task_summary,
                    "reflection_text": reflection_text,
                    "success": success,
                    "tools_used": tools_used,
                    "created_at": datetime.now().isoformat()
                })
                data["list"] = reflections
                with open(self._reflections_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"存储反思记录失败: {e}")

        def get_recent_reflections(self, limit: int = 10) -> List[Dict]:
            try:
                with open(self._reflections_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                reflections = data.get("list", [])
                return list(reversed(reflections[-limit:])) if limit else list(reversed(reflections))
            except Exception as e:
                logger.error(f"读取反思记录失败: {e}")
                return []

# 全局单例实例
memory_core = MemoryCore()
