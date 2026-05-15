"""
中间态文件管理工具
负责任务中间态文件的创建、读取、保存、清理。
支持磁盘配额检查与自动清理。
"""
import os
import json
import shutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from logger import logger


WORKFLOW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "workflow")
DEFAULT_MAX_QUOTA_BYTES = 1024 * 1024 * 1024  # 1GB 默认配额


def ensure_workflow_dir(task_id: str) -> str:
    """
    确保任务工作目录存在，并返回路径。
    """
    task_dir = os.path.join(WORKFLOW_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    logger.debug(f"✅ 工作目录已就绪：{task_dir}")
    return task_dir


def save_task_state(task_id: str, stage: str, data: Dict[str, Any]) -> str:
    """
    保存任务中间态到文件。
    :param task_id: 任务 ID
    :param stage: 阶段名 (e.g., 'plan', 'result', 'review')
    :param data: 数据内容
    :return: 文件路径
    """
    # 检查磁盘配额
    if not check_disk_quota():
        # 尝试自动清理
        auto_cleanup_old_tasks(days_old=7)
        if not check_disk_quota():
            raise Exception("磁盘配额不足，无法保存任务。")
    
    task_dir = ensure_workflow_dir(task_id)
    file_path = os.path.join(task_dir, f"{stage}.json")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "data": data
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 已保存 {stage} 到：{file_path}")
    return file_path


def load_task_state(task_id: str, stage: str) -> Optional[Dict[str, Any]]:
    """
    加载任务中间态从文件。
    :param task_id: 任务 ID
    :param stage: 阶段名
    :return: 数据内容，若不存在则返回 None
    """
    task_dir = os.path.join(WORKFLOW_DIR, task_id)
    file_path = os.path.join(task_dir, f"{stage}.json")
    
    if not os.path.exists(file_path):
        logger.warning(f"⚠️ 文件不存在：{file_path}")
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    return content.get("data")


def get_task_summary(task_id: str) -> Dict[str, Any]:
    """
    获取任务摘要（所有中间态文件的简要信息）。
    """
    task_dir = os.path.join(WORKFLOW_DIR, task_id)
    if not os.path.exists(task_dir):
        return {}
    
    summary = {}
    for file_name in os.listdir(task_dir):
        if file_name.endswith('.json'):
            stage = file_name.replace('.json', '')
            file_path = os.path.join(task_dir, file_name)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                summary[stage] = {
                    "size": os.path.getsize(file_path),
                    "updated": content.get("timestamp"),
                    "preview": str(content.get("data", {}))[:100]
                }
            except Exception as e:
                logger.error(f"❌ 读取摘要失败：{file_path}, 错误：{e}")
    
    return summary


def cleanup_task_dir(task_id: str, keep_logs: bool = False) -> bool:
    """
    清理任务工作目录。
    :param task_id: 任务 ID
    :param keep_logs: 是否保留日志文件（若为 True，则只删除中间态文件）
    :return: 是否成功
    """
    task_dir = os.path.join(WORKFLOW_DIR, task_id)
    if not os.path.exists(task_dir):
        return True
    
    try:
        if keep_logs:
            # 只删除中间态文件，保留日志
            for file_name in os.listdir(task_dir):
                if file_name.endswith('.json') and file_name != 'logs.json':
                    os.remove(os.path.join(task_dir, file_name))
        else:
            # 删除整个目录
            shutil.rmtree(task_dir)
        logger.info(f"🧹 已清理任务目录：{task_dir}")
        return True
    except Exception as e:
        logger.error(f"❌ 清理失败：{task_dir}, 错误：{e}")
        return False


def list_active_tasks() -> List[str]:
    """
    列出所有活跃任务 ID。
    """
    if not os.path.exists(WORKFLOW_DIR):
        return []
    
    return [d for d in os.listdir(WORKFLOW_DIR) if os.path.isdir(os.path.join(WORKFLOW_DIR, d))]


def get_workflow_dir_size() -> int:
    """
    获取 workflow 目录总大小（字节）。
    """
    total_size = 0
    if not os.path.exists(WORKFLOW_DIR):
        return 0
    
    for dirpath, dirnames, filenames in os.walk(WORKFLOW_DIR):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
            except OSError:
                continue
    
    return total_size


def check_disk_quota(max_quota_bytes: int = DEFAULT_MAX_QUOTA_BYTES) -> bool:
    """
    检查磁盘配额是否充足。
    :param max_quota_bytes: 最大配额（字节）
    :return: True 若充足，False 若超出配额
    """
    current_size = get_workflow_dir_size()
    return current_size < max_quota_bytes


def auto_cleanup_old_tasks(days_old: int = 7, max_quota_bytes: int = DEFAULT_MAX_QUOTA_BYTES) -> int:
    """
    自动清理旧任务目录（超过指定天数）。
    :param days_old: 保留天数
    :param max_quota_bytes: 最大配额（字节）
    :return: 清理的文件数
    """
    cleaned_count = 0
    cutoff_time = datetime.now() - timedelta(days=days_old)
    
    if not os.path.exists(WORKFLOW_DIR):
        return 0
    
    # 先清理旧任务
    for task_id in os.listdir(WORKFLOW_DIR):
        task_dir = os.path.join(WORKFLOW_DIR, task_id)
        if not os.path.isdir(task_dir):
            continue
        
        # 获取目录中最早的文件时间
        try:
            files = os.listdir(task_dir)
            if not files:
                continue
            
            oldest_file_time = min(
                os.path.getmtime(os.path.join(task_dir, f)) for f in files
            )
            oldest_datetime = datetime.fromtimestamp(oldest_file_time)
            
            if oldest_datetime < cutoff_time:
                # 清理旧任务
                cleanup_task_dir(task_id, keep_logs=False)
                cleaned_count += 1
                logger.info(f"🧹 已清理旧任务：{task_id[:8]}... (超过 {days_old} 天)")
        except Exception as e:
            logger.error(f"❌ 检查旧任务失败：{task_dir}, 错误：{e}")
    
    # 若仍超出配额，继续清理最近的任务
    current_size = get_workflow_dir_size()
    if current_size >= max_quota_bytes:
        logger.warning(f"⚠️ 超出配额，继续清理最近的任务...")
        # 按修改时间排序，清理最近的任务
        tasks_by_time = []
        for task_id in os.listdir(WORKFLOW_DIR):
            task_dir = os.path.join(WORKFLOW_DIR, task_id)
            if os.path.isdir(task_dir):
                try:
                    latest_time = max(
                        os.path.getmtime(os.path.join(task_dir, f)) for f in os.listdir(task_dir)
                    )
                    tasks_by_time.append((task_id, latest_time))
                except Exception:
                    continue
        
        tasks_by_time.sort(key=lambda x: x[1])
        
        for task_id, _ in tasks_by_time:
            if current_size < max_quota_bytes:
                break
            cleanup_task_dir(task_id, keep_logs=False)
            cleaned_count += 1
            current_size = get_workflow_dir_size()
            logger.info(f"🧹 已清理任务以释放空间：{task_id[:8]}...")
    
    return cleaned_count