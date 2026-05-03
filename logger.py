#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化日志系统 (Structured Logging)

功能：
- JSON 行格式结构化日志
- 跨组件 Trace ID 追踪
- 异步批量写入，性能优化
- 集成敏感信息脱敏
- 自动日志轮转（保留30天，压缩归档）
"""

import json
import logging
import sys
import os
import time
import threading
import queue
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import gzip
import shutil

from config import (
    PROJECT_ROOT,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_FILE,
    LOG_FILE_JSON,
    LOG_ROTATION_DAYS,
    LOG_COMPRESS,
    LOG_ASYNC_QUEUE_SIZE,
    LOG_BATCH_SIZE,
    LOG_FLUSH_INTERVAL,
    TRACE_ID_HEADER,
    MASKING_ENABLED,
)
from data_masker import masker


class JsonFormatter(logging.Formatter):
    """JSON 格式化器"""

    def __init__(self, include_trace_id: bool = True):
        super().__init__()
        self.include_trace_id = include_trace_id

    def format(self, record: logging.LogRecord) -> str:
        # 提取基础字段
        log_entry = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "component": record.name,
            "action": record.getMessage(),
        }

        # 添加异常信息
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_entry["stack_info"] = record.stack_info

        # 添加额外的自定义字段
        if hasattr(record, "details") and record.details:
            log_entry["details"] = record.details

        # 添加 Trace ID
        if self.include_trace_id and hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        elif self.include_trace_id:
            log_entry["trace_id"] = None

        # 脱敏处理
        if MASKING_ENABLED:
            log_entry = masker.mask(log_entry)

        # 转换为 JSON 字符串
        try:
            return json.dumps(log_entry, ensure_ascii=False)
        except Exception as e:
            # 如果序列化失败，返回简化的错误信息
            return json.dumps({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "ERROR",
                "component": "logger",
                "action": "log_serialization_failed",
                "error": str(e),
                "original_message": str(record.getMessage())[:100],
            })


class TextFormatter(logging.Formatter):
    """传统文本格式化器（保持兼容）"""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        # 如果有额外 details，附加到消息
        if hasattr(record, "details") and record.details:
            details_str = " " + json.dumps(record.details, ensure_ascii=False)
            record.msg = record.msg + details_str
        return super().format(record)


class AsyncHandler(logging.Handler):
    """异步批量写入处理器"""

    def __init__(
        self,
        filename: str,
        queue_size: int = LOG_ASYNC_QUEUE_SIZE,
        batch_size: int = LOG_BATCH_SIZE,
        flush_interval: float = LOG_FLUSH_INTERVAL,
    ):
        super().__init__()
        self.filename = filename
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # 确保目录存在
        Path(filename).parent.mkdir(parents=True, exist_ok=True)

        # 异步队列
        self.queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

        # 轮转状态
        self._last_rotation_check = time.time()

    def emit(self, record: logging.LogRecord) -> None:
        """将日志记录放入队列"""
        try:
            msg = self.format(record)
            self.queue.put_nowait(msg)
        except queue.Full:
            # 队列满，直接同步写入（应急）
            self._sync_write(self.format(record))
        except Exception:
            self.handleError(record)

    def _worker_loop(self):
        """后台工作线程：批量写入"""
        batch: List[str] = []
        last_flush = time.time()

        while not self._shutdown.is_set():
            try:
                # 等待日志条目，超时定期刷盘
                try:
                    timeout = max(0.1, self.flush_interval - (time.time() - last_flush))
                    msg = self.queue.get(timeout=timeout)
                    batch.append(msg)
                except queue.Empty:
                    pass

                # 检查是否达到批处理大小或刷盘时间
                should_flush = (
                    len(batch) >= self.batch_size
                    or (time.time() - last_flush) >= self.flush_interval
                )

                if should_flush and batch:
                    self._flush_batch(batch)
                    batch.clear()
                    last_flush = time.time()

                # 检查是否需要日志轮转（每天一次）
                if self._should_rotate():
                    self._rotate_logs()

            except Exception as e:
                # 工作线程异常不退出，记录到 stderr
                print(f"[AsyncHandler] Worker error: {e}", file=sys.stderr)

        # 退出前刷新剩余
        if batch:
            self._flush_batch(batch)

    def _should_rotate(self) -> bool:
        """检查是否需要进行日志轮转"""
        # 每天检查一次，避免频繁 stat
        if time.time() - self._last_rotation_check < 86400:
            return False
        if not Path(self.filename).exists():
            return False
        # 检查文件修改时间
        mtime = Path(self.filename).stat().st_mtime
        cutoff = time.time() - (LOG_ROTATION_DAYS * 86400)
        return mtime < cutoff

    def _rotate_logs(self):
        """执行日志轮转：压缩归档超过保留天数的日志"""
        try:
            log_dir = Path(self.filename).parent
            # 查找所有 .jsonl 或 .log 文件
            for log_file in log_dir.glob("*.jsonl"):
                if log_file.name == Path(self.filename).name:
                    continue  # 跳过当前活跃日志
                mtime = log_file.stat().st_mtime
                age_days = (time.time() - mtime) / 86400
                if age_days >= LOG_ROTATION_DAYS:
                    if LOG_COMPRESS:
                        # 压缩为 .gz
                        gz_path = log_file.with_suffix(log_file.suffix + ".gz")
                        with open(log_file, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                        log_file.unlink(missing_ok=True)
                    else:
                        # 直接删除
                        log_file.unlink(missing_ok=True)
            self._last_rotation_check = time.time()
        except Exception as e:
            print(f"[AsyncHandler] 日志轮转失败: {e}", file=sys.stderr)

    def _flush_batch(self, batch: List[str]):
        """批量写入磁盘"""
        if not batch:
            return
        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                for line in batch:
                    f.write(line + "\n")
        except Exception as e:
            print(f"[AsyncHandler] 写入失败: {e}", file=sys.stderr)
            # 回退到同步写入
            for line in batch:
                self._sync_write(line)

    def _sync_write(self, line: str):
        """同步单条写入（应急）"""
        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"[AsyncHandler] 同步写入失败: {e}", file=sys.stderr)

    def close(self):
        """关闭处理器，等待队列清空"""
        self._shutdown.set()
        self._worker.join(timeout=5)
        super().close()


class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        self._trace_context = threading.local()
        self._setup_logger()

    def _setup_logger(self):
        """配置日志记录器"""
        if self.logger.handlers:
            return  # 已经配置过

        self.logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

        # 选择格式化器
        if LOG_FORMAT == "json":
            formatter = JsonFormatter(include_trace_id=True)
        else:
            formatter = TextFormatter()

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 文件处理器 - 强制写入 JSON 格式日志到文件，便于排查问题
        # 无论 LOG_FORMAT 如何，都写入结构化日志到文件
        try:
            log_file_path = LOG_FILE_JSON or os.path.join(PROJECT_ROOT, "logs", "hermes.jsonl")
            file_handler = AsyncHandler(
                filename=log_file_path,
                queue_size=LOG_ASYNC_QUEUE_SIZE,
                batch_size=LOG_BATCH_SIZE,
                flush_interval=LOG_FLUSH_INTERVAL,
            )
            file_handler.setFormatter(JsonFormatter(include_trace_id=True))
            self.logger.addHandler(file_handler)
            # 初始化时记录一条日志，确认文件写入正常
            self.logger.info("✅ 日志文件处理器已初始化", {"log_file": log_file_path})
        except Exception as e:
            # 文件处理器失败不阻塞整体，但记录到 stderr
            print(f"[StructuredLogger] 无法创建日志文件处理器: {e}", file=sys.stderr)

        # 传统日志文件（如果指定且不同于 JSON 文件）
        if LOG_FILE and LOG_FILE != (LOG_FILE_JSON or os.path.join(PROJECT_ROOT, "logs", "hermes.jsonl")):
            try:
                traditional_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
                traditional_handler.setFormatter(TextFormatter())
                self.logger.addHandler(traditional_handler)
            except Exception as e:
                self.logger.warning(f"无法创建传统日志文件 {LOG_FILE}: {e}")

    def set_trace_id(self, trace_id: str):
        """设置当前线程的 Trace ID"""
        self._trace_context.value = trace_id

    def get_trace_id(self) -> Optional[str]:
        """获取当前线程的 Trace ID"""
        return getattr(self._trace_context, "value", None)

    def log(
        self,
        level: int,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        exc_info=None,
    ):
        """
        记录结构化日志

        Args:
            level: 日志级别 (logging.DEBUG, INFO, etc.)
            action: 操作名称（作为消息主体）
            details: 额外的结构化数据字典
            exc_info: 异常信息（True 表示捕获当前异常）
        """
        extra_dict = {
            "details": details or {},
            "trace_id": self.get_trace_id(),
        }
        self.logger.log(level, action, extra=extra_dict, exc_info=exc_info)

    def debug(self, action: str, details: Optional[Dict[str, Any]] = None):
        self.log(logging.DEBUG, action, details)

    def info(self, action: str, details: Optional[Dict[str, Any]] = None):
        self.log(logging.INFO, action, details)

    def warning(self, action: str, details: Optional[Dict[str, Any]] = None):
        self.log(logging.WARNING, action, details)

    def error(self, action: str, details: Optional[Dict[str, Any]] = None, exc_info=True):
        self.log(logging.ERROR, action, details, exc_info=exc_info)

    def critical(self, action: str, details: Optional[Dict[str, Any]] = None, exc_info=True):
        self.log(logging.CRITICAL, action, details, exc_info=exc_info)


# 全局函数：快速获取 logger
def get_logger(name: str = "local_agent") -> StructuredLogger:
    """获取或创建结构化日志记录器"""
    return StructuredLogger(name)


# 为了向后兼容，保留旧的 logger 接口
class CompatLogger:
    """兼容旧代码的 logger 包装器"""

    def __init__(self, name: str = "local_agent"):
        self._logger = StructuredLogger(name)

    def set_trace_id(self, trace_id: str):
        self._logger.set_trace_id(trace_id)

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, details=kwargs.get("details"))

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, details=kwargs.get("details"))

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, details=kwargs.get("details"))

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, details=kwargs.get("details"), exc_info=kwargs.get("exc_info", True))

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(msg, details=kwargs.get("details"), exc_info=kwargs.get("exc_info", True))


# 创建默认 logger 实例（向后兼容）
try:
    logger = CompatLogger("local_agent")
except Exception as e:
    print(f"[logger] 初始化失败: {e}")
    raise