"""
OpenClaw 控制器技能。
通过 HTTP API 控制 OpenClaw 执行任务。
Author: 破执
Date: 2026-05-15
"""

import os
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

from logger import get_logger

logger = get_logger('openclaw_controller')

# 技能元数据
SKILL_NAME = "openclaw_controller"
SKILL_DESCRIPTION = "控制 OpenClaw 执行任务，通过 HTTP API 发送任务并获取结果。"
SKILL_TRIGGER = "当需要调用 OpenClaw 执行独立任务、分布式计算或跨平台协作时使用。"
SKILL_CATEGORY = "system"
SKILL_REQUIRES_CONFIRMATION = True
SKILL_PARAMETERS = [
    {
        "name": "action",
        "type": "string",
        "description": "操作类型: send_task(发送任务), get_status(获取状态), get_result(获取结果), list_tasks(列出任务)"
    },
    {
        "name": "host",
        "type": "string",
        "description": "OpenClaw 地址，默认 http://localhost:8080",
        "default": "http://localhost:8080"
    },
    {
        "name": "task_description",
        "type": "string",
        "description": "任务描述（action=send_task 时必填）",
        "default": ""
    },
    {
        "name": "task_id",
        "type": "string",
        "description": "任务ID（action=get_status/get_result 时必填）",
        "default": ""
    },
    {
        "name": "timeout",
        "type": "integer",
        "description": "请求超时时间（秒），默认 30",
        "default": 30
    }
]


def _make_request(url: str, method: str = "GET", data: Optional[Dict] = None,
                  timeout: int = 30, headers: Optional[Dict] = None) -> tuple:
    """
    发送 HTTP 请求。

    Returns:
        (success: bool, result: dict or str)
    """
    default_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if headers:
        default_headers.update(headers)

    try:
        req_data = None
        if data:
            req_data = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_data,
            headers=default_headers,
            method=method
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_body = response.read().decode("utf-8", errors="replace")
            try:
                return True, json.loads(resp_body)
            except json.JSONDecodeError:
                return True, {"raw_response": resp_body}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return False, f"HTTP {e.code}: {e.reason}\n{error_body}"
    except urllib.error.URLError as e:
        return False, f"连接失败: {e.reason}"
    except Exception as e:
        return False, f"请求异常: {str(e)}"


def _send_task(host: str, task_description: str, timeout: int) -> str:
    """发送任务到 OpenClaw。"""
    url = f"{host.rstrip('/')}/api/tasks"

    payload = {
        "description": task_description,
        "source": "xuanshu_agent",
        "priority": "normal"
    }

    success, result = _make_request(url, method="POST", data=payload, timeout=timeout)

    if not success:
        return f"❌ 发送任务失败: {result}"

    task_id = result.get("task_id", "unknown")
    status = result.get("status", "unknown")
    return f"✅ 任务已发送\n任务ID: {task_id}\n状态: {status}\n描述: {task_description[:100]}..."


def _get_status(host: str, task_id: str, timeout: int) -> str:
    """获取任务状态。"""
    url = f"{host.rstrip('/')}/api/tasks/{task_id}/status"

    success, result = _make_request(url, method="GET", timeout=timeout)

    if not success:
        return f"❌ 获取状态失败: {result}"

    status = result.get("status", "unknown")
    progress = result.get("progress", 0)
    message = result.get("message", "")

    output = f"✅ 任务状态\n任务ID: {task_id}\n状态: {status}\n进度: {progress}%"
    if message:
        output += f"\n消息: {message}"

    return output


def _get_result(host: str, task_id: str, timeout: int) -> str:
    """获取任务结果。"""
    url = f"{host.rstrip('/')}/api/tasks/{task_id}/result"

    success, result = _make_request(url, method="GET", timeout=timeout)

    if not success:
        return f"❌ 获取结果失败: {result}"

    status = result.get("status", "unknown")
    output_data = result.get("output", "")
    error = result.get("error", "")

    result_text = f"✅ 任务结果\n任务ID: {task_id}\n状态: {status}"

    if output_data:
        if isinstance(output_data, str):
            result_text += f"\n输出:\n{output_data}"
        else:
            result_text += f"\n输出:\n{json.dumps(output_data, ensure_ascii=False, indent=2)}"

    if error:
        result_text += f"\n错误:\n{error}"

    return result_text


def _list_tasks(host: str, timeout: int) -> str:
    """列出所有任务。"""
    url = f"{host.rstrip('/')}/api/tasks"

    success, result = _make_request(url, method="GET", timeout=timeout)

    if not success:
        return f"❌ 获取任务列表失败: {result}"

    tasks = result.get("tasks", [])
    if not tasks:
        return "✅ 当前无任务"

    output = f"✅ 任务列表（共 {len(tasks)} 个）:\n"
    for task in tasks:
        tid = task.get("task_id", "unknown")[:8]
        status = task.get("status", "unknown")
        desc = task.get("description", "")[:40]
        output += f"  [{tid}...] {status} | {desc}\n"

    return output


def execute(action: str, host: str = "http://localhost:8080", task_description: str = "",
            task_id: str = "", timeout: int = 30, **kwargs) -> str:
    """
    执行 OpenClaw 控制操作。

    Args:
        action: 操作类型
        host: OpenClaw 地址
        task_description: 任务描述
        task_id: 任务ID
        timeout: 超时时间
        **kwargs: 额外参数（忽略）

    Returns:
        操作结果
    """
    action = action.lower().strip()
    logger.info(f"OpenClaw 控制: action={action}, host={host}")

    if action == "send_task":
        if not task_description:
            return "❌ action=send_task 时需要提供 task_description 参数"
        return _send_task(host, task_description, timeout)

    elif action == "get_status":
        if not task_id:
            return "❌ action=get_status 时需要提供 task_id 参数"
        return _get_status(host, task_id, timeout)

    elif action == "get_result":
        if not task_id:
            return "❌ action=get_result 时需要提供 task_id 参数"
        return _get_result(host, task_id, timeout)

    elif action == "list_tasks":
        return _list_tasks(host, timeout)

    else:
        return (
            f"❌ 不支持的操作类型: {action}\n"
            f"支持的操作: send_task(发送任务), get_status(获取状态), "
            f"get_result(获取结果), list_tasks(列出任务)"
        )
