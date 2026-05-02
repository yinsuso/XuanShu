# 技能系统文档 - 参考Hermes Agent设计

## 📦 简介

这是一个完整的技能系统，参考了 **Hermes Agent** 的设计风格，包含：
- 模块化的技能注册
- 自动参数推断
- 技能分类管理
- OpenAI Function Calling 兼容的Schema
- 装饰器快速开发

## 🚀 快速开始

### 启动命令

```bash
# 启动命令行界面（推荐）
python start_skill_agent.py --cli

# 启动Web界面
python start_skill_agent.py --web

# 启用向量记忆
python start_skill_agent.py --cli --vector
```

或者直接使用：
```bash
# 新版SkillAgent（推荐）
python agent_skill.py

# 原版Agent（兼容）
python agent.py
```

## 📁 目录结构

```
local-agent/
├── skills/                      # 技能系统目录
│   ├── __init__.py             # 包入口
│   ├── base.py                 # 基类和注册表
│   ├── decorators.py           # 装饰器
│   ├── loader.py               # 技能加载器
│   ├── file_skills.py          # 文件操作技能
│   ├── code_skills.py          # 代码执行技能
│   ├── search_skills.py        # 搜索技能
│   ├── utility_skills.py       # 实用工具技能
│   └── example_custom_skill.py # 自定义示例技能
├── agent_skill.py              # 新版SkillAgent
└── start_skill_agent.py        # 统一启动脚本
```

## 🛠️ 内置技能列表

### 📁 文件操作 (file_operation)

| 技能名 | 描述 |
|--------|------|
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件内容 |
| `edit_file` | 编辑文件：替换指定内容 |
| `list_dir` | 列出目录内容 |
| `file_exists` | 检查文件或目录是否存在 |
| `get_file_info` | 获取文件详细信息 |

### 💻 代码执行 (code_execution)

| 技能名 | 描述 | 需确认 |
|--------|------|--------|
| `run_code` | 执行Python代码 | ✅ |
| `eval_expression` | 计算Python表达式 | ❌ |

### 🔍 搜索 (search)

| 技能名 | 描述 |
|--------|------|
| `web_search` | 搜索网络信息 |
| `search_images` | 搜索图片 |

### 🛠️ 实用工具 (utility)

| 技能名 | 描述 |
|--------|------|
| `get_time` | 获取当前时间 |
| `calculate` | 简单计算：支持 +, -, *, / |
| `random_number` | 生成随机数 |
| `countdown` | 倒计时（秒） |
| `convert_units` | 单位转换:支持长度、重量 |

### ✨ 自定义示例 (custom)

| 技能名 | 描述 |
|--------|------|
| `hello_world` | 问候用户的示例技能 |
| `joke` | 讲笑话 |
| `mood_check` | 检查心情如何 |

## 🔧 开发自定义技能

### 方法1: 使用装饰器（推荐）

```python
from skills import skill, SkillCategory
from skills.decorators import log_execution


@skill(
    name="my_skill",
    description="我的技能描述",
    category=SkillCategory.CUSTOM,
    requires_confirmation=False
)
@log_execution
def my_skill(param1: str, param2: int = 10) -> str:
    """技能函数文档
    参数会自动从类型注解推断
    """
    result = f"参数1: {param1}, 参数2: {param2}"
    return result
```

### 方法2: 继承基类（高级）

```python
from skills import Skill, SkillCategory, SkillMetadata, Parameter


class MySkill(Skill):
    metadata = SkillMetadata(
        name="my_advanced_skill",
        description="高级技能描述",
        category=SkillCategory.CUSTOM
    )

    parameters = [
        Parameter(name="input_str", type="string", description="输入字符串", required=True),
        Parameter(name="option", type="integer", description="选项", required=False, default=0)
    ]

    def execute(self, input_str: str, option: int = 0) -> str:
        return f"执行结果: {input_str}, option={option}"
```

### 加载自定义技能

```python
from skills import registry

# 方式1: 放在skills目录，自动加载
# 文件名: skills/my_skill.py

# 方式2: 从文件动态加载
from skills.loader import loader
loader.load_from_file("path/to/my_skill.py")

# 方式3: 手动注册
registry.register(MySkill())
```

## 📊 技能分类

```python
class SkillCategory(Enum):
    FILE_OPERATION = "file_operation"    # 文件操作
    CODE_EXECUTION = "code_execution"    # 代码执行
    SEARCH = "search"                    # 搜索
    SYSTEM = "system"                    # 系统操作
    UTILITY = "utility"                  # 实用工具
    CUSTOM = "custom"                    # 自定义
```

## 🎯 技能Schema（OpenAI兼容）

所有技能会自动生成 OpenAI Function Calling 兼容的 Schema：

```json
{
  "type": "function",
  "function": {
    "name": "skill_name",
    "description": "技能描述",
    "parameters": {
      "type": "object",
      "properties": {
        "param1": {
          "type": "string",
          "description": "参数说明"
        }
      },
      "required": ["param1"]
    }
  }
}
```

## 🛡️ 安全特性

### 需要用户确认的技能

使用 `requires_confirmation=True` 标记的技能在执行前会要求用户确认：

```python
@skill(
    name="dangerous_skill",
    description="这个技能需要确认",
    requires_confirmation=True
)
def dangerous_skill():
    pass
```

### 执行次数限制

在 `config.py` 中配置 `MAX_CODE_EXECUTIONS` 限制高风险技能的执行次数。

## 📝 使用示例

### 命令行交互

```
居士请吩咐: 列出当前目录
🧠 思考中...
🛠️  执行技能: list_dir
📊 结果:
📁 __pycache__
📄 agent.py
📁 web
...
```

### 运行代码

```
居士请吩咐: 计算 10 的阶乘
🧠 思考中...
🛠️  执行技能: run_code
⚠️  执行技能 'run_code'
是否确认? (y/n): y
📊 结果: 3628800
```

## 🔍 API接口

### SkillAgent类

```python
from agent_skill import SkillAgent

agent = SkillAgent(
    use_vector_memory=False,  # 向量记忆
    auto_load_skills=True,     # 自动加载技能
    load_examples=False         # 加载示例技能
)

response = agent.process("你好")
print(response)

agent.run()  # 交互模式
```

### 技能注册表

```python
from skills import registry

# 获取所有技能
skills = registry.get_all()

# 获取技能
skill = registry.get("read_file")

# 获取OpenAI schemas
schemas = registry.get_openai_schemas()

# 按分类获取
from skills import SkillCategory
file_skills = registry.get_by_category(SkillCategory.FILE_OPERATION)

# 列出所有技能
registry.list_skills()
```

## 🎨 装饰器参考

| 装饰器 | 描述 |
|--------|------|
| `@tool()` | 快速注册为技能 |
| `@skill()` | 完整技能装饰器 |
| `@log_execution` | 记录执行日志 |
| `@require_confirmation` | 要求用户确认 |
| `@with_metadata` | 添加版本和作者信息 |

## 📖 参考设计

本系统参考了以下开源项目的设计理念：
- **Hermes Agent** - NousResearch
- **LangChain** - LangChainAI
- **OpenAI Function Calling** - OpenAI

## 🚀 下一步计划

- [ ] 向量数据库集成（ChromaDB/Pinecone）
- [ ] 技能执行历史与学习
- [ ] 多Agent协作
- [ ] Web界面技能管理面板
- [ ] 技能市场与分享
