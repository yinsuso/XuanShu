import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from config import PROJECT_ROOT
from logger import logger

DB_PATH = os.path.join(PROJECT_ROOT, "data", "token_stats.db")
JSON_PATH = os.path.join(PROJECT_ROOT, "data", "token_stats.json")
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


def estimate_tokens_by_chars(text: str) -> int:
    """基于字符数估算token数（中文1字≈1.5token，英文1词≈1.3token，通用兜底）"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.2) + 1


class TokenTrackerJSON:
    """基于JSON文件的token追踪器，作为sqlite3的降级方案"""
    def __init__(self):
        self.data: List[Dict[str, Any]] = []
        self._init_db()

    def _init_db(self):
        """初始化JSON存储"""
        if os.path.exists(JSON_PATH):
            try:
                with open(JSON_PATH, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        self.data = json.loads(content)
                    else:
                        self.data = []
            except Exception as e:
                logger.warning(f"加载token统计JSON文件失败，重新初始化: {e}")
                self.data = []
        else:
            self.data = []
        self._save()

    def _save(self):
        """保存数据到JSON文件"""
        try:
            with open(JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存token统计JSON文件失败: {e}")

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
        new_record = {
            "id": len(self.data) + 1 if not self.data else max(r.get("id", 0) for r in self.data) + 1,
            "timestamp": timestamp,
            "model_name": model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "provider": provider
        }
        self.data.append(new_record)
        self._save()
        logger.debug(f"记录token使用: {model_name} - 总{total_tokens} (提示:{prompt_tokens}, 完成:{completion_tokens})")
    
    def record_usage_estimation(
        self,
        model_name: str,
        prompt_text: str,
        completion_text: str,
        provider: str
    ):
        """智能记录token使用：优先直接数值，没有就用估算"""
        prompt_tokens = estimate_tokens_by_chars(prompt_text)
        completion_tokens = estimate_tokens_by_chars(completion_text)
        self.record_usage(model_name, prompt_tokens, completion_tokens, provider)

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """解析时间戳字符串"""
        try:
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

    def get_total_usage(self) -> Dict[str, int]:
        """获取总token使用量"""
        total_prompt = sum(r.get("prompt_tokens", 0) for r in self.data)
        total_completion = sum(r.get("completion_tokens", 0) for r in self.data)
        total_total = sum(r.get("total_tokens", 0) for r in self.data)
        call_count = len(self.data)
        return {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_total,
            "call_count": call_count
        }

    def get_today_usage(self) -> Dict[str, int]:
        """获取今日token使用量"""
        today = datetime.now().date()
        today_start = datetime(today.year, today.month, today.day).isoformat()
        
        filtered = [r for r in self.data if r.get("timestamp", "") >= today_start]
        total_prompt = sum(r.get("prompt_tokens", 0) for r in filtered)
        total_completion = sum(r.get("completion_tokens", 0) for r in filtered)
        total_total = sum(r.get("total_tokens", 0) for r in filtered)
        call_count = len(filtered)
        
        return {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_total,
            "call_count": call_count
        }

    def get_usage_by_period(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取指定天数内的token使用统计"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        date_groups: Dict[str, Dict[str, int]] = {}
        
        for record in self.data:
            ts_str = record.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= start_date:
                    date_key = ts.date().isoformat()
                    if date_key not in date_groups:
                        date_groups[date_key] = {
                            "date": date_key,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "call_count": 0
                        }
                    date_groups[date_key]["prompt_tokens"] += record.get("prompt_tokens", 0)
                    date_groups[date_key]["completion_tokens"] += record.get("completion_tokens", 0)
                    date_groups[date_key]["total_tokens"] += record.get("total_tokens", 0)
                    date_groups[date_key]["call_count"] += 1
            except Exception:
                continue
        
        result = list(date_groups.values())
        result.sort(key=lambda x: x["date"], reverse=True)
        return result

    def get_usage_by_model(self) -> List[Dict[str, Any]]:
        """按模型统计token使用量"""
        model_groups: Dict[str, Dict[str, Any]] = {}
        
        for record in self.data:
            model_key = f"{record.get('model_name', 'unknown')}||{record.get('provider', 'unknown')}"
            if model_key not in model_groups:
                model_groups[model_key] = {
                    "model_name": record.get('model_name', 'unknown'),
                    "provider": record.get('provider', 'unknown'),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0
                }
            model_groups[model_key]["prompt_tokens"] += record.get("prompt_tokens", 0)
            model_groups[model_key]["completion_tokens"] += record.get("completion_tokens", 0)
            model_groups[model_key]["total_tokens"] += record.get("total_tokens", 0)
            model_groups[model_key]["call_count"] += 1
        
        result = list(model_groups.values())
        result.sort(key=lambda x: x["total_tokens"], reverse=True)
        return result

    def get_recent_usage(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的token使用记录"""
        sorted_records = sorted(
            self.data,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )
        limited = sorted_records[:limit]
        return [
            {
                "timestamp": r.get("timestamp", ""),
                "model_name": r.get("model_name", ""),
                "provider": r.get("provider", ""),
                "prompt_tokens": r.get("prompt_tokens", 0),
                "completion_tokens": r.get("completion_tokens", 0),
                "total_tokens": r.get("total_tokens", 0)
            }
            for r in limited
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


try:
    import sqlite3

    class TokenTrackerSQLite:
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
            """记录token使用情况 - 支持为0的兜底情况"""
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
            
            logger.debug(f"记录token使用: {model_name} - 总{total_tokens} (提示:{prompt_tokens}, 完成:{completion_tokens})")
        
        def record_usage_estimation(
            self,
            model_name: str,
            prompt_text: str,
            completion_text: str,
            provider: str
        ):
            """智能记录token使用：优先直接数值，没有就用估算"""
            prompt_tokens = estimate_tokens_by_chars(prompt_text)
            completion_tokens = estimate_tokens_by_chars(completion_text)
            self.record_usage(model_name, prompt_tokens, completion_tokens, provider)

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

    TokenTracker = TokenTrackerSQLite
    logger.info("token_tracker 使用 SQLite 存储模式")

except ImportError as e:
    logger.warning(f"sqlite3 模块不可用，自动切换到 JSON 文件存储模式: {e}")
    TokenTracker = TokenTrackerJSON


token_tracker = TokenTracker()
