import os
import ast
import subprocess
import sys
import re
from typing import Optional, Tuple
from logger import logger
from config import PROJECT_ROOT

try:
    from evolution.reflection import Reflection
except ImportError:
    Reflection = None

AUTO_SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills", "auto_generated")
os.makedirs(AUTO_SKILLS_DIR, exist_ok=True)

INIT_FILE = os.path.join(AUTO_SKILLS_DIR, "__init__.py")
if not os.path.exists(INIT_FILE):
    with open(INIT_FILE, 'w', encoding='utf-8') as f:
        f.write("")


class SkillValidator:
    """技能验证器"""

    @staticmethod
    def validate_syntax(code: str) -> Tuple[bool, str]:
        """验证Python语法"""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        except Exception as e:
            return False, f"解析错误: {e}"

    @staticmethod
    def validate_skill_structure(code: str) -> Tuple[bool, str]:
        """验证技能结构"""
        try:
            tree = ast.parse(code)
            has_skill_decorator = False
            has_function = False

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    has_function = True
                if isinstance(node, ast.Call):
                    if hasattr(node.func, 'id') and node.func.id == 'skill':
                        has_skill_decorator = True
                    elif hasattr(node.func, 'attr') and node.func.attr == 'skill':
                        has_skill_decorator = True

            if not has_function:
                return False, "缺少函数定义"
            if not has_skill_decorator:
                return False, "缺少@skill装饰器"

            return True, ""
        except Exception as e:
            return False, f"结构验证错误: {e}"

    @staticmethod
    def test_import(filepath: str) -> Tuple[bool, str]:
        """测试导入技能"""
        try:
            dirname = os.path.dirname(filepath)
            filename = os.path.basename(filepath)
            module_name = os.path.splitext(filename)[0]

            test_code = f"""
import sys
sys.path.insert(0, r'{dirname}')
sys.path.insert(0, r'{PROJECT_ROOT}')
import {module_name}
print("ok")
"""

            result = subprocess.run(
                [sys.executable, "-c", test_code],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                cwd=PROJECT_ROOT
            )

            if result.returncode == 0:
                return True, "测试通过"
            else:
                err = result.stderr or "未知错误"
                return False, f"导入测试失败: {err}"
        except Exception as e:
            return False, f"测试错误: {e}"


