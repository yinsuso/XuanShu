"""
技能注册表与加载器。
统一加载所有技能，提供技能注册、查询、执行接口。
支持两种技能格式：
  1. 旧格式：SKILL_NAME 等全局变量 + execute 函数
  2. 新格式：@skill 装饰器（来自 skills.base）
Author: 破执
Date: 2026-04-30
"""

import os
import sys
import importlib.util
import inspect
from typing import Dict, List, Any, Optional

# 技能注册表
_skills_registry: Dict[str, dict] = {}
_skill_filepaths: Dict[str, str] = {}


class SkillMetadata:
    """技能元数据结构。"""
    def __init__(self, name: str, description: str, trigger: str, category: str,
                 requires_confirmation: bool, parameters: List[dict]):
        self.name = name
        self.description = description
        self.trigger = trigger
        self.category = category
        self.requires_confirmation = requires_confirmation
        self.parameters = parameters


class Skill:
    """技能封装类。"""
    def __init__(self, name: str, execute_func, metadata: SkillMetadata):
        self.name = name
        self.execute_func = execute_func
        self.metadata = metadata

    def execute(self, **kwargs) -> str:
        """执行技能。"""
        return self.execute_func(**kwargs)


def _load_skill_legacy(module, file_path: str) -> Optional[Skill]:
    """加载旧格式技能（SKILL_NAME 等全局变量）。"""
    required_attrs = ['SKILL_NAME', 'SKILL_DESCRIPTION', 'SKILL_TRIGGER',
                     'SKILL_CATEGORY', 'SKILL_REQUIRES_CONFIRMATION', 'SKILL_PARAMETERS', 'execute']
    for attr in required_attrs:
        if not hasattr(module, attr):
            return None

    metadata = SkillMetadata(
        name=module.SKILL_NAME,
        description=module.SKILL_DESCRIPTION,
        trigger=module.SKILL_TRIGGER,
        category=module.SKILL_CATEGORY,
        requires_confirmation=module.SKILL_REQUIRES_CONFIRMATION,
        parameters=module.SKILL_PARAMETERS
    )

    skill = Skill(
        name=module.SKILL_NAME,
        execute_func=module.execute,
        metadata=metadata
    )
    return skill


def _load_skill_decorator(module, file_path: str) -> Optional[Skill]:
    """加载新格式技能（@skill 装饰器，来自 skills.base）。"""
    try:
        # 检查模块是否通过 @skill 装饰器注册了技能
        # skills.base 中的 @skill 装饰器会将技能注册到 base_registry
        from skills.base import base_registry

        # 获取该模块中通过装饰器注册的所有函数
        registered_skills = []
        for skill_obj in base_registry.get_all():
            # 检查这个技能是否来自当前模块
            if hasattr(skill_obj, 'func') and hasattr(skill_obj.func, '__module__'):
                if skill_obj.func.__module__ == module.__name__:
                    registered_skills.append(skill_obj)

        if not registered_skills:
            return None

        # 取第一个注册的技能（通常一个文件只有一个）
        skill_obj = registered_skills[0]
        metadata = skill_obj.metadata

        # 构建参数列表
        sig = inspect.signature(skill_obj.func)
        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            param_type = 'string'
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = 'integer'
                elif param.annotation == float:
                    param_type = 'number'
                elif param.annotation == bool:
                    param_type = 'boolean'
                elif param.annotation == list:
                    param_type = 'array'
                elif param.annotation == dict:
                    param_type = 'object'

            param_info = {
                'name': param_name,
                'type': param_type,
                'description': f'参数: {param_name}'
            }
            if param.default != inspect.Parameter.empty:
                param_info['default'] = param.default
            parameters.append(param_info)

        skill_metadata = SkillMetadata(
            name=metadata.name,
            description=metadata.description,
            trigger=f"当需要 {metadata.description} 时使用",
            category=metadata.category.value if hasattr(metadata.category, 'value') else str(metadata.category),
            requires_confirmation=metadata.requires_confirmation,
            parameters=parameters
        )

        skill = Skill(
            name=metadata.name,
            execute_func=skill_obj.func,
            metadata=skill_metadata
        )
        return skill

    except Exception as e:
        print(f"加载装饰器格式技能失败 {file_path}: {e}")
        return None


def _load_skill_from_file(file_path: str) -> Optional[Skill]:
    """从文件加载技能，自动检测格式。"""
    try:
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)

        # 确保 skills.base 已导入（装饰器格式需要）
        try:
            import skills.base
        except ImportError:
            pass

        spec.loader.exec_module(module)

        # 先尝试加载旧格式
        skill = _load_skill_legacy(module, file_path)
        if skill:
            return skill

        # 再尝试加载新格式（@skill 装饰器）
        skill = _load_skill_decorator(module, file_path)
        if skill:
            return skill

        return None

    except Exception as e:
        print(f"加载技能失败 {file_path}: {e}")
        return None


