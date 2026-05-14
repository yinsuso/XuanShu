---
name: bidding_info_search
description: 查询招标信息，通过关键词和省份筛选，获取招标标题和链接。当 Agent 需要查询政府采购、工程招标、设备采购等招投标信息时调用此技能。
category: network
requires_confirmation: false
version: "1.0"
author: XuanShu Agent
tags: ["招标", "采购", "招投标", "信息查询", "网络搜索"]
parameters:
  - name: "keyword"
    type: "string"
    description: "搜索关键词（必填），如：设备采购、工程建设、软件开发、服务外包等。关键词越具体，结果越精准。"
    required: true
  - name: "province"
    type: "string"
    description: "省份（可选），如：北京、上海、广东、浙江。不填则查询全国范围。"
    required: false
    default: ""
  - name: "timeout"
    type: "integer"
    description: "请求超时时间（秒），默认 15 秒。网络较慢时可适当增大。"
    required: false
    default: 15
---

## Core Capability
访问 http://www.sizebid.com/bid-information.html 查询招标信息，使用 BeautifulSoup 解析 HTML 数据。每个 class="row-info" 的 div 标签为一个项目，提取 class="publish-date" 的发布时间、以及 a 标签的标题和链接。返回格式化的招标信息列表。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **招标信息查询**：用户要求"查一下最近有哪些软件开发的招标"、"北京地区的工程招标信息"
- **市场调研**：了解某个行业的招标动态和竞争情况
- **商机发现**：寻找特定领域的采购机会
- **竞品监控**：监控竞争对手参与的招标项目
- **行业分析**：分析某个地区的招标趋势和规模

**判断标准**：当用户需要查询招投标、政府采购、工程招标等信息时，使用此技能。

## Parameters

| Name     | Type    | Description                                         | Required | Default |
| -------- | ------- | --------------------------------------------------- | -------- | ------- |
| keyword  | string  | 搜索关键词（必填），如：设备采购、工程建设          | Yes      | -       |
| province | string  | 省份（可选），如：北京、上海、广东、浙江            | No       | ""      |
| timeout  | integer | 请求超时时间（秒），默认 15 秒                      | No       | 15      |

## Supported Keywords（常用关键词）

- **工程建设**：建筑工程、市政工程、装修工程、土建工程
- **IT 相关**：软件开发、系统集成、网络安全、信息化、云计算
- **设备采购**：设备采购、仪器采购、办公设备、医疗设备
- **服务类**：服务外包、咨询服务、运维服务、物业服务
- **其他**：政府采购、物资采购、图书采购、车辆采购

## Supported Provinces（支持省份）

北京、上海、广东、浙江、江苏、山东、河南、四川、湖北、湖南、福建、安徽、河北、陕西、江西、重庆、辽宁、云南、广西、山西、贵州、天津、内蒙古、新疆、黑龙江、吉林、甘肃、海南、宁夏、青海、西藏、台湾、香港、澳门

## Example Usage

### 场景1：查询全国范围的软件招标
```json
{
  "skill": "bidding_info_search",
  "args": {
    "keyword": "软件开发",
    "province": ""
  }
}
```

### 场景2：查询特定省份的设备采购
```json
{
  "skill": "bidding_info_search",
  "args": {
    "keyword": "设备采购",
    "province": "广东"
  }
}
```

### 场景3：查询工程建设招标（自定义超时）
```json
{
  "skill": "bidding_info_search",
  "args": {
    "keyword": "工程建设",
    "province": "北京",
    "timeout": 30
  }
}
```

## Execution Signature
```python
def execute(keyword: str, province: str = "", timeout: int = 15, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
```
✅ 招标信息查询成功
关键词: 设备采购
省份: 北京
共找到 25 条信息：

2026-05-10 - 北京市某医院医疗设备采购项目：http://www.sizebid.com/bid/12345.html
2026-05-09 - 某高校实验室仪器采购招标：http://www.sizebid.com/bid/12344.html
2026-05-08 - 某区政府办公设备采购：http://www.sizebid.com/bid/12343.html
...
```

### 错误返回
- 网络超时：`❌ 招标信息查询失败: 请求超时`
- 网站不可达：`❌ 招标信息查询失败: 无法连接到 www.sizebid.com`
- 解析失败：`❌ 招标信息查询失败: 页面解析错误，网站结构可能已变更`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **bidding_info_search → web_fetch**：查询到感兴趣的招标信息后，抓取详细页面获取完整内容
2. **bidding_info_search → file_write**：将查询结果保存到文件，便于后续分析和存档
3. **bidding_info_search → python_exec**：对查询结果进行统计分析，如按日期、地区汇总

## Best Practices（最佳实践）

1. **关键词精准**：使用具体的关键词（如"医疗软件开发"而非"软件"）可获得更精准的结果
2. **省份筛选**：如需特定地区的信息，务必填写省份参数，减少无关结果
3. **超时调整**：目标网站响应较慢时，将 timeout 增大到 20-30 秒
4. **结果验证**：返回的链接建议用 `web_fetch` 验证是否可访问，确认信息有效性
5. **定期查询**：招标信息更新频繁，如需持续关注，建议定期执行查询

## Notes
- 使用 BeautifulSoup 解析 HTML，每个项目从 class="row-info" 的 div 中提取
- 发布时间为 class="publish-date" 的文本内容
- 自动处理相对路径，转换为完整 URL
- 结果长度超过 8000 字符时会自动截断
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 目标网站结构变更可能导致解析失败，如遇此情况请反馈
