"""P3-4-W1 cleaning-service routes — dynamic /api/v1/clean/{op_id} + /list.

Endpoints:
  GET  /healthz
  GET  /api/v1/clean/list                — all 32 operators
  GET  /api/v1/clean/list?modality=image — filter by modality
  GET  /api/v1/clean/{op_id}/schema      — params schema
  POST /api/v1/clean/{op_id}             — execute one operator
  POST /api/v1/clean/{op_id}/preview     — dry-run
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .operators import OPERATORS, OPERATOR_META, get_meta, get_operator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cleaning-service"])


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "cleaning-service",
        "version": "0.4.0",  # P3-4-W1
        "operator_count": len(OPERATORS),
    }


# ── /api/v1/clean/list ───────────────────────────────────────────────────────
@router.get("/api/v1/clean/list")
async def list_operators(
    modality: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the 32-operator metadata list, optionally filtered."""
    from .operators import list_operators as _list
    ops = _list(modality=modality, category=category)
    return {
        "count": len(ops),
        "total": len(OPERATORS),
        "filters": {"modality": modality, "category": category},
        "operators": ops,
    }


# ── /api/v1/clean/{op_id}/schema ─────────────────────────────────────────────
@router.get("/api/v1/clean/{op_id}/schema")
async def get_schema(op_id: str) -> Dict[str, Any]:
    meta = get_meta(op_id)
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    return {
        "id": meta["id"],
        "name": meta["name"],
        "category": meta["category"],
        "modality": meta["modality"],
        "description": meta.get("description", ""),
        "params": meta.get("params", []),
    }


# ── Dynamic /api/v1/clean/{op_id} ────────────────────────────────────────────
class ExecuteBody(BaseModel):
    data: Any = Field(..., description="Input — list[str|path|dict], str, or dict")
    params: Dict[str, Any] = Field(default_factory=dict)


def _ensure_list(data: Any) -> List[Any]:
    if isinstance(data, list):
        return data
    return [data]


def _wrap_output(op_id: str, data: Any, result: Any, is_list_in: bool) -> Any:
    """If the operator expected a single item (input wasn't a list), unwrap."""
    if is_list_in:
        return result
    if isinstance(result, list) and len(result) >= 1:
        return result[0]
    return result


@router.post("/api/v1/clean/{op_id}")
async def execute_operator(op_id: str, body: ExecuteBody) -> Dict[str, Any]:
    """Execute the operator. data: list of items (or single item)."""
    op = get_operator(op_id)
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    started = time.time()
    is_list = isinstance(body.data, list)
    items = _ensure_list(body.data)
    try:
        result = op(items, body.params or {})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("operator %s failed", op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"execute_failed: {e}")
    out = _wrap_output(op_id, body.data, result, is_list)

    # P4-4-W2: lineage hook — best-effort, never blocks the response
    try:
        from services.dataset_service.lineage.collector import record_operator
        # Use a synthetic dataset name based on the request's first item
        # to represent the "input dataset" the operator saw.
        in_id = ""
        if items and isinstance(items[0], dict):
            in_id = str(items[0].get("id", "")) or f"batch-{len(items)}"
        else:
            in_id = f"batch-{len(items)}"
        in_qn = f"ds.in.{op_id}.{in_id}" if in_id else f"ds.in.{op_id}"
        out_qn = f"ds.out.{op_id}.{in_id}" if in_id else f"ds.out.{op_id}"
        record_operator(
            operator_id=op_id,
            inputs=[in_qn],
            outputs=[out_qn],
            edge_type="cleaned_by",
            pipeline_id=body.params.get("pipeline_id", "") if isinstance(body.params, dict) else "",
        )
    except Exception:  # noqa: BLE001
        logger.debug("lineage hook failed for cleaning op %s", op_id, exc_info=True)

    return {
        "op_id": op_id,
        "ok": True,
        "input_count": len(items),
        "output_count": len(result) if isinstance(result, list) else 1,
        "result": out,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


@router.post("/api/v1/clean/{op_id}/preview")
async def preview_operator(op_id: str, body: ExecuteBody) -> Dict[str, Any]:
    """Dry-run: shallow copy of items, return before/after length + sample."""
    op = get_operator(op_id)
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    import copy
    items = _ensure_list(body.data)
    items_copy = copy.copy(items)  # shallow; operators shouldn't mutate
    try:
        result = op(items_copy, body.params or {})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"preview_failed: {e}")
    sample = result
    if isinstance(result, list) and len(result) > 5:
        sample = result[:5]
    return {
        "op_id": op_id,
        "input_count": len(items),
        "output_count": len(result) if isinstance(result, list) else 1,
        "sample": sample,
    }