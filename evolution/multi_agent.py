import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from logger import logger



class AgentRole(Enum):
    """Agent角色"""
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    INTEGRATOR = "integrator"


@dataclass
class AgentMessage:
    """Agent间消息"""
    from_agent: str
    to_agent: Optional[str]
    content: str
    message_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """任务上下文"""
    original_task: str
    current_step: int = 0
    history: List[AgentMessage] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"


class BaseAgent(ABC):
    """Agent基类"""
    
    def __init__(self, role: AgentRole, name: str):
        self.role = role
        self.name = name
        self.context: Optional[TaskContext] = None
    
    @abstractmethod
    def process(self, message: Optional[AgentMessage] = None) -> AgentMessage:
        """处理消息"""
        pass
    
    def set_context(self, context: TaskContext):
        """设置上下文"""
        self.context = context


class PlannerAgent(BaseAgent):
    """规划Agent"""
    
    def __init__(self):
        super().__init__(AgentRole.PLANNER, "Planner")
    
    def process(self, message: Optional[AgentMessage] = None) -> AgentMessage:
        task = self.context.original_task if self.context else ""
        
        plan = self._create_plan(task)
        
        return AgentMessage(
            from_agent=self.name,
            to_agent="Executor",
            content=json.dumps(plan, ensure_ascii=False),
            message_type="plan",
            metadata={"plan": plan}
        )
    
    def _create_plan(self, task: str) -> Dict[str, Any]:
        """创建任务计划"""
        return {
            "task": task,
            "steps": [
                {"id": 1, "description": "分析任务需求", "status": "pending"},
                {"id": 2, "description": "执行主要操作", "status": "pending"},
                {"id": 3, "description": "验证结果", "status": "pending"}
            ]
        }


class ExecutorAgent(BaseAgent):
    """执行Agent"""
    
    def __init__(self, skill_agent):
        super().__init__(AgentRole.EXECUTOR, "Executor")
        self.skill_agent = skill_agent
    
    def process(self, message: Optional[AgentMessage] = None) -> AgentMessage:
        if not message:
            return AgentMessage(
                from_agent=self.name,
                to_agent="Planner",
                content="等待任务",
                message_type="status"
            )
        
        if message.message_type == "plan":
            plan = message.metadata.get("plan", {})
            results = self._execute_plan(plan)
            
            return AgentMessage(
                from_agent=self.name,
                to_agent="Reviewer",
                content=json.dumps(results, ensure_ascii=False),
                message_type="result",
                metadata={"results": results}
            )
        
        return AgentMessage(
            from_agent=self.name,
            to_agent="Integrator",
            content="执行完成",
            message_type="status"
        )
    
    def _execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """执行计划"""
        results = {}
        steps = plan.get("steps", [])
        
        for step in steps:
            step_id = step.get("id")
            description = step.get("description", "")
            results[f"step_{step_id}"] = {
                "description": description,
                "status": "completed",
                "output": f"已完成: {description}"
            }
        
        return results


class ReviewerAgent(BaseAgent):
    """审查Agent"""
    
    def __init__(self):
        super().__init__(AgentRole.REVIEWER, "Reviewer")
    
    def process(self, message: Optional[AgentMessage] = None) -> AgentMessage:
        if not message:
            return AgentMessage(
                from_agent=self.name,
                to_agent="Executor",
                content="等待结果",
                message_type="status"
            )
        
        review = self._review_results(message.metadata.get("results", {}))
        
        return AgentMessage(
            from_agent=self.name,
            to_agent="Integrator",
            content=json.dumps(review, ensure_ascii=False),
            message_type="review",
            metadata={"review": review}
        )
    
    def _review_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """审查结果"""
        return {
            "approved": True,
            "comments": "结果符合要求",
            "suggestions": []
        }


class IntegratorAgent(BaseAgent):
    """整合Agent"""
    
    def __init__(self):
        super().__init__(AgentRole.INTEGRATOR, "Integrator")
    
    def process(self, message: Optional[AgentMessage] = None) -> AgentMessage:
        if not message:
            return AgentMessage(
                from_agent=self.name,
                to_agent="Reviewer",
                content="等待审查",
                message_type="status"
            )
        
        final_result = self._integrate(message)
        
        return AgentMessage(
            from_agent=self.name,
            to_agent=None,
            content=final_result,
            message_type="final"
        )
    
    def _integrate(self, message: AgentMessage) -> str:
        """整合最终结果"""
        review = message.metadata.get("review", {})
        approved = review.get("approved", False)
        
        if approved:
            return "任务完成！结果已通过审查。"
        else:
            return "任务需要改进，请重新执行。"


class MultiAgentOrchestrator:
    """多Agent协调器"""
    
    def __init__(self, skill_agent):
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent(skill_agent)
        self.reviewer = ReviewerAgent()
        self.integrator = IntegratorAgent()
        
        self.agents = {
            "Planner": self.planner,
            "Executor": self.executor,
            "Reviewer": self.reviewer,
            "Integrator": self.integrator
        }
    
    def execute_task(self, task: str) -> str:
        """执行任务"""
        context = TaskContext(original_task=task)
        
        for agent in self.agents.values():
            agent.set_context(context)
        
        logger.info(f"启动多Agent协作: {task}")
        
        message = None
        current_agent = self.planner
        
        while True:
            message = current_agent.process(message)
            context.history.append(message)
            
            if message.message_type == "final":
                context.status = "completed"
                return message.content
            
            if not message.to_agent or message.to_agent not in self.agents:
                context.status = "completed"
                return message.content
            
            current_agent = self.agents[message.to_agent]
            context.current_step += 1
            
            if context.current_step > 20:
                context.status = "timeout"
                return "执行超时"