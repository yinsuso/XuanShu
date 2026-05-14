"""
数据库查询技能。
支持 MySQL、PostgreSQL、SQLite3 数据库的查询操作。
Author: Local Agent
Date: 2026-05-14
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from logger import logger

# 技能元数据
SKILL_NAME = "database_query"
SKILL_DESCRIPTION = "查询数据库信息，支持 MySQL、PostgreSQL、SQLite3 等多种数据库。"
SKILL_TRIGGER = "当需要读取数据库中的数据、查询表结构或执行 SQL 查询时使用。"
SKILL_CATEGORY = "io"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "db_type",
        "type": "string",
        "description": "数据库类型，支持 mysql、postgresql、sqlite3"
    },
    {
        "name": "connection_string",
        "type": "string",
        "description": "数据库连接字符串（sqlite3为文件路径，mysql/postgresql为 host:port:database:user:password 格式）"
    },
    {
        "name": "query",
        "type": "string",
        "description": "要执行的 SQL 查询语句（仅支持 SELECT）"
    }
]


def _parse_connection_string_mysql(connection_string: str) -> Dict[str, str]:
    """解析 MySQL/PostgreSQL 连接字符串"""
    parts = connection_string.split(":")
    if len(parts) < 5:
        raise ValueError("连接字符串格式错误，应为 host:port:database:user:password")
    
    return {
        "host": parts[0],
        "port": int(parts[1]),
        "database": parts[2],
        "user": parts[3],
        "password": parts[4] if len(parts) > 4 else ""
    }


def _query_sqlite3(connection_string: str, query: str) -> List[Dict[str, Any]]:
    """执行 SQLite3 查询"""
    try:
        conn = sqlite3.connect(connection_string)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)
        
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description] if cursor.description else []
        
        result = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col] = row[i]
            result.append(row_dict)
        
        cursor.close()
        conn.close()
        return result
    except sqlite3.Error as e:
        logger.error(f"SQLite3 查询错误: {e}")
        raise Exception(f"SQLite3 查询错误: {str(e)}")


def _query_mysql(connection_string: str, query: str) -> List[Dict[str, Any]]:
    """执行 MySQL 查询"""
    try:
        import pymysql
        config = _parse_connection_string_mysql(connection_string)
        
        conn = pymysql.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with conn.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchall()
        
        conn.close()
        return result
    except ImportError:
        raise Exception("未安装 pymysql，请执行: pip install pymysql")
    except Exception as e:
        logger.error(f"MySQL 查询错误: {e}")
        raise Exception(f"MySQL 查询错误: {str(e)}")


def _query_postgresql(connection_string: str, query: str) -> List[Dict[str, Any]]:
    """执行 PostgreSQL 查询"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        config = _parse_connection_string_mysql(connection_string)
        
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"]
        )
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query)
        rows = cursor.fetchall()
        
        result = [dict(row) for row in rows]
        
        cursor.close()
        conn.close()
        return result
    except ImportError:
        raise Exception("未安装 psycopg2，请执行: pip install psycopg2-binary")
    except Exception as e:
        logger.error(f"PostgreSQL 查询错误: {e}")
        raise Exception(f"PostgreSQL 查询错误: {str(e)}")


def execute(db_type: str, connection_string: str, query: str, **kwargs) -> str:
    """
    执行数据库查询。
    
    Args:
        db_type: 数据库类型（mysql、postgresql、sqlite3）
        connection_string: 连接字符串
        query: SQL 查询语句
        **kwargs: 额外参数（忽略）
    
    Returns:
        查询结果（JSON 格式）或错误信息
    """
    try:
        # 安全检查：仅允许 SELECT 查询
        query_stripped = query.strip().upper()
        if not query_stripped.startswith("SELECT") and not query_stripped.startswith("PRAGMA") and not query_stripped.startswith("SHOW"):
            return json.dumps({
                "error": "仅支持 SELECT、PRAGMA、SHOW 查询，不支持数据修改操作"
            }, ensure_ascii=False)
        
        db_type = db_type.lower().strip()
        
        if db_type == "sqlite3":
            result = _query_sqlite3(connection_string, query)
        elif db_type == "mysql":
            result = _query_mysql(connection_string, query)
        elif db_type == "postgresql":
            result = _query_postgresql(connection_string, query)
        else:
            return json.dumps({
                "error": f"不支持的数据库类型: {db_type}，支持 mysql、postgresql、sqlite3"
            }, ensure_ascii=False)
        
        return json.dumps({
            "success": True,
            "count": len(result),
            "data": result
        }, ensure_ascii=False, default=str)
        
    except Exception as e:
        logger.error(f"数据库查询技能执行失败: {e}")
        return json.dumps({
            "error": str(e)
        }, ensure_ascii=False)
