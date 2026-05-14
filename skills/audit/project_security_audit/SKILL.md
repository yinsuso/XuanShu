---
name: project_security_audit
description: 系统化审计项目的前后端一致性、安全漏洞与代码质量。采用倒推审查机制和网络安全攻防推敲，适用于大型项目全面审计。
category: system
requires_confirmation: False
version: "1.0"
author: 破执
tags: []
parameters:
  -   name: "project_root"
      type: "string"
      description: "项目根目录绝对路径"
      required: True
  -   name: "output_format"
      type: "string"
      description: "输出格式：markdown 或 json"
      required: False
      default: "markdown"
      enum: ['markdown', 'json']
  -   name: "audit_scope"
      type: "array"
      description: "审计范围：frontend, backend, security, dependencies, all"
      required: False
      default: ['all']
---

## Core Capability
系统化审计项目的前后端一致性、安全漏洞与代码质量。采用倒推审查机制和网络安全攻防推敲，适用于大型项目全面审计。

## Trigger Scenario
当需要对大型项目进行全面安全审计、前后端一致性验证或代码安全审查时使用。

## Parameters
| Name | Type | Description | Required | Default |
| ---- | ---- | ----------- | -------- | ------- |
| project_root | string | 项目根目录绝对路径 | Yes |  |
| output_format | string | 输出格式：markdown 或 json | No | markdown |
| audit_scope | array | 审计范围：frontend, backend, security, dependencies, all | No | ['all'] |

## Example Usage
```json
{
  "skill": "project_security_audit",
  "args": {
    "param1": "value"
  }
}
```

## Execution Signature
```python
def project_security_audit.execute(project_root: string, output_format: string = "markdown", audit_scope: array = ['all'], **kwargs) -> str:
    ...
```

## Notes
- This skill now accepts extra parameters via `**kwargs`; unknown arguments are safely ignored.