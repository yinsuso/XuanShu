"""
文本处理公共工具模块。
提供全角半角转换、文本清理等基础功能。
Author: 玄枢
Date: 2026-05-15
"""


def normalize_fullwidth_numbers(value):
    """
    将字符串中的全角数字转换为半角数字。
    同时处理全角的小数点和正负号。

    Args:
        value: 输入值（字符串、数字或其他类型）

    Returns:
        转换后的值。如果输入是字符串则返回转换后的字符串；
        如果输入是数字则原样返回；其他类型也原样返回。
    """
    if not isinstance(value, str):
        return value

    fullwidth = "０１２３４５６７８９．＋－"
    halfwidth = "0123456789.+-"
    trans = str.maketrans(fullwidth, halfwidth)
    return value.translate(trans)


def normalize_numeric_param(value, target_type=float):
    """
    将参数值转换为数字类型，自动处理全角数字。

    Args:
        value: 输入值（字符串、数字或其他类型）
        target_type: 目标类型（int 或 float）

    Returns:
        转换后的数字值

    Raises:
        ValueError: 如果转换失败
    """
    if value is None:
        raise ValueError("值为空")

    if isinstance(value, (int, float)):
        return target_type(value)

    if isinstance(value, str):
        normalized = normalize_fullwidth_numbers(value)
        normalized = normalized.strip()
        if not normalized:
            raise ValueError("值为空字符串")
        return target_type(normalized)

    raise ValueError(f"不支持的类型: {type(value)}")
