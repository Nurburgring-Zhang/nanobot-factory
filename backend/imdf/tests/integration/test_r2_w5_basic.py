"""Minimal test to verify sys.path setup from conftest"""
import sys
print("=== sys.path (first 5) ===")
for p in sys.path[:5]:
    print(f"  {p}")
print(f"=== 'api' in any path? {any('api' in p for p in sys.path)} ===")

import os
imdf_path = "D:\\Hermes\\生产平台\\nanobot-factory\\backend\\imdf"
print(f"=== imdf in sys.path? {imdf_path in sys.path} ===")

try:
    from api.routes_extended import stats_router
    print("OK: from api.routes_extended")
except Exception as e:
    print(f"FAIL: {e!r}")
