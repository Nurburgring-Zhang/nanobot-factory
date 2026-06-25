"""P4-6-W1 Editor Tests — shared fixtures + TestClient.

Hermetic, no live uvicorn, no DB.  Imports ``editor_routes.router``
as a single APIRouter and mounts it on a fresh FastAPI app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add backend to sys.path so ``services.*`` imports resolve
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# JWT secret for any auth imports
os.environ.setdefault("JWT_SECRET",
                      "test-jwt-secret-for-editor-tests-not-for-prod")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.workflow_service.editor_routes import router as editor_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(editor_router)
    return TestClient(app)


@pytest.fixture
def sample_timeline():
    """Three clips totalling 9 seconds."""
    return {
        "clips": [
            {"id": "c1", "src": "a.mp4", "start": 0.0, "end": 3.0,
             "duration": 3.0},
            {"id": "c2", "src": "b.mp4", "start": 3.0, "end": 6.0,
             "duration": 3.0},
            {"id": "c3", "src": "c.mp4", "start": 6.0, "end": 9.0,
             "duration": 3.0},
        ],
        "cuts": [],
        "transitions": [],
        "effects": [],
    }


@pytest.fixture
def sample_project(client):
    """Create a sample project and return its dict."""
    r = client.post("/api/v1/workflow/editor/projects", json={
        "name": "Sample Project",
        "owner": "tester",
    })
    assert r.status_code == 201, r.text
    return r.json()
