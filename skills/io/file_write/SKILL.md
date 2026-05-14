---
name: file_write
description: 写入内容到指定文件，自动创建父目录。
category: io
requires_confirmation: False
version: "1.0"
author: 破执
tags: []
parameters:
  -   name: "path"
      type: "string"
      description: "文件绝对路径或相对路径"
  -   name: "content"
      type: "string"
      description: "要写入的内容"
---

## Core Capability
写入内容到指定文件，自动创建父目录。

## Trigger Scenario
当需要创建新文件、修改代码或保存配置时使用。

## Parameters
| Name | Type | Description | Required | Default |
| ---- | ---- | ----------- | -------- | ------- |
| path | string | 文件绝对路径或相对路径 | Yes |  |
| content | string | 要写入的内容 | Yes |  |

## Example Usage
```json
{
  "skill": "file_write",
  "args": {
    "param1": "value"
  }
}
```

## Execution Signature
```python
def file_write.execute(path: string, content: string, **kwargs) -> str:
    ...
```

## Notes
- This skill now accepts extra parameters via `**kwargs`; unknown arguments are safely ignored.