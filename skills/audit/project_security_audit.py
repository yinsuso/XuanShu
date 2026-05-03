#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目安全审计技能 - 倒推审查 + 网络安全攻防

功能：
- 从前端开始审计，向后端追溯
- 检查 API 端点完整性
- 分析核心依赖链
- 执行安全攻防推敲
- 生成详细审计报告

Author: Hermes Agent (基于四象协作流程)
Date: 2026-05-03
"""

import os
import json
import re
import ast
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime

# 技能元数据（必须）
SKILL_NAME = "project_security_audit"
SKILL_DESCRIPTION = "系统化审计项目的前后端一致性、安全漏洞与代码质量。采用倒推审查机制和网络安全攻防推敲，适用于大型项目全面审计。"
SKILL_TRIGGER = "当需要对大型项目进行全面安全审计、前后端一致性验证或代码安全审查时使用。"
SKILL_CATEGORY = "system"  # system, audit, security
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "project_root",
        "type": "string",
        "description": "项目根目录绝对路径",
        "required": True
    },
    {
        "name": "output_format",
        "type": "string",
        "description": "输出格式：markdown 或 json",
        "required": False,
        "default": "markdown",
        "enum": ["markdown", "json"]
    },
    {
        "name": "audit_scope",
        "type": "array",
        "description": "审计范围：frontend, backend, security, dependencies, all",
        "required": False,
        "default": ["all"]
    }
]


def execute(project_root: str, output_format: str = "markdown", audit_scope: List[str] = None) -> str:
    """
    执行项目安全审计
    
    Args:
        project_root: 项目根目录
        output_format: 输出格式 (markdown/json)
        audit_scope: 审计范围列表，默认 ["all"]
    
    Returns:
        审计报告（Markdown 或 JSON）
    """
    if audit_scope is None:
        audit_scope = ["all"]
    
    # 确保路径存在
    root_path = Path(project_root).resolve()
    if not root_path.exists():
        return f"❌ 项目目录不存在: {project_root}"
    
    # 初始化审计报告
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "project_root": str(root_path),
        "audit_scope": audit_scope,
        "frontend_analysis": {},
        "backend_analysis": {},
        "security_assessment": {},
        "dependency_check": {},
        "issues_found": [],
        "recommendations": []
    }
    
    print(f"🔍 开始项目安全审计: {root_path}")
    
    # 执行各阶段审计
    try:
        _audit_frontend(report, root_path)
    except Exception as e:
        report["frontend_analysis"]["error"] = str(e)
    
    try:
        _audit_backend(report, root_path)
    except Exception as e:
        report["backend_analysis"]["error"] = str(e)
    
    try:
        _audit_security(report, root_path)
    except Exception as e:
        report["security_assessment"]["error"] = str(e)
    
    try:
        _audit_dependencies(report, root_path)
    except Exception as e:
        report["dependency_check"]["error"] = str(e)
    
    # 汇总问题与建议
    _summarize_issues(report)
    
    # 输出报告
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    else:
        return _generate_markdown_report(report)


def _audit_frontend(report: Dict, root_path: Path):
    """审计前端页面与API映射"""
    print("  📄 审计前端...")
    
    web_dir = root_path / "web"
    if not web_dir.exists():
        report["frontend_analysis"]["status"] = "no_web_directory"
        return
    
    # 扫描前端文件
    templates_dir = web_dir / "templates"
    static_dir = web_dir / "static"
    
    frontend_files = {}
    api_calls = set()
    
    # 分析 HTML 模板
    if templates_dir.exists():
        for html_file in templates_dir.glob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            frontend_files[str(html_file)] = {
                "size": html_file.stat().st_size,
                "type": "html"
            }
            # 提取 API 调用（从 script src 或 fetch）
            api_calls.update(_extract_api_calls(content))
    
    # 分析 JavaScript
    js_apis = set()
    if static_dir.exists():
        for js_file in static_dir.rglob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            frontend_files[str(js_file)] = {
                "size": js_file.stat().st_size,
                "type": "javascript"
            }
            js_apis.update(_extract_api_calls(content))
    
    api_calls.update(js_apis)
    
    report["frontend_analysis"] = {
        "web_directory": str(web_dir),
        "total_files": len(frontend_files),
        "files": frontend_files,
        "api_endpoints_used": list(api_calls),
        "pages_detected": _detect_pages(frontend_files)
    }


def _extract_api_calls(content: str) -> Set[str]:
    """从文本中提取 API 调用端点"""
    apis = set()
    
    # fetch('/api/xxx')
    fetch_pattern = r"fetch\(['\"](\/api\/[a-zA-Z0-9_\-=\/]+)['\"]"
    apis.update(re.findall(fetch_pattern, content))
    
    # axios.post('/api/xxx')
    axios_pattern = r"axios\.(?:post|get|put|delete)\(['\"](\/api\/[a-zA-Z0-9_\-=\/]+)['\"]"
    apis.update(re.findall(axios_pattern, content))
    
    # 直接 URL 引用
    url_pattern = r"['\"](\/api\/[a-zA-Z0-9_\-=\/]+)['\"]"
    apis.update(re.findall(url_pattern, content))
    
    return apis


def _detect_pages(frontend_files: Dict) -> List[str]:
    """检测前端页面"""
    pages = []
    for filepath, info in frontend_files.items():
        if info["type"] == "html":
            pages.append(Path(filepath).name)
    return pages


def _audit_backend(report: Dict, root_path: Path):
    """审计后端 API 实现"""
    print("  🔧 审计后端...")
    
    # 查找主应用文件
    app_files = []
    for pattern in ["app.py", "web_app.py", "main.py", "server.py", "api.py"]:
        candidate = root_path / pattern
        if candidate.exists():
            app_files.append(str(candidate))
    
    # 也可能在 application 包内
    for py_file in root_path.rglob("*.py"):
        if py_file.name.startswith("app") or py_file.name.startswith("server"):
            if str(py_file) not in app_files:
                app_files.append(str(py_file))
    
    if not app_files:
        report["backend_analysis"] = {"status": "no_app_files_found"}
        return
    
    # 分析 API 端点
    api_endpoints = {}
    for app_file in app_files:
        try:
            content = Path(app_file).read_text(encoding="utf-8")
            endpoints = _extract_api_endpoints(content)
            if endpoints:
                api_endpoints[app_file] = endpoints
        except Exception as e:
            pass
    
    report["backend_analysis"] = {
        "app_files": app_files,
        "api_endpoints_defined": api_endpoints,
        "total_endpoints": sum(len(v) for v in api_endpoints.values())
    }


def _extract_api_endpoints(content: str) -> List[Dict]:
    """从 Python 代码中提取 FastAPI/Flask 路由"""
    endpoints = []
    
    # FastAPI 装饰器: @app.post("/api/xxx")
    fastapi_pattern = r'@app\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']\s*\)'
    for match in re.finditer(fastapi_pattern, content):
        method, path = match.groups()
        # 尝试获取下一个函数名
        func_match = re.search(r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content[match.end():match.end()+200])
        func_name = func_match.group(1) if func_match else "unknown"
        endpoints.append({
            "method": method.upper(),
            "path": path,
            "function": func_name
        })
    
    # Flask 装饰器: @app.route("/api/xxx", methods=['GET'])
    flask_pattern = r'@app\.route\s*\(\s*["\']([^"\']+)["\']\s*,\s*methods\s*=\s*\[([^\]]+)\]'
    for match in re.finditer(flask_pattern, content):
        path, methods_str = match.groups()
        methods = [m.strip().strip("'\"") for m in methods_str.split(',')]
        func_match = re.search(r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content[match.end():match.end()+200])
        func_name = func_match.group(1) if func_match else "unknown"
        endpoints.append({
            "method": ", ".join(methods),
            "path": path,
            "function": func_name
        })
    
    return endpoints


def _audit_security(report: Dict, root_path: Path):
    """网络安全攻防推敲"""
    print("  🛡️ 执行安全审计...")
    
    vulnerabilities = []
    recommendations = []
    
    # 1. 代码执行风险
    vuln_code_execution = _check_code_execution_risks(root_path)
    if vuln_code_execution:
        vulnerabilities.extend(vuln_code_execution)
    
    # 2. API 密钥泄露
    vuln_api_keys = _check_api_key_exposure(root_path)
    if vuln_api_keys:
        vulnerabilities.extend(vuln_api_keys)
    
    # 3. 路径遍历风险
    vuln_path_traversal = _check_path_traversal(root_path)
    if vuln_path_traversal:
        vulnerabilities.extend(vuln_path_traversal)
    
    # 4. 日志脱敏检查
    vuln_logging = _check_logging_sanitization(root_path)
    if vuln_logging:
        vulnerabilities.extend(vuln_logging)
    
    # 5. 速率限制缺失
    if not _check_rate_limiting(root_path):
        recommendations.append("Web API 需要添加速率限制以防止 DoS 攻击")
    
    report["security_assessment"] = {
        "vulnerabilities": vulnerabilities,
        "recommendations": recommendations,
        "risk_level": _calculate_risk_level(vulnerabilities)
    }


def _check_code_execution_risk_impact(root_path: Path) -> List[Dict]:
    """检查代码执行风险（技能、eval、subprocess等）"""
    risks = []
    
    # 扫描所有 Python 文件
    for py_file in root_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            
            # 检查危险函数
            dangerous_patterns = {
                "os.system": "使用 os.system 可能存在命令注入风险",
                "subprocess.run": "使用 subprocess 需确保参数来源可信",
                "subprocess.Popen": "使用 subprocess.Popen 需严格参数校验",
                "eval(": "使用 eval() 执行动态代码极度危险",
                "exec(": "使用 exec() 执行动态代码极度危险",
                "__import__": "动态导入模块可能绕过安全限制"
            }
            
            for pattern, description in dangerous_patterns.items():
                if pattern in content:
                    # 检查是否在技能系统中（允许但需沙箱）
                    location = "skill_system" if "skills" in str(py_file) else "core"
                    risks.append({
                        "file": str(py_file),
                        "pattern": pattern,
                        "description": description,
                        "location": location,
                        "severity": "critical" if pattern in ["eval(", "exec("] else "high"
                    })
        except Exception:
            continue
    
    return risks


def _check_api_key_exposure(root_path: Path) -> List[Dict]:
    """检查 API 密钥是否明文存储"""
    risks = []
    
    # 常见密钥文件名
    key_files = [
        "model_config.json",
        ".env",
        "secrets.json",
        "config.json"
    ]
    
    for key_file in key_files:
        path = root_path / "data" / key_file if "data" in str(root_path) else root_path / key_file
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # 检查是否包含密钥字段
            if "api_key" in content or "secret" in content.lower():
                # 进一步检查是否加密
                if "encrypted" not in content.lower():
                    risks.append({
                        "file": str(path),
                        "issue": "API 密钥明文存储",
                        "recommendation": "使用系统密钥库（Windows DPAPI / macOS Keychain / Linux Secret Service）加密存储",
                        "severity": "high"
                    })
    
    return risks


def _check_path_traversal(root_path: Path) -> List[Dict]:
    """检查路径遍历风险"""
    risks = []
    
    for py_file in root_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            
            # 检查文件操作函数是否参数校验
            file_ops = ["open(", "os.path.join", "Path(", "read_file", "write_file"]
            for op in file_ops:
                if op in content:
                    # 检查是否有路径校验
                    if "realpath" not in content and "abspath" not in content:
                        risks.append({
                            "file": str(py_file),
                            "pattern": op,
                            "issue": "文件操作可能缺乏路径校验，存在路径遍历风险",
                            "severity": "high"
                        })
        except Exception:
            continue
    
    return risks


def _check_logging_sanitization(root_path: Path) -> List[Dict]:
    """检查日志脱敏是否完整"""
    risks = []
    
    logger_file = root_path / "logger.py"
    if not logger_file.exists():
        return [{"issue": "未发现结构化日志系统", "severity": "medium"}]
    
    content = logger_file.read_text(encoding="utf-8")
    
    # 检查是否使用脱敏器
    if "masker" not in content and "mask" not in content:
        risks.append({
            "file": "logger.py",
            "issue": "日志系统未集成敏感信息脱敏",
            "recommendation": "集成 data_masker 对所有日志输出进行脱敏",
            "severity": "medium"
        })
    
    return risks


def _check_rate_limiting(root_path: Path) -> bool:
    """检查是否有限速机制"""
    # 简单的检查：搜索相关关键词
    for py_file in root_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            if "rate_limit" in content or "limiter" in content or "slowapi" in content:
                return True
        except Exception:
            continue
    return False


def _calculate_risk_level(vulnerabilities: List[Dict]) -> str:
    """计算整体风险等级"""
    if not vulnerabilities:
        return "low"
    
    critical = sum(1 for v in vulnerabilities if v.get("severity") == "critical")
    high = sum(1 for v in vulnerabilities if v.get("severity") == "high")
    
    if critical > 0:
        return "critical"
    elif high > 0:
        return "high"
    else:
        return "medium"


def _audit_dependencies(report: Dict, root_path: Path):
    """审计依赖导入关系"""
    print("  📦 审计依赖...")
    
    # 检查 requirements.txt / pyproject.toml
    req_files = list(root_path.glob("requirements*.txt")) + list(root_path.glob("pyproject.toml"))
    imports = set()
    circular_deps = []
    
    for req_file in req_files:
        try:
            if req_file.suffix == ".txt":
                with open(req_file, "r", encoding="utf-8") as f:
                    reqs = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            else:
                # pyproject.toml 简单解析（不完整）
                reqs = []  # TODO: 完整解析
        except Exception:
            continue
    
    # 分析 import 语句（简单分析）
    py_files = list(root_path.rglob("*.py"))
    for py_file in py_files[:50]:  # 限制数量避免过慢
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])
        except Exception:
            continue
    
    report["dependency_check"] = {
        "requirements_files": [str(f) for f in req_files],
        "detected_imports": list(imports)[:100],  # 限制长度
        "circular_dependencies": circular_deps
    }


def _summarize_issues(report: Dict):
    """汇总所有问题与建议"""
    all_issues = []
    
    # 从安全评估中提取问题
    vulnerabilities = report.get("security_assessment", {}).get("vulnerabilities", [])
    for vuln in vulnerabilities:
        all_issues.append({
            "category": "security",
            "severity": vuln.get("severity"),
            "description": vuln.get("issue") or vuln.get("pattern"),
            "file": vuln.get("file"),
            "recommendation": vuln.get("recommendation", "")
        })
    
    # 从后端分析中检查 API 端点缺失
    frontend_apis = set(report.get("frontend_analysis", {}).get("api_endpoints_used", []))
    backend_endpoints = set()
    for endpoints in report.get("backend_analysis", {}).get("api_endpoints_defined", {}).values():
        for ep in endpoints:
            backend_endpoints.add(ep["path"])
    
    missing_apis = frontend_apis - backend_endpoints
    for api in missing_apis:
        all_issues.append({
            "category": "compatibility",
            "severity": "high",
            "description": f"前端调用的 API {api} 在后端未实现",
            "recommendation": "在 web_app.py 中添加对应路由"
        })
    
    # 汇总建议
    recommendations = []
    recommendations.extend(report.get("security_assessment", {}).get("recommendations", []))
    
    report["issues_found"] = all_issues
    report["recommendations"] = recommendations


def _generate_markdown_report(report: Dict) -> str:
    """生成 Markdown 格式报告"""
    md = []
    md.append(f"# 🔍 项目安全审计报告")
    md.append(f"**生成时间**: {report['timestamp']}")
    md.append(f"**项目路径**: {report['project_root']}")
    md.append(f"**审计范围**: {', '.join(report['audit_scope'])}")
    md.append("")
    
    # 风险评估摘要
    risk_level = report.get("security_assessment", {}).get("risk_level", "unknown")
    risk_emoji = {"critical": "🔴", "high": "🟡", "medium": "🟠", "low": "🟢"}.get(risk_level, "⚪")
    md.append(f"## 📊 风险评估摘要")
    md.append(f"- **整体风险等级**: {risk_emoji} {risk_level.upper()}")
    md.append(f"- **发现问题总数**: {len(report.get('issues_found', []))}")
    md.append(f"- **前端文件数**: {report.get('frontend_analysis', {}).get('total_files', 0)}")
    md.append(f"- **API 端点总数**: {report.get('backend_analysis', {}).get('total_endpoints', 0)}")
    md.append("")
    
    # 前端分析
    if "frontend_analysis" in report and report["frontend_analysis"]:
        md.append("## 📄 前端分析")
        frontend = report["frontend_analysis"]
        md.append(f"- 前端目录: `{frontend.get('web_directory', 'N/A')}`")
        md.append(f"- 文件总数: {frontend.get('total_files', 0)}")
        
        pages = frontend.get("pages_detected", [])
        if pages:
            md.append("- 检测页面:")
            for page in pages:
                md.append(f"  - `{page}`")
        
        apis = frontend.get("api_endpoints_used", [])
        if apis:
            md.append("- 前端调用的 API:")
            for api in apis:
                md.append(f"  - `{api}`")
        md.append("")
    
    # 后端分析
    if "backend_analysis" in report and report["backend_analysis"]:
        md.append("## 🔧 后端分析")
        backend = report["backend_analysis"]
        md.append(f"- 应用文件: {', '.join([Path(f).name for f in backend.get('app_files', [])])}")
        md.append(f"- API 端点总数: {backend.get('total_endpoints', 0)}")
        
        endpoints = backend.get("api_endpoints_defined", {})
        if endpoints:
            md.append("- 已定义端点:")
            for file, eps in endpoints.items():
                file_name = Path(file).name
                for ep in eps:
                    md.append(f"  - `{ep['method']} {ep['path']}` → `{ep['function']}` (in {file_name})")
        md.append("")
    
    # 安全评估
    if "security_assessment" in report and report["security_assessment"]:
        md.append("## 🛡️ 安全评估")
        sec = report["security_assessment"]
        vulns = sec.get("vulnerabilities", [])
        
        if vulns:
            md.append("### 🔴 发现漏洞")
            for vuln in vulns:
                severity_icon = {"critical": "🔴", "high": "🟡", "medium": "🟠"}.get(vuln.get("severity"), "⚪")
                md.append(f"{severity_icon} **{vuln.get('pattern') or vuln.get('issue')}**")
                if "file" in vuln:
                    md.append(f"   - 文件: `{Path(vuln['file']).name}`")
                if "description" in vuln:
                    md.append(f"   - 描述: {vuln['description']}")
                if "recommendation" in vuln:
                    md.append(f"   - 修复建议: {vuln['recommendation']}")
                md.append("")
        else:
            md.append("✅ 未发现严重漏洞")
        
        recs = sec.get("recommendations", [])
        if recs:
            md.append("### 💡 安全建议")
            for rec in recs:
                md.append(f"- {rec}")
        md.append("")
    
    # 依赖检查
    if "dependency_check" in report and report["dependency_check"]:
        md.append("## 📦 依赖分析")
        dep = report["dependency_check"]
        req_files = dep.get("requirements_files", [])
        if req_files:
            md.append("- 依赖配置文件:")
            for f in req_files:
                md.append(f"  - `{Path(f).name}`")
        
        imports = dep.get("detected_imports", [])
        if imports:
            md.append(f"- 检测到的导入库 (前50): `{', '.join(list(imports)[:50])}`")
        md.append("")
    
    # 问题汇总
    if report.get("issues_found"):
        md.append("## 📝 问题汇总")
        for issue in report["issues_found"]:
            severity_icon = {"critical": "🔴", "high": "🟡", "medium": "🟠", "low": "🟢"}.get(issue["severity"], "⚪")
            md.append(f"{severity_icon} **{issue['description']}**")
            if issue.get("file"):
                md.append(f"   - 文件: `{Path(issue['file']).name}`")
            if issue.get("recommendation"):
                md.append(f"   - 建议: {issue['recommendation']}")
            md.append("")
    
    # 最终建议
    if report.get("recommendations"):
        md.append("## ✅ 建议行动计划")
        for i, rec in enumerate(report["recommendations"], 1):
            md.append(f"{i}. {rec}")
    
    md.append("---")
    md.append("*本报告由玄枢Agent自动生成，遵循四象协作标准流程。*")
    
    return "\n".join(md)
