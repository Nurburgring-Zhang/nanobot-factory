"""P4-5-W2: FastAPI routes for iterative sessions + multi-agent runs + consistency.

Endpoints
---------
    /api/v1/assets/sessions                GET (list), POST (create)
    /api/v1/assets/sessions/{id}           GET, PATCH (finalize/discard), DELETE
    /api/v1/assets/sessions/{id}/iterate   POST  (multi-turn dialogue)
    /api/v1/assets/sessions/{id}/feedback  POST
    /api/v1/assets/sessions/{id}/assets    GET
    /api/v1/assets/sessions/{id}/ab_test   POST (start), GET (list)
    /api/v1/assets/sessions/{id}/ab_test/{ab_id}/score  POST
    /api/v1/assets/sessions/{id}/ab_test/{ab_id}/best   POST (pick winner)
    /api/v1/assets/agents                  GET (list 7 agents + status)
    /api/v1/assets/multi_generate          POST (start orchestrator)
    /api/v1/assets/multi_generate/runs     GET
    /api/v1/assets/multi_generate/runs/{run_id}  GET
    /api/v1/assets/consistency/run         POST
    /api/v1/assets/consistency/report      GET
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from .agents import AGENT_REGISTRY, MultiAgentOrchestrator, get_orchestrator, list_agents
from .consistency import ConsistencyConfig, ConsistencyWorkflow, get_workflow
from .session import SessionState, SessionStore, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assets", tags=["asset-iteration"])


# ── Request models ──────────────────────────────────────────────────────────
class CreateSessionRequest(BaseModel):
    owner_id: str
    project_id: str
    modality: str = Field(default="image")
    initial_prompt: str
    params: Optional[Dict[str, Any]] = None
    title: Optional[str] = None


class IterateRequest(BaseModel):
    text: str
    parent_version_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=-1, le=5)
    text: Optional[str] = None
    asset_id: Optional[str] = None


class AssetRequest(BaseModel):
    prompt_version_id: str
    modality: str
    url: str
    seed: int = 0
    metrics: Optional[Dict[str, Any]] = None


class ABVariant(BaseModel):
    text: str
    params: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class ABStartRequest(BaseModel):
    parent_prompt_version_id: str
    variants: List[ABVariant] = Field(min_length=2)


class ABScoreRequest(BaseModel):
    scores: Dict[str, float]


class MultiGenerateRequest(BaseModel):
    brief: Dict[str, Any]
    character_pool: Optional[Dict[str, Dict[str, Any]]] = None
    scenes: Optional[List[Dict[str, Any]]] = None
    parallel: bool = True


class ConsistencyRunRequest(BaseModel):
    project_id: str
    brief: Dict[str, Any]
    config: Optional[Dict[str, Any]] = None
    character_pool: Optional[Dict[str, Dict[str, Any]]] = None


# ── Helpers ────────────────────────────────────────────────────────────────
def _store() -> SessionStore:
    return get_session_store()


def _workflow() -> ConsistencyWorkflow:
    return get_workflow()


def _orchestrator() -> MultiAgentOrchestrator:
    return get_orchestrator()


def _session_or_404(session_id: str) -> Dict[str, Any]:
    row = _store().get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return row


# ── Session CRUD ───────────────────────────────────────────────────────────
@router.get("/sessions")
async def list_sessions(
    owner_id: Optional[str] = None,
    project_id: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    rows = _store().list_sessions(owner_id=owner_id, project_id=project_id, state=state, limit=limit, offset=offset)
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSessionRequest) -> Dict[str, Any]:
    row = _store().create_session(
        owner_id=body.owner_id,
        project_id=body.project_id,
        modality=body.modality,
        initial_prompt=body.initial_prompt,
        params=body.params,
        title=body.title,
    )
    return row


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    sess = _session_or_404(session_id)
    assets = _store().list_assets(session_id)
    feedback = _store().list_feedback(session_id)
    ab = _store().list_ab(session_id)
    return {
        **sess,
        "assets": assets,
        "feedback": feedback,
        "ab_tests": ab,
    }


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    action = (body or {}).get("action")
    if action == "finalize":
        row = _store().finalize(session_id)
    elif action == "discard":
        row = _store().discard(session_id)
    else:
        raise HTTPException(status_code=400, detail="action must be 'finalize' or 'discard'")
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return row


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> None:
    if not _store().delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")


@router.post("/sessions/{session_id}/iterate", status_code=status.HTTP_201_CREATED)
async def iterate_session(session_id: str, body: IterateRequest) -> Dict[str, Any]:
    pv = _store().iterate_prompt(
        session_id,
        body.text,
        parent_version_id=body.parent_version_id,
        params=body.params,
        note=body.note,
    )
    if pv is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found or discarded")
    sess = _store().get_session(session_id)
    return {"prompt_version": pv.__dict__, "session": sess}


@router.post("/sessions/{session_id}/feedback", status_code=status.HTTP_201_CREATED)
async def add_feedback(session_id: str, body: FeedbackRequest) -> Dict[str, Any]:
    row = _store().add_feedback(session_id, body.rating, body.text, body.asset_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return row


@router.get("/sessions/{session_id}/feedback")
async def list_feedback(session_id: str) -> Dict[str, Any]:
    _session_or_404(session_id)
    return {"items": _store().list_feedback(session_id), "count": len(_store().list_feedback(session_id))}


@router.post("/sessions/{session_id}/assets", status_code=status.HTTP_201_CREATED)
async def add_asset(session_id: str, body: AssetRequest) -> Dict[str, Any]:
    row = _store().add_asset(
        session_id,
        prompt_version_id=body.prompt_version_id,
        modality=body.modality,
        url=body.url,
        seed=body.seed,
        metrics=body.metrics,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return row


@router.get("/sessions/{session_id}/assets")
async def list_assets(session_id: str) -> Dict[str, Any]:
    _session_or_404(session_id)
    rows = _store().list_assets(session_id)
    return {"items": rows, "count": len(rows)}


# ── A/B testing ────────────────────────────────────────────────────────────
@router.post("/sessions/{session_id}/ab_test", status_code=status.HTTP_201_CREATED)
async def start_ab(session_id: str, body: ABStartRequest) -> Dict[str, Any]:
    row = _store().start_ab(
        session_id,
        parent_prompt_version_id=body.parent_prompt_version_id,
        variants=[v.model_dump() for v in body.variants],
    )
    if not row:
        raise HTTPException(status_code=400, detail="A/B requires ≥2 variants and an existing session")
    return row


@router.get("/sessions/{session_id}/ab_test")
async def list_ab(session_id: str) -> Dict[str, Any]:
    _session_or_404(session_id)
    rows = _store().list_ab(session_id)
    return {"items": rows, "count": len(rows)}


@router.post("/sessions/{session_id}/ab_test/{ab_id}/score")
async def score_ab(session_id: str, ab_id: str, body: ABScoreRequest) -> Dict[str, Any]:
    row = _store().score_ab(ab_id, body.scores)
    if not row:
        raise HTTPException(status_code=404, detail=f"A/B {ab_id} not found")
    return row


@router.post("/sessions/{session_id}/ab_test/{ab_id}/best")
async def pick_best(session_id: str, ab_id: str) -> Dict[str, Any]:
    row = _store().pick_best(ab_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"A/B {ab_id} not found or not yet scored")
    return row


# ── Multi-Agent ────────────────────────────────────────────────────────────
@router.get("/agents")
async def agents_endpoint() -> Dict[str, Any]:
    items = list_agents()
    return {
        "items": items,
        "count": len(items),
        "active_runs": len(_orchestrator().history(limit=100)),
    }


@router.post("/multi_generate", status_code=status.HTTP_201_CREATED)
async def multi_generate(body: MultiGenerateRequest) -> Dict[str, Any]:
    orch = _orchestrator()
    # Run async-friendly. We offload to a thread so the FastAPI event loop stays free.
    report = await asyncio.to_thread(
        orch.run_sync,
        body.brief,
        character_pool=body.character_pool,
        scenes=body.scenes,
        parallel=body.parallel,
    )
    return report.to_dict()


@router.get("/multi_generate/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=200)) -> Dict[str, Any]:
    rows = _orchestrator().history(limit=limit)
    # Trim event lists for the listing endpoint.
    summary = []
    for r in rows:
        summary.append(
            {
                "run_id": r.get("run_id"),
                "started_at": r.get("started_at"),
                "finished_at": r.get("finished_at"),
                "ok": r.get("ok"),
                "asset_count": len(r.get("asset_pool", [])),
                "agent_results": r.get("agent_results", []),
            }
        )
    return {"items": summary, "count": len(summary)}


@router.get("/multi_generate/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    row = _orchestrator().get(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return row


# ── Consistency ────────────────────────────────────────────────────────────
@router.post("/consistency/run")
async def consistency_run(body: ConsistencyRunRequest) -> Dict[str, Any]:
    cfg_dict = body.config or {}
    allowed = {f for f in ConsistencyConfig.__dataclass_fields__.keys()}
    cfg_kwargs = {k: v for k, v in cfg_dict.items() if k in allowed}
    cfg = ConsistencyConfig(**cfg_kwargs)
    report = _workflow().run(
        project_id=body.project_id,
        brief=body.brief,
        config=cfg,
        character_pool=body.character_pool,
    )
    return report.to_dict()


@router.get("/consistency/report")
async def consistency_report(
    project_id: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    rows = _workflow().history(project_id=project_id, limit=limit)
    return {"items": rows, "count": len(rows)}


__all__ = ["router"]