class SkillGenerator:
    def __init__(self):
        self.skill_count = 0
        self.validator = SkillValidator()

    def get_generation_prompt(self, reflection) -> str:
        if reflection is None:
            task_summary = "用户自定义技能"
            skill_idea = "根据用户需求生成技能"
        else:
            task_summary = getattr(reflection, 'task_summary', '自动复盘技能')
            skill_idea = getattr(reflection, 'skill_idea', '根据复盘生成技能')

        prompt = f"""基于以下复盘分析，生成一个新的Python技能函数。

复盘信息:
- 任务总结: {task_summary}
- 技能想法: {skill_idea}

请生成一个完整的Python技能文件，包含:
1. 必要的导入：from skills.base import skill, SkillCategory（注意：必须使用绝对导入）
2. 使用@skill装饰器注册技能
3. 完整的函数实现
4. 参数定义和文档字符串
5. 适当的错误处理
6. 命名规范：
   - 技能名称（name）必须使用英文小写 snake_case 格式（如 quick_calc）
   - 长度不超过30字符
   - 仅包含小写字母、数字、下划线
   - 禁止使用中文、标点、空格

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

请只返回Python代码，不要其他解释。"""
        return prompt

    def generate_and_save(
        self,
        reflection,
        code: str
    ) -> Tuple[bool, Optional[str], str]:
        """生成、验证并保存技能，支持技能升级"""
        try:
            code = self._extract_code(code)

            # 验证语法
            is_valid, error = self.validator.validate_syntax(code)
            if not is_valid:
                return False, None, error

            # 验证技能结构
            is_valid, error = self.validator.validate_skill_structure(code)
            if not is_valid:
                return False, None, error

            # 尝试提取技能名称
            match = re.search(r'@skill\s*\(\s*name\s*=\s*[\'"]([^\'"]+)[\'"]', code)
            skill_name = match.group(1) if match else None

            # 检查是否已存在同名技能
            existing_filepath = None
            if skill_name:
                from skills import _skill_filepaths
                existing_filepath = _skill_filepaths.get(skill_name)

            if existing_filepath:
                # 升级现有技能
                try:
                    # 备份原文件
                    with open(existing_filepath, 'r', encoding='utf-8') as f:
                        original_code = f.read()
                    # 写入新代码
                    with open(existing_filepath, 'w', encoding='utf-8') as f:
                        f.write(code)
                    # 测试导入
                    is_valid, error = self.validator.test_import(existing_filepath)
                    if not is_valid:
                        # 恢复原文件
                        with open(existing_filepath, 'w', encoding='utf-8') as f:
                            f.write(original_code)
                        return False, None, f"升级失败: {error}"
                    # 重新加载技能
                    from skills import load_skills
                    load_skills()
                    logger.info(f"技能升级成功: {skill_name}")
                    return True, existing_filepath, "技能升级成功"
                except Exception as e:
                    return False, None, f"升级失败: {e}"
            else:
                # 全新生成技能
                skill_idea = getattr(reflection, 'skill_idea', 'new_skill') if reflection else 'new_skill'
                filepath = self.save_skill(skill_idea, code)
                if not filepath:
                    return False, None, "保存失败"
                is_valid, error = self.validator.test_import(filepath)
                if not is_valid:
                    os.remove(filepath)
                    return False, None, error
                from skills import load_skills
                load_skills()
                logger.info(f"新技能已生成并加载: {filepath}")

                # 触发技能同步到集群（如果处于协作模式）
                self._sync_skill_to_cluster(skill_name, code)

                return True, filepath, "生成成功"

        except Exception as e:
            return False, None, f"生成错误: {e}"

    def _sync_skill_to_cluster(self, skill_name: str, skill_code: str):
        """
        将新生成的技能同步到协作集群中的所有节点

        Args:
            skill_name: 技能名称
            skill_code: 技能完整 Python 代码
        """
        try:
            # 尝试获取集群管理器
            import sys
            cluster_manager = None

            # 从 web_app 模块获取全局集群管理器
            for mod_name, mod in sys.modules.items():
                if 'web_app' in mod_name and hasattr(mod, 'app'):
                    app = getattr(mod, 'app', None)
                    if app and hasattr(app, 'state'):
                        cluster_manager = getattr(app.state, 'cluster_manager', None)
                        break

            if cluster_manager and hasattr(cluster_manager, 'broadcast_skill_sync'):
                # 获取当前节点ID
                node_id = None
                if hasattr(cluster_manager, 'own_node') and cluster_manager.own_node:
                    node_id = cluster_manager.own_node.node_id

                cluster_manager.broadcast_skill_sync(skill_name, skill_code, generated_by=node_id)
                logger.info(f"[SkillGenerator] 技能 '{skill_name}' 已触发集群同步")
            else:
                logger.debug("[SkillGenerator] 未检测到集群管理器，跳过技能同步")
        except Exception as e:
            logger.warning(f"[SkillGenerator] 技能同步到集群失败: {e}")

    def _extract_code(self, text: str) -> str:
        """从文本中提取代码"""
        if "```python" in text:
            start = text.find("```python") + len("```python")
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        if "```" in text:
            start = text.find("```") + len("```")
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        return text.strip()

    def save_skill(self, skill_name: str, code: str) -> Optional[str]:
        try:
            safe_name = "".join(c if c.isalnum() or c in '_-' else '_' for c in skill_name)
            safe_name = safe_name.lower().replace('-', '_')
            filename = f"auto_{safe_name}_{self.skill_count}.py"
            filepath = os.path.join(AUTO_SKILLS_DIR, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code)

            self.skill_count += 1
            logger.info(f"自动生成的技能已保存: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"保存技能失败: {e}")
            return None
