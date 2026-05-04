"""
审批管理器
负责风险扫描与审批流程协作（与 Web 界面联动）。
"""
import requests
import time
from config import WEB_APP_URL, APPROVAL_TIMEOUT, APPROVAL_POLL_INTERVAL, APPROVAL_API_TOKEN
from .scanner import FirewallScanner
from logger import get_logger

logger = get_logger("security.approval")

class ApprovalManager:
    def __init__(self):
        self.scanner = FirewallScanner()

    def request(self, skill_name: str, args: dict) -> dict:
        """
        请求审批。若风险为 low/medium 则自动放行；
        若为 high/critical 则通过 Web 审批队列等待人工决定。
        返回结构：{
            "allowed": bool,
            "risk_level": str,
            "reasons": list,
            "message": str
        }
        """
        scan_result = self.scanner.scan(skill_name, args)
        risk_level = scan_result["risk_level"]
        reasons = scan_result["reasons"]

        # 低、中危自动放行
        if risk_level in ("low", "medium"):
            return {"allowed": True, "risk_level": risk_level, "reasons": reasons, "message": ""}

        # 高危及以上需要人工审批
        try:
            headers = {"Content-Type": "application/json"}
            if APPROVAL_API_TOKEN:
                headers["X-Approval-Token"] = APPROVAL_API_TOKEN
            payload = {"skill_name": skill_name, "args": args, "risk_level": risk_level}
            # 提交审批请求
            resp = requests.post(
                f"{WEB_APP_URL}/api/approvals/create",
                json=payload,
                headers=headers,
                timeout=10
            )
            if resp.status_code != 200:
                logger.error("审批请求提交失败", status=resp.status_code, body=resp.text)
                return {
                    "allowed": False,
                    "risk_level": risk_level,
                    "reasons": reasons,
                    "message": f"审批提交失败（{resp.status_code}）"
                }
            data = resp.json()
            approval_id = data.get("approval_id")
            if not approval_id:
                return {
                    "allowed": False,
                    "risk_level": risk_level,
                    "reasons": reasons,
                    "message": "审批响应无效（缺少approval_id）"
                }

            # 轮询等待审批结果
            start = time.time()
            while time.time() - start < APPROVAL_TIMEOUT:
                time.sleep(APPROVAL_POLL_INTERVAL)
                try:
                    resp2 = requests.get(
                        f"{WEB_APP_URL}/api/approvals/{approval_id}/status",
                        headers=headers,
                        timeout=10
                    )
                    if resp2.status_code == 200:
                        status_data = resp2.json()
                        if status_data.get("status") == "decided":
                            decision = status_data.get("decision")
                            allowed = (decision == "approve")
                            msg = "" if allowed else "审批被拒绝"
                            logger.info("审批完成", approval_id=approval_id, decision=decision)
                            return {"allowed": allowed, "risk_level": risk_level, "reasons": reasons, "message": msg}
                except Exception as e:
                    logger.warning("轮询审批状态异常", error=str(e))
                    # 继续重试
                    pass
            # 超时
            return {
                "allowed": False,
                "risk_level": risk_level,
                "reasons": reasons,
                "message": f"审批超时（{APPROVAL_TIMEOUT}s）"
            }
        except Exception as e:
            logger.exception("审批过程异常")
            return {
                "allowed": False,
                "risk_level": risk_level,
                "reasons": reasons,
                "message": f"审批异常：{str(e)}"
            }
