---
name: tv_search
description: 搜索影视节目信息，获取播放地址。支持按关键词搜索影视资源，返回搜索结果列表及播放链接。当用户需要搜索电影、电视剧、综艺节目等影视资源时调用此技能。
category: network
requires_confirmation: false
version: "1.0"
author: XuanShu Agent
tags: ["影视", "搜索", "电影", "电视剧", "播放地址", "网络搜索"]
parameters:
  - name: "action"
    type: "string"
    description: "操作类型（必填）。search=搜索影视，play=获取播放地址"
    required: true
    enum: ["search", "play"]
  - name: "keyword"
    type: "string"
    description: "搜索关键词（action=search 时必填），如：电影名称、电视剧名称、演员名"
    required: false
    default: ""
  - name: "vod_id"
    type: "string"
    description: "影视 ID（action=play 时必填），从搜索结果中获取"
    required: false
    default: ""
  - name: "play_index"
    type: "integer"
    description: "集数索引（action=play 时可选），默认第 1 集"
    required: false
    default: 1
  - name: "page"
    type: "integer"
    description: "页码（action=search 时可选），默认第 1 页"
    required: false
    default: 1
  - name: "timeout"
    type: "integer"
    description: "请求超时时间（秒），默认 30 秒。网络较慢时可适当增大。"
    required: false
    default: 30
---

## Core Capability
基于影视资源聚合 API，提供影视搜索和播放地址获取功能。支持搜索电影、电视剧、综艺、动漫等影视资源，返回搜索结果列表（包含影视名称、年份、状态、类型、ID 等信息），并可根据影视 ID 获取详细的播放地址信息，支持多线路解析和智能线路选择（优先非 m3u8 线路，手机端更友好）。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **影视搜索**：用户要求"搜索电影 xxx"、"找一下电视剧 yyy"、"有没有 zzz 的资源"
- **播放地址获取**：用户提供了影视 ID，需要获取播放链接
- **资源查找**：用户想查找某部影视的在线观看地址
- **多集数选择**：用户需要获取特定集数的播放地址（如第 5 集）
- **线路切换**：用户需要查看所有可用播放线路

**判断标准**：当用户需要搜索影视节目、获取播放地址、查找电影/电视剧/综艺资源时，使用此技能。

## Parameters

| Name       | Type    | Description                                           | Required | Default |
| ---------- | ------- | ----------------------------------------------------- | -------- | ------- |
| action     | string  | 操作类型（必填）。search=搜索影视，play=获取播放地址  | Yes      | -       |
| keyword    | string  | 搜索关键词（action=search 时必填）                    | No       | ""      |
| vod_id     | string  | 影视 ID（action=play 时必填）                         | No       | ""      |
| play_index | integer | 集数索引（action=play 时可选），默认第 1 集           | No       | 1       |
| page       | integer | 页码（action=search 时可选），默认第 1 页             | No       | 1       |
| timeout    | integer | 请求超时时间（秒），默认 30 秒                        | No       | 30      |

## Supported Actions（支持的操作）

### 1. search - 搜索影视
根据关键词搜索影视资源，返回搜索结果列表。

**必填参数**：action=search, keyword=关键词

**可选参数**：page=页码, timeout=超时时间

### 2. play - 获取播放地址
根据影视 ID 获取详细的播放地址信息。

**必填参数**：action=play, vod_id=影视ID

**可选参数**：play_index=集数索引, timeout=超时时间

## Example Usage

### 场景1：搜索电影
```json
{
  "skill": "tv_search",
  "args": {
    "action": "search",
    "keyword": "流浪地球"
  }
}
```

### 场景2：搜索电视剧（第2页）
```json
{
  "skill": "tv_search",
  "args": {
    "action": "search",
    "keyword": "三体",
    "page": 2
  }
}
```

### 场景3：获取影视播放地址
```json
{
  "skill": "tv_search",
  "args": {
    "action": "play",
    "vod_id": "12345"
  }
}
```

### 场景4：获取特定集数
```json
{
  "skill": "tv_search",
  "args": {
    "action": "play",
    "vod_id": "12345",
    "play_index": 5
  }
}
```

