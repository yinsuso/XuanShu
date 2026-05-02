"""
目录列表技能。
列出指定目录下的文件和子目录。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

from skills.utils.file_utils import list_directory_safe

# 技能元数据
SKILL_NAME = "file_list"
SKILL_DESCRIPTION = "列出指定目录下的文件和子目录。"
SKILL_TRIGGER = "当需要查看项目结构、查找文件时使用。"
SKILL_CATEGORY = "io"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "path",
        "type": "string",
        "description": "目录路径（相对于项目根目录）",
        "default": "."
    }
]

def execute(path: str = ".") -> str:
    """
    执行目录列表操作。
    
    Args:
        path: 目录路径
        
    Returns:
        目录列表或错误信息
    """
    return list_directory_safe(path)