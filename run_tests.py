#!/usr/bin/env python3
"""
玄枢安全模块测试运行器
生成测试报告
"""
import sys
import os
import time

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

test_modules = [
    "tests.test_docker_sandbox",
    "tests.test_firewall_approval",
    "tests.test_network_policy",
]

results = []
total_start = time.time()
for mod_name in test_modules:
    try:
        mod = __import__(mod_name, fromlist=["run_tests"])
        if hasattr(mod, "run_tests"):
            start = time.time()
            mod.run_tests()
            elapsed = time.time() - start
            results.append((mod_name, "PASS", elapsed))
            print(f"✅ {mod_name} passed ({elapsed:.3f}s)")
        else:
            results.append((mod_name, "SKIP (no run_tests)", 0))
            print(f"⏭️ {mod_name} skipped")
    except Exception as e:
        elapsed = time.time() - start if 'start' in locals() else 0
        results.append((mod_name, f"FAIL: {e}", elapsed))
        import traceback
        traceback.print_exc()
        print(f"❌ {mod_name} failed: {e}")

total_elapsed = time.time() - total_start
print("
" + "="*60)
print(" TEST REPORT ".center(60, "="))
print("="*60)
for name, status, elapsed in results:
    print(f"{name:<45} {status:<10} {elapsed:.3f}s")
print("-"*60)
print(f"Total: {len(results)} tests, total time {total_elapsed:.3f}s")
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s.startswith("FAIL"))
skipped = sum(1 for _, s, _ in results if s.startswith("SKIP"))
print(f"✅ Passed: {passed}  ❌ Failed: {failed}  ⏭️ Skipped: {skipped}")
print("="*60)

# 可选：写入报告文件
report_path = os.path.join(PROJECT_ROOT, "test_report.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("玄枢安全模块测试报告
")
    f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
")
    f.write("="*60 + "
")
    for name, status, elapsed in results:
        f.write(f"{name} | {status} | {elapsed:.3f}s
")
    f.write("-"*60 + "
")
    f.write(f"总计: {len(results)} 测试
")
    f.write(f"✅ 通过: {passed}  ❌ 失败: {failed}  ⏭️ 跳过: {skipped}
")
print(f"📄 报告已保存至: {report_path}")
