"""Pytest config — make ``backend.skills`` importable when tests are run from
the project root without installing the package.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
if str(_BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT.parent))