## Execution Signature
```python
def execute(action: str, keyword: str = "", vod_id: str = "", play_index: int = 1, page: int = 1, timeout: int = 30, **kwargs) -> str:
    ...
```

## Output Format

### search 成功返回
```
✅ 影视搜索成功
关键词: 流浪地球
共找到 15 部：

1. 《流浪地球》(2019) - HD [电影] [ID: 12345]
2. 《流浪地球2》(2023) - HD [电影] [ID: 12346]
3. 《流浪地球：飞跃2020特别版》- HD [电影] [ID: 12347]
...

提示：使用 play 操作并传入 vod_id 获取播放地址
```

### play 成功返回
```
✅ 《流浪地球》播放信息

当前线路: 极速线路
播放地址: https://example.com/video.mp4

线路: 极速线路（共 1 集）
  正片: https://example.com/video.mp4

线路: 高清线路 [m3u8]（共 1 集）
  正片: https://example.com/video.m3u8

⚠️ 提示：m3u8 格式需使用 MX Player、VLC 等支持 HLS 的播放器
```

### 错误返回
- 缺少参数：`❌ 搜索操作需要提供 keyword 参数`
- 未找到结果：`✅ 搜索完成，未找到与 'xxx' 相关的影视`
- 播放信息缺失：`❌ 未找到影视 ID '12345' 的播放信息`
- 网络超时：`❌ 执行出错：请求超时`
- API 异常：`❌ 执行出错：API 返回错误`

## Data Flow（数据流程）

```
用户输入"搜索电影 xxx"
    ↓
调用 execute(action="search", keyword="xxx")
    ↓
调用 search_tv(keyword="xxx")
    ↓
请求 API: https://jszyapi.com/api.php/provide/vod/?ac=detail&wd=xxx
    ↓
返回搜索结果列表（vod_id, vod_name, vod_year, vod_remarks, type_name）
    ↓
格式化输出给用户

用户选择 vod_id
    ↓
调用 execute(action="play", vod_id="12345")
    ↓
调用 get_play_url(vod_id="12345")
    ↓
请求 API 获取详情
    ↓
解析 vod_play_url 和 vod_play_from（支持多线路 $$$ 分隔）
    ↓
优先选择非 m3u8 线路
    ↓
返回播放地址、集数列表、所有线路
    ↓
格式化输出给用户
```

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **tv_search → web_fetch**：获取播放地址后，验证链接是否可访问
2. **tv_search → file_write**：将搜索结果保存到文件，便于后续查看
3. **tv_search → python_exec**：对搜索结果进行统计分析，如按年份、类型汇总

## Best Practices（最佳实践）

1. **关键词精准**：使用具体的影视名称（如"流浪地球"而非"科幻电影"）可获得更精准的结果
2. **分页查询**：结果较多时，使用 page 参数翻页查看
3. **超时调整**：网络较慢时，将 timeout 增大到 45-60 秒
4. **线路选择**：优先使用非 m3u8 线路，手机端可直接播放；m3u8 格式需第三方播放器
5. **ID 复用**：获取到 vod_id 后，可直接用于 play 操作，无需重复搜索
6. **集数索引**：play_index 从 1 开始，表示第几集

## Safety Notes（安全提示）

- **合法合规**：仅搜索公开可访问的影视资源
- **版权问题**：注意影视资源的版权状态，遵守当地法律法规
- **API 限流**：避免高频请求，两次搜索建议间隔 1-2 秒
- **链接安全**：播放地址来自第三方 API，使用前建议验证链接安全性
- **内容审核**：搜索结果可能包含各类影视内容，展示前建议进行内容过滤

## Notes

- 主 API: `https://jszyapi.com/api.php/provide/vod/`，备用 API: `https://dbzyapi.tv/api.php/provide/vod/`
- 支持多线路解析，线路之间用 `$$$` 分隔，集数之间用 `#` 分隔，集数名称和地址用 `$` 分隔
- 优先选择非 m3u8 线路，若所有线路均为 m3u8，则使用第一条线路
- 结果长度超过 8000 字符时会自动截断
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 部分影视可能没有播放地址，或播放地址已失效
- 目标 API 服务变更可能导致功能异常，如遇此情况请反馈
