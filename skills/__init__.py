"""
技能注册表与加载器。
统一加载所有技能，提供技能注册、查询、执行接口。
Author: Hermes Agent (Refactored)
Date: 2026-04-30
"""

import os
import importlib.util
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

def _load_skill_from_file(file_path: str) -> Optional[Skill]:
    """从文件加载技能。"""
    try:
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 检查必需属性
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
__all__ = ['registry', 'load_skills', 'get_skill', 'list_skills', 'get_openai_schemas']