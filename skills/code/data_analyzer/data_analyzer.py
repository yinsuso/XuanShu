"""
数据分析技能。
提供数据清洗、统计分析、可视化等功能。
Author: 破执
Date: 2026-05-15
"""

import os
import json
import csv
import io
from typing import Optional, List, Dict, Any
from collections import Counter

from logger import get_logger

logger = get_logger('data_analyzer')

# 技能元数据
SKILL_NAME = "data_analyzer"
SKILL_DESCRIPTION = "数据分析工具，支持数据清洗、统计分析、数据可视化图表生成。"
SKILL_TRIGGER = "当需要对数据进行处理、分析、统计或生成图表时使用。"
SKILL_CATEGORY = "code"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "action",
        "type": "string",
        "description": "操作类型: analyze(分析), clean(清洗), stats(统计), visualize(可视化), convert(格式转换)"
    },
    {
        "name": "input_path",
        "type": "string",
        "description": "输入文件路径（CSV/JSON/TXT）",
        "default": ""
    },
    {
        "name": "data",
        "type": "string",
        "description": "直接传入数据（JSON格式字符串，可选）",
        "default": ""
    },
    {
        "name": "output_path",
        "type": "string",
        "description": "输出文件路径（可选）",
        "default": ""
    },
    {
        "name": "options",
        "type": "string",
        "description": "额外选项（JSON格式，如列名、过滤条件等）",
        "default": ""
    }
]


def _load_data(input_path: str = "", data_str: str = "") -> tuple:
    """
    加载数据。
    返回 (success, data_list, columns)
    """
    if input_path:
        abs_path = os.path.abspath(input_path.strip())
        if not os.path.exists(abs_path):
            return False, f"文件不存在: {abs_path}", []

        ext = os.path.splitext(abs_path)[1].lower()

        try:
            if ext == ".csv":
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    columns = reader.fieldnames or []
                    return True, rows, columns

            elif ext == ".json":
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        if content and isinstance(content[0], dict):
                            return True, content, list(content[0].keys())
                        else:
                            return True, [{"value": v} for v in content], ["value"]
                    elif isinstance(content, dict):
                        rows = [{"key": k, "value": str(v)} for k, v in content.items()]
                        return True, rows, ["key", "value"]

            elif ext in (".txt", ".log"):
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    rows = [{"line_num": i + 1, "content": line.rstrip("\n\r")}
                            for i, line in enumerate(lines)]
                    return True, rows, ["line_num", "content"]

            else:
                return False, f"不支持的文件格式: {ext}", []

        except Exception as e:
            return False, f"读取文件失败: {str(e)}", []

    elif data_str:
        try:
            data = json.loads(data_str)
            if isinstance(data, list):
                if data and isinstance(data[0], dict):
                    return True, data, list(data[0].keys())
                else:
                    return True, [{"value": v} for v in data], ["value"]
            elif isinstance(data, dict):
                rows = [{"key": k, "value": str(v)} for k, v in data.items()]
                return True, rows, ["key", "value"]
            else:
                return True, [{"value": data}], ["value"]
        except json.JSONDecodeError:
            lines = data_str.strip().split("\n")
            rows = [{"line_num": i + 1, "content": line}
                    for i, line in enumerate(lines)]
            return True, rows, ["line_num", "content"]

    else:
        return False, "请提供 input_path 或 data 参数", []


def _parse_options(options_str: str) -> dict:
    """解析选项字符串。"""
    if not options_str:
        return {}
    try:
        return json.loads(options_str)
    except:
        return {}


