import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from logger import logger
from config import PROJECT_ROOT
from .evolution.trajectory import TaskTrajectory

REFLECTIONS_DIR = os.path.join(PROJECT_ROOT, "data", "reflections")
os.makedirs(REFLECTIONS_DIR, exist_ok=True)


@dataclass
class Reflection:
    reflection_id: str
    trajectory_id: str
    task_summary: str
    what_went_well: str
    what_went_wrong: str
    improvements: str
    skills_used: List[str]
    timestamp: datetime
    should_generate_skill: bool = False
    skill_idea: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reflection_id": self.reflection_id,
            "trajectory_id": self.trajectory_id,
            "task_summary": self.task_summary,
            "what_went_well": self.what_went_well,
            "what_went_wrong": self.what_went_wrong,
            "improvements": self.improvements,
            "skills_used": self.skills_used,
            "timestamp": self.timestamp.isoformat(),
            "should_generate_skill": self.should_generate_skill,
            "skill_idea": self.skill_idea
        }

    def save(self):
        filename = f"{self.reflection_id}.json"
        filepath = os.path.join(REFLECTIONS_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"反思已保存: {filepath}")


class Reflector:
    def __init__(self):
        pass

    def get_reflection_prompt(self, trajectory: TaskTrajectory) -> str:
        steps_text = "\n".join([
            f"[{step.step_type.value}] {step.content}"
            for step in trajectory.steps
        ])

        prompt = f"""
请对以下任务执行过程进行复盘分析。

任务描述: {trajectory.task_description}
是否成功: {trajectory.success}
执行摘要: {trajectory.summary}

执行过程:
{steps_text}

请以JSON格式返回分析结果:
{{
  "task_summary": "任务总结",
  "what_went_well": "做得好的地方",
  "what_went_wrong": "可以改进的地方",
  "improvements": "未来如何做得更好",
  "should_generate_skill": true/false,
  "skill_idea": "如果应该生成技能，描述技能应该做什么"
}}

如果这个任务有重复执行的价值，或者有通用的模式，请将should_generate_skill设为true。
"""
        return prompt

    def create_reflection_from_response(
        self,
        trajectory: TaskTrajectory,
        response: str,
        skills_used: List[str]
    ) -> Reflection:
        import uuid

        reflection_data = self._parse_reflection(response)

        reflection = Reflection(
            reflection_id=str(uuid.uuid4()),
            trajectory_id=trajectory.trajectory_id,
            task_summary=reflection_data.get("task_summary", trajectory.summary),
            what_went_well=reflection_data.get("what_went_well", ""),
            what_went_wrong=reflection_data.get("what_went_wrong", ""),
            improvements=reflection_data.get("improvements", ""),
            skills_used=skills_used,
            timestamp=datetime.now(),
            should_generate_skill=reflection_data.get("should_generate_skill", False),
            skill_idea=reflection_data.get("skill_idea", "")
        )
        reflection.save()
        return reflection

    def _parse_reflection(self, response: str) -> Dict[str, Any]:
        json_start = response.find('{')
        if json_start >= 0:
            try:
                json_str = response[json_start:]
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        return {
            "task_summary": response[:200] if len(response) > 200 else response,
            "what_went_well": "",
            "what_went_wrong": "",
            "improvements": "",
            "should_generate_skill": False,
            "skill_idea": ""
        }