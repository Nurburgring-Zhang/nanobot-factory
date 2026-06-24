"""Smoke tests for P3-6-W1 basic workflow templates (25 项).

Uses TestClient (no live uvicorn) for hermetic + fast verification.

Verifies:
  1. /api/v1/workflow/templates  returns 25 items in 5 categories
  2. /api/v1/workflow/templates/categories returns counts
  3. /api/v1/workflow/templates/{id} returns full detail for one template
  4. /api/v1/workflow/templates/{id}/run dry-run returns mocked step exec
  5. 404 on unknown template id
  6. 5 representative templates (one per category) dry-run successfully
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend root on sys.path
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Disable rate limiting / oauth for hermetic test
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("IMDF_TEST_MODE", "1")

from fastapi.testclient import TestClient

from services.workflow_service.main import app


CATEGORIES = ["collection", "cleaning", "annotation", "scoring", "filter"]

# One canonical template per category (expected to exist)
CANONICAL: dict[str, str] = {
    "collection": "tpl-coll-001",
    "cleaning":   "tpl-cln-001",
    "annotation": "tpl-ann-001",
    "scoring":    "tpl-scr-001",
    "filter":     "tpl-flt-001",
}


def _ok(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"  PASS  {msg}")


def main() -> None:
    client = TestClient(app)
    print("\n=== P3-6-W1 basic workflow templates smoke ===")

    # ----- 1. list all -----
    r = client.get("/api/v1/workflow/templates")
    _ok(r.status_code == 200, f"GET /templates  -> 200 (got {r.status_code})")
    body = r.json()
    _ok(body["total"] == 25, f"total == 25 (got {body['total']})")
    _ok(set(body["counts_by_category"].keys()) == set(CATEGORIES),
        f"5 categories present: {body['counts_by_category']}")
    _ok(all(body["counts_by_category"][c] == 5 for c in CATEGORIES),
        f"each category has 5: {body['counts_by_category']}")
    _ok(len(body["items"]) == 25, f"items len == 25 (got {len(body['items'])})")
    # every item has the required fields
    required = {"id", "name", "category", "description", "steps",
                "tags", "version", "inputs", "outputs", "metrics"}
    missing = []
    for t in body["items"]:
        if not required.issubset(t.keys()):
            missing.append(t["id"])
    _ok(not missing, f"every template has all required fields (missing: {missing})")
    # steps are non-empty lists
    _ok(all(len(t["steps"]) >= 1 for t in body["items"]),
        "every template has >= 1 step")

    # ----- 2. categories endpoint -----
    r = client.get("/api/v1/workflow/templates/categories")
    _ok(r.status_code == 200, f"GET /categories -> 200 (got {r.status_code})")
    cat_body = r.json()
    _ok(cat_body["total"] == 25, f"categories total == 25 (got {cat_body['total']})")

    # ----- 3. category filter -----
    for cat in CATEGORIES:
        r = client.get("/api/v1/workflow/templates", params={"category": cat})
        _ok(r.status_code == 200, f"GET /templates?category={cat} -> 200")
        b = r.json()
        _ok(b["total"] == 5, f"category {cat} returns 5 (got {b['total']})")
        _ok(all(t["category"] == cat for t in b["items"]),
            f"all items in {cat} have category == {cat}")

    # ----- 4. detail -----
    for cat, tid in CANONICAL.items():
        r = client.get(f"/api/v1/workflow/templates/{tid}")
        _ok(r.status_code == 200, f"GET /{tid} -> 200 (got {r.status_code})")
        t = r.json()
        _ok(t["id"] == tid, f"detail id matches")
        _ok(t["category"] == cat, f"detail category matches")
        _ok(len(t["steps"]) >= 1, f"detail has steps")
        _ok(isinstance(t["inputs"], dict), f"detail has inputs dict")
        _ok(isinstance(t["metrics"], list), f"detail has metrics list")

    # ----- 5. dry-run (5 representative templates, one per category) -----
    for cat, tid in CANONICAL.items():
        r = client.post(
            f"/api/v1/workflow/templates/{tid}/run",
            json={"dry_run": True, "trigger": "test"},
        )
        _ok(r.status_code == 200, f"POST /{tid}/run dry-run -> 200 (got {r.status_code})")
        b = r.json()
        _ok(b["template_id"] == tid, f"  response template_id matches")
        _ok(b["category"] == cat, f"  response category matches")
        _ok(b["dry_run"] is True, f"  dry_run == true")
        _ok(b["status"] == "completed", f"  status == completed (got {b['status']})")
        _ok(b["step_count"] == len(b["steps"]),
             f"  step_count {b['step_count']} == len(steps) {len(b['steps'])}")
        _ok(all(s["status"] == "ok" for s in b["steps"]),
             f"  every step status == ok")
        _ok(all(s["duration_ms"] >= 0 for s in b["steps"]),
             f"  every step has non-negative duration")
        _ok(isinstance(b["metrics"], dict), f"  metrics is dict")

    # ----- 6. 404 paths -----
    r = client.get("/api/v1/workflow/templates/tpl-does-not-exist")
    _ok(r.status_code == 404, f"GET unknown template -> 404 (got {r.status_code})")
    r = client.post("/api/v1/workflow/templates/tpl-does-not-exist/run",
                    json={"dry_run": True})
    _ok(r.status_code == 404, f"POST unknown template run -> 404 (got {r.status_code})")
    r = client.get("/api/v1/workflow/templates", params={"category": "bogus"})
    _ok(r.status_code == 400, f"GET unknown category -> 400 (got {r.status_code})")

    # ----- 7. dry-run with custom inputs -----
    r = client.post(
        "/api/v1/workflow/templates/tpl-coll-001/run",
        json={"dry_run": True, "inputs": {"max_depth": 3, "max_pages": 999}},
    )
    _ok(r.status_code == 200, f"POST run with custom inputs -> 200")
    b = r.json()
    _ok(b["metrics"]["inputs_count"] >= 2,
        f"  inputs_count reflects merged inputs ({b['metrics']['inputs_count']})")

    # ----- 8. healthz still works (legacy) -----
    r = client.get("/healthz")
    _ok(r.status_code == 200, f"GET /healthz -> 200")

    print("\n=== ALL SMOKE TESTS PASSED ===\n")


if __name__ == "__main__":
    main()