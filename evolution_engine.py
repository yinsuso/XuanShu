import json
from typing import List, Dict, Optional
from memory_core import memory_core
from model_providers import call_model, ModelConfig, config_manager

class EvolutionEngine:
    def __init__(self):
        """
        初始化进化引擎。
        """
        pass

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

        # call_model 返回纯文本字符串
        reflection_text = response
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

请生成一个符合以下规范的 Python 文件内容：
1. 使用 @skill 装饰器注册技能（from skills.base import skill, SkillCategory）
2. 包含完整的函数实现
3. 代码简洁、安全、高效
4. 必须有 try/except 错误处理
5. 所有参数和返回值必须有类型标注
6. 技能名称必须使用英文小写 snake_case，长度不超过30字符

模板示例:
```python
from skills.base import skill, SkillCategory

@skill(
    name="skill_name",
    description="技能描述",
    category=SkillCategory.UTILITY
)
def skill_function(param1: str, param2: int = 0) -> str:
    \"\"\"技能函数文档\"\"\"
    try:
        # 实现代码
        result = f"处理: {{param1}}, {{param2}}"
        return result
    except Exception as e:
        return f"错误: {{e}}"
```

只输出 Python 代码，不要其他解释。
"""
        # 调用模型：使用动态获取的配置
        response = call_model(
            config=config,
            prompt=prompt,
            system_prompt="你是一个 Python 专家，擅长生成高质量的技能代码。"
        )

        # call_model 返回纯文本字符串（技能代码）
        return response

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
                # 使用 SkillGenerator 统一生成和保存技能
                try:
                    from evolution.skill_generator import SkillGenerator
                    generator = SkillGenerator()
                    # 构建一个简化的 reflection 对象用于生成器
                    class SimpleReflection:
                        def __init__(self, task_summary, skill_idea):
                            self.task_summary = task_summary
                            self.skill_idea = skill_idea

                    simple_reflection = SimpleReflection(
                        task_summary=task[:100],
                        skill_idea=reflection.get("skill_idea", "new_skill")
                    )

                    success_flag, filepath, message = generator.generate_and_save(
                        simple_reflection, skill_code
                    )

                    if success_flag and filepath:
                        print(f"✅ 新技能已生成并加载: {filepath}")
                        print(f"   技能已自动注册，无需重启 Agent。")
                    else:
                        print(f"❌ 技能生成失败: {message}")
                except Exception as e:
                    print(f"❌ 技能生成失败: {e}")
                    # 降级处理：直接保存到 skills/ 目录
                    skill_name = reflection.get("skill_idea", "new_skill").replace(" ", "_").lower()
                    skill_path = f"skills/{skill_name}.py"
                    with open(skill_path, 'w', encoding='utf-8') as f:
                        f.write(skill_code)
                    print(f"⚠️ 已降级保存到: {skill_path}")
                    print(f"   请重启 Agent 以加载新技能。")
            else:
                print(f"❌ 技能生成失败。")
        else:
            print(f"ℹ️ 暂无新技能建议。")
