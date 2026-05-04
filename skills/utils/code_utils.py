#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码执行公共工具模块。
提供安全的 Python 代码执行、沙箱限制、超时控制等功能。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

import subprocess
import sys
import os
import tempfile
import time
from typing import Optional, Tuple
from logger import get_logger
logger = get_logger('code_utils')

# 导入安全沙箱（可选）
try:
    from security.sandbox.docker_sandbox import get_default_sandbox, DockerSandbox
    DOCKER_SANDBOX_AVAILABLE = True
except ImportError:
    DOCKER_SANDBOX_AVAILABLE = False

# 导入配置
try:
    from config import SANDBOX_ENABLED, PROJECT_ROOT
except ImportError:
    SANDBOX_ENABLED = True  # 默认启用
    PROJECT_ROOT = os.getcwd()

# 全局沙箱实例（延迟初始化）
_sandbox_instance = None


def execute_python_code(code: str, timeout: int = 10, max_output: int = 2000) -> str:
    """
    安全执行 Python 代码（支持 Docker 沙箱或 subprocess 降级）。
    
    Args:
        code: Python 代码字符串
        timeout: 执行超时时间（秒）
        max_output: 最大返回长度
        
    Returns:
        执行结果或错误信息
    """
    # 尝试使用 Docker 沙箱（高安全性）
    if SANDBOX_ENABLED and DOCKER_SANDBOX_AVAILABLE:
        try:
            global _sandbox_instance
            if _sandbox_instance is None:
                _sandbox_instance = get_default_sandbox()
            
            if _sandbox_instance.is_available():
                result = _sandbox_instance.execute(code, skill_name="python_exec")
                # 即使使用沙箱，也需要限制输出长度
                if len(result) > max_output:
                    result = result[:max_output] + "\n... (输出过长，已截断)"
                return result
            else:
                # 沙箱不可用，降级
                logger.warning("Docker 沙箱不可用，降级到 subprocess 模式")
        except Exception as e:
            logger.error("Docker 沙箱执行失败，降级", details={"error": str(e)})
    
    # 降级：传统 subprocess 模式
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        start_time = time.time()
        
        # 执行代码
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(temp_file)
        )
        
        elapsed = time.time() - start_time
        
        # 清理临时文件
        os.unlink(temp_file)
        
        # 处理输出
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode != 0:
            if error:
                return f"❌ 执行失败 (耗时 {elapsed:.2f}s):\n{error}"
            else:
                return f"❌ 执行失败 (耗时 {elapsed:.2f}s)，无错误信息"
        
        # 限制输出长度
        if len(output) > max_output:
            output = output[:max_output] + "\n... (输出过长，已截断)"
        
        if output:
            return f"✅ 执行成功 (耗时 {elapsed:.2f}s):\n{output}"
        else:
            return f"✅ 执行成功 (耗时 {elapsed:.2f}s)，无输出"
    
    except subprocess.TimeoutExpired:
        return f"❌ 执行超时 (超过 {timeout}s)"
    except Exception as e:
        return f"❌ 执行异常：{str(e)}"


def execute_shell_command(command: str, timeout: int = 10, max_output: int = 2000) -> str:
    """
    安全执行 Shell 命令（仅限白名单命令）。
    
    Args:
        command: Shell 命令
        timeout: 执行超时时间
        max_output: 最大返回长度
        
    Returns:
        执行结果或错误信息
    """
    # 白名单校验
    allowed_commands = ['ls', 'pwd', 'echo', 'cat', 'head', 'tail', 'wc', 'find', 'grep']
    cmd_parts = command.split()
    if not cmd_parts or cmd_parts[0] not in allowed_commands:
        return f"❌ 安全拦截：命令 '{cmd_parts[0]}' 不在白名单中"
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode != 0:
            if error:
                return f"❌ 执行失败:\n{error}"
            else:
                return f"❌ 执行失败，无错误信息"
        
        # 限制输出长度
        if len(output) > max_output:
            output = output[:max_output] + "\n... (输出过长，已截断)"
        
        if output:
            return f"✅ 执行成功:\n{output}"
        else:
            return f"✅ 执行成功，无输出"
    
    except subprocess.TimeoutExpired:
        return f"❌ 执行超时 (超过 {timeout}s)"
    except Exception as e:
        return f"❌ 执行异常：{str(e)}"
