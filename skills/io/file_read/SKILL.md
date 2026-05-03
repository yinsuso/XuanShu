---
name: file_read
description: 读取指定文件内容，支持大文件分块读取。
category: io
requires_confirmation: False
version: "1.0"
author: Hermes Agent
tags: []
parameters:
  -   name: "path"
      type: "string"
      description: "文件绝对路径或相对路径（相对于项目根目录）"
  -   name: "lines"
      type: "integer"
      description: "读取行数（可选），默认读取全部"
      default: 0
---

## Core Capability
读取指定文件内容，支持大文件分块读取。

## Trigger Scenario
当需要查看文件内容、分析代码或读取配置文件时使用。

## Parameters
| Name | Type | Description | Required | Default |
| ---- | ---- | ----------- | -------- | ------- |
| path | string | 文件绝对路径或相对路径（相对于项目根目录） | Yes |  |
| lines | integer | 读取行数（可选），默认读取全部 | No | 0 |

## Example Usage
```json
{
  "skill": "file_read",
  "args": {
    "param1": "value"
  }
}
```

## Execution Signature
```python
def file_read.execute(path: string, lines: integer = 0, **kwargs) -> str:
    ...
```

## Notes
- This skill now accepts extra parameters via `**kwargs`; unknown arguments are safely ignored.