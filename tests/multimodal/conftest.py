"""Shared fixtures for tests.multimodal.

The fixtures here make sure the in-process Python can import the
``imdf.multimodal`` package regardless of cwd.  The package itself lives at
``backend/imdf/multimodal``; pytest is invoked with ``rootdir=backend`` so
``imdf.multimodal.*`` imports resolve normally.

We avoid depending on the wider ``backend`` package — that pulls in celery,
SQLAlchemy etc. which are flaky on Windows.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(scope="session")
def backend_root() -> Path:
    return BACKEND_ROOT