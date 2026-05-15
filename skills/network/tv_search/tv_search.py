"""
影视搜索技能。
基于影视资源 API，提供影视搜索和播放地址获取功能。
流程：用户输入关键词 -> 输出所有搜索结果列表 -> 用户输入序号 -> 获取选中影视详情 -> 逐集输出播放链接
Author: XuanShu Agent
Date: 2026-05-14
"""

from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urlencode

from skills.utils.net_utils import safe_request, fetch_json

# 技能元数据
SKILL_NAME = "tv_search"
SKILL_DESCRIPTION = "搜索影视节目信息并获取播放地址。分两步执行：第一步根据关键词搜索并输出所有结果列表供用户选择；第二步根据用户选择的序号获取该影视的详细信息和逐集播放链接。"
SKILL_TRIGGER = "当用户需要搜索影视节目、获取播放地址、查找电影电视剧资源时使用。用户只需说'搜索电影 xxx'、'我想看 yyy'、'有没有 zzz 的资源'即可。"
SKILL_CATEGORY = "network"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "keyword",
        "type": "string",
        "description": "影视名称关键词（必填），如：电影名称、电视剧名称、演员名。用于搜索相关影视。"
    },
    {
        "name": "vod_id",
        "type": "string",
        "description": "影视ID（在第二步使用）。当用户选择了某个影视后，传入该影视的vod_id获取详情和播放地址。",
        "default": ""
    },
    {
        "name": "page",
        "type": "integer",
        "description": "页码（可选），默认第 1 页",
        "default": 1
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "请求超时时间（秒），默认 30 秒",
        "default": 30
    }
]

# API 配置
API_URL = "https://jszyapi.com/api.php/provide/vod/"
BACKUP_API_URL = "https://dbzyapi.tv/api.php/provide/vod/"


def fetch_api_data(params: Dict[str, Any], timeout: int = 30) -> Optional[Dict]:
    """
    调用影视 API 获取数据。

    Args:
        params: 查询参数
        timeout: 超时时间（秒）

    Returns:
        API 返回的 JSON 数据，失败返回 None
    """
    try:
        query_string = urlencode(params)
        url = f"{API_URL}?{query_string}"

        result = fetch_json(url, timeout=timeout)

        if result["success"]:
            return result.get("data")

        # 主 API 失败，尝试备用 API
        backup_url = f"{BACKUP_API_URL}?{query_string}"
        result = fetch_json(backup_url, timeout=timeout)

        if result["success"]:
            return result.get("data")

        return None
    except Exception:
        return None


def search_tv(keyword: str, page: int = 1, timeout: int = 30) -> Tuple[List[Dict], int]:
    """
    搜索影视。

    Args:
        keyword: 搜索关键词
        page: 页码
        timeout: 超时时间

    Returns:
        (影视列表, 总数)
    """
    params = {"ac": "detail", "wd": keyword, "page": page}
    data = fetch_api_data(params, timeout)

    if data and data.get("code") == 1:
        return data.get("list", []), data.get("total", 0)
    return [], 0


def get_vod_detail(vod_id: str, timeout: int = 30) -> Optional[Dict]:
    """
    获取影视详情。

    Args:
        vod_id: 影视 ID
        timeout: 超时时间

    Returns:
        影视详情字典，失败返回 None
    """
    params = {"ac": "detail", "ids": vod_id}
    data = fetch_api_data(params, timeout)

    if data and data.get("code") == 1:
        vod_list = data.get("list", [])
        return vod_list[0] if vod_list else None
    return None


def parse_play_urls(vod_detail: Dict) -> List[Dict]:
    """
    解析播放地址。

    解析 vod_play_url 和 vod_play_from 字段，支持多线路（$$$ 分隔）。
    每集格式：episode_name$play_url

    Args:
        vod_detail: 影视详情字典

    Returns:
        播放源列表，每个源包含名称和集数列表
    """
    play_url_str = vod_detail.get("vod_play_url", "")
    play_from_str = vod_detail.get("vod_play_from", "")

    if not play_url_str or not play_from_str:
        return []

    play_sources = play_from_str.split("$$$")
    play_url_parts = play_url_str.split("$$$")

    sources = []
    for i, source_name in enumerate(play_sources):
        if i >= len(play_url_parts):
            break

        episodes = []
        url_list = play_url_parts[i].split("#")
        for item in url_list:
            if "$" in item:
                parts = item.split("$", 1)
                if len(parts) == 2:
                    episodes.append({
                        "name": parts[0].strip(),
                        "url": parts[1].strip(),
                        "n": len(episodes) + 1
                    })

        if episodes:
            sources.append({
                "name": source_name,
                "episodes": episodes
            })

    return sources


