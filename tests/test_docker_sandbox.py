"""
测试 Docker 沙箱模块
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_docker_sandbox_instantiation():
    from security.sandbox.docker_sandbox import DockerSandbox
    sandbox = DockerSandbox()
    assert sandbox is not None
    available = sandbox.is_available()
    assert isinstance(available, bool)
    print(f"✅ DockerSandbox instantiated, available={available}")

def run_tests():
    test_docker_sandbox_instantiation()

if __name__ == "__main__":
    run_tests()
