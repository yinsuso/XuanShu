"""
工作流引擎 (Workflow Engine)
负责协调多代理工作流：Planner → Executor → Reviewer → Integrator。
支持异常处理、重试机制、回滚逻辑。
"""
import uuid
import time
from typing import Dict, Any, List, Optional
from logger import logger
from evolution.role_switcher import RoleSwitcher, Role
from utils.context_cleaner import ContextCleaner
from utils.file_manager import (
    save_task_state,
    load_task_state,
    get_task_summary,
    cleanup_task_dir
)


class WorkflowEngine:
    """
    工作流引擎
    协调虚拟多代理的完整工作流，支持重试与回滚。
    """
    
    def __init__(self, model_callback=None, max_retries: int = 3):
        """
        :param model_callback: 模型调用回调函数，签名: (prompt, system_prompt) -> response_text
        :param max_retries: 最大重试次数
        """
        self.role_switcher = RoleSwitcher(ContextCleaner())
        self.model_callback = model_callback
        self.max_retries = max_retries
        self.current_task_id: Optional[str] = None
    
    def start_task(self, user_input: str) -> str:
        """
        开始一个新任务。
        :param user_input: 用户输入
        :return: 最终结果或错误信息
        """
        self.current_task_id = str(uuid.uuid4())
        logger.info(f"🚀 新任务启动：{self.current_task_id[:8]}...")
        
        try:
            # 1. Planner 阶段
            plan = self._run_with_retry(self._run_planner, user_input, "Planner")
            save_task_state(self.current_task_id, "plan", plan)
            
            # 2. Executor 阶段
            result = self._run_with_retry(self._run_executor, plan, "Executor")
            save_task_state(self.current_task_id, "result", result)
            
            # 3. Reviewer 阶段
            review = self._run_with_retry(self._run_reviewer, result, "Reviewer")
            save_task_state(self.current_task_id, "review", review)
            
            # 4. 若审查未通过，尝试修正
            if not review.get("approved", False):
                logger.info("⚠️ 审查未通过，尝试修正...")
                result = self._run_with_retry(self._run_corrector, result, review, "Corrector")
                save_task_state(self.current_task_id, "result", result)
                review = self._run_with_retry(self._run_reviewer, result, "Reviewer")
                save_task_state(self.current_task_id, "review", review)
            
            # 5. Integrator 阶段
            final_output = self._run_integrator(plan, result, review)
            
            logger.info(f"✅ 任务完成：{self.current_task_id[:8]}...")
            return final_output
            
        except Exception as e:
            logger.error(f"❌ 任务失败：{e}")
            self._rollback()
            return f"任务执行失败：{str(e)}。已回滚到上一状态。"
    
    def _run_with_retry(self, func, *args, stage_name: str = "Unknown"):
        """
        带重试机制的运行器。
        :param func: 要执行的函数
        :param args: 函数参数
        :param stage_name: 阶段名称
        :return: 函数结果
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"🔄 {stage_name} 尝试 {attempt}/{self.max_retries}")
                result = func(*args)
                
                # 检查是否成功（针对特定阶段）
                if stage_name == "Executor" and isinstance(result, dict):
                    if result.get("status") == "failed":
                        raise Exception(result.get("output", "未知错误"))
                elif stage_name == "Reviewer" and isinstance(result, dict):
                    if not result.get("approved", False) and attempt == self.max_retries:
                        # 最后一次重试仍未通过，抛出异常
                        raise Exception("审查未通过，无法继续")
                
                return result
                
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ {stage_name} 尝试 {attempt} 失败：{e}")
                if attempt < self.max_retries:
                    time.sleep(1)  # 重试间隔
        
        # 所有重试失败
        raise Exception(f"{stage_name} 在 {self.max_retries} 次重试后仍失败：{last_error}")
    
    def _run_planner(self, user_input: str) -> Dict[str, Any]:
        """运行 Planner 角色"""
        logger.info("📝 阶段：Planner")
        
        # 构建 Prompt
        prompt = f"用户输入：{user_input}"
        history = [{"role": "user", "content": prompt}]
        
        # 切换角色
        self.role_switcher.switch_to(Role.PLANNER, history)
        system_prompt = self.role_switcher.get_prompt(Role.PLANNER)
        
        # 调用模型
        response = self._call_model(prompt, system_prompt)
        
        # 解析 JSON
        try:
            plan = self._parse_json(response)
        except Exception as e:
            logger.error(f"❌ Planner 解析失败：{e}")
            plan = {"task": user_input, "steps": [{"id": 1, "description": "执行用户输入", "expected_output": "结果"}]}
        
        return plan
    
    def _run_executor(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """运行 Executor 角色"""
        logger.info("⚙️ 阶段：Executor")
        
        # 构建 Prompt
        prompt = f"请执行以下计划：\n{plan}"
        history = [{"role": "user", "content": prompt}]
        
        # 切换角色
        self.role_switcher.switch_to(Role.EXECUTOR, history)
        system_prompt = self.role_switcher.get_prompt(Role.EXECUTOR)
        
        # 调用模型
        response = self._call_model(prompt, system_prompt)
        
        # 解析 JSON
        try:
            result = self._parse_json(response)
        except Exception as e:
            logger.error(f"❌ Executor 解析失败：{e}")
            result = {"step_id": 1, "status": "failed", "output": f"执行失败：{e}"}
        
        return result
    
    def _run_corrector(self, result: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
        """运行 Corrector 角色（修正执行结果）"""
        logger.info("🔧 阶段：Corrector")
        
        # 构建 Prompt
        prompt = f"""
        执行结果：{result}
        审查意见：{review}
        请根据审查意见修正执行结果。
        """
        history = [{"role": "user", "content": prompt}]
        
        # 切换角色到 Executor（复用执行逻辑）
        self.role_switcher.switch_to(Role.EXECUTOR, history)
        system_prompt = self.role_switcher.get_prompt(Role.EXECUTOR) + "\n\n注意：这是修正阶段，请根据审查意见调整执行。"
        
        # 调用模型
        response = self._call_model(prompt, system_prompt)
        
        # 解析 JSON
        try:
            corrected_result = self._parse_json(response)
        except Exception as e:
            logger.error(f"❌ Corrector 解析失败：{e}")
            corrected_result = {"step_id": result.get("step_id", 1), "status": "failed", "output": f"修正失败：{e}"}
        
        return corrected_result
    
    def _run_reviewer(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """运行 Reviewer 角色"""
        logger.info("🔍 阶段：Reviewer")
        
        # 构建 Prompt
        prompt = f"请审查以下执行结果：\n{result}"
        history = [{"role": "user", "content": prompt}]
        
        # 切换角色
        self.role_switcher.switch_to(Role.REVIEWER, history)
        system_prompt = self.role_switcher.get_prompt(Role.REVIEWER)
        
        # 调用模型
        response = self._call_model(prompt, system_prompt)
        
        # 解析 JSON
        try:
            review = self._parse_json(response)
        except Exception as e:
            logger.error(f"❌ Reviewer 解析失败：{e}")
            review = {"approved": False, "comments": f"审查失败：{e}", "suggestions": []}
        
        return review
    
    def _run_integrator(self, plan: Dict[str, Any], result: Dict[str, Any], review: Dict[str, Any]) -> str:
        """运行 Integrator 角色"""
        logger.info("📊 阶段：Integrator")
        
        # 构建 Prompt
        prompt = f"""
        请整合以下信息，生成最终回复：
        - 计划：{plan}
        - 执行结果：{result}
        - 审查意见：{review}
        """
        history = [{"role": "user", "content": prompt}]
        
        # 切换角色
        self.role_switcher.switch_to(Role.INTEGRATOR, history)
        system_prompt = self.role_switcher.get_prompt(Role.INTEGRATOR)
        
        # 调用模型
        response = self._call_model(prompt, system_prompt)
        
        return response
    
    def _call_model(self, prompt: str, system_prompt: str) -> str:
        """调用模型（需外部注入）"""
        if self.model_callback:
            return self.model_callback(prompt, system_prompt)
        else:
            logger.warning("⚠️ 模型回调未设置，返回模拟响应")
            return "模拟响应：任务已执行。"
    
    def _parse_json(self, text: str) -> Dict[str, Any]:
        """解析 JSON（简化版）"""
        import json
        import re
        
        # 尝试提取 JSON 代码块
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # 尝试直接解析
        return json.loads(text)
    
    def _rollback(self):
        """回滚到上一状态（清理当前任务目录）"""
        if self.current_task_id:
            logger.warning(f"🔄 回滚任务：{self.current_task_id[:8]}...")
            cleanup_task_dir(self.current_task_id)
            self.current_task_id = None
    
    def cleanup(self, task_id: Optional[str] = None):
        """清理任务目录"""
        tid = task_id or self.current_task_id
        if tid:
            cleanup_task_dir(tid)
            logger.info(f"🧹 已清理任务：{tid[:8]}...")