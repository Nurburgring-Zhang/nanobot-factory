"""
F1.14: Search API Routes — Multimodal Vector Retrieval
=======================================================
Unified search API supporting text, image, and hybrid search.

Endpoints:
  POST   /api/search                  — Unified multimodal search
  POST   /api/search/images           — Image similarity search (by image file path)
  POST   /api/search/hybrid           — Hybrid BM25+FTS5 search
  GET    /api/search/indices          — List available search indices
  POST   /api/search/index/text       — Index text documents
  POST   /api/search/index/images     — Index image files
  DELETE /api/search/index/{name}     — Delete an index
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# R2-3: 路径 ID 校验 (index name)
from api._common.validators import validate_id

# ---------------------------------------------------------------------------
# Create router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/search", tags=["search"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = ""
    collection: str = "text_index"
    top_k: int = Field(default=10, ge=1, le=100)
    search_type: str = Field(default="vector", description="vector|fts5|hybrid")
    filters: Optional[Dict[str, Any]] = None


class ImageSearchRequest(BaseModel):
    image_path: str = ""
    collection: str = "image_index"
    top_k: int = Field(default=5, ge=1, le=50)


class IndexTextRequest(BaseModel):
    collection: str = "text_index"
    documents: List[str] = Field(default_factory=list)
    metadata_list: Optional[List[Dict[str, Any]]] = None


class IndexImageRequest(BaseModel):
    collection: str = "image_index"
    image_paths: List[str] = Field(default_factory=list)
    metadata_list: Optional[List[Dict[str, Any]]] = None


class CreateIndexRequest(BaseModel):
    name: str = ""
    dimension: int = Field(default=256, ge=1, le=4096)


class DeleteVectorsRequest(BaseModel):
    collection: str = ""
    doc_ids: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("")
@router.post("/")
async def search(req: SearchRequest):
    """Unified multimodal search.

    Supports:
      - Text vector search (TF-IDF + BM25)
      - FTS5 full-text search
      - Hybrid (combined ranking)

    Example:
        POST /api/search
        {"query": "machine learning", "collection": "text_index", "search_type": "vector", "top_k": 10}
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()

        if req.search_type == "hybrid":
            results = retriever.hybrid_search(req.query, req.top_k)
        elif req.search_type == "fts5":
            results = retriever.search(req.collection, req.query,
                                       req.top_k, search_type="fts5")
        else:  # vector (default)
            results = retriever.search(req.collection, req.query,
                                       req.top_k, search_type="vector")

        return {
            "success": True,
            "query": req.query,
            "collection": req.collection,
            "search_type": req.search_type,
            "total": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/images")
async def search_images(req: ImageSearchRequest):
    """Search for similar images by image fingerprint (pHash + color).

    Provide an image file path, get back similar images from the index.

    Example:
        POST /api/search/images
        {"image_path": "/path/to/query.jpg", "collection": "image_index", "top_k": 5}
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()

        if not os.path.exists(req.image_path):
            return {"success": False, "error": f"Image not found: {req.image_path}"}

        results = retriever.search_images(
            req.collection, req.image_path, req.top_k
        )

        return {
            "success": True,
            "query_image": req.image_path,
            "collection": req.collection,
            "total": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Image search failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/hybrid")
async def hybrid_search(req: SearchRequest):
    """Hybrid search combining vector (BM25/TF-IDF) + FTS5 with reciprocal rank fusion.

    Example:
        POST /api/search/hybrid
        {"query": "deep learning", "top_k": 10}
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()

        results = retriever.hybrid_search(req.query, req.top_k)

        return {
            "success": True,
            "query": req.query,
            "search_type": "hybrid",
            "total": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/indices")
async def list_indices(
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
    """List all available search indices/collections.

    Example:
        GET /api/search/indices
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()
        indices = retriever.store.list_indices()

        if q:
            indices = [i for i in indices if q.lower() in (i.get("name") or "").lower()]
        total = len(indices)
        if sort_by:
            indices = sorted(
                indices, key=lambda i: i.get(sort_by) or "",
                reverse=(order == "desc"),
            )
        page = indices[offset: offset + limit]
        return {
            "success": True,
            "indices": page,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"List indices failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/index/create")
async def create_index(req: CreateIndexRequest):
    """Create a new vector index/collection.

    Example:
        POST /api/search/index/create
        {"name": "my_collection", "dimension": 256}
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()
        result = retriever.store.create_index(req.name, req.dimension)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/index/{name}")
async def delete_index(name: str):
    """Delete a search index and all its vectors.

    Example:
        DELETE /api/search/index/my_collection
    """
    validate_id(name, "name")
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()
        result = retriever.store.delete_index(name)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Indexing Routes
# ---------------------------------------------------------------------------

@router.post("/index/text")
async def index_text(req: IndexTextRequest):
    """Index text documents for vector search.

    Example:
        POST /api/search/index/text
        {
          "collection": "my_texts",
          "documents": ["doc one text", "doc two text"],
          "metadata_list": [{"source": "wiki"}, {"source": "paper"}]
        }
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()

        if not req.documents:
            return {"success": False, "error": "No documents provided"}

        result = retriever.index_text(
            req.collection, req.documents, req.metadata_list
        )
        return result
    except Exception as e:
        logger.error(f"Index text failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/index/images")
async def index_images(req: IndexImageRequest):
    """Index image files for visual similarity search.

    Computes pHash + dominant color fingerprints for each image.

    Example:
        POST /api/search/index/images
        {
          "collection": "my_images",
          "image_paths": ["/data/img1.jpg", "/data/img2.png"],
          "metadata_list": [{"label": "cat"}, {"label": "dog"}]
        }
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()

        if not req.image_paths:
            return {"success": False, "error": "No image paths provided"}

        # Validate paths exist
        missing = [p for p in req.image_paths if not os.path.exists(p)]
        if missing:
            return {
                "success": False,
                "error": f"Images not found: {missing[:5]}",
                "hint": "Use absolute paths or paths relative to the IMDF project root"
            }

        result = retriever.index_images(
            req.collection, req.image_paths, req.metadata_list
        )
        return result
    except Exception as e:
        logger.error(f"Index images failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/index/delete-vectors")
async def delete_vectors(req: DeleteVectorsRequest):
    """Delete specific vectors from a collection by doc_id.

    Example:
        POST /api/search/index/delete-vectors
        {"collection": "text_index", "doc_ids": ["abc123", "def456"]}
    """
    try:
        from engines.vector_retrieval import get_retriever
        retriever = get_retriever()
        result = retriever.store.delete_vectors(req.collection, req.doc_ids)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Quick Test / Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def search_status(
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
    """Get search system status — collection counts, DB path, etc."""
    try:
        from engines.vector_retrieval import get_retriever, DEFAULT_VECTOR_DB
        retriever = get_retriever()
        indices = retriever.store.list_indices()

        if q:
            indices = [i for i in indices if q.lower() in (i.get("name") or "").lower()]
        total = len(indices)
        if sort_by:
            indices = sorted(
                indices, key=lambda i: i.get(sort_by) or "",
                reverse=(order == "desc"),
            )
        page = indices[offset: offset + limit]

        total_vectors = sum(idx.get("doc_count", 0) for idx in page)

        return {
            "success": True,
            "status": "ok",
            "db_path": DEFAULT_VECTOR_DB,
            "total_collections": total,
            "total_vectors": total_vectors,
            "indices": page,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
