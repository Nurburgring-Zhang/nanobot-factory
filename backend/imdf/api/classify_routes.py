"""分类规则引擎API路由 — F1.13 (R2-2: Body 验证)"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

try:
    from engines.classification_engine import ClassificationEngine, ClassificationRule, create_default_rules
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engines.classification_engine import ClassificationEngine, ClassificationRule, create_default_rules

# R2-3: 路径 ID 校验
from api._common.validators import validate_id

# R2-2: Body 验证模型
from api._common.body_schemas import ClassifyInitDefaultsRequest

router = APIRouter(prefix="/api/classify", tags=["classification"])
engine = ClassificationEngine()

class RuleCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]{1,128}$")
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field("默认", min_length=1, max_length=64)
    description: str = Field("", max_length=4096)
    priority: int = Field(0, ge=-1000, le=1000)
    field: str = Field("", max_length=128)
    operator: Literal["contains", "equals", "starts_with", "ends_with", "regex", "gt", "lt", "in"] = Field("contains")
    value: str = Field("", max_length=4096)

class ClassifyRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(..., min_length=1, max_length=10000)

class NLFilterRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(..., min_length=1, max_length=10000)
    query: str = Field(..., min_length=1, max_length=4096)

@router.post("/rule")
async def add_rule(rule: RuleCreate):
    r = ClassificationRule(**rule.model_dump())
    rid = engine.add_rule(r)
    return {"success": True, "id": rid}

@router.get("/rules")
async def list_rules(
    category: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="分类过滤 (白名单字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    rules = engine.list_rules(category)
    if q:
        rules = [r for r in rules if q.lower() in str(r).lower()]
    total = len(rules)
    page = rules[offset: offset + limit]
    return {
        "success": True,
        "rules": page,
        "total": total,
        "category": category,
        "limit": limit,
        "offset": offset,
    }

@router.delete("/rule/{rule_id}")
async def delete_rule(rule_id: str):
    validate_id(rule_id, "rule_id")
    engine.delete_rule(rule_id)
    return {"success": True}

@router.post("/run")
async def classify_items(req: ClassifyRequest):
    results = engine.classify_batch(req.items)
    return {"success": True, "results": results}

@router.post("/nl-filter")
async def nl_filter(req: NLFilterRequest):
    results = engine.nl_filter(req.items, req.query)
    return {"success": True, "results": results, "count": len(results)}

@router.get("/taxonomy")
async def get_taxonomy(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    tree = engine.get_taxonomy_tree()
    if q:
        tree = [t for t in tree if q.lower() in str(t).lower()]
    total = len(tree)
    page = tree[offset: offset + limit]
    return {
        "success": True,
        "tree": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/init-defaults")
async def init_default_rules(req: ClassifyInitDefaultsRequest = ClassifyInitDefaultsRequest(category="default", labels=["label"])):
    """初始化默认规则 (R2-2: Pydantic 验证 body)"""
    create_default_rules(engine)
    return {"success": True, "rules_count": len(engine.rules), "category": req.category, "labels_count": len(req.labels), "overwrite": req.overwrite}
