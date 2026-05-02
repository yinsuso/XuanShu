"""
统一记忆核心模块 (Unified Memory Core)
实现基于 SQLite 的高性能持久化存储，支持 WAL 模式以消除并发锁死问题。
遵循“潜意识(DB) $\rightarrow$ 意识(MD)”的同步架构。
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

from config import MEMORY_DB_PATH, PROJECT_ROOT
from logger import logger

class MemoryCore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MemoryCore, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = MEMORY_DB_PATH):
        # 防止多次初始化
        if hasattr(self, 'initialized'):
            return
            
        self.db_path = db_path
        self._init_db()
        self.initialized = True
        logger.info(f"✅ 统一记忆系统已初始化 (SQLite WAL 模式): {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """
        管理数据库连接的上下文管理器。
        开启 WAL 模式以支持并发读写，减少 'database is locked' 错误。
        """
        conn = sqlite3.connect(self.db_path, timeout=30) # 增加超时时间
        try:
            # 开启 WAL 模式
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA synchronous=NORMAL;')
            conn.row_factory = sqlite3.Row # 返回字典格式
            yield conn
        except sqlite3.Error as e:
            logger.error(f"数据库连接异常: {e}")
            raise
        finally:
            conn.close()

    def _init_db(self):
        """初始化数据库表结构"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 核心记忆表 (Key-Value)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS core_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 2. 对话历史表 (Episode)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 3. 反思记录表 (Reflections)
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

    # --- 核心记忆接口 (潜意识) ---
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

    # --- 对话历史接口 ---
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

    # --- 反思记录接口 (进化核心) ---
    def add_reflection(self, task_summary: str, reflection_text: str, success: bool, tools_used: List[str]):
        try:
            # 将列表安全转换为 JSON 字符串
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
                    # 鲁棒性解析 JSON 字段
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

# 全局单例实例
memory_core = MemoryCore()
