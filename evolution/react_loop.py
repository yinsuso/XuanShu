import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from logger import logger


class ThoughtType(Enum):
    """思考类型"""
    REASON = "reason"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    CORRECTION = "correction" # 新增：明确的修正计划


@dataclass
class Thought:
    """思考节点"""
    thought_type: ThoughtType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class ActionDecision:
    """行动决策"""
    needs_action: bool
    skill_name: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    final_answer: Optional[str] = None
    reasoning: str = ""


class ReActLoop:
    """Reasoning + Acting 循环"""

    def __init__(self, agent, max_iterations: int = 10):
        self.agent = agent
        self.max_iterations = max_iterations
        self.thoughts: List[Thought] = []

    def _list_skills(self) -> str:
        """获取技能列表字符串"""
        try:
            skills = self.agent.skills_registry.list_skills()
            if not skills:
                return "（暂无技能）"
            lines = []
            for s in skills:
                lines.append(f"- {s['name']}: {s['description']}")
            return "\n".join(lines)
        except Exception as e:
            return f"（技能列表获取失败: {e}）"
    
    def run(self, task: str) -> str:
        """运行ReAct循环"""
        logger.info(f"启动ReAct循环: {task[:100]}...")
        
        # 用于检测死循环：记录 (技能名, 参数) -> 出现次数
        action_history = {}
        
        for iteration in range(self.max_iterations):
            logger.info(f"迭代 {iteration + 1}/{self.max_iterations}")
            
            thought = self._think(task, iteration)
            self.thoughts.append(thought)
            
            decision = self._decide_action(thought)
            
            if not decision.needs_action:
                logger.info("任务完成，返回最终答案")
                return decision.final_answer or "任务完成"
            
            # 死循环检测
            action_key = (decision.skill_name, json.dumps(decision.args, sort_keys=True))
            action_history[action_key] = action_history.get(action_key, 0) + 1
            if action_history[action_key] >= 3:
                logger.warning(f"检测到潜在死循环：技能 {decision.skill_name} 已重复调用 3 次")
                correction = self._reflect_and_correct(task, "检测到重复操作，请强制改变策略")
                self.thoughts.append(correction)

            result = self._execute_action(decision)
            
            observation = Thought(
                thought_type=ThoughtType.OBSERVATION,
                content=result,
                metadata={"iteration": iteration}
            )
            self.thoughts.append(observation)
            
            # 实时感知：如果观察结果包含错误或失败，立即触发修正
            if "❌" in result or "错误" in result or "fail" in result.lower():
                logger.info("检测到执行结果异常，触发实时修正...")
                correction = self._reflect_and_correct(task, result)
                self.thoughts.append(correction)
            elif self._should_reflect(iteration):
                reflection = self._reflect(task)
                self.thoughts.append(reflection)
        
        logger.warning("达到最大迭代次数")
        return self._generate_final_summary()
    def _think(self, task: str, iteration: int) -> Thought:
        """思考步骤"""
        context = self._build_context(task)
        
        prompt = f"""任务: {task}

当前迭代: {iteration + 1}

已有的思考过程:
{self._format_thoughts()}

请继续思考下一步该做什么。请用清晰的语言描述你的推理过程。"""
        
        response = self.agent.call_model(prompt)
        content = response.get("response", "")

        return Thought(
            thought_type=ThoughtType.REASON,
            content=content,
            metadata={"iteration": iteration}
        )

    def _decide_action(self, thought: Thought) -> ActionDecision:
        """决定行动"""
        prompt = f"""基于以下思考，决定下一步行动：

思考内容:
{thought.content}

可用技能:
{self._list_skills()}

请决定：
1. 是否需要调用技能？
2. 如果需要，调用哪个技能？参数是什么？
3. 如果不需要，给出最终答案。

请用JSON格式返回：
{{
    "needs_action": true/false,
    "skill_name": "技能名称或null",
    "args": {{"参数名": "参数值"}},
    "final_answer": "最终答案或null",
    "reasoning": "决策理由"
}}"""

        response = self.agent.call_model(prompt)
        content = response.get("response", "")
        
        return self._parse_decision(content)
    
    def _execute_action(self, decision: ActionDecision) -> str:
        """执行行动"""
        if not decision.skill_name:
            return "无需执行技能"
        
        logger.info(f"执行技能: {decision.skill_name}")
        return self.agent._execute_skill(decision.skill_name, decision.args)
    
    def _reflect(self, task: str) -> Thought:
        """反思"""
        prompt = f"""任务: {task}

请对当前的执行过程进行反思：
1. 目前进展如何？
2. 有什么可以改进的地方？
3. 下一步的策略是否需要调整？

思考历史:
{self._format_thoughts()}"""

        response = self.agent.call_model(prompt)
        content = response.get("response", "")

        return Thought(
            thought_type=ThoughtType.REFLECTION,
            content=content,
            metadata={"type": "reflection"}
        )
    
    def _format_thoughts(self) -> str:
        """格式化思考历史"""
        if not self.thoughts:
            return "（暂无思考历史）"

        lines = []
        for i, thought in enumerate(self.thoughts[-8:], 1):  # 最近8条
            prefix = "🔥" if thought.thought_type == ThoughtType.CORRECTION else ""
            lines.append(f"{i}. {prefix}[{thought.thought_type.value}] {thought.content[:200]}")
        return "\n".join(lines)

    def _build_context(self, task: str) -> str:
        """构建上下文"""
        parts = [f"任务: {task}"]

        if self.thoughts:
            # 1. 首先提取最近的修正计划 (Correction)，给予最高优先级
            corrections = [t.content for t in self.thoughts if t.thought_type == ThoughtType.CORRECTION]
            if corrections:
                parts.append("\n【⚠️ 最高优先级：当前修正计划】")
                parts.append(corrections[-1]) # 取最近的一次修正

            # 2. 添加最近的思考历史
            parts.append("\n思考历史:")
            parts.append(self._format_thoughts())

        return "\n".join(parts)

    def _should_reflect(self, iteration: int) -> bool:
        """判断是否应该进行反思"""
        return iteration > 0 and iteration % 3 == 0
    
    def _reflect_and_correct(self, task: str, error_info: str) -> Thought:
        """反思并生成修正计划"""
        prompt = f"""任务: {task}

执行过程中遇到问题: {error_info}

请分析问题原因并制定修正计划：
1. 问题原因是什么？
2. 下一步应该如何调整策略？
3. 具体的修正步骤是什么？

思考历史:
{self._format_thoughts()}

请给出明确的修正计划。"""

        response = self.agent.call_model(prompt)
        content = response.get("response", "")

        return Thought(
            thought_type=ThoughtType.CORRECTION,
            content=content,
            metadata={"type": "correction", "error": error_info}
        )
    
    def _parse_decision(self, content: str) -> ActionDecision:
        """解析模型返回的决策JSON"""
        try:
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            data = json.loads(content.strip())
            return ActionDecision(
                needs_action=data.get("needs_action", False),
                skill_name=data.get("skill_name"),
                args=data.get("args", {}),
                final_answer=data.get("final_answer"),
                reasoning=data.get("reasoning", "")
            )
        except Exception as e:
            logger.error(f"决策解析失败: {e}")
            return ActionDecision(
                needs_action=False,
                final_answer=f"解析决策时发生错误: {e}",
                reasoning="解析失败"
            )
    
    def _generate_final_summary(self) -> str:
        """生成最终总结"""
        prompt = f"""任务: {self.thoughts[0].content if self.thoughts else "未知任务"}

请对整个执行过程进行总结：
1. 完成了什么？
2. 遇到了什么问题？
3. 最终结果是什么？

思考历史:
{self._format_thoughts()}

请用自然语言给出最终总结报告。"""

        response = self.agent.call_model(prompt)
        return response.get("response", "任务已完成")