---
name: browser_control
description: 控制浏览器打开网页、获取页面信息。支持打开 URL、获取页面标题和内容、搜索关键词等。当需要打开网页、浏览网站、搜索信息或获取页面内容时调用此技能。
category: network
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["browser", "web", "url", "open", "search", "internet"]
parameters:
  - name: "action"
    type: "string"
    description: "操作类型: open(打开网页), info(获取页面信息), search(搜索关键词)"
    required: true
  - name: "url"
    type: "string"
    description: "网页 URL（action=open 或 info 时必填）"
    required: false
    default: ""
  - name: "query"
    type: "string"
    description: "搜索关键词（action=search 时必填）"
    required: false
    default: ""
  - name: "browser"
    type: "string"
    description: "指定浏览器（可选）。如 chrome, firefox, edge, safari"
    required: false
    default: ""
---

## Core Capability
控制浏览器执行各种网页操作，包括打开指定 URL、获取页面标题和元信息、使用搜索引擎搜索关键词。支持 Windows、Linux、macOS 三平台，自动查找系统中可用的浏览器。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **打开网页**：让用户在浏览器中查看某个网站
- **搜索信息**：用搜索引擎查找关键词
- **获取页面信息**：获取网页标题、描述、状态码等元信息
- **验证链接**：检查网页是否可访问
- **推荐网站**：打开用户可能感兴趣的网页

**判断标准**：当需要与浏览器交互或获取网页信息时，使用此技能。

## Parameters

| Name    | Type   | Description                                           | Required | Default |
| ------- | ------ | ----------------------------------------------------- | -------- | ------- |
| action  | string | 操作类型: open/info/search                            | Yes      | -       |
| url     | string | 网页 URL                                              | No       | ""      |
| query   | string | 搜索关键词                                            | No       | ""      |
| browser | string | 指定浏览器（可选）                                    | No       | ""      |

## Supported Actions

| Action | 说明           | 必填参数 | 示例                          |
| ------ | -------------- | -------- | ----------------------------- |
| open   | 打开网页       | url      | 在浏览器中打开指定 URL        |
| info   | 获取页面信息   | url      | 获取标题、描述、状态码等      |
| search | 搜索关键词     | query    | 用 DuckDuckGo 搜索            |

## Supported Browsers

| 平台    | 优先级顺序                              |
| ------- | --------------------------------------- |
| Windows | Edge → Chrome → Firefox                 |
| Linux   | Chrome → Chromium → Firefox → xdg-open  |
| macOS   | Safari(open) → Chrome → Firefox         |

## Example Usage

### 场景1：打开网页
```json
{
  "skill": "browser_control",
  "args": {
    "action": "open",
    "url": "https://github.com"
  }
}
```

### 场景2：用指定浏览器打开
```json
{
  "skill": "browser_control",
  "args": {
    "action": "open",
    "url": "https://example.com",
    "browser": "firefox"
  }
}
```

### 场景3：获取页面信息
```json
{
  "skill": "browser_control",
  "args": {
    "action": "info",
    "url": "https://www.python.org"
  }
}
```

### 场景4：搜索关键词
```json
{
  "skill": "browser_control",
  "args": {
    "action": "search",
    "query": "Python 教程"
  }
}
```

### 场景5：搜索并用指定浏览器打开
```json
{
  "skill": "browser_control",
  "args": {
    "action": "search",
    "query": "OpenAI GPT-4",
    "browser": "chrome"
  }
}
```

## Execution Signature
```python
def execute(action: str, url: str = "", query: str = "", browser: str = "", **kwargs) -> str:
    ...
```

## Output Format

### open 成功
```
✅ 已用 chrome 打开: https://github.com
```

### info 成功
```
✅ 页面信息获取成功
URL: https://www.python.org
状态码: 200
内容类型: text/html; charset=utf-8
标题: Welcome to Python.org
描述: The official home of the Python Programming Language...
```

### search 成功
```
✅ 已用 edge 打开: https://duckduckgo.com/?q=Python+教程
```

### 错误返回
- 未找到浏览器：`❌ 未找到可用的浏览器。请确认已安装 Chrome、Firefox、Edge 等浏览器`
- 参数缺失：`❌ action=open 时需要提供 url 参数`
- 页面错误：`❌ HTTP 错误 404: Not Found`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **browser_control → web_fetch**：先用 browser 打开页面，再用 web_fetch 抓取详细内容
2. **browser_control(search) → web_fetch**：搜索后用 web_fetch 获取搜索结果页面内容
3. **browser_control(info) → file_write**：将页面信息保存到文件

## Best Practices（最佳实践）

1. **URL 格式**：可以省略 https:// 前缀，会自动补全
2. **浏览器选择**：不指定 browser 时自动选择系统默认浏览器
3. **info 操作**：适合快速检查网页状态，无需打开浏览器
4. **搜索隐私**：使用 DuckDuckGo 搜索引擎，不追踪用户

## Safety Notes（安全提示）

- **URL 验证**：会自动补全 http:// 前缀
- **隐私保护**：搜索使用 DuckDuckGo，不记录搜索历史
- **安全浏览**：打开网页时请确保 URL 来源可信
- **网络访问**：需要网络连接才能访问外部网站

## Notes
- 支持 Windows、Linux、macOS 三平台
- 自动查找 Chrome、Firefox、Edge、Safari 等常见浏览器
- 搜索功能使用 DuckDuckGo（隐私友好，无需 API Key）
- info 操作仅获取页面元信息，不会打开浏览器窗口
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
