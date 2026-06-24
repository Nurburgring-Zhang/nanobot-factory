"""
F2.6 模板市场 API 路由 — Template Market Routes
===============================================
Endpoints:
  GET    /api/templates              → 模板列表 (分页/搜索/过滤/排序)
  GET    /api/templates/popular      → 热门模板   [R2-Worker-5]
  GET    /api/templates/top-rated    → 高分模板   [R2-Worker-5]
  GET    /api/templates/categories   → 分类列表+统计
  GET    /api/templates/stats        → 市场统计   [R2-Worker-5]
  POST   /api/templates              → 创建模板
  GET    /api/templates/{id}         → 模板详情
  PUT    /api/templates/{id}         → 更新模板
  DELETE /api/templates/{id}         → 删除(归档)模板
  POST   /api/templates/{id}/publish → 发布模板
  POST   /api/templates/{id}/use     → 使用模板(计数+1)
  POST   /api/templates/{id}/rate    → 评分模板(1-5分)
  GET    /api/templates/{id}/ratings → 查看评分记录
  GET    /api/templates/{id}/versions → 查看版本历史

R2-Worker-5: stats / popular / top-rated 加入 ``DateRangeParams`` / ``Granularity`` / dimension 白名单。
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel, Field

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension
# R2-3: 路径 ID 校验
from api._common.validators import validate_id

router = APIRouter(prefix="/api/templates", tags=["templates"])

# 模板模块允许的聚合维度
TEMPLATE_ALLOWED_DIMENSIONS = ("category", "author", "status", "tag", "rating", "date")


def _get_engine():
    """延迟加载模板市场引擎"""
    from engines.template_market import get_template_market_engine
    return get_template_market_engine()


# ─── Request/Response Models ────────────────────────────────────────────

class TemplateCreateRequest(BaseModel):
    name: str = Field(..., description="模板名称", min_length=1, max_length=200)
    description: str = Field("", description="模板描述")
    category: str = Field("general", description="分类: drama/picture_book/product_image/digital_human/advertisement/general")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    author: str = Field("system", description="作者")
    config: Optional[dict] = Field(None, description="模板配置JSON")
    thumbnail_url: str = Field("", description="缩略图URL")
    preview_urls: Optional[List[str]] = Field(None, description="预览图URL列表")


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="模板名称")
    description: Optional[str] = Field(None, description="模板描述")
    category: Optional[str] = Field(None, description="分类")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    config: Optional[dict] = Field(None, description="模板配置JSON")
    thumbnail_url: Optional[str] = Field(None, description="缩略图URL")
    preview_urls: Optional[List[str]] = Field(None, description="预览图URL列表")


class TemplateRateRequest(BaseModel):
    user_id: str = Field(..., description="评分用户ID")
    score: float = Field(..., ge=1.0, le=5.0, description="评分 1-5")
    comment: str = Field("", description="评分备注")


# ─── Routes ─────────────────────────────────────────────────────────────

@router.get("")
async def list_templates(
    category: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$",
        description="分类过滤 (白名单字符, ≤64 字符)",
    ),
    status: str = Query(
        "published", pattern=r"^(draft|published|archived)$",
        description="状态: draft/published/archived",
    ),
    search: Optional[str] = Query(
        None, max_length=200, description="搜索关键词, ≤200 字符",
    ),
    tags: Optional[str] = Query(
        None, max_length=512, description="标签过滤(逗号分隔, ≤512 字符)",
    ),
    sort_by: str = Query(
        "download_count", pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    sort_order: str = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """模板列表 (分页/搜索/过滤/排序) (R2.5-W1: Pydantic Query 验证)"""
    engine = _get_engine()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = engine.list_templates(
        category=category,
        status=status,
        search=search,
        tags=tag_list,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return {"success": True, **result}


@router.get("/popular")
async def popular_templates(
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
    dr: DateRangeParams = Depends(),
    dimension: str = Query(
        "category",
        description=f"聚合维度, 允许: {list(TEMPLATE_ALLOWED_DIMENSIONS)}",
    ),
):
    """热门模板（按下载量排序）

    R2-Worker-5: 注入 DateRangeParams + dimension 白名单。
    """
    if not is_valid_dimension(dimension, scope="templates"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(TEMPLATE_ALLOWED_DIMENSIONS)}",
        )
    engine = _get_engine()
    items = engine.get_popular_templates(limit=limit)
    return {
        "success": True,
        "items": items,
        "count": len(items),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "dimension": dimension,
    }


@router.get("/top-rated")
async def top_rated_templates(
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
    dr: DateRangeParams = Depends(),
    dimension: str = Query(
        "category",
        description=f"聚合维度, 允许: {list(TEMPLATE_ALLOWED_DIMENSIONS)}",
    ),
):
    """高分模板（按评分排序）

    R2-Worker-5: 注入 DateRangeParams + dimension 白名单。
    """
    if not is_valid_dimension(dimension, scope="templates"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(TEMPLATE_ALLOWED_DIMENSIONS)}",
        )
    engine = _get_engine()
    items = engine.get_top_rated_templates(limit=limit)
    return {
        "success": True,
        "items": items,
        "count": len(items),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "dimension": dimension,
    }


@router.get("/categories")
async def list_categories(
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
    """获取所有分类及每个分类的模板数量"""
    engine = _get_engine()
    cats = engine.get_categories()
    if q:
        cats = [c for c in cats if q.lower() in str(c).lower()]
    total = len(cats)
    if sort_by:
        cats = sorted(
            cats, key=lambda c: c.get(sort_by, "") if isinstance(c, dict) else "",
            reverse=(order == "desc"),
        )
    page = cats[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def market_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "category",
        description=f"聚合维度, 允许: {list(TEMPLATE_ALLOWED_DIMENSIONS)}",
    ),
):
    """获取模板市场总体统计数据

    R2-Worker-5: 注入 DateRangeParams + granularity 枚举 + dimension 白名单。
    """
    if not is_valid_dimension(dimension, scope="templates"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(TEMPLATE_ALLOWED_DIMENSIONS)}",
        )
    engine = _get_engine()
    stats = engine.get_stats()
    return {
        "success": True,
        "data": stats,
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }


@router.post("")
async def create_template(req: TemplateCreateRequest):
    """创建新模板"""
    engine = _get_engine()
    tmpl = engine.create_template(
        name=req.name,
        description=req.description,
        category=req.category,
        tags=req.tags,
        author=req.author,
        config=req.config or {},
        thumbnail_url=req.thumbnail_url,
        preview_urls=req.preview_urls,
        status="draft",
    )
    return {"success": True, "data": tmpl.to_dict()}


@router.get("/{template_id}")
async def get_template(template_id: str):
    """获取模板详情 (自动增加查看计数)"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    tmpl = engine.get_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    return {"success": True, "data": tmpl.to_dict()}


