"""P3-5-W2 collection-service routes — dynamic /api/v1/collect/{op_id} + /list.

Endpoints:
  GET  /healthz
  GET  /api/v1/collect/list                 — all 15 operators
  GET  /api/v1/collect/list?source=...      — filter by source
  GET  /api/v1/collect/{op_id}/schema       — params schema
  POST /api/v1/collect/{op_id}              — execute one operator
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .operators import OPERATORS, list_operators as _list, get_operator, get_meta

logger = logging.getLogger(__name__)
router = APIRouter(tags=["collection-service"])


@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "collection-service",
        "version": "0.1.0",
        "operator_count": len(OPERATORS),
    }


@router.get("/api/v1/collect/list")
async def list_operators(
    source: Optional[str] = None,
    modality: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the 15-operator metadata list, optionally filtered."""
    ops = _list(source=source, modality=modality)
    return {
        "count": len(ops),
        "total": len(OPERATORS),
        "filters": {"source": source, "modality": modality},
        "operators": ops,
    }


@router.get("/api/v1/collect/{op_id}/schema")
async def get_schema(op_id: str) -> Dict[str, Any]:
    meta = get_meta(op_id)
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    return meta


class CollectRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048,
                       description="URL / search query / id / keyword")
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/collect/{op_id}")
async def execute_operator(op_id: str, body: CollectRequest) -> Dict[str, Any]:
    op = get_operator(op_id)
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    started = time.time()
    try:
        result = op(body.query, body.params or {})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("collection operator %s failed", op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"execute_failed: {e}")
    return {
        "op_id": op_id,
        "ok": True,
        "query": body.query,
        "result": result,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


__all__ = ["router"]
