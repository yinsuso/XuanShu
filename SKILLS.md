# 玄枢项目技能系统开发规范

## 1. 概述
玄枢项目的技能系统采用 Python 函数装饰器方式注册，每个技能独立文件，具备自描述元数据，便于动态加载、版本管理和自动化验证。

## 2. 命名规则
- 使用英文小写 `snake_case` 格式
- 仅允许字符：a-z, 0-9, _
- 长度 ≤ 30 字符
- 示例：`quick_calc`, `web_search`, `data_analyzer`
- 禁止：中文、大写、连字符、空格、标点

## 3. 技能标准
每个技能文件必须满足：

### 3.1 导入规范
```python
from skills.base import skill, SkillCategory
```
必须使用绝对导入，不得使用相对导入（如 `from .base import`）。

### 3.2 装饰器元数据
使用 `@skill` 装饰器，参数包括：
- `name` (str): 技能标识，符合命名规则
- `description` (str): 简短描述，≤100 字
- `category` (SkillCategory): 引用 `SkillCategory` 枚举
- `version` (str): 版本，语义化版本如 "1.0.0"
- `author` (str, optional): 作者
- `requires_confirmation` (bool, default=False): 是否需要用户确认执行
- `deprecated` (bool, default=False): 是否已废弃

### 3.3 函数定义
- 参数需类型标注（可包含默认值）
- 返回值必须类型标注
- 必须包含文档字符串（docstring）说明功能、参数、返回值
- 函数名建议为明确的动词（如 `fetch`, `calc`）

### 3.4 错误处理与日志
- 使用 `try/except` 捕获异常
- 记录错误日志 `logger.error(...)` 并返回用户友好的错误信息
- 避免未处理的异常导致 Agent 崩溃

### 3.5 文件结构
```
skills/
├── __init__.py
├── base.py
└── your_skill.py
```

## 4. 实现步骤
1. 在 `skills/` 目录下创建 `.py` 文件（可子目录）
2. 编写导入、装饰器和函数
3. 保存后重启服务或动态加载
4. 使用 `skill_validator` 验证：
   ```bash
   python -m evolution.skill_validator
   ```
5. 通过 `list_skills()` 查看注册情况

## 5. 使用方式
Agent 通过技能名称调用：
```python
result = skill_registry.get('your_skill')(*args)
```
在对话中，大模型会根据用户意图自动选择技能并调用。

## 6. 完整示例
### 技能：快速计算器

**文件：** `skills/quick_calc.py`

```python
from skills.base import skill, SkillCategory
import logging

logger = logging.getLogger(__name__)

@skill(
    name="quick_calc",
    description="执行快速算术运算：支持加减乘除、幂运算",
    category=SkillCategory.UTILITY,
    version="1.0.0",
    author="玄枢团队",
    requires_confirmation=False
)
def calculate(expression: str) -> str:
    """计算一个数学表达式并返回结果。

    参数:
      expression (str): 数学表达式字符串，例如 "2 + 3 * 4"

    返回:
      str: 计算结果或错误信息
    """
    try:
        # 安全检查：只允许数字、运算符和小数点
        allowed = set("0123456789.+-*/() ")
        if not all(c in allowed for c in expression):
            return "❌ 表达式包含非法字符"
        # 使用 eval（生产环境建议使用 ast 或解析器）
        result = eval(expression, {"__builtins__": None}, {})
        return f"🧮 结果: {result}"
    except Exception as e:
        logger.error(f"计算失败: {expression}, 错误: {e}")
        return f"⚠️ 计算错误: {e}"
```

## 7. 调试与测试
- 启用开发模式：在配置中设置 `development_mode = True`
- 查看日志：`logs/agent.log` 或控制台输出
- 测试调用：
  ```bash
  curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message":"用 quick_calc 计算 12*12"}'
  ```
- 验证语法：`python -m py_compile skills/quick_calc.py`

## 8. 升级与兼容
- 修改后递增 `version`
- 尽量保持参数向后兼容
- 废弃功能标记 `deprecated=True`，保留至少一个版本周期

## 9. 密钥与安全
- 敏感信息（API keys）必须通过环境变量或配置管理读取
  ```python
  import os
  api_key = os.getenv("OPENAI_API_KEY")
  ```
- 禁止在代码中硬编码密钥
- 使用 `config_manager` 加密存储（如适用）

## 10. 常见问题 (FAQ)
- **Q: 技能未被加载？**  
  A: 检查语法错误、装饰器参数、导入路径；查看启动日志。

- **Q: 如何调试？**  
  A: 查看 `logs/skills.log`，确保 `SkillValidator` 通过。

- **Q: 如何删除/禁用技能？**  
  A: 删除文件后重启，或标记 `deprecated=True`。

- **Q: 命名冲突怎么办？**  
  A: 系统拒绝重复名称，请更名。

## 11. 与 Hermes Agent 对照
本规范参考 Hermes Agent 的 skill 设计：
- 使用 `@skill` 装饰器作为注册机制
- 通过元数据实现自描述
- 强调错误处理与日志
- 支持动态加载与验证

不同的是，玄枢采用简单文件结构、无 SKILL.md 文件，但可以通过 docstring 提供丰富文档。

---
**最后更新：** 2026-04-17
**维护者：** 玄枢开发团队
