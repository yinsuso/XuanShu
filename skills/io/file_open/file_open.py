"""
文件打开技能。
使用系统默认程序打开文件，模拟双击打开的效果。
支持 Windows、Linux、macOS 三平台。
Author: 破执
Date: 2026-05-15
"""

import os
import platform
import subprocess

from logger import get_logger

logger = get_logger('file_open')

# 技能元数据
SKILL_NAME = "file_open"
SKILL_DESCRIPTION = "使用系统默认程序打开文件，模拟双击打开的效果。支持文档、图片、视频、网页等各种文件类型。"
SKILL_TRIGGER = "当需要用系统默认程序打开文件、预览文档、播放媒体或启动应用程序时使用。"
SKILL_CATEGORY = "io"
SKILL_REQUIRES_CONFIRMATION = True
SKILL_PARAMETERS = [
    {
        "name": "path",
        "type": "string",
        "description": "要打开的文件路径（绝对路径或相对项目根目录的路径）"
    },
    {
        "name": "application",
        "type": "string",
        "description": "指定用哪个程序打开（可选）。如未指定则使用系统默认程序",
        "default": ""
    },
    {
        "name": "wait",
        "type": "boolean",
        "description": "是否等待程序关闭后再返回（默认 False）",
        "default": False
    }
]


def _get_system() -> str:
    """获取当前操作系统类型。"""
    return platform.system().lower()


def _validate_path(file_path: str) -> tuple:
    """
    验证文件路径。
    返回 (是否有效, 绝对路径或错误信息)
    """
    if not file_path or not file_path.strip():
        return False, "文件路径不能为空"

    # 处理相对路径
    if not os.path.isabs(file_path):
        # 尝试相对于项目根目录
        from config import PROJECT_ROOT
        abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, file_path))
    else:
        abs_path = os.path.abspath(file_path)

    # 检查路径是否存在
    if not os.path.exists(abs_path):
        return False, f"路径不存在: {abs_path}"

    return True, abs_path


def _open_with_default(file_path: str, wait: bool = False) -> str:
    """
    使用系统默认程序打开文件。

    Args:
        file_path: 文件绝对路径
        wait: 是否等待程序关闭

    Returns:
        操作结果
    """
    system = _get_system()

    try:
        if system == "windows":
            # Windows: 使用 start 命令
            # start 命令的第一个参数是窗口标题，所以传空字符串
            cmd = ["cmd", "/c", "start", "", file_path]
            subprocess.Popen(
                cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return f"✅ 已使用默认程序打开: {os.path.basename(file_path)}"

        elif system == "darwin":
            # macOS: 使用 open 命令
            cmd = ["open", file_path]
            if wait:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            return f"✅ 已使用默认程序打开: {os.path.basename(file_path)}"

        else:
            # Linux: 使用 xdg-open
            cmd = ["xdg-open", file_path]
            if wait:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            return f"✅ 已使用默认程序打开: {os.path.basename(file_path)}"

    except FileNotFoundError as e:
        logger.error(f"系统命令未找到: {e}")
        if system == "linux":
            return "❌ 未找到 xdg-open 命令。请安装 xdg-utils 包: sudo apt-get install xdg-utils"
        elif system == "darwin":
            return "❌ 未找到 open 命令。这是 macOS 系统命令，不应该缺失。"
        else:
            return f"❌ 打开文件失败: {str(e)}"
    except Exception as e:
        logger.error(f"打开文件失败: {e}")
        return f"❌ 打开文件失败: {str(e)}"


def _open_with_app(file_path: str, application: str, wait: bool = False) -> str:
    """
    使用指定程序打开文件。

    Args:
        file_path: 文件绝对路径
        application: 程序名称或路径
        wait: 是否等待程序关闭

    Returns:
        操作结果
    """
    system = _get_system()

    try:
        if system == "windows":
            # Windows: start "" "程序" "文件"
            cmd = ["cmd", "/c", "start", "", application, file_path]
            subprocess.Popen(
                cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        elif system == "darwin":
            # macOS: open -a "程序" "文件"
            cmd = ["open", "-a", application, file_path]
            if wait:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

        else:
            # Linux: 直接调用程序
            cmd = [application, file_path]
            if wait:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

        return f"✅ 已使用 {application} 打开: {os.path.basename(file_path)}"

    except FileNotFoundError:
        return f"❌ 未找到程序: {application}。请确认程序已安装并添加到 PATH 中。"
    except Exception as e:
        logger.error(f"使用指定程序打开失败: {e}")
        return f"❌ 打开失败: {str(e)}"


def execute(path: str, application: str = "", wait: bool = False, **kwargs) -> str:
    """
    使用系统默认程序或指定程序打开文件。

    Args:
        path: 文件路径
        application: 指定程序（可选）
        wait: 是否等待程序关闭
        **kwargs: 额外参数（忽略）

    Returns:
        操作结果
    """
    # 验证路径
    valid, result = _validate_path(path)
    if not valid:
        return f"❌ {result}"

    file_path = result
    logger.info(f"打开文件: {file_path}, 程序: {application or '默认'}, 等待: {wait}")

    # 判断使用默认程序还是指定程序
    if application and application.strip():
        return _open_with_app(file_path, application.strip(), wait)
    else:
        return _open_with_default(file_path, wait)
