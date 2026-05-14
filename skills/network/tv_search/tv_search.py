"""
影视搜索技能。
基于影视资源 API，提供影视搜索和播放地址获取功能。
Author: XuanShu Agent
Date: 2026-05-14
"""

from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urlencode

from skills.utils.net_utils import safe_request, fetch_json

# 技能元数据
SKILL_NAME = "tv_search"
SKILL_DESCRIPTION = "搜索影视节目信息，获取播放地址。支持按关键词搜索影视资源，返回搜索结果列表及播放链接。当用户需要搜索电影、电视剧、综艺节目等影视资源时调用此技能。"
SKILL_TRIGGER = "当用户需要搜索影视节目、获取播放地址、查找电影电视剧资源时使用。"
SKILL_CATEGORY = "network"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "action",
        "type": "string",
        "description": "操作类型（必填）。search=搜索影视，play=获取播放地址",
        "enum": ["search", "play"]
    },
    {
        "name": "keyword",
        "type": "string",
        "description": "搜索关键词（action=search 时必填），如：电影名称、电视剧名称、演员名",
        "default": ""
    },
    {
        "name": "vod_id",
        "type": "string",
        "description": "影视 ID（action=play 时必填），从搜索结果中获取",
        "default": ""
    },
    {
        "name": "play_index",
        "type": "integer",
        "description": "集数索引（action=play 时可选），默认第 1 集",
        "default": 1
    },
    {
        "name": "page",
        "type": "integer",
        "description": "页码（action=search 时可选），默认第 1 页",
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


def get_play_url(vod_id: str, play_index: int = 1, timeout: int = 30) -> Optional[Dict]:
    """
    获取播放 URL（优先非 m3u8 线路，手机友好）。

    Args:
        vod_id: 影视 ID
        play_index: 集数索引（从 1 开始）
        timeout: 超时时间

    Returns:
        播放数据字典，包含 url/list/sources/vod/current_source_name，失败返回 None
    """
    vod_detail = get_vod_detail(vod_id, timeout)
    if not vod_detail:
        return None

    sources = parse_play_urls(vod_detail)
    if not sources:
        return None

    # 优先选择非 m3u8 线路（手机可直接播放）
    preferred_source = None
    for source in sources:
        if "m3u8" not in source["name"].lower():
            preferred_source = source
            break

    if not preferred_source:
        # 所有线路都是 m3u8，使用第一条
        preferred_source = sources[0]

    episodes = preferred_source.get("episodes", [])
    if episodes and play_index <= len(episodes):
        play_url = episodes[play_index - 1]["url"]
        return {
            "url": play_url,
            "list": episodes,
            "sources": sources,
            "vod": vod_detail,
            "current_source_name": preferred_source["name"]
        }

    return None


def format_search_results(results: List[Dict], keyword: str, total: int) -> str:
    """
    格式化搜索结果。

    Args:
        results: 影视列表
        keyword: 搜索关键词
        total: 总数

    Returns:
        格式化后的字符串
    """
    lines = [f"✅ 影视搜索成功", f"关键词: {keyword}", f"共找到 {total} 部：", ""]

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
    lines.append("提示：使用 play 操作并传入 vod_id 获取播放地址")
    return "\n".join(lines)


def format_play_info(play_data: Dict) -> str:
    """
    格式化播放信息。

    Args:
        play_data: 播放数据

    Returns:
        格式化后的字符串
    """
    if not play_data:
        return "❌ 未找到播放信息"

    vod = play_data.get("vod", {})
    name = vod.get("vod_name", "未知")
    sources = play_data.get("sources", [])
    current_source = play_data.get("current_source_name", "")
    current_url = play_data.get("url", "")

    lines = [f"✅ 《{name}》播放信息", ""]
    lines.append(f"当前线路: {current_source}")
    lines.append(f"播放地址: {current_url}")
    lines.append("")

    # 列出所有线路的集数
    for source in sources:
        source_name = source.get("name", "")
        episodes = source.get("episodes", [])

        is_m3u8 = "m3u8" in source_name.lower()
        if episodes and not is_m3u8:
            first_url = episodes[0].get("url", "")
            if ".m3u8" in first_url.lower():
                is_m3u8 = True

        m3u8_tag = " [m3u8]" if is_m3u8 else ""
        lines.append(f"线路: {source_name}{m3u8_tag}（共 {len(episodes)} 集）")

        for ep in episodes:
            ep_name = ep.get("name", "").strip()
            ep_url = ep.get("url", "").strip()
            lines.append(f"  {ep_name}: {ep_url}")
        lines.append("")

    if any("m3u8" in s.get("name", "").lower() for s in sources):
        lines.append("⚠️ 提示：m3u8 格式需使用 MX Player、VLC 等支持 HLS 的播放器")

    return "\n".join(lines)


def execute(action: str, keyword: str = "", vod_id: str = "", play_index: int = 1, page: int = 1, timeout: int = 30, **kwargs) -> str:
    """
    执行影视搜索技能。

    Args:
        action: 操作类型，search 或 play
        keyword: 搜索关键词（search 时必填）
        vod_id: 影视 ID（play 时必填）
        play_index: 集数索引（play 时可选，默认 1）
        page: 页码（search 时可选，默认 1）
        timeout: 超时时间（秒，默认 30）
        **kwargs: 兼容额外参数

    Returns:
        格式化后的搜索结果或播放信息
    """
    action = action.lower().strip()

    if action == "search":
        if not keyword:
            return "❌ 搜索操作需要提供 keyword 参数"

        results, total = search_tv(keyword, page, timeout)

        if not results:
            return f"✅ 搜索完成，未找到与 '{keyword}' 相关的影视"

        return format_search_results(results, keyword, total)

    elif action == "play":
        if not vod_id:
            return "❌ 播放操作需要提供 vod_id 参数"

        play_data = get_play_url(vod_id, play_index, timeout)

        if not play_data:
            return f"❌ 未找到影视 ID '{vod_id}' 的播放信息"

        return format_play_info(play_data)

    else:
        return f"❌ 未知操作: {action}，支持 search 或 play"
