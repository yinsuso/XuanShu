#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
敏感信息脱敏模块 (DataMasker)
负责识别并脱敏日志、记忆库、用户输出中的敏感信息
"""

import re
import json
import threading
from typing import Union, Dict, Any, List
from pathlib import Path
from datetime import datetime
from config import (
    MASKING_ENABLED,
    MASKING_PATTERNS,
    MASKING_REPLACEMENT,
    MASKING_PRESERVE_LENGTH,
    MASKING_STATS_PATH,
)


class DataMasker:
    """敏感信息脱敏器，支持正则模式和统计追踪"""

    _instance = None
    _lock = threading.Lock()
    _stats_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._patterns = self._compile_patterns()
        self._stats = self._load_stats()
        self._ensure_logs_dir()

    def _compile_patterns(self) -> List[re.Pattern]:
        """预编译所有正则模式，提升性能"""
        compiled = []
        for pattern in MASKING_PATTERNS:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                # 记录错误但不阻止初始化
                print(f"[DataMasker] 警告: 正则模式编译失败 '{pattern}': {e}")
        return compiled

    def _load_stats(self) -> Dict[str, Any]:
        """加载脱敏统计"""
        if not MASKING_STATS_PATH:
            return {"total_masked": 0, "by_pattern": {}, "last_updated": None}
        try:
            if Path(MASKING_STATS_PATH).exists():
                with open(MASKING_STATS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[DataMasker] 警告: 无法加载统计文件: {e}")
        return {"total_masked": 0, "by_pattern": {}, "last_updated": None}

    def _save_stats(self):
        """保存脱敏统计"""
        if not MASKING_STATS_PATH:
            return
        try:
            self._stats["last_updated"] = datetime.utcnow().isoformat() + "Z"
            with open(MASKING_STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DataMasker] 错误: 保存统计失败: {e}")

    def _ensure_logs_dir(self):
        """确保日志目录存在"""
        if MASKING_STATS_PATH:
            Path(MASKING_STATS_PATH).parent.mkdir(parents=True, exist_ok=True)

    def mask(self, text: Union[str, Dict, List, Any]) -> Union[str, Dict, List, Any]:
        """
        主脱敏入口：支持字符串、字典、列表的递归脱敏

        Args:
            text: 待脱敏内容（字符串、字典或列表）

        Returns:
            脱敏后的内容（保持原类型）
        """
        if not MASKING_ENABLED:
            return text

        if isinstance(text, str):
            return self._mask_string(text)
        elif isinstance(text, dict):
            return {k: self.mask(v) for k, v in text.items()}
        elif isinstance(text, list):
            return [self.mask(item) for item in text]
        else:
            return text

    def _mask_string(self, text: str) -> str:
        """对单个字符串执行脱敏"""
        if not isinstance(text, str) or not text.strip():
            return text

        original = text
        for pattern in self._patterns:
            matches = pattern.findall(text)
            if matches:
                count = len(matches) if isinstance(matches, list) else 1
                self._increment_stats(pattern.pattern, count)
                text = pattern.sub(self._get_replacement(text), text)
        return text

    def _get_replacement(self, text: str) -> str:
        """根据配置生成替换文本"""
        if MASKING_PRESERVE_LENGTH:
            # 保持长度，用*替换
            length = len(text) if isinstance(text, str) else 8
            return "*" * min(length, 12)
        else:
            return MASKING_REPLACEMENT

    def _increment_stats(self, pattern_name: str, count: int):
        """更新统计信息"""
        with self._stats_lock:
            self._stats["total_masked"] = self._stats.get("total_masked", 0) + count
            self._stats["by_pattern"][pattern_name] = (
                self._stats["by_pattern"].get(pattern_name, 0) + count
            )

    def get_stats(self) -> Dict[str, Any]:
        """获取当前统计"""
        with self._stats_lock:
            return self._stats.copy()

    def reset_stats(self):
        """重置统计并保存"""
        with self._stats_lock:
            self._stats = {"total_masked": 0, "by_pattern": {}, "last_updated": None}
            self._save_stats()

    def force_flush(self):
        """强制保存统计到磁盘"""
        self._save_stats()


# 全局单例，方便其他模块导入使用
masker = DataMasker()
