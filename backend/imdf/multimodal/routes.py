"""P4-7-W2: FastAPI router for the multimodal API.

Endpoints (mounted under /api/v1/multimodal and /api/v1/agent/multimodal):

* POST /api/v1/multimodal/understand           — single understanding task
* POST /api/v1/multimodal/understand/batch     — batch
* POST /api/v1/multimodal/generate             — text + ref images → media
* POST /api/v1/multimodal/rag/index            — add media to RAG
* POST /api/v1/multimodal/rag/search           — text/image query
* GET  /api/v1/multimodal/providers            — list generation providers
* GET  /api/v1/multimodal/services             — list 12 service capabilities
* POST /api/v1/multimodal/services/{name}/smoke — run a service smoke
* POST /api/v1/agent/multimodal                — MultimodalAgent invoke
* GET  /api/v1/agent/multimodal/tools          — list agent tools
* GET  /api/v1/multimodal/healthz              — liveness

This router is self-contained: include it in any FastAPI app with
``app.include_router(build_router())``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .generation import CrossModalGeneration
from .multimodal_agent import MultimodalAgent
from .rag import MultimodalRAG
from .service_integration import list_capabilities, run_smoke
from .types import (
    AgentRequest,
    GenerationRequest,
    GenerationTarget,
    MediaRef,
    ModalKind,
    UnderstandingRequest,
    UnderstandingTask,
    parse_media_item,
)
from .understanding import CrossModalUnderstanding

logger = logging.getLogger(__name__)


# ── request / response pydantic models ────────────────────────────────────
class MediaItem(BaseModel):
    kind: Optional[str] = None
    url: Optional[str] = None
    data_b64: Optional[str] = None
    text: Optional[str] = None
    mime: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class UnderstandRequest(BaseModel):
    task: str
    media: List[MediaItem] = Field(default_factory=list)
    query: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    text: str
    target: str
    ref_images: List[MediaItem] = Field(default_factory=list)
    provider: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class RagIndexRequest(BaseModel):
    media: List[MediaItem]


class RagSearchRequest(BaseModel):
    query: Optional[str] = None
    media: Optional[MediaItem] = None
    top_k: int = 5


class AgentInvokeRequest(BaseModel):
    prompt: str
    media: List[MediaItem] = Field(default_factory=list)
    session_id: Optional[str] = None
    save_to_memory: bool = True


class ServiceSmokeRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


# ── singletons (process-level) ─────────────────────────────────────────────
_understanding: Optional[CrossModalUnderstanding] = None
_generation: Optional[CrossModalGeneration] = None
_rag: Optional[MultimodalRAG] = None
_agent: Optional[MultimodalAgent] = None


def get_understanding() -> CrossModalUnderstanding:
    global _understanding
    if _understanding is None:
        _understanding = CrossModalUnderstanding()
    return _understanding


def get_generation() -> CrossModalGeneration:
    global _generation
    if _generation is None:
        _generation = CrossModalGeneration()
    return _generation


def get_rag() -> MultimodalRAG:
    global _rag
    if _rag is None:
        _rag = MultimodalRAG()
    return _rag


def get_agent() -> MultimodalAgent:
    global _agent
    if _agent is None:
        _agent = MultimodalAgent(get_understanding(), get_rag())
    return _agent


# ── helpers ────────────────────────────────────────────────────────────────
def _to_media_refs(items: List[MediaItem]) -> List[MediaRef]:
    return [parse_media_item(i.model_dump()) for i in items]


def _validate_task(task: str) -> UnderstandingTask:
    try:
        return UnderstandingTask(task)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown task: {task}",
        ) from exc


def _validate_target(target: str) -> GenerationTarget:
    try:
        return GenerationTarget(target)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown target modality: {target}",
        ) from exc


# ── router factory ─────────────────────────────────────────────────────────
def build_router(prefix: str = "/api/v1/multimodal") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["multimodal"])

    @router.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {
            "ok": True,
            "service": "multimodal",
            "understanding_model": get_understanding().model,
            "providers": get_generation().available_providers(),
            "agent_tools": len(get_agent().tools),
        }

    # ── understanding ─────────────────────────────────────────────────
    @router.post("/understand")
    def understand(req: UnderstandRequest) -> Dict[str, Any]:
        task = _validate_task(req.task)
        if not req.media:
            raise HTTPException(status_code=422, detail="media must not be empty")
        if task in (UnderstandingTask.VQA, UnderstandingTask.REASONING) and not req.query:
            raise HTTPException(status_code=422, detail=f"task={task.value} requires query")
        und = get_understanding()
        out = und.understand(
            UnderstandingRequest(
                task=task, media=_to_media_refs(req.media), query=req.query, params=req.params,
            )
        )
        return out.to_dict()

    @router.post("/understand/batch")
    def understand_batch(reqs: List[UnderstandRequest]) -> Dict[str, Any]:
        if not reqs:
            raise HTTPException(status_code=422, detail="empty batch")
        und = get_understanding()
        out = []
        for r in reqs:
            task = _validate_task(r.task)
            out.append(
                und.understand(
                    UnderstandingRequest(
                        task=task, media=_to_media_refs(r.media), query=r.query, params=r.params,
                    )
                ).to_dict()
            )
        return {"count": len(out), "results": out}

    # ── generation ─────────────────────────────────────────────────────
    @router.get("/providers")
    def providers() -> Dict[str, Any]:
        return {"providers": get_generation().available_providers()}

    @router.post("/generate")
    def generate(req: GenerateRequest) -> Dict[str, Any]:
        target = _validate_target(req.target)
        if not req.text.strip():
            raise HTTPException(status_code=422, detail="text must not be empty")
        gen = get_generation()
        out = gen.generate(
            GenerationRequest(
                text=req.text, target=target,
                ref_images=_to_media_refs(req.ref_images),
                provider=req.provider, params=req.params,
            )
        )
        return out.to_dict()

    # ── RAG ────────────────────────────────────────────────────────────
    @router.post("/rag/index")
    def rag_index(req: RagIndexRequest) -> Dict[str, Any]:
        if not req.media:
            raise HTTPException(status_code=422, detail="media must not be empty")
        rag = get_rag()
        parsed = rag.index(_to_media_refs(req.media))
        return {"indexed": len(parsed), "parsed": parsed}

    @router.post("/rag/search")
    def rag_search(req: RagSearchRequest) -> Dict[str, Any]:
        if not req.query and not req.media:
            raise HTTPException(status_code=422, detail="either query or media is required")
        rag = get_rag()
        if req.media:
            ref = parse_media_item(req.media.model_dump())
        else:
            ref = MediaRef(kind=ModalKind.TEXT, text=req.query)
        items = rag.search(ref, top_k=req.top_k)
        return {"hits": [it.to_dict() for it in items]}

    # ── 12 service capabilities ────────────────────────────────────────
    @router.get("/services")
    def services() -> Dict[str, Any]:
        return {"services": list_capabilities()}

    @router.post("/services/{name}/smoke")
    def service_smoke(name: str, req: ServiceSmokeRequest) -> Dict[str, Any]:
        try:
            return run_smoke(name, req.payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ── multimodal agent ───────────────────────────────────────────────
    @router.get("/agent/multimodal/tools")
    def agent_tools() -> Dict[str, Any]:
        return {"tools": get_agent().tools}

    @router.post("/agent/multimodal")
    def agent_invoke(req: AgentInvokeRequest) -> Dict[str, Any]:
        if not req.prompt.strip() and not req.media:
            raise HTTPException(status_code=422, detail="prompt or media required")
        agent = get_agent()
        out = agent.invoke(
            AgentRequest(
                prompt=req.prompt, media=_to_media_refs(req.media),
                session_id=req.session_id, save_to_memory=req.save_to_memory,
            )
        )
        return out.to_dict()

    return router


def build_agent_router(prefix: str = "/api/v1/agent") -> APIRouter:
    """Tiny alias router — mounted under /api/v1/agent per spec."""
    router = APIRouter(prefix=prefix, tags=["agent-multimodal"])

    @router.get("/multimodal/tools")
    def agent_tools() -> Dict[str, Any]:
        return {"tools": get_agent().tools}

    @router.post("/multimodal")
    def agent_invoke(req: AgentInvokeRequest) -> Dict[str, Any]:
        agent = get_agent()
        out = agent.invoke(
            AgentRequest(
                prompt=req.prompt, media=_to_media_refs(req.media),
                session_id=req.session_id, save_to_memory=req.save_to_memory,
            )
        )
        return out.to_dict()

    return router