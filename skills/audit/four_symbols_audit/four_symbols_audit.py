"""
四象审计技能。
在开发/修改代码时自动执行四象审计（青龙-环境、白虎-代码、朱雀-验证、玄武-沟通）。
Author: 破执
Date: 2026-05-15
"""

import os
import sys
import ast
import platform
from pathlib import Path
from typing import List, Tuple, Dict

from logger import get_logger

logger = get_logger('four_symbols_audit')

# 技能元数据
SKILL_NAME = "four_symbols_audit"
SKILL_DESCRIPTION = "四象审计：在开发/修改代码时执行环境、代码、验证、沟通四维审计。"
SKILL_TRIGGER = "在编写、修改或审查代码时，执行四象审计确保代码质量和安全性。"
SKILL_CATEGORY = "audit"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "file_path",
        "type": "string",
        "description": "要审计的文件路径"
    },
    {
        "name": "audit_type",
        "type": "string",
        "description": "审计类型: all(全部), qinglong(青龙-环境), baihu(白虎-代码), zhuque(朱雀-验证), xuanwu(玄武-沟通)",
        "default": "all"
    }
]


class FourSymbolsAuditor:
    """四象审计器。"""

    def __init__(self, file_path: str):
        self.file_path = os.path.abspath(file_path)
        self.issues: List[Dict] = []
        self.content = ""
        self.lines = []
        self.ast_tree = None

    def load(self) -> bool:
        """加载文件内容。"""
        if not os.path.exists(self.file_path):
            self.issues.append({
                "symbol": "青龙",
                "level": "致命",
                "message": f"文件不存在: {self.file_path}"
            })
            return False

        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                self.content = f.read()
                self.lines = self.content.split("\n")
        except Exception as e:
            self.issues.append({
                "symbol": "青龙",
                "level": "致命",
                "message": f"无法读取文件: {str(e)}"
            })
            return False

        # 尝试解析 AST
        if self.file_path.endswith(".py"):
            try:
                self.ast_tree = ast.parse(self.content)
            except SyntaxError as e:
                self.issues.append({
                    "symbol": "白虎",
                    "level": "致命",
                    "message": f"语法错误 第{e.lineno}行: {e.msg}",
                    "line": e.lineno
                })
                return False

        return True

    def audit_qinglong(self) -> List[Dict]:
        """
        青龙审计 - 环境审计。
        检查运行环境、路径、依赖等。
        """
        issues = []

        # 检查硬编码路径
        hardcoded_paths = [
            "/usr/local", "/opt/", "/www/", "/home/",
            "C:\\", "D:\\", "E:\\", "J:\\",
            "/var/log", "/etc/"
        ]

        for i, line in enumerate(self.lines, 1):
            for path in hardcoded_paths:
                if path in line and not line.strip().startswith("#"):
                    # 排除注释和字符串中的合法使用
                    stripped = line.strip()
                    if "expanduser" in stripped or "expandvars" in stripped:
                        continue
                    if "os.path.join" in stripped or "os.path.abspath" in stripped:
                        continue
                    issues.append({
                        "symbol": "青龙",
                        "level": "警告",
                        "message": f"可能存在硬编码路径: {path}",
                        "line": i,
                        "suggestion": "使用 os.path.join() 或 Path 构建路径，避免硬编码"
                    })
                    break

        # 检查平台相关代码是否兼容
        if "platform.system()" not in self.content and ("win32" in self.content or "linux" in self.content):
            issues.append({
                "symbol": "青龙",
                "level": "提示",
                "message": "检测到平台判断代码，建议统一使用 platform.system() 或 sys.platform",
                "suggestion": "使用 platform.system() 获取平台信息"
            })

        # 检查环境变量读取
        if "os.environ" in self.content and "os.getenv" not in self.content:
            issues.append({
                "symbol": "青龙",
                "level": "提示",
                "message": "使用 os.environ 直接访问环境变量，建议使用 os.getenv() 提供默认值",
                "suggestion": "os.environ['KEY'] → os.getenv('KEY', 'default')"
            })

        return issues

    def audit_baihu(self) -> List[Dict]:
        """
        白虎审计 - 代码审计。
        检查代码质量、安全问题、规范遵循等。
        """
        issues = []

        if not self.file_path.endswith(".py"):
            issues.append({
                "symbol": "白虎",
                "level": "提示",
                "message": "非 Python 文件，跳过 AST 代码审计"
            })
            return issues

        # 缩进检查
        indent_issues = self._check_indentation()
        issues.extend(indent_issues)

        # AST 遍历检查
        if self.ast_tree:
            for node in ast.walk(self.ast_tree):
                # 检查 eval/exec
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ("eval", "exec"):
                            issues.append({
                                "symbol": "白虎",
                                "level": "高危",
                                "message": f"发现 {node.func.id}() 调用，存在代码注入风险",
                                "line": getattr(node, "lineno", 0),
                                "suggestion": "使用 ast.literal_eval() 替代 eval()，或实现安全的表达式解析"
                            })

                # 检查 subprocess shell=True
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "run":
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append({
                                    "symbol": "白虎",
                                    "level": "高危",
                                    "message": "subprocess.run(shell=True) 存在命令注入风险",
                                    "line": getattr(node, "lineno", 0),
                                    "suggestion": "使用 shell=False 并传入列表参数"
                                })

                # 检查硬编码密钥
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    val = node.value.lower()
                    if any(k in val for k in ["password", "secret", "token", "api_key", "apikey"]):
                        if len(node.value) > 8 and not node.value.startswith("$"):
                            issues.append({
                                "symbol": "白虎",
                                "level": "高危",
                                "message": "发现可能的硬编码密钥/密码",
                                "line": getattr(node, "lineno", 0),
                                "suggestion": "使用环境变量或配置文件存储敏感信息"
                            })

                # 检查裸 except
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        issues.append({
                            "symbol": "白虎",
                            "level": "中危",
                            "message": "使用裸 except: 会捕获所有异常包括 KeyboardInterrupt",
                            "line": getattr(node, "lineno", 0),
                            "suggestion": "使用 except Exception: 或更具体的异常类型"
                        })

        # 检查 import 规范
        import_lines = []
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append((i, stripped))

        # 检查是否有未使用的 import（简单检查）
        for i, imp in import_lines:
            module = imp.replace("import ", "").replace("from ", "").split()[0].split(".")[0]
            if module not in ("os", "sys", "typing", "json", "re", "logging"):
                # 简单检查是否在代码中使用
                usage_count = sum(1 for l in self.lines if module in l)
                if usage_count <= 1:  # 只有 import 那一行
                    issues.append({
                        "symbol": "白虎",
                        "level": "提示",
                        "message": f"可能的未使用导入: {module}",
                        "line": i,
                        "suggestion": "删除未使用的导入，或使用 __all__ 明确导出"
                    })

        return issues

    def _check_indentation(self) -> List[Dict]:
        """检查缩进问题。"""
        issues = []
        has_tab = False
        has_space = False

        for i, line in enumerate(self.lines, 1):
            if "\t" in line:
                has_tab = True
            if "    " in line:
                has_space = True

        if has_tab and has_space:
            issues.append({
                "symbol": "白虎",
                "level": "中危",
                "message": "缩进混用 Tab 和空格，可能导致 Python 缩进错误",
                "suggestion": "统一使用 4 个空格缩进"
            })
        elif has_tab and not has_space:
            issues.append({
                "symbol": "白虎",
                "level": "提示",
                "message": "使用 Tab 缩进，建议统一为 4 个空格",
                "suggestion": "将 Tab 替换为 4 个空格"
            })

        return issues

    def audit_zhuque(self) -> List[Dict]:
        """
        朱雀审计 - 验证审计。
        检查测试覆盖、运行验证等。
        """
        issues = []

        # 检查是否有测试相关代码
        has_test = any("test" in l.lower() for l in self.lines if not l.strip().startswith("#"))
        has_assert = "assert " in self.content
        has_main = 'if __name__ == "__main__"' in self.content

        if not has_test and not has_assert and self.file_path.endswith(".py"):
            # 检查是否是主模块（非测试文件）
            basename = os.path.basename(self.file_path)
            if not basename.startswith("test_") and not basename.endswith("_test.py"):
                issues.append({
                    "symbol": "朱雀",
                    "level": "提示",
                    "message": "未检测到测试代码或断言，建议添加单元测试",
                    "suggestion": "添加测试用例或使用 if __name__ == '__main__': 进行基本验证"
                })

        # 检查是否有运行验证入口
        if not has_main and self.file_path.endswith(".py"):
            issues.append({
                "symbol": "朱雀",
                "level": "提示",
                "message": "缺少 if __name__ == '__main__': 入口，不利于独立验证",
                "suggestion": "添加主入口用于快速验证模块功能"
            })

        # 检查文件大小
        file_size = os.path.getsize(self.file_path)
        if file_size > 100 * 1024:  # 100KB
            issues.append({
                "symbol": "朱雀",
                "level": "提示",
                "message": f"文件较大 ({file_size / 1024:.1f} KB)，建议拆分为多个模块",
                "suggestion": "按功能拆分大文件，提高可维护性"
            })

        return issues

    def audit_xuanwu(self) -> List[Dict]:
        """
        玄武审计 - 沟通审计。
        检查文档、注释、日志等。
        """
        issues = []

        # 检查文件头注释
        has_docstring = '"""' in self.content or "'''" in self.content
        has_module_doc = False

        if self.lines:
            first_lines = "\n".join(self.lines[:5])
            if '"""' in first_lines or "'''" in first_lines:
                has_module_doc = True

        if not has_module_doc and self.file_path.endswith(".py"):
            issues.append({
                "symbol": "玄武",
                "level": "提示",
                "message": "缺少模块文档字符串（docstring）",
                "suggestion": "在文件开头添加模块说明文档字符串"
            })

        # 检查关键函数是否有文档
        if self.ast_tree:
            for node in ast.walk(self.ast_tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not ast.get_docstring(node):
                        func_name = node.name
                        if not func_name.startswith("_") and len(node.body) > 3:
                            issues.append({
                                "symbol": "玄武",
                                "level": "提示",
                                "message": f"函数 '{func_name}' 缺少文档字符串",
                                "line": node.lineno,
                                "suggestion": f"为 {func_name} 添加文档字符串说明功能和参数"
                            })

        # 检查日志使用
        has_logging = "logger" in self.content or "logging" in self.content
        has_print = any(l.strip().startswith("print(") for l in self.lines)

        if has_print and not has_logging:
            issues.append({
                "symbol": "玄武",
                "level": "提示",
                "message": "使用 print() 输出信息，建议使用日志系统",
                "suggestion": "使用 logger.info/debug/error() 替代 print()"
            })

        # 检查 TODO/FIXME
        todos = []
        for i, line in enumerate(self.lines, 1):
            upper = line.upper()
            if "TODO" in upper or "FIXME" in upper or "HACK" in upper:
                todos.append((i, line.strip()))

        if todos:
            issues.append({
                "symbol": "玄武",
                "level": "提示",
                "message": f"发现 {len(todos)} 处待办/修复标记",
                "suggestion": "尽快处理 TODO/FIXME，或记录到技术债清单"
            })
            for line_no, text in todos[:3]:
                issues.append({
                    "symbol": "玄武",
                    "level": "信息",
                    "message": f"  第{line_no}行: {text[:60]}",
                    "line": line_no
                })

        return issues

    def run_audit(self, audit_type: str = "all") -> str:
        """执行审计。"""
        if not self.load():
            return self._format_report()

        # 执行各象审计
        if audit_type in ("all", "qinglong"):
            self.issues.extend(self.audit_qinglong())

        if audit_type in ("all", "baihu"):
            self.issues.extend(self.audit_baihu())

        if audit_type in ("all", "zhuque"):
            self.issues.extend(self.audit_zhuque())

        if audit_type in ("all", "xuanwu"):
            self.issues.extend(self.audit_xuanwu())

        return self._format_report()

    def _format_report(self) -> str:
        """格式化审计报告。"""
        if not self.issues:
            return f"✅ 四象审计通过\n文件: {self.file_path}\n未发现明显问题。"

        # 按级别统计
        levels = {"致命": 0, "高危": 0, "中危": 0, "警告": 0, "提示": 0, "信息": 0}
        symbols = {"青龙": 0, "白虎": 0, "朱雀": 0, "玄武": 0}

        for issue in self.issues:
            levels[issue.get("level", "提示")] += 1
            symbols[issue.get("symbol", "未知")] += 1

        # 生成报告
        report = f"📋 四象审计报告\n"
        report += f"文件: {self.file_path}\n"
        report += f"问题总数: {len(self.issues)}\n\n"

        # 摘要
        report += "【摘要】\n"
        for symbol, count in symbols.items():
            if count > 0:
                report += f"  {symbol}: {count} 项\n"

        report += "\n【级别分布】\n"
        for level, count in levels.items():
            if count > 0:
                emoji = {"致命": "💀", "高危": "🔴", "中危": "🟠", "警告": "🟡", "提示": "🔵", "信息": "⚪"}.get(level, "")
                report += f"  {emoji} {level}: {count}\n"

        # 详细问题
        report += "\n【详细问题】\n"
        for i, issue in enumerate(self.issues, 1):
            symbol = issue.get("symbol", "未知")
            level = issue.get("level", "提示")
            message = issue.get("message", "")
            line = issue.get("line", "")
            suggestion = issue.get("suggestion", "")

            line_info = f" 第{line}行" if line else ""
            report += f"\n{i}. [{symbol}] {level}{line_info}\n"
            report += f"   {message}\n"
            if suggestion:
                report += f"   💡 建议: {suggestion}\n"

        # 结论
        fatal = levels.get("致命", 0)
        high = levels.get("高危", 0)
        medium = levels.get("中危", 0)

        if fatal > 0:
            report += f"\n❌ 审计未通过：发现 {fatal} 个致命问题，必须修复后才能提交。"
        elif high > 0:
            report += f"\n⚠️ 审计警告：发现 {high} 个高危问题，建议修复后再提交。"
        elif medium > 0:
            report += f"\n⚠️ 审计提示：发现 {medium} 个中危问题，建议关注。"
        else:
            report += f"\n✅ 审计基本通过：未发现严重问题，但仍有优化空间。"

        return report


def execute(file_path: str, audit_type: str = "all", **kwargs) -> str:
    """
    执行四象审计。

    Args:
        file_path: 要审计的文件路径
        audit_type: 审计类型
        **kwargs: 额外参数（忽略）

    Returns:
        审计报告
    """
    if not file_path or not file_path.strip():
        return "❌ 请提供 file_path 参数"

    audit_type = audit_type.lower().strip()
    valid_types = ("all", "qinglong", "baihu", "zhuque", "xuanwu")

    if audit_type not in valid_types:
        return (
            f"❌ 不支持的审计类型: {audit_type}\n"
            f"支持的类型: all(全部), qinglong(青龙-环境), baihu(白虎-代码), "
            f"zhuque(朱雀-验证), xuanwu(玄武-沟通)"
        )

    auditor = FourSymbolsAuditor(file_path.strip())
    return auditor.run_audit(audit_type)