@router.put("/{template_id}")
async def update_template(template_id: str, req: TemplateUpdateRequest):
    """更新模板（仅更新提交的字段）"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    updates = req.dict(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    tmpl = engine.update_template(template_id, **updates)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    return {"success": True, "data": tmpl.to_dict()}


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    """软删除模板（归档）"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    ok = engine.delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    return {"success": True, "message": "模板已归档"}


@router.post("/{template_id}/publish")
async def publish_template(template_id: str):
    """发布模板 (draft → published)"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    tmpl = engine.publish_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    return {"success": True, "data": tmpl.to_dict(), "message": "模板已发布"}


@router.post("/{template_id}/use")
async def use_template(template_id: str):
    """使用/下载模板 (计数+1)"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    tmpl = engine.use_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    return {
        "success": True,
        "data": tmpl.to_dict(),
        "message": f"模板使用次数: {tmpl.download_count}",
    }


@router.post("/{template_id}/rate")
async def rate_template(template_id: str, req: TemplateRateRequest):
    """评分模板 (1-5分，同一用户重复评分会覆盖)"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    tmpl = engine.rate_template(
        template_id=template_id,
        user_id=req.user_id,
        score=req.score,
        comment=req.comment,
    )
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    return {
        "success": True,
        "data": tmpl.to_dict(),
        "message": f"评分成功: {req.score}/5",
    }


@router.get("/{template_id}/ratings")
async def get_template_ratings(template_id: str):
    """获取模板所有评分记录"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    tmpl = engine.get_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")
    ratings = engine.get_template_ratings(template_id)
    return {
        "success": True,
        "data": ratings,
        "count": len(ratings),
        "avg_rating": tmpl.rating,
        "rating_count": tmpl.rating_count,
    }


@router.get("/{template_id}/versions")
async def get_template_versions(template_id: str):
    """获取模板版本历史"""
    validate_id(template_id, "template_id")
    engine = _get_engine()
    versions = engine.get_versions(template_id)
    if not versions:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在或没有版本记录")
    return {"success": True, "data": versions, "count": len(versions)}
