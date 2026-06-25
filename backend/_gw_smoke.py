"""Rate limit + auth + 404 tests on the gateway."""
import sys, time
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND = Path(r"D:\Hermes\生产平台\nanobot-factory\backend")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

from backend.gateway.main import app

client = TestClient(app)
print("=" * 80)
print("GATEWAY CONTROL + RATE LIMIT TEST")
print("=" * 80)

# 1. Health
r = client.get("/healthz")
print(f"[1] /healthz → {r.status_code} body={r.json()}")

# 2. Ready
r = client.get("/readyz")
print(f"[2] /readyz  → {r.status_code} body={r.json()}")

# 3. Routes (should have all 12 service prefixes)
r = client.get("/_gw/routes")
routes = r.json()["routes"]
prefixes = sorted(set(rt["prefix"] for rt in routes))
print(f"[3] /_gw/routes → {r.status_code} count={len(routes)} unique prefixes={len(prefixes)}")
# Check duplicates
from collections import Counter
prefix_counts = Counter(rt["prefix"] for rt in routes)
dups = {p: c for p, c in prefix_counts.items() if c > 1}
if dups:
    print(f"    DUPLICATE PREFIXES: {dups}")
else:
    print(f"    No duplicate prefixes (clean)")

# 4. Breakers
r = client.get("/_gw/breakers")
print(f"[4] /_gw/breakers → {r.status_code} body={r.json()}")

# 5. 404 on unknown route (no auth, no service)
r = client.get("/api/v1/auth/login")  # public route
print(f"[5] /api/v1/auth/login (no auth) → {r.status_code}")
# Note: gateway will try to forward to 127.0.0.1:8001, which is down → likely 502/503

# 6. Protected route without JWT
r = client.get("/api/v1/users")
print(f"[6] /api/v1/users (no auth) → {r.status_code} body={r.json()}")

# 7. Rate limit — fire 150 requests in burst
print("\n[7] Rate limit test — 150 rapid GET /healthz (bypassed)... skipping, /healthz is bypassed")
# Test with non-bypassed path — use /_gw/routes which is bypassed too. Use a protected route instead.
# Actually we can hit the catch-all path with no auth to get 401 quickly without upstream
t0 = time.time()
codes = []
for i in range(150):
    r = client.get("/api/v1/users")
    codes.append(r.status_code)
dt = time.time() - t0
from collections import Counter
cc = Counter(codes)
print(f"    150 calls in {dt:.2f}s → code distribution: {dict(cc)}")
if 429 in cc:
    print(f"    ✓ Rate limiter triggered ({cc[429]} / 150)")
else:
    print(f"    ✗ No rate limiter triggered (capacity 100 burst → expected ~50x 429)")

# 8. Invalid JWT
r = client.get("/api/v1/users", headers={"Authorization": "Bearer invalid_token"})
print(f"\n[8] /api/v1/users (bad JWT) → {r.status_code} body={r.json()}")

# 9. Wrong scheme
r = client.get("/api/v1/users", headers={"Authorization": "Basic xyz"})
print(f"[9] /api/v1/users (Basic auth) → {r.status_code} body={r.json()}")

print("\n" + "=" * 80)