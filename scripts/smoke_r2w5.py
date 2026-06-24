"""Smoke test imports of all modified route files."""
import sys
import os

# 路由文件用 'from api._common...' 风格, 需要 backend/imdf 在 sys.path
# 但同时 backend/ 上层也要有, 否则 imdf.api 包找不到
# 用 subprocess 隔离, 模拟 canvas_web.py 启动时的 sys.path
import subprocess

# 路由文件直接通过 subprocess + sys.path.insert 测试
SCRIPT = r"""
import sys
import os
# 1) backend/ 先 (让 imdf.api 包可解析)
sys.path.insert(0, r'%BACKEND%')
# 2) 然后 backend/imdf/ (让 'from api._common...' 工作)
sys.path.insert(0, r'%IMDF%')

mods = [
    "imdf.api.ops_dashboard_routes",
    "imdf.api.monitor_routes",
    "imdf.api.audit_routes",
    "imdf.api.personnel_routes",
    "imdf.api.pe_routes",
    "imdf.api.dam_routes",
    "imdf.api.template_routes",
    "imdf.api.quality_v2_routes",
    "imdf.api.routes_extended",
    "imdf.api.webhook_routes",
    "imdf.api._common.date_range",
    "imdf.api._common.granularity",
    "imdf.api._common.dimension",
]
failed = []
for m in mods:
    try:
        __import__(m)
        print(f"[OK] {m}")
    except Exception as e:
        failed.append((m, str(e)[:300]))
        print(f"[FAIL] {m}: {e!r}")
print(f"\nTotal: {len(mods)} modules, failed: {len(failed)}")
if failed:
    sys.exit(1)
"""

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
IMDF = os.path.join(BACKEND, "imdf")
script = SCRIPT.replace("%BACKEND%", BACKEND).replace("%IMDF%", IMDF)

r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
print(r.stdout)
if r.returncode != 0:
    print("STDERR:", r.stderr[:2000])
sys.exit(r.returncode)

failed = []
for m in mods:
    try:
        __import__(m)
        print(f"[OK] {m}")
    except Exception as e:
        failed.append((m, str(e)[:300]))
        print(f"[FAIL] {m}: {e!r}")

print(f"\nTotal: {len(mods)} modules, failed: {len(failed)}")
if failed:
    sys.exit(1)
