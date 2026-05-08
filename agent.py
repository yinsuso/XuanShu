     1|"""

# 兜底：防止 PROJECT_ROOT 未定义
try:
    PROJECT_ROOT
except NameError:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
     2|UniversalAgent v5.0 - 认知进化版
     3|集成 ReAct 思考闭环与强制复盘机制，实现从执行到进化的全链路闭环。
     4|"""
     5|
     6|import sys
     7|import os
     8|from pathlib import Path
     9|
    10|# Ensure project root is in sys.path for script-mode execution
    11|_current_root = Path(__file__).resolve().parent
    12|if str(_current_root) not in sys.path:
    13|    sys.path.insert(0, str(_current_root))
    14|
    15|import re
    16|import json
    17|from typing import Dict, Any, List, Optional, Tuple
    18|
    19|from config import MODEL_NAME, MAX_CODE_EXECUTIONS, SYSTEM_CONTEXT_FILES, PROJECT_ROOT
    20|from memory_core import memory_core
    21|from memory_enhanced import EnhancedMemorySystem
    22|from evolution_engine import EvolutionEngine
    23|from evolution.react_loop import ReActLoop
    24|from skills import registry, load_skills, list_skills
    25|from logger import logger
    26|
    27|# 安全审批支持
    28|try:
    29|    from security.firewall.approval import ApprovalManager
    30|    SECURITY_AVAILABLE = True
    31|except ImportError:
    32|    SECURITY_AVAILABLE = False
    33|from model_providers import config_manager, call_model
    34|from conversation_manager import ConversationManager, MessageRole, conversation_manager as global_conversation_manager
    35|
    36|class UniversalAgent:
    37|    def __init__(
    38|        self,
    39|        auto_load_skills: bool = True,
    40|        enable_evolution: bool = True,
    41|        conversation_id: Optional[str] = None
    42|    ):
    43|        self.conversation_id = conversation_id
    44|        self.conversation_manager = ConversationManager(conversation_id)
    45|        self.memory_system = EnhancedMemorySystem()
    46|        # 兼容性别名：使 agent.memory 指向 memory_core，供 web_app.py 等使用
    47|        self.memory = self.memory_system.db
    48|        self.enable_evolution = enable_evolution
    49|        self.skills_registry = registry
    50|        self.code_execution_count = 0
    51|
    52|        # 安全审批管理器（可选）
    53|        self.approval_manager = None
    54|        if SECURITY_AVAILABLE:
    55|            try:
    56|                # 检查全局安全开关
    57|                from config import SECURITY_ENABLED
    58|                if SECURITY_ENABLED:
    59|                    self.approval_manager = ApprovalManager()
    60|            except Exception:
    61|                # 配置缺失则禁用
    62|                self.approval_manager = None
    63|        
    64|        # 进化引擎
    65|        self.evolution = EvolutionEngine()
    66|        
    67|        # 加载技能
    68|        if auto_load_skills:
    69|            self._load_skills()
    70|        
    71|        self._log_startup_info()
    72|
    73|    @property
    74|    def current_model(self):
    75|        """动态获取当前模型配置"""
    76|        config = config_manager.current_config
    77|        if not config:
    78|            configs = config_manager.list_configs()
    79|            return configs[0] if configs else None
    80|        return config
    81|
    82|    def _log_startup_info(self):
    83|        model_info = "未知"
    84|        if self.current_model:
    85|            model_info = f"{self.current_model.name} ({self.current_model.model_name})"
    86|        
    87|        logger.info("🤖 UniversalAgent v5.0 (Cognitive Evolution) 初始化完成")
    88|        logger.info(f"📦 实际运行模型: {model_info}")
    89|        logger.info(f"🔧 技能数量: {len(self.skills_registry.get_all())}")
    90|        logger.info(f"🧬 进化功能: {'启用' if self.enable_evolution else '禁用'}")
    91|
    92|    def _load_skills(self):
    93|        try:
    94|            load_skills()
    95|        except Exception as e:
    96|            logger.error(f"加载技能失败：{e}")
    97|
    98|    def _build_system_prompt(self) -> str:
    99|        skill_schemas = registry.get_openai_schemas()
   100|        skills_info = [f"📌 {s['function']['name']}: {s['function']['description']}" for s in skill_schemas]
   101|
   102|        # 整合统一记忆系统的上下文
   103|        core_ctx = self.memory_system.get_full_context(query="")
   104|
   105|        # 读取系统上下文文件（如 MEMORY.md, SOUL.md）
   106|        context_files_content = []
   107|        for rel_path in SYSTEM_CONTEXT_FILES:
   108|            file_path = os.path.join(PROJECT_ROOT, rel_path) if not os.path.isabs(rel_path) else rel_path
   109|            try:
   110|                if os.path.exists(file_path):
   111|                    with open(file_path, 'r', encoding='utf-8') as f:
   112|                        content = f.read().strip()
   113|                        if content:
   114|                            context_files_content.append(f"【{rel_path}】\n{content}")
   115|                else:
   116|                    logger.warning(f"系统上下文文件不存在：{file_path}")
   117|            except Exception as e:
   118|                logger.warning(f"读取系统上下文文件失败 {file_path}: {e}")
   119|
   120|        # 使用常规字符串拼接避免 f-string 与 三引号的转义问题
   121|        system_prompt = "你是一个智能 AI 助手，具备深度思考与自主进化能力。\n\n"
   122|        system_prompt += "【核心认知/记忆】\n" + core_ctx + "\n\n"
   123|        system_prompt += "【核心能力】\n1. 🗣️ 自然对话: 流畅理解上下文。\n2. 🛠️ 工具使用: 通过 JSON 格式调用技能。\n3. 🧠 自主思考: 面对复杂任务时使用 <think> 标签规划。\n4. ⚡ 自主进化: 通过任务复盘提升能力。\n\n"
   124|        system_prompt += "【可用技能】\n" + "\n".join(skills_info[:20])
   125|        if len(skills_info) > 20:
   126|            system_prompt += "\n..."
   127|
   128|        if context_files_content:
   129|            system_prompt += "\n\n【系统背景文档】\n" + "\n\n".join(context_files_content) + "\n\n"
   130|
   131|        system_prompt += "\n【调用技能格式】\n```json\n{\n \"skill\": \"技能名称\",\n \"args\": { \"参数名\": \"参数值\" }\n}\n```\n\n"
   132|        system_prompt += "【行为规则】\n- 简单任务直接回答。\n- 复杂任务必须先输出 <think> 标签进行步骤规划。\n- 遇到 URL 必须调用 `web_fetch`。\n- 诚实、准确、简洁。\n\n开始！"
   133|
   134|        return system_prompt
   135|
   136|    def call_model(self, prompt: str, use_context: bool = True) -> Dict[str, Any]:
   137|        config = config_manager.current_config
   138|        if config is None:
   139|            config_manager.load_configs()
   140|            config = config_manager.current_config
   141|            if config is None:
   142|                raise ValueError("❌ 无法获取模型配置！请检查 data/model_config.json")
   143|        
   144|        response_text = call_model(
   145|            config=config,
   146|            prompt=prompt,
   147|            system_prompt=self._build_system_prompt()
   148|        )
   149|        return {"response": response_text}
   150|
   151|    def process_adaptive(self, user_input: str) -> str:
   152|        """
   153|        自适应处理入口：根据任务复杂度自动选择 Simple 或 ReAct 模式，并在结束后强制复盘。
   154|        """
   155|        self.conversation_manager.add_user_message(user_input)
   156|        
   157|        is_complex = any(word in user_input for word in ['分析', '研究', '编写', '查找', '对比', '计划']) or len(user_input) > 50
   158|        
   159|        final_response = ""
   160|        tools_used = []
   161|        success = True
   162|
   163|        try:
   164|            if is_complex:
   165|                logger.info("🚀 检测到复杂任务，启动 ReAct 闭环模式...")
   166|                react_loop = ReActLoop(self)
   167|                final_response = react_loop.run(user_input)
   168|                tools_used = list(set([t.metadata.get('skill') for t in react_loop.thoughts if t.metadata.get('skill')]))
   169|            else:
   170|                logger.info("⚡ 执行简单对话模式...")
   171|                final_response = self._process_simple(user_input)
   172|
   173|            self.conversation_manager.add_assistant_message(final_response)
   174|            self.conversation_manager.save_current()
   175|
   176|        except Exception as e:
   177|            success = False
   178|            final_response = f"处理过程中出现错误：{str(e)}"
   179|            logger.error(f"Agent 执行异常: {e}", exc_info=True)
   180|
   181|        # 进化触发条件：仅复杂任务 或 执行失败 时触发
   182|        should_evolve = self.enable_evolution and (not success or is_complex)
   183|        if should_evolve:
   184|            try:
   185|                self.evolution.run_evolution_cycle(
   186|                    task=user_input,
   187|                    result=final_response,
   188|                    success=success,
   189|                    tools_used=tools_used
   190|                )
   191|            except Exception as e:
   192|                logger.error(f"进化循环触发失败: {e}")
   193|
   194|        return final_response
   195|
   196|    def _process_simple(self, user_input: str) -> str:
   197|        conversation_history = self.conversation_manager.get_history_text(limit=10)
   198|        prompt = f"【对话历史】\n{conversation_history}\n\n【用户问题】\n{user_input}\n\n请回答或调用技能。"
   199|        
   200|        response = self.call_model(prompt)
   201|        output = response.get("response", "")
   202|        
   203|        skill_name, skill_args = self._parse_skill_call(output)
   204|        if skill_name:
   205|            skill_result = self._execute_skill(skill_name, skill_args or {})
   206|            follow_up = f"技能结果:\n{skill_result}\n\n请根据结果回答用户。"
   207|            final_data = self.call_model(follow_up)
   208|            return final_data.get("response", "")
   209|        
   210|        return output
   211|
   212|    def _parse_skill_call(self, text: str):
   213|        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
   214|        if json_match:
   215|            try:
   216|                skill_call = json.loads(json_match.group(1))
   217|                name = skill_call.get('skill') or skill_call.get('tool')
   218|                return name, skill_call.get('args', {})
   219|            except json.JSONDecodeError: pass
   220|        return None, None
   221|
   222|    def _execute_skill(self, skill_name: str, args: dict):
   223|        skill = self.skills_registry.get(skill_name)
   224|        if not skill: return f"❌ 未知技能：{skill_name}"
   225|        # 安全审批检查
   226|        if self.approval_manager is not None:
   227|                approval = self.approval_manager.request(skill_name, args)
   228|                if not approval.get('allowed', True):
   229|                    return f"❌ 安全拦截：{approval.get('message','已被阻止')} (风险等级: {approval.get('risk_level','unknown')})"
   230|        try:
   231|            return skill.execute(**args)
   232|        except Exception as e:
   233|            return f"❌ 技能执行失败：{str(e)}"
   234|
   235|    def run(self):
   236|        print("\n🚀 Hermes Agent v5.0 (Evolution Enabled) 已启动！")
   237|        print("📝 输入 'exit' 退出 | 'skills' 查看技能 | 'memory' 查看记忆\n")
   238|        
   239|        while True:
   240|            try:
   241|                user_input = input("👤 您：").strip()
   242|                if not user_input: continue
   243|                if user_input.lower() in ['exit', 'quit', 'q']: break
   244|                
   245|                if user_input.lower() == 'skills':
   246|                    for s in list_skills(): print(f"  - {s['name']}: {s['description']}")
   247|                    continue
   248|                
   249|                if user_input.lower() == 'memory':
   250|                    mem = memory_core.get_all_core_memory()
   251|                    for k, v in mem.items(): print(f"  {k}: {v}")
   252|                    continue
   253|                
   254|                response = self.process_adaptive(user_input)
   255|                print(f"🤖 玄枢：{response}\n")
   256|                
   257|            except KeyboardInterrupt: break
   258|            except Exception as e:
   259|                print(f"❌ 错误：{str(e)}\n")
   260|
   261|def main():
   262|    agent = UniversalAgent()
   263|    agent.run()
   264|
   265|if __name__ == "__main__":
   266|    main()
   267|