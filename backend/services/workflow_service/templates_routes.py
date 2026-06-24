"""P3-6-W1: Basic workflow template routes (采集/清洗/标注/评分/筛选 25 项).

Public REST surface (mounted under ``/api/v1/workflow/templates``):

  GET    /api/v1/workflow/templates                  list 25 templates
  GET    /api/v1/workflow/templates/categories       category summary
  GET    /api/v1/workflow/templates/{template_id}    one template detail
  POST   /api/v1/workflow/templates/{template_id}/run
                                                     dry-run (mock step exec)

The legacy ``/api/v1/workflows/...`` routes from ``routes.py`` are kept
unchanged for backward compatibility; this module adds a parallel
``/api/v1/workflow/...`` (singular workflow) surface for the basic
template registry.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.workflow_service.basic_templates import (
    TEMPLATES,
    categories_with_count,
    get as get_template,
    list_by_category,
    list_categories,
)

# P3-6-W1: import the deeper business_templates registry (11 entries:
# 5 export + 5 feedback + 1 pipeline, ids tpl-bz2-*).
try:
    from services.workflow_service.business_templates import (
        TEMPLATES as BIZ2_TEMPLATES,
        categories_with_count as biz2_categories_with_count,
        list_categories as biz2_list_categories,
    )
    HAS_BIZ2 = True
except Exception as _biz2_e:  # noqa: BLE001
    import logging
    logging.getLogger(__name__).warning(
        "business_templates import failed: %s", _biz2_e)
    BIZ2_TEMPLATES = []
    biz2_categories_with_count = lambda: {}  # noqa: E731
    biz2_list_categories = lambda: []  # noqa: E731
    HAS_BIZ2 = False

# Combined catalog = 25 basic + 11 business_templates_v2 = 36 by default.
# The basic-templatess registry already includes the 25 W2 business
# templates in the legacy list-style files, so to avoid double-counting
# we only merge the 11 NEW business templates here. When callers need
# the full 103-entry legacy+basic+biz2 catalog, they can call
# /api/v1/workflows/templates (the plural routes.py surface).
_COMBINED_TEMPLATES = list(TEMPLATES) + list(BIZ2_TEMPLATES)
_COMBINED_CATEGORIES = (
    list_categories() + (biz2_list_categories() if HAS_BIZ2 else [])
)
_COMBINED_COUNTS: Dict[str, int] = {}
for _c, _n in categories_with_count().items():
    _COMBINED_COUNTS[_c] = _n
if HAS_BIZ2:
    for _c, _n in biz2_categories_with_count().items():
        _COMBINED_COUNTS[_c] = _COMBINED_COUNTS.get(_c, 0) + _n

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow/templates", tags=["workflow-templates"])


# =====================================================================
# Pydantic models
# =====================================================================

class RunRequest(BaseModel):
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="模板 inputs 覆盖; 未提供则用模板默认值")
    dry_run: bool = Field(
        default=True,
        description="true = mock step execution, false = schedule real run")
    trigger: str = Field(default="manual", max_length=32)


class StepResult(BaseModel):
    id: str
    name: str
    operator: str
    status: str
    duration_ms: int
    output_preview: Optional[Dict[str, Any]] = None


class RunResponse(BaseModel):
    run_id: str
    template_id: str
    template_name: str
    category: str
    status: str
    trigger: str
    dry_run: bool
    started_at: str
    finished_at: str
    duration_ms: int
    step_count: int
    steps: List[StepResult]
    metrics: Dict[str, Any]


# =====================================================================
# Helpers
# =====================================================================

def _now() -> str:
    return datetime.utcnow().isoformat()


def _hash_inputs(inputs: Dict[str, Any]) -> str:
    """Stable hash of inputs for deterministic run_id component."""
    import json
    s = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _default_for_input(spec: Dict[str, Any]) -> Any:
    """Return the template input's default value, respecting the spec."""
    if "default" in spec:
        return spec["default"]
    t = spec.get("type", "string")
    if t in ("int", "integer"):
        return 0
    if t in ("float", "number"):
        return 0.0
    if t in ("bool", "boolean"):
        return False
    if t == "array":
        return []
    if t == "object":
        return {}
    return None


