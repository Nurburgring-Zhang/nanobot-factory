"""VDP-2026 R4 — Multimodal coordinator HTTP routes.

  GET    /api/v1/multimodal_v2/modalities             8 modalities
  GET    /api/v1/multimodal_v2/modalities/{key}      one
  GET    /api/v1/multimodal_v2/exports                9 export formats
  GET    /api/v1/multimodal_v2/describe               modalities + exports + format map
  POST   /api/v1/multimodal_v2/run                    run a multi-step modal pipeline
  GET    /api/v1/multimodal_v2/runs                   history (filter by modality)
  GET    /api/v1/multimodal_v2/health
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body

from .engine import (
    MultimodalPipeline, get_pipeline, EXPORTS,
    configure_db, MODALITIES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/multimodal_v2", tags=["multimodal_v2"])


@router.get("/modalities")
async def list_modalities() -> Dict[str, Any]:
    return {"total": len(MODALITIES), "items": [m.to_dict() for m in MODALITIES.values()]}


@router.get("/modalities/{key}")
async def get_modality(key: str) -> Dict[str, Any]:
    if key not in MODALITIES:
        raise HTTPException(404, f"未知模态: {key}")  # noqa: B904
    return MODALITIES[key].to_dict()


@router.get("/exports")
async def list_exports() -> Dict[str, Any]:
    return {"total": len(EXPORTS), "items": [e.to_dict() for e in EXPORTS]}


@router.get("/describe")
async def describe() -> Dict[str, Any]:
    return get_pipeline().describe()


@router.post("/run")
async def run_pipeline(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    modality = payload.get("modality")
    if modality not in MODALITIES:
        raise HTTPException(400, f"未知模态: {modality}")  # noqa: B904
    pipeline = get_pipeline()
    run = pipeline.run(
        modality=modality,
        inputs=payload.get("inputs", {}),
        spec=payload.get("spec", {}),
        actor=payload.get("actor", "system"),
    )
    return run.to_dict()


@router.get("/runs")
async def list_runs(
    modality: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    pipeline = get_pipeline()
    runs = pipeline.list_runs(modality=modality, limit=limit)
    return {"total": len(runs), "items": runs}


@router.get("/health")
async def health() -> Dict[str, Any]:
    pipeline = get_pipeline()
    return {
        "status": "ok",
        "modalities": len(MODALITIES),
        "exports": len(EXPORTS),
        "runs_in_db": len(pipeline.list_runs(limit=500)),
    }
