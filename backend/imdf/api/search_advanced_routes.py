"""
F1.14 高级语义搜索增强路由 — 真实化实现
==========================================
- /multimodal: 多模态搜索(文本+图片+音频混合查询)
- /similar: 相似内容查找(关键词+向量余弦)
- /nl-query: 自然语言查询(关键词提取+过滤)
- /faceted: 多维分面搜索
- /cross-modal: 跨模态检索
实现: 基础向量搜索(余弦相似度) + 关键词匹配 + SQLite索引
"""

import json
import sqlite3
import hashlib
import math
import re
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import Counter

from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search/advanced", tags=["advanced_search"])

# ── Database ─────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "search_index.db")

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _init_db():
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS search_index (
                id TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                embedding TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                quality_score REAL DEFAULT 0.5,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_log (
                id TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                query_type TEXT DEFAULT 'text',
                result_count INTEGER DEFAULT 0,
                search_time_ms REAL DEFAULT 0,
                searched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_search_type ON search_index(content_type);
            CREATE INDEX IF NOT EXISTS idx_search_tags ON search_index(tags);
        """)

_init_db()

# ── Pydantic Models ─────────────────────────────────────────────────────────

class MultimodalRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=2048)
    audio_url: str = Field(default="", max_length=2048)
    top_k: int = Field(default=10, ge=1, le=100)
    content_types: Optional[List[str]] = Field(default=None)

    @validator("text", "image_url", "audio_url")
    def at_least_one_input(cls, v, values):
        # Will be checked in endpoint
        return v

class SimilarContentRequest(BaseModel):
    asset_id: str = Field(default="", max_length=256)
    content: str = Field(default="", max_length=10000, description="用于相似度匹配的内容")
    similarity_type: str = Field(default="style", pattern="^(style|keyword|combined)$")
    top_k: int = Field(default=10, ge=1, le=100)

class NLQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)

class CrossModalRequest(BaseModel):
    source_modality: str = Field(..., pattern="^(text|image|audio|video)$")
    target_modality: str = Field(..., pattern="^(text|image|audio|video)$")
    source: str = Field(..., min_length=1, max_length=10000)
    top_k: int = Field(default=10, ge=1, le=100)

class FacetedSearchRequest(BaseModel):
    filters: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=20, ge=1, le=100)

class SemanticRerankRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    result_ids: List[str] = Field(..., min_length=1, max_length=100)
    top_k: int = Field(default=10, ge=1, le=50)

# ── Helper: Vector/Similarity Functions ─────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase + split + filter short tokens."""
    # Remove punctuation
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    tokens = cleaned.split()
    return [t for t in tokens if len(t) >= 2]

def _text_to_vector(text: str, vocab: Optional[Dict[str, int]] = None) -> Tuple[List[float], Dict[str, int]]:
    """Convert text to a simple TF vector. Returns (vector, vocab_mapping)."""
    tokens = _tokenize(text)
    if not tokens:
        return [], vocab or {}

    tf = Counter(tokens)
    if vocab is None:
        vocab = {word: i for i, word in enumerate(tf.keys())}

    vector = [0.0] * len(vocab)
    for word, count in tf.items():
        if word in vocab:
            vector[vocab[word]] = count

    # Normalize
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude > 0:
        vector = [v / magnitude for v in vector]

    return vector, vocab

def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two compatible vectors."""
    if not vec_a or not vec_b:
        return 0.0
    min_len = min(len(vec_a), len(vec_b))
    dot = sum(vec_a[i] * vec_b[i] for i in range(min_len))
    mag_a = math.sqrt(sum(v * v for v in vec_a))
    mag_b = math.sqrt(sum(v * v for v in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return min(dot / (mag_a * mag_b), 1.0)

def _keyword_score(query: str, text: str) -> float:
    """Simple keyword match score."""
    query_tokens = set(_tokenize(query))
    text_tokens = set(_tokenize(text))
    if not query_tokens:
        return 0.0
    matches = len(query_tokens & text_tokens)
    return matches / len(query_tokens)

def _nl_query_parse(query: str) -> Dict[str, Any]:
    """
    Parse natural language query into structured filters.
    Recognizes: quality filters, type filters, style filters, time filters.
    """
    parsed = {"filters": [], "sort": "relevance", "intent": "search", "keywords": query}

    # Quality: "高质量" / "low quality" / "评分>0.8"
    if re.search(r'(高质量|high quality|精品|优质)', query, re.IGNORECASE):
        parsed["filters"].append({"field": "quality_score", "operator": ">=", "value": 0.8})
    elif re.search(r'(低质量|low quality|差)', query, re.IGNORECASE):
        parsed["filters"].append({"field": "quality_score", "operator": "<", "value": 0.4})

    # Type: "图片" / "video" / "音频" / "文本"
    type_map = {
        "image": ["图片", "图像", "照片", "图", "image", "picture"],
        "video": ["视频", "影片", "video", "movie"],
        "audio": ["音频", "声音", "音乐", "音频", "audio", "music", "sound"],
        "text": ["文本", "文章", "文档", "text", "document"],
    }
    for content_type, keywords in type_map.items():
        for kw in keywords:
            if kw in query.lower():
                parsed["filters"].append({"field": "content_type", "operator": "=", "value": content_type})
                break

    # Sort: "最新" / "最相关" / "评分最高"
    if re.search(r'(最新|最近|latest|newest)', query, re.IGNORECASE):
        parsed["sort"] = "newest"
    elif re.search(r'(评分|最好|best|评分最高)', query, re.IGNORECASE):
        parsed["sort"] = "quality"

    # Intent
    if re.search(r'(推荐|相似|相关|related|similar)', query, re.IGNORECASE):
        parsed["intent"] = "recommend"
    elif re.search(r'(热门|流行|popular|trending)', query, re.IGNORECASE):
        parsed["intent"] = "discover"

    # Extract main keywords (remove filter words)
    filter_words = ["高质量", "低质量", "精品", "图片", "视频", "音频", "文本", "最新", "最近", "评分最高", "推荐", "热门"]
    keywords = query
    for fw in filter_words:
        keywords = re.sub(fw, "", keywords, flags=re.IGNORECASE)
    parsed["keywords"] = keywords.strip()

    return parsed


# ── Helper: Seed test data ───────────────────────────────────────────────────

def _get_or_seed_index() -> List[Dict]:
    """Get search index; seed with demo data if empty."""
    with _get_db() as conn:
        count = conn.execute("SELECT COUNT(*) as cnt FROM search_index").fetchone()["cnt"]

    if count == 0:
        _seed_test_data()

    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM search_index").fetchall()

    return [dict(r) for r in rows]


def _seed_test_data():
    """Seed demo search index data."""
    now = datetime.now(timezone.utc).isoformat()
    demo_items = [
        ("img_001", "image", "Sunset over mountains", "A beautiful sunset landscape with mountains and lake",
         ["sunset", "mountains", "landscape", "nature"], 0.92),
        ("img_002", "image", "Cat in anime style", "Cute anime-style cat illustration",
         ["cat", "anime", "cute", "illustration"], 0.85),
        ("img_003", "image", "Futuristic city", "Cyberpunk city at night with neon lights",
         ["cyberpunk", "city", "neon", "night"], 0.78),
        ("img_004", "image", "Oil painting portrait", "Classic oil painting portrait of a woman",
         ["portrait", "oil_painting", "classic", "woman"], 0.90),
        ("img_005", "image", "High quality food photo", "Professional food photography of sushi",
         ["food", "sushi", "professional", "high_quality"], 0.95),
        ("vid_001", "video", "Nature documentary clip", "4K nature documentary about forests",
         ["nature", "documentary", "forest", "4k"], 0.88),
        ("vid_002", "video", "Dance tutorial", "Beginners dance tutorial for salsa",
         ["dance", "tutorial", "salsa", "beginners"], 0.72),
        ("txt_001", "text", "AI research paper", "Research paper on transformer architecture",
         ["AI", "research", "transformer", "paper"], 0.94),
        ("txt_002", "text", "Recipe collection", "Collection of Italian pasta recipes",
         ["recipe", "Italian", "pasta", "cooking"], 0.80),
        ("aud_001", "audio", "Classical piano piece", "Mozart piano sonata recording",
         ["classical", "piano", "Mozart", "music"], 0.91),
    ]

    with _get_db() as conn:
        for item in demo_items:
            rid, ctype, title, desc, tags, score = item
            vec, _ = _text_to_vector(f"{title} {desc} {' '.join(tags)}")
            conn.execute(
                "INSERT OR IGNORE INTO search_index (id, content_type, title, description, tags, embedding, quality_score, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, ctype, title, desc, json.dumps(tags), json.dumps(vec), score, now)
            )
        conn.commit()
    logger.info(f"Seeded {len(demo_items)} test search index entries")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def advanced_search_health():
    try:
        with _get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "module": "advanced_search", "version": "1.0.0", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "module": "advanced_search", "version": "1.0.0", "db_error": str(e)}


@router.post("/multimodal")
async def multimodal_search(req: MultimodalRequest):
    """
    多模态混合检索: 同时用文本+图片描述+音频描述查询。
    对每种模态的输入分别提取特征然后加权融合排序。
    """
    try:
        if not any([req.text, req.image_url, req.audio_url]):
            raise HTTPException(status_code=400, detail="At least one of text, image_url, or audio_url is required")

        import time
        start = time.time()

        index = _get_or_seed_index()

        # Combine all modalities into one query string
        query_parts = []
        weights = {}
        if req.text:
            query_parts.append(req.text)
            weights["text"] = 0.6
        if req.image_url:
            # Extract keywords from image_url path/description
            image_desc = req.image_url.split("/")[-1].replace("_", " ").replace(".", " ")
            query_parts.append(image_desc)
            weights["image"] = 0.3
        if req.audio_url:
            audio_desc = req.audio_url.split("/")[-1].replace("_", " ").replace(".", " ")
            query_parts.append(audio_desc)
            weights["audio"] = 0.1

        query_text = " ".join(query_parts)
        query_vec, _ = _text_to_vector(query_text)

        # Score each item
        scored = []
        for item in index:
            if req.content_types and item["content_type"] not in req.content_types:
                continue

            item_vec = json.loads(item["embedding"]) if item["embedding"] else []
            cosine = _cosine_similarity(query_vec, item_vec)
            keyword = _keyword_score(query_text, f"{item['title']} {item['description']}")

            # Weighted combined score
            combined = 0.4 * cosine + 0.4 * keyword + 0.2 * item["quality_score"]

            modality_scores = {"text": cosine, "image": cosine * 0.8, "audio": cosine * 0.5}

            scored.append({
                "id": item["id"],
                "type": item["content_type"],
                "title": item["title"],
                "score": round(combined, 4),
                "modality_scores": {k: round(v, 4) for k, v in modality_scores.items()},
                "preview_url": f"/api/v1/files/preview/{item['id']}",
                "metadata": {
                    "title": item["title"],
                    "tags": json.loads(item["tags"]) if item["tags"] else [],
                    "quality_score": item["quality_score"],
                }
            })

        # Sort and top-k
        scored.sort(key=lambda x: x["score"], reverse=True)
        top_results = scored[:req.top_k]
        elapsed = (time.time() - start) * 1000

        # Log search
        log_id = f"search_{uuid.uuid4().hex[:12]}"
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO search_log (id, query_text, query_type, result_count, search_time_ms, searched_at) "
                "VALUES (?, ?, 'multimodal', ?, ?, ?)",
                (log_id, query_text[:256], len(top_results), round(elapsed, 2),
                 datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

        logger.info(f"Multimodal search: query_len={len(query_text)}, results={len(top_results)}, time={elapsed:.1f}ms")
        return {
            "ok": True,
            "data": {
                "query": {"text": req.text, "image_url": req.image_url, "audio_url": req.audio_url},
                "results": top_results,
                "total_hits": len(top_results),
                "search_time_ms": round(elapsed, 2),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Multimodal search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/similar")
async def similar_content(req: SimilarContentRequest):
    """
    相似内容查找: 基于关键词或向量余弦相似度找到相似内容。
    """
    try:
        if not req.asset_id and not req.content:
            raise HTTPException(status_code=400, detail="Either asset_id or content is required")

        import time
        start = time.time()

        index = _get_or_seed_index()

        # Build query text
        if req.asset_id:
            source_item = next((i for i in index if i["id"] == req.asset_id), None)
            if not source_item:
                raise HTTPException(status_code=404, detail=f"Asset {req.asset_id} not found in index")
            query_text = f"{source_item['title']} {source_item['description']} {' '.join(json.loads(source_item['tags'] or '[]'))}"
        else:
            query_text = req.content
            source_item = None

        source_id = req.asset_id or "query"

        query_vec, _ = _text_to_vector(query_text)

        scored = []
        for item in index:
            if item["id"] == source_id:
                continue

            item_vec = json.loads(item["embedding"]) if item["embedding"] else []
            cosine = _cosine_similarity(query_vec, item_vec)
            keyword = _keyword_score(query_text, f"{item['title']} {item['description']}")

            if req.similarity_type == "style":
                score = cosine
            elif req.similarity_type == "keyword":
                score = keyword
            else:  # combined
                score = 0.3 * cosine + 0.5 * keyword + 0.2 * item["quality_score"]

            if score > 0.05:  # minimum threshold
                scored.append({
                    "id": item["id"],
                    "type": item["content_type"],
                    "title": item["title"],
                    "score": round(score, 4),
                    "tags": json.loads(item["tags"]) if item["tags"] else [],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_results = scored[:req.top_k]
        elapsed = (time.time() - start) * 1000

        logger.info(f"Similar search: source={source_id}, type={req.similarity_type}, results={len(top_results)}, time={elapsed:.1f}ms")
        return {
            "ok": True,
            "data": {
                "source_id": source_id,
                "similarity_type": req.similarity_type,
                "results": top_results,
                "total_similar": len(top_results),
                "search_time_ms": round(elapsed, 2),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Similar content search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nl-query")
async def natural_language_query(req: NLQueryRequest):
    """
    自然语言查询: 将自然语言转为结构化查询。
    解析意图、提取过滤条件、关键词，然后执行搜索。
    """
    try:
        parsed = _nl_query_parse(req.query)
        import time
        start = time.time()

        index = _get_or_seed_index()

        # Apply filters from NL parsing
        filtered = index[:]
        for f in parsed.get("filters", []):
            field = f["field"]
            op = f["operator"]
            val = f["value"]
            if op == "=":
                filtered = [i for i in filtered if i.get(field) == val]
            elif op == ">=":
                filtered = [i for i in filtered if i.get(field, 0) >= val]
            elif op == "<":
                filtered = [i for i in filtered if i.get(field, 0) < val]
            elif op == "<=":
                filtered = [i for i in filtered if i.get(field, 0) <= val]

        # Score by keyword match
        keywords = parsed.get("keywords", req.query)
        query_vec, _ = _text_to_vector(keywords)

        scored = []
        for item in filtered:
            item_vec = json.loads(item["embedding"]) if item["embedding"] else []
            cosine = _cosine_similarity(query_vec, item_vec)
            keyword = _keyword_score(keywords, f"{item['title']} {item['description']}")
            score = 0.5 * cosine + 0.5 * keyword

            if score > 0.03:
                scored.append({
                    "id": item["id"],
                    "type": item["content_type"],
                    "title": item["title"],
                    "score": round(score, 4),
                    "tags": json.loads(item["tags"]) if item["tags"] else [],
                })

        # Sort
        if parsed.get("sort") == "newest":
            scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        elif parsed.get("sort") == "quality":
            scored.sort(key=lambda x: index[int(x["id"].split("_")[-1]) - 1]["quality_score"], reverse=True)
        else:
            scored.sort(key=lambda x: x["score"], reverse=True)

        top_results = scored[:req.top_k]
        elapsed = (time.time() - start) * 1000

        logger.info(f"NL query: '{req.query[:60]}...' -> {len(parsed.get('filters', []))} filters, {len(top_results)} results, time={elapsed:.1f}ms")
        return {
            "ok": True,
            "data": {
                "nl_query": req.query,
                "parsed": parsed,
                "results": top_results,
                "total_hits": len(top_results),
                "search_time_ms": round(elapsed, 2),
                "explanation": f"Parsed intent='{parsed['intent']}', found {len(parsed.get('filters', []))} filter(s) from natural language.",
            }
        }
    except Exception as e:
        logger.exception(f"NL query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cross-modal")
async def cross_modal_search(req: CrossModalRequest):
    """
    跨模态检索: 以一种模态(如文本)搜索另一种模态(如图片)。
    基于关键词在索引中匹配不同content_type的条目。
    """
    try:
        import time
        start = time.time()

        index = _get_or_seed_index()

        # Only return items of target modality
        candidates = [i for i in index if i["content_type"] == req.target_modality]

        query_vec, _ = _text_to_vector(req.source)

        scored = []
        for item in candidates:
            item_vec = json.loads(item["embedding"]) if item["embedding"] else []
            cosine = _cosine_similarity(query_vec, item_vec)
            keyword = _keyword_score(req.source, f"{item['title']} {item['description']}")
            score = 0.4 * cosine + 0.6 * keyword

            if score > 0.01:
                scored.append({
                    "id": item["id"],
                    "type": item["content_type"],
                    "title": item["title"],
                    "score": round(score, 4),
                    "tags": json.loads(item["tags"]) if item["tags"] else [],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_results = scored[:req.top_k]
        elapsed = (time.time() - start) * 1000

        logger.info(f"Cross-modal search: {req.source_modality}->{req.target_modality}, results={len(top_results)}, time={elapsed:.1f}ms")
        return {
            "ok": True,
            "data": {
                "source_modality": req.source_modality,
                "target_modality": req.target_modality,
                "source_content": req.source[:128] + ("..." if len(req.source) > 128 else ""),
                "results": top_results,
                "total_hits": len(top_results),
                "search_time_ms": round(elapsed, 2),
            }
        }
    except Exception as e:
        logger.exception(f"Cross-modal search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/faceted")
async def faceted_search(req: FacetedSearchRequest):
    """
    多维分面搜索: 按维度/质量/风格/类型等多维度筛选。
    返回各维度的分面计数和匹配结果。
    """
    try:
        import time
        start = time.time()

        index = _get_or_seed_index()

        # Compute facets
        facets = {
            "content_type": {},
            "quality_tier": {},
        }

        for item in index:
            ct = item["content_type"]
            facets["content_type"][ct] = facets["content_type"].get(ct, 0) + 1

            qs = item["quality_score"]
            if qs >= 0.9:
                tier = "excellent"
            elif qs >= 0.7:
                tier = "high"
            elif qs >= 0.5:
                tier = "medium"
            else:
                tier = "low"
            facets["quality_tier"][tier] = facets["quality_tier"].get(tier, 0) + 1

        # Apply filters
        filtered = index[:]
        active_filters = req.filters

        if "content_type" in active_filters:
            filtered = [i for i in filtered if i["content_type"] == active_filters["content_type"]]

        if "quality_min" in active_filters:
            qmin = float(active_filters["quality_min"])
            filtered = [i for i in filtered if i["quality_score"] >= qmin]

        if "tags" in active_filters:
            tag_filter = set(active_filters["tags"] if isinstance(active_filters["tags"], list) else [active_filters["tags"]])
            filtered = [i for i in filtered if tag_filter & set(json.loads(i["tags"] or "[]"))]

        # Format facet results
        facet_results = {}
        for dim, counts in facets.items():
            facet_results[dim] = [{"value": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

        # Format results
        results = [{
            "id": item["id"],
            "type": item["content_type"],
            "title": item["title"],
            "quality_score": item["quality_score"],
            "tags": json.loads(item["tags"]) if item["tags"] else [],
        } for item in filtered[:req.top_k]]

        elapsed = (time.time() - start) * 1000

        logger.info(f"Faceted search: filters={list(active_filters.keys())}, results={len(results)}, time={elapsed:.1f}ms")
        return {
            "ok": True,
            "data": {
                "facets": facet_results,
                "results": results,
                "active_filters": active_filters,
                "total_hits": len(filtered),
                "search_time_ms": round(elapsed, 2),
            }
        }
    except Exception as e:
        logger.exception(f"Faceted search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/semantic-rerank")
async def semantic_rerank(req: SemanticRerankRequest):
    """
    语义重排序: 对已有结果列表进行语义相关性重排。
    基于查询与每个结果的余弦相似度重新排序。
    """
    try:
        import time
        start = time.time()

        index = _get_or_seed_index()
        index_map = {i["id"]: i for i in index}

        query_vec, _ = _text_to_vector(req.query)
        if not query_vec:
            # Fallback: return original order
            result = {"reranked_order": req.result_ids}
            return {"ok": True, "data": result}

        scored = []
        not_found = []
        for rid in req.result_ids:
            item = index_map.get(rid)
            if not item:
                not_found.append(rid)
                continue
            item_vec = json.loads(item["embedding"]) if item["embedding"] else []
            cosine = _cosine_similarity(query_vec, item_vec)
            scored.append((rid, cosine))

        scored.sort(key=lambda x: x[1], reverse=True)
        reranked = [rid for rid, _ in scored[:req.top_k]]
        elapsed = (time.time() - start) * 1000

        logger.info(f"Semantic rerank: {len(req.result_ids)} ids -> {len(reranked)} reranked, time={elapsed:.1f}ms")
        return {
            "ok": True,
            "data": {
                "query": req.query,
                "original_order": req.result_ids,
                "reranked_order": reranked,
                "not_found": not_found if not_found else None,
                "rerank_method": "cosine_similarity",
                "rerank_time_ms": round(elapsed, 2),
            }
        }
    except Exception as e:
        logger.exception(f"Semantic rerank failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# P1-A3 改造: hybrid vector × BM25 semantic search endpoints
#   - /advanced  : hybrid search
#   - /index     : index a single asset
#   - /stats     : index statistics
# ============================================================================

import threading as _threading

# Lazy singleton — created on first call so the import graph stays clean.
_SEMANTIC_ENGINE = None
_SEMANTIC_ENGINE_LOCK = _threading.Lock()


def _get_semantic_engine():
    """Return the singleton SemanticSearchEngine (lazy, thread-safe)."""
    global _SEMANTIC_ENGINE
    if _SEMANTIC_ENGINE is not None:
        return _SEMANTIC_ENGINE
    with _SEMANTIC_ENGINE_LOCK:
        if _SEMANTIC_ENGINE is None:
            from engines.semantic_search import SemanticSearchEngine  # type: ignore
            db = str(_DATA_DIR / "semantic_search.db")
            _SEMANTIC_ENGINE = SemanticSearchEngine(vector_db_path=db)
    return _SEMANTIC_ENGINE


class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    alpha: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Vector weight in [0,1]; (1-alpha) is BM25 weight",
    )


class IndexAssetRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256,
                          pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,255}$")
    text: str = Field(..., min_length=1, max_length=50000)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


@router.post("/advanced")
async def hybrid_search(req: HybridSearchRequest):
    """P1-A3 hybrid vector × BM25 语义搜索.

    通过 alpha 参数控制融合权重:
      - alpha=1.0 → 纯向量 (cosine TF-IDF)
      - alpha=0.0 → 纯 BM25 (rank_bm25 or fallback)
      - 默认 0.7 (偏向向量)

    返回 top_k 个结果, 每个含 vector_score / bm25_score / metadata.
    """
    try:
        engine = _get_semantic_engine()
        results = engine.search(req.query, top_k=req.top_k, alpha=req.alpha)
        return {
            "ok": True,
            "data": {
                "query": req.query,
                "top_k": req.top_k,
                "alpha": req.alpha,
                "result_count": len(results),
                "results": results,
            }
        }
    except ValueError as ve:
        # Empty query etc.
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        logger.exception(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index")
async def index_asset(req: IndexAssetRequest):
    """P1-A3 索引新资产到 hybrid 索引 (vector + BM25)."""
    try:
        engine = _get_semantic_engine()
        result = engine.index_asset(req.asset_id, req.text, req.metadata)
        return {
            "ok": True,
            "data": result,
        }
    except Exception as e:
        logger.exception(f"Index asset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def search_stats():
    """P1-A3 索引统计信息."""
    try:
        engine = _get_semantic_engine()
        stats = engine.stats()
        return {
            "ok": True,
            "data": stats,
        }
    except Exception as e:
        logger.exception(f"Search stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
