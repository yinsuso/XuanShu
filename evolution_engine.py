import json
from typing import List, Dict, Optional
from memory_core import memory_core
from model_providers import call_model, ModelConfig, config_manager

class EvolutionEngine:
    def __init__(self, model_config: ModelConfig = None):
        """
        初始化进化引擎。
        
        Args:
            model_config: 当前使用的模型配置。若为 None，则使用默认配置。
        """
        self.model_config = model_config
    
    def generate_reflection_prompt(self, task: str, result: str, success: bool, tools_used: List[str]) -> str:
        """生成反思提示词"""
        return f"""
你是一个自我进化的 AI 助手。请对以下任务执行情况进行深度复盘：

【任务】
{task}

【结果】
{result}

【执行状态】
{'✅ 成功' if success else '❌ 失败'}

【使用工具】
{', '.join(tools_used) if tools_used else '无'}

请回答以下问题：
1. **成功之处**：哪些步骤或工具使用得当？
2. **不足之处**：哪些地方可以改进？是否有更好的工具或方法？
3. **经验总结**：如果再次遇到类似任务，你会怎么做？
4. **新技能建议**：是否发现可复用的模式？如果有，请描述新技能的功能。

请用 JSON 格式输出，包含以下字段：
{{
  "what_went_well": "成功之处",
  "what_went_wrong": "不足之处",
  "improvements": "经验总结",
  "should_generate_skill": true/false,
  "skill_idea": "新技能描述（如果 applicable）"
}}
"""
    
    def analyze_reflection(self, reflection_text: str) -> Dict:
        """分析反思结果"""
        try:
            # 尝试解析 JSON
            start = reflection_text.find('{')
            end = reflection_text.rfind('}') + 1
            if start != -1 and end != -1:
                return json.loads(reflection_text[start:end])
        except:
            pass
        
        #  fallback: 简单解析
        return {
            "what_went_well": "任务完成",
            "what_went_wrong": "无明显问题",
            "improvements": "保持当前策略",
            "should_generate_skill": False,
            "skill_idea": None
        }
    
    def perform_reflection(self, task: str, result: str, success: bool, tools_used: List[str]) -> Dict:
        """执行复盘"""
        
        # 动态获取当前配置
        config = config_manager.current_config
        if not config:
            configs = config_manager.list_configs()
            config = configs[0] if configs else None
        
        prompt = self.generate_reflection_prompt(task, result, success, tools_used)
        
        # 调用模型：使用动态获取的配置
        response = call_model(
            config=config,
            prompt=prompt,
            system_prompt="你是一个自我进化的 AI 助手，擅长复盘和总结经验。"
        )
        
        reflection_text = response.get("response", "")
        reflection = self.analyze_reflection(reflection_text)
        
        # 保存到记忆
        memory_core.add_reflection(
            task_summary=task[:100],
            reflection_text=reflection.get("improvements", ""),
            success=success,
            tools_used=tools_used
        )
        
        return reflection
    
    def suggest_new_skill(self, reflection: Dict) -> Optional[str]:
        """根据反思建议新技能"""
        
        if not reflection.get("should_generate_skill"):
            return None
        
        skill_idea = reflection.get("skill_idea", "")
        if not skill_idea:
            return None
        
        # 动态获取当前配置
        config = config_manager.current_config
        if not config:
            configs = config_manager.list_configs()
            config = configs[0] if configs else None
        
        # 生成技能代码模板
        prompt = f"""
根据以下反思，生成一个 Python 技能代码：

【新技能描述】
{skill_idea}

请生成一个符合 Hermes 技能规范的 Python 文件内容：
1. 包含 YAML 格式的元数据（name, description, trigger, category, requires_confirmation, parameters）
2. 包含 `execute` 函数实现
3. 代码简洁、安全、高效

只输出代码内容，不要包含其他说明。
"""
        # 调用模型：使用动态获取的配置
        response = call_model(
            config=config,
            prompt=prompt,
            system_prompt="你是一个 Python 专家，擅长生成高质量的技能代码。"
        )
        
        return response.get("response", "")
    
    def run_evolution_cycle(self, task: str, result: str, success: bool, tools_used: List[str]):
        """运行完整进化循环"""
        print("\n🧠 正在复盘...")
        
        reflection = self.perform_reflection(task, result, success, tools_used)
        
        print(f"✅ 复盘完成！")
        print(f"   成功之处: {reflection.get('what_went_well', 'N/A')}")
        print(f"   不足之处: {reflection.get('what_went_wrong', 'N/A')}")
        print(f"   改进建议: {reflection.get('improvements', 'N/A')}")
        
        if reflection.get("should_generate_skill"):
            print(f"💡 发现可复用模式，正在生成新技能...")
            skill_code = self.suggest_new_skill(reflection)
            
            if skill_code:
                # 保存技能
                skill_name = reflection.get("skill_idea", "new_skill").replace(" ", "_").lower()
                skill_path = f"skills/{skill_name}.py"
                
                with open(skill_path, 'w', encoding='utf-8') as f:
                    f.write(skill_code)
                
                print(f"✅ 新技能已生成: {skill_path}")
                print(f"   请重启 Agent 以加载新技能。")
            else:
                print(f"❌ 技能生成失败。")
        else:
            print(f"ℹ️ 暂无新技能建议。")