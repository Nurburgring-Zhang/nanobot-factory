"""P3-2-W2 dataset-service routes — public REST surface.

Exposes:
  GET  /healthz
  GET  /api/v1/datasets                          — list datasets
  POST /api/v1/datasets                          — create new dataset
  GET  /api/v1/datasets/{name}                   — dataset metadata
  DELETE /api/v1/datasets/{name}                 — delete dataset
  GET  /api/v1/datasets/{name}/versions          — list versions
  POST /api/v1/datasets/{name}/versions          — create version (incremental)
  GET  /api/v1/datasets/{name}/versions/{v}      — version metadata
  GET  /api/v1/datasets/{name}/versions/{v}/samples — list samples (paginated)
  POST /api/v1/datasets/{name}/versions/{v}/samples — add samples
  POST /api/v1/datasets/{name}/versions/{v}/export — export to jsonl/parquet

  P3-4-W2 additions:
  GET  /api/v1/dataset/filter/list               — list 10 filter operators
  GET  /api/v1/dataset/filter/{op_id}            — filter op metadata
  POST /api/v1/dataset/filter/{op_id}/run        — run filter op on data
  GET  /api/v1/dataset/export/list               — list 12 export operators
  GET  /api/v1/dataset/export/{op_id}            — export op metadata
  POST /api/v1/dataset/export/{op_id}/run        — run export op (writes to path/dir)
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .store import DatasetStore

# P3-4-W2 modular registries
from .operators import OPERATORS as FILTER_OPERATORS, list_operators as _filter_list, get_operator as _filter_get
from .exporters import OPERATORS as EXPORT_OPERATORS, list_operators as _export_list, get_operator as _export_get

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dataset-service"])

# Module-level store (singleton, in-memory; persists to /app/data or env)
_DATA_DIR = os.environ.get("IMDF_DATA_DIR", "")
if _DATA_DIR:
    _STORE = DatasetStore(data_dir=os.path.join(_DATA_DIR, "datasets"))
else:
    _STORE = DatasetStore(data_dir="imdf/data/datasets")


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "dataset-service",
        "version": "0.1.0",
        "data_dir": str(_STORE.data_dir),
        "dataset_count": _STORE.count_datasets(),
    }


# ── /api/v1/datasets ─────────────────────────────────────────────────────────
class CreateDatasetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    data_type: str = Field("image", pattern="^(image|text|video|audio|multimodal)$")
    tags: List[str] = Field(default_factory=list)


@router.post("/api/v1/datasets", status_code=status.HTTP_201_CREATED)
async def create_dataset(req: CreateDatasetRequest) -> Dict[str, Any]:
    try:
        ds = _STORE.create_dataset(
            name=req.name,
            description=req.description,
            data_type=req.data_type,
            tags=req.tags,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ds


@router.get("/api/v1/datasets")
async def list_datasets() -> Dict[str, Any]:
    return {"count": _STORE.count_datasets(), "datasets": _STORE.list_datasets()}


@router.get("/api/v1/datasets/{name}")
async def get_dataset(name: str) -> Dict[str, Any]:
    ds = _STORE.get_dataset(name)
    if not ds:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"dataset_not_found: {name}")
    return ds


@router.delete("/api/v1/datasets/{name}")
async def delete_dataset(name: str) -> Dict[str, Any]:
    deleted = _STORE.delete_dataset(name)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"dataset_not_found: {name}")
    return {"success": True, "name": name}


# ── /api/v1/datasets/{name}/versions ────────────────────────────────────────
class CreateVersionRequest(BaseModel):
    version: Optional[str] = None  # auto-generate if missing
    parent_version: Optional[str] = None
    description: str = ""
    tags: List[str] = Field(default_factory=list)


@router.post("/api/v1/datasets/{name}/versions", status_code=status.HTTP_201_CREATED)
async def create_version(name: str, req: CreateVersionRequest) -> Dict[str, Any]:
    if not _STORE.get_dataset(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"dataset_not_found: {name}")
    try:
        v = _STORE.create_version(
            dataset_name=name,
            version=req.version or f"v{time.strftime('%Y%m%d.%H%M%S')}",
            parent=req.parent_version,
            description=req.description,
            tags=req.tags,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    return v


@router.get("/api/v1/datasets/{name}/versions")
async def list_versions(name: str) -> Dict[str, Any]:
    if not _STORE.get_dataset(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"dataset_not_found: {name}")
    return {"dataset": name, "versions": _STORE.list_versions(name)}


@router.get("/api/v1/datasets/{name}/versions/{version}")
async def get_version(name: str, version: str) -> Dict[str, Any]:
    v = _STORE.get_version(name, version)
    if not v:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"version_not_found: {name}@{version}",
        )
    return v


# ── /api/v1/datasets/{name}/versions/{v}/samples ────────────────────────────
class AddSamplesRequest(BaseModel):
    samples: List[Dict[str, Any]] = Field(..., min_length=1)


@router.post(
    "/api/v1/datasets/{name}/versions/{version}/samples",
    status_code=status.HTTP_201_CREATED,
)
async def add_samples(name: str, version: str, req: AddSamplesRequest) -> Dict[str, Any]:
    try:
        added = _STORE.add_samples(name, version, req.samples)
    except KeyError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"success": True, "added": added}


@router.get("/api/v1/datasets/{name}/versions/{version}/samples")
async def list_samples(
    name: str, version: str, limit: int = 50, offset: int = 0
) -> Dict[str, Any]:
    v = _STORE.get_version(name, version)
    if not v:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"version_not_found: {name}@{version}",
        )
    samples = _STORE.list_samples(name, version, limit=limit, offset=offset)
    return {
        "dataset": name,
        "version": version,
        "limit": limit,
        "offset": offset,
        "count": len(samples),
        "samples": samples,
    }


# ── /api/v1/datasets/{name}/versions/{v}/export ──────────────────────────────
class ExportRequest(BaseModel):
    format: str = Field("jsonl", pattern="^(jsonl|json|csv)$")


@router.post("/api/v1/datasets/{name}/versions/{version}/export")
async def export_version(
    name: str, version: str, req: ExportRequest
) -> Dict[str, Any]:
    v = _STORE.get_version(name, version)
    if not v:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"version_not_found: {name}@{version}",
        )
    samples = _STORE.list_samples(name, version, limit=10_000_000, offset=0)
    export_id = uuid.uuid4().hex[:12]
    body = {
        "export_id": export_id,
        "dataset": name,
        "version": version,
        "format": req.format,
        "sample_count": len(samples),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples_preview": samples[:5],
    }
    return body


# ════════════════════════════════════════════════════════════════════════════════
# P3-4-W2 modular operators (filter + export)
# ════════════════════════════════════════════════════════════════════════════════

# ── /api/v1/dataset/filter/list ────────────────────────────────────────────────
@router.get("/api/v1/dataset/filter/list")
async def list_filter_operators(category: Optional[str] = None) -> Dict[str, Any]:
    """List all 10 filter operators (P3-4-W2 modular)."""
    ops = _filter_list()
    if category:
        ops = [o for o in ops if o.get("category") == category]
    return {"count": len(ops), "operators": ops, "registry": "modular"}


@router.get("/api/v1/dataset/filter/{op_id}")
async def get_filter_operator(op_id: str) -> Dict[str, Any]:
    m = _filter_get(op_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"filter_not_found: {op_id}")
    return {
        "id": m.OP_ID,
        "name": m.NAME,
        "category": m.CATEGORY,
        "description": m.DESCRIPTION,
        "params": list(getattr(m, "PARAMS", []) or []),
    }


class FilterRunRequest(BaseModel):
    data: Any = Field(..., description="Input — list of dicts/numbers to filter")
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/dataset/filter/{op_id}/run")
async def run_filter_operator(op_id: str, req: FilterRunRequest) -> Dict[str, Any]:
    """Run a single filter operator (P3-4-W2 modular)."""
    m = _filter_get(op_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"filter_not_found: {op_id}")
    started = time.time()
    try:
        result = m.run(req.data, req.params)
    except Exception as e:  # noqa: BLE001
        logger.exception("filter %s failed", op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"filter_failed: {e}")
    return {
        "op_id": op_id,
        "ok": True,
        "result": result,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


# ── /api/v1/dataset/export/list ────────────────────────────────────────────────
@router.get("/api/v1/dataset/export/list")
async def list_export_operators(category: Optional[str] = None) -> Dict[str, Any]:
    """List all 12 export operators (P3-4-W2 modular)."""
    ops = _export_list()
    if category:
        ops = [o for o in ops if o.get("category") == category]
    return {"count": len(ops), "operators": ops, "registry": "modular"}


@router.get("/api/v1/dataset/export/{op_id}")
async def get_export_operator(op_id: str) -> Dict[str, Any]:
    m = _export_get(op_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"export_not_found: {op_id}")
    return {
        "id": m.OP_ID,
        "name": m.NAME,
        "category": m.CATEGORY,
        "description": m.DESCRIPTION,
        "params": list(getattr(m, "PARAMS", []) or []),
    }


class ExportRunRequest(BaseModel):
    data: Any = Field(..., description="Input — list of dicts/numbers to export")
    params: Dict[str, Any] = Field(default_factory=dict,
        description="Exporter-specific params (path / dir / etc.)")


@router.post("/api/v1/dataset/export/{op_id}/run")
async def run_export_operator(op_id: str, req: ExportRunRequest) -> Dict[str, Any]:
    """Run a single export operator (writes files to disk)."""
    m = _export_get(op_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"export_not_found: {op_id}")
    started = time.time()
    try:
        result = m.run(req.data, req.params)
    except Exception as e:  # noqa: BLE001
        logger.exception("export %s failed", op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"export_failed: {e}")
    return {
        "op_id": op_id,
        "ok": result.get("ok", True) if isinstance(result, dict) else True,
        "result": result,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
