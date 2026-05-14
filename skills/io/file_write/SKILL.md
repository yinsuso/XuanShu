---
name: file_write
description: 写入内容到指定文件，自动创建父目录。当 Agent 需要创建新文件、修改现有代码、保存配置或写入任何文本内容时调用此技能。
category: io
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["file", "write", "io", "create", "modify"]
parameters:
  - name: "path"
    type: "string"
    description: "文件绝对路径或相对路径。若文件已存在则覆盖写入；若目录不存在会自动创建父目录。"
    required: true
  - name: "content"
    type: "string"
    description: "要写入的完整文本内容。对于代码文件，请确保缩进、换行符和语法正确。"
    required: true
---

## Core Capability
将文本内容写入指定文件。支持自动创建不存在的父目录，支持覆盖已有文件。是 Agent 进行代码生成、配置保存、日志记录、文档创建的核心能力。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **代码生成**：用户要求"帮我写一个 Python 脚本"、"生成一个配置文件"
- **代码修改**：分析完现有代码后，将修改后的代码写回文件
- **配置保存**：根据用户输入生成并保存配置项
- **日志记录**：将运行结果、分析摘要保存到文件
- **文档创建**：生成项目文档、使用说明等
- **数据导出**：将查询结果、分析数据导出为 JSON/CSV/TXT 文件

**判断标准**：当 Agent 需要将文本内容持久化到磁盘文件时，使用此技能。

## Parameters

| Name    | Type   | Description                                           | Required | Default |
| ------- | ------ | ----------------------------------------------------- | -------- | ------- |
| path    | string | 文件绝对路径或相对路径                                | Yes      | -       |
| content | string | 要写入的完整文本内容                                  | Yes      | -       |

## Example Usage

### 场景1：创建新的 Python 脚本
```json
{
  "skill": "file_write",
  "args": {
    "path": "scripts/hello.py",
    "content": "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n\ndef main():\n    print('Hello, 玄枢!')\n\nif __name__ == '__main__':\n    main()\n"
  }
}
```

### 场景2：修改现有配置文件
```json
{
  "skill": "file_write",
  "args": {
    "path": "config/settings.json",
    "content": "{\n  \"debug\": false,\n  \"port\": 8080,\n  \"host\": \"0.0.0.0\"\n}\n"
  }
}
```

### 场景3：保存分析结果到日志文件
```json
{
  "skill": "file_write",
  "args": {
    "path": "logs/analysis_2024-01-15.log",
    "content": "[2024-01-15 10:30:00] 安全审计完成\n发现问题: 3 个\n建议: 立即修复 SQL 注入漏洞\n"
  }
}
```

## Execution Signature
```python
def file_write.execute(path: str, content: str, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
```
✅ 文件写入成功: /absolute/path/to/file
```

### 错误返回
- 路径为目录：`错误: '/path/to/dir' 是目录，无法写入`
- 权限不足：`错误: 没有权限写入文件 '/path/to/file'`
- 磁盘空间不足：`错误: 磁盘空间不足，无法写入`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **file_read → file_write**：先读取原文件 → 分析修改需求 → 写入修改后的内容
2. **python_exec → file_write**：执行脚本生成数据 → 将结果写入文件
3. **web_fetch → file_write**：抓取网页内容 → 清洗后保存到本地文件
4. **file_write → python_exec**：写入脚本后，立即执行验证

## Best Practices（最佳实践）

1. **修改前备份**：修改重要文件前，建议先 `file_read` 读取原内容，或告知用户备份
2. **路径确认**：使用绝对路径避免歧义；若使用相对路径，确保相对于项目根目录
3. **内容检查**：写入代码文件前，在思维链中检查缩进（4空格）、语法正确性
4. **原子写入**：对于重要文件，先写入临时文件，确认无误后再覆盖原文件
5. **编码统一**：文本内容统一使用 UTF-8 编码，换行符使用 `\n`

## Safety Notes（安全提示）

- **覆盖警告**：此技能会覆盖已有文件，执行前请确认路径正确
- **敏感文件**：谨慎修改系统配置文件（如 `/etc/` 下文件），修改前请确认影响范围
- **权限检查**：确保 Agent 对目标目录有写入权限

## Notes
- 自动创建父目录功能依赖操作系统权限，若目录创建失败会返回错误
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 写入内容过大时（如 >10MB），建议分块写入或使用其他方式
