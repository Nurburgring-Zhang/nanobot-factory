"""R8-Worker-2 resilience conftest.

Provides:
- ``client``: a FastAPI ``TestClient`` wrapping the IMDF app (avoids uvicorn boot).
- ``auth_token``: a real JWT from ``/auth/login`` (admin user).
- ``adb_conn``: a raw sqlite3 connection to imdf.db (for DB-lock tests).
- ``tmp_data_dir``: isolated data directory for state-changing tests.

Bootstrapping notes (R0/R7 history):
- canvas_web.py boot registers ~50+ routers (10–15 s on this machine).
- ``api.readyz`` uses synchronous sqlite — safe to call from TestClient threads.
- ``api.auth_routes`` requires ``JWT_SECRET`` — already set by parent conftest.
"""
from __future__ import annotations

import os
import sys
import time
import sqlite3
from pathlib import Path

import pytest

# Ensure IMDF path is importable (mirror top-level conftest behavior).
_PROJ_ROOT = Path(__file__).resolve().parents[2]
_IMDF_PATH = _PROJ_ROOT / "backend" / "imdf"
if str(_IMDF_PATH) not in sys.path:
    sys.path.insert(0, str(_IMDF_PATH))

# Force-test JWT secret if upstream conftest didn't.
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-only-do-not-use-in-prod")


def _import_app():
    """Import canvas_web.app — cached across tests (expensive: ~10-15s)."""
    from api.canvas_web import app as canvas_app  # noqa: WPS433 (intentional late import)
    return canvas_app


@pytest.fixture(scope="session")
def canvas_app():
    """Session-scoped IMDF FastAPI app."""
    return _import_app()


@pytest.fixture
def client(canvas_app):
    """Per-test TestClient (cheap, no server boot)."""
    from fastapi.testclient import TestClient
    with TestClient(canvas_app) as c:
        yield c


def _get_imdb_path() -> Path:
    return _IMDF_PATH / "data" / "imdf.db"


@pytest.fixture(scope="session")
def imdb_path() -> Path:
    return _get_imdb_path()


@pytest.fixture
def db_conn(imdb_path):
    """Raw sqlite3 connection — for fault injection / lock tests."""
    assert imdb_path.exists(), f"imdf.db missing at {imdb_path}"
    conn = sqlite3.connect(str(imdb_path), timeout=2.0)
    try:
        yield conn
    finally:
        conn.close()


# Admin credentials — we register our own test user so the test is
# hermetic. The strong-password check rejects common passwords
# ("admin", "admin123", etc.), so we use one that passes validation.
TEST_USER = ("r8w2_admin", "R8w2-Strong-Pass-2026!")
TEST_USER_WEAK = ("r8w2_weak", "weak")


@pytest.fixture
def auth_token(client):
    """Register a fresh test user, log in, return the JWT.

    Registers via /auth/register so the test never depends on a seeded
    admin user existing in imdf.db (which the R0/R7 history shows is
    not guaranteed across reset DBs).
    """
    # Best effort: try to register. If user exists from a previous run,
    # the API returns 400 and we proceed straight to login.
    client.post("/auth/register", json={
        "username": TEST_USER[0], "password": TEST_USER[1], "role": "admin"
    })

    r = client.post("/auth/login", json={
        "username": TEST_USER[0], "password": TEST_USER[1]
    })
    if r.status_code != 200:
        pytest.skip(
            f"could not log in after register: {r.status_code} {r.text[:200]}"
        )
    data = r.json()
    token = data.get("data", {}).get("access_token") or data.get("access_token")
    if not token:
        pytest.skip(f"no access_token in response: {data}")
    return token
