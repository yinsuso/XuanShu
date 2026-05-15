---
name: format_converter
description: 文档格式转换，支持 Word、PDF、TXT 等格式互转。当需要将文档从一种格式转换为另一种格式时调用此技能。
category: io
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["convert", "format", "docx", "pdf", "txt", "document"]
parameters:
  - name: "input_path"
    type: "string"
    description: "输入文件路径"
    required: true
  - name: "output_path"
    type: "string"
    description: "输出文件路径（可选，默认与输入文件同目录）"
    required: false
    default: ""
  - name: "output_format"
    type: "string"
    description: "目标格式: pdf, docx, txt, html, md"
    required: false
    default: ""
---

## Core Capability
支持 Word (docx)、PDF、TXT、HTML、Markdown 等常见文档格式之间的相互转换。优先使用专用库进行转换，复杂格式使用 pandoc 作为后备方案。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **文档格式转换**：Word 转 PDF、PDF 转 Word、TXT 转 PDF 等
- **内容提取**：从 PDF/Word 中提取纯文本内容
- **格式统一**：将多种格式统一为同一种格式
- **报告生成**：将文本内容转换为 PDF 报告

**判断标准**：当需要改变文档的文件格式时，使用此技能。

## Parameters

| Name          | Type   | Description                        | Required | Default |
| ------------- | ------ | ---------------------------------- | -------- | ------- |
| input_path    | string | 输入文件路径                       | Yes      | -       |
| output_path   | string | 输出文件路径（可选）               | No       | ""      |
| output_format | string | 目标格式（如未提供 output_path）   | No       | ""      |

## Supported Conversions

| 源格式 | 目标格式 | 转换方式           |
| ------ | -------- | ------------------ |
| TXT    | DOCX     | python-docx        |
| DOCX   | TXT      | python-docx        |
| PDF    | TXT      | pdfplumber/PyPDF2  |
| TXT    | PDF      | reportlab          |
| *      | *        | pandoc（后备方案） |

## Example Usage

### 场景1：Word 转 PDF
```json
{
  "skill": "format_converter",
  "args": {
    "input_path": "./report.docx",
    "output_format": "pdf"
  }
}
```

### 场景2：PDF 转 TXT（提取文本）
```json
{
  "skill": "format_converter",
  "args": {
    "input_path": "./document.pdf",
    "output_path": "./document.txt"
  }
}
```

### 场景3：TXT 转 Word
```json
{
  "skill": "format_converter",
  "args": {
    "input_path": "./notes.txt",
    "output_format": "docx"
  }
}
```

## Execution Signature
```python
def execute(input_path: str, output_path: str = "", output_format: str = "", **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
```
✅ 转换成功: report.docx → report.pdf
```

### 错误返回
- 文件不存在：`❌ 输入文件不存在: /path/to/file`
- 未安装依赖：`❌ 未安装 python-docx。请运行: pip install python-docx`
- 转换失败：`❌ 转换失败: [错误信息]`

## Dependencies

| 依赖库       | 用途           | 安装命令                      |
| ------------ | -------------- | ----------------------------- |
| python-docx  | Word 文档处理  | pip install python-docx       |
| pdfplumber   | PDF 文本提取   | pip install pdfplumber        |
| PyPDF2       | PDF 处理（后备）| pip install PyPDF2           |
| reportlab    | PDF 生成       | pip install reportlab         |
| pandoc       | 通用格式转换   | https://pandoc.org/installing |

## Notes
- 优先使用专用库转换，效果更好的同时保留更多格式信息
- pandoc 作为通用后备方案，支持更多格式组合
- 中文字体支持依赖系统安装的字体文件
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
