"""
文件写入技能。
写入内容到指定文件，自动创建父目录。
Author: 破执
Date: 2026-04-30
"""

from skills.utils.file_utils import write_file_safe

# 技能元数据
SKILL_NAME = "file_write"
SKILL_DESCRIPTION = "写入内容到指定文件，自动创建父目录。"
SKILL_TRIGGER = "当需要创建新文件、修改代码或保存配置时使用。"
SKILL_CATEGORY = "io"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "path",
        "type": "string",
        "description": "文件绝对路径或相对路径"
    },
    {
        "name": "content",
        "type": "string",
        "description": "要写入的内容"
    }
]

def execute(path: str, content: str, **kwargs) -> str:
    """
    执行文件写入操作。
    
    Args:
        path: 文件路径
        content: 要写入的内容
        **kwargs: 额外参数（忽略）
    
    Returns:
        操作结果
    """
    return write_file_safe(path, content)