def _mock_step_exec(step: Dict[str, Any], inputs: Dict[str, Any]) -> StepResult:
    """Dry-run a single step: report a deterministic mock result.

    Real implementations would dispatch on ``step['operator']``; here we
    always return a structured preview so the endpoint is hermetic.
    """
    op = step.get("operator", "")
    duration_ms = (hash(op) & 0xFFFF) % 200 + 5  # 5-205 ms mock
    output_preview: Dict[str, Any] = {
        "operator": op,
        "config_keys": list(step.get("config", {}).keys()),
        "mock": True,
    }
    return StepResult(
        id=step["id"],
        name=step["name"],
        operator=op,
        status="ok",
        duration_ms=duration_ms,
        output_preview=output_preview,
    )


# =====================================================================
# Endpoints
# =====================================================================

@router.get("")
@router.get("/")
async def list_templates(
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """List workflow templates (25 basic + 11 business v2 = 36 by default).

    Optional ``?category=collection|cleaning|annotation|scoring|filter|
    export|feedback|pipeline``.
    """
    items = _COMBINED_TEMPLATES
    if category:
        if category not in _COMBINED_CATEGORIES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"unknown_category: {category!r}")
        # category union across both registries
        items = [t for t in _COMBINED_TEMPLATES
                 if t.get("category") == category]
    return {
        "total": len(items),
        "categories": _COMBINED_CATEGORIES,
        "counts_by_category": _COMBINED_COUNTS,
        "items": items,
    }


@router.get("/categories")
async def get_categories() -> Dict[str, Any]:
    """Return all categories with counts (basic + business v2)."""
    return {
        "categories": _COMBINED_CATEGORIES,
        "counts": _COMBINED_COUNTS,
        "total": len(_COMBINED_TEMPLATES),
    }


@router.get("/{template_id}")
async def get_one(template_id: str) -> Dict[str, Any]:
    """Return the full template detail (incl. inputs/steps/metrics).

    Looks up across both ``basic_templates`` (25 entries) and
    ``business_templates`` (11 v2 entries).
    """
    tpl = get_template(template_id)
    if tpl is None and HAS_BIZ2:
        from services.workflow_service.business_templates import (
            get as _biz2_get,
        )
        tpl = _biz2_get(template_id)
    if tpl is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"template_not_found: {template_id}")
    return tpl


@router.post("/{template_id}/run", response_model=RunResponse)
async def run_template(template_id: str, body: RunRequest) -> RunResponse:
    """Dry-run (or schedule) a template.

    By default ``dry_run=true`` — every step is mocked and the response
    contains per-step status + duration. ``dry_run=false`` returns a
    stub ``status=scheduled`` response (real execution is owned by the
    DAG runtime in ``services.workflow_service.dag``).
    """
    tpl = get_template(template_id)
    if tpl is None and HAS_BIZ2:
        from services.workflow_service.business_templates import (
            get as _biz2_get,
        )
        tpl = _biz2_get(template_id)
    if tpl is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"template_not_found: {template_id}")

    # Resolve effective inputs (request overrides > template default)
    effective: Dict[str, Any] = {}
    for k, spec in tpl.get("inputs", {}).items():
        effective[k] = _default_for_input(spec)
    effective.update(body.inputs)

    started_at = _now()
    t0 = time.perf_counter()

    if body.dry_run:
        steps: List[StepResult] = []
        for step in tpl["steps"]:
            steps.append(_mock_step_exec(step, effective))
        duration_ms = int((time.perf_counter() - t0) * 1000)
        run_id = (
            f"dry-{template_id}-"
            f"{uuid.uuid4().hex[:8]}-{_hash_inputs(effective)}"
        )
        return RunResponse(
            run_id=run_id,
            template_id=template_id,
            template_name=tpl["name"],
            category=tpl["category"],
            status="completed",
            trigger=body.trigger,
            dry_run=True,
            started_at=started_at,
            finished_at=_now(),
            duration_ms=duration_ms,
            step_count=len(steps),
            steps=steps,
            metrics={
                "operator_count": len({
                    s.operator for s in steps
                }),
                "step_count": len(steps),
                "inputs_count": len(effective),
                "outputs_declared": len(tpl.get("outputs", [])),
            },
        )

    # Non dry-run: hand off to DAG runtime (stub here)
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    logger.info(
        "scheduled run %s for template %s (inputs=%d)",
        run_id, template_id, len(effective))
    return RunResponse(
        run_id=run_id,
        template_id=template_id,
        template_name=tpl["name"],
        category=tpl["category"],
        status="scheduled",
        trigger=body.trigger,
        dry_run=False,
        started_at=started_at,
        finished_at=started_at,
        duration_ms=0,
        step_count=len(tpl["steps"]),
        steps=[],
        metrics={
            "note": "non-dry-run handoff is owned by DAG runtime",
            "steps_planned": len(tpl["steps"]),
        },
    )


__all__ = ["router"]