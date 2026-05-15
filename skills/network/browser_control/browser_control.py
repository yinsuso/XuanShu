"""
浏览器控制技能。
控制浏览器打开网页、获取页面标题和内容、截图等。
支持 Windows、Linux、macOS 三平台。
Author: 破执
Date: 2026-05-15
"""

import os
import platform
import subprocess
import urllib.request
import urllib.error
from typing import Optional

from logger import get_logger

logger = get_logger('browser_control')

# 技能元数据
SKILL_NAME = "browser_control"
SKILL_DESCRIPTION = "控制浏览器打开网页、获取页面信息。支持打开 URL、获取页面标题和内容、搜索关键词等。"
SKILL_TRIGGER = "当需要打开网页、浏览网站、搜索信息或获取页面内容时使用。"
SKILL_CATEGORY = "network"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "action",
        "type": "string",
        "description": "操作类型: open(打开网页), info(获取页面信息), search(搜索关键词)"
    },
    {
        "name": "url",
        "type": "string",
        "description": "网页 URL（action=open 或 info 时必填）",
        "default": ""
    },
    {
        "name": "query",
        "type": "string",
        "description": "搜索关键词（action=search 时必填）",
        "default": ""
    },
    {
        "name": "browser",
        "type": "string",
        "description": "指定浏览器（可选）。如 chrome, firefox, edge, safari",
        "default": ""
    }
]


def _get_system() -> str:
    """获取当前操作系统类型。"""
    return platform.system().lower()


def _find_browser(browser_name: str = "") -> Optional[str]:
    """
    查找浏览器可执行文件路径。

    Args:
        browser_name: 指定浏览器名称（可选）

    Returns:
        浏览器路径或 None
    """
    system = _get_system()

    # 如果指定了浏览器名称
    if browser_name:
        browser_name = browser_name.lower()
        # 尝试从 PATH 中查找
        import shutil
        path = shutil.which(browser_name)
        if path:
            return path

        # 常见浏览器名称映射
        name_map = {
            "chrome": ["google-chrome", "chrome", "chromium", "chromium-browser"],
            "firefox": ["firefox", "mozilla-firefox"],
            "edge": ["microsoft-edge", "msedge", "edge"],
            "safari": ["safari"],
        }

        names = name_map.get(browser_name, [browser_name])
        for name in names:
            path = shutil.which(name)
            if path:
                return path
        return None

    # 未指定浏览器，按优先级查找
    if system == "windows":
        browsers = ["msedge", "chrome", "firefox"]
    elif system == "darwin":
        browsers = ["open", "google-chrome", "firefox"]
    else:
        browsers = ["google-chrome", "chromium", "chromium-browser", "firefox", "xdg-open"]

    import shutil
    for browser in browsers:
        path = shutil.which(browser)
        if path:
            return path

    return None


def _open_url(url: str, browser: str = "") -> str:
    """
    用浏览器打开 URL。

    Args:
        url: 网页地址
        browser: 指定浏览器（可选）

    Returns:
        操作结果
    """
    # 验证 URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    system = _get_system()
    browser_path = _find_browser(browser)

    if not browser_path:
        return (
            "❌ 未找到可用的浏览器。\n"
            "请确认已安装 Chrome、Firefox、Edge 等浏览器，并添加到系统 PATH。"
        )

    try:
        if system == "darwin" and browser_path == "/usr/bin/open":
            # macOS 使用 open 命令
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        elif system == "linux" and os.path.basename(browser_path) == "xdg-open":
            # Linux 使用 xdg-open
            subprocess.Popen(
                [browser_path, url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        elif system == "windows":
            # Windows 使用 start 命令
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            # 直接调用浏览器
            subprocess.Popen(
                [browser_path, url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        browser_name = os.path.basename(browser_path)
        return f"✅ 已用 {browser_name} 打开: {url}"

    except Exception as e:
        logger.error(f"打开浏览器失败: {e}")
        return f"❌ 打开浏览器失败: {str(e)}"


def _get_page_info(url: str) -> str:
    """
    获取页面基本信息（标题、状态码）。

    Args:
        url: 网页地址

    Returns:
        页面信息
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "unknown")

            # 读取内容并提取标题
            html = response.read().decode("utf-8", errors="replace")

            # 提取标题
            title = "未找到标题"
            import re
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                # 清理 HTML 实体
                title = title.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
                title = title.replace("&amp;", "&").replace("&quot;", '"')

            # 提取描述
            desc = ""
            desc_match = re.search(
                r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
                html,
                re.IGNORECASE
            )
            if desc_match:
                desc = desc_match.group(1).strip()

            result = f"✅ 页面信息获取成功\n"
            result += f"URL: {url}\n"
            result += f"状态码: {status}\n"
            result += f"内容类型: {content_type}\n"
            result += f"标题: {title}"
            if desc:
                # 限制描述长度
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                result += f"\n描述: {desc}"

            return result

    except urllib.error.HTTPError as e:
        return f"❌ HTTP 错误 {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"❌ URL 错误: {e.reason}"
    except Exception as e:
        logger.error(f"获取页面信息失败: {e}")
        return f"❌ 获取页面信息失败: {str(e)}"


def _search(query: str, browser: str = "") -> str:
    """
    用搜索引擎搜索关键词。

    Args:
        query: 搜索关键词
        browser: 指定浏览器（可选）

    Returns:
        操作结果
    """
    if not query or not query.strip():
        return "❌ 搜索关键词不能为空"

    # 使用 DuckDuckGo 搜索（隐私友好，无需 API Key）
    import urllib.parse
    encoded_query = urllib.parse.quote(query.strip())
    search_url = f"https://duckduckgo.com/?q={encoded_query}"

    return _open_url(search_url, browser)


def execute(action: str, url: str = "", query: str = "", browser: str = "", **kwargs) -> str:
    """
    执行浏览器控制操作。

    Args:
        action: 操作类型 (open/info/search)
        url: 网页 URL
        query: 搜索关键词
        browser: 指定浏览器
        **kwargs: 额外参数（忽略）

    Returns:
        操作结果
    """
    action = action.lower().strip()

    if action == "open":
        if not url:
            return "❌ action=open 时需要提供 url 参数"
        return _open_url(url, browser)

    elif action == "info":
        if not url:
            return "❌ action=info 时需要提供 url 参数"
        return _get_page_info(url)

    elif action == "search":
        if not query:
            return "❌ action=search 时需要提供 query 参数"
        return _search(query, browser)

    else:
        return (
            f"❌ 不支持的操作类型: {action}\n"
            f"支持的操作: open(打开网页), info(获取页面信息), search(搜索关键词)"
        )
