---
name: python_exec
description: 安全执行 Python 代码，支持超时控制和输出限制。
category: code
requires_confirmation: True
version: "1.0"
author: Hermes Agent
tags: []
parameters:
  -   name: "code"
      type: "string"
      description: "要执行的 Python 代码"
  -   name: "timeout"
      type: "integer"
      description: "执行超时时间（秒），默认 10 秒"
      default: 10
---

## Core Capability
安全执行 Python 代码，支持超时控制和输出限制。

## Trigger Scenario
当需要运行 Python 脚本、测试代码或执行计算任务时使用。

## Parameters
| Name | Type | Description | Required | Default |
| ---- | ---- | ----------- | -------- | ------- |
| code | string | 要执行的 Python 代码 | Yes |  |
| timeout | integer | 执行超时时间（秒），默认 10 秒 | No | 10 |

## Example Usage
```json
{
  "skill": "python_exec",
  "args": {
    "param1": "value"
  }
}
```

## Execution Signature
```python
def python_exec.execute(code: string, timeout: integer = 10, **kwargs) -> str:
    ...
```

## Notes
- This skill now accepts extra parameters via `**kwargs`; unknown arguments are safely ignored.