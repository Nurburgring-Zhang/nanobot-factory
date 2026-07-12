"""conftest for tests/security/ — ensure backend/ is on sys.path.

Without this, ``from imdf.security...`` won't resolve when pytest runs
this test from the project root with pythonpath=backend/imdf (the value
declared in the root pytest.ini).

P21 R3 — Extreme security pentest suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"

_backend = str(_BACKEND_DIR)
if _backend not in sys.path:
    sys.path.insert(0, _backend)
