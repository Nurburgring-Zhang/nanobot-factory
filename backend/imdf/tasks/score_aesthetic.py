"""
Async aesthetic scoring tasks (P2-1-W2)
=========================================

Tasks:
- `score_batch`  — score a list of image paths.
- `score_directory` — score every image file under a directory.
- `score_one` — score a single image (low overhead path).

These wrap AestheticScorer — Pillow-based metrics only, no external services.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from celery import shared_task

_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


def _result_to_dict(result) -> Dict[str, Any]:
    """AestheticResult is a dataclass — serialise via __dict__ for JSON output."""
    if result is None:
        return {"ok": False, "error": "scorer returned None"}
    if hasattr(result, "__dict__"):
        d = dict(result.__dict__)
        for k, v in list(d.items()):
            if hasattr(v, "__dict__"):
                d[k] = dict(v.__dict__)
        return {"ok": True, **d}
    return {"ok": True, "value": str(result)}


@shared_task(name="imdf.tasks.score_aesthetic.score_batch", bind=True, acks_late=True)
def score_batch(self, image_paths: List[str]) -> Dict[str, Any]:
    """Score a list of image paths."""
    from engines.aesthetic_scorer import AestheticScorer
    try:
        scorer = AestheticScorer()
        results = scorer.score_batch(list(image_paths or []))
        return {
            "ok": True,
            "count": len(results),
            "results": [_result_to_dict(r) for r in results],
            "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("score_batch failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.score_aesthetic.score_directory", bind=True, acks_late=True)
def score_directory(self, directory: str, extensions: List[str] = None) -> Dict[str, Any]:
    """Score every image under a directory."""
    from engines.aesthetic_scorer import AestheticScorer
    try:
        scorer = AestheticScorer()
        exts = tuple(extensions) if extensions else ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        results = scorer.score_directory(directory or ".", extensions=exts)
        return {
            "ok": True,
            "directory": directory,
            "count": len(results),
            "results": [_result_to_dict(r) for r in results],
            "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("score_directory failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.score_aesthetic.score_one", bind=True)
def score_one(self, image_path: str) -> Dict[str, Any]:
    """Score a single image — quick-path task used by /api/queue/score-on-demand."""
    from engines.aesthetic_scorer import AestheticScorer
    try:
        scorer = AestheticScorer()
        result = scorer.score_image(image_path or "")
        return {"ok": True, **_result_to_dict(result), "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "task_id": self.request.id}