"""Integration test for 3 fixed endpoints using FastAPI TestClient.

Mirrors the spec's "真实 curl 测试 6 个 case (每个端点合法+非法)".
Replaces curl since the IMDF server can't be started reliably
(start_imdf.py has sys.path bug — see memory).

Run: pytest tests/integration/test_crash_endpoints.py -v
Or:  python this_file.py  (one-shot report)
"""
import sys
from pathlib import Path

# Add imdf to sys.path (avoid start_imdf.py's broken path insertion)
_IMDF_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "imdf"
if str(_IMDF_DIR) not in sys.path:
    sys.path.insert(0, str(_IMDF_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from api.canvas_web import app  # noqa: E402

client = TestClient(app)


def banner(text: str) -> None:
    print()
    print("=" * 70)
    print(f" {text}")
    print("=" * 70)


def show(label: str, resp) -> None:
    print(f"[{label}] {resp.request.method} {resp.request.url.path}")
    print(f"  status: {resp.status_code}")
    body = resp.text
    if len(body) > 200:
        body = body[:200] + "..."
    print(f"  body  : {body}")


# ───────────────────── endpoint 1: GET /api/aesthetic/elo-entry/{image_id} ──
banner("EP1: /api/aesthetic/elo-entry/{image_id}")

show("LEGAL img_001", client.get("/api/aesthetic/elo-entry/img_001"))
show("BAD  DROP TABLE", client.get("/api/aesthetic/elo-entry/DROP%20TABLE"))
show("BAD  💥", client.get("/api/aesthetic/elo-entry/" + "%F0%9F%92%A5"))


# ───────────────────── endpoint 2: GET /api/drama/episode/{episode_id} ─────
banner("EP2: /api/drama/episode/{episode_id}")

show("LEGAL ep_0001", client.get("/api/drama/episode/ep_0001"))
show("BAD  OR 1=1", client.get("/api/drama/episode/" + "OR%201%3D1"))
show("BAD  (empty-after-slash)", client.get("/api/drama/episode/"))


# ───────────────────── endpoint 3: DELETE /canvas/element/{element_id} ─────
banner("EP3: DELETE /canvas/element/{element_id}")

show("LEGAL elem-001", client.delete("/canvas/element/elem-001"))
show("BAD  💥", client.delete("/canvas/element/" + "%F0%9F%92%A5"))
show("BAD  ../etc", client.delete("/canvas/element/" + "..%2Fetc"))

print()
print("=" * 70)
print(" Done — 9 cases (3 endpoints x 3 cases each)")
print("=" * 70)
