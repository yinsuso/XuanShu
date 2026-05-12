"""
防火墙风险扫描器
负责对技能调用进行风险评估，确定风险等级，
低/中危自动放行，高危/临界触发人工审批。
"""
import re
from typing import List, Dict, Any
from logger import get_logger

logger = get_logger("security.firewall.scanner")


class FirewallScanner:
    """
    防火墙风险扫描器
    扫描技能调用，识别潜在危险操作，分配风险等级。
    """

    # 高危模式（直接触发人工审批）
    HIGH_RISK_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"dd\s+if=/dev/(zero|random|mem)",
        r"mkfs\s+/dev/",
        r":\(\)\{ :\| :& \};:",  # fork炸弹
        r"chmod\s+777\s+/",
        r"chown\s+-R\s+\w+:\w+\s+/etc",
        r"sudo\s+",
        r"su\s+",
        r"passwd\s+",
        r"visudo\s+",
        r"mount\s+",
        r"umount\s+",
        r"reboot\s+",
        r"shutdown\s+",
        r"halt\s+",
        r"poweroff\s+",
        r"kill\s+-9\s+1\s*",  # 杀init/systemd进程
    ]

    # 中危模式（记录日志但自动放行）
    MEDIUM_RISK_PATTERNS = [
        r"curl\s+",
        r"wget\s+",
        r"nc\s+",
        r"telnet\s+",
        r"ping\s+",
        r"nslookup\s+",
        r"dig\s+",
        r"netstat\s+",
        r"ss\s+",
        r"ps\s+",
        r"top\s+",
        r"htop\s+",
        r"kill\s+",
        r"pkill\s+",
        r"systemctl\s+",
        r"service\s+",
    ]

    # 关键路径模式
    SENSITIVE_PATH_PATTERNS = [
        r"/etc/passwd",
        r"/etc/shadow",
        r"/etc/ssh/",
        r"/root/",
        r"/home/\w+/.ssh/",
        r"~/.ssh/",
        r"/proc/self/fd/",
    ]

    def __init__(self):
        """初始化扫描器，预编译所有正则表达式"""
        self._high_regexes = [re.compile(p, re.IGNORECASE) for p in self.HIGH_RISK_PATTERNS]
        self._medium_regexes = [re.compile(p, re.IGNORECASE) for p in self.MEDIUM_RISK_PATTERNS]
        self._path_regexes = [re.compile(p, re.IGNORECASE) for p in self.SENSITIVE_PATH_PATTERNS]
        logger.info("防火墙风险扫描器初始化完成")

    def _scan_content(self, content: str) -> Dict[str, Any]:
        """扫描单个内容字符串，返回风险信息"""
        risk_level = "low"
        reasons = []

        # 检查高危模式
        for idx, regex in enumerate(self._high_regexes):
            if regex.search(content):
                risk_level = "critical"
                reasons.append(f"检测到高危操作模式 #{idx+1}")

        # 检查中危模式
        for idx, regex in enumerate(self._medium_regexes):
            if regex.search(content):
                if risk_level != "critical":
                    risk_level = "medium"
                reasons.append(f"检测到中危网络/系统操作 #{idx+1}")

        # 检查敏感路径
        for idx, regex in enumerate(self._path_regexes):
            if regex.search(content):
                if risk_level == "low":
                    risk_level = "medium"
                reasons.append(f"检测到敏感文件路径 #{idx+1}")

        return {
            "risk_level": risk_level,
            "reasons": reasons,
        }

    def scan(self, skill_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        扫描技能调用，评估整体风险等级

        Args:
            skill_name: 技能名称
            args: 技能参数字典

        Returns:
            {
                "risk_level": str,  # low/medium/high/critical
                "reasons": list,    # 风险原因列表
            }
        """
        risk_level = "low"
        reasons = []

        # 扫描技能名称本身
        name_result = self._scan_content(skill_name)
        if name_result["risk_level"] != "low":
            risk_level = name_result["risk_level"]
            reasons.extend(name_result["reasons"])

        # 递归扫描所有参数值
        def recursive_scan(value: Any):
            nonlocal risk_level, reasons
            if isinstance(value, str):
                r = self._scan_content(value)
                if r["risk_level"] == "critical" and risk_level not in ("critical",):
                    risk_level = "critical"
                elif r["risk_level"] == "high" and risk_level not in ("critical", "high"):
                    risk_level = "high"
                elif r["risk_level"] == "medium" and risk_level == "low":
                    risk_level = "medium"
                reasons.extend(r["reasons"])
            elif isinstance(value, dict):
                for v in value.values():
                    recursive_scan(v)
            elif isinstance(value, list):
                for v in value:
                    recursive_scan(v)

        recursive_scan(args)

        # 最终决策：高危及以上触发人工审批
        if risk_level in ("critical", "high"):
            logger.warning(
                "高危技能调用触发审批",
                details={
                    "skill": skill_name,
                    "risk_level": risk_level,
                    "reasons": reasons,
                }
            )

        return {
            "risk_level": risk_level,
            "reasons": reasons,
        }
