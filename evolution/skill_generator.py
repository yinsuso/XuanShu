import os
import ast
import subprocess
import sys
from typing import Optional, Tuple
from logger import logger
from config import PROJECT_ROOT
from .evolution.reflection import Reflection
from skills import get_skill_filepath, load_skills

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
            
            if dirname not in sys.path:
                sys.path.insert(0, dirname)
            
            test_code = f"""
import {module_name}
print("导入成功")
"""
            
            result = subprocess.run(
                [sys.executable, "-c", test_code],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=PROJECT_ROOT
            )
            
            if result.returncode == 0:
                return True, "测试通过"
            else:
                return False, f"导入测试失败: {result.stderr}"
        except Exception as e:
            return False, f"测试错误: {e}"


class SkillGenerator:
    def __init__(self):
        self.skill_count = 0
        self.validator = SkillValidator()
    
    def get_generation_prompt(self, reflection: Reflection) -> str:
        prompt = f"""基于以下复盘分析，生成一个新的Python技能函数。

复盘信息:
- 任务总结: {reflection.task_summary}
- 技能想法: {reflection.skill_idea}

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
    """技能函数文档"""
    try:
        # 实现代码
        result = f"处理: {param1}, {param2}"
        return result
    except Exception as e:
        return f"错误: {e}"
```

请只返回Python代码，不要其他解释。"""
        return prompt
def skill_function(param1: str, param2: int = 0) -> str:
    \"\"\"技能函数文档\"\"\"
    try:
        # 实现代码
        result = f"处理: {param1}, {param2}"
        return result
    except Exception as e:
        return f"错误: {{e}}"
```

请只返回Python代码，不要其他解释。"""
        return prompt
    
    def generate_and_save(
        self,
        reflection: Reflection,
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
            import re
            match = re.search(r'@skill\s*\(\s*name\s*=\s*['"]([^'"]+)['\"]', code)
            skill_name = match.group(1) if match else None
            existing_filepath = get_skill_filepath(skill_name) if skill_name else None

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
                    load_skills()
                    logger.info(f"技能升级成功: {skill_name}")
                    return True, existing_filepath, "技能升级成功"
                except Exception as e:
                    return False, None, f"升级失败: {e}"
            else:
                # 全新生成技能
                filepath = self.save_skill(reflection.skill_idea, code)
                if not filepath:
                    return False, None, "保存失败"
                is_valid, error = self.validator.test_import(filepath)
                if not is_valid:
                    os.remove(filepath)
                    return False, None, error
                load_skills()
                logger.info(f"新技能已生成并加载: {filepath}")
                return True, filepath, "生成成功"

        except Exception as e:
            return False, None, f"生成错误: {e}"
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