"""P3-2-W2 + P3-4-W2 scoring-service routes — public REST surface.

Exposes:
  GET  /healthz                                — liveness
  GET  /api/v1/score/operators                 — list 15 scoring operators (legacy, P3-2-W2)
  GET  /api/v1/score/operators/{op_id}         — one operator's metadata (legacy)
  POST /api/v1/score/run                       — run one scorer (legacy)
  POST /api/v1/score/run/batch                 — run multiple scorers and aggregate (legacy)
  POST /api/v1/score/rank                      — score + rank a list of items (legacy)
  GET  /api/v1/score/list                      — list 15 scoring operators (P3-4-W2 modular)
  GET  /api/v1/score/{op_id}                   — one operator's metadata (P3-4-W2 modular)
  POST /api/v1/score/{op_id}/run               — run a single scorer (P3-4-W2 modular)

NOTE: Static-path routes (/list, /operators, /run, /run/batch, /rank) MUST be
registered BEFORE the dynamic /{op_id} route so FastAPI dispatches them
correctly (FastAPI matches in registration order; a dynamic route registered
first would otherwise capture static segments like "operators" or "run").
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Legacy registry (P3-2-W2 single-file pattern; renamed to _legacy_* for package coexistence)
from ._legacy_operators import SCORING_OPERATORS, get_operator_meta
from ._legacy_dispatch import apply_scorer

# New modular registry (P3-4-W2)
from .operators import OPERATORS as _NEW_OPERATORS, list_operators as _new_list, get_operator as _new_get

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scoring-service"])


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "scoring-service",
        "version": "0.1.0",
        "operator_count": len(_NEW_OPERATORS),
        "legacy_operator_count": len(SCORING_OPERATORS),
    }


# ════════════════════════════════════════════════════════════════════════════════
# Static-path routes — MUST come before the dynamic /{op_id} route
# ════════════════════════════════════════════════════════════════════════════════

# ── /api/v1/score/list (P3-4-W2 modular) ──────────────────────────────────────
@router.get("/api/v1/score/list")
async def list_score_operators(category: Optional[str] = None) -> Dict[str, Any]:
    """List all 15 scoring operators (P3-4-W2 modular registry)."""
    ops = _new_list()
    if category:
        ops = [o for o in ops if o.get("category") == category]
    return {"count": len(ops), "operators": ops, "registry": "modular"}


# ── /api/v1/score/operators (legacy, P3-2-W2) ────────────────────────────────
@router.get("/api/v1/score/operators")
async def list_operators(category: Optional[str] = None) -> Dict[str, Any]:
    ops = SCORING_OPERATORS
    if category:
        ops = [o for o in ops if o.get("category") == category]
    return {"count": len(ops), "operators": ops}


@router.get("/api/v1/score/operators/{op_id}")
async def get_operator(op_id: str) -> Dict[str, Any]:
    meta = get_operator_meta(op_id)
    if not meta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"scorer_not_found: {op_id}")
    return meta


# ── /api/v1/score/run (legacy, P3-2-W2) ───────────────────────────────────────
class ScoreRequest(BaseModel):
    op_id: str = Field(..., description="Scorer id (e.g. score.aesthetic)")
    data: Any = Field(..., description="Input — str / list[str] / list[dict]")
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/score/run")
async def run_scorer(req: ScoreRequest) -> Dict[str, Any]:
    started = time.time()
    meta = get_operator_meta(req.op_id)
    if not meta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"scorer_not_found: {req.op_id}")
    try:
        result = apply_scorer(req.op_id, req.data, req.params)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("score run failed: op=%s", req.op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"score_failed: {e}")
    return {
        "op_id": req.op_id,
        "ok": True,
        "result": result,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


class ScoreStep(BaseModel):
    op_id: str
    params: Dict[str, Any] = Field(default_factory=dict)


class BatchScoreRequest(BaseModel):
    steps: List[ScoreStep]
    data: Any


@router.post("/api/v1/score/run/batch")
async def run_batch(req: BatchScoreRequest) -> Dict[str, Any]:
    """Run multiple scorers and aggregate results."""
    started = time.time()
    scores: Dict[str, Any] = {}
    for i, step in enumerate(req.steps):
        meta = get_operator_meta(step.op_id)
        if not meta:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"step[{i}] scorer_not_found: {step.op_id}",
            )
        try:
            scores[step.op_id] = apply_scorer(step.op_id, req.data, step.params)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"step[{i}] score_failed: {e}",
            )
    return {
        "ok": True,
        "scores": scores,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


class RankRequest(BaseModel):
    op_id: str
    items: List[Any] = Field(..., description="Items to score and rank")
    params: Dict[str, Any] = Field(default_factory=dict)
    top_k: Optional[int] = None
    descending: bool = True


@router.post("/api/v1/score/rank")
async def rank_items(req: RankRequest) -> Dict[str, Any]:
    """Score each item, sort by primary score, return top-K."""
    started = time.time()
    meta = get_operator_meta(req.op_id)
    if not meta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"scorer_not_found: {req.op_id}")
    scored: List[Dict[str, Any]] = []
    for idx, item in enumerate(req.items):
        try:
            r = apply_scorer(req.op_id, item, req.params)
            primary = _extract_primary(r)
        except Exception as e:  # noqa: BLE001
            primary = 0.0
            r = {"error": str(e)}
        scored.append({"index": idx, "item": item, "score": primary, "detail": r})
    scored.sort(key=lambda x: x["score"], reverse=req.descending)
    if req.top_k:
        scored = scored[: req.top_k]
    return {
        "op_id": req.op_id,
        "ok": True,
        "count": len(scored),
        "ranking": scored,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


# ════════════════════════════════════════════════════════════════════════════════
# Dynamic routes — registered LAST so static paths take precedence
# ════════════════════════════════════════════════════════════════════════════════

# ── /api/v1/score/{op_id} (P3-4-W2 modular) ───────────────────────────────────
@router.get("/api/v1/score/{op_id}")
async def get_score_operator(op_id: str) -> Dict[str, Any]:
    """Get one scoring operator's metadata (P3-4-W2 modular)."""
    m = _new_get(op_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"scorer_not_found: {op_id}")
    return {
        "id": m.OP_ID,
        "name": m.NAME,
        "category": m.CATEGORY,
        "description": m.DESCRIPTION,
        "params": list(getattr(m, "PARAMS", []) or []),
    }


