"""
绘本一键成书 API Routes
========================
POST   /api/book/generate      → 一键生成绘本
GET    /api/book/{id}          → 获取绘本详情
GET    /api/book/list          → 绘本列表
GET    /api/book/{id}/export   → 导出(支持PDF/EPUB/HTML/PNG)
GET    /api/book/images/{filename} → 获取绘本图片
DELETE /api/book/{id}          → 删除绘本
"""

from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from engines.book_engine import get_book_engine, Book, BookPage
# R2.5-W3: 路径参数校验
from api._common.validators import validate_id

router = APIRouter(prefix="/api/book", tags=["picture-book"])


# ─── Request/Response Models ────────────────────────────────────────────────

class GenerateBookRequest(BaseModel):
    title: str = Field("我的故事书", description="书名")
    story: str = Field(..., description="故事内容")
    style: str = Field("storybook", description="画风: storybook/watercolor/cartoon/realistic/anime")
    pages: int = Field(8, ge=2, le=32, description="页数")
    audience: str = Field("3-6", description="目标读者: 3-6/6-10/10+/adult")
    generate_images: bool = Field(True, description="是否生成插图")


class BookResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BookListResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]] = []
    total: int = 0


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=Dict[str, Any])
async def generate_book(req: GenerateBookRequest):
    """
    一键生成绘本。

    流程: 解析故事 → LLM生成逐页插图描述 → 插图渲染 → 排版组装

    Request:
    {
        "title": "小兔子的冒险",
        "story": "在一个遥远的森林里...",
        "style": "storybook",
        "pages": 8,
        "audience": "3-6",
        "generate_images": true
    }

    Returns:
        {
            "success": true,
            "data": {
                "id": "book_abc123...",
                "title": "小兔子的冒险",
                "pages": [...],
                "status": "illustrations_ready",
                ...
            }
        }
    """
    engine = get_book_engine()

    try:
        book = await engine.generate_book(
            title=req.title,
            story=req.story,
            style=req.style,
            num_pages=req.pages,
            audience=req.audience,
            generate_images=req.generate_images,
        )
        return {
            "success": True,
            "data": book.to_dict(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/list", response_model=Dict[str, Any])
async def list_books(
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
    """
    获取所有绘本列表。

    Returns:
        {
            "success": true,
            "data": [{id, title, style, status, page_count, created_at, ...}, ...],
            "total": 5
        }
    """
    engine = get_book_engine()
    books = engine.list_books()
    if q:
        books = [b for b in books if q.lower() in (b.title or "").lower()]
    total = len(books)
    if sort_by == "title":
        books = sorted(books, key=lambda b: b.title, reverse=(order == "desc"))
    page = books[offset: offset + limit]
    return {
        "success": True,
        "data": [b.to_dict() for b in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{book_id}", response_model=Dict[str, Any])
async def get_book(book_id: str):
    """
    获取绘本详情。

    Returns:
        {
            "success": true,
            "data": {id, title, story, pages:[{page_num, text, illustration_prompt, image_url}], ...}
        }
    """
    validate_id(book_id, "book_id")
    engine = get_book_engine()
    book = engine.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"绘本 {book_id} 未找到")
    return {
        "success": True,
        "data": book.to_dict(),
    }


@router.delete("/{book_id}", response_model=Dict[str, Any])
async def delete_book(book_id: str):
    """
    删除绘本及其插图文件。

    Returns:
        {"success": true, "message": "绘本已删除"}
    """
    validate_id(book_id, "book_id")
    engine = get_book_engine()
    ok = engine.delete_book(book_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"绘本 {book_id} 未找到")
    return {
        "success": True,
        "message": f"绘本 {book_id} 已删除",
    }


@router.get("/{book_id}/export")
async def export_book(
    book_id: str,
    format: str = Query("html", description="导出格式: html / png"),
):
    """
    导出绘本。

    Query参数:
        format: 导出格式 (html / png — pdf/epub需要额外依赖)

    返回文件下载。
    """
    validate_id(book_id, "book_id")
    engine = get_book_engine()
    book = engine.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"绘本 {book_id} 未找到")

    if format == "html":
        html_path = engine.render_html_path(book_id)
        if not html_path:
            raise HTTPException(status_code=500, detail="HTML渲染失败")

        return FileResponse(
            html_path,
            media_type="text/html; charset=utf-8",
            filename=f"{book.title.replace(' ', '_')}.html",
        )

    elif format == "png":
        # Return first page as PNG (for thumbnail/preview)
        if not book.pages:
            raise HTTPException(status_code=404, detail="绘本无页面")

        first_page = book.pages[0]
        if first_page.image_path and Path(first_page.image_path).exists():
            return FileResponse(
                first_page.image_path,
                media_type="image/png",
                filename=f"{book.title.replace(' ', '_')}_page1.png",
            )
        raise HTTPException(status_code=404, detail="暂无插图文件")

    elif format == "pdf":
        raise HTTPException(
            status_code=501,
            detail="PDF导出需要安装 weasyprint 或 playwright。请使用 HTML 格式后在浏览器中打印为 PDF。"
        )

    elif format == "epub":
        raise HTTPException(
            status_code=501,
            detail="EPUB导出需要安装 ebooklib。请使用 HTML 格式后转换。"
        )

    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}. 支持: html, png")


@router.get("/{book_id}/preview", response_class=HTMLResponse)
async def preview_book(book_id: str):
    """
    获取绘本HTML预览(可直接在浏览器中查看)。

    注: 大绘本(>10页含base64图片)可能返回较大的响应体。
    """
    validate_id(book_id, "book_id")
    engine = get_book_engine()
    html = engine.render_html(book_id)
    if not html:
        raise HTTPException(status_code=404, detail=f"绘本 {book_id} 未找到")
    return HTMLResponse(content=html)


@router.get("/images/{filename:path}")
async def get_book_image(filename: str, book_id: str = Query("")):
    """
    获取绘本插图文件。

    如果指定 book_id query 参数，则在对应绘本目录查找图片。
    """
    engine = get_book_engine()
    # Try with book_id context first
    if book_id:
        img_path = engine.get_image_path(book_id, filename)
        if img_path:
            return FileResponse(img_path, media_type="image/png")

    # Fallback: scan all book directories
    import os
    for book in engine.list_books():
        img_path = engine.get_image_path(book.id, filename)
        if img_path and os.path.exists(img_path):
            return FileResponse(img_path, media_type="image/png")

    raise HTTPException(status_code=404, detail=f"图片 {filename} 未找到")
