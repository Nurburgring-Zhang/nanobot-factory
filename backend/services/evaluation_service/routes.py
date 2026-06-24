"""P3-2-W2 evaluation-service routes — public REST surface.

Exposes:
  GET  /healthz
  GET  /api/v1/evaluations/metrics/catalog
  POST /api/v1/evaluations                         — create evaluation task
  GET  /api/v1/evaluations                         — list evaluations
  GET  /api/v1/evaluations/{id}                    — task detail
  POST /api/v1/evaluations/{id}/run                — run the eval (synchronous mock)
  POST /api/v1/evaluations/{id}/cancel             — cancel
  GET  /api/v1/evaluations/{id}/results            — per-sample scores
  GET  /api/v1/evaluations/{id}/summary            — aggregate metrics
  POST /api/v1/evaluations/{id}/bad_cases/extract  — auto-extract bad cases
  GET  /api/v1/bad_cases                           — list bad cases
  GET  /api/v1/bad_cases/{id}                      — bad case detail
  PATCH /api/v1/bad_cases/{id}/status              — mark fixed/ignored
"""
from __future__ import annotations

import logging
import statistics
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .store import EvaluationStore
from .operators import OPERATORS, list_operators as _list_eval_ops, get_operator as _get_eval_op, get_meta as _get_eval_meta

logger = logging.getLogger(__name__)
router = APIRouter(tags=["evaluation-service"])

# Singleton store
import os
_DATA_DIR = os.environ.get("IMDF_DATA_DIR", "")
if _DATA_DIR:
    _STORE = EvaluationStore(data_dir=os.path.join(_DATA_DIR, "evaluations"))
else:
    _STORE = EvaluationStore(data_dir="imdf/data/evaluations")


# ── /api/v1/eval/* (P3-5-W2 — 10 evaluation operators) ──────────────────────
@router.get("/api/v1/eval/list")
async def eval_list(modality: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
    """Return the 10 evaluation operator metadata list."""
    ops = _list_eval_ops(modality=modality, category=category)
    return {
        "count": len(ops),
        "total": len(OPERATORS),
        "filters": {"modality": modality, "category": category},
        "operators": ops,
    }


@router.get("/api/v1/eval/{op_id}/schema")
async def eval_schema(op_id: str) -> Dict[str, Any]:
    meta = _get_eval_meta(op_id)
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    return meta


class EvalExecuteBody(BaseModel):
    items: List[Any] = Field(default_factory=list, description="Samples to score")
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/eval/{op_id}")
async def eval_execute(op_id: str, body: EvalExecuteBody) -> Dict[str, Any]:
    op = _get_eval_op(op_id)
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"operator_not_found: {op_id}")
    started = time.time()
    try:
        result = op(body.items, body.params or {})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("eval operator %s failed", op_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"execute_failed: {e}")
    out_count = len(result) if isinstance(result, list) else 1
    return {
        "op_id": op_id,
        "ok": True,
        "input_count": len(body.items),
        "output_count": out_count,
        "result": result,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "evaluation-service",
        "version": "0.1.0",
        "data_dir": str(_STORE.data_dir),
        "evaluation_count": _STORE.count_evaluations(),
        "bad_case_count": _STORE.count_bad_cases(),
    }


# ── /api/v1/evaluations/metrics/catalog ──────────────────────────────────────
@router.get("/api/v1/evaluations/metrics/catalog")
async def list_metrics() -> Dict[str, Any]:
    return {
        "count": 8,
        "metrics": [
            {"name": "accuracy", "description": "Classification accuracy (0-1)"},
            {"name": "f1_score", "description": "Macro F1 (0-1)"},
            {"name": "bleu", "description": "BLEU score (0-1)"},
            {"name": "rouge_l", "description": "ROUGE-L (0-1)"},
            {"name": "clip_score", "description": "CLIP image-text alignment (0-1)"},
            {"name": "aesthetic", "description": "Aesthetic score (0-100)"},
            {"name": "latency_p50_ms", "description": "Median inference latency (ms)"},
            {"name": "latency_p99_ms", "description": "p99 inference latency (ms)"},
        ],
    }


