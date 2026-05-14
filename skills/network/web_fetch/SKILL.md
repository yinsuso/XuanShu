---
name: web_fetch
description: 抓取网页内容并清洗为纯文本，支持自动识别相对路径，处理常见反爬策略。
category: network
requires_confirmation: false
version: "1.0"
author: 破执
tags: []
parameters:
  - name: url
    type: string
    description: 要抓取的网页 URL 地址
  - name: timeout
    type: integer
    description: 请求超时时间（秒），默认 10 秒
    default: 10
---

## Core Capability
抓取网页内容并清洗为纯文本，支持自动识别相对路径，处理常见反爬策略。

## Trigger Scenario
当需要读取网页内容、分析 URL 信息或获取网络数据时使用。

## Parameters
| Name | Type   | Description                                         | Required | Default |
| ---- | ------ | --------------------------------------------------- | -------- | ------- |
| url  | string | 要抓取的网页 URL 地址                               | Yes      | -       |
| timeout | integer | 请求超时时间（秒），默认 10 秒                      | No       | 10      |

## Example Usage
```json
{
  "skill": "web_fetch",
  "args": {
    "url": "https://example.com"
  }
}
```

## Execution Signature
```python
def execute(url: str, timeout: int = 10, **kwargs) -> str:
    ...
```

## Notes
- This skill now accepts extra parameters via `**kwargs`; unknown arguments are safely ignored.
- The underlying implementation uses `fetch_webpage_text` from utils.net_utils; ensure network connectivity and optionally install `bs4` for enhanced parsing.
