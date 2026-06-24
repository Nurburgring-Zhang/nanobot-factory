"""P4-4-W2 lineage package.

Public surface:

  * ``models``    — ORM + Pydantic + engine bootstrap
  * ``collector`` — SQL / AST / operator / manual / pipeline-step collection
  * ``graph``     — NetworkX-based asset graph
  * ``impact``    — upstream / downstream / risk / notify
  * ``api``       — FastAPI router (mounted in dataset_service.main)
  * ``tracker``   — decorator + context-manager for service-side hooks

The router (``api.router``) is mounted by ``dataset_service.main`` under
``/api/v1/lineage``.

Cross-service hook
------------------
The ``@track_lineage`` decorator in :mod:`tracker` wraps any function
that takes ``inputs=...`` / ``outputs=...`` arguments (or returns a
dataset path) and records a ``cleaned_by`` / ``scored_by`` edge
automatically. Use it inside ``cleaning_service``, ``scoring_service``,
``workflow_service`` (P3-6 templates), and ``collection_service`` (P3-1
crawlers) to wire lineage collection without rewriting the op itself.
"""
from __future__ import annotations

from . import api, collector, graph, impact, models, tracker
from .api import router
from .collector import (
    collect_from_python,
    collect_from_sql,
    record_manual,
    record_operator,
    record_pipeline_step,
)
from .graph import AssetGraph, get_graph
from .impact import ImpactAnalyzer, NotificationPlan, get_analyzer
from .models import (
    Asset,
    AssetORM,
    Edge,
    EdgeORM,
    Run,
    RunORM,
    init_lineage_db,
    reset_lineage_engine,
)
from .tracker import track_lineage, track_lineage_ctx

__version__ = "0.1.0"

__all__ = [
    # submodules
    "api",
    "collector",
    "graph",
    "impact",
    "models",
    "tracker",
    # router
    "router",
    # collector
    "collect_from_sql",
    "collect_from_python",
    "record_operator",
    "record_manual",
    "record_pipeline_step",
    # graph
    "AssetGraph",
    "get_graph",
    # impact
    "ImpactAnalyzer",
    "NotificationPlan",
    "get_analyzer",
    # models
    "Asset",
    "Edge",
    "Run",
    "AssetORM",
    "EdgeORM",
    "RunORM",
    "init_lineage_db",
    "reset_lineage_engine",
    # tracker
    "track_lineage",
    "track_lineage_ctx",
    "__version__",
]
