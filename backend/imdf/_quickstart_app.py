"""P22-P2-real-fix-3 — quickstart standalone app.

This is a minimal FastAPI app that wires up:
- DB session (already initialised by quickstart.py)
- 5 SFC P22-P2-real views (WorkflowBuilder / CollectionCenter /
  Delivery / CapabilityRegistry / PackManager)
- 50 builtin skills (P22-P1c)
- 30 P2 channels (P22-P2a)
- Celery eager mode (in-process)

Real production should use the full uvicorn + 13 micro-services
cluster (P2b systemd); this file is for 5-min standalone demo only.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import time

app = FastAPI(
    title="ZhiYing Quickstart (standalone)",
    description="5-min standalone mode — full app in one process. Real prod: use systemd cluster.",
    version="2.0.0+",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "ZhiYing (智影) Quickstart",
        "version": "2.0.0+",
        "mode": "standalone",
        "docs": "/docs",
        "endpoints": [
            "/healthz", "/api/v1/sfc/workflow", "/api/v1/sfc/collection",
            "/api/v1/sfc/delivery", "/api/v1/sfc/capability", "/api/v1/sfc/pack",
            "/api/v1/skills", "/api/v1/channels", "/api/v1/celery/health",
            "/api/v1/engines",
        ],
    }


@app.get("/healthz")
def healthz():
    """Liveness + readiness probe."""
    from common.db import ping  # type: ignore
    return {
        "status": "ok",
        "mode": "standalone",
        "db": ping(),
        "ts": int(time.time()),
    }


@app.get("/api/v1/sfc/{name}")
def sfc_view(name: str):
    """P22-P2-real 5 SFC views: workflow / collection / delivery / capability / pack."""
    views = {
        "workflow": "WorkflowBuilder — workflow templates + lifecycle",
        "collection": "CollectionCenter — RSS + crawler +3 态 (loading/empty/error)",
        "delivery": "Delivery — 7 状态机 (draft→submitted→in_review→approved→delivered→archived)",
        "capability": "CapabilityRegistry — capability_id + inputs schema",
        "pack": "PackManager — pack status transitions",
    }
    if name not in views:
        raise HTTPException(404, f"unknown view: {name}")
    return {"view": name, "description": views[name], "engine": "vue3-naiveui", "version": "p22-p2-real"}


@app.get("/api/v1/skills")
def list_skills():
    """List all 50 builtin skills (P22-P1c)."""
    from backend.skills_builtin import BUILTIN_SKILLS
    return {
        "total": len(BUILTIN_SKILLS),
        "skills": [{"id": s.id, "name": s.name, "category": s.category} for s in BUILTIN_SKILLS],
    }


@app.get("/api/v1/channels")
def list_channels():
    """List all 30 P2 channels (P22-P2a)."""
    import imdf.intelligence.agent_reach.channels as c
    return {
        "total": len(c.__all__),
        "channels": c.__all__,
    }


@app.get("/api/v1/celery/health")
def celery_health():
    from imdf.celery_app import health_summary
    return health_summary()


@app.get("/api/v1/engines")
def list_engines():
    """List all engines in imdf.engines (P22-P5 smoke-tested)."""
    from pathlib import Path
    eng_dir = Path(__file__).parent / "engines"
    if not eng_dir.is_dir():
        return {"total": 0, "engines": []}
    out = []
    for p in sorted(eng_dir.rglob("*.py")):
        if p.name in ("__init__.py", "conftest.py") or p.name.startswith("test_"):
            continue
        rel = p.relative_to(Path(__file__).parent).as_posix()[:-3]
        out.append(rel.replace("/", "."))
    return {"total": len(out), "engines": out}
