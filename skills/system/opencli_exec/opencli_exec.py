"""
OpenCLI 命令执行技能。
用于执行 opencli 命令，例如 opencli help、opencli version 等。
Author: 破执
Date: 2026-05-14
"""

import subprocess
import shutil
import os

from logger import get_logger

logger = get_logger('opencli_exec')

# 技能元数据
SKILL_NAME = "opencli_exec"
SKILL_DESCRIPTION = "执行 opencli 命令，获取命令输出结果。支持 help、version、list 等所有 opencli 子命令。"
SKILL_TRIGGER = "当需要执行 opencli 命令、查询 opencli 版本、获取帮助信息或执行其他 opencli 相关操作时使用。"
SKILL_CATEGORY = "system"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "command",
        "type": "string",
        "description": "要执行的 opencli 命令（不包含 'opencli' 前缀），例如 'help'、'version'、'list' 等"
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "执行超时时间（秒），默认 30 秒",
        "default": 30
    }
]


def _find_opencli() -> str:
    """
    查找 opencli 可执行文件路径。
    优先查找环境变量 PATH 中的 opencli，其次查找常见安装路径。
    """
    # 1. 尝试从 PATH 中查找
    opencli_path = shutil.which("opencli")
    if opencli_path:
        return opencli_path

    # 2. 尝试常见安装路径（Windows / Linux / macOS）
    common_paths = [
        # Windows
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\opencli\opencli.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\opencli\opencli.exe"),
        os.path.expandvars(r"%PROGRAMFILES(x86)%\opencli\opencli.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\opencli\opencli.exe"),
        r"C:\Program Files\opencli\opencli.exe",
        r"C:\Program Files (x86)\opencli\opencli.exe",
        # Linux / macOS
        "/usr/local/bin/opencli",
        "/usr/bin/opencli",
        "/opt/opencli/bin/opencli",
        os.path.expanduser("~/.local/bin/opencli"),
        os.path.expanduser("~/bin/opencli"),
    ]

    for path in common_paths:
        if os.path.isfile(path):
            return path

    return "opencli"


def execute(command: str = "", timeout: int = 30, **kwargs) -> str:
    """
    执行 opencli 命令。

    Args:
        command: 要执行的 opencli 子命令（不包含 'opencli' 前缀），例如 'help'、'version'
        timeout: 执行超时时间（秒）
        **kwargs: 额外参数（忽略）

    Returns:
        命令执行结果或错误信息
    """
    opencli_path = _find_opencli()

    # 构建完整命令
    if command and command.strip():
        full_command = f"{opencli_path} {command.strip()}"
    else:
        full_command = opencli_path

    logger.info(f"执行 opencli 命令: {full_command}")

    try:
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )

        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if result.returncode != 0:
            error_msg = stderr or stdout or f"命令退出码: {result.returncode}"
            logger.error(f"opencli 命令执行失败: {error_msg}")
            return f"❌ opencli 命令执行失败 (退出码 {result.returncode}):\n{error_msg}"

        if stdout:
            return f"✅ opencli 执行成功:\n{stdout}"
        else:
            return "✅ opencli 执行成功，无输出"

    except subprocess.TimeoutExpired:
        logger.error(f"opencli 命令执行超时 (超过 {timeout}s)")
        return f"❌ opencli 命令执行超时 (超过 {timeout}s)"
    except FileNotFoundError:
        logger.error("未找到 opencli 可执行文件")
        return (
            "❌ 未找到 opencli 可执行文件。\n"
            "请确认 opencli 已正确安装，并且已添加到系统 PATH 环境变量中。\n"
            "常见安装路径:\n"
            "  - Windows: %LOCALAPPDATA%\\Programs\\opencli\\opencli.exe\n"
            "  - Linux: /usr/local/bin/opencli\n"
            "  - macOS: /usr/local/bin/opencli"
        )
    except Exception as e:
        logger.error(f"opencli 命令执行异常: {e}")
        return f"❌ opencli 命令执行异常: {str(e)}"
