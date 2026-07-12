"""P19-A2: conftest for backend/imdf/providers/tests/.

Goals:
- Make ``providers.*`` and ``providers.tests.*`` importable when pytest
  collects from backend/imdf/.
- Redirect sqlite DB used by registry to tmp_path so tests do not
  pollute the real ``backend/data/providers.db``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# 1. Make imdf/ first on sys.path (same trick as tests/conftest.py)
IMDF = Path(__file__).resolve().parents[2]  # .../backend/imdf
BACKEND = IMDF.parent
sys.path = [p for p in sys.path if Path(p).resolve() != BACKEND.resolve()]
sp = str(IMDF.resolve())
if sp not in sys.path:
    sys.path.insert(0, sp)


@pytest.fixture
def tmp_registry_db(tmp_path, monkeypatch):
    """Per-test isolated registry DB.

    Returns a tuple ``(registry_module, providers_pkg)`` where
    ``registry_module`` is the imported ``providers.registry`` module
    and ``providers_pkg`` is the ``providers`` package.

    Side effect: resets the module-level _REGISTRY singleton so the
    tmp DB path is picked up on the first ``get_registry()`` call.
    Also initializes the schema on the new DB.
    """
    from providers import registry as reg_mod
    from providers import __init__ as providers_pkg  # noqa: F401  (ensure pkg loaded)

    db_path = tmp_path / "providers.db"
    monkeypatch.setattr(reg_mod, "_DB_PATH", db_path)
    # Reset module singletons so the next get_registry() uses the tmp DB.
    try:
        reg_mod.reset_registry_for_test()
    except Exception:
        pass
    # Initialize schema on the tmp DB. (get_db_path() only auto-inits when
    # _DB_PATH is None — we set it explicitly so we must init ourselves.)
    try:
        reg_mod._init_db()
    except Exception:
        pass
    yield reg_mod, providers_pkg
    try:
        reg_mod.reset_registry_for_test()
    except Exception:
        pass


@pytest.fixture
def tmp_registry_module(tmp_path, monkeypatch):
    """Variant of ``tmp_registry_db`` that yields only ``reg_mod``."""
    from providers import registry as reg_mod

    db_path = tmp_path / "providers.db"
    monkeypatch.setattr(reg_mod, "_DB_PATH", db_path)
    try:
        reg_mod.reset_registry_for_test()
    except Exception:
        pass
    try:
        reg_mod._init_db()
    except Exception:
        pass
    yield reg_mod
    try:
        reg_mod.reset_registry_for_test()
    except Exception:
        pass