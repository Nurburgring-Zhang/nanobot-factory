"""数据寻源API路由 — F1.1"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from engines.discovery_engine import get_discovery

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

class DiscoverRequest(BaseModel):
    query: str
    platforms: Optional[List[str]] = None

class RegisterSourceRequest(BaseModel):
    id: str
    name: str
    platform: str
    url: str
    description: str = ""
    format: str = ""
    size: str = ""
    license: str = ""

@router.post("/search")
async def discover_sources(req: DiscoverRequest):
    engine = get_discovery()
    results = engine.discover(req.query, req.platforms)
    return {"success": True, "query": req.query, "results": results, "count": len(results)}

@router.get("/registered")
async def list_registered():
    return {"success": True, "sources": get_discovery().list_registered()}

@router.post("/register")
async def register_source(req: RegisterSourceRequest):
    from engines.discovery_engine import DataSource
    src = DataSource(**req.model_dump())
    sid = get_discovery().register_manual_source(src)
    return {"success": True, "id": sid}

@router.post("/clear-cache")
async def clear_cache():
    get_discovery().clear_cache()
    return {"success": True}
