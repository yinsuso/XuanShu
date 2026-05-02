"""
文件操作公共工具模块。
提供安全的文件读写、目录列表等基础功能，所有操作均受路径安全限制。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

import os
from typing import Optional, List
from config import ALLOWED_DIR

def validate_path(path: str) -> str:
    """
    验证并转换路径为绝对路径，确保不越界。
    
    Args:
        path: 相对路径或绝对路径
        
    Returns:
        安全的绝对路径
        
    Raises:
        ValueError: 如果路径越界
    """
    abs_path = os.path.abspath(os.path.join(ALLOWED_DIR, path))
    if not abs_path.startswith(ALLOWED_DIR):
        raise ValueError(f"路径越界：{path}")
    return abs_path

def read_file_safe(path: str, lines: int = 0, max_length: int = 8000) -> str:
    """
    安全读取文件内容。
    
    Args:
        path: 文件路径
        lines: 读取行数（0 表示全部）
        max_length: 最大返回长度
        
    Returns:
        文件内容或错误信息
    """
    try:
        abs_path = validate_path(path)
        
        if not os.path.exists(abs_path):
            return f"❌ 文件不存在：{abs_path}"
        
        if not os.path.isfile(abs_path):
            return f"❌ 不是文件：{abs_path}"
        
        with open(abs_path, 'r', encoding='utf-8') as f:
            if lines > 0:
                content = ''.join(f.readlines()[:lines])
            else:
                content = f.read()
        
        # 限制长度
        if len(content) > max_length:
            content = content[:max_length] + "\n... (内容过长，已截断)"
        
        return f"✅ 读取成功 ({abs_path}):\n{content}"
    
    except ValueError as e:
        return f"❌ 安全拦截：{str(e)}"
    except Exception as e:
        return f"❌ 读取失败：{str(e)}"

def write_file_safe(path: str, content: str) -> str:
    """
    安全写入文件内容。
    
    Args:
        path: 文件路径
        content: 要写入的内容
        
    Returns:
        操作结果
    """
    try:
        abs_path = validate_path(path)
        
        # 创建父目录
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"✅ 写入成功 ({abs_path})"
    
    except ValueError as e:
        return f"❌ 安全拦截：{str(e)}"
    except Exception as e:
        return f"❌ 写入失败：{str(e)}"

def list_directory_safe(path: str = ".") -> str:
    """
    安全列出目录内容。
    
    Args:
        path: 目录路径
        
    Returns:
        目录列表或错误信息
    """
    try:
        abs_path = validate_path(path)
        
        if not os.path.isdir(abs_path):
            return f"❌ 不是目录：{abs_path}"
        
        entries = os.listdir(abs_path)
        result = []
        for entry in sorted(entries):
            full_path = os.path.join(abs_path, entry)
            if os.path.isdir(full_path):
                result.append(f"[DIR]  {entry}")
            else:
                result.append(f"[FILE] {entry}")
        
        return f"✅ 目录列表 ({abs_path}):\n" + "\n".join(result)
    
    except ValueError as e:
        return f"❌ 安全拦截：{str(e)}"
    except Exception as e:
        return f"❌ 列表失败：{str(e)}"