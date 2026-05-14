---
name: web_fetch
description: 抓取网页内容并清洗为纯文本，支持自动识别相对路径，处理常见反爬策略。当 Agent 需要获取网页内容、分析网页信息、抓取网络数据或验证 URL 可访问性时调用此技能。
category: network
requires_confirmation: false
version: "1.0"
author: 破执
tags: ["web", "fetch", "http", "crawl", "url", "network"]
parameters:
  - name: "url"
    type: "string"
    description: "要抓取的网页 URL 地址。支持 HTTP 和 HTTPS 协议。若 URL 不含协议头，默认尝试 HTTPS。"
    required: true
  - name: "timeout"
    type: "integer"
    description: "请求超时时间（秒），默认 10 秒。对于响应较慢的网站，建议设置为 15-30 秒。"
    required: false
    default: 10
---

## Core Capability
发送 HTTP GET 请求抓取网页内容，自动清洗 HTML 标签提取纯文本，处理相对路径转换为绝对路径，应对常见反爬策略（如 User-Agent 伪装）。是 Agent 获取网络信息、进行网页分析、数据采集的核心能力。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **网页内容获取**：用户要求"帮我看看这个网页说了什么"、"提取这篇文章的内容"
- **信息验证**：需要验证某个 URL 是否可访问、网页内容是否符合预期
- **数据采集**：抓取网页上的特定信息，如新闻标题、产品信息、价格数据
- **链接分析**：分析网页中的所有链接，检查是否有死链或恶意链接
- **竞品分析**：抓取竞品网站的信息进行分析
- **文档获取**：获取在线文档、API 文档的内容
- **实时信息**：获取最新的网页信息（如股价、汇率、新闻）

**判断标准**：当 Agent 需要获取某个网页的文本内容时，使用此技能。

## Parameters

| Name    | Type    | Description                                           | Required | Default |
| ------- | ------- | ----------------------------------------------------- | -------- | ------- |
| url     | string  | 要抓取的网页 URL 地址                                 | Yes      | -       |
| timeout | integer | 请求超时时间（秒），默认 10 秒                        | No       | 10      |

## Example Usage

### 场景1：抓取网页内容
```json
{
  "skill": "web_fetch",
  "args": {
    "url": "https://example.com/article",
    "timeout": 15
  }
}
```

### 场景2：获取 API 文档
```json
{
  "skill": "web_fetch",
  "args": {
    "url": "https://api.example.com/docs",
    "timeout": 20
  }
}
```

### 场景3：验证 URL 可访问性
```json
{
  "skill": "web_fetch",
  "args": {
    "url": "https://my-site.com/status",
    "timeout": 10
  }
}
```

### 场景4：抓取新闻内容
```json
{
  "skill": "web_fetch",
  "args": {
    "url": "https://news.example.com/2024/01/15/tech-news",
    "timeout": 15
  }
}
```

## Execution Signature
```python
def execute(url: str, timeout: int = 10, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
返回清洗后的纯文本内容，保留段落结构：

```
网页标题: 示例文章标题

这是一段正文内容。web_fetch 技能会自动去除 HTML 标签，
将网页内容转换为易读的纯文本格式。

- 列表项 1
- 列表项 2

链接: https://example.com/link1
链接: https://example.com/link2
```

### 错误返回
- URL 无效：`错误: 无效的 URL 格式: 'not-a-url'`
- 连接超时：`错误: 请求超时: https://slow-site.com (超过 10 秒)`
- 404 错误：`错误: HTTP 404: 页面未找到`
- 403 禁止访问：`错误: HTTP 403: 访问被拒绝，可能触发反爬机制`
- DNS 解析失败：`错误: 无法解析域名: example.invalid`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **web_fetch → python_exec**：抓取网页 → 用 Python 进一步解析提取特定数据
2. **web_fetch → file_write**：抓取网页内容 → 保存到本地文件供后续分析
3. **web_fetch → text_to_speech**：抓取文章 → 转换为语音朗读
4. **web_fetch → database_query**：抓取数据 → 存入数据库（需配合其他技能）

## Best Practices（最佳实践）

1. **超时设置**：国内网站 10-15 秒通常足够；国外网站或慢速网站建议 20-30 秒
2. **URL 格式**：确保 URL 包含协议头（`https://` 或 `http://`），不含空格和中文
3. **反爬应对**：若返回 403 错误，可能是触发反爬机制，可尝试更换 User-Agent 或增加延迟
4. **内容清洗**：返回的是纯文本，如需提取特定字段（如价格、标题），建议配合 `python_exec` 使用正则或 BeautifulSoup
5. **批量抓取**：批量抓取多个网页时，建议设置间隔时间（如 1-2 秒），避免对目标网站造成压力

## Safety Notes（安全提示）

- **合法合规**：仅抓取公开可访问的网页，遵守目标网站的 robots.txt 规则
- **隐私保护**：不要抓取包含个人隐私信息的页面
- **频率控制**：避免高频请求同一网站，防止被封 IP
- **内容审核**：抓取的网页内容可能包含不当信息，展示前建议进行内容过滤

## Notes
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 底层实现使用 `fetch_webpage_text` from `utils.net_utils`；确保网络连通性
- 建议安装 `beautifulsoup4` 以获得更好的 HTML 解析效果
- 对于需要登录或 JavaScript 渲染的页面，此技能可能无法获取完整内容
- 返回内容长度可能有限制，超长的网页内容可能会被截断
