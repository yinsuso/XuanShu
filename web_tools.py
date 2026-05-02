import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Optional

def fetch_url(url: str, timeout: int = 10) -> str:
    """
    抓取网页内容并清洗为纯文本。
    支持自动识别相对路径，处理常见反爬策略。
    """
    try:
        # 基础校验
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
            parsed = urlparse(url)
        
        if parsed.scheme not in ['http', 'https']:
            return f"❌ 不支持的协议: {parsed.scheme}"

        # 设置请求头，模拟浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        # 发送请求
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()

        # 编码处理
        if response.encoding is None:
            response.encoding = response.apparent_encoding
        
        html = response.text
        soup = BeautifulSoup(html, 'lxml')

        # 清洗 HTML：移除脚本、样式、导航等无关内容
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
            tag.decompose()

        # 提取文本
        text = soup.get_text(separator='\n', strip=True)
        
        # 清理多余空白
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # 限制长度（防止上下文溢出）
        if len(text) > 4000:
            text = text[:4000] + "\n... (内容过长，已截断)"

        return f"✅ 成功抓取:\nURL: {url}\n内容:\n{text}"

    except requests.exceptions.Timeout:
        return f"❌ 请求超时: {url}"
    except requests.exceptions.RequestException as e:
        return f"❌ 请求失败: {str(e)}"
    except Exception as e:
        return f"❌ 解析错误: {str(e)}"

def search_web(query: str) -> str:
    """
    使用 DuckDuckGo 搜索网络信息。
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(f"- {r['title']}: {r['href']}")
        return "\n".join(results) if results else "未找到相关信息。"
    except Exception as e:
        return f"搜索错误: {str(e)}"