def _analyze_data(rows: List[Dict], columns: List[str], options: dict) -> str:
    """数据分析概览。"""
    if not rows:
        return "❌ 数据为空"

    output = f"✅ 数据分析结果\n"
    output += f"总行数: {len(rows)}\n"
    output += f"总列数: {len(columns)}\n"
    output += f"列名: {', '.join(columns)}\n\n"

    # 每列的统计
    for col in columns:
        values = [str(r.get(col, "")).strip() for r in rows if r.get(col) is not None]
        non_empty = [v for v in values if v]
        empty_count = len(values) - len(non_empty)

        output += f"【列: {col}】\n"
        output += f"  非空值: {len(non_empty)} / {len(values)}"
        if empty_count > 0:
            output += f" (空值: {empty_count})"
        output += "\n"

        # 尝试数值统计
        numeric_values = []
        for v in non_empty:
            try:
                numeric_values.append(float(v))
            except:
                pass

        if numeric_values:
            output += f"  数值统计:\n"
            output += f"    最小值: {min(numeric_values)}\n"
            output += f"    最大值: {max(numeric_values)}\n"
            output += f"    平均值: {sum(numeric_values) / len(numeric_values):.2f}\n"
            output += f"    中位数: {_median(numeric_values):.2f}\n"
        else:
            # 文本统计：唯一值数量
            unique = set(non_empty)
            output += f"  唯一值: {len(unique)}\n"
            if len(unique) <= 10:
                counter = Counter(non_empty)
                top = counter.most_common(5)
                output += f"  高频值:\n"
                for val, count in top:
                    output += f"    {val}: {count} 次\n"

        output += "\n"

    return output


