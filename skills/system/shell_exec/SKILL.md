---
name: shell_exec
description: 执行系统 Shell 命令，支持 Windows、Linux、macOS 三平台。自动识别当前操作系统并适配命令格式。当需要执行系统命令、查看系统信息、操作文件系统或运行命令行工具时调用此技能。
category: system
requires_confirmation: True
version: "1.0"
author: 破执
tags: ["shell", "command", "system", "cli", "terminal"]
parameters:
  - name: "command"
    type: "string"
    description: "要执行的命令内容"
    required: true
  - name: "shell"
    type: "boolean"
    description: "是否使用 shell 执行（默认 True）。简单命令可设为 False 更安全"
    required: false
    default: true
  - name: "timeout"
    type: "integer"
    description: "执行超时时间（秒），默认 30 秒"
    required: false
    default: 30
  - name: "working_dir"
    type: "string"
    description: "工作目录（可选），默认当前目录"
    required: false
    default: ""
---

## Core Capability
在 Windows、Linux、macOS 三大操作系统上执行 Shell 命令，自动识别当前系统并适配命令格式。支持 CMD、PowerShell、Bash、Zsh 等常见 shell。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **系统信息查询**：查看系统版本、CPU、内存、磁盘等信息
- **文件系统操作**：列出目录、复制移动文件、查找文件等
- **网络诊断**：ping、curl、wget、netstat、ipconfig/ifconfig 等
- **进程管理**：查看进程、结束进程等
- **软件包管理**：apt/yum/brew/npm/pip 等包管理器操作
- **Git 操作**：git clone、git pull、git status 等
- **构建编译**：make、cmake、gcc、msbuild 等
- **服务管理**：systemctl、service、sc 等

**判断标准**：当需要执行系统级命令行操作时，使用此技能。

## Parameters

| Name        | Type    | Description                                           | Required | Default |
| ----------- | ------- | ----------------------------------------------------- | -------- | ------- |
| command     | string  | 要执行的命令内容                                      | Yes      | -       |
| shell       | boolean | 是否使用 shell 执行                                   | No       | true    |
| timeout     | integer | 执行超时时间（秒）                                    | No       | 30      |
| working_dir | string  | 工作目录（可选）                                      | No       | ""      |

## Supported Platforms

| 平台    | Shell 类型     | 说明                          |
| ------- | -------------- | ----------------------------- |
| Windows | CMD / PowerShell | 自动检测 PowerShell 语法      |
| Linux   | Bash / Sh      | 使用默认 shell 执行           |
| macOS   | Bash / Zsh     | 使用默认 shell 执行           |

## Example Usage

### 场景1：查看系统信息（Linux/macOS）
```json
{
  "skill": "shell_exec",
  "args": {
    "command": "uname -a && df -h"
  }
}
```

### 场景2：查看系统信息（Windows）
```json
{
  "skill": "shell_exec",
  "args": {
    "command": "systeminfo | findstr /B /C:\"OS\""
  }
}
```

### 场景3：列出目录内容
```json
{
  "skill": "shell_exec",
  "args": {
    "command": "ls -la",
    "working_dir": "/home/user/projects"
  }
}
```

### 场景4：Git 操作
```json
{
  "skill": "shell_exec",
  "args": {
    "command": "git status",
    "working_dir": "./my-project",
    "timeout": 10
  }
}
```

### 场景5：网络诊断
```json
{
  "skill": "shell_exec",
  "args": {
    "command": "ping -c 4 google.com",
    "timeout": 15
  }
}
```

### 场景6：PowerShell 命令（Windows）
```json
{
  "skill": "shell_exec",
  "args": {
    "command": "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5"
  }
}
```

## Execution Signature
```python
def execute(command: str, shell: bool = True, timeout: int = 30, working_dir: str = "", **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
```
✅ 执行成功 (linux):
总用量 128
drwxr-xr-x  5 user user  4096 May 15 10:00 .
drwxr-xr-x 20 user user  4096 May 14 09:00 ..
```

### 错误返回
- 命令执行失败：`❌ 命令执行失败 (退出码 1): [错误信息]`
- 执行超时：`❌ 命令执行超时 (超过 30s)`
- 命令未找到：`❌ 命令未找到: [命令名]`
- 安全拦截：`❌ 命令包含危险操作，已被安全拦截`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **shell_exec → file_read**：执行命令获取文件路径后读取内容
2. **shell_exec → file_write**：将命令输出保存到文件
3. **shell_exec → python_exec**：命令输出用 Python 进一步处理

## Best Practices（最佳实践）

1. **超时设置**：简单命令 10-15 秒足够；网络操作建议 30-60 秒
2. **工作目录**：涉及相对路径时，显式设置 working_dir
3. **安全性**：避免执行用户输入的未经验证的命令
4. **跨平台**：尽量使用跨平台命令，或根据系统分别处理
5. **输出控制**：命令输出可能很长，必要时使用管道过滤

## Safety Notes（安全提示）

- **危险命令拦截**：自动拦截 rm -rf /、format、dd 等破坏性命令
- **确认机制**：该技能默认需要用户确认后执行
- **权限注意**：部分命令可能需要管理员/root 权限
- **编码处理**：Windows 使用 GBK/UTF-8，Linux/macOS 使用 UTF-8

## Notes
- 支持 Windows CMD、PowerShell、Linux Bash、macOS Zsh/Bash
- 自动识别 PowerShell 语法（以 Get-/Set-/Write- 等开头的命令）
- 命令输出长度限制为 3000 字符，超出部分会被截断
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
