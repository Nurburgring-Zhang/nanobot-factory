"""Quick startup smoke test for all 12 services + gateway.
Usage: python _smoke_all.py
"""
import sys
import time
import importlib
import traceback
from pathlib import Path

BACKEND = Path(r"D:\Hermes\生产平台\nanobot-factory\backend")
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(PROJECT))

SERVICES = [
    ("user_service", "backend.services.user_service.main"),
    ("asset_service", "backend.services.asset_service.main"),
    ("annotation_service", "backend.services.annotation_service.main"),
    ("cleaning_service", "backend.services.cleaning_service.main"),
    ("scoring_service", "backend.services.scoring_service.main"),
    ("dataset_service", "backend.services.dataset_service.main"),
    ("evaluation_service", "backend.services.evaluation_service.main"),
    ("agent_service", "backend.services.agent_service.main"),
    ("workflow_service", "backend.services.workflow_service.main"),
    ("notification_service", "backend.services.notification_service.main"),
    ("search_service", "backend.services.search_service.main"),
    ("collection_service", "backend.services.collection_service.main"),
]

results = []
for name, modpath in SERVICES:
    t0 = time.time()
    try:
        mod = importlib.import_module(modpath)
        app = getattr(mod, "app", None)
        if app is None:
            results.append((name, "FAIL", "no app", 0))
            continue
        n_routes = len(app.routes)
        # Collect unique paths
        paths = set()
        for r in app.routes:
            p = getattr(r, "path", None)
            if p:
                paths.add(p)
        dt = int((time.time() - t0) * 1000)
        results.append((name, "OK", f"{n_routes} routes, {len(paths)} paths, {dt}ms", dt))
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        tb = traceback.format_exc().splitlines()[-1]
        results.append((name, "FAIL", f"{type(e).__name__}: {tb}", dt))

# Gateway last (different import path)
for name, modpath in [("api_gateway", "backend.gateway.main")]:
    t0 = time.time()
    try:
        mod = importlib.import_module(modpath)
        app = getattr(mod, "app", None)
        n_routes = len(app.routes) if app else 0
        paths = set()
        for r in app.routes:
            p = getattr(r, "path", None)
            if p:
                paths.add(p)
        dt = int((time.time() - t0) * 1000)
        results.append((name, "OK", f"{n_routes} routes, {len(paths)} paths, {dt}ms", dt))
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        tb = traceback.format_exc().splitlines()[-1]
        results.append((name, "FAIL", f"{type(e).__name__}: {tb}", dt))

print(f"\n{'='*80}")
print(f"STARTUP SMOKE TEST - {len(results)} apps")
print(f"{'='*80}")
ok = sum(1 for _, s, _, _ in results if s == "OK")
fail = sum(1 for _, s, _, _ in results if s == "FAIL")
print(f"OK: {ok}  FAIL: {fail}\n")
for name, status, msg, ms in results:
    flag = "[PASS]" if status == "OK" else "[FAIL]"
    print(f"{flag} {name:25s} {ms:>5}ms  {msg}")

sys.exit(0 if fail == 0 else 1)