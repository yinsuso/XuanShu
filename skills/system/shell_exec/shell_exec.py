"""
Shell 命令执行技能。
支持 Windows、Linux、macOS 三平台命令行执行，自动识别当前系统并适配。
Author: 破执
Date: 2026-05-15
"""

import subprocess
import shutil
import os
import platform

from logger import get_logger

logger = get_logger('shell_exec')

# 技能元数据
SKILL_NAME = "shell_exec"
SKILL_DESCRIPTION = "执行系统 Shell 命令，支持 Windows、Linux、macOS 三平台。自动识别当前操作系统并适配命令格式。"
SKILL_TRIGGER = "当需要执行系统命令、查看系统信息、操作文件系统或运行命令行工具时使用。"
SKILL_CATEGORY = "system"
SKILL_REQUIRES_CONFIRMATION = True
SKILL_PARAMETERS = [
    {
        "name": "command",
        "type": "string",
        "description": "要执行的命令内容"
    },
    {
        "name": "shell",
        "type": "boolean",
        "description": "是否使用 shell 执行（默认 True）。简单命令可设为 False 更安全",
        "default": True
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "执行超时时间（秒），默认 30 秒",
        "default": 30
    },
    {
        "name": "working_dir",
        "type": "string",
        "description": "工作目录（可选），默认当前目录",
        "default": ""
    }
]


def _get_system_info() -> dict:
    """获取当前系统信息。"""
    system = platform.system().lower()
    return {
        "os": system,
        "is_windows": system == "windows",
        "is_linux": system == "linux",
        "is_macos": system == "darwin",
        "shell": "cmd.exe" if system == "windows" else "/bin/bash"
    }


def _validate_command(command: str, sys_info: dict) -> tuple:
    """
    命令安全性校验。
    返回 (是否允许, 错误信息)
    """
    if not command or not command.strip():
        return False, "命令不能为空"

    command_lower = command.lower().strip()

    # 危险命令黑名单（跨平台）
    dangerous_patterns = [
        # 破坏性操作
        "rm -rf /", "rd /s /q \\", "del /f /s /q \\",
        "format ", "mkfs.", "dd if=",
        # 系统关键文件
        " > /etc/passwd", " > /etc/shadow",
        # 远程下载执行
        "curl .*| *sh", "wget .*| *sh",
        "powershell .*-enc", "powershell .*-encoded",
        # 注册表破坏
        "reg delete", "reg add",
    ]

    for pattern in dangerous_patterns:
        if pattern in command_lower:
            return False, f"命令包含危险操作，已被安全拦截: {pattern}"

    return True, ""


def execute(command: str, shell: bool = True, timeout: int = 30, working_dir: str = "", **kwargs) -> str:
    """
    执行系统 Shell 命令。

    Args:
        command: 要执行的命令内容
        shell: 是否使用 shell 执行（默认 True）
        timeout: 执行超时时间（秒）
        working_dir: 工作目录（可选）
        **kwargs: 额外参数（忽略）

    Returns:
        命令执行结果或错误信息
    """
    if not command or not command.strip():
        return "❌ 命令不能为空"

    sys_info = _get_system_info()
    logger.info(f"执行 {sys_info['os']} 命令: {command}")

    # 安全性校验
    allowed, error_msg = _validate_command(command, sys_info)
    if not allowed:
        logger.warning(f"命令被安全拦截: {command}")
        return f"❌ {error_msg}"

    # 处理工作目录
    cwd = None
    if working_dir and working_dir.strip():
        cwd = os.path.abspath(working_dir.strip())
        if not os.path.isdir(cwd):
            return f"❌ 工作目录不存在: {cwd}"

    try:
        # Windows 下特殊处理
        if sys_info["is_windows"] and shell:
            # 检测是否使用 PowerShell 语法
            ps_commands = ["get-", "set-", "write-", "invoke-", "start-", "stop-", "new-", "remove-"]
            is_ps = any(command.lower().strip().startswith(cmd) for cmd in ps_commands)

            if is_ps:
                # PowerShell 命令
                result = subprocess.run(
                    ["powershell.exe", "-Command", command],
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd
                )
            else:
                # CMD 命令
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="gbk" if sys_info["is_windows"] else "utf-8",
                    errors="replace",
                    cwd=cwd
                )
        else:
            # Linux / macOS
            if shell:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd
                )
            else:
                # 不使用 shell，解析命令
                result = subprocess.run(
                    command.split(),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd
                )

        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if result.returncode != 0:
            error_msg = stderr or stdout or f"命令退出码: {result.returncode}"
            logger.error(f"命令执行失败: {error_msg}")
            return f"❌ 命令执行失败 (退出码 {result.returncode}):\n{error_msg}"

        # 合并输出
        output = stdout
        if stderr:
            output += f"\n[stderr]:\n{stderr}"

        if output:
            # 限制输出长度
            max_output = 3000
            if len(output) > max_output:
                output = output[:max_output] + "\n... (输出过长，已截断)"
            return f"✅ 执行成功 ({sys_info['os']}):\n{output}"
        else:
            return f"✅ 执行成功 ({sys_info['os']})，无输出"

    except subprocess.TimeoutExpired:
        logger.error(f"命令执行超时 (超过 {timeout}s)")
        return f"❌ 命令执行超时 (超过 {timeout}s)"
    except FileNotFoundError as e:
        logger.error(f"命令未找到: {e}")
        return f"❌ 命令未找到: {str(e)}\n请确认命令已安装并添加到系统 PATH 中。"
    except Exception as e:
        logger.error(f"命令执行异常: {e}")
        return f"❌ 命令执行异常: {str(e)}"
