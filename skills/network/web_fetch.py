"""
网页抓取技能。
抓取网页内容并清洗为纯文本，支持自动识别相对路径。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

from skills.utils.net_utils import fetch_webpage_text

# 技能元数据
SKILL_NAME = "web_fetch"
SKILL_DESCRIPTION = "抓取网页内容并清洗为纯文本，支持自动识别相对路径，处理常见反爬策略。"
SKILL_TRIGGER = "当需要读取网页内容、分析 URL 信息或获取网络数据时使用。"
SKILL_CATEGORY = "network"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "url",
        "type": "string",
        "description": "要抓取的网页 URL 地址"
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "请求超时时间（秒），默认 10 秒",
        "default": 10
    }
]

def execute(url: str, timeout: int = 10, **kwargs):
    """
    执行网页抓取操作。
    
    Args:
        url: 网页 URL
        timeout: 超时时间
        **kwargs: 兼容额外参数（如 max_pages），本技能当前仅支持单页抓取
    
    Returns:
        网页内容或错误信息
    """
    # 忽略未使用的参数以提升兼容性
    return fetch_webpage_text(url, timeout=timeout)