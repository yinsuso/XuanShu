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

    def _filter_by_date_range(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """按日期范围过滤记录"""
        filtered = []
        for record in self.data:
            try:
                ts = self._parse_timestamp(record.get("timestamp", ""))
                if start_date and ts < start_date:
                    continue
                if end_date and ts > end_date:
                    continue
                filtered.append(record)
            except Exception:
                continue
        return filtered

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
        today_start = datetime(today.year, today.month, today.day)
        today_end = today_start + timedelta(days=1)
        filtered = self._filter_by_date_range(today_start, today_end)

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
        """获取指定天数内的token使用统计（按天聚合）"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        filtered = self._filter_by_date_range(start_date, end_date)

        date_groups: Dict[str, Dict[str, int]] = {}

        for record in filtered:
            ts = self._parse_timestamp(record.get("timestamp", ""))
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

    def get_usage_by_date_and_model(
        self,
        days: int = 7,
        model_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """按天和模型交叉统计token使用量（精细化统计）"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        filtered = self._filter_by_date_range(start_date, end_date)

        if model_name:
            filtered = [r for r in filtered if r.get("model_name") == model_name]

        cross_groups: Dict[str, Dict[str, Any]] = {}

        for record in filtered:
            ts = self._parse_timestamp(record.get("timestamp", ""))
            date_key = ts.date().isoformat()
            model = record.get("model_name", "unknown")
            provider = record.get("provider", "unknown")
            group_key = f"{date_key}||{model}||{provider}"

            if group_key not in cross_groups:
                cross_groups[group_key] = {
                    "date": date_key,
                    "model_name": model,
                    "provider": provider,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0
                }
            cross_groups[group_key]["prompt_tokens"] += record.get("prompt_tokens", 0)
            cross_groups[group_key]["completion_tokens"] += record.get("completion_tokens", 0)
            cross_groups[group_key]["total_tokens"] += record.get("total_tokens", 0)
            cross_groups[group_key]["call_count"] += 1

        result = list(cross_groups.values())
        result.sort(key=lambda x: (x["date"], x["total_tokens"]), reverse=True)
        return result

    def get_daily_model_breakdown(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """获取某一天的模型使用明细，不传date则取今天"""
        if date_str is None:
            date_str = datetime.now().date().isoformat()

        target_date = datetime.fromisoformat(date_str).date()
        day_start = datetime(target_date.year, target_date.month, target_date.day)
        day_end = day_start + timedelta(days=1)
        filtered = self._filter_by_date_range(day_start, day_end)

        model_groups: Dict[str, Dict[str, Any]] = {}
        for record in filtered:
            model = record.get("model_name", "unknown")
            provider = record.get("provider", "unknown")
            key = f"{model}||{provider}"
            if key not in model_groups:
                model_groups[key] = {
                    "model_name": model,
                    "provider": provider,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0
                }
            model_groups[key]["prompt_tokens"] += record.get("prompt_tokens", 0)
            model_groups[key]["completion_tokens"] += record.get("completion_tokens", 0)
            model_groups[key]["total_tokens"] += record.get("total_tokens", 0)
            model_groups[key]["call_count"] += 1

        models = list(model_groups.values())
        models.sort(key=lambda x: x["total_tokens"], reverse=True)

        total_prompt = sum(m["prompt_tokens"] for m in models)
        total_completion = sum(m["completion_tokens"] for m in models)
        total_tokens = sum(m["total_tokens"] for m in models)
        total_calls = sum(m["call_count"] for m in models)

        return {
            "date": date_str,
            "summary": {
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "call_count": total_calls
            },
            "models": models
        }

    def get_model_usage_by_period(
        self,
        model_name: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """获取某个模型在指定天数内的每日使用量"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        filtered = self._filter_by_date_range(start_date, end_date)
        filtered = [r for r in filtered if r.get("model_name") == model_name]

        date_groups: Dict[str, Dict[str, int]] = {}
        for record in filtered:
            ts = self._parse_timestamp(record.get("timestamp", ""))
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

        result = list(date_groups.values())
        result.sort(key=lambda x: x["date"], reverse=True)
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

    def get_detailed_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取精细化统计信息"""
        return {
            "total": self.get_total_usage(),
            "today": self.get_today_usage(),
            "today_breakdown": self.get_daily_model_breakdown(),
            "daily": self.get_usage_by_period(days),
            "models": self.get_usage_by_model(),
            "daily_model": self.get_usage_by_date_and_model(days),
            "recent": self.get_recent_usage(10)
        }

    def _get_filtered_records(
        self,
        days: int = 7,
        model_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取按条件筛选后的原始记录"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        filtered = self._filter_by_date_range(start_date, end_date)

        if model_name:
            filtered = [r for r in filtered if r.get("model_name") == model_name]

        if date_str:
            target_date = datetime.fromisoformat(date_str).date()
            filtered = [
                r for r in filtered
                if self._parse_timestamp(r.get("timestamp", "")).date() == target_date
            ]

        return filtered

    def _calc_stats_from_records(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """从记录列表计算统计摘要"""
        total_prompt = sum(r.get("prompt_tokens", 0) for r in records)
        total_completion = sum(r.get("completion_tokens", 0) for r in records)
        total_total = sum(r.get("total_tokens", 0) for r in records)
        call_count = len(records)
        return {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_total,
            "call_count": call_count
        }

    def _calc_daily_from_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从记录列表按天聚合统计"""
        date_groups: Dict[str, Dict[str, int]] = {}
        for record in records:
            ts = self._parse_timestamp(record.get("timestamp", ""))
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
        result = list(date_groups.values())
        result.sort(key=lambda x: x["date"], reverse=True)
        return result

    def _calc_models_from_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从记录列表按模型聚合统计"""
        model_groups: Dict[str, Dict[str, Any]] = {}
        for record in records:
            model = record.get("model_name", "unknown")
            provider = record.get("provider", "unknown")
            key = f"{model}||{provider}"
            if key not in model_groups:
                model_groups[key] = {
                    "model_name": model,
                    "provider": provider,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0
                }
            model_groups[key]["prompt_tokens"] += record.get("prompt_tokens", 0)
            model_groups[key]["completion_tokens"] += record.get("completion_tokens", 0)
            model_groups[key]["total_tokens"] += record.get("total_tokens", 0)
            model_groups[key]["call_count"] += 1
        result = list(model_groups.values())
        result.sort(key=lambda x: x["total_tokens"], reverse=True)
        return result

    def _calc_daily_model_from_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从记录列表按天和模型交叉聚合统计"""
        cross_groups: Dict[str, Dict[str, Any]] = {}
        for record in records:
            ts = self._parse_timestamp(record.get("timestamp", ""))
            date_key = ts.date().isoformat()
            model = record.get("model_name", "unknown")
            provider = record.get("provider", "unknown")
            group_key = f"{date_key}||{model}||{provider}"
            if group_key not in cross_groups:
                cross_groups[group_key] = {
                    "date": date_key,
                    "model_name": model,
                    "provider": provider,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0
                }
            cross_groups[group_key]["prompt_tokens"] += record.get("prompt_tokens", 0)
            cross_groups[group_key]["completion_tokens"] += record.get("completion_tokens", 0)
            cross_groups[group_key]["total_tokens"] += record.get("total_tokens", 0)
            cross_groups[group_key]["call_count"] += 1
        result = list(cross_groups.values())
        result.sort(key=lambda x: (x["date"], x["total_tokens"]), reverse=True)
        return result

    def _calc_today_breakdown_from_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """从记录列表计算今日模型明细"""
        today = datetime.now().date()
        today_records = [
            r for r in records
            if self._parse_timestamp(r.get("timestamp", "")).date() == today
        ]
        models = self._calc_models_from_records(today_records)
        summary = self._calc_stats_from_records(today_records)
        return {
            "date": today.isoformat(),
            "summary": summary,
            "models": models
        }

    def get_filtered_stats(
        self,
        days: int = 7,
        model_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取带筛选条件的完整统计信息"""
        records = self._get_filtered_records(days, model_name, date_str)
        return {
            "total": self._calc_stats_from_records(records),
            "today": self._calc_today_breakdown_from_records(records)["summary"],
            "today_breakdown": self._calc_today_breakdown_from_records(records),
            "daily": self._calc_daily_from_records(records),
            "models": self._calc_models_from_records(records),
            "daily_model": self._calc_daily_model_from_records(records),
            "recent": sorted(
                [
                    {
                        "timestamp": r.get("timestamp", ""),
                        "model_name": r.get("model_name", ""),
                        "provider": r.get("provider", ""),
                        "prompt_tokens": r.get("prompt_tokens", 0),
                        "completion_tokens": r.get("completion_tokens", 0),
                        "total_tokens": r.get("total_tokens", 0)
                    }
                    for r in records
                ],
                key=lambda x: x["timestamp"],
                reverse=True
            )[:10]
        }

    def get_available_dates(self, days: int = 30) -> List[str]:
        """获取有数据的日期列表"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        filtered = self._filter_by_date_range(start_date, end_date)

        dates = set()
        for record in filtered:
            try:
                ts = self._parse_timestamp(record.get("timestamp", ""))
                dates.add(ts.date().isoformat())
            except Exception:
                continue

        return sorted(list(dates), reverse=True)

    def get_model_list(self) -> List[Dict[str, str]]:
        """获取所有使用过的模型列表"""
        models = {}
        for record in self.data:
            model = record.get("model_name", "unknown")
            provider = record.get("provider", "unknown")
            key = f"{model}||{provider}"
            if key not in models:
                models[key] = {"model_name": model, "provider": provider}
        return list(models.values())


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

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_token_usage_provider ON token_usage(provider)
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
            """获取指定天数内的token使用统计（按天聚合）"""
            start_date = (datetime.now() - timedelta(days=days)).isoformat()

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
            ''', (start_date,))

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

        def get_usage_by_date_and_model(
            self,
            days: int = 7,
            model_name: Optional[str] = None
        ) -> List[Dict[str, Any]]:
            """按天和模型交叉统计token使用量（精细化统计）"""
            start_date = (datetime.now() - timedelta(days=days)).isoformat()

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            if model_name:
                cursor.execute('''
                    SELECT DATE(timestamp) as date,
                           model_name,
                           provider,
                           SUM(prompt_tokens) as prompt,
                           SUM(completion_tokens) as completion,
                           SUM(total_tokens) as total,
                           COUNT(*) as calls
                    FROM token_usage
                    WHERE timestamp >= ? AND model_name = ?
                    GROUP BY DATE(timestamp), model_name, provider
                    ORDER BY date DESC, total DESC
                ''', (start_date, model_name))
            else:
                cursor.execute('''
                    SELECT DATE(timestamp) as date,
                           model_name,
                           provider,
                           SUM(prompt_tokens) as prompt,
                           SUM(completion_tokens) as completion,
                           SUM(total_tokens) as total,
                           COUNT(*) as calls
                    FROM token_usage
                    WHERE timestamp >= ?
                    GROUP BY DATE(timestamp), model_name, provider
                    ORDER BY date DESC, total DESC
                ''', (start_date,))

            results = cursor.fetchall()
            conn.close()

            return [
                {
                    "date": row[0],
                    "model_name": row[1],
                    "provider": row[2],
                    "prompt_tokens": row[3] or 0,
                    "completion_tokens": row[4] or 0,
                    "total_tokens": row[5] or 0,
                    "call_count": row[6] or 0
                }
                for row in results
            ]

        def get_daily_model_breakdown(self, date_str: Optional[str] = None) -> Dict[str, Any]:
            """获取某一天的模型使用明细，不传date则取今天"""
            if date_str is None:
                date_str = datetime.now().date().isoformat()

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT model_name,
                       provider,
                       SUM(prompt_tokens) as prompt,
                       SUM(completion_tokens) as completion,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM token_usage
                WHERE DATE(timestamp) = ?
                GROUP BY model_name, provider
                ORDER BY total DESC
            ''', (date_str,))

            results = cursor.fetchall()

            cursor.execute('''
                SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*)
                FROM token_usage
                WHERE DATE(timestamp) = ?
            ''', (date_str,))

            summary = cursor.fetchone()
            conn.close()

            models = [
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

            return {
                "date": date_str,
                "summary": {
                    "prompt_tokens": summary[0] or 0,
                    "completion_tokens": summary[1] or 0,
                    "total_tokens": summary[2] or 0,
                    "call_count": summary[3] or 0
                },
                "models": models
            }

        def get_model_usage_by_period(
            self,
            model_name: str,
            days: int = 30
        ) -> List[Dict[str, Any]]:
            """获取某个模型在指定天数内的每日使用量"""
            start_date = (datetime.now() - timedelta(days=days)).isoformat()

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT DATE(timestamp) as date,
                       SUM(prompt_tokens) as prompt,
                       SUM(completion_tokens) as completion,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM token_usage
                WHERE timestamp >= ? AND model_name = ?
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            ''', (start_date, model_name))

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

        def get_detailed_stats(self, days: int = 7) -> Dict[str, Any]:
            """获取精细化统计信息"""
            return {
                "total": self.get_total_usage(),
                "today": self.get_today_usage(),
                "today_breakdown": self.get_daily_model_breakdown(),
                "daily": self.get_usage_by_period(days),
                "models": self.get_usage_by_model(),
                "daily_model": self.get_usage_by_date_and_model(days),
                "recent": self.get_recent_usage(10)
            }

        def _build_where_clause(
            self,
            days: int = 7,
            model_name: Optional[str] = None,
            date_str: Optional[str] = None
        ) -> tuple:
            """构建筛选条件的 WHERE 子句和参数"""
            conditions = ["timestamp >= ?"]
            params = [(datetime.now() - timedelta(days=days)).isoformat()]

            if model_name:
                conditions.append("model_name = ?")
                params.append(model_name)

            if date_str:
                conditions.append("DATE(timestamp) = ?")
                params.append(date_str)

            where_clause = " AND ".join(conditions)
            return where_clause, params

        def get_filtered_stats(
            self,
            days: int = 7,
            model_name: Optional[str] = None,
            date_str: Optional[str] = None
        ) -> Dict[str, Any]:
            """获取带筛选条件的完整统计信息"""
            where_clause, params = self._build_where_clause(days, model_name, date_str)
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # total
            cursor.execute(f'''
                SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*)
                FROM token_usage
                WHERE {where_clause}
            ''', params)
            total_row = cursor.fetchone()
            total = {
                "prompt_tokens": total_row[0] or 0,
                "completion_tokens": total_row[1] or 0,
                "total_tokens": total_row[2] or 0,
                "call_count": total_row[3] or 0
            }

            # today
            today_str = datetime.now().date().isoformat()
            today_conditions = conditions = ["DATE(timestamp) = ?"]
            today_params = [today_str]
            if model_name:
                today_conditions.append("model_name = ?")
                today_params.append(model_name)
            if date_str:
                today_conditions.append("DATE(timestamp) = ?")
                today_params.append(date_str)
            today_where = " AND ".join(today_conditions)
            cursor.execute(f'''
                SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*)
                FROM token_usage
                WHERE {today_where}
            ''', today_params)
            today_row = cursor.fetchone()
            today = {
                "prompt_tokens": today_row[0] or 0,
                "completion_tokens": today_row[1] or 0,
                "total_tokens": today_row[2] or 0,
                "call_count": today_row[3] or 0
            }

            # today_breakdown
            cursor.execute(f'''
                SELECT model_name, provider,
                       SUM(prompt_tokens) as prompt,
                       SUM(completion_tokens) as completion,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM token_usage
                WHERE {today_where}
                GROUP BY model_name, provider
                ORDER BY total DESC
            ''', today_params)
            today_models = [
                {
                    "model_name": row[0],
                    "provider": row[1],
                    "prompt_tokens": row[2] or 0,
                    "completion_tokens": row[3] or 0,
                    "total_tokens": row[4] or 0,
                    "call_count": row[5] or 0
                }
                for row in cursor.fetchall()
            ]
            today_breakdown = {
                "date": today_str,
                "summary": today,
                "models": today_models
            }

            # daily
            cursor.execute(f'''
                SELECT DATE(timestamp) as date,
                       SUM(prompt_tokens) as prompt,
                       SUM(completion_tokens) as completion,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM token_usage
                WHERE {where_clause}
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            ''', params)
            daily = [
                {
                    "date": row[0],
                    "prompt_tokens": row[1] or 0,
                    "completion_tokens": row[2] or 0,
                    "total_tokens": row[3] or 0,
                    "call_count": row[4] or 0
                }
                for row in cursor.fetchall()
            ]

            # models
            cursor.execute(f'''
                SELECT model_name, provider,
                       SUM(prompt_tokens) as prompt,
                       SUM(completion_tokens) as completion,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM token_usage
                WHERE {where_clause}
                GROUP BY model_name, provider
                ORDER BY total DESC
            ''', params)
            models = [
                {
                    "model_name": row[0],
                    "provider": row[1],
                    "prompt_tokens": row[2] or 0,
                    "completion_tokens": row[3] or 0,
                    "total_tokens": row[4] or 0,
                    "call_count": row[5] or 0
                }
                for row in cursor.fetchall()
            ]

            # daily_model
            cursor.execute(f'''
                SELECT DATE(timestamp) as date,
                       model_name,
                       provider,
                       SUM(prompt_tokens) as prompt,
                       SUM(completion_tokens) as completion,
                       SUM(total_tokens) as total,
                       COUNT(*) as calls
                FROM token_usage
                WHERE {where_clause}
                GROUP BY DATE(timestamp), model_name, provider
                ORDER BY date DESC, total DESC
            ''', params)
            daily_model = [
                {
                    "date": row[0],
                    "model_name": row[1],
                    "provider": row[2],
                    "prompt_tokens": row[3] or 0,
                    "completion_tokens": row[4] or 0,
                    "total_tokens": row[5] or 0,
                    "call_count": row[6] or 0
                }
                for row in cursor.fetchall()
            ]

            # recent
            cursor.execute(f'''
                SELECT timestamp, model_name, provider, prompt_tokens, completion_tokens, total_tokens
                FROM token_usage
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT 10
            ''', params)
            recent = [
                {
                    "timestamp": row[0],
                    "model_name": row[1],
                    "provider": row[2],
                    "prompt_tokens": row[3],
                    "completion_tokens": row[4],
                    "total_tokens": row[5]
                }
                for row in cursor.fetchall()
            ]

            conn.close()

            return {
                "total": total,
                "today": today,
                "today_breakdown": today_breakdown,
                "daily": daily,
                "models": models,
                "daily_model": daily_model,
                "recent": recent
            }

        def get_available_dates(self, days: int = 30) -> List[str]:
            """获取有数据的日期列表"""
            start_date = (datetime.now() - timedelta(days=days)).isoformat()

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT DISTINCT DATE(timestamp) as date
                FROM token_usage
                WHERE timestamp >= ?
                ORDER BY date DESC
            ''', (start_date,))

            results = cursor.fetchall()
            conn.close()

            return [row[0] for row in results]

        def get_model_list(self) -> List[Dict[str, str]]:
            """获取所有使用过的模型列表"""
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT DISTINCT model_name, provider
                FROM token_usage
                ORDER BY model_name
            ''')

            results = cursor.fetchall()
            conn.close()

            return [
                {"model_name": row[0], "provider": row[1]}
                for row in results
            ]

    TokenTracker = TokenTrackerSQLite
    logger.info("token_tracker 使用 SQLite 存储模式")

except ImportError as e:
    logger.warning(f"sqlite3 模块不可用，自动切换到 JSON 文件存储模式: {e}")
    TokenTracker = TokenTrackerJSON


token_tracker = TokenTracker()