# ── /api/v1/evaluations ──────────────────────────────────────────────────────
class CreateEvalRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    model_name: str = Field(..., min_length=1)
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str = Field("v1")
    metrics: List[str] = Field(default_factory=lambda: ["accuracy", "f1_score"])
    sample_size: int = Field(100, ge=1, le=100_000)
    description: str = ""


@router.post("/api/v1/evaluations", status_code=status.HTTP_201_CREATED)
async def create_evaluation(req: CreateEvalRequest) -> Dict[str, Any]:
    valid = {"accuracy", "f1_score", "bleu", "rouge_l", "clip_score", "aesthetic",
             "latency_p50_ms", "latency_p99_ms"}
    bad = [m for m in req.metrics if m not in valid]
    if bad:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"invalid_metrics: {bad} (allowed: {sorted(valid)})",
        )
    e = _STORE.create_evaluation(
        name=req.name,
        model_name=req.model_name,
        dataset_name=req.dataset_name,
        dataset_version=req.dataset_version,
        metrics=req.metrics,
        sample_size=req.sample_size,
        description=req.description,
    )
    return e


@router.get("/api/v1/evaluations")
async def list_evaluations(
    model_name: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    evs = _STORE.list_evaluations(
        model_name=model_name, status_filter=status_filter, limit=limit, offset=offset
    )
    return {"count": len(evs), "evaluations": evs}


@router.get("/api/v1/evaluations/{eval_id}")
async def get_evaluation(eval_id: str) -> Dict[str, Any]:
    e = _STORE.get_evaluation(eval_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"evaluation_not_found: {eval_id}")
    return e


# ── /api/v1/evaluations/{id}/run ─────────────────────────────────────────────
@router.post("/api/v1/evaluations/{eval_id}/run")
async def run_evaluation(eval_id: str) -> Dict[str, Any]:
    e = _STORE.get_evaluation(eval_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"evaluation_not_found: {eval_id}")
    if e["status"] in ("running", "success"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"evaluation_already_{e['status']}",
        )
    _STORE.update_evaluation(eval_id, status="running", started_at=_now_iso())

    # Synchronous mock run: produce per-sample + aggregate metrics
    n = e["sample_size"]
    sample_results = _simulate_run(e, n)
    summary = _aggregate_metrics(sample_results, e["metrics"])

    _STORE.update_evaluation(
        eval_id,
        status="success",
        completed_at=_now_iso(),
        sample_results=sample_results,
        summary=summary,
    )
    return {
        "id": eval_id,
        "status": "success",
        "sample_count": n,
        "summary": summary,
    }


@router.post("/api/v1/evaluations/{eval_id}/cancel")
async def cancel_evaluation(eval_id: str) -> Dict[str, Any]:
    e = _STORE.get_evaluation(eval_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"evaluation_not_found: {eval_id}")
    _STORE.update_evaluation(eval_id, status="cancelled", completed_at=_now_iso())
    return {"id": eval_id, "status": "cancelled"}


@router.get("/api/v1/evaluations/{eval_id}/results")
async def get_results(eval_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    e = _STORE.get_evaluation(eval_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"evaluation_not_found: {eval_id}")
    results = e.get("sample_results", [])
    return {
        "id": eval_id,
        "total": len(results),
        "limit": limit,
        "offset": offset,
        "results": results[offset : offset + limit],
    }


@router.get("/api/v1/evaluations/{eval_id}/summary")
async def get_summary(eval_id: str) -> Dict[str, Any]:
    e = _STORE.get_evaluation(eval_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"evaluation_not_found: {eval_id}")
    return {
        "id": eval_id,
        "name": e["name"],
        "model_name": e["model_name"],
        "dataset_name": e["dataset_name"],
        "dataset_version": e["dataset_version"],
        "status": e["status"],
        "summary": e.get("summary", {}),
        "created_at": e["created_at"],
        "completed_at": e.get("completed_at", ""),
    }


# ── /api/v1/evaluations/{id}/bad_cases/extract ──────────────────────────────
@router.post("/api/v1/evaluations/{eval_id}/bad_cases/extract")
async def extract_bad_cases(eval_id: str, threshold: float = 0.5) -> Dict[str, Any]:
    e = _STORE.get_evaluation(eval_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"evaluation_not_found: {eval_id}")
    if e["status"] != "success":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"evaluation_not_success (current={e['status']})",
        )
    results = e.get("sample_results", [])
    bad_ids: List[str] = []
    for r in results:
        primary = r.get("scores", {}).get("accuracy")
        if primary is not None and primary < threshold:
            bc = _STORE.add_bad_case(
                evaluation_id=eval_id,
                sample_id=r["sample_id"],
                reason=f"accuracy<{threshold}",
                sample=r,
            )
            bad_ids.append(bc["id"])
    return {"evaluation_id": eval_id, "extracted": len(bad_ids), "bad_case_ids": bad_ids}


# ── /api/v1/bad_cases ────────────────────────────────────────────────────────
@router.get("/api/v1/bad_cases")
async def list_bad_cases(
    evaluation_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    items = _STORE.list_bad_cases(
        evaluation_id=evaluation_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return {"count": len(items), "bad_cases": items}


@router.get("/api/v1/bad_cases/{case_id}")
async def get_bad_case(case_id: str) -> Dict[str, Any]:
    bc = _STORE.get_bad_case(case_id)
    if not bc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"bad_case_not_found: {case_id}")
    return bc


class BadCaseStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|fixed|ignored|wontfix)$")
    note: str = ""


@router.patch("/api/v1/bad_cases/{case_id}/status")
async def update_bad_case_status(case_id: str, body: BadCaseStatusUpdate) -> Dict[str, Any]:
    bc = _STORE.update_bad_case(case_id, status=body.status, note=body.note)
    if not bc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"bad_case_not_found: {case_id}")
    return bc


# ── helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _simulate_run(evaluation: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
    """Generate n synthetic per-sample results, deterministic by id+model."""
    seed = f"{evaluation['id']}:{evaluation['model_name']}"
    import hashlib
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    base_acc = ((h % 50) + 50) / 100.0  # 0.5 - 0.99
    out: List[Dict[str, Any]] = []
    for i in range(n):
        # Slight per-sample noise
        noise = (((h + i * 37) % 200) - 100) / 1000.0
        acc = max(0.0, min(1.0, base_acc + noise))
        scores: Dict[str, float] = {}
        for m in evaluation["metrics"]:
            if m == "accuracy":
                scores[m] = round(acc, 4)
            elif m == "f1_score":
                scores[m] = round(acc * 0.95, 4)
            elif m == "bleu":
                scores[m] = round(0.3 + acc * 0.4, 4)
            elif m == "rouge_l":
                scores[m] = round(0.4 + acc * 0.4, 4)
            elif m == "clip_score":
                scores[m] = round(0.2 + acc * 0.5, 4)
            elif m == "aesthetic":
                scores[m] = round(50 + acc * 40, 2)
            elif m == "latency_p50_ms":
                scores[m] = round(80 + (1 - acc) * 200, 2)
            elif m == "latency_p99_ms":
                scores[m] = round(120 + (1 - acc) * 400, 2)
        out.append({
            "sample_id": f"sample_{i:05d}",
            "scores": scores,
        })
    return out


def _aggregate_metrics(
    sample_results: List[Dict[str, Any]], metrics: List[str]
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for m in metrics:
        vals = [
            r["scores"][m]
            for r in sample_results
            if isinstance(r.get("scores", {}).get(m), (int, float))
        ]
        if not vals:
            out[m] = 0.0
            continue
        if m in ("latency_p50_ms", "latency_p99_ms"):
            out[m] = round(statistics.median(vals), 2)
        else:
            out[m] = round(sum(vals) / len(vals), 4)
    return out
