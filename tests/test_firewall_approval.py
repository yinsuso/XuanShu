"""
测试防火墙扫描与审批机制
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_firewall_scanner():
    from security.firewall.scanner import FirewallScanner
    scanner = FirewallScanner()
    
    # Critical pattern
    result = scanner.scan("python_exec", {"code": "rm -rf /"})
    assert result["risk_level"] == "critical", f"Expected critical, got {result['risk_level']}"
    
    # High pattern
    result = scanner.scan("shell_exec", {"cmd": "sudo apt-get update"})
    assert result["risk_level"] == "high", f"Expected high, got {result['risk_level']}"
    
    # Medium pattern
    result = scanner.scan("shell_exec", {"cmd": "wget http://example.com"})
    assert result["risk_level"] == "medium", f"Expected medium, got {result['risk_level']}"
    
    # Low pattern (no dangerous)
    result = scanner.scan("python_exec", {"code": "print('hello')"})
    assert result["risk_level"] == "low", f"Expected low, got {result['risk_level']}"
    
    print("✅ FirewallScanner tests passed")

def test_approval_manager():
    from security.firewall.approval import ApprovalManager
    mgr = ApprovalManager()
    
    # Critical should be denied
    decision = mgr.request("python_exec", {"code": "rm -rf /"})
    assert decision["allowed"] is False, "Critical should be denied"
    assert "风险" in decision["message"] or "阻止" in decision["message"]
    
    # High should be denied
    decision = mgr.request("python_exec", {"code": "__import__('os').system('ls')"})
    assert decision["allowed"] is False, "High should be denied"
    
    # Medium should be allowed (auto)
    decision = mgr.request("python_exec", {"code": "import subprocess; subprocess.run(['ls'])"})
    assert decision["allowed"] is True, "Medium should be allowed"
    
    # Low should be allowed
    decision = mgr.request("python_exec", {"code": "print('test')"})
    assert decision["allowed"] is True, "Low should be allowed"
    
    print("✅ ApprovalManager tests passed")

def run_tests():
    test_firewall_scanner()
    test_approval_manager()

if __name__ == "__main__":
    run_tests()
