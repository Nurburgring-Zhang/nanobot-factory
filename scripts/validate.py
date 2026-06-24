#!/usr/bin/env python3
"""一键验证: 启动→健康检查→API测试→结果"""
import subprocess, time, urllib.request, json, sys

BASE = "http://127.0.0.1:8765"
PASS, FAIL = 0, 0

def check(name, path, method="GET", body=None):
    global PASS, FAIL
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as r:
            resp = json.loads(r.read())
            status = "ok" if resp.get("success") or resp.get("status") == "ok" else "warn"
            if status == "ok": PASS += 1
            else: FAIL += 1
            print(f"  {'✅' if status=='ok' else '⚠️'} {name}")
    except Exception as e:
        FAIL += 1
        print(f"  ❌ {name}: {str(e)[:50]}")

print("="*50)
print("  IMDF 一键验证")
print("="*50)

checks = [
    ("首页","/"),("健康检查","/api/v1/health"),("API文档","/openapi.json"),
    ("数据集","/api/datasets?page=1"),("模型网关","/api/models"),
    ("分类规则","/api/classify/rules"),("模板市场","/api/templates"),
    ("审美评分","/api/aesthetic/health"),("调度器","/api/scheduler/health"),
]
for name, path in checks: check(name, path)

print(f"\n结果: {PASS}✅ / {FAIL}❌")
sys.exit(0 if PASS >= len(checks)*0.8 else 1)
