# 玄枢项目技能系统开发规范

## 1. 概述

玄枢项目的技能系统采用 Python 函数装饰器方式注册，每个技能独立目录存放，具备自描述元数据，便于动态加载、版本管理和自动化验证。

## 2. 命名规则

- 使用英文小写 `snake_case` 格式
- 仅允许字符：a-z, 0-9, _
- 长度 ≤ 30 字符
- 示例：`quick_calc`, `web_search`, `data_analyzer`
- 禁止：中文、大写、连字符、空格、标点

## 3. 技能目录结构标准

每个技能必须在 `skills/` 目录下的对应分类中**单独创建一个目录**，目录结构如下：

```
skills/
├── __init__.py
├── base.py
├── code/
│   └── python_exec/
│       ├── python_exec.py      # 技能实现代码
│       └── SKILL.md            # 技能详细说明文档
├── io/
│   └── file_list/
│       ├── file_list.py
│       └── SKILL.md
└── ...
```

### 3.1 目录命名规则

- 目录名与技能名保持一致（snake_case）
- 必须包含两个文件：
  1. **`<skill_name>.py`** — 技能实现代码
  2. **`SKILL.md`** — 技能详细说明文档

### 3.2 SKILL.md 文件规范

`SKILL.md` 必须包含以下完整信息：

