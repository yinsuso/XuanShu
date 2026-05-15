---
name: file_read
description: 读取指定文件内容，支持大文件分块读取。当 Agent 需要查看代码、分析日志、读取配置文件或获取任何文本文件内容时调用此技能。
category: io
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["file", "read", "io", "content", "code"]
parameters:
  - name: "path"
    type: "string"
    description: "文件绝对路径或相对路径（相对于项目根目录）。支持常见文本格式如 .py, .md, .json, .txt, .yaml, .html 等。"
    required: true
  - name: "lines"
    type: "integer"
    description: "读取行数（可选），默认读取全部。当文件较大时，建议先读取前 50-100 行进行预览。"
    required: false
    default: 0
---

## Core Capability
读取指定文件内容并返回文本。支持大文件分块读取，避免一次性加载超大文件导致内存问题。是 Agent 进行代码审计、日志分析、配置读取的基础能力。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **代码审查**：用户要求"帮我看看这个文件有什么问题"、"分析这段代码"
- **日志排查**：用户要求"查看错误日志"、"分析运行日志"
- **配置读取**：需要读取 `config.py`、`settings.json`、`.env` 等配置文件
- **内容确认**：在执行 `file_write` 前，先读取原文件确认内容；在执行 `python_exec` 前，读取脚本内容
- **依赖分析**：读取 `requirements.txt`、`package.json` 等依赖文件
- **文档阅读**：读取项目文档、README 等获取上下文

**判断标准**：当 Agent 需要获取某个文件的文本内容以进行分析、确认或展示时，优先使用此技能。

## Parameters

| Name  | Type    | Description                                           | Required | Default |
| ----- | ------- | ----------------------------------------------------- | -------- | ------- |
| path  | string  | 文件绝对路径或相对路径（相对于项目根目录）            | Yes      | -       |
| lines | integer | 读取行数（可选），默认读取全部。建议大文件先读前100行 | No       | 0       |

## Example Usage

### 场景1：读取代码文件进行审查
```json
{
  "skill": "file_read",
  "args": {
    "path": "agent.py",
    "lines": 50
  }
}
```

### 场景2：读取日志文件排查错误
```json
{
  "skill": "file_read",
  "args": {
    "path": "logs/error.log",
    "lines": 100
  }
}
```

### 场景3：读取配置文件
```json
{
  "skill": "file_read",
  "args": {
    "path": "config.py"
  }
}
```

## Execution Signature
```python
def file_read.execute(path: str, lines: int = 0, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
返回文件的文本内容，包含行号前缀（如 `1→content`），便于 Agent 精确定位代码位置。

示例：
```
1→import os
2→import sys
3→from typing import Dict, Any
4→
5→class UniversalAgent:
6→    def __init__(self):
7→        self.name = "玄枢"
```

### 错误返回
- 文件不存在：`错误: 文件 '/path/to/file' 不存在`
- 路径为目录：`错误: '/path/to/dir' 是目录，不是文件`
- 权限不足：`错误: 没有权限读取文件 '/path/to/file'`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **file_list → file_read**：先用 `file_list` 浏览目录结构，找到目标文件后，再用 `file_read` 读取内容
2. **file_read → file_write**：读取旧文件 → 分析修改点 → 写入新内容
3. **file_read → python_exec**：读取脚本内容确认无误后，执行脚本
4. **file_read → web_fetch**：读取本地配置后，根据配置去抓取网页

## Best Practices（最佳实践）

1. **大文件策略**：对于日志文件、大型代码文件，先使用 `lines: 50` 或 `lines: 100` 读取开头部分，根据需要再读取更多
2. **路径确认**：优先使用绝对路径；若使用相对路径，确保相对于项目根目录
3. **读取前检查**：如果不确定文件是否存在，可以先通过 `file_list` 确认目录内容
4. **敏感文件**：读取包含密码、密钥的文件时，注意在返回结果中脱敏处理

## Notes
- 该技能仅支持读取文本文件，二进制文件会返回错误或乱码
- 默认编码为 UTF-8，如遇编码错误会尝试其他编码
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 读取大文件时建议分块读取，避免内存占用过高

## 全角数字兼容性说明

**【重要】当技能涉及用户输入数字（如读取行数 lines）时，必须考虑全角数字的兼容性。**

在中文输入环境下，用户可能输入全角数字（如 `５０`、`１００`）而非半角数字（如 `50`、`100`）。本技能已内置全角数字自动转换功能，无需 Agent 额外处理。

**涉及全角数字兼容性的参数：**
- `lines`（读取行数）：支持全角数字输入，如 `５０`、`１００`

**全角数字对照表：**
| 全角 | 半角 |
|------|------|
| ０ | 0 |
| １ | 1 |
| ２ | 2 |
| ３ | 3 |
| ４ | 4 |
| ５ | 5 |
| ６ | 6 |
| ７ | 7 |
| ８ | 8 |
| ９ | 9 |