def _median(values: List[float]) -> float:
    """计算中位数。"""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        return sorted_vals[n // 2]
    else:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2


def _clean_data(rows: List[Dict], columns: List[str], options: dict) -> tuple:
    """数据清洗。"""
    cleaned = []
    removed = 0

    for row in rows:
        new_row = {}
        for col in columns:
            val = row.get(col, "")
            if val is None:
                val = ""
            # 去除首尾空格
            val = str(val).strip()
            new_row[col] = val

        # 检查是否为空行
        if any(new_row.values()):
            cleaned.append(new_row)
        else:
            removed += 1

    return cleaned, removed


def _stats_data(rows: List[Dict], columns: List[str], options: dict) -> str:
    """统计分析。"""
    if not rows:
        return "❌ 数据为空"

    target_col = options.get("column", "")
    if target_col and target_col not in columns:
        return f"❌ 列 '{target_col}' 不存在"

    output = "✅ 统计分析结果\n\n"

    cols_to_analyze = [target_col] if target_col else columns

    for col in cols_to_analyze:
        if col not in columns:
            continue

        values = []
        for r in rows:
            v = r.get(col, "")
            if v is not None and str(v).strip():
                try:
                    values.append(float(v))
                except:
                    pass

        output += f"【列: {col}】\n"

        if not values:
            output += "  无有效数值数据\n\n"
            continue

        n = len(values)
        mean = sum(values) / n
        sorted_vals = sorted(values)
        median = _median(values)

        # 方差和标准差
        variance = sum((x - mean) ** 2 for x in values) / n
        std_dev = variance ** 0.5

        output += f"  样本数: {n}\n"
        output += f"  最小值: {min(values):.4f}\n"
        output += f"  最大值: {max(values):.4f}\n"
        output += f"  平均值: {mean:.4f}\n"
        output += f"  中位数: {median:.4f}\n"
        output += f"  标准差: {std_dev:.4f}\n"
        output += f"  方差: {variance:.4f}\n"

        # 四分位数
        q1 = sorted_vals[n // 4] if n >= 4 else sorted_vals[0]
        q3 = sorted_vals[3 * n // 4] if n >= 4 else sorted_vals[-1]
        output += f"  Q1: {q1:.4f}\n"
        output += f"  Q3: {q3:.4f}\n"
        output += f"  IQR: {q3 - q1:.4f}\n\n"

    return output


def _visualize_data(rows: List[Dict], columns: List[str], options: dict, output_path: str) -> str:
    """数据可视化。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "❌ 未安装 matplotlib。请运行: pip install matplotlib"

    chart_type = options.get("chart_type", "bar")
    x_col = options.get("x_column", columns[0] if columns else "")
    y_col = options.get("y_column", "")

    if not x_col or x_col not in columns:
        return f"❌ 请指定有效的 x_column"

    # 准备数据
    labels = []
    values = []

    for r in rows[:50]:  # 限制最多50个数据点
        label = str(r.get(x_col, ""))[:20]
        if y_col and y_col in columns:
            try:
                val = float(r.get(y_col, 0))
            except:
                val = 0
        else:
            val = 1

        if label:
            labels.append(label)
            values.append(val)

    if not labels:
        return "❌ 无有效数据用于可视化"

    # 创建图表
    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        ax.bar(range(len(labels)), values)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
    elif chart_type == "line":
        ax.plot(range(len(labels)), values, marker="o")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
    elif chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    elif chart_type == "hist":
        ax.hist(values, bins=min(20, len(values)))
    else:
        ax.bar(range(len(labels)), values)

    ax.set_title(options.get("title", "Data Visualization"))
    if y_col:
        ax.set_ylabel(y_col)
    ax.set_xlabel(x_col)

    plt.tight_layout()

    # 保存
    if not output_path:
        output_path = "chart.png"
    abs_output = os.path.abspath(output_path)
    plt.savefig(abs_output, dpi=150, bbox_inches="tight")
    plt.close()

    return f"✅ 图表已保存: {abs_output}\n类型: {chart_type}\n数据点: {len(labels)}"


def _convert_format(rows: List[Dict], columns: List[str], output_path: str) -> str:
    """格式转换。"""
    if not output_path:
        return "❌ 请提供 output_path 参数"

    abs_output = os.path.abspath(output_path)
    ext = os.path.splitext(abs_output)[1].lower()

    try:
        if ext == ".csv":
            with open(abs_output, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)

        elif ext == ".json":
            with open(abs_output, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)

        elif ext == ".txt":
            with open(abs_output, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(", ".join(f"{k}={v}" for k, v in row.items()) + "\n")

        else:
            return f"❌ 不支持的输出格式: {ext}"

        return f"✅ 转换成功: {abs_output}\n行数: {len(rows)}"

    except Exception as e:
        return f"❌ 转换失败: {str(e)}"


def execute(action: str, input_path: str = "", data: str = "", output_path: str = "",
            options: str = "", **kwargs) -> str:
    """
    执行数据分析操作。

    Args:
        action: 操作类型
        input_path: 输入文件路径
        data: 直接传入的数据
        output_path: 输出文件路径
        options: 额外选项
        **kwargs: 额外参数（忽略）

    Returns:
        操作结果
    """
    action = action.lower().strip()
    opts = _parse_options(options)

    logger.info(f"数据分析: action={action}")

    # 加载数据（clean 和 convert 也需要数据）
    if action in ("analyze", "clean", "stats", "visualize", "convert"):
        success, result, columns = _load_data(input_path, data)
        if not success:
            return f"❌ {result}"
        rows = result
    else:
        rows = []
        columns = []

    if action == "analyze":
        return _analyze_data(rows, columns, opts)

    elif action == "clean":
        cleaned, removed = _clean_data(rows, columns, opts)
        if output_path:
            return _convert_format(cleaned, columns, output_path) + f"\n清洗: 移除 {removed} 行空数据"
        return f"✅ 数据清洗完成\n原始行数: {len(rows)}\n清洗后: {len(cleaned)}\n移除空行: {removed}"

    elif action == "stats":
        return _stats_data(rows, columns, opts)

    elif action == "visualize":
        return _visualize_data(rows, columns, opts, output_path)

    elif action == "convert":
        return _convert_format(rows, columns, output_path)

    else:
        return (
            f"❌ 不支持的操作类型: {action}\n"
            f"支持的操作: analyze(分析), clean(清洗), stats(统计), "
            f"visualize(可视化), convert(格式转换)"
        )