def load_skills(base_dir: str = None) -> List[str]:
    """
    加载所有技能。

    Args:
        base_dir: 技能目录路径，默认为当前目录下的 skills

    Returns:
        加载的技能名称列表
    """
    global _skills_registry
    _skills_registry.clear()

    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    loaded_skills = []

    # 遍历所有子目录
    for root, dirs, files in os.walk(base_dir):
        # 跳过 __pycache__
        dirs[:] = [d for d in dirs if d != '__pycache__']

        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                file_path = os.path.join(root, file)
                skill = _load_skill_from_file(file_path)
                if skill:
                    _skills_registry[skill.name] = {
                        'skill': skill,
                        'metadata': skill.metadata
                    }
                    _skill_filepaths[skill.name] = file_path
                    loaded_skills.append(skill.name)

    print(f"✅ 已加载 {len(loaded_skills)} 个技能：{', '.join(loaded_skills)}")
    return loaded_skills


def get_skill(name: str) -> Optional[Skill]:
    """获取指定技能。"""
    global _skills_registry
    if name in _skills_registry:
        return _skills_registry[name]['skill']
    return None


def list_skills() -> List[dict]:
    """列出所有技能信息。"""
    global _skills_registry
    return [
        {
            'name': info['metadata'].name,
            'description': info['metadata'].description,
            'category': info['metadata'].category,
            'requires_confirmation': info['metadata'].requires_confirmation
        }
        for info in _skills_registry.values()
    ]


def get_openai_schemas() -> List[dict]:
    """获取 OpenAI 风格的技能 Schema 列表。"""
    global _skills_registry
    schemas = []
    for info in _skills_registry.values():
        schema = {
            'function': {
                'name': info['metadata'].name,
                'description': info['metadata'].description,
                'parameters': {
                    'type': 'object',
                    'properties': {
                        p['name']: {
                            'type': p['type'],
                            'description': p['description']
                        }
                        for p in info['metadata'].parameters
                    },
                    'required': [p['name'] for p in info['metadata'].parameters if 'default' not in p]
                }
            }
        }
        schemas.append(schema)
    return schemas


def unload_skill(name: str) -> bool:
    """
    卸载指定技能。
    从所有注册表中彻底移除，包括 _skills_registry、_skill_filepaths 和 base_registry。

    Args:
        name: 技能名称

    Returns:
        是否成功卸载
    """
    global _skills_registry, _skill_filepaths
    found = False

    if name in _skills_registry:
        del _skills_registry[name]
        found = True

    if name in _skill_filepaths:
        del _skill_filepaths[name]
        found = True

    # 同时清理 skills.base 中的 base_registry（装饰器注册的技能）
    try:
        from skills.base import base_registry
        if name in base_registry._skills:
            del base_registry._skills[name]
            # 清理分类索引
            for cat, names in list(base_registry._categories.items()):
                if name in names:
                    names.remove(name)
                    if not names:
                        del base_registry._categories[cat]
                    break
            found = True
    except Exception:
        pass

    if found:
        print(f"✅ 已卸载技能：{name}")
        return True
    return False


def clear_skills() -> None:
    """清空所有已加载技能。"""
    global _skills_registry, _skill_filepaths
    _skills_registry.clear()
    _skill_filepaths.clear()
    print("✅ 已清空所有技能")


# 自动加载
load_skills()


# --- 兼容性导出：为了兼容旧版 agent.py 中的 `from skills import registry` ---
# 创建一个伪 registry 对象，提供旧版接口
class _LegacyRegistry:
    """伪注册表对象，提供旧版接口以兼容 agent.py。"""

    def get_all(self):
        """返回所有技能对象列表。"""
        global _skills_registry
        return [info['skill'] for info in _skills_registry.values()]

    def get_openai_schemas(self):
        """返回 OpenAI 风格的技能 Schema 列表。"""
        return get_openai_schemas()

    def get(self, name):
        """获取指定技能。"""
        return get_skill(name)

    def list_skills(self):
        """列出所有技能信息（兼容 web_app.py 调用）。"""
        return list_skills()


# 导出 registry 对象
registry = _LegacyRegistry()

# 同时导出其他常用函数（兼容旧版）
__all__ = ['registry', 'load_skills', 'get_skill', 'list_skills', 'get_openai_schemas', 'unload_skill', 'clear_skills']
