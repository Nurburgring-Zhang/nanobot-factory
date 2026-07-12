"""VDP-2026 R7 — Deployment Readiness HTTP routes.

Mounts the readiness catalog (ENDPOINT_CATALOGUE in ``readiness.py``)
under ``/api/v1/deploy_r7/*`` so external platforms (Prometheus,
Grafana, internal status pages) can poll it. The original
``readiness.py`` only emitted an info-log on canvas_web boot — that
left the catalog invisible to anything outside the Python process.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from .readiness import (
    ENDPOINT_CATALOGUE,
    audit_against_app,
    readiness_report,
    write_helm_chart_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/deploy_r7", tags=["deploy_r7"])


@router.get("/readiness")
async def readiness() -> Dict[str, Any]:
    """Per-module endpoint count + total surface area.

    The shape matches the legacy in-process ``readiness_report()`` so
    downstream consumers (dashboards, ops scripts) don't need to
    change. New field ``mounted_via_http: true`` signals the catalog
    is now reachable over HTTP, not just inside Python.
    """
    rep = readiness_report()
    rep["mounted_via_http"] = True
    return rep


@router.get("/endpoints")
async def endpoints() -> Dict[str, Any]:
    """Flat list of catalogued endpoints (module / method / path)."""
    return {
        "count": len(ENDPOINT_CATALOGUE),
        "endpoints": ENDPOINT_CATALOGUE,
    }


@router.get("/endpoints_by_module")
async def endpoints_by_module() -> Dict[str, List[Dict[str, str]]]:
    """Grouped view: ``{module: [endpoint, ...]}``."""
    by_module: Dict[str, List[Dict[str, str]]] = {}
    for e in ENDPOINT_CATALOGUE:
        by_module.setdefault(e["module"], []).append(e)
    return by_module


@router.post("/audit")
async def audit(payload: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Compare the catalog against an externally-supplied mounted-app
    route table. The request body is ``{"mounted_paths": [..]}`` — a
    list of currently-mounted paths. Anything in the catalog whose
    longest-prefix match is missing is reported as ``missing``.
    """
    mounted_paths = list(payload.get("mounted_paths", []))
    mounted = set(mounted_paths)

    matched, missing = [], []
    for e in ENDPOINT_CATALOGUE:
        # Longest-prefix match: e.g. /api/v1/projects/stats -> /api/v1/projects/stats
        # (exact) or /api/v1/projects (4 levels) if the exact path is not mounted.
        parts = e["path"].split("/")
        best = None
        for i in range(len(parts), 0, -1):
            candidate = "/".join(parts[:i])
            if candidate in mounted:
                best = candidate
                break
        if best is None:
            missing.append(e)
        else:
            matched.append({**e, "matched_path": best})
    return {
        "catalogued": len(ENDPOINT_CATALOGUE),
        "matched": len(matched),
        "missing": missing,
        "checked_paths": mounted_paths,
    }


@router.get("/health")
async def health() -> Dict[str, Any]:
    """Readiness probe — liveness + catalog freshness."""
    rep = readiness_report()
    return {
        "status": "ok",
        "total_endpoints": rep["total_endpoints"],
        "modules": rep["modules"],
        "mounted_via_http": True,
    }


@router.get("/helm_summary")
async def helm_summary() -> Dict[str, Any]:
    """Render the human-readable helm chart summary that
    ``write_helm_chart_summary`` writes to disk; expose it inline so
    ops can fetch it from a browser without SSH.
    """
    import io
    buf = io.StringIO()
    # write_helm_chart_summary takes a Path; capture into our buffer.
    from pathlib import Path
    tmp = Path("/tmp/_imdf_helm_summary.md")
    write_helm_chart_summary(tmp)
    text = tmp.read_text(encoding="utf-8")
    tmp.unlink(missing_ok=True)
    return {"summary_md": text}
