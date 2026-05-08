"""

# 兜底：防止 PROJECT_ROOT 未定义
try:
    PROJECT_ROOT
except NameError:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
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

from config import MODEL_NAME, MAX_CODE_EXECUTIONS, SYSTEM_CONTEXT_FILES, PROJECT_ROOT
from memory_core import memory_core
from memory_enhanced import EnhancedMemorySystem
from evolution_engine import EvolutionEngine
from evolution.react_loop import ReActLoop
from skills import registry, load_skills, list_skills
from logger import logger

# 安全审批支持
try:
    from security.firewall.approval import ApprovalManager
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
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
        # 兼容性别名：使 agent.memory 指向 memory_core，供 web_app.py 等使用
        self.memory = self.memory_system.db
        self.enable_evolution = enable_evolution
        self.skills_registry = registry
        self.code_execution_count = 0

        # 安全审批管理器（可选）
        self.approval_manager = None
        if SECURITY_AVAILABLE:
            try:
                # 检查全局安全开关
                from config import SECURITY_ENABLED
                if SECURITY_ENABLED:
                    self.approval_manager = ApprovalManager()
            except Exception:
                # 配置缺失则禁用
                self.approval_manager = None
        
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

    def _build_system_prompt(self, query: str = "") -> str:
        skill_schemas = registry.get_openai_schemas()
        skills_info = [f"📌 {s['function']['name']}: {s['function']['description']}" for s in skill_schemas]

        # 整合统一记忆系统的上下文（带查询检索）
        core_ctx = self.memory_system.get_full_context(query=query)

        # 读取系统上下文文件（如 MEMORY.md, SOUL.md）并解析结构化内容
        memory_sections = self._parse_memory_files()

        # ========== 构建结构化系统提示词（参考 Hermes 模式）==========
        
        system_prompt = ""
        
        # 1. 角色定义（使用 XML 标签增强模型识别）
        system_prompt += "<system_prompt>\n"
        system_prompt += "<identity>\n"
        system_prompt += "你是玄枢智能助手，一个具备深度思考、工具使用和自主进化能力的AI助手。\n"
        system_prompt += "你的目标是帮助用户完成各种任务，从简单问答到复杂的代码编写和数据分析。\n"
        system_prompt += "</identity>\n\n"
        
        # 2. 核心指令（结构化）
        system_prompt += "<instructions>\n"
        system_prompt += "<rule>始终使用中文进行思考和回复</rule>\n"
        system_prompt += "<rule>对于简单问题，直接给出简洁准确的回答</rule>\n"
        system_prompt += "<rule>对于复杂任务，使用 <think> 标签进行步骤规划</rule>\n"
        system_prompt += "<rule>需要外部信息时，使用工具获取数据</rule>\n"
        system_prompt += "<rule>保持诚实，对于不确定的问题要明确说明</rule>\n"
        system_prompt += "<rule>回答要简洁明了，避免冗长</rule>\n"
        system_prompt += "</instructions>\n\n"
        
        # 3. 身份认同（从 SOUL.md 解析）
        if memory_sections.get('identity'):
            system_prompt += "<identity_core>\n"
            system_prompt += memory_sections['identity'] + "\n"
            system_prompt += "</identity_core>\n\n"
        
        # 4. 核心记忆（从数据库）
        if core_ctx:
            system_prompt += "<memory_core>\n"
            system_prompt += core_ctx + "\n"
            system_prompt += "</memory_core>\n\n"
        
        # 5. 关键事实（从 MEMORY.md 解析）
        if memory_sections.get('key_facts'):
            system_prompt += "<key_facts>\n"
            system_prompt += memory_sections['key_facts'] + "\n"
            system_prompt += "</key_facts>\n\n"
        
        # 6. 用户偏好（从 MEMORY.md 解析）
        if memory_sections.get('user_preferences'):
            system_prompt += "<user_preferences>\n"
            system_prompt += memory_sections['user_preferences'] + "\n"
            system_prompt += "</user_preferences>\n\n"
        
        # 7. 历史经验（从 MEMORY.md 解析）
        if memory_sections.get('historical_knowledge'):
            system_prompt += "<historical_knowledge>\n"
            system_prompt += memory_sections['historical_knowledge'] + "\n"
            system_prompt += "</historical_knowledge>\n\n"
        
        # 8. 能力边界（从 SOUL.md 解析）
        if memory_sections.get('capabilities'):
            system_prompt += "<capabilities>\n"
            system_prompt += memory_sections['capabilities'] + "\n"
            system_prompt += "</capabilities>\n\n"
        
        # 9. 可用技能
        system_prompt += "<available_skills>\n"
        system_prompt += "\n".join(skills_info[:20])
        if len(skills_info) > 20:
            system_prompt += "\n..."
        system_prompt += "\n</available_skills>\n\n"
        
        # 10. 工具调用格式
        system_prompt += "<tool_format>\n"
        system_prompt += "当需要使用工具时，请使用 JSON 格式输出：\n"
        system_prompt += "```json\n"
        system_prompt += "{ \"skill\": \"技能名称\", \"args\": { \"参数名\": \"参数值\" } }\n"
        system_prompt += "```\n"
        system_prompt += "</tool_format>\n\n"
        
        # 11. 输出格式偏好
        if memory_sections.get('output_preferences'):
            system_prompt += "<output_preferences>\n"
            system_prompt += memory_sections['output_preferences'] + "\n"
            system_prompt += "</output_preferences>\n\n"
        
        system_prompt += "</system_prompt>\n"
        
        return system_prompt

    def _parse_memory_files(self) -> dict:
        """解析记忆文件，提取结构化内容（参考 Hermes 记忆模式）"""
        sections = {}
        
        for rel_path in SYSTEM_CONTEXT_FILES:
            file_path = os.path.join(PROJECT_ROOT, rel_path) if not os.path.isabs(rel_path) else rel_path
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            # 解析 Markdown 格式的章节
                            sections.update(self._parse_markdown_sections(content, rel_path))
                else:
                    logger.warning(f"系统上下文文件不存在：{file_path}")
            except Exception as e:
                logger.warning(f"读取系统上下文文件失败 {file_path}: {e}")
        
        return sections

    def _parse_markdown_sections(self, content: str, filename: str) -> dict:
        """解析 Markdown 文件中的章节内容"""
        import re
        sections = {}
        
        if filename == "SOUL.md":
            # SOUL.md 结构：身份认同、核心指令、能力边界、输出格式偏好、工作流程
            patterns = {
                'identity': r'##\s*1\.?\s*身份认同[\s\S]*?(?=##\s*2\.|$)',
                'instructions': r'##\s*2\.?\s*核心指令[\s\S]*?(?=##\s*3\.|$)',
                'capabilities': r'##\s*3\.?\s*能力边界[\s\S]*?(?=##\s*4\.|$)',
                'output_preferences': r'##\s*4\.?\s*输出格式偏好[\s\S]*?(?=##\s*5\.|$)',
                'workflow': r'##\s*5\.?\s*工作流程[\s\S]*?(?=##\s*6\.|$|$)'
            }
        elif filename == "MEMORY.md":
            # MEMORY.md 结构：系统背景、关键事实、历史经验、用户偏好
            patterns = {
                'system_context': r'##\s*1\.?\s*系统背景[\s\S]*?(?=##\s*2\.|$)',
                'key_facts': r'##\s*2\.?\s*关键事实[\s\S]*?(?=##\s*3\.|$)',
                'historical_knowledge': r'##\s*3\.?\s*历史经验[\s\S]*?(?=##\s*4\.|$)',
                'user_preferences': r'##\s*4\.?\s*用户偏好[\s\S]*?(?=##\s*5\.|$|$)'
            }
        else:
            return sections
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                # 提取章节内容并清理格式
                section_content = match.group(0)
                # 移除标题行
                section_content = re.sub(r'^##\s*\d+\.?\s*[^\n]+\n', '', section_content)
                # 移除多余空行
                section_content = '\n'.join(line.strip() for line in section_content.split('\n') if line.strip())
                sections[key] = section_content.strip()
        
        return sections

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
            system_prompt=self._build_system_prompt(query=prompt)
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

        # 进化触发条件：仅复杂任务 或 执行失败 时触发
        should_evolve = self.enable_evolution and (not success or is_complex)
        if should_evolve:
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
        # 安全审批检查
        if self.approval_manager is not None:
                approval = self.approval_manager.request(skill_name, args)
                if not approval.get('allowed', True):
                    return f"❌ 安全拦截：{approval.get('message','已被阻止')} (风险等级: {approval.get('risk_level','unknown')})"
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
                print(f"🤖 玄枢：{response}\n")
                
            except KeyboardInterrupt: break
            except Exception as e:
                print(f"❌ 错误：{str(e)}\n")

def main():
    agent = UniversalAgent()
    agent.run()

if __name__ == "__main__":
    main()
