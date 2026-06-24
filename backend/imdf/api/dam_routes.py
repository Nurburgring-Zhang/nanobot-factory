"""
DAM (Digital Asset Management) API Routes — F1.8
================================================
Endpoints:
  GET  /api/dam/files           → 文件列表 (分页/搜索/过滤)
  GET  /api/dam/files/{id}      → 文件详情
  GET  /api/dam/files/{id}/preview → 生成预览
  POST /api/dam/files/{id}/tag  → AI打标
  POST /api/dam/smart-folder    → 创建智能文件夹
  GET  /api/dam/smart-folders   → 列出智能文件夹
  GET  /api/dam/smart-folder/{id}/contents → 智能文件夹内容
  GET  /api/dam/lineage/{id}    → 血统图谱
  POST /api/dam/lineage         → 添加血统关系
  GET  /api/dam/stats           → 格式统计  [R2-Worker-5]
  POST /api/dam/scan            → 重新扫描目录
  GET  /api/dam/formats         → 支持格式列表

R2-Worker-5: /stats 加入 ``DateRangeParams`` / ``Granularity`` / dimension 白名单校验。
"""

from fastapi import APIRouter, Query, HTTPException, Body, Depends
from typing import Dict, Any, List, Optional
from pathlib import Path

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

router = APIRouter(prefix="/api/dam", tags=["dam"])

# DAM 模块允许的聚合维度
DAM_ALLOWED_DIMENSIONS = ("category", "format", "folder", "date", "size")


def _get_manager():
    """Lazy-load DAM manager."""
    from engines.dam_engine import get_dam_manager
    return get_dam_manager()


# ═══════════════════════════════════════════════════════════════════════════
# File listing & browsing
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/files")
async def list_files(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(
        None, max_length=200, description="搜索关键词, ≤200 字符",
    ),
    category: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$",
        description="分类过滤 (白名单字符, ≤64 字符)",
    ),
    sort: str = Query("name", pattern="^(name|size|date|category)$"),
):
    """List DAM files with pagination, search, and category filter.

    Supports semantic search across file names, tags, and AI labels.
    Filter by category: image, video, audio, 3d, document, dataset, archive.
    """
    mgr = _get_manager()

    # Auto-scan on first request if empty
    if not mgr._files:
        mgr.scan_all()

    result = mgr.get_files(category=category, search=search, page=page, size=size)

    # Sort
    items = result["items"]
    if sort == "size":
        items.sort(key=lambda f: f["size_bytes"], reverse=True)
    elif sort == "date":
        items.sort(key=lambda f: f.get("modified_at", 0), reverse=True)
    elif sort == "category":
        items.sort(key=lambda f: f.get("category", ""))
    else:  # name
        items.sort(key=lambda f: f.get("name", "").lower())

    result["items"] = items
    return {"success": True, **result}


@router.get("/files/{file_id}")
async def get_file(file_id: str):
    """Get a single DAM file's details."""
    mgr = _get_manager()
    dam_file = mgr.get_file(file_id)
    if not dam_file:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    return {"success": True, "data": dam_file.to_dict()}


@router.get("/files/{file_id}/preview")
async def preview_file(file_id: str):
    """Generate and return preview for a file."""
    mgr = _get_manager()
    dam_file = mgr.get_file(file_id)
    if not dam_file:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    preview = mgr.preview_engine.generate_preview(dam_file.path)
    if not preview:
        raise HTTPException(status_code=500, detail="Preview generation failed")

    return {"success": True, "data": preview}


@router.post("/files/{file_id}/tag")
async def tag_file(file_id: str):
    """Run AI auto-tagging on a specific file."""
    mgr = _get_manager()
    dam_file = mgr.get_file(file_id)
    if not dam_file:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    try:
        result = await mgr.ai_tag_file(file_id)
        return {"success": True, "data": result, "file_id": file_id}
    except Exception as e:
        return {"success": False, "error": str(e), "file_id": file_id}


