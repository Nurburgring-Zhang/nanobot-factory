"""
Async vector indexing tasks (P2-1-W2)
======================================

Tasks:
- ``index_asset``        — index a single (asset_id, text, metadata) tuple.
- ``index_batch``        — index a batch of assets.
- ``reindex_all``        — reindex every asset currently held by the engine.

These wrap ``engines.semantic_search.SemanticSearchEngine``.
The engine is in-process (no network hop), so we keep things on a single
worker — but routing them through Celery means the API can enqueue
reindexing work without blocking the request thread.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import shared_task

_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


@shared_task(name="imdf.tasks.vector_index.index_asset", bind=True, acks_late=True)
def index_asset(
    self,
    asset_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Index a single asset."""
    try:
        from engines.semantic_search import SemanticSearchEngine
        engine = SemanticSearchEngine()
        result = engine.index_asset(asset_id=asset_id, text=text or "", metadata=metadata or {})
        return {"ok": True, "asset_id": asset_id, "result": result, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        logger.exception("index_asset failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.vector_index.index_batch", bind=True, acks_late=True)
def index_batch(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Index a batch of assets.

    Each item is ``{"asset_id": ..., "text": ..., "metadata": {...}}``.
    """
    items = list(items or [])
    successes = 0
    failures: List[Dict[str, Any]] = []
    for it in items:
        try:
            index_asset.run(  # type: ignore[attr-defined]
                asset_id=it.get("asset_id", ""),
                text=it.get("text", ""),
                metadata=it.get("metadata") or {},
            )
            successes += 1
        except Exception as exc:
            failures.append({
                "asset_id": it.get("asset_id", ""),
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            })
    return {
        "ok": True,
        "total": len(items),
        "successes": successes,
        "failures": len(failures),
        "failure_details": failures,
        "task_id": self.request.id,
    }


@shared_task(name="imdf.tasks.vector_index.reindex_all", bind=True)
def reindex_all(self) -> Dict[str, Any]:
    """Reload the in-memory index from the underlying persistence layer.

    This is mostly useful after a worker restart or after bulk-loading new
    assets via a separate path.
    """
    try:
        from engines.semantic_search import SemanticSearchEngine
        engine = SemanticSearchEngine()
        # Reload pulls from sqlite3 — implemented as ``_load_from_db`` on
        # the engine; fall back to constructing a fresh instance which also
        # loads from disk.
        if hasattr(engine, "_load_from_db"):
            engine._load_from_db()
        size = len(getattr(engine, "_meta_by_id", {}))
        return {"ok": True, "indexed": size, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "task_id": self.request.id}
