import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from .config import PROJECT_ROOT
from .logger import logger

DB_PATH = os.path.join(PROJECT_ROOT, "data", "token_stats.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@dataclass
class TokenUsage:
    id: int
    timestamp: datetime
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider: str


class TokenTracker:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model_name TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                provider TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp ON token_usage(timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_token_usage_model ON token_usage(model_name)
        ''')
        
        conn.commit()
        conn.close()

    def record_usage(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider: str
    ):
        """记录token使用情况"""
        total_tokens = prompt_tokens + completion_tokens
        timestamp = datetime.now().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO token_usage 
            (timestamp, model_name, prompt_tokens, completion_tokens, total_tokens, provider)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (timestamp, model_name, prompt_tokens, completion_tokens, total_tokens, provider))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"记录token使用: {model_name} - {total_tokens} tokens")

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """解析时间戳字符串"""
        try:
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

    def get_total_usage(self) -> Dict[str, int]:
        """获取总token使用量"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*)
            FROM token_usage
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        return {
            "prompt_tokens": result[0] or 0,
            "completion_tokens": result[1] or 0,
            "total_tokens": result[2] or 0,
            "call_count": result[3] or 0
        }

    def get_today_usage(self) -> Dict[str, int]:
        """获取今日token使用量"""
        today = datetime.now().date()
        today_start = datetime(today.year, today.month, today.day).isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*)
            FROM token_usage
            WHERE timestamp >= ?
        ''', (today_start,))
        
        result = cursor.fetchone()
        conn.close()
        
        return {
            "prompt_tokens": result[0] or 0,
            "completion_tokens": result[1] or 0,
            "total_tokens": result[2] or 0,
            "call_count": result[3] or 0
        }

    def get_usage_by_period(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取指定天数内的token使用统计"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DATE(timestamp) as date, 
                   SUM(prompt_tokens) as prompt, 
                   SUM(completion_tokens) as completion, 
                   SUM(total_tokens) as total,
                   COUNT(*) as calls
            FROM token_usage
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        ''', (start_date.isoformat(),))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                "date": row[0],
                "prompt_tokens": row[1] or 0,
                "completion_tokens": row[2] or 0,
                "total_tokens": row[3] or 0,
                "call_count": row[4] or 0
            }
            for row in results
        ]

    def get_usage_by_model(self) -> List[Dict[str, Any]]:
        """按模型统计token使用量"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT model_name, provider,
                   SUM(prompt_tokens) as prompt, 
                   SUM(completion_tokens) as completion, 
                   SUM(total_tokens) as total,
                   COUNT(*) as calls
            FROM token_usage
            GROUP BY model_name, provider
            ORDER BY total DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                "model_name": row[0],
                "provider": row[1],
                "prompt_tokens": row[2] or 0,
                "completion_tokens": row[3] or 0,
                "total_tokens": row[4] or 0,
                "call_count": row[5] or 0
            }
            for row in results
        ]

    def get_recent_usage(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的token使用记录"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, model_name, provider, prompt_tokens, completion_tokens, total_tokens
            FROM token_usage
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                "timestamp": row[0],
                "model_name": row[1],
                "provider": row[2],
                "prompt_tokens": row[3],
                "completion_tokens": row[4],
                "total_tokens": row[5]
            }
            for row in results
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取综合统计信息"""
        return {
            "total": self.get_total_usage(),
            "today": self.get_today_usage(),
            "weekly": self.get_usage_by_period(7),
            "models": self.get_usage_by_model(),
            "recent": self.get_recent_usage(10)
        }


token_tracker = TokenTracker()