"""
Python 代码执行技能。
安全执行 Python 代码，支持超时控制和输出限制。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

from skills.utils.code_utils import execute_python_code

# 技能元数据
SKILL_NAME = "python_exec"
SKILL_DESCRIPTION = "安全执行 Python 代码，支持超时控制和输出限制。"
SKILL_TRIGGER = "当需要运行 Python 脚本、测试代码或执行计算任务时使用。"
SKILL_CATEGORY = "code"
SKILL_REQUIRES_CONFIRMATION = True  # 代码执行需要确认
SKILL_PARAMETERS = [
    {
        "name": "code",
        "type": "string",
        "description": "要执行的 Python 代码"
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "执行超时时间（秒），默认 10 秒",
        "default": 10
    }
]

def execute(code: str, timeout: int = 10) -> str:
    """
    执行 Python 代码。
    
    Args:
        code: Python 代码
        timeout: 超时时间
        
    Returns:
        执行结果或错误信息
    """
    return execute_python_code(code, timeout=timeout)