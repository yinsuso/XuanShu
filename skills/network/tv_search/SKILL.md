---
name: tv_search
description: 搜索影视节目信息并获取播放地址。分两步执行：第一步根据关键词搜索并输出所有结果列表供用户选择；第二步根据用户选择的序号（vod_id）获取该影视的详细信息和逐集播放链接。
category: network
requires_confirmation: false
version: "3.0"
author: XuanShu Agent
tags: ["影视", "搜索", "电影", "电视剧", "播放地址", "网络搜索"]
parameters:
  - name: "keyword"
    type: "string"
    description: "影视名称关键词（必填），如：电影名称、电视剧名称、演员名。用于搜索相关影视。"
    required: true
  - name: "vod_id"
    type: "string"
    description: "影视ID（第二步使用）。当用户从搜索结果列表中选择了某个影视后，传入该影视的vod_id获取详情和播放地址。第一步搜索时不需要此参数。"
    required: false
    default: ""
  - name: "page"
    type: "integer"
    description: "页码（可选），默认第 1 页"
    required: false
    default: 1
  - name: "timeout"
    type: "integer"
    description: "请求超时时间（秒），默认 30 秒。网络较慢时可适当增大。"
    required: false
    default: 30
---

## Core Capability

基于影视资源聚合 API，提供**分步式影视搜索和播放地址获取**功能。

### 两步流程

**第一步：搜索并展示列表**
1. 用户输入影视名称关键词
2. 调用 `execute(keyword="xxx")` 搜索相关影视
3. 输出**所有搜索结果**（不自动选择），每条结果带序号、名称、年份、状态、类型、vod_id
4. 提示用户回复序号选择想看哪一部

**第二步：获取详情和播放链接**
1. 用户回复序号（如"1"、"2"，支持全角数字如"１"、"２"）
2. Agent 根据序号找到对应的 vod_id
3. **必须同时传入 keyword（原始搜索关键词）和 vod_id**，调用 `execute(keyword="xxx", vod_id="yyy")` 获取该影视详情
4. 输出影视基本信息 + **逐集播放链接**（每集一行：集名：url）

**【关键规则】第二步调用时，keyword 参数不能为空！必须从对话历史中找到用户最初输入的搜索关键词。**

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **影视搜索**：用户要求"搜索电影 xxx"、"找一下电视剧 yyy"、"有没有 zzz 的资源"
- **想看某部影视**：用户说"我想看 xxx"、"给我找 xxx 的资源"
- **资源查找**：用户想查找某部影视的在线观看地址
- **固定触发方式**：用户说"影视搜索：关键词"，如"影视搜索：神与律师"

**判断标准**：当用户需要搜索影视节目、获取播放地址、查找电影/电视剧/综艺/动漫资源时，使用此技能。

**重要提示**：
- 第一步调用时只需要 keyword 参数
- 第二步调用时需要 keyword + vod_id 参数
- 不要自作聪明自动选择，必须输出所有结果让用户自己选择

## Parameters

| Name    | Type    | Description                                           | Required | Default |
| ------- | ------- | ----------------------------------------------------- | -------- | ------- |
| keyword | string  | 影视名称关键词（必填）                                 | Yes      | -       |
| vod_id  | string  | 影视ID（第二步使用），从第一步结果中获取                | No       | ""      |
| page    | integer | 页码（可选），默认第 1 页                             | No       | 1       |
| timeout | integer | 请求超时时间（秒），默认 30 秒                        | No       | 30      |

## Example Usage

### 第一步：搜索影视（只传 keyword）
```json
{
  "skill": "tv_search",
  "args": {
    "keyword": "神与律师"
  }
}
```
返回：
```
🎬 影视搜索成功
关键词: 神与律师
共找到 3 部相关影视：

1. 《神与律师事务所》(2026) - 第16集完结 [韩剧] [ID: 101880]
2. 《律师之神》(2023) - 完结 [日剧] [ID: 102345]
3. 《神的律师》(2022) - 完结 [美剧] [ID: 103456]

💡 请回复你想看的序号（如：1），我会为你获取该影视的详细信息和播放地址。
```

### 第二步：获取选中影视详情（传 keyword + vod_id）
用户回复"1"后，Agent 调用：
```json
{
  "skill": "tv_search",
  "args": {
    "keyword": "神与律师",
    "vod_id": "101880"
  }
}
```
返回：
```
🎬 《神与律师事务所》

年份: 2026 | 类型: 韩剧 | 状态: 第16集完结 | 导演: 某某某 | 演员: 某某某, 某某某

简介: 该剧讲述了...

========================================

📺 线路: 极速线路（共 5 集）
------------------------------
第1集：<a href="https://example.com/ep1.mp4" target="_blank">https://example.com/ep1.mp4</a>
第2集：<a href="https://example.com/ep2.mp4" target="_blank">https://example.com/ep2.mp4</a>
第3集：<a href="https://example.com/ep3.mp4" target="_blank">https://example.com/ep3.mp4</a>
第4集：<a href="https://example.com/ep4.mp4" target="_blank">https://example.com/ep4.mp4</a>
第5集：<a href="https://example.com/ep5.mp4" target="_blank">https://example.com/ep5.mp4</a>

📺 线路: 高清线路 [m3u8]（共 16 集）
------------------------------
第1集：https://example.com/ep1.m3u8
第2集：https://example.com/ep2.m3u8
...
第16集：https://example.com/ep16.m3u8

⚠️ 提示：m3u8 格式需使用 MX Player、VLC 等支持 HLS 的播放器
```

