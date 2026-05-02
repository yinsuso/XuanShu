"""
任务管理器 (Task Manager)
负责异步任务队列、后台执行、进度推送。
"""
import asyncio
import uuid
from typing import Dict, Any, Optional, Callable
from .logger import logger
from .evolution.workflow_engine import WorkflowEngine


class TaskManager:
    """
    任务管理器
    管理异步任务队列，支持后台执行与进度推送。
    """
    
    def __init__(self, model_callback: Callable):
        """
        :param model_callback: 模型调用回调函数
        """
        self.task_queue = asyncio.Queue()
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.model_callback = model_callback
        self.engine = WorkflowEngine(model_callback=model_callback, max_retries=3)
        self.running = True
        
        # 启动后台任务执行器
        asyncio.create_task(self._task_executor())
    
    async def submit_task(self, user_input: str, on_progress: Optional[Callable] = None) -> str:
        """
        提交新任务。
        :param user_input: 用户输入
        :param on_progress: 进度回调函数 (stage: str, message: str)
        :return: 任务 ID
        """
        task_id = str(uuid.uuid4())
        self.active_tasks[task_id] = {
            "status": "pending",
            "stage": "pending",
            "progress": 0,
            "result": None,
            "error": None,
            "on_progress": on_progress
        }
        
        await self.task_queue.put((task_id, user_input))
        logger.info(f"📥 任务已提交：{task_id[:8]}...")
        return task_id
    
    async def _task_executor(self):
        """后台任务执行器（持续运行）"""
        logger.info("🚀 任务执行器已启动")
        
        while self.running:
            try:
                task_id, user_input = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                logger.info(f"🔄 开始执行任务：{task_id[:8]}...")
                
                # 更新任务状态
                if task_id in self.active_tasks:
                    self.active_tasks[task_id]["status"] = "running"
                    self.active_tasks[task_id]["stage"] = "starting"
                    self.active_tasks[task_id]["progress"] = 10
                
                # 执行任务
                try:
                    # 定义进度回调
                    def on_progress(stage: str, message: str):
                        if task_id in self.active_tasks:
                            self.active_tasks[task_id]["stage"] = stage
                            self.active_tasks[task_id]["progress"] = self._get_progress(stage)
                            logger.info(f"📊 任务 {task_id[:8]}... 进度：{stage} ({message})")
                            
                            # 调用外部回调
                            if self.active_tasks[task_id]["on_progress"]:
                                asyncio.create_task(
                                    self.active_tasks[task_id]["on_progress"](stage, message)
                                )
                    
                    # 执行工作流（需注入进度回调）
                    # 注意：此处简化处理，实际需改造 WorkflowEngine 支持进度回调
                    result = self.engine.start_task(user_input)
                    
                    # 更新任务状态
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]["status"] = "completed"
                        self.active_tasks[task_id]["stage"] = "completed"
                        self.active_tasks[task_id]["progress"] = 100
                        self.active_tasks[task_id]["result"] = result
                        
                except Exception as e:
                    logger.error(f"❌ 任务执行失败：{task_id[:8]}... {e}")
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]["status"] = "failed"
                        self.active_tasks[task_id]["stage"] = "error"
                        self.active_tasks[task_id]["error"] = str(e)
                
                self.task_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ 任务执行器错误：{e}")
    
    def _get_progress(self, stage: str) -> int:
        """根据阶段返回进度百分比"""
        progress_map = {
            "starting": 10,
            "Planner": 25,
            "Executor": 50,
            "Reviewer": 75,
            "Corrector": 85,
            "Integrator": 95,
            "completed": 100,
            "error": 0
        }
        return progress_map.get(stage, 0)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self.active_tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务（简化版：仅标记状态）"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["status"] = "cancelled"
            self.active_tasks[task_id]["stage"] = "cancelled"
            logger.info(f"🚫 任务已取消：{task_id[:8]}...")
            return True
        return False
    
    def stop(self):
        """停止任务执行器"""
        self.running = False
        logger.info("🛑 任务执行器已停止")