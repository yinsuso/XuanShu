---
name: opencli_exec
description: 执行 opencli 命令，获取命令输出结果。支持 help、version、list 等所有 opencli 子命令。当 Agent 需要执行 opencli 相关操作、查询 opencli 版本或获取帮助信息时调用此技能。
category: system
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["opencli", "cli", "command", "system", "tool"]
parameters:
  - name: "command"
    type: "string"
    description: "要执行的 opencli 子命令（不包含 'opencli' 前缀），例如 'help'、'version'、'list'、'status'。不填则执行 opencli 不带参数。"
    required: false
    default: ""
  - name: "timeout"
    type: "integer"
    description: "执行超时时间（秒），默认 30 秒。对于耗时较长的命令，可适当增大。"
    required: false
    default: 30
---

## Core Capability
在系统中查找并执行 opencli 可执行文件，返回命令的标准输出结果。支持 Windows、Linux、macOS 三大平台，自动在系统 PATH 和常见安装路径中查找 opencli。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **查询版本**：需要确认 opencli 是否已安装及版本号
- **获取帮助**：需要查看 opencli 支持的子命令和用法
- **执行子命令**：需要执行 opencli 的某个特定功能（如 `list`、`status`）
- **故障排查**：opencli 相关功能异常时，检查 opencli 状态
- **环境检查**：项目依赖 opencli 时，检查环境是否满足要求

**判断标准**：当需要执行 opencli 命令或查询 opencli 信息时，使用此技能。

## Parameters

| Name    | Type    | Description                                           | Required | Default |
| ------- | ------- | ----------------------------------------------------- | -------- | ------- |
| command | string  | 要执行的 opencli 子命令（不包含 'opencli' 前缀）      | No       | ""      |
| timeout | integer | 执行超时时间（秒），默认 30 秒                        | No       | 30      |

## Supported Commands（常用命令）

| Command   | 说明                     | 示例用法                    |
| --------- | ------------------------ | --------------------------- |
| `help`    | 显示帮助信息             | `execute(command="help")`   |
| `version` | 显示版本号               | `execute(command="version")` |
| `list`    | 列出可用资源或模块       | `execute(command="list")`   |
| `status`  | 查看当前状态             | `execute(command="status")`  |

> 注：实际支持的子命令取决于 opencli 的版本和安装配置。

## Example Usage

### 场景1：获取 opencli 帮助信息
```json
{
  "skill": "opencli_exec",
  "args": {
    "command": "help"
  }
}
```

### 场景2：查询 opencli 版本
```json
{
  "skill": "opencli_exec",
  "args": {
    "command": "version"
  }
}
```

### 场景3：执行 list 命令
```json
{
  "skill": "opencli_exec",
  "args": {
    "command": "list",
    "timeout": 60
  }
}
```

### 场景4：执行状态查询（自定义超时）
```json
{
  "skill": "opencli_exec",
  "args": {
    "command": "status",
    "timeout": 45
  }
}
```

### 场景5：不带参数执行 opencli
```json
{
  "skill": "opencli_exec",
  "args": {}
}
```

## Execution Signature
```python
def execute(command: str = "", timeout: int = 30, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
```
✅ opencli 执行成功:
opencli version 2.1.0
Build: 2024-01-15
Platform: windows/amd64
```

### 错误返回
- 命令执行失败：`❌ opencli 命令执行失败: [错误信息]`
- 执行超时：`❌ opencli 命令执行超时: 超过 30 秒限制`
- 未找到 opencli：`❌ 未找到 opencli 可执行文件，请确认已安装并添加到 PATH`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **opencli_exec → python_exec**：获取 opencli 输出后，用 Python 解析处理
2. **opencli_exec → file_write**：将 opencli 的输出结果保存到日志文件
3. **file_read → opencli_exec**：读取配置文件获取 opencli 配置后，执行相关命令

## Best Practices（最佳实践）

1. **超时设置**：简单命令（如 `version`、`help`）10 秒足够；复杂命令（如 `list`）建议 30-60 秒
2. **命令格式**：`command` 参数不需要包含 `opencli` 前缀，直接传入子命令即可
3. **错误处理**：执行失败时，先检查 opencli 是否已安装（执行 `command="version"` 验证）
4. **输出解析**：返回的文本输出可能需要进一步解析，可配合 `python_exec` 处理

## Safety Notes（安全提示）

- **命令安全**：仅执行已知的 opencli 子命令，不要执行用户输入的任意命令
- **权限检查**：部分 opencli 命令可能需要管理员权限，执行失败时考虑权限问题
- **环境依赖**：确保 opencli 已正确安装并添加到系统 PATH

## Notes
- 该技能会自动在系统 PATH 和常见安装路径中查找 opencli 可执行文件
- 支持 Windows、Linux、macOS 三大平台
- 命令参数不需要包含 'opencli' 前缀
- 默认超时时间为 30 秒，可根据需要调整
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
