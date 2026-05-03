#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试结构化日志系统和脱敏功能
"""

import os
import sys
import time
import json
from pathlib import Path

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

# 设置环境变量（模拟配置）
os.environ["LOG_FORMAT"] = "json"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["MASKING_ENABLED"] = "true"
os.environ["LOG_FILE_JSON"] = "logs/test_hermes.jsonl"
os.environ["LOG_ASYNC_QUEUE_SIZE"] = "10"
os.environ["LOG_BATCH_SIZE"] = "2"
os.environ["LOG_FLUSH_INTERVAL"] = "1.0"
os.environ["LOG_ROTATION_DAYS"] = "30"
os.environ["LOG_COMPRESS"] = "false"

print("=" * 60)
print("🔍 测试 1: 导入模块")
print("=" * 60)

try:
    from logger import StructuredLogger, get_logger
    from data_masker import masker, DataMasker
    print("✅ 模块导入成功")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("🔍 测试 2: DataMasker 脱敏功能")
print("=" * 60)

test_cases = [
    ("这是正常文本", "这是正常文本"),
    ("Bearer sk-1234567890abcdefghijklmnopqrstuvwxyz123456", "Bearer [REDACTED]"),
    ("API_KEY=sk-abcdef1234567890ghijklmnopqrstuvwxyz", "API_KEY=[REDACTED]"),
    ("使用 ghp_1234567890abcdefghijklmnopqrstuvwxyz 访问", "使用 [REDACTED] 访问"),
    ("AWS密钥 AKIAIOSFODNN7EXAMPLE 请妥善保管", "AWS密钥 [REDACTED] 请妥善保管"),
    ("密码是 $PASSWORD 和 $SECRET_KEY", "密码是 [REDACTED] 和 [REDACTED]"),
]

all_passed = True
for original, expected in test_cases:
    result = masker.mask(original)
    status = "✅" if result == expected else "❌"
    if result != expected:
        all_passed = False
        print(f"{status} 失败: '{original}' -> '{result}' (期望: '{expected}')")
    else:
        print(f"{status} 通过: '{original}' -> '{result}'")

if all_passed:
    print("✅ 所有脱敏测试通过")
else:
    print("❌ 部分脱敏测试失败")

print("\n" + "=" * 60)
print("🔍 测试 3: StructuredLogger 基础功能")
print("=" * 60)

logger = StructuredLogger("test_hermes")

# 测试 Trace ID 设置
logger.set_trace_id("test-trace-12345")
print(f"✅ Trace ID 设置: {logger.get_trace_id()}")

# 测试不同级别的日志
try:
    logger.debug("debug_action", details={"key": "value1", "number": 123})
    logger.info("info_action", details={"status": "started", "user": "test_user"})
    logger.warning("warning_action", details={"reason": "test_warning"})
    logger.error("error_action", details={"error_code": 500})
    print("✅ 基础日志记录成功")
except Exception as e:
    print(f"❌ 基础日志记录失败: {e}")

print("\n" + "=" * 60)
print("🔍 测试 4: 结构化字段和异常记录")
print("=" * 60)

try:
    logger.info(
        "file_operation",
        details={
            "operation": "read",
            "path": "/etc/passwd",
            "size": 1024,
            "sensitive": "Bearer token123",
        },
    )
    print("✅ 结构化详情字段记录成功")
except Exception as e:
    print(f"❌ 结构化详情记录失败: {e}")

try:
    # 测试异常记录
    try:
        raise ValueError("这是一个测试异常")
    except ValueError:
        logger.error("exception_caught", details={"context": "测试异常捕获"})
    print("✅ 异常记录成功")
except Exception as e:
    print(f"❌ 异常记录失败: {e}")

print("\n" + "=" * 60)
print("🔍 测试 5: 脱敏在日志中的效果")
print("=" * 60)

logger.info(
    "sensitive_test",
    details={
        "api_key": "sk-abcdef1234567890ghijklmnopqrstuvwxyz",
        "authorization": "Bearer ghp_1234567890abcdefghijklmnopqrstuvwxyz",
        "aws_key": "AKIAIOSFODNN7EXAMPLE",
        "normal_field": "这是普通字段",
    },
)
print("✅ 敏感信息脱敏日志已记录（请检查日志文件）")

print("\n" + "=" * 60)
print("🔍 测试 6: 异步写入和文件生成")
print("=" * 60)

# 等待异步写入完成
time.sleep(3)

log_file = Path("logs/test_hermes.jsonl")
if log_file.exists():
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    print(f"✅ 日志文件已生成，共 {len(lines)} 条记录")

    # 检查前3条记录的格式
    for i, line in enumerate(lines[:3]):
        try:
            entry = json.loads(line)
            required_fields = ["timestamp", "level", "component", "action"]
            if all(f in entry for f in required_fields):
                print(f"  记录 {i+1}: ✅ JSON 格式正确，action={entry['action']}, level={entry['level']}")
            else:
                print(f"  记录 {i+1}: ❌ 缺少必要字段")
        except json.JSONDecodeError as e:
            print(f"  记录 {i+1}: ❌ JSON 解析失败: {e}")
else:
    print("❌ 日志文件未生成")

print("\n" + "=" * 60)
print("🔍 测试 7: 脱敏统计")
print("=" * 60)

stats = masker.get_stats()
print(f"📊 脱敏统计:")
print(f"  总脱敏次数: {stats.get('total_masked', 0)}")
print(f"  按模式统计: {json.dumps(stats.get('by_pattern', {}), indent=2, ensure_ascii=False)}")

print("\n" + "=" * 60)
print("🎉 所有测试完成！")
print("=" * 60)
print("\n📝 请检查生成的日志文件: logs/test_hermes.jsonl")
print("📊 脱敏统计文件: logs/masking_stats.json")
print("\n💡 下一步: 设置环境变量 LOG_FORMAT=json 以启用结构化日志")
print("   然后在你的代码中使用: from logger import get_logger; logger = get_logger('your_module')")
