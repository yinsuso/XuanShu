"""
文件读取技能。
读取指定文件内容，支持大文件分块读取。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

from skills.utils.file_utils import read_file_safe

# 技能元数据
SKILL_NAME = "file_read"
SKILL_DESCRIPTION = "读取指定文件内容，支持大文件分块读取。"
SKILL_TRIGGER = "当需要查看文件内容、分析代码或读取配置文件时使用。"
SKILL_CATEGORY = "io"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "path",
        "type": "string",
        "description": "文件绝对路径或相对路径（相对于项目根目录）"
    },
    {
        "name": "lines",
        "type": "integer",
        "description": "读取行数（可选），默认读取全部",
        "default": 0
    }
]

def execute(path: str, lines: int = 0) -> str:
    """
    执行文件读取操作。
    
    Args:
        path: 文件路径
        lines: 读取行数
        
    Returns:
        文件内容或错误信息
    """
    return read_file_safe(path, lines=lines)