## Execution Signature
```python
def execute(keyword: str, vod_id: str = "", page: int = 1, timeout: int = 30, **kwargs) -> str:
    ...
```

## Output Format

### 第一步输出（搜索结果列表）
```
🎬 影视搜索成功
关键词: xxx
共找到 N 部相关影视：

1. 《影视A》(2024) - 完结 [类型] [ID: 12345]
2. 《影视B》(2023) - 连载中 [类型] [ID: 12346]
3. 《影视C》(2022) - 完结 [类型] [ID: 12347]

💡 请回复你想看的序号（如：1），我会为你获取该影视的详细信息和播放地址。
```

### 第二步输出（影视详情 + 逐集链接）
```
🎬 《影视名称》

年份: 2024 | 类型: 韩剧 | 状态: 完结 | 导演: xxx | 演员: xxx

简介: xxx...

========================================

📺 线路: 线路名称（共 N 集）
------------------------------
第1集：https://xxx
第2集：https://xxx
...
第N集：https://xxx
```

### 错误返回
- 缺少参数：`❌ 请提供影视名称关键词，例如：'流浪地球'、'三体'、'神与律师'`
- 未找到结果：`✅ 搜索完成，未找到与 'xxx' 相关的影视，请尝试其他关键词。`
- 未找到详情：`❌ 未找到影视详情，ID: xxx`

## Data Flow（数据流程）

```
用户输入"搜索电影 xxx"
    ↓
调用 execute(keyword="xxx")  —— 第一步
    ↓
请求 API: https://jszyapi.com/api.php/provide/vod/?ac=detail&wd=xxx
    ↓
返回所有搜索结果列表（带序号和 vod_id）
    ↓
用户回复序号（如"1"）
    ↓
Agent 找到对应 vod_id
    ↓
调用 execute(keyword="xxx", vod_id="yyy")  —— 第二步
    ↓
请求 API: https://jszyapi.com/api.php/provide/vod/?ac=detail&ids=yyy
    ↓
返回影视详情 + 逐集播放链接
```

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **tv_search → web_fetch**：获取播放地址后，验证链接是否可访问
2. **tv_search → file_write**：将搜索结果或播放列表保存到文件
3. **tv_search → python_exec**：对搜索结果进行统计分析

## Best Practices（最佳实践）

1. **关键词精准**：使用具体的影视名称（如"流浪地球"而非"科幻电影"）可获得更精准的结果
2. **不要自动选择**：第一步必须输出所有结果，让用户自己选择序号
3. **逐集输出**：第二步必须一集集输出，不要跳过任何集数
4. **分页查询**：结果较多时，使用 page 参数翻页查看
5. **超时调整**：网络较慢时，将 timeout 增大到 45-60 秒
6. **线路选择**：展示所有可用线路，让用户自行选择

## Safety Notes（安全提示）

- **合法合规**：仅搜索公开可访问的影视资源
- **版权问题**：注意影视资源的版权状态，遵守当地法律法规
- **API 限流**：避免高频请求，两次搜索建议间隔 1-2 秒
- **链接安全**：播放地址来自第三方 API，使用前建议验证链接安全性

## Notes

- 主 API: `https://jszyapi.com/api.php/provide/vod/`，备用 API: `https://dbzyapi.tv/api.php/provide/vod/`
- 支持多线路解析，线路之间用 `$$$` 分隔，集数之间用 `#` 分隔，集数名称和地址用 `$` 分隔
- 结果长度超过 8000 字符时会自动截断
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 部分影视可能没有播放地址，或播放地址已失效
- 目标 API 服务变更可能导致功能异常，如遇此情况请反馈
- **v3.0 更新**：改为分步式流程，第一步输出所有搜索结果列表，第二步根据用户选择的 vod_id 输出逐集播放链接，不再自动智能选择

## 全角数字兼容性说明

**【重要】当技能涉及用户输入数字（如序号、页码、数量等）时，必须考虑全角数字的兼容性。**

在中文输入环境下，用户可能输入全角数字（如 `１`、`２`、`３`）而非半角数字（如 `1`、`2`、`3`）。Agent 在解析用户输入时，必须将全角数字转换为半角数字后再进行处理。

**处理要求：**
1. Agent 在调用技能前，应自动将用户输入中的全角数字转换为半角数字
2. 技能代码本身也应具备全角数字的容错处理能力
3. 涉及数字匹配的正则表达式应同时兼容全角和半角数字

**全角数字对照表：**
| 全角 | 半角 |
|------|------|
| ０ | 0 |
| １ | 1 |
| ２ | 2 |
| ３ | 3 |
| ４ | 4 |
| ５ | 5 |
| ６ | 6 |
| ７ | 7 |
| ８ | 8 |
| ９ | 9 |