@router.post("/files/tag-all")
async def tag_all_files():
    """Run AI auto-tagging on all files."""
    mgr = _get_manager()
    try:
        results = await mgr.ai_tag_all(concurrency=3)
        return {"success": True, "count": len(results), "data": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# Smart Folders
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/smart-folders")
async def list_smart_folders():
    """List all smart folders."""
    mgr = _get_manager()
    folders = mgr.get_smart_folders()
    return {"success": True, "data": folders, "total": len(folders)}


@router.post("/smart-folder")
async def create_smart_folder(data: Dict[str, Any] = Body(...)):
    """Create a new smart folder.

    Request body:
    {
        "name": "High-res Images",
        "description": "Images above 4K resolution",
        "rules": [
            {"field": "category", "operator": "eq", "value": "image"},
            {"field": "metadata.width", "operator": "gt", "value": "3840"}
        ]
    }

    Supported operators: eq, ne, in, not_in, contains, starts_with, ends_with, gt, lt, gte, lte, regex
    """
    name = data.get("name", "")
    if not name:
        raise HTTPException(status_code=400, detail="Smart folder name is required")

    rules = data.get("rules", [])
    description = data.get("description", "")

    mgr = _get_manager()
    sf = mgr.create_smart_folder(name, rules, description)
    return {"success": True, "data": sf}


@router.get("/smart-folder/{folder_id}/contents")
async def smart_folder_contents(folder_id: str):
    """Get the contents of a smart folder (matched files)."""
    mgr = _get_manager()
    sf = mgr.smart_folder_engine.get(folder_id)
    if not sf:
        raise HTTPException(status_code=404, detail=f"Smart folder {folder_id} not found")

    contents = mgr.get_smart_folder_contents(folder_id)
    return {"success": True, "data": {
        "folder": sf.to_dict(),
        "files": contents,
        "count": len(contents),
    }}


@router.delete("/smart-folder/{folder_id}")
async def delete_smart_folder(folder_id: str):
    """Delete a smart folder."""
    mgr = _get_manager()
    ok = mgr.smart_folder_engine.delete(folder_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Smart folder {folder_id} not found")
    return {"success": True, "message": f"Smart folder {folder_id} deleted"}


# ═══════════════════════════════════════════════════════════════════════════
# Lineage
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/lineage/{file_id}")
async def get_lineage(file_id: str, depth: int = Query(5, ge=1, le=10)):
    """Get data lineage graph for a file.

    Returns ancestors, descendants, and full DAG subset.
    """
    mgr = _get_manager()
    lineage = mgr.get_lineage(file_id)
    if not lineage:
        # Return empty lineage structure instead of 404
        return {"success": True, "data": {
            "node": {"file_id": file_id, "name": file_id, "category": "unknown",
                     "parents": [], "children": [], "operations": [], "metadata": {}},
            "ancestors": [],
            "descendants": [],
            "full_graph": {"nodes": {file_id: {"name": file_id, "category": "unknown"}}, "edges": []},
        }}
    return {"success": True, "data": lineage}


@router.post("/lineage")
async def add_lineage(data: Dict[str, Any] = Body(...)):
    """Add a lineage relationship between files.

    Request body:
    {
        "parent_id": "source_file_hash",
        "child_id": "derived_file_hash",
        "operation": "image_resize"
    }
    """
    parent_id = data.get("parent_id", "")
    child_id = data.get("child_id", "")
    operation = data.get("operation", "")

    if not parent_id or not child_id:
        raise HTTPException(status_code=400, detail="parent_id and child_id are required")

    mgr = _get_manager()
    mgr.add_lineage(parent_id, child_id, operation)
    return {"success": True, "data": {
        "parent_id": parent_id,
        "child_id": child_id,
        "operation": operation,
    }}


# ═══════════════════════════════════════════════════════════════════════════
# Stats & Info
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def dam_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "category",
        description=f"聚合维度, 允许: {list(DAM_ALLOWED_DIMENSIONS)}",
    ),
):
    """Get DAM statistics: file counts, sizes, format distribution.

    R2-Worker-5: DateRangeParams + granularity 枚举 + dimension 白名单校验。
    """
    if not is_valid_dimension(dimension, scope="dam"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(DAM_ALLOWED_DIMENSIONS)}",
        )
    mgr = _get_manager()
    stats = mgr.get_format_stats()
    stats["smart_folders_count"] = len(mgr.get_smart_folders())
    return {
        "success": True,
        "data": stats,
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }


@router.get("/formats")
async def supported_formats():
    """List all supported file formats (90+)."""
    mgr = _get_manager()
    return {
        "success": True,
        "data": {
            "total_formats": mgr.preview_engine.get_total_format_count(),
            "categories": mgr.preview_engine.get_all_categories(),
        },
    }


@router.post("/scan")
async def rescan_directories(directories: Optional[List[str]] = Body(None)):
    """Re-scan directories for new files."""
    mgr = _get_manager()
    if directories:
        mgr._scan_directories = directories
    discovered = mgr.scan_all()
    return {
        "success": True,
        "data": {
            "files_found": len(discovered),
            "total_registered": len(mgr._files),
            "categories": {
                cat: {"count": count}
                for cat, count in mgr.get_format_stats()["categories"].items()
                if isinstance(count, dict)
            },
        },
    }


@router.get("/search/suggest")
async def search_suggest(
    prefix: str = Query("", min_length=1, max_length=200, description="搜索前缀 (1..200 字符)"),
    limit: int = Query(20, ge=1, le=100, description="返回条数 (1..100)"),
):
    """Get search autocomplete suggestions (R2.5-W1: Pydantic Query 验证)."""
    mgr = _get_manager()
    files = [f.to_dict() for f in mgr._files.values()]
    mgr.search_engine.index_files(files)
    suggestions = mgr.search_engine.suggest(prefix)[:limit]
    return {"success": True, "data": suggestions, "count": len(suggestions)}