class ScoreModularRequest(BaseModel):
    data: Any = Field(..., description="Input — str / list[str] / list[dict]")
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/score/{op_id}/run")
async def run_score_operator(op_id: str, req: ScoreModularRequest) -> Dict[str, Any]:
    """Run a single scoring operator (P3-4-W2 modular)."""
    m = _new_get(op_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"scorer_not_found: {op_id}")
    started = time.time()
    try:
        result = m.run(req.data, req.params)
    except Exception as e:  # noqa: BLE001
        logger.exception("score %s failed", op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"score_failed: {e}")
    return {
        "op_id": op_id,
        "ok": True,
        "result": result,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _extract_primary(result: Any) -> float:
    """Pull a single comparable float out of a scorer result."""
    if isinstance(result, (int, float)):
        return float(result)
    if isinstance(result, dict):
        for k in ("overall", "score", "value", "primary", "mean",
                  "aesthetic", "technical", "clarity", "composition",
                  "color_harmony", "resolution_score", "noise_score",
                  "text_quality", "diversity", "safety", "relevance",
                  "preference", "difficulty", "creativity", "consistency"):
            if k in result and isinstance(result[k], (int, float)):
                return float(result[k])
        # If list of dicts with score
        if "scores" in result and isinstance(result["scores"], list) and result["scores"]:
            return _extract_primary(result["scores"][0])
    if isinstance(result, list) and result:
        return _extract_primary(result[0])
    return 0.0
