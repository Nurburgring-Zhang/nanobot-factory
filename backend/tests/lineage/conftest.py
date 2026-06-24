"""Shared pytest fixtures for the lineage test-suite.

Each test gets a fresh SQLite lineage DB (file under tempdir) so the
suite is hermetic and parallel-safe.
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Make ``backend/`` importable so ``from services...`` resolves.
_BACKEND = Path(__file__).resolve().parents[1]  # tests/lineage -> backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Also make the project root importable (for services.dataset_service.lineage)
_PROJECT_ROOT = _BACKEND  # tests/lineage is at backend/tests/lineage
# Actually we want backend/ (services.dataset_service.* lives there)
# _BACKEND already is backend/, so we don't need to add another.

# Clean env: make sure no stray DB URL leaks in.
os.environ.pop("IMDF_P2_DB_URL", None)
os.environ.pop("LINEAGE_DB_URL", None)


@pytest.fixture
def lineage_db_url():
    """Yield a fresh SQLite URL, reset engines before/after."""
    from services.dataset_service.lineage.models import (
        init_lineage_db,
        reset_lineage_engine,
    )
    from services.dataset_service.lineage import graph as _graph_mod
    from services.dataset_service.lineage import impact as _impact_mod

    tmpdir = tempfile.mkdtemp(prefix="nanobot_lineage_")
    db_path = os.path.join(tmpdir, "lineage_test.db")
    url = f"sqlite:///{db_path}"
    reset_lineage_engine()
    init_lineage_db(db_url=url, auto_create=True)
    # Reset graph + analyzer caches so each test gets a fresh singleton
    _graph_mod.reset_graph()
    _impact_mod.reset_analyzer()
    yield url
    reset_lineage_engine()
    _graph_mod.reset_graph()
    _impact_mod.reset_analyzer()
    shutil.rmtree(tmpdir, ignore_errors=True)