def format_search_results(results: List[Dict], keyword: str, total: int) -> str:
    """
    格式化搜索结果列表，供用户选择。
    输出所有搜索结果，每条包含序号、名称、年份、状态、类型。

    Args:
        results: 影视列表
        keyword: 搜索关键词
        total: 总数

    Returns:
        格式化后的字符串
    """
    lines = [f"🎬 影视搜索成功", f"关键词: {keyword}", f"共找到 {total} 部相关影视：", ""]

    for i, vod in enumerate(results, 1):
        name = vod.get("vod_name", "未知")
        year = vod.get("vod_year", "")
        remarks = vod.get("vod_remarks", "")
        type_name = vod.get("type_name", "")
        vod_id = vod.get("vod_id", "")

        info = f"{i}. 《{name}》"
        if year:
            info += f" ({year})"
        if remarks:
            info += f" - {remarks}"
        if type_name:
            info += f" [{type_name}]"
        info += f" [ID: {vod_id}]"

        lines.append(info)

    lines.append("")
    lines.append("💡 请回复你想看的序号（如：1），我会为你获取该影视的详细信息和播放地址。")
    return "\n".join(lines)


def format_vod_detail(vod: Dict) -> str:
    """
    格式化影视详情和逐集播放链接。
    按用户要求：一集集输出，格式为 集数名：url

    Args:
        vod: 影视详情字典

    Returns:
        格式化后的字符串
    """
    name = vod.get("vod_name", "未知")
    year = vod.get("vod_year", "")
    remarks = vod.get("vod_remarks", "")
    type_name = vod.get("type_name", "")
    actor = vod.get("vod_actor", "")
    director = vod.get("vod_director", "")
    content = vod.get("vod_content", "")

    lines = [f"🎬 《{name}》", ""]

    # 基本信息
    info_parts = []
    if year:
        info_parts.append(f"年份: {year}")
    if type_name:
        info_parts.append(f"类型: {type_name}")
    if remarks:
        info_parts.append(f"状态: {remarks}")
    if director:
        info_parts.append(f"导演: {director}")
    if actor:
        info_parts.append(f"演员: {actor}")

    if info_parts:
        lines.append(" | ".join(info_parts))
        lines.append("")

    if content:
        import re
        content_clean = re.sub(r'<[^>]+>', '', content)
        if len(content_clean) > 200:
            content_clean = content_clean[:200] + "..."
        lines.append(f"简介: {content_clean}")
        lines.append("")

    # 解析播放地址
    sources = parse_play_urls(vod)

    if not sources:
        lines.append("❌ 抱歉，该影视暂无可用播放地址")
        return "\n".join(lines)

    lines.append("=" * 40)
    lines.append("")

    # 逐个线路输出，每集一行：集名：url
    for source in sources:
        source_name = source.get("name", "")
        episodes = source.get("episodes", [])

        is_m3u8 = "m3u8" in source_name.lower()
        if episodes and not is_m3u8:
            first_url = episodes[0].get("url", "")
            if ".m3u8" in first_url.lower():
                is_m3u8 = True

        m3u8_tag = " [m3u8]" if is_m3u8 else ""
        lines.append(f"📺 线路: {source_name}{m3u8_tag}（共 {len(episodes)} 集）")
        lines.append("-" * 30)

        for ep in episodes:
            ep_name = ep.get("name", "").strip()
            ep_url = ep.get("url", "").strip()
            lines.append(f"{ep_name}：{ep_url}")

        lines.append("")

    if any("m3u8" in s.get("name", "").lower() for s in sources):
        lines.append("⚠️ 提示：m3u8 格式需使用 MX Player、VLC 等支持 HLS 的播放器")

    return "\n".join(lines)


def execute(keyword: str, vod_id: str = "", page: int = 1, timeout: int = 30, **kwargs) -> str:
    """
    执行影视搜索技能。

    两步流程：
    1. 当只提供 keyword 时：搜索影视并输出所有结果列表，供用户选择序号
    2. 当提供 keyword + vod_id 时：获取指定影视的详情和逐集播放链接

    Args:
        keyword: 搜索关键词（必填）
        vod_id: 影视ID（第二步使用，用户选择后传入）
        page: 页码（可选，默认 1）
        timeout: 超时时间（秒，默认 30）
        **kwargs: 兼容额外参数

    Returns:
        格式化后的搜索结果列表或影视详情（含逐集播放链接）
    """
    # 第二步：如果提供了 vod_id，获取该影视详情并逐集输出（keyword 可为空）
    if vod_id:
        vod_detail = get_vod_detail(vod_id, timeout)
        if not vod_detail:
            return f"❌ 未找到影视详情，ID: {vod_id}"
        return format_vod_detail(vod_detail)

    # 第一步：搜索影视，输出所有结果列表（必须提供 keyword）
    if not keyword:
        return "❌ 请提供影视名称关键词，例如：'流浪地球'、'三体'、'神与律师'"

    results, total = search_tv(keyword, page, timeout)

    if not results:
        return f"✅ 搜索完成，未找到与 '{keyword}' 相关的影视，请尝试其他关键词。"

    # 输出所有搜索结果，让用户选择
    return format_search_results(results, keyword, total)
