"""
角色切换器 (Role Switcher)
实现虚拟多代理的核心：通过 System Prompt 动态切换角色，并清理上下文。
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from .logger import logger


class Role(Enum):
    """代理角色枚举"""
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    INTEGRATOR = "integrator"


# 各角色的 System Prompt 模板
ROLE_PROMPTS = {
    Role.PLANNER: """你现在的角色是【规划者 (Planner)】。
你的任务是：分析用户输入，拆解为可执行的步骤计划。
规则：
1. 不要执行任何操作，只输出计划。
2. 计划需包含：步骤 ID、描述、预期输出。
3. 输出格式为 JSON：
{{
  "task": "任务描述",
  "steps": [
    {{"id": 1, "description": "步骤描述", "expected_output": "预期输出"}},
    ...
  ]
}}
4. 保持简洁、清晰。
""",
    
    Role.EXECUTOR: """你现在的角色是【执行者 (Executor)】。
你的任务是：根据给定的计划，执行具体操作（如代码生成、文件读写、数据查询）。
规则：
1. 严格按照计划步骤执行，不要跳过或修改。
2. 每一步执行后，记录结果。
3. 若遇到错误，记录错误信息，不要继续。
4. 输出格式为 JSON：
{{
  "step_id": 1,
  "status": "success" | "failed",
  "output": "执行结果或错误信息"
}}
5. 保持结果准确、可验证。
""",
    
    Role.REVIEWER: """你现在的角色是【审查者 (Reviewer)】。
你的任务是：审查执行结果，判断是否符合要求。
规则：
1. 检查执行结果是否完整、准确。
2. 若符合，标记为 "approved"。
3. 若不符合，指出具体问题，并给出修改建议。
4. 输出格式为 JSON：
{{
  "approved": true | false,
  "comments": "审查意见",
  "suggestions": ["建议1", "建议2", ...]
}}
5. 保持客观、严谨。
""",
    
    Role.INTEGRATOR: """你现在的角色是【整合者 (Integrator)】。
你的任务是：汇总所有中间结果，生成最终回复。
规则：
1. 整合规划、执行、审查的所有信息。
2. 生成最终回复，确保逻辑连贯、信息完整。
3. 若审查未通过，需说明原因及后续建议。
4. 输出格式为自然语言（非 JSON）。
5. 保持友好、清晰。
"""
}


class RoleSwitcher:
    """
    角色切换器
    负责管理角色切换、System Prompt 注入、上下文清理。
    """
    
    def __init__(self, context_cleaner=None):
        """
        :param context_cleaner: 上下文清理器实例
        """
        self.context_cleaner = context_cleaner
        self.current_role: Optional[Role] = None
    
    def switch_to(self, role: Role, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        切换到指定角色，并清理上下文。
        :param role: 目标角色
        :param history: 当前历史消息
        :return: 清理后的历史消息（包含新的 System Prompt）
        """
        self.current_role = role
        logger.info(f"🔄 角色切换：{self.current_role.value.upper()}")
        
        # 1. 清理上下文
        if self.context_cleaner:
            cleaned_history = self.context_cleaner.clean_and_summarize(history)
        else:
            cleaned_history = history[-5:] if len(history) > 5 else history  # 简单保留最后 5 条
        
        # 2. 注入新的 System Prompt
        system_prompt = ROLE_PROMPTS[role]
        new_system_msg = {
            "role": "system",
            "content": system_prompt,
            "timestamp": "now"
        }
        
        # 3. 返回新的历史消息（System Prompt + 清理后的历史）
        return [new_system_msg] + cleaned_history
    
    def get_current_role(self) -> Optional[Role]:
        """获取当前角色"""
        return self.current_role
    
    def get_prompt(self, role: Role) -> str:
        """获取指定角色的 Prompt"""
        return ROLE_PROMPTS.get(role, "")