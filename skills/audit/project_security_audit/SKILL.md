---
name: project_security_audit
description: 系统化审计项目的前后端一致性、安全漏洞与代码质量。采用倒推审查机制和网络安全攻防推敲，适用于大型项目全面审计。当 Agent 需要对项目进行安全评估、代码质量检查或一致性验证时调用此技能。
category: system
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["security", "audit", "code-quality", "vulnerability", "review"]
parameters:
  - name: "project_root"
    type: "string"
    description: "项目根目录绝对路径。审计将从此目录开始递归扫描所有相关文件。"
    required: true
  - name: "output_format"
    type: "string"
    description: "输出格式：markdown（易读）或 json（结构化数据）。默认 markdown。"
    required: false
    default: "markdown"
    enum: ["markdown", "json"]
  - name: "audit_scope"
    type: "array"
    description: "审计范围：frontend（前端）、backend（后端）、security（安全）、dependencies（依赖）、all（全部）。默认 ['all']。"
    required: false
    default: ["all"]
---

## Core Capability
对指定项目进行全面的安全审计和代码质量检查，包括：

- **前后端一致性检查**：验证 API 接口定义与前端调用是否匹配
- **安全漏洞扫描**：检测常见的安全漏洞，如 SQL 注入、XSS、CSRF、硬编码密钥等
- **代码质量评估**：检查代码规范、重复代码、复杂度过高的函数
- **依赖安全分析**：检查第三方依赖是否存在已知漏洞
- **配置安全审查**：检查配置文件中的敏感信息泄露风险

采用倒推审查机制，从攻击者视角审视代码，结合网络安全攻防推敲，发现潜在的安全隐患。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **项目安全评估**：用户要求"帮我检查一下这个项目的安全性"、"有没有漏洞"
- **代码审查**：项目上线前进行全面的代码质量和安全检查
- **合规检查**：需要满足安全合规要求（如等保、ISO27001）
- **漏洞排查**：怀疑项目存在安全问题，需要系统排查
- **技术债评估**：评估项目的技术债务和安全风险
- **第三方审计**：对外包或引入的第三方代码进行安全审计
- **定期巡检**：定期对运行中的项目进行安全巡检

**判断标准**：当需要对项目进行全面的安全、质量、一致性审计时，使用此技能。

## Parameters

| Name          | Type   | Description                                           | Required | Default |
| ------------- | ------ | ----------------------------------------------------- | -------- | ------- |
| project_root  | string | 项目根目录绝对路径                                    | Yes      | -       |
| output_format | string | 输出格式：markdown 或 json                            | No       | markdown |
| audit_scope   | array  | 审计范围：frontend, backend, security, dependencies, all | No       | ["all"] |

## Audit Scope Details（审计范围详解）

| Scope        | 说明                                                         |
| ------------ | ------------------------------------------------------------ |
| `frontend`   | 审计前端代码：HTML/JS/CSS 中的 XSS 漏洞、敏感信息泄露、不安全的 DOM 操作 |
| `backend`    | 审计后端代码：API 安全、输入验证、认证授权、会话管理           |
| `security`   | 专项安全审计：SQL 注入、命令注入、路径遍历、反序列化漏洞等       |
| `dependencies` | 审计依赖项：检查 requirements.txt、package.json 中的已知漏洞 |
| `all`        | 执行全部审计范围（默认）                                       |

## Example Usage

### 场景1：全面审计项目
```json
{
  "skill": "project_security_audit",
  "args": {
    "project_root": "/path/to/project",
    "output_format": "markdown",
    "audit_scope": ["all"]
  }
}
```

### 场景2：仅审计安全漏洞
```json
{
  "skill": "project_security_audit",
  "args": {
    "project_root": "/path/to/project",
    "output_format": "json",
    "audit_scope": ["security"]
  }
}
```

### 场景3：审计前后端一致性
```json
{
  "skill": "project_security_audit",
  "args": {
    "project_root": "/path/to/project",
    "output_format": "markdown",
    "audit_scope": ["frontend", "backend"]
  }
}
```

### 场景4：审计依赖安全
```json
{
  "skill": "project_security_audit",
  "args": {
    "project_root": "/path/to/project",
    "output_format": "json",
    "audit_scope": ["dependencies"]
  }
}
```

## Execution Signature
```python
def project_security_audit.execute(project_root: str, output_format: str = "markdown", audit_scope: list = ["all"], **kwargs) -> str:
    ...
```

## Output Format

### Markdown 格式
返回结构化的审计报告，包含以下章节：

```markdown
# 项目安全审计报告

## 审计概览
- 审计时间: 2024-01-15 10:30:00
- 项目路径: /path/to/project
- 审计范围: all
- 风险等级: 🔴 高风险 / 🟡 中风险 / 🟢 低风险

## 发现的问题

### 🔴 高风险
1. **SQL 注入漏洞** (backend)
   - 位置: `app.py:45`
   - 描述: 用户输入直接拼接到 SQL 语句中
   - 建议: 使用参数化查询

### 🟡 中风险
2. **硬编码密钥** (security)
   - 位置: `config.py:12`
   - 描述: API 密钥硬编码在源代码中
   - 建议: 使用环境变量或密钥管理服务

### 🟢 低风险
3. **缺少输入验证** (frontend)
   - 位置: `index.html:88`
   - 描述: 表单提交缺少前端验证
   - 建议: 增加必填项和格式验证

## 统计摘要
- 总问题数: 15
- 高风险: 3
- 中风险: 7
- 低风险: 5
- 已修复: 0
```

### JSON 格式
返回结构化的 JSON 数据，便于程序化处理：

```json
{
  "audit_time": "2024-01-15T10:30:00",
  "project_root": "/path/to/project",
  "summary": {
    "total": 15,
    "high": 3,
    "medium": 7,
    "low": 5
  },
  "findings": [
    {
      "severity": "high",
      "category": "backend",
      "title": "SQL 注入漏洞",
      "location": "app.py:45",
      "description": "用户输入直接拼接到 SQL 语句中",
      "recommendation": "使用参数化查询"
    }
  ]
}
```

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **file_list → project_security_audit**：先浏览项目结构 → 执行全面审计
2. **project_security_audit → file_read**：发现漏洞后，读取具体文件确认问题
3. **project_security_audit → file_write**：根据审计报告生成修复代码
4. **project_security_audit → python_exec**：验证修复代码的正确性

## Best Practices（最佳实践）

1. **审计前准备**：确保项目代码完整，没有未提交的修改
2. **分范围审计**：大型项目建议分范围审计（如先 `security`，再 `backend`），避免输出过长
3. **结果验证**：审计发现的问题建议人工复核，避免误报
4. **修复跟踪**：将审计结果保存到文件，跟踪修复进度
5. **定期审计**：建议每月或每季度执行一次安全审计

## Safety Notes（安全提示）

- **代码保密**：审计过程中不会将代码上传到外部服务器，所有分析在本地完成
- **敏感信息**：审计报告可能包含文件路径和代码片段，分享时注意脱敏
- **误报处理**：自动化审计可能存在误报，关键问题建议人工确认
- **修复验证**：修复漏洞后，建议重新运行审计验证修复效果

## Notes
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 审计深度取决于项目规模和复杂度，大型项目可能需要较长时间
- 部分高级漏洞可能需要人工渗透测试才能发现，自动化审计不能替代专业安全测试
- 建议结合 `python_exec` 对发现的漏洞进行验证性利用测试（仅在授权环境下）
