import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from .config import PROJECT_ROOT
from .logger import logger

TRACES_DIR = os.path.join(PROJECT_ROOT, "data", "traces")
os.makedirs(TRACES_DIR, exist_ok=True)


class StepType(Enum):
    THINK = "think"
    ACT = "act"
    OBSERVE = "observe"
    REFLECT = "reflect"


@dataclass
class ExecutionStep:
    step_id: str
    step_type: StepType
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TaskTrajectory:
    trajectory_id: str
    task_description: str
    start_time: datetime
    end_time: Optional[datetime] = None
    steps: List[ExecutionStep] = None
    success: bool = False
    summary: str = ""

    def __post_init__(self):
        if self.steps is None:
            self.steps = []

    def add_step(self, step_type: StepType, content: str, metadata: Dict[str, Any] = None):
        step = ExecutionStep(
            step_id=str(uuid.uuid4()),
            step_type=step_type,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        self.steps.append(step)
        logger.debug(f"添加轨迹步骤: {step_type.value}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "task_description": self.task_description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_type": s.step_type.value,
                    "content": s.content,
                    "timestamp": s.timestamp.isoformat(),
                    "metadata": s.metadata
                }
                for s in self.steps
            ],
            "success": self.success,
            "summary": self.summary
        }

    def save(self):
        filename = f"{self.trajectory_id}.json"
        filepath = os.path.join(TRACES_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"轨迹已保存: {filepath}")

    @classmethod
    def load(cls, trajectory_id: str) -> Optional['TaskTrajectory']:
        filename = f"{trajectory_id}.json"
        filepath = os.path.join(TRACES_DIR, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskTrajectory':
        trajectory = cls(
            trajectory_id=data["trajectory_id"],
            task_description=data["task_description"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data["end_time"] else None,
            success=data["success"],
            summary=data["summary"]
        )
        trajectory.steps = [
            ExecutionStep(
                step_id=s["step_id"],
                step_type=StepType(s["step_type"]),
                content=s["content"],
                timestamp=datetime.fromisoformat(s["timestamp"]),
                metadata=s["metadata"]
            )
            for s in data["steps"]
        ]
        return trajectory


class TrajectoryRecorder:
    def __init__(self):
        self.current_trajectory: Optional[TaskTrajectory] = None
        self.trajectories: Dict[str, TaskTrajectory] = {}

    def start_task(self, task_description: str) -> str:
        trajectory_id = str(uuid.uuid4())
        self.current_trajectory = TaskTrajectory(
            trajectory_id=trajectory_id,
            task_description=task_description,
            start_time=datetime.now()
        )
        self.trajectories[trajectory_id] = self.current_trajectory
        logger.info(f"开始记录任务轨迹: {trajectory_id}")
        return trajectory_id

    def end_task(self, success: bool, summary: str = ""):
        if self.current_trajectory:
            self.current_trajectory.end_time = datetime.now()
            self.current_trajectory.success = success
            self.current_trajectory.summary = summary
            self.current_trajectory.save()
            logger.info(f"结束任务轨迹记录: {self.current_trajectory.trajectory_id}")

    def record_think(self, content: str, metadata: Dict[str, Any] = None):
        if self.current_trajectory:
            self.current_trajectory.add_step(StepType.THINK, content, metadata)

    def record_act(self, content: str, metadata: Dict[str, Any] = None):
        if self.current_trajectory:
            self.current_trajectory.add_step(StepType.ACT, content, metadata)

    def record_observe(self, content: str, metadata: Dict[str, Any] = None):
        if self.current_trajectory:
            self.current_trajectory.add_step(StepType.OBSERVE, content, metadata)

    def record_reflect(self, content: str, metadata: Dict[str, Any] = None):
        if self.current_trajectory:
            self.current_trajectory.add_step(StepType.REFLECT, content, metadata)

    def get_trajectory(self, trajectory_id: str) -> Optional[TaskTrajectory]:
        return self.trajectories.get(trajectory_id)

    def list_trajectories(self, limit: int = 20) -> List[Dict[str, Any]]:
        files = sorted(
            [f for f in os.listdir(TRACES_DIR) if f.endswith('.json')],
            key=lambda x: os.path.getmtime(os.path.join(TRACES_DIR, x)),
            reverse=True
        )
        trajectories = []
        for f in files[:limit]:
            filepath = os.path.join(TRACES_DIR, f)
            with open(filepath, 'r', encoding='utf-8') as fp:
                trajectories.append(json.load(fp))
        return trajectories


recorder = TrajectoryRecorder()