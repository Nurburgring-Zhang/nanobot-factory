"""P3-2-W1 smoke test — verify each microservice boots via TestClient.

Run from: D:\\Hermes\\生产平台\\nanobot-factory\\
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/test_p3_2_w1_services.py -v --tb=short
"""
from __future__ import annotations

import os
import sys
import importlib
from pathlib import Path

# Ensure imdf.* / services.* are importable
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Force a deterministic JWT secret for the auth route imports
os.environ.setdefault("JWT_SECRET", "test-secret-DO-NOT-USE-IN-PROD-abcdef123456")
os.environ.setdefault("IMDF_TEST_MODE", "1")

from fastapi.testclient import TestClient  # noqa: E402


# ── user-service ────────────────────────────────────────────────────────────
def test_user_service_boot():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service"] == "user-service"
    assert body["status"] in ("ok", "degraded")
    print(f"  user-service /healthz: {body}")


def test_user_service_root():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "user-service"
    assert "/api/v1/users" in body["endpoints"]["users"]


def test_user_service_list_users():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/users")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    print(f"  user-service /api/v1/users count={len(body)}")


def test_user_service_list_roles():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/roles")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert any(x["name"] == "admin" for x in body)
    assert any(x["name"] == "annotator" for x in body)


def test_user_service_role_permissions():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/roles/permissions")
    assert r.status_code == 200
    body = r.json()
    assert "roles" in body


def test_user_service_get_user_404():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/users/nonexistent_user_xyz")
    assert r.status_code == 404


def test_user_service_role_validation():
    mod = importlib.import_module("services.user_service.main")
    client = TestClient(mod.app)
    r = client.put("/api/v1/users/foo/role", json={"role": "superhacker"})
    assert r.status_code == 400, r.text


# ── asset-service ───────────────────────────────────────────────────────────
def test_asset_service_boot():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "asset-service"


def test_asset_service_root():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "asset-service"


def test_asset_service_list_assets():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/assets")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    print(f"  asset-service /api/v1/assets count={len(body)}")


def test_asset_service_formats():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/assets/formats")
    assert r.status_code == 200
    body = r.json()
    assert "image/png" in body
    assert "video/mp4" in body


def test_asset_service_list_items():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/items")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_asset_service_item_categories():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/items/categories")
    assert r.status_code == 200
    body = r.json()
    assert "image" in body
    assert "video" in body


def test_asset_service_add_item_roundtrip():
    mod = importlib.import_module("services.asset_service.main")
    client = TestClient(mod.app)
    payload = {
        "name": "test-asset-" + os.urandom(3).hex(),
        "category": "image",
        "file_path": "/tmp/test.png",
    }
    r = client.post("/api/v1/items/add", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["name"] == payload["name"]


# ── annotation-service ──────────────────────────────────────────────────────
def test_annotation_service_boot():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "annotation-service"


def test_annotation_service_root():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "annotation-service"


def test_annotation_service_list_annotations():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/annotations")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    print(f"  annotation-service /api/v1/annotations count={len(body)}")


def test_annotation_service_list_tasks():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_annotation_service_list_operators():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    r = client.get("/api/v1/operators")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 20
    op_ids = [op["id"] for op in body]
    assert "bbox" in op_ids
    assert "polygon" in op_ids


def test_annotation_service_annotation_roundtrip():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    payload = {
        "task_id": "test-task-" + os.urandom(3).hex(),
        "asset_id": "asset-1",
        "label": "cat",
        "operator": "bbox",
        "confidence": 0.95,
    }
    r = client.post("/api/v1/annotations", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "id" in body


def test_annotation_service_task_roundtrip():
    mod = importlib.import_module("services.annotation_service.main")
    client = TestClient(mod.app)
    payload = {
        "name": "smoke-task-" + os.urandom(3).hex(),
        "type": "image-classification",
        "status": "open",
    }
    r = client.post("/api/v1/tasks", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    task_id = body["id"]

    # Now fetch it
    r2 = client.get(f"/api/v1/tasks/{task_id}")
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["id"] == task_id
    assert body2["status"] == "open"
