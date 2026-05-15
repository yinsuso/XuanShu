---
name: data_analyzer
description: 数据分析工具，支持数据清洗、统计分析、数据可视化图表生成。当需要对数据进行处理、分析、统计或生成图表时调用此技能。
category: code
requires_confirmation: False
version: "1.0"
author: 破执
tags: ["data", "analysis", "statistics", "visualization", "chart", "csv", "json"]
parameters:
  - name: "action"
    type: "string"
    description: "操作类型: analyze(分析), clean(清洗), stats(统计), visualize(可视化), convert(格式转换)"
    required: true
  - name: "input_path"
    type: "string"
    description: "输入文件路径（CSV/JSON/TXT）"
    required: false
    default: ""
  - name: "data"
    type: "string"
    description: "直接传入数据（JSON格式字符串，可选）"
    required: false
    default: ""
  - name: "output_path"
    type: "string"
    description: "输出文件路径（可选）"
    required: false
    default: ""
  - name: "options"
    type: "string"
    description: "额外选项（JSON格式，如列名、过滤条件等）"
    required: false
    default: ""
---

## Core Capability
提供完整的数据分析流水线：数据加载（CSV/JSON/TXT）、数据清洗（去空值、去重）、统计分析（描述性统计、四分位数）、可视化（柱状图/折线图/饼图/直方图）、格式转换。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **数据概览**：快速了解数据集的结构和内容分布
- **数据清洗**：去除空值、标准化格式
- **统计分析**：计算均值、中位数、标准差、四分位数等
- **可视化**：生成图表直观展示数据
- **格式转换**：CSV ↔ JSON ↔ TXT 互转

**判断标准**：当需要处理或分析结构化数据时，使用此技能。

## Parameters

| Name        | Type   | Description                  | Required | Default |
| ----------- | ------ | ---------------------------- | -------- | ------- |
| action      | string | 操作类型                     | Yes      | -       |
| input_path  | string | 输入文件路径                 | No       | ""      |
| data        | string | 直接传入的数据               | No       | ""      |
| output_path | string | 输出文件路径                 | No       | ""      |
| options     | string | 额外选项（JSON格式）         | No       | ""      |

## Supported Actions

| Action    | 说明         | 输出         |
| --------- | ------------ | ------------ |
| analyze   | 数据概览分析 | 文本报告     |
| clean     | 数据清洗     | 清洗后的数据 |
| stats     | 统计分析     | 统计报告     |
| visualize | 可视化图表   | PNG图片      |
| convert   | 格式转换     | 目标格式文件 |

## Supported Formats

| 格式 | 扩展名       | 说明           |
| ---- | ------------ | -------------- |
| CSV  | .csv         | 逗号分隔值     |
| JSON | .json        | JSON对象/数组  |
| TXT  | .txt, .log   | 纯文本行       |

## Options 说明

```json
{
  "column": "age",
  "chart_type": "bar",
  "x_column": "name",
  "y_column": "score",
  "title": "成绩分布"
}
```

| 选项        | 说明                    | 适用 action |
| ----------- | ----------------------- | ----------- |
| column      | 指定分析的列            | stats       |
| chart_type  | 图表类型: bar/line/pie/hist | visualize |
| x_column    | X轴数据列               | visualize   |
| y_column    | Y轴数据列               | visualize   |
| title       | 图表标题                | visualize   |

## Example Usage

### 场景1：数据概览分析
```json
{
  "skill": "data_analyzer",
  "args": {
    "action": "analyze",
    "input_path": "./data/users.csv"
  }
}
```

### 场景2：统计分析
```json
{
  "skill": "data_analyzer",
  "args": {
    "action": "stats",
    "input_path": "./data/sales.csv",
    "options": "{\"column\":\"amount\"}"
  }
}
```

### 场景3：生成柱状图
```json
{
  "skill": "data_analyzer",
  "args": {
    "action": "visualize",
    "input_path": "./data/scores.csv",
    "output_path": "./chart.png",
    "options": "{\"chart_type\":\"bar\",\"x_column\":\"name\",\"y_column\":\"score\",\"title\":\"成绩分布\"}"
  }
}
}
```

### 场景4：数据清洗并导出
```json
{
  "skill": "data_analyzer",
  "args": {
    "action": "clean",
    "input_path": "./data/raw.csv",
    "output_path": "./data/cleaned.csv"
  }
}
```

## Execution Signature
```python
def execute(action: str, input_path: str = "", data: str = "",
            output_path: str = "", options: str = "", **kwargs) -> str:
    ...
```

## Dependencies

| 依赖库      | 用途         | 安装命令                 |
| ----------- | ------------ | ------------------------ |
| matplotlib  | 图表生成     | pip install matplotlib   |

## Notes
- 支持从文件加载或直接传入 JSON 数据
- 可视化最多显示 50 个数据点
- 图表使用 Agg 后端，无需 GUI 环境
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
