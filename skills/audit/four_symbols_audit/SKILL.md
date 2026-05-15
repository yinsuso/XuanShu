---
name: four_symbols_audit
description: 四象审计：在开发/修改代码时执行环境、代码、验证、沟通四维审计。在编写、修改或审查代码时，执行四象审计确保代码质量和安全性。
category: audit
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["audit", "code-review", "quality", "security", "lint"]
parameters:
  - name: "file_path"
    type: "string"
    description: "要审计的文件路径"
    required: true
  - name: "audit_type"
    type: "string"
    description: "审计类型: all(全部), qinglong(青龙-环境), baihu(白虎-代码), zhuque(朱雀-验证), xuanwu(玄武-沟通)"
    required: false
    default: "all"
---

## Core Capability
在代码开发/修改过程中执行四象审计，自动检测环境配置、代码质量、验证机制、沟通文档四个维度的问题。基于 AST 静态分析，支持 Python 文件的深度审计。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **代码提交前**：提交代码前执行审计，确保质量
- **代码审查**：审查他人代码时发现问题
- **开发过程中**：编写代码时实时检查
- **重构后**：重构完成后验证代码质量
- **安全审计**：检查潜在安全风险

**判断标准**：在涉及代码编写、修改、审查的任何环节，都应执行四象审计。

## Parameters

| Name       | Type   | Description                  | Required | Default |
| ---------- | ------ | ---------------------------- | -------- | ------- |
| file_path  | string | 要审计的文件路径             | Yes      | -       |
| audit_type | string | 审计类型                     | No       | all     |

## Four Symbols（四象）

| 象   | 名称   | 审计内容                           | 检查项示例                     |
| ---- | ------ | ---------------------------------- | ------------------------------ |
| 青龙 | 环境   | 路径、平台兼容性、环境变量         | 硬编码路径、平台判断、环境配置 |
| 白虎 | 代码   | 语法、安全、规范、缩进             | eval/exec、shell注入、缩进混用 |
| 朱雀 | 验证   | 测试、运行验证、文件大小           | 缺少测试、无main入口、文件过大 |
| 玄武 | 沟通   | 文档、注释、日志、TODO             | 缺少docstring、print替代日志   |

## Audit Levels

| 级别 | 说明         | 处理方式           |
| ---- | ------------ | ------------------ |
| 致命 | 无法运行     | 必须修复           |
| 高危 | 安全风险     | 必须修复           |
| 中危 | 潜在问题     | 建议修复           |
| 警告 | 规范问题     | 建议关注           |
| 提示 | 优化建议     | 可选处理           |
| 信息 | 仅供参考     | 了解即可           |

## Example Usage

### 场景1：完整审计
```json
{
  "skill": "four_symbols_audit",
  "args": {
    "file_path": "./agent.py",
    "audit_type": "all"
  }
}
```

### 场景2：仅代码安全审计
```json
{
  "skill": "four_symbols_audit",
  "args": {
    "file_path": "./web_app.py",
    "audit_type": "baihu"
  }
}
```

### 场景3：审计整个目录
```json
{
  "skill": "four_symbols_audit",
  "args": {
    "file_path": "./skills/system/shell_exec/shell_exec.py"
  }
}
```

## Execution Signature
```python
def execute(file_path: str, audit_type: str = "all", **kwargs) -> str:
    ...
```

## Output Format

### 审计通过
```
✅ 四象审计通过
文件: ./agent.py
未发现明显问题。
```

### 发现问题
```
📋 四象审计报告
文件: ./web_app.py
问题总数: 5

【摘要】
  青龙: 1 项
  白虎: 2 项
  朱雀: 0 项
  玄武: 2 项

【级别分布】
  🔴 高危: 1
  🟡 警告: 1
  🔵 提示: 3

【详细问题】

1. [白虎] 高危 第45行
   发现 eval() 调用，存在代码注入风险
   💡 建议: 使用 ast.literal_eval() 替代 eval()

...

⚠️ 审计警告：发现 1 个高危问题，建议修复后再提交。
```

## Best Practices

1. **提交前必审**：每次提交代码前执行 all 审计
2. **增量审计**：修改后仅审计修改的文件
3. **高危必修**：高危和致命级别问题必须修复
4. **持续改进**：定期审计整个项目，逐步降低提示数量

## Notes
- 基于 AST 静态分析，无需执行代码
- 当前主要支持 Python 文件审计
- 非 Python 文件仅执行基础检查
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
