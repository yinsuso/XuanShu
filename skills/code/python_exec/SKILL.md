---
name: python_exec
description: 安全执行 Python 代码，支持超时控制和输出限制。当 Agent 需要运行 Python 脚本、测试代码片段、执行计算任务、验证代码逻辑或进行数据处理时调用此技能。执行前需要用户确认。
category: code
requires_confirmation: True
version: "1.0"
author: 破执
tags: ["python", "code", "execute", "script", "calculation", "test"]
parameters:
  - name: "code"
    type: "string"
    description: "要执行的 Python 代码。支持多行代码、函数定义、import 语句。代码将在隔离环境中执行。"
    required: true
  - name: "timeout"
    type: "integer"
    description: "执行超时时间（秒），默认 10 秒。对于复杂计算或网络请求，建议设置为 30-60 秒。"
    required: false
    default: 10
---

## Core Capability
在隔离环境中安全执行 Python 代码，捕获标准输出和错误输出，支持超时控制防止死循环。是 Agent 进行代码验证、数据处理、快速计算、自动化测试的核心能力。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **代码验证**：用户要求"帮我测试这段代码是否能运行"、"验证这个函数的逻辑"
- **快速计算**：需要进行数学计算、数据统计、格式转换等
- **数据处理**：对已有数据进行清洗、转换、分析
- **脚本执行**：执行已写好的 Python 脚本文件（配合 file_read 读取脚本内容）
- **正则测试**：测试正则表达式是否匹配目标文本
- **API 调试**：编写小段代码测试 API 接口的响应
- **算法验证**：验证某个算法或逻辑的正确性

**判断标准**：当 Agent 需要执行 Python 代码来完成计算、验证、测试或数据处理时，使用此技能。

## Parameters

| Name    | Type    | Description                                           | Required | Default |
| ------- | ------- | ----------------------------------------------------- | -------- | ------- |
| code    | string  | 要执行的 Python 代码                                  | Yes      | -       |
| timeout | integer | 执行超时时间（秒），默认 10 秒                        | No       | 10      |

## Example Usage

### 场景1：简单计算
```json
{
  "skill": "python_exec",
  "args": {
    "code": "result = sum(range(1, 101))\nprint(f'1到100的和为: {result}')",
    "timeout": 5
  }
}
```

### 场景2：数据处理与格式转换
```json
{
  "skill": "python_exec",
  "args": {
    "code": "import json\n\ndata = {'name': '玄枢', 'version': '1.0', 'features': ['agent', 'multi-agent']}\nprint(json.dumps(data, ensure_ascii=False, indent=2))",
    "timeout": 10
  }
}
```

### 场景3：正则表达式测试
```json
{
  "skill": "python_exec",
  "args": {
    "code": "import re\n\ntext = '联系邮箱: admin@example.com, 电话: 13800138000'\nemail_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}'\nemails = re.findall(email_pattern, text)\nprint(f'找到邮箱: {emails}')",
    "timeout": 10
  }
}
```

### 场景4：文件操作测试
```json
{
  "skill": "python_exec",
  "args": {
    "code": "import os\n\n# 列出当前目录文件\nfiles = os.listdir('.')\nprint(f'当前目录文件: {files}')\n\n# 检查某个文件是否存在\nprint(f'config.py 存在: {os.path.exists(\"config.py\")}')",
    "timeout": 10
  }
}
```

### 场景5：执行已有脚本（先 file_read 读取）
```json
{
  "skill": "python_exec",
  "args": {
    "code": "exec(open('scripts/data_analysis.py').read())",
    "timeout": 30
  }
}
```

## Execution Signature
```python
def python_exec.execute(code: str, timeout: int = 10, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
返回代码的标准输出（stdout）内容：

```
1到100的和为: 5050
```

### 错误返回
- 语法错误：`❌ 执行失败: SyntaxError: invalid syntax (line 3)`
- 运行时异常：`❌ 执行失败: NameError: name 'undefined_var' is not defined`
- 超时：`❌ 执行超时: 代码执行超过 10 秒限制`
- 输出截断：`⚠️ 输出过长，已截断显示前 2000 字符`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **file_read → python_exec**：读取脚本文件内容 → 执行脚本
2. **python_exec → file_write**：执行代码生成数据 → 将结果写入文件
3. **web_fetch → python_exec**：抓取网页数据 → 用 Python 解析处理
4. **database_query → python_exec**：查询数据库 → 用 Python 分析和可视化

## Best Practices（最佳实践）

1. **超时设置**：简单计算 5-10 秒足够；涉及网络请求建议 30-60 秒；大数据处理建议 120 秒
2. **输出控制**：代码中使用 `print()` 输出结果，避免直接返回变量（会被忽略）
3. **异常处理**：在代码中使用 `try-except` 捕获异常，输出友好的错误信息
4. **代码简洁**：单次执行的代码不宜过长，复杂逻辑建议拆分为多个步骤
5. **依赖检查**：使用 `import` 前确认依赖库是否已安装，可用 `try-except ImportError` 处理

## Safety Notes（安全提示）

- **用户确认**：此技能需要用户确认后才能执行，防止误操作
- **隔离环境**：代码在隔离环境中执行，无法直接访问宿主机敏感资源
- **禁止操作**：禁止执行删除文件、修改系统配置、访问敏感路径等破坏性操作
- **资源限制**：执行有超时限制和内存限制，防止恶意代码耗尽资源
- **网络访问**：部分环境可能限制网络访问，涉及网络请求的代码可能失败

## Notes
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 代码执行后，环境中的变量不会保留到下一次执行
- 标准错误（stderr）会被捕获并返回，便于调试
- 对于需要持久化的结果，建议结合 `file_write` 保存到文件
