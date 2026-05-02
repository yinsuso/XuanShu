"""
技能系统基类
参考Hermes Agent的设计风格
"""
import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Type, get_type_hints, Tuple
from enum import Enum
from functools import wraps

from logger import logger


class SkillCategory(Enum):
    """技能分类"""
    FILE_OPERATION = "file_operation"    # 文件操作
    CODE_EXECUTION = "code_execution"    # 代码执行
    CODE_ANALYSIS = "code_analysis"      # 代码分析
    SEARCH = "search"                    # 搜索
    SYSTEM = "system"                    # 系统操作
    UTILITY = "utility"                  # 实用工具
    CUSTOM = "custom"                    # 自定义


@dataclass
class Parameter:
    """参数定义"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: List[Any] = field(default_factory=list)

    def to_schema(self) -> Dict[str, Any]:
        """转换为JSON Schema"""
        schema = {
            "type": self.type,
            "description": self.description
        }
        if self.default is not None:
            schema["default"] = self.default
        if self.enum:
            schema["enum"] = self.enum
        return schema


@dataclass
class SkillMetadata:
    """技能元数据"""
    name: str
    description: str
    category: SkillCategory
    version: str = "1.0.0"
    author: str = "Local Agent"
    requires_confirmation: bool = False
    deprecated: bool = False


class Skill(ABC):
    """
    技能基类
    参考Hermes Agent的Skill设计
    """

    # 子类可以覆盖这些
    metadata: SkillMetadata = None
    parameters: List[Parameter] = field(default_factory=list)

    def __init__(self):
        if self.metadata is None:
            raise ValueError("Skill必须定义metadata")

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        执行技能
        子类必须实现这个方法
        """
        pass

    def validate_parameters(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证参数"""
        for param in self.parameters:
            if param.required and param.name not in params:
                return False, f"缺少必需参数: {param.name}"

            if param.name in params:
                # 简单类型验证
                value = params[param.name]
                if param.enum and value not in param.enum:
                    return False, f"参数 {param.name} 必须是以下之一: {param.enum}"

        return True, None

    def to_openai_schema(self) -> Dict[str, Any]:
        """
        转换为OpenAI Function Calling格式
        兼容OpenAI/Anthropic等模型
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }


class FunctionSkill(Skill):
    """
    函数包装技能
    允许使用装饰器快速将函数转换为技能
    """

    def __init__(self, func: Callable, metadata: SkillMetadata, parameters: List[Parameter]):
        self.func = func
        self.metadata = metadata
        self.parameters = parameters
        super().__init__()

    def execute(self, **kwargs) -> str:
        """执行包装的函数"""
        try:
            result = self.func(**kwargs)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"技能执行失败: {self.metadata.name} - {e}")
            return f"错误: {str(e)}"


class SkillRegistry:
    """
    技能注册表
    参考Hermes Agent的skill manager设计
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: Dict[str, Skill] = {}
            cls._instance._categories: Dict[SkillCategory, List[str]] = {}
        return cls._instance

    def register(self, skill: Skill) -> None:
        """注册技能"""
        name = skill.metadata.name
        self._skills[name] = skill

        category = skill.metadata.category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(name)

        logger.info(f"技能已注册: {name} ({category.value})")

    def register_function(
        self,
        func: Callable,
        name: str,
        description: str,
        category: SkillCategory = SkillCategory.UTILITY,
        requires_confirmation: bool = False
    ) -> FunctionSkill:
        """
        从函数注册技能
        自动推断参数类型
        """
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = type_hints.get(param_name, str)
            type_str = self._get_type_str(param_type)
            required = param.default == inspect.Parameter.empty
            default = param.default if not required else None

            parameters.append(Parameter(
                name=param_name,
                type=type_str,
                description=f"参数: {param_name}",
                required=required,
                default=default
            ))

        metadata = SkillMetadata(
            name=name,
            description=description,
            category=category,
            requires_confirmation=requires_confirmation
        )

        skill = FunctionSkill(func, metadata, parameters)
        self.register(skill)
        return skill

    def _get_type_str(self, type_obj: Type) -> str:
        """获取类型字符串"""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        return type_map.get(type_obj, "string")

    def get(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self._skills.get(name)

    def get_all(self) -> List[Skill]:
        """获取所有技能"""
        return list(self._skills.values())

    def get_by_category(self, category: SkillCategory) -> List[Skill]:
        """按分类获取技能"""
        names = self._categories.get(category, [])
        return [self._skills[name] for name in names if name in self._skills]

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """获取所有技能的OpenAI Function Calling schema"""
        return [skill.to_openai_schema() for skill in self._skills.values()]

    def list_skills(self) -> List[Dict[str, str]]:
        """列出所有技能"""
        return [
            {
                "name": s.metadata.name,
                "description": s.metadata.description,
                "category": s.metadata.category.value,
                "version": s.metadata.version,
                "requires_confirmation": s.metadata.requires_confirmation
            }
            for s in self._skills.values()
        ]

    def clear(self) -> None:
        """清空注册表"""
        self._skills.clear()
        self._categories.clear()
        logger.info("技能注册表已清空")


# 全局注册表实例
registry = SkillRegistry()


def skill(
    name: str,
    description: str,
    category: SkillCategory = SkillCategory.UTILITY,
    requires_confirmation: bool = False
):
    """
    技能装饰器
    参考Hermes Agent的装饰器风格
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        registry.register_function(
            func=wrapper,
            name=name,
            description=description,
            category=category,
            requires_confirmation=requires_confirmation
        )
        return wrapper

    return decorator