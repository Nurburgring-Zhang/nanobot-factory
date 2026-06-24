"""
R8 前置冒烟 — 验证 R0+R7+R6.5 修复能跑
8 关键端点 + R0 3 CRITICAL 修复 + R7 健康端点 + R6.5 前端 SPA
"""
import sys
import json
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')

from fastapi.testclient import TestClient

results = []

def check(name, ok, detail=""):
    status = "✅ PASS" if ok else "❌ FAIL"
    results.append({"name": name, "ok": ok, "detail": detail})
    print(f"{status} | {name} | {detail}")

try:
    # 加载 app (可能慢,等待久一点)
    print("[INFO] loading api.canvas_web:app ...")
    from api.canvas_web import app
    client = TestClient(app)

    # ===== R7 健康端点 =====
    r = client.get("/healthz")
    check("R7 /healthz (liveness)", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:120]}")

    r = client.get("/readyz")
    check("R7 /readyz (readiness, DB+disk)", r.status_code in (200, 503), f"HTTP {r.status_code}: {r.text[:120]}")

    r = client.get("/metrics")
    body = r.text[:200]
    check("R7 /metrics (Prometheus)", r.status_code == 200 and "imdf_" in body, f"HTTP {r.status_code}, has imdf_: {'imdf_' in body}")

    # ===== R0 修复 #1: 审美 8 端点 (R1 已修,验证不 500) =====
    for ep in ["/api/aesthetic/health", "/api/aesthetic/elo-ranking", "/api/aesthetic/elo-stats"]:
        try:
            r = client.get(ep)
            ok = r.status_code == 200
            check(f"R0 审美 {ep}", ok, f"HTTP {r.status_code}")
        except Exception as e:
            check(f"R0 审美 {ep}", False, f"Exception: {e}")

    # ===== R0 修复 #2: 数字人 2 端点 (W2 新建) =====
    try:
        r = client.get("/digital-human/models")
        body = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and body.get("success") and len(body.get("data", {}).get("models", [])) >= 5
        check("R0 数字人 /digital-human/models", ok, f"HTTP {r.status_code}, models count: {len(body.get('data', {}).get('models', []))}")
    except Exception as e:
        check("R0 数字人 /digital-human/models", False, f"Exception: {e}")

    # ===== R0 修复 #3: stats/compare (W3 加参数) =====
    try:
        r = client.get("/api/stats/compare?period_a=2026-01&period_b=2026-06")
        check("R0 stats/compare (带参)", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        check("R0 stats/compare (带参)", False, f"Exception: {e}")

    try:
        r = client.get("/api/stats/compare")  # 缺参数应 422
        check("R0 stats/compare (无参→422)", r.status_code == 422, f"HTTP {r.status_code}")
    except Exception as e:
        check("R0 stats/compare (无参→422)", False, f"Exception: {e}")

    # ===== R6.5 前端 SPA (静态文件由 canvas_web.py StaticFiles 挂载) =====
    try:
        r = client.get("/")
        has_app = 'id="app"' in r.text
        check("R6.5 GET / (SPA 入口)", r.status_code == 200 and has_app,
              f"HTTP {r.status_code}, has #app: {has_app}")
    except Exception as e:
        check("R6.5 GET / (SPA 入口)", False, f"Exception: {e}")

    # 总结
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"TOTAL: {passed}/{total} PASS")
    print(f"{'='*60}")
    sys.exit(0 if passed == total else 1)

except Exception as e:
    print(f"[FATAL] cannot load app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(2)
