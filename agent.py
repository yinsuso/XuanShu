"""
UniversalAgent v5.0 - 认知进化版
集成 ReAct 思考闭环与强制复盘机制，实现从执行到进化的全链路闭环。
"""

import sys
import os
from pathlib import Path

# Ensure project root is in sys.path for script-mode execution
_current_root = Path(__file__).resolve().parent
if str(_current_root) not in sys.path:
    sys.path.insert(0, str(_current_root))

import re
import json
from typing import Dict, Any, List, Optional, Tuple

from config import MODEL_NAME, MAX_CODE_EXECUTIONS
from memory_core import memory_core
from memory_enhanced import EnhancedMemorySystem
from evolution_engine import EvolutionEngine
from evolution.react_loop import ReActLoop
from skills import registry, load_skills, list_skills
from logger import logger
from model_providers import config_manager, call_model
from conversation_manager import ConversationManager, MessageRole, conversation_manager as global_conversation_manager

class UniversalAgent:
    def __init__(
        self,
        auto_load_skills: bool = True,
        enable_evolution: bool = True,
        conversation_id: Optional[str] = None
    ):
        self.conversation_id = conversation_id
        self.conversation_manager = ConversationManager(conversation_id)
        self.memory_system = EnhancedMemorySystem()
        self.enable_evolution = enable_evolution
        self.skills_registry = registry
        self.code_execution_count = 0
        
        # 进化引擎
        self.evolution = EvolutionEngine()
        
        # 加载技能
        if auto_load_skills:
            self._load_skills()
        
        self._log_startup_info()

    @property
    def current_model(self):
        """动态获取当前模型配置"""
        config = config_manager.current_config
        if not config:
            configs = config_manager.list_configs()
            return configs[0] if configs else None
        return config

    def _log_startup_info(self):
        model_info = "未知"
        if self.current_model:
            model_info = f"{self.current_model.name} ({self.current_model.model_name})"
        
        logger.info("🤖 UniversalAgent v5.0 (Cognitive Evolution) 初始化完成")
        logger.info(f"📦 实际运行模型: {model_info}")
        logger.info(f"🔧 技能数量: {len(self.skills_registry.get_all())}")
        logger.info(f"🧬 进化功能: {'启用' if self.enable_evolution else '禁用'}")

    def _load_skills(self):
        try:
            load_skills()
        except Exception as e:
            logger.error(f"加载技能失败：{e}")

    def _build_system_prompt(self) -> str:
        skill_schemas = registry.get_openai_schemas()
        skills_info = [f"📌 {s['function']['name']}: {s['function']['description']}" for s in skill_schemas]

        # 整合统一记忆系统的上下文
        core_ctx = self.memory_system.get_full_context(query="")
        
        # 使用常规字符串拼接避免 f-string 与 三引号的转义问题
        system_prompt = "你是一个智能 AI 助手，具备深度思考与自主进化能力。\n\n"
        system_prompt += "【核心认知/记忆】\n" + core_ctx + "\n\n"
        system_prompt += "【核心能力】\n1. 🗣️ 自然对话: 流畅理解上下文。\n2. 🛠️ 工具使用: 通过 JSON 格式调用技能。\n3. 🧠 自主思考: 面对复杂任务时使用 <think> 标签规划。\n4. ⚡ 自主进化: 通过任务复盘提升能力。\n\n"
        system_prompt += "【可用技能】\n" + "\n".join(skills_info[:20])
        if len(skills_info) > 20:
            system_prompt += "\n..."
        
        system_prompt += "\n\n【调用技能格式】\n```json\n{\n \"skill\": \"技能名称\",\n \"args\": { \"参数名\": \"参数值\" }\n}\n```\n\n"
        system_prompt += "【行为规则】\n- 简单任务直接回答。\n- 复杂任务必须先输出 <think> 标签进行步骤规划。\n- 遇到 URL 必须调用 `web_fetch`。\n- 诚实、准确、简洁。\n\n开始！"
        
        return system_prompt

    def call_model(self, prompt: str, use_context: bool = True) -> Dict[str, Any]:
        config = config_manager.current_config
        if config is None:
            config_manager.load_configs()
            config = config_manager.current_config
            if config is None:
                raise ValueError("❌ 无法获取模型配置！请检查 data/model_config.json")
        
        response_text = call_model(
            config=config,
            prompt=prompt,
            system_prompt=self._build_system_prompt()
        )
        return {"response": response_text}

    def process_adaptive(self, user_input: str) -> str:
        """
        自适应处理入口：根据任务复杂度自动选择 Simple 或 ReAct 模式，并在结束后强制复盘。
        """
        self.conversation_manager.add_user_message(user_input)
        
        is_complex = any(word in user_input for word in ['分析', '研究', '编写', '查找', '对比', '计划']) or len(user_input) > 50
        
        final_response = ""
        tools_used = []
        success = True

        try:
            if is_complex:
                logger.info("🚀 检测到复杂任务，启动 ReAct 闭环模式...")
                react_loop = ReActLoop(self)
                final_response = react_loop.run(user_input)
                tools_used = list(set([t.metadata.get('skill') for t in react_loop.thoughts if t.metadata.get('skill')]))
            else:
                logger.info("⚡ 执行简单对话模式...")
                final_response = self._process_simple(user_input)

            self.conversation_manager.add_assistant_message(final_response)
            self.conversation_manager.save_current()

        except Exception as e:
            success = False
            final_response = f"处理过程中出现错误：{str(e)}"
            logger.error(f"Agent 执行异常: {e}", exc_info=True)

        if self.enable_evolution:
            try:
                self.evolution.run_evolution_cycle(
                    task=user_input,
                    result=final_response,
                    success=success,
                    tools_used=tools_used
                )
            except Exception as e:
                logger.error(f"进化循环触发失败: {e}")

        return final_response

    def _process_simple(self, user_input: str) -> str:
        conversation_history = self.conversation_manager.get_history_text(limit=10)
        prompt = f"【对话历史】\n{conversation_history}\n\n【用户问题】\n{user_input}\n\n请回答或调用技能。"
        
        response = self.call_model(prompt)
        output = response.get("response", "")
        
        skill_name, skill_args = self._parse_skill_call(output)
        if skill_name:
            skill_result = self._execute_skill(skill_name, skill_args or {})
            follow_up = f"技能结果:\n{skill_result}\n\n请根据结果回答用户。"
            final_data = self.call_model(follow_up)
            return final_data.get("response", "")
        
        return output

    def _parse_skill_call(self, text: str):
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                skill_call = json.loads(json_match.group(1))
                name = skill_call.get('skill') or skill_call.get('tool')
                return name, skill_call.get('args', {})
            except json.JSONDecodeError: pass
        return None, None

    def _execute_skill(self, skill_name: str, args: dict):
        skill = self.skills_registry.get(skill_name)
        if not skill: return f"❌ 未知技能：{skill_name}"
        try:
            return skill.execute(**args)
        except Exception as e:
            return f"❌ 技能执行失败：{str(e)}"

    def run(self):
        print("\n🚀 Hermes Agent v5.0 (Evolution Enabled) 已启动！")
        print("📝 输入 'exit' 退出 | 'skills' 查看技能 | 'memory' 查看记忆\n")
        
        while True:
            try:
                user_input = input("👤 您：").strip()
                if not user_input: continue
                if user_input.lower() in ['exit', 'quit', 'q']: break
                
                if user_input.lower() == 'skills':
                    for s in list_skills(): print(f"  - {s['name']}: {s['description']}")
                    continue
                
                if user_input.lower() == 'memory':
                    mem = memory_core.get_all_core_memory()
                    for k, v in mem.items(): print(f"  {k}: {v}")
                    continue
                
                response = self.process_adaptive(user_input)
                print(f"🤖 破执：{response}\n")
                
            except KeyboardInterrupt: break
            except Exception as e:
                print(f"❌ 错误：{str(e)}\n")

def main():
    agent = UniversalAgent()
    agent.run()

if __name__ == "__main__":
    main()
