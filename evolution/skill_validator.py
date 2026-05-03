import ast
import re
from typing import Tuple, Any

class SkillValidator:
    """增强的技能验证器，遵循玄枢系统完整规范。"""

    def validate_syntax(self, code: str) -> Tuple[bool, Any]:
        """基础语法检查（编译）。"""
        try:
            compile(code, '<skill>', 'exec')
            return True, None
        except Exception as e:
            return False, str(e)

    def validate_skill_structure(self, code: str) -> Tuple[bool, str]:
        """综合结构验证：装饰器、命名、导入、函数签名、文档字符串、错误处理。"""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"

        func_node = None
        skill_name = None

        # 查找第一个使用 @skill 装饰的函数
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == 'skill':
                        kwargs = {kw.arg: kw.value for kw in dec.keywords}
                        # 必需参数检查
                        for req in ('name', 'description', 'category'):
                            if req not in kwargs:
                                return False, f"缺少必需装饰器参数: {req}"
                        # 提取 skill name
                        name_node = kwargs['name']
                        if isinstance(name_node, ast.Str):
                            skill_name = name_node.s
                        elif isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
                            skill_name = name_node.value
                        else:
                            return False, "skill name 必须是字符串字面量"
                        # description 也应为字符串（仅检查类型）
                        desc_node = kwargs['description']
                        if not (isinstance(desc_node, (ast.Str, ast.Constant))):
                            return False, "skill description 必须是字符串字面量"
                        func_node = node
                        break
                if func_node:
                    break

        if not func_node:
            return False, "未找到使用 @skill 装饰的函数"

        # 2. 命名规范（英文 snake_case，长度 ≤30，仅允许 a-z0-9_）
        if skill_name:
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,29}', skill_name):
                return False, f"技能名称不符合规范: {skill_name} (需英文小写 snake_case，≤30 字符，仅允许 a-z0-9_)"

        # 3. 导入检查：必须包含 from skills.base import skill, SkillCategory
        if not self._check_imports(tree):
            return False, "缺少正确导入: 必须 `from skills.base import skill, SkillCategory`"

        # 4. 类型标注：所有参数和返回值必须有类型注解
        if not self._check_type_hints(func_node):
            return False, "函数参数或返回值缺少类型标注"

        # 5. 文档字符串
        if not ast.get_docstring(func_node):
            return False, "函数缺少文档字符串"

        # 6. 错误处理：至少一个 try/except
        if not self._has_try_except(func_node):
            return False, "函数缺少错误处理 (try/except)"

        return True, ""

    def _check_imports(self, tree: ast.AST) -> bool:
        """验证是否从 skills.base 导入了 skill 和 SkillCategory。"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == 'skills.base':
                    names = [alias.name for alias in node.names]
                    if 'skill' in names and 'SkillCategory' in names:
                        return True
        return False

    def _check_type_hints(self, func_node: ast.FunctionDef) -> bool:
        """检查所有参数和返回值的类型标注。"""
        # 参数
        for arg in func_node.args.args:
            if arg.annotation is None:
                return False
        # 返回类型
        if func_node.returns is None:
            return False
        return True

    def _has_try_except(self, func_node: ast.FunctionDef) -> bool:
        """检查函数体内是否存在 try 语句。"""
        for stmt in ast.walk(func_node):
            if isinstance(stmt, ast.Try):
                return True
        return False
