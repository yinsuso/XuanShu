"""
测试网络访问控制策略
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_check_network_policy():
    from skills.utils.net_utils import _check_network_policy
    
    # Blocked IP
    assert _check_network_policy("169.254.169.254") is False, "IP should be blocked"
    
    # Blocked domain
    assert _check_network_policy("metadata.google.internal") is False, "Domain should be blocked"
    
    # Whitelisted
    assert _check_network_policy("api.openai.com") is True, "Whitelisted should be allowed"
    
    # Nonexistent, default deny
    assert _check_network_policy("example.com") is False, "Default deny should block"
    
    print("✅ Network policy checks passed")

def run_tests():
    test_check_network_policy()

if __name__ == "__main__":
    run_tests()
