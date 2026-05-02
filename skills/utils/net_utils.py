"""
网络请求公共工具模块。
提供安全的 HTTP 请求、网页抓取、内容清洗等基础功能。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Optional

# 默认请求头，模拟浏览器
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

def safe_request(url: str, method: str = "GET", timeout: int = 10, headers: Optional[dict] = None, **kwargs) -> dict:
    """
    安全的 HTTP 请求封装。
    
    Args:
        url: 请求 URL
        method: 请求方法 (GET, POST 等)
        timeout: 超时时间（秒）
        headers: 自定义请求头
        **kwargs: 其他 requests 参数
        
    Returns:
        {"success": bool, "status_code": int, "text": str, "error": str}
    """
    try:
        # 协议校验
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
            parsed = urlparse(url)
        
        if parsed.scheme not in ['http', 'https']:
            return {"success": False, "status_code": 0, "text": "", "error": f"不支持的协议：{parsed.scheme}"}
        
        # 合并请求头
        req_headers = DEFAULT_HEADERS.copy()
        if headers:
            req_headers.update(headers)
        
        # 发送请求
        response = requests.request(
            method=method,
            url=url,
            headers=req_headers,
            timeout=timeout,
            allow_redirects=True,
            **kwargs
        )
        response.raise_for_status()
        
        # 编码处理
        if response.encoding is None:
            response.encoding = response.apparent_encoding
        
        return {
            "success": True,
            "status_code": response.status_code,
            "text": response.text,
            "error": ""
        }
    
    except requests.exceptions.Timeout:
        return {"success": False, "status_code": 0, "text": "", "error": f"请求超时：{url}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "status_code": 0, "text": "", "error": f"请求失败：{str(e)}"}
    except Exception as e:
        return {"success": False, "status_code": 0, "text": "", "error": f"未知错误：{str(e)}"}

def fetch_webpage_text(url: str, timeout: int = 10, max_length: int = 4000) -> str:
    """
    抓取网页并清洗为纯文本。
    
    Args:
        url: 网页 URL
        timeout: 超时时间
        max_length: 最大返回长度
        
    Returns:
        清洗后的文本内容或错误信息
    """
    result = safe_request(url, timeout=timeout)
    
    if not result["success"]:
        return f"❌ {result['error']}"
    
    try:
        html = result["text"]
        soup = BeautifulSoup(html, 'lxml')
        
        # 清洗 HTML：移除脚本、样式、导航等无关内容
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
            tag.decompose()
        
        # 提取文本
        text = soup.get_text(separator='\n', strip=True)
        
        # 清理多余空白
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # 限制长度
        if len(text) > max_length:
            text = text[:max_length] + "\n... (内容过长，已截断)"
        
        return f"✅ 成功抓取:\nURL: {url}\n内容:\n{text}"
    
    except Exception as e:
        return f"❌ 解析错误：{str(e)}"

def fetch_json(url: str, timeout: int = 10) -> dict:
    """
    抓取 JSON 数据。
    
    Args:
        url: JSON 数据 URL
        timeout: 超时时间
        
    Returns:
        {"success": bool, "data": dict/list, "error": str}
    """
    result = safe_request(url, timeout=timeout)
    
    if not result["success"]:
        return {"success": False, "data": None, "error": result["error"]}
    
    try:
        import json
        data = json.loads(result["text"])
        return {"success": True, "data": data, "error": ""}
    except Exception as e:
        return {"success": False, "data": None, "error": f"JSON 解析失败：{str(e)}"}