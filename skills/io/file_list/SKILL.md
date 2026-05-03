---
name: file_list
description: 列出指定目录下的文件和子目录。
category: io
requires_confirmation: False
version: "1.0"
author: Hermes Agent
tags: []
parameters:
  -   name: "path"
      type: "string"
      description: "目录路径（相对于项目根目录）"
      default: "."
---

## Core Capability
列出指定目录下的文件和子目录。

## Trigger Scenario
当需要查看项目结构、查找文件时使用。

## Parameters
| Name | Type | Description | Required | Default |
| ---- | ---- | ----------- | -------- | ------- |
| path | string | 目录路径（相对于项目根目录） | No | . |

## Example Usage
```json
{
  "skill": "file_list",
  "args": {
    "param1": "value"
  }
}
```

## Execution Signature
```python
def file_list.execute(path: string = ".", **kwargs) -> str:
    ...
```

## Notes
- This skill now accepts extra parameters via `**kwargs`; unknown arguments are safely ignored.