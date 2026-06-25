"""Real API endpoint smoke test via TestClient (3-5 sec total)."""
import sys, time, importlib
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND = Path(r"D:\Hermes\生产平台\nanobot-factory\backend")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

SERVICES = {
    "user_service": "backend.services.user_service.main",
    "asset_service": "backend.services.asset_service.main",
    "annotation_service": "backend.services.annotation_service.main",
    "cleaning_service": "backend.services.cleaning_service.main",
    "scoring_service": "backend.services.scoring_service.main",
    "dataset_service": "backend.services.dataset_service.main",
    "evaluation_service": "backend.services.evaluation_service.main",
    "agent_service": "backend.services.agent_service.main",
    "workflow_service": "backend.services.workflow_service.main",
    "notification_service": "backend.services.notification_service.main",
    "search_service": "backend.services.search_service.main",
    "collection_service": "backend.services.collection_service.main",
    "api_gateway": "backend.gateway.main",
}

# Endpoints to probe per service (common test paths)
PROBES = {
    "_default": [("GET", "/"), ("GET", "/healthz"), ("GET", "/readyz"), ("GET", "/metrics")],
    "api_gateway": [("GET", "/"), ("GET", "/healthz"), ("GET", "/readyz"), ("GET", "/_gw/routes"), ("GET", "/_gw/breakers")],
}

results = []
for name, modpath in SERVICES.items():
    t0 = time.time()
    try:
        mod = importlib.import_module(modpath)
        client = TestClient(mod.app)
        probes = PROBES.get(name, PROBES["_default"])
        out = []
        for method, path in probes:
            try:
                resp = getattr(client, method.lower())(path, timeout=5)
                code = resp.status_code
                body_preview = ""
                try:
                    if "application/json" in resp.headers.get("content-type", ""):
                        j = resp.json()
                        if isinstance(j, dict):
                            body_preview = str({k: v for k, v in list(j.items())[:3]})[:80]
                        else:
                            body_preview = str(type(j).__name__)
                    else:
                        body_preview = f"{resp.headers.get('content-type','')} {len(resp.content)}b"
                except Exception:
                    body_preview = "parse-err"
                out.append(f"{method} {path}={code} {body_preview}")
            except Exception as e:
                out.append(f"{method} {path}=EXC:{type(e).__name__}:{e}")
        dt = int((time.time() - t0) * 1000)
        results.append((name, "OK", "\n     ".join(out), dt))
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        results.append((name, "FAIL", f"{type(e).__name__}: {str(e)[:100]}", dt))

print("=" * 80)
print("REAL API SMOKE TEST (TestClient)")
print("=" * 80)
ok = sum(1 for _, s, _, _ in results if s == "OK")
print(f"OK: {ok} / {len(results)}\n")
for name, status, msg, ms in results:
    flag = "[OK]" if status == "OK" else "[FL]"
    print(f"{flag} {name:22s} {ms:>5}ms")
    if status == "OK":
        for line in msg.split("\n     "):
            print(f"     {line}")
    else:
        print(f"     {msg}")
    print()

sys.exit(0 if ok == len(results) else 1)