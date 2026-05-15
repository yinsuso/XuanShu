"""
招标信息查询技能。
访问 http://www.sizebid.com/bid-information.html 查询招标信息，使用 bs4 解析数据。
Author: XuanShu Agent
Date: 2026-05-13
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import re
from typing import List, Dict, Optional

from skills.utils.net_utils import safe_request, DEFAULT_HEADERS

# 技能元数据
SKILL_NAME = "bidding_info_search"
SKILL_DESCRIPTION = "查询招标信息、采购公告、项目招标等招投标相关信息。通过关键词和省份筛选，获取招标标题和链接。支持固定触发方式：招标搜索：关键词。"
SKILL_TRIGGER = "当用户需要查询招标信息、采购公告、项目招标、招投标信息时使用。触发方式包括：搜索招标信息、查找招标项目、网上找找招投标、招标搜索：关键词 等。"
SKILL_CATEGORY = "network"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "keyword",
        "type": "string",
        "description": "搜索关键词（必填），如：设备采购、工程建设、轴承、空调。支持通过'招标搜索：关键词'方式触发。"
    },
    {
        "name": "province",
        "type": "string",
        "description": "省份（可选），如：北京、上海、广东、浙江",
        "default": ""
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "请求超时时间（秒），默认 30 秒",
        "default": 30
    }
]

def clean_html_tags(text: str) -> str:
    """
    去除文本中的 HTML 标签。

    Args:
        text: 包含 HTML 标签的文本

    Returns:
        纯文本内容
    """
    if not text:
        return ""
    # 使用 BeautifulSoup 去除标签
    soup = BeautifulSoup(text, 'lxml')
    return soup.get_text(separator=' ', strip=True)

def execute(keyword: str, province: str = "", timeout: int = 30, **kwargs) -> str:
    """
    执行招标信息查询操作。

    Args:
        keyword: 搜索关键词
        province: 省份（可选）
        timeout: 超时时间
        **kwargs: 兼容额外参数

    Returns:
        招标信息列表（Markdown 格式）
    """
    try:
        # 构建 URL
        base_url = "http://www.sizebid.com/bid-information.html"
        params = {
            "keyWord": keyword,
            "period": "",
            "province": province,
            "city": ""
        }

        # 构建查询字符串
        query_parts = []
        for key, value in params.items():
            if value:
                query_parts.append(f"{quote(key)}={quote(value)}")
            else:
                query_parts.append(f"{quote(key)}=")
        query_string = "&".join(query_parts)
        full_url = f"{base_url}?{query_string}"

        # 发送请求
        result = safe_request(full_url, timeout=timeout)

        if not result["success"]:
            return f"❌ 查询失败：{result['error']}"

        html = result["text"]
        soup = BeautifulSoup(html, 'lxml')

        # 查找 id 为 content-area 的元素
        content_area = soup.find(id="content-area")

        if not content_area:
            return f"❌ 未找到内容区域，请检查页面结构是否变化。\nURL: {full_url}"

        # 获取所有 class="row-info" 的 div 标签，每个代表一个招标项目
        row_infos = content_area.find_all('div', class_='row-info')

        if not row_infos:
            return f"✅ 查询完成，但未找到相关招标信息。\nURL: {full_url}"

        # 构建结果
        output_lines = [f"✅ 招标信息查询成功"]
        output_lines.append(f"关键词: {keyword}")
        if province:
            output_lines.append(f"省份: {province}")
        output_lines.append(f"共找到 {len(row_infos)} 条信息：")
        output_lines.append("")

        for row in row_infos:
            # 获取发布时间（class="publish-date"）
            publish_date_elem = row.find(class_='publish-date')
            publish_date = publish_date_elem.get_text(strip=True) if publish_date_elem else "未知时间"

            # 获取 a 标签（招标标题和链接）
            link = row.find('a', href=True)
            if not link:
                continue

            # 获取链接文本并去除 HTML 标签
            link_text = clean_html_tags(str(link))

            # 获取 href，处理相对路径
            href = link.get('href', '')
            if href and not href.startswith(('http://', 'https://')):
                href = urljoin(base_url, href)

            # 如果链接文本为空，尝试使用 title 属性
            if not link_text:
                link_text = link.get('title', '未知标题')

            # 去除多余空白
            link_text = re.sub(r'\s+', ' ', link_text).strip()

            # 按要求的格式输出：发布时间-招标名称：招标链接
            output_lines.append(f"{publish_date}-{link_text}：{href}")

        output_lines.append("")

        # 截断过长的结果
        full_output = "\n".join(output_lines)
        if len(full_output) > 8000:
            full_output = full_output[:7950] + "\n\n... (结果过长，已截断)"

        return full_output

    except Exception as e:
        return f"❌ 执行出错：{str(e)}"
