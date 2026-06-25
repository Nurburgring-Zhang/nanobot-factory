"""Integration tests: full API chain — register → login → create API key → call API.

Tests the complete authentication + API key lifecycle using the FastAPI TestClient.
Requires a running app or uses TestClient for in-process testing.
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-integration-32chars!"


@pytest.fixture(scope="module")
def client():
    """Create a FastAPI TestClient for the full app."""
    from api.canvas_web import app
    with TestClient(app) as c:
        yield c


class TestAuthChain:
    """Register → Login → Get JWT → Access protected endpoints."""

    @pytest.fixture(autouse=True)
    def setup_users(self, monkeypatch):
        """Ensure isolated user state."""
        from api.auth_routes import users_db
        monkeypatch.setattr("api.auth_routes.users_db", {})
        monkeypatch.setattr("api.api_key_routes.users_db", {})

    def test_register_user(self, client):
        """POST /auth/register should create a new user."""
        resp = client.post("/auth/register", json={
            "username": "integ_user",
            "password": "StrongP@ss1",
            "role": "viewer",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "integ_user"
        assert data["role"] == "viewer"

    def test_register_duplicate_fails(self, client):
        """Registering the same username twice should return 400."""
        client.post("/auth/register", json={
            "username": "integ_user2",
            "password": "StrongP@ss1",
        })
        resp = client.post("/auth/register", json={
            "username": "integ_user2",
            "password": "AnotherPass1!",
        })
        assert resp.status_code in (400, 409)

    def test_register_weak_password_fails(self, client):
        """Registering with a weak password should return 400."""
        resp = client.post("/auth/register", json={
            "username": "weak_user",
            "password": "123456",
        })
        assert resp.status_code == 400

    def test_login_returns_token(self, client):
        """POST /auth/login should return a JWT access_token."""
        # Register first
        client.post("/auth/register", json={
            "username": "login_user",
            "password": "StrongP@ss1",
        })
        resp = client.post("/auth/login", json={
            "username": "login_user",
            "password": "StrongP@ss1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_login_wrong_password_fails(self, client):
        """Login with wrong password should return 401."""
        client.post("/auth/register", json={
            "username": "badlogin_user",
            "password": "StrongP@ss1",
        })
        resp = client.post("/auth/login", json={
            "username": "badlogin_user",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user_fails(self, client):
        """Login with non-existent username should return 401."""
        resp = client.post("/auth/login", json={
            "username": "nonexistent_xyz",
            "password": "StrongP@ss1",
        })
        assert resp.status_code == 401

    def test_get_me_with_token(self, client):
        """GET /auth/me with valid token should return user info."""
        client.post("/auth/register", json={
            "username": "me_user",
            "password": "StrongP@ss1",
        })
        login_resp = client.post("/auth/login", json={
            "username": "me_user",
            "password": "StrongP@ss1",
        })
        token = login_resp.json()["access_token"]

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "me_user"

    def test_get_me_without_token_fails(self, client):
        """GET /auth/me without token should return 401."""
        resp = client.get("/auth/me")
        assert resp.status_code in (401, 403)

    def test_refresh_token(self, client):
        """POST /auth/refresh should return a new access token."""
        client.post("/auth/register", json={
            "username": "refresh_user",
            "password": "StrongP@ss1",
        })
        login_resp = client.post("/auth/login", json={
            "username": "refresh_user",
            "password": "StrongP@ss1",
        })
        old_token = login_resp.json()["access_token"]

        resp = client.post("/auth/refresh",
                           headers={"Authorization": f"Bearer {old_token}"})
        assert resp.status_code == 200
        new_token = resp.json()["access_token"]
        assert new_token != old_token


class TestAPIKeyChain:
    """Register → Login → Create API Key → List → Revoke."""

    @pytest.fixture
    def auth_headers(self, client):
        """Register a user, log in, and return auth headers."""
        client.post("/auth/register", json={
            "username": "apikey_user",
            "password": "StrongP@ss1",
        })
        resp = client.post("/auth/login", json={
            "username": "apikey_user",
            "password": "StrongP@ss1",
        })
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_create_api_key(self, client, auth_headers):
        """POST /api/v1/api-keys/create should return an API key."""
        resp = client.post("/api/v1/api-keys/create",
                           json={"name": "test-key"},
                           headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "key" in data["data"]
        assert data["data"]["key"].startswith("imdf_sk-")
        # imdf_sk- prefix + 32 hex chars
        assert len(data["data"]["key"]) == len("imdf_sk-") + 32

    def test_create_api_key_without_auth_fails(self, client):
        """Creating an API key without auth should fail."""
        resp = client.post("/api/v1/api-keys/create",
                           json={"name": "bad-key"})
        assert resp.status_code in (401, 403)

    def test_list_api_keys(self, client, auth_headers):
        """GET /api/v1/api-keys should list keys (without exposing key values)."""
        # Create a key first
        client.post("/api/v1/api-keys/create",
                    json={"name": "list-key"},
                    headers=auth_headers)
        resp = client.get("/api/v1/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_revoke_api_key(self, client, auth_headers):
        """DELETE /api/v1/api-keys/{id} should revoke a key."""
        # Create a key
        create_resp = client.post("/api/v1/api-keys/create",
                                  json={"name": "revoke-key"},
                                  headers=auth_headers)
        key_id = create_resp.json()["data"]["id"]

        # Revoke it
        resp = client.delete(f"/api/v1/api-keys/{key_id}",
                             headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_revoke_nonexistent_key(self, client, auth_headers):
        """Revoking a non-existent key should return 404."""
        resp = client.delete("/api/v1/api-keys/nonexistent-id",
                             headers=auth_headers)
        assert resp.status_code == 404

    def test_full_api_key_lifecycle(self, client):
        """Full lifecycle: register → login → create key → list → revoke."""
        # 1. Register
        resp = client.post("/auth/register", json={
            "username": "lifecycle_user",
            "password": "StrongP@ss1",
        })
        assert resp.status_code == 200

        # 2. Login
        resp = client.post("/auth/login", json={
            "username": "lifecycle_user",
            "password": "StrongP@ss1",
        })
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create API Key
        resp = client.post("/api/v1/api-keys/create",
                           json={"name": "lifecycle-key"},
                           headers=headers)
        assert resp.status_code == 200
        key_data = resp.json()["data"]
        assert key_data["key"].startswith("imdf_sk-")
        key_id = key_data["id"]

        # 4. List keys
        resp = client.get("/api/v1/api-keys", headers=headers)
        assert resp.status_code == 200
        keys = resp.json()["data"]
        assert any(k["id"] == key_id for k in keys)

        # 5. Revoke key
        resp = client.delete(f"/api/v1/api-keys/{key_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True
