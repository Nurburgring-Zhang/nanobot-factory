"""Real business endpoint probe — POST/list endpoints with TestClient."""
import sys, time, importlib
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND = Path(r"D:\Hermes\生产平台\nanobot-factory\backend")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

# Endpoints to test business logic (not just health)
PROBES = [
    # (service, method, path, body, headers, expected_status_pattern)
    ("annotation_service", "GET", "/api/v1/tasks", None, {}, "200|404|401"),
    ("annotation_service", "GET", "/api/v1/operators", None, {}, "200|404"),
    ("cleaning_service", "GET", "/api/v1/clean/operators", None, {}, "200|404"),
    ("cleaning_service", "POST", "/api/v1/clean/run", {"operator": "noop", "input": {"x": 1}}, {}, "200|400|422"),
    ("scoring_service", "GET", "/api/v1/score/operators", None, {}, "200|404"),
    ("scoring_service", "POST", "/api/v1/score/run", {"operator": "noop", "input": {"x": 1}}, {}, "200|400|422"),
    ("dataset_service", "GET", "/api/v1/datasets", None, {}, "200|404"),
    ("dataset_service", "GET", "/api/v1/datasets?limit=5", None, {}, "200|404"),
    ("evaluation_service", "GET", "/api/v1/evaluations", None, {}, "200|404"),
    ("agent_service", "GET", "/api/v1/agents", None, {}, "200|404"),
    ("agent_service", "GET", "/api/v1/agents/types", None, {}, "200|404"),
    ("workflow_service", "GET", "/api/v1/workflows", None, {}, "200|404"),
    ("workflow_service", "GET", "/api/v1/workflows/templates", None, {}, "200|404"),
    ("notification_service", "GET", "/api/v1/notifications", None, {}, "200|404"),
    ("search_service", "GET", "/api/v1/search/health", None, {}, "200|404"),
    ("search_service", "POST", "/api/v1/search/text", {"query": "test", "limit": 5}, {}, "200|400|422"),
    ("collection_service", "GET", "/api/v1/collections", None, {}, "200|404"),
    ("user_service", "GET", "/api/v1/users", None, {"X-User": "admin"}, "200|401|403"),
    ("user_service", "GET", "/api/v1/roles", None, {"X-User": "admin"}, "200|401|403"),
    ("asset_service", "GET", "/api/v1/assets", None, {"X-User": "admin"}, "200|401|403"),
    ("asset_service", "GET", "/api/v1/assets/models", None, {"X-User": "admin"}, "200|401|403"),
]

# Cache clients
clients = {}

def get_client(name):
    if name not in clients:
        modpath = f"backend.services.{name}.main"
        mod = importlib.import_module(modpath)
        clients[name] = TestClient(mod.app)
    return clients[name]

print("=" * 90)
print("BUSINESS ENDPOINT PROBE")
print("=" * 90)
ok, fail = 0, 0
for svc, method, path, body, headers, expected in PROBES:
    try:
        client = get_client(svc)
        t0 = time.time()
        if method == "GET":
            resp = client.get(path, headers=headers, timeout=10)
        elif method == "POST":
            resp = client.post(path, json=body, headers=headers, timeout=10)
        else:
            resp = client.request(method, path, json=body, headers=headers, timeout=10)
        dt = int((time.time() - t0) * 1000)

        # Parse status
        code = resp.status_code
        ok_in_expected = any(p.strip() in str(code) for p in expected.split("|"))
        status_match = "PASS" if ok_in_expected else "UNEXP"

        # Parse body
        try:
            j = resp.json()
            if isinstance(j, dict):
                if "success" in j:
                    bshape = f"success={j['success']}"
                elif "data" in j:
                    bshape = f"data={type(j['data']).__name__}"
                else:
                    bshape = f"keys={list(j.keys())[:3]}"
            else:
                bshape = f"type={type(j).__name__}"
        except Exception:
            bshape = f"non-json {resp.headers.get('content-type','')[:30]}"

        flag = "[OK]" if status_match == "PASS" else "[UN]"
        print(f"{flag} {svc:22s} {method:5s} {path:50s} {dt:>5}ms {code} [{bshape[:60]}]")
        if status_match == "PASS":
            ok += 1
        else:
            fail += 1
    except Exception as e:
        print(f"[ERR] {svc:22s} {method:5s} {path:50s} EXC:{type(e).__name__}: {str(e)[:80]}")
        fail += 1

print(f"\n{'=' * 90}\nBusiness endpoints: OK={ok} FAIL={fail} / Total {len(PROBES)}\n{'=' * 90}")
sys.exit(0 if fail == 0 else 1)