```yaml
---
name: skill_name
description: 技能描述
category: io
category: io
requires_confirmation: false
version: "1.0"
author: 作者名
tags: ["tag1", "tag2"]
parameters:
  - name: "param1"
    type: "string"
    description: "参数说明"
    required: true
  - name: "param2"
    type: "integer"
    description: "参数说明"
    required: false
    default: 10
---

## Core Capability
技能核心能力的简要说明。

## Trigger Scenario（触发场景）

以下场景应调用此技能：

- **场景1**：具体场景描述
- **场景2**：具体场景描述

**判断标准**：何时应该使用此技能的明确判断条件。

## Parameters

| Name | Type | Description | Required | Default |
|------|------|-------------|----------|---------|
| param1 | string | 参数说明 | Yes | - |
| param2 | integer | 参数说明 | No | 10 |

## Example Usage

### 场景1：示例场景
```json
{
  "skill": "skill_name",
  "args": {
    "param1": "value1"
  }
}
```

## Execution Signature
```python
def execute(param1: str, param2: int = 10, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
描述成功时的返回格式和内容。

### 错误返回
- 错误情况1：`错误: 具体错误信息`
- 错误情况2：`错误: 具体错误信息`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **skill_a → skill_b**：先做什么 → 再做什么

## Best Practices（最佳实践）

1. 使用建议1
2. 使用建议2

## Notes
- 其他注意事项
```

## 4. 技能代码规范

### 4.1 导入规范

```python
from skills.base import skill, SkillCategory
```

必须使用绝对导入，不得使用相对导入（如 `from .base import`）。

### 4.2 装饰器元数据

使用 `@skill` 装饰器，参数包括：
- `name` (str): 技能标识，符合命名规则
- `description` (str): 简短描述，≤100 字
- `category` (SkillCategory): 引用 `SkillCategory` 枚举
- `version` (str): 版本，语义化版本如 "1.0.0"
- `author` (str, optional): 作者
- `requires_confirmation` (bool, default=False): 是否需要用户确认执行
- `deprecated` (bool, default=False): 是否已废弃

### 4.3 函数定义

- 参数需类型标注（可包含默认值）
- 返回值必须类型标注
- 必须包含文档字符串（docstring）说明功能、参数、返回值
- 函数名建议为明确的动词（如 `fetch`, `calc`）

### 4.4 错误处理与日志

- 使用 `try/except` 捕获异常
- 记录错误日志 `logger.error(...)` 并返回用户友好的错误信息
- 避免未处理的异常导致 Agent 崩溃

## 5. 实现步骤

1. 在 `skills/` 下找到或创建合适的分类目录（如 `io/`, `code/`, `network/`）
2. 在该分类目录下**创建与技能同名的子目录**（如 `skills/io/my_skill/`）
3. 在子目录中创建两个文件：
   - `<skill_name>.py` — 技能实现代码
   - `SKILL.md` — 技能详细说明文档
4. 编写导入、装饰器和函数
5. 保存后重启服务或动态加载
6. 使用 `skill_validator` 验证：
   ```bash
   python -m evolution.skill_validator
   ```
7. 通过 `list_skills()` 查看注册情况

## 6. 完整示例

### 目录结构

```
skills/utility/quick_calc/
├── quick_calc.py
└── SKILL.md
```

### 技能代码：quick_calc.py

```python
from skills.base import skill, SkillCategory
import logging

logger = logging.getLogger(__name__)

@skill(
    name="quick_calc",
    description="执行快速算术运算：支持加减乘除、幂运算",
    category=SkillCategory.UTILITY,
    version="1.0.0",
    author="玄枢团队",
    requires_confirmation=False
)
def calculate(expression: str) -> str:
    """计算一个数学表达式并返回结果。

    参数:
      expression (str): 数学表达式字符串，例如 "2 + 3 * 4"

    返回:
      str: 计算结果或错误信息
    """
    try:
        # 安全检查：只允许数字、运算符和小数点
        allowed = set("0123456789.+-*/() ")
        if not all(c in allowed for c in expression):
            return "❌ 表达式包含非法字符"
        # 使用 eval（生产环境建议使用 ast 或解析器）
        result = eval(expression, {"__builtins__": None}, {})
        return f"🧮 结果: {result}"
    except Exception as e:
        logger.error(f"计算失败: {expression}, 错误: {e}")
        return f"⚠️ 计算错误: {e}"
```

### 技能文档：SKILL.md

```yaml
---
name: quick_calc
description: 执行快速算术运算：支持加减乘除、幂运算
category: utility
requires_confirmation: false
version: "1.0.0"
author: 玄枢团队
tags: ["math", "calc", "utility"]
parameters:
  - name: "expression"
    type: "string"
    description: "数学表达式字符串，例如 '2 + 3 * 4'"
    required: true
---

## Core Capability
执行快速算术运算，支持加减乘除、幂运算等基础数学操作。

## Trigger Scenario（触发场景）

以下场景应调用此技能：

- **数学计算**：用户需要进行简单的数学运算
- **数据验证**：验证某个数值计算结果
- **快速换算**：进行单位换算或比例计算

**判断标准**：当用户需要执行数学表达式计算时，使用此技能。

## Parameters

| Name | Type | Description | Required | Default |
|------|------|-------------|----------|---------|
| expression | string | 数学表达式字符串 | Yes | - |

## Example Usage

```json
{
  "skill": "quick_calc",
  "args": {
    "expression": "2 + 3 * 4"
  }
}
```

## Execution Signature
```python
def calculate(expression: str) -> str:
    ...
```

## Output Format

### 成功返回
```
🧮 结果: 14
```

### 错误返回
- 非法字符：`❌ 表达式包含非法字符`
- 计算错误：`⚠️ 计算错误: ...`

## Notes
- 仅支持基础算术运算符：+, -, *, /, ()
- 出于安全考虑，不支持函数调用和变量引用
```

## 7. 调试与测试

- 启用开发模式：在配置中设置 `development_mode = True`
- 查看日志：`logs/agent.log` 或控制台输出
- 测试调用：
  ```bash
  curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message":"用 quick_calc 计算 12*12"}'
  ```
- 验证语法：`python -m py_compile skills/utility/quick_calc/quick_calc.py`

## 8. 升级与兼容

- 修改后递增 `version`
- 尽量保持参数向后兼容
- 废弃功能标记 `deprecated=True`，保留至少一个版本周期

## 9. 密钥与安全

- 敏感信息（API keys）必须通过环境变量或配置管理读取
  ```python
  import os
  api_key = os.getenv("OPENAI_API_KEY")
  ```
- 禁止在代码中硬编码密钥
- 使用 `config_manager` 加密存储（如适用）

## 10. 模型如何创建技能（面向 AI Agent）

> 本节说明玄枢项目中的 AI Agent（大模型）如何创建和使用技能。

### 10.1 何时应该创建技能

作为 Agent，当你遇到以下情况时，应该主动创建新技能：

1. **用户明确要求**："创建一个XXX技能"
2. **重复性任务**：发现某个任务需要频繁执行相似操作
3. **可自动化流程**：用户描述了一个可以通过 Python 代码自动化的流程

### 10.2 创建技能的方法

在对话中，你可以直接输出完整的 Python 技能代码。系统会自动检测、验证并注册该技能。

**输出格式**：

```python
from skills.base import skill, SkillCategory

@skill(
    name="skill_name",  # 英文小写 snake_case
    description="技能描述",
    category=SkillCategory.UTILITY
)
def your_function(param1: str, param2: int = 0) -> str:
    """函数文档字符串"""
    try:
        # 实现代码
        result = f"处理结果: {param1}"
        return result
    except Exception as e:
        return f"错误: {e}"
```

**关键规范**：
- `name` 必须使用英文小写 snake_case（如 `quick_calc`, `web_search`）
- 仅允许字符：a-z, 0-9, _
- 长度 ≤ 30 字符
- 禁止使用中文、大写、连字符、空格、标点
- 必须使用绝对导入 `from skills.base import skill, SkillCategory`

### 10.3 技能创建后的存储结构

**单机模式**：
- 创建的技能保存在 `skills/auto_generated/` 目录下
- 系统会自动为每个技能创建独立目录并生成对应的 `SKILL.md` 文件
- 如需分享，需要手动复制代码

**协作模式**：
- **房主节点**创建技能后，系统会自动通过 `SKILL_SYNC` 消息广播到所有 Worker 节点
- Worker 节点会自动接收并加载新技能
- 同步失败时系统会记录日志，不会阻塞主流程
- 你可以在创建技能后询问成员是否已成功接收

### 10.4 创建后立即调用

技能创建并验证通过后，会立即出现在可用技能列表中。你可以直接调用：

```json
{ "skill": "你刚创建的技能名", "args": { "参数名": "参数值" } }
```

## 11. 常见问题 (FAQ)

- **Q: 技能未被加载？**
  A: 检查语法错误、装饰器参数、导入路径；查看启动日志。确保技能文件位于正确的目录结构中。

- **Q: 如何调试？**
  A: 查看 `logs/skills.log`，确保 `SkillValidator` 通过。

- **Q: 如何删除/禁用技能？**
  A: 删除文件后重启，或标记 `deprecated=True`。

- **Q: 命名冲突怎么办？**
  A: 系统拒绝重复名称，请更名。

- **Q: 模型创建的技能如何同步给其他成员？**
  A: 协作模式下，房主节点创建的技能会自动广播到所有 Worker。单机模式下需要手动复制代码文件。

- **Q: 技能创建失败怎么办？**
  A: 检查：1) 名称是否符合 snake_case 规范 2) 是否使用了绝对导入 3) 语法是否正确 4) 是否包含 SKILL.md 文件。查看 `logs/agent.log` 获取详细错误信息。

## 12. 与 破执 对照

本规范参考 破执 的 skill 设计：
- 使用 `@skill` 装饰器作为注册机制
- 通过元数据实现自描述
- 强调错误处理与日志
- 支持动态加载与验证

不同的是，玄枢采用目录结构组织技能，每个技能独立目录并包含 SKILL.md 文件提供丰富文档。

---
**最后更新：** 2026-05-14
**维护者：** 玄枢开发团队
