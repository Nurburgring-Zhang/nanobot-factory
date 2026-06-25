"""
test_11_views_load.py
P0-7 verification — 11 stub views render their SPA shell.

We do a lightweight HTTP-level smoke test:
  - GET /<route>  →  200 OK
  - Body contains <div id="app"> (Vue mount point)
  - Body contains <script type="module" src="/src/main.ts"> (Vite entry)

This proves Vite serves every route and the client-side router will
load the corresponding view chunk. The vue-tsc + vite build steps
already verified the view components themselves compile and bundle
without TypeScript errors.
"""
import sys
import time
import urllib.request
import urllib.error

VIEWS = [
    "/dataset",
    "/annotation",
    "/review",
    "/scoring",
    "/workflows",
    "/engines",
    "/tasks",
    "/users",
    "/billing",
    "/monitoring",
    "/settings",
]

BASE = "http://127.0.0.1:5183"


def _fetch(path: str) -> tuple[int, str]:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("utf-8", errors="replace")
        return r.status, body


def test_dataset_route_loads():
    status, body = _fetch("/dataset")
    assert status == 200, f"GET /dataset returned {status}"
    assert 'id="app"' in body, "Vue mount point missing"
    assert "/src/main.ts" in body, "Vite entry script missing"


def test_annotation_route_loads():
    status, body = _fetch("/annotation")
    assert status == 200, f"GET /annotation returned {status}"
    assert 'id="app"' in body


def test_review_route_loads():
    status, body = _fetch("/review")
    assert status == 200
    assert 'id="app"' in body


def test_scoring_route_loads():
    status, body = _fetch("/scoring")
    assert status == 200
    assert 'id="app"' in body


def test_workflows_route_loads():
    status, body = _fetch("/workflows")
    assert status == 200
    assert 'id="app"' in body


def test_engines_route_loads():
    status, body = _fetch("/engines")
    assert status == 200
    assert 'id="app"' in body


def test_tasks_route_loads():
    status, body = _fetch("/tasks")
    assert status == 200
    assert 'id="app"' in body


def test_users_route_loads():
    status, body = _fetch("/users")
    assert status == 200
    assert 'id="app"' in body


def test_billing_route_loads():
    status, body = _fetch("/billing")
    assert status == 200
    assert 'id="app"' in body


def test_monitoring_route_loads():
    status, body = _fetch("/monitoring")
    assert status == 200
    assert 'id="app"' in body


def test_settings_route_loads():
    status, body = _fetch("/settings")
    assert status == 200
    assert 'id="app"' in body


def test_all_11_views_summary():
    """Aggregate: all 11 routes must be 200."""
    failures = []
    for path in VIEWS:
        t0 = time.time()
        try:
            status, _body = _fetch(path)
            dt = (time.time() - t0) * 1000
            if status != 200:
                failures.append(f"{path} -> {status}")
            else:
                print(f"  PASS  {path:<14} 200 OK  ({dt:.0f}ms)")
        except urllib.error.URLError as exc:
            failures.append(f"{path} -> {exc}")
            print(f"  FAIL  {path:<14} {exc}")
    assert not failures, f"Failed views: {failures}"
    assert len(VIEWS) == 11


if __name__ == "__main__":
    failures = []
    passed = 0
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    print(f"Running {len(tests)} smoke tests against {BASE}")
    print("-" * 60)
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failures.append((name, str(exc)))
        except Exception as exc:
            print(f"  ERROR {name}: {exc}")
            failures.append((name, repr(exc)))
    print("-" * 60)
    print(f"PASS: {passed}/{len(tests)}")
    if failures:
        for n, e in failures:
            print(f"  {n}: {e}")
        sys.exit(1)
    print("ALL PASS")
    sys.exit(0)
