import os
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from .logger import logger
from .config import PROJECT_ROOT

WORKFLOW_DIR = os.path.join(PROJECT_ROOT, "data", "workflows")
os.makedirs(WORKFLOW_DIR, exist_ok=True)


class WorkflowStatus(Enum):
    """工作流状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """工作流步骤"""
    step_id: str
    name: str
    description: str
    skill_name: Optional[str] = None
    skill_args: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowTemplate:
    """工作流模板"""
    template_id: str
    name: str
    description: str
    category: str
    steps: List[WorkflowStep]
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "steps": [
                {
                    "step_id": s.step_id,
                    "name": s.name,
                    "description": s.description,
                    "skill_name": s.skill_name,
                    "skill_args": s.skill_args,
                    "condition": s.condition,
                    "depends_on": s.depends_on
                }
                for s in self.steps
            ],
            "variables": self.variables,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowTemplate':
        steps = [
            WorkflowStep(
                step_id=s["step_id"],
                name=s["name"],
                description=s["description"],
                skill_name=s.get("skill_name"),
                skill_args=s.get("skill_args", {}),
                condition=s.get("condition"),
                depends_on=s.get("depends_on", [])
            )
            for s in data["steps"]
        ]
        
        return cls(
            template_id=data["template_id"],
            name=data["name"],
            description=data["description"],
            category=data["category"],
            steps=steps,
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {})
        )


class WorkflowInstance:
    """工作流实例"""
    
    def __init__(self, template: WorkflowTemplate, variables: Dict[str, Any] = None):
        self.template = template
        self.instance_id = f"{template.template_id}_{os.urandom(4).hex()}"
        self.variables = {**template.variables, **(variables or {})}
        self.steps = [WorkflowStep(**s.__dict__) for s in template.steps]
        self.status = WorkflowStatus.PENDING
        self.results: Dict[str, Any] = {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def get_next_step(self) -> Optional[WorkflowStep]:
        """获取下一步"""
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            
            if step.depends_on:
                deps_completed = all(
                    self._get_step(dep).status == StepStatus.COMPLETED
                    for dep in step.depends_on
                )
                if not deps_completed:
                    continue
            
            if step.condition:
                if not self._evaluate_condition(step.condition):
                    step.status = StepStatus.SKIPPED
                    continue
            
            return step
        
        return None
    
    def _get_step(self, step_id: str) -> Optional[WorkflowStep]:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def _evaluate_condition(self, condition: str) -> bool:
        try:
            namespace = {**self.variables, **self.results}
            result = eval(condition, {}, namespace)
            return bool(result)
        except Exception as e:
            logger.warning(f"条件评估失败: {e}")
            return True
    
    def is_complete(self) -> bool:
        return all(
            step.status in [StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED]
            for step in self.steps
        )
    
    def get_progress(self) -> Dict[str, Any]:
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        total = len(self.steps)
        
        return {
            "instance_id": self.instance_id,
            "status": self.status.value,
            "completed": completed,
            "total": total,
            "progress": completed / total if total > 0 else 0
        }


class WorkflowEngine:
    """工作流引擎"""
    
    def __init__(self, skill_agent):
        self.skill_agent = skill_agent
        self.templates: Dict[str, WorkflowTemplate] = {}
        self.instances: Dict[str, WorkflowInstance] = {}
        self._load_presets()
    
    def _load_presets(self):
        """加载预设模板"""
        presets = self._get_preset_templates()
        for template in presets:
            self.templates[template.template_id] = template
            self._save_template(template)
        
        self._load_templates()
    
    def _get_preset_templates(self) -> List[WorkflowTemplate]:
        """获取预设模板"""
        return [
            WorkflowTemplate(
                template_id="code_development",
                name="代码开发流程",
                description="标准的代码开发工作流：分析->实现->测试->文档",
                category="development",
                steps=[
                    WorkflowStep(
                        step_id="analyze",
                        name="需求分析",
                        description="分析任务需求，理解目标",
                        skill_name=None
                    ),
                    WorkflowStep(
                        step_id="implement",
                        name="代码实现",
                        description="编写或修改代码",
                        skill_name="run_code",
                        depends_on=["analyze"]
                    ),
                    WorkflowStep(
                        step_id="test",
                        name="测试验证",
                        description="测试代码功能",
                        skill_name="run_code",
                        depends_on=["implement"]
                    ),
                    WorkflowStep(
                        step_id="document",
                        name="文档编写",
                        description="编写或更新文档",
                        depends_on=["test"]
                    )
                ]
            ),
            WorkflowTemplate(
                template_id="file_analysis",
                name="文件分析流程",
                description="分析文件内容并生成报告",
                category="analysis",
                steps=[
                    WorkflowStep(
                        step_id="list_files",
                        name="列出文件",
                        description="获取文件列表",
                        skill_name="list_dir"
                    ),
                    WorkflowStep(
                        step_id="read_files",
                        name="读取文件",
                        description="读取关键文件内容",
                        skill_name="read_file",
                        depends_on=["list_files"]
                    ),
                    WorkflowStep(
                        step_id="analyze",
                        name="分析内容",
                        description="分析文件内容",
                        depends_on=["read_files"]
                    ),
                    WorkflowStep(
                        step_id="report",
                        name="生成报告",
                        description="生成分析报告",
                        depends_on=["analyze"]
                    )
                ]
            ),
            WorkflowTemplate(
                template_id="refactoring",
                name="代码重构流程",
                description="代码审查->重构->验证",
                category="refactoring",
                steps=[
                    WorkflowStep(
                        step_id="review",
                        name="代码审查",
                        description="审查现有代码",
                        skill_name="analyze_python_file"
                    ),
                    WorkflowStep(
                        step_id="plan_refactor",
                        name="重构计划",
                        description="制定重构计划",
                        depends_on=["review"]
                    ),
                    WorkflowStep(
                        step_id="execute_refactor",
                        name="执行重构",
                        description="实施代码重构",
                        skill_name="edit_file",
                        depends_on=["plan_refactor"]
                    ),
                    WorkflowStep(
                        step_id="verify",
                        name="验证结果",
                        description="验证重构结果",
                        skill_name="run_code",
                        depends_on=["execute_refactor"]
                    )
                ]
            )
        ]
    
    def create_instance(
        self,
        template_id: str,
        variables: Dict[str, Any] = None
    ) -> Optional[WorkflowInstance]:
        """创建工作流实例"""
        if template_id not in self.templates:
            logger.error(f"模板不存在: {template_id}")
            return None
        
        template = self.templates[template_id]
        instance = WorkflowInstance(template, variables)
        self.instances[instance.instance_id] = instance
        
        logger.info(f"创建工作流实例: {instance.instance_id}")
        return instance
    
    def execute_task(self, task: str, template_id: str = None) -> Dict[str, Any]:
        """执行任务工作流"""
        if template_id and template_id in self.templates:
            instance = self.create_instance(template_id, {"task": task})
            if instance:
                return self.execute_instance(instance.instance_id)
        
        return {"error": "模板不存在或未选择"}
    
    def execute_instance(self, instance_id: str) -> Dict[str, Any]:
        """执行工作流实例"""
        if instance_id not in self.instances:
            return {"error": "实例不存在"}
        
        instance = self.instances[instance_id]
        instance.status = WorkflowStatus.RUNNING
        
        import time
        instance.start_time = time.time()
        
        logger.info(f"开始执行工作流: {instance_id}")
        
        while not instance.is_complete():
            step = instance.get_next_step()
            if not step:
                break
            
            step.status = StepStatus.RUNNING
            logger.info(f"执行步骤: {step.name}")
            
            try:
                if step.skill_name:
                    args = self._interpolate_args(step.skill_args, instance)
                    result = self.skill_agent._execute_skill(step.skill_name, args)
                    step.result = result
                    instance.results[step.step_id] = result
                else:
                    step.result = f"完成: {step.description}"
                
                step.status = StepStatus.COMPLETED
                logger.info(f"步骤完成: {step.name}")
            
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                logger.error(f"步骤失败: {step.name} - {e}")
        
        instance.status = WorkflowStatus.COMPLETED
        instance.end_time = time.time()
        
        logger.info(f"工作流完成: {instance_id}")
        
        return {
            "instance_id": instance_id,
            "status": instance.status.value,
            "results": instance.results,
            "duration": instance.end_time - instance.start_time if instance.end_time and instance.start_time else 0
        }
    
    def _interpolate_args(self, args: Dict[str, Any], instance: WorkflowInstance) -> Dict[str, Any]:
        """插值参数"""
        result = {}
        
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                var_name = value[2:-1]
                result[key] = instance.variables.get(var_name, value)
            else:
                result[key] = value
        
        return result
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有模板"""
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "step_count": len(t.steps)
            }
            for t in self.templates.values()
        ]
    
    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """获取模板"""
        return self.templates.get(template_id)
    
    def save_template(self, template: WorkflowTemplate):
        """保存模板"""
        self.templates[template.template_id] = template
        self._save_template(template)
    
    def _save_template(self, template: WorkflowTemplate):
        filepath = os.path.join(WORKFLOW_DIR, f"{template.template_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(template.to_dict(), f, ensure_ascii=False, indent=2)
    
    def _load_templates(self):
        for filename in os.listdir(WORKFLOW_DIR):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(WORKFLOW_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    template = WorkflowTemplate.from_dict(data)
                    self.templates[template.template_id] = template
            except Exception as e:
                logger.error(f"加载模板失败: {filename} - {e}")