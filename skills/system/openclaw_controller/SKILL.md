---
name: openclaw_controller
description: 控制 OpenClaw 执行任务，通过 HTTP API 发送任务并获取结果。当需要调用 OpenClaw 执行独立任务、分布式计算或跨平台协作时调用此技能。
category: system
requires_confirmation: True
version: "1.0"
author: 破执
tags: ["openclaw", "agent", "remote", "task", "distributed"]
parameters:
  - name: "action"
    type: "string"
    description: "操作类型: send_task(发送任务), get_status(获取状态), get_result(获取结果), list_tasks(列出任务)"
    required: true
  - name: "host"
    type: "string"
    description: "OpenClaw 地址，默认 http://localhost:18789"
    required: false
    default: "http://localhost:18789"
  - name: "task_description"
    type: "string"
    description: "任务描述（action=send_task 时必填）"
    required: false
    default: ""
  - name: "task_id"
    type: "string"
    description: "任务ID（action=get_status/get_result 时必填）"
    required: false
    default: ""
  - name: "timeout"
    type: "integer"
    description: "请求超时时间（秒），默认 30"
    required: false
    default: 30
---

## Core Capability
通过 HTTP API 与 OpenClaw 通信，实现远程任务分发和结果获取。支持发送任务、查询状态、获取结果、列出任务等完整生命周期管理。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **分布式计算**：将复杂任务分发到 OpenClaw 执行
- **跨平台协作**：与运行 OpenClaw 的其他机器协作
- **负载分流**：将任务 offload 到远程 OpenClaw
- **结果收集**：获取 OpenClaw 上任务执行结果

**判断标准**：当需要与 OpenClaw 交互时，使用此技能。

## Parameters

| Name             | Type    | Description                        | Required | Default                  |
| ---------------- | ------- | ---------------------------------- | -------- | ------------------------ |
| action           | string  | 操作类型                           | Yes      | -                        |
| host             | string  | OpenClaw 地址                      | No       | http://localhost:18789    |
| task_description | string  | 任务描述                           | No       | ""                       |
| task_id          | string  | 任务ID                             | No       | ""                       |
| timeout          | integer | 超时时间（秒）                     | No       | 30                       |

## Supported Actions

| Action     | 说明         | 必填参数         |
| ---------- | ------------ | ---------------- |
| send_task  | 发送任务     | task_description |
| get_status | 获取任务状态 | task_id          |
| get_result | 获取任务结果 | task_id          |
| list_tasks | 列出所有任务 | 无               |

## Example Usage

### 场景1：发送任务
```json
{
  "skill": "openclaw_controller",
  "args": {
    "action": "send_task",
    "host": "http://192.168.1.101:18789",
    "task_description": "分析这段代码的安全漏洞"
  }
}
```

### 场景2：获取任务状态
```json
{
  "skill": "openclaw_controller",
  "args": {
    "action": "get_status",
    "host": "http://192.168.1.101:18789",
    "task_id": "task-xyz789"
  }
}
```

### 场景3：获取任务结果
```json
{
  "skill": "openclaw_controller",
  "args": {
    "action": "get_result",
    "task_id": "task-xyz789"
  }
}
```

## Execution Signature
```python
def execute(action: str, host: str = "http://localhost:18789",
            task_description: str = "", task_id: str = "",
            timeout: int = 30, **kwargs) -> str:
    ...
```

## Notes
- OpenClaw 需要运行并暴露 HTTP API
- 默认地址为 http://localhost:18789，可修改为远程地址
- 任务ID由 OpenClaw 生成并返回
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
