---
name: file_list
description: 列出指定目录下的文件和子目录。当 Agent 需要浏览项目结构、查找特定文件、确认目录内容或探索未知目录时调用此技能。
category: io
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["file", "list", "directory", "browse", "explore"]
parameters:
  - name: "path"
    type: "string"
    description: "目录路径（相对于项目根目录）。使用 '.' 表示当前目录，'..' 表示上级目录。支持绝对路径。"
    required: false
    default: "."
---

## Core Capability
列出指定目录下的所有文件和子目录，返回树形结构或列表形式的目录内容。是 Agent 探索项目结构、定位目标文件、了解目录组织方式的基础能力。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **项目初探**：首次接触项目时，浏览整体目录结构，了解项目组织方式
- **文件定位**：用户提到某个文件名但不完整时，通过目录列表确认完整路径
- **确认存在性**：执行 `file_read` 或 `file_write` 前，先确认目标目录是否存在
- **批量操作前**：需要对某个目录下的多个文件进行操作前，先列出文件清单
- **查找特定类型文件**：如查找所有 `.py` 文件、所有 `.md` 文档
- **验证创建结果**：执行 `file_write` 创建文件后，验证文件是否成功创建

**判断标准**：当 Agent 需要了解"某个目录下有什么"时，使用此技能。

## Parameters

| Name | Type   | Description                                           | Required | Default |
| ---- | ------ | ----------------------------------------------------- | -------- | ------- |
| path | string | 目录路径（相对于项目根目录）。'.' 表示当前目录       | No       | .       |

## Example Usage

### 场景1：浏览项目根目录结构
```json
{
  "skill": "file_list",
  "args": {
    "path": "."
  }
}
```

### 场景2：查看特定模块目录
```json
{
  "skill": "file_list",
  "args": {
    "path": "skills"
  }
}
```

### 场景3：查看深层目录
```json
{
  "skill": "file_list",
  "args": {
    "path": "evolution/cluster"
  }
}
```

## Execution Signature
```python
def file_list.execute(path: str = ".", **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
返回目录内容的树形结构，包含文件和子目录：

```
📁 skills/
  📁 audit/
    📁 project_security_audit/
      📄 SKILL.md
      📄 project_security_audit.py
  📁 code/
    📁 python_exec/
      📄 SKILL.md
      📄 python_exec.py
  📁 io/
    📁 file_list/
    📁 file_read/
    📁 file_write/
  📄 base.py
  📄 __init__.py
```

### 错误返回
- 路径不存在：`错误: 路径 '/path/to/dir' 不存在`
- 路径为文件：`错误: '/path/to/file' 是文件，不是目录`
- 权限不足：`错误: 没有权限访问目录 '/path/to/dir'`

## Agent Workflow（工作流协作）

此技能通常作为工作流的**第一步**使用：

1. **file_list → file_read**：先浏览目录找到目标文件 → 读取文件内容
2. **file_list → file_write**：确认目标目录存在 → 在目标目录下创建新文件
3. **file_list → python_exec**：确认脚本存在 → 执行脚本
4. **file_list → file_list**：逐层深入，从根目录到子目录逐步探索

## Best Practices（最佳实践）

1. **从根目录开始**：首次接触项目时，先 `path: "."` 浏览根目录，建立整体认知
2. **逐层深入**：不要一次列出过深层级，逐层探索更易理解
3. **结合 file_read**：找到关键文件（如 `README.md`、`agent.py`）后，立即读取获取详细信息
4. **验证路径**：用户提供的相对路径不确定时，先用 `file_list` 验证

## Notes
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 对于超大目录（如包含数千个文件的目录），返回结果可能会被截断
- 隐藏文件（以 `.` 开头的文件）通常会显示，但取决于操作系统
