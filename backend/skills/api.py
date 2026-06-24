"""P4-8-W1: FastAPI router for the skills framework.

Mounted on the agent_service app at prefix ``/api/v1``.  Endpoints:

  * ``GET  /skills``                        — list / search skills
  * ``GET  /skills/{name}``                 — skill detail
  * ``POST /skills/{name}/run``             — execute a skill
  * ``POST /skills/{name}/install``         — install community skill
  * ``POST /skills/{name}/rate``            — submit a rating
  * ``GET  /skills/marketplace/list``       — marketplace list
  * ``POST /skills/orchestrator/run``       — run a skill chain
  * ``POST /skills/orchestrator/auto``      — auto-route + run
  * ``GET  /obsidian/wiki``                 — wiki list
  * ``POST /obsidian/wiki``                 — create/update page
  * ``GET  /obsidian/wiki/{slug}``          — page detail
  * ``DELETE /obsidian/wiki/{slug}``        — delete page
  * ``GET  /obsidian/wiki/{slug}/backlinks``— backlinks
  * ``GET  /obsidian/wiki/graph``           — knowledge graph
  * ``POST /obsidian/llm_kb/ingest``        — LLM auto-KB ingest
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from .base import SkillCategory
from .context import SkillContext
from .marketplace import (
    get_marketplace,
    new_community_skill,
    reset_marketplace_for_test,
)
from .obsidian import (
    KBIngestItem,
    get_knowledge_graph,
    get_llm_kb,
    reset_singletons_for_test as reset_obsidian_for_test,
)
from .orchestrator import ChainStep, SkillOrchestrator
from .registry import SKILL_REGISTRY
from .result import SkillResult

logger = logging.getLogger(__name__)


# ── Pydantic request models ──────────────────────────────────────────────────
class RunSkillRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    user_id: str = "anonymous"
    project_id: str = "default"


class RunChainRequest(BaseModel):
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    user_id: str = "anonymous"
    project_id: str = "default"


class RateSkillRequest(BaseModel):
    stars: int = Field(..., ge=1, le=5)
    review: str = ""
    user_id: str = "anonymous"


class WikiUpsertRequest(BaseModel):
    slug: str
    title: Optional[str] = None
    content: str = ""
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMSessionIngestRequest(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    dedupe: bool = True


class LLMItemsIngestRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list)


class InstallCommunitySkillRequest(BaseModel):
    name: str
    description: str
    category: str = "productivity"
    tags: Optional[List[str]] = None
    author: str = "community"


# ── Router ───────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1", tags=["skills"])


# Skills --------------------------------------------------------------------
# IMPORTANT: declare the more specific /skills/orchestrator/* routes BEFORE
# the catch-all /skills/{name}/... so FastAPI does not match 'orchestrator'
# against the {name} path parameter.

@router.post("/skills/orchestrator/run")
async def run_chain(req: RunChainRequest) -> Dict[str, Any]:
    if not req.steps:
        raise HTTPException(status_code=422, detail="steps is empty")
    steps = [ChainStep.from_dict(s) for s in req.steps]
    ctx = SkillContext.create(user_id=req.user_id, project_id=req.project_id)
    orch = SkillOrchestrator()
    chain = await orch.run_chain(steps, ctx)
    return chain.to_dict()


@router.post("/skills/orchestrator/auto")
async def run_auto(query: str = Body(..., embed=True),
                   inputs: Optional[Dict[str, Any]] = None,
                   user_id: str = "anonymous",
                   project_id: str = "default") -> Dict[str, Any]:
    ctx = SkillContext.create(user_id=user_id, project_id=project_id, inputs=inputs or {})
    orch = SkillOrchestrator()
    return (await orch.run_auto(query, ctx, inputs=inputs)).to_dict()


@router.get("/skills")
def list_skills(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    cat = None
    if category:
        try:
            cat = SkillCategory(category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"unknown category: {category}")
    if query:
        items = SKILL_REGISTRY.search(query)
    else:
        items = SKILL_REGISTRY.list(category=cat, tag=tag)
    return {
        "count": len(items),
        "categories": SKILL_REGISTRY.categories_summary(),
        "items": items,
    }


@router.get("/skills/marketplace/list")
def marketplace_list(
    category: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    cat = None
    if category:
        try:
            cat = SkillCategory(category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"unknown category: {category}")
    mp = get_marketplace()
    items = mp.list(category=cat, query=query)
    return {"count": len(items), "items": items}


@router.get("/skills/{name}")
def get_skill(name: str, version: Optional[str] = None) -> Dict[str, Any]:
    if name in {"orchestrator", "marketplace"}:
        # Defensive: should never reach here because static routes are first.
        raise HTTPException(status_code=404, detail=f"unknown skill: {name}")
    if not SKILL_REGISTRY.has(name):
        raise HTTPException(status_code=404, detail=f"skill not found: {name}")
    try:
        meta = SKILL_REGISTRY.meta(name, version=version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return meta.to_dict()


@router.post("/skills/{name}/run")
async def run_skill(name: str, req: RunSkillRequest) -> Dict[str, Any]:
    if name == "orchestrator":
        # Should never reach here either — explicit route wins.
        raise HTTPException(status_code=404, detail="use /skills/orchestrator/run")
    if not SKILL_REGISTRY.has(name):
        raise HTTPException(status_code=404, detail=f"skill not found: {name}")
    ctx = SkillContext.create(
        user_id=req.user_id, project_id=req.project_id, inputs=req.inputs,
    )
    orch = SkillOrchestrator()
    result = await orch.run_skill(name, ctx, inputs=req.inputs)
    return result.to_dict()


# Marketplace ----------------------------------------------------------------

@router.post("/skills/install_community")
def install_community_skill(req: InstallCommunitySkillRequest) -> Dict[str, Any]:
    mp = get_marketplace()
    entry = new_community_skill(
        name=req.name,
        description=req.description,
        category=req.category,
        tags=req.tags,
        author=req.author,
    )
    mp.publish(entry)
    return entry.to_dict()


@router.post("/skills/{name}/install")
def install_skill(name: str) -> Dict[str, Any]:
    if name in {"orchestrator", "marketplace", "install_community"}:
        raise HTTPException(status_code=404, detail=f"unknown skill: {name}")
    mp = get_marketplace()
    entry = mp.get(name)
    if entry is None:
        # Auto-create from registry if it's a known skill.
        if SKILL_REGISTRY.has(name):
            meta = SKILL_REGISTRY.meta(name)
            entry = new_community_skill(
                name=name,
                description=meta.description,
                category=str(meta.category.value if hasattr(meta.category, "value") else meta.category),
                tags=list(meta.tags),
                author=meta.author,
            )
            entry.version = meta.version
            entry.builtin = True
            mp.publish(entry)
        else:
            raise HTTPException(status_code=404, detail=f"unknown skill: {name}")
    return mp.install(name)


@router.post("/skills/{name}/rate")
def rate_skill(name: str, req: RateSkillRequest) -> Dict[str, Any]:
    if name in {"orchestrator", "marketplace", "install_community"}:
        raise HTTPException(status_code=404, detail=f"unknown skill: {name}")
    mp = get_marketplace()
    if mp.get(name) is None:
        raise HTTPException(status_code=404, detail=f"unknown skill: {name}")
    return mp.rate(name, user_id=req.user_id, stars=req.stars, review=req.review)


# Obsidian ------------------------------------------------------------------
# Static routes MUST come before /wiki/{slug} so graph/tags/backlinks
# don't get swallowed by the {slug} path parameter.

@router.get("/obsidian/wiki/graph")
def wiki_graph() -> Dict[str, Any]:
    g = get_knowledge_graph()
    return g.graph()


@router.get("/obsidian/wiki/tags")
def wiki_tag_cloud() -> Dict[str, Any]:
    g = get_knowledge_graph()
    return {"tags": g.tag_cloud()}


@router.get("/obsidian/wiki")
def wiki_list(tag: Optional[str] = None) -> Dict[str, Any]:
    g = get_knowledge_graph()
    pages = g.list_pages(tag=tag)
    return {"count": len(pages), "items": [p.to_dict() for p in pages]}


@router.post("/obsidian/wiki")
def wiki_upsert(req: WikiUpsertRequest) -> Dict[str, Any]:
    g = get_knowledge_graph()
    page = g.upsert(
        slug=req.slug, title=req.title, content=req.content,
        tags=req.tags, metadata=req.metadata,
    )
    return page.to_dict()


@router.get("/obsidian/wiki/{slug}/backlinks")
def wiki_backlinks(slug: str) -> Dict[str, Any]:
    if slug in {"graph", "tags"}:
        raise HTTPException(status_code=404, detail=f"wiki page not found: {slug}")
    g = get_knowledge_graph()
    page = g.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail=f"wiki page not found: {slug}")
    return {"slug": slug, "backlinks": g.backlinks(slug)}


@router.get("/obsidian/wiki/{slug}")
def wiki_detail(slug: str) -> Dict[str, Any]:
    if slug in {"graph", "tags"}:
        raise HTTPException(status_code=404, detail=f"wiki page not found: {slug}")
    g = get_knowledge_graph()
    page = g.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail=f"wiki page not found: {slug}")
    return page.to_dict()


@router.delete("/obsidian/wiki/{slug}")
def wiki_delete(slug: str) -> Dict[str, Any]:
    if slug in {"graph", "tags"}:
        raise HTTPException(status_code=404, detail=f"wiki page not found: {slug}")
    g = get_knowledge_graph()
    ok = g.delete(slug)
    if not ok:
        raise HTTPException(status_code=404, detail=f"wiki page not found: {slug}")
    return {"deleted": slug}


@router.post("/obsidian/llm_kb/ingest")
def llm_kb_ingest(req: LLMItemsIngestRequest) -> Dict[str, Any]:
    kb = get_llm_kb()
    items = [
        KBIngestItem(
            source=str(it.get("source", "user")),
            source_id=str(it.get("source_id", "")),
            content=str(it.get("content", "")),
            metadata=dict(it.get("metadata") or {}),
        )
        for it in req.items
    ]
    report = kb.ingest(items)
    return report.to_dict()


@router.post("/obsidian/llm_kb/ingest_session")
def llm_kb_ingest_session(req: LLMSessionIngestRequest) -> Dict[str, Any]:
    kb = get_llm_kb()
    report = kb.ingest_session(req.session_id, req.messages, dedupe=req.dedupe)
    return report.to_dict()


# ── Testing helpers ──────────────────────────────────────────────────────────
def reset_for_test() -> None:  # pragma: no cover
    reset_marketplace_for_test()
    reset_obsidian_for_test()


__all__ = ["router", "reset_for_test"]