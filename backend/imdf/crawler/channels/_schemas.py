"""Pydantic v2 schemas for crawler channels (P20-B1)

Pydantic v2 models for the modern async search API. These models provide:
- Type-safe request/response validation
- JSON serialization with `model_dump()` and `model_dump_json()`
- Backward-compat with the existing dataclass-based CrawledItem
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    """搜索请求 — Pydantic v2 验证 input."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=200)
    max_results: int = Field(default=50, ge=1, le=100)
    page: int = Field(default=1, ge=1, le=20)
    extra: Dict[str, Any] = Field(default_factory=dict)


class CrawledItemModel(BaseModel):
    """Pydantic v2 版本的 10 字段 CrawledItem."""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    id: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=2000)
    source: str = Field(..., min_length=1, max_length=50)
    author: str = Field(default="", max_length=200)
    keywords: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    thumbnail_url: str = Field(default="", max_length=2000)
    extra: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dataclass(cls, item: Any) -> "CrawledItemModel":
        ct = item.created_at
        if ct is None:
            ct = datetime.utcnow()
        elif isinstance(ct, str):
            try:
                ct = datetime.fromisoformat(ct)
            except (ValueError, TypeError):
                ct = datetime.utcnow()
        return cls(
            id=str(item.id),
            url=item.url,
            title=item.title or "",
            description=item.description or "",
            source=item.source or "unknown",
            author=item.author or "",
            keywords=list(item.keywords or []),
            created_at=ct,
            thumbnail_url=item.thumbnail_url or "",
            extra=dict(item.extra or {}),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrawledItemModel":
        ct = data.get("created_at")
        if isinstance(ct, str):
            try:
                ct = datetime.fromisoformat(ct)
            except (ValueError, TypeError):
                ct = datetime.utcnow()
        elif ct is None:
            ct = datetime.utcnow()
        return cls(
            id=str(data.get("id", "")),
            url=data.get("url", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            source=data.get("source", "unknown"),
            author=data.get("author", ""),
            keywords=list(data.get("keywords") or []),
            created_at=ct,
            thumbnail_url=data.get("thumbnail_url", ""),
            extra=dict(data.get("extra") or {}),
        )


class SearchResponse(BaseModel):
    """Pydantic v2 搜索响应 — 包含 items + 元数据."""
    model_config = ConfigDict(extra="allow")

    query: str
    items: List[CrawledItemModel] = Field(default_factory=list)
    count: int = 0
    page: int = 1
    has_more: bool = False
    mock: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["SearchRequest", "CrawledItemModel", "SearchResponse", "convert_crawl_result"]


def convert_crawl_result(result_items: List[Dict[str, Any]],
                        query: str, page: int = 1,
                        mock: bool = False,
                        extra_metadata: Optional[Dict[str, Any]] = None) -> List[CrawledItemModel]:
    """把 crawl() 的 items (list of dict) 转换为 List[CrawledItemModel].

    给 5 渠道 crawler 的 async search() 共享.
    """
    out: List[CrawledItemModel] = []
    for d in result_items:
        try:
            out.append(CrawledItemModel.from_dict(d))
        except Exception:
            continue
    return out


def build_search_response(result_items: List[Dict[str, Any]],
                          query: str, page: int = 1,
                          mock: bool = False,
                          extra_metadata: Optional[Dict[str, Any]] = None) -> SearchResponse:
    """从 crawl() 结果构造 SearchResponse (Pydantic v2)."""
    items = convert_crawl_result(result_items, query=query, page=page, mock=mock)
    return SearchResponse(
        query=query,
        items=items,
        count=len(items),
        page=page,
        has_more=len(items) >= 50,  # 启发式: 达到上限可能还有更多
        mock=mock,
        metadata=extra_metadata or {},
    )
