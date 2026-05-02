import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from .logger import logger


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    task_id: str
    description: str
    order: int
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    result: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "order": self.order,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "result": self.result,
            "error": self.error
        }


@dataclass
class TaskPlan:
    plan_id: str
    original_task: str
    subtasks: List[SubTask] = field(default_factory=list)
    current_step: int = 0

    def get_next_subtask(self) -> Optional[SubTask]:
        for subtask in self.subtasks:
            if subtask.status == TaskStatus.PENDING:
                deps_ok = all(
                    self.get_subtask(dep).status == TaskStatus.COMPLETED
                    for dep in subtask.dependencies
                )
                if deps_ok:
                    return subtask
        return None

    def get_subtask(self, task_id: str) -> Optional[SubTask]:
        for subtask in self.subtasks:
            if subtask.task_id == task_id:
                return subtask
        return None

    def is_complete(self) -> bool:
        return all(
            subtask.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for subtask in self.subtasks
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "original_task": self.original_task,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "current_step": self.current_step
        }


class TaskPlanner:
    def __init__(self):
        pass

    def create_plan_from_response(self, original_task: str, plan_response: str) -> TaskPlan:
        try:
            plan_data = self._parse_plan(plan_response)
            return self._create_plan_from_data(original_task, plan_data)
        except Exception as e:
            logger.error(f"解析任务计划失败: {e}")
            return self._create_simple_plan(original_task)

    def _parse_plan(self, plan_response: str) -> List[Dict[str, Any]]:
        json_match = plan_response.find('{')
        if json_match >= 0:
            try:
                json_str = plan_response[json_match:]
                data = json.loads(json_str)
                if isinstance(data, dict) and 'steps' in data:
                    return data['steps']
                elif isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        steps = []
        lines = plan_response.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if line and any(line.startswith(f"{n}.") or line.startswith(f"{n}、") for n in range(1, 20)):
                desc = line[line.find('.') + 1:].strip() if '.' in line else line[line.find('、') + 1:].strip()
                if desc:
                    steps.append({"description": desc, "order": len(steps) + 1})
        return steps

    def _create_plan_from_data(self, original_task: str, plan_data: List[Dict[str, Any]]) -> TaskPlan:
        import uuid
        plan = TaskPlan(
            plan_id=str(uuid.uuid4()),
            original_task=original_task
        )
        for i, step_data in enumerate(plan_data):
            subtask = SubTask(
                task_id=str(uuid.uuid4()),
                description=step_data.get("description", str(step_data)),
                order=step_data.get("order", i + 1),
                dependencies=step_data.get("dependencies", [])
            )
            plan.subtasks.append(subtask)
        logger.info(f"创建任务计划: {len(plan.subtasks)} 个子任务")
        return plan

    def _create_simple_plan(self, original_task: str) -> TaskPlan:
        plan = TaskPlan(
            plan_id=str(uuid.uuid4()),
            original_task=original_task
        )
        plan.subtasks.append(SubTask(
            task_id=str(uuid.uuid4()),
            description=original_task,
            order=1
        ))
        return plan

    def get_planning_prompt(self, task: str, available_skills: List[str]) -> str:
        prompt = f"""
任务: {task}

请将上述任务拆解为多个清晰、可执行的子任务。

要求:
1. 每个子任务应该是一个独立的行动
2. 子任务之间应该有合理的顺序
3. 考虑任务的依赖关系

可用技能: {', '.join(available_skills)}

请以JSON格式返回计划，格式如下:
{{
  "steps": [
    {{"description": "子任务1描述", "order": 1, "dependencies": []}},
    {{"description": "子任务2描述", "order": 2, "dependencies": ["子任务1的id"]}}
  ]
}}

如果任务很简单，也可以只有一个步骤。
"""
        return prompt