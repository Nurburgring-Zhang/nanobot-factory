"""
F2.6 模板市场引擎 — Template Market Engine
============================================
模板市场核心引擎:
- 模板CRUD (创建/更新/删除/发布)
- 模板分类 (短剧/绘本/商品图/数字人/广告)
- 模板评分 + 下载计数
- 模板搜索 (关键词+分类+标签)
- SQLite持久化存储

Persistence: data/imdf.db → template_market table
"""

from __future__ import annotations
import os
import json
import uuid
import sqlite3
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums & Constants
# ============================================================================

class TemplateCategory(str, Enum):
    DRAMA = "drama"              # 短剧
    PICTURE_BOOK = "picture_book"  # 绘本
    PRODUCT_IMAGE = "product_image"  # 商品图
    DIGITAL_HUMAN = "digital_human"  # 数字人
    ADVERTISEMENT = "advertisement"  # 广告
    GENERAL = "general"          # 通用

    @classmethod
    def labels_zh(cls) -> Dict[str, str]:
        return {
            "drama": "短剧",
            "picture_book": "绘本",
            "product_image": "商品图",
            "digital_human": "数字人",
            "advertisement": "广告",
            "general": "通用",
        }

    @classmethod
    def from_str(cls, s: str) -> "TemplateCategory":
        try:
            return cls(s)
        except ValueError:
            return cls.GENERAL


class TemplateStatus(str, Enum):
    DRAFT = "draft"          # 草稿
    PUBLISHED = "published"  # 已发布
    ARCHIVED = "archived"    # 已归档


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TemplateVersion:
    """模板版本记录"""
    version: int = 1
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "config": self.config,
            "created_at": self.created_at,
        }


@dataclass
class Template:
    """市场模板"""
    id: str
    name: str
    description: str = ""
    category: str = "general"          # 分类
    tags: List[str] = field(default_factory=list)
    author: str = "system"
    status: str = "draft"              # draft/published/archived
    config: Dict[str, Any] = field(default_factory=dict)  # 模板配置(JSON)
    thumbnail_url: str = ""
    preview_urls: List[str] = field(default_factory=list)
    
    # 统计
    rating: float = 0.0                # 平均评分 (0-5)
    rating_count: int = 0              # 评分人数
    download_count: int = 0            # 使用/下载次数
    view_count: int = 0                # 查看次数
    
    # 版本
    versions: List[TemplateVersion] = field(default_factory=list)
    current_version: int = 1
    
    # 时间戳
    created_at: str = ""
    updated_at: str = ""
    published_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "category_label": TemplateCategory.labels_zh().get(self.category, self.category),
            "tags": self.tags,
            "author": self.author,
            "status": self.status,
            "config": self.config,
            "thumbnail_url": self.thumbnail_url,
            "preview_urls": self.preview_urls,
            "rating": round(self.rating, 1),
            "rating_count": self.rating_count,
            "download_count": self.download_count,
            "view_count": self.view_count,
            "current_version": self.current_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
        }


@dataclass
class TemplateRatingRecord:
    """评分记录"""
    template_id: str
    user_id: str
    score: float                       # 1-5
    comment: str = ""
    created_at: str = ""


# ============================================================================
# Template Market Engine
# ============================================================================

class TemplateMarketEngine:
    """模板市场核心引擎"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "data", "imdf.db"
            )
        self.db_path = db_path
        self._init_db()
        self._seed_defaults()

    # ─── Database ───────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS template_market (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    category TEXT DEFAULT 'general',
                    tags TEXT DEFAULT '[]',
                    author TEXT DEFAULT 'system',
                    status TEXT DEFAULT 'draft',
                    config TEXT DEFAULT '{}',
                    thumbnail_url TEXT DEFAULT '',
                    preview_urls TEXT DEFAULT '[]',
                    rating REAL DEFAULT 0.0,
                    rating_count INTEGER DEFAULT 0,
                    download_count INTEGER DEFAULT 0,
                    view_count INTEGER DEFAULT 0,
                    versions TEXT DEFAULT '[]',
                    current_version INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT '',
                    published_at TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS template_ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    comment TEXT DEFAULT '',
                    created_at TEXT DEFAULT '',
                    UNIQUE(template_id, user_id)
                )
            """)
            conn.commit()

    def _row_to_template(self, row: sqlite3.Row) -> Template:
        return Template(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            category=row["category"] or "general",
            tags=json.loads(row["tags"] or "[]"),
            author=row["author"] or "system",
            status=row["status"] or "draft",
            config=json.loads(row["config"] or "{}"),
            thumbnail_url=row["thumbnail_url"] or "",
            preview_urls=json.loads(row["preview_urls"] or "[]"),
            rating=row["rating"] or 0.0,
            rating_count=row["rating_count"] or 0,
            download_count=row["download_count"] or 0,
            view_count=row["view_count"] or 0,
            versions=[TemplateVersion(**v) for v in json.loads(row["versions"] or "[]")],
            current_version=row["current_version"] or 1,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            published_at=row["published_at"] or "",
        )

    # ─── Seed Defaults ──────────────────────────────────────────────────

    def _seed_defaults(self):
        """预置示例模板（仅当市场为空时）"""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM template_market").fetchone()[0]
            if count > 0:
                return

        defaults = [
            {
                "name": "短剧 - 都市反转模板",
                "description": "都市题材短剧模板，含开场冲突/反转/结尾钩子结构",
                "category": "drama",
                "tags": ["都市", "反转", "爽剧", "快节奏"],
                "config": {
                    "scenes": 6,
                    "duration_per_scene": 30,
                    "style": "cinematic",
                    "aspect_ratio": "9:16",
                    "character_count": 3,
                    "prompt_template": "都市场景，{character}在{location}，{action}",
                },
            },
            {
                "name": "绘本 - 儿童睡前故事模板",
                "description": "温馨绘本模板，适合3-6岁儿童睡前阅读",
                "category": "picture_book",
                "tags": ["儿童", "温馨", "睡前", "动物"],
                "config": {
                    "pages": 12,
                    "style": "watercolor",
                    "format": "square",
                    "text_per_page_max": 60,
                    "color_palette": "pastel",
                },
            },
            {
                "name": "商品图 - 电商白底棚拍模板",
                "description": "电商标准白底商品图，适合Amazon/Shopify",
                "category": "product_image",
                "tags": ["电商", "白底", "棚拍", "Amazon"],
                "config": {
                    "background": "pure_white",
                    "lighting": "studio_3point",
                    "resolution": "2000x2000",
                    "angle": "front_45",
                    "shadow": "soft_drop",
                },
            },
            {
                "name": "数字人 - 口播讲解模板",
                "description": "AI数字人口播视频模板，适合知识科普/产品讲解",
                "category": "digital_human",
                "tags": ["口播", "知识科普", "AI主播", "讲解"],
                "config": {
                    "avatar_style": "realistic",
                    "voice": "zh-CN-XiaoxiaoNeural",
                    "background": "virtual_studio",
                    "gestures": True,
                    "subtitle": True,
                },
            },
            {
                "name": "广告 - 信息流投放模板",
                "description": "短视频信息流广告模板，适合抖音/快手/TikTok投放",
                "category": "advertisement",
                "tags": ["信息流", "投放", "抖音", "TikTok"],
                "config": {
                    "duration": 15,
                    "aspect_ratio": "9:16",
                    "hook_in_3s": True,
                    "cta": "点击下方链接",
                    "music": "trending",
                },
            },
            {
                "name": "通用 - 图文混排模板",
                "description": "通用图文混排模板，适合社交媒体/公众号文章配图",
                "category": "general",
                "tags": ["图文", "混排", "社交媒体", "公众号"],
                "config": {
                    "layout": "mixed",
                    "image_ratio": 0.6,
                    "text_ratio": 0.4,
                    "font_system": "sans-serif",
                    "max_images": 9,
                },
            },
        ]

        now = datetime.now().isoformat()
        with self._connect() as conn:
            for d in defaults:
                tmpl_id = f"tmpl_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO template_market
                    (id, name, description, category, tags, author, status, config,
                     rating, rating_count, download_count, view_count,
                     versions, current_version, created_at, updated_at, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        tmpl_id,
                        d["name"],
                        d["description"],
                        d["category"],
                        json.dumps(d.get("tags", [])),
                        "system",
                        "published",
                        json.dumps(d.get("config", {})),
                        4.5, 100, 500, 1200,
                        json.dumps([TemplateVersion(version=1, config=d.get("config", {}), created_at=now).to_dict()]),
                        1,
                        now,
                        now,
                        now,
                    ),
                )
            conn.commit()
        logger.info(f"Seeded {len(defaults)} default templates into market")

    # ─── CRUD ───────────────────────────────────────────────────────────

    def create_template(self, name: str, description: str = "",
                        category: str = "general", tags: List[str] = None,
                        author: str = "system", config: Dict[str, Any] = None,
                        thumbnail_url: str = "", preview_urls: List[str] = None,
                        status: str = "draft") -> Template:
        """创建新模板"""
        tmpl_id = f"tmpl_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        tags = tags or []
        config = config or {}
        preview_urls = preview_urls or []

        v1 = TemplateVersion(version=1, config=config, created_at=now)

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO template_market
                (id, name, description, category, tags, author, status, config,
                 thumbnail_url, preview_urls, versions, current_version,
                 created_at, updated_at, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tmpl_id, name, description, category,
                    json.dumps(tags), author, status,
                    json.dumps(config), thumbnail_url,
                    json.dumps(preview_urls),
                    json.dumps([v1.to_dict()]), 1,
                    now, now,
                    now if status == "published" else "",
                ),
            )
            conn.commit()

        return self.get_template(tmpl_id)

    def get_template(self, template_id: str) -> Optional[Template]:
        """获取模板详情（自动+1查看计数）"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM template_market WHERE id = ?", (template_id,)
            ).fetchone()

            if not row:
                return None

            # Bump view count
            conn.execute(
                "UPDATE template_market SET view_count = view_count + 1 WHERE id = ?",
                (template_id,),
            )
            conn.commit()

            return self._row_to_template(row)

    def update_template(self, template_id: str, **kwargs) -> Optional[Template]:
        """更新模板字段"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM template_market WHERE id = ?", (template_id,)
            ).fetchone()
            if not row:
                return None

            allowed = [
                "name", "description", "category", "tags", "config",
                "thumbnail_url", "preview_urls", "status",
            ]
            updates = {}
            for k in allowed:
                if k in kwargs and kwargs[k] is not None:
                    v = kwargs[k]
                    if k in ("tags", "preview_urls"):
                        v = json.dumps(v)
                    elif k == "config":
                        v = json.dumps(v)
                    updates[k] = v

            if not updates:
                return self._row_to_template(row)

            # If config changed, create a new version
            if "config" in updates:
                tmpl = self._row_to_template(row)
                new_ver = tmpl.current_version + 1
                now = datetime.now().isoformat()
                versions = tmpl.versions.copy()
                versions.append(TemplateVersion(
                    version=new_ver,
                    config=json.loads(updates["config"]),
                    created_at=now,
                ).to_dict())
                updates["versions"] = json.dumps(versions)
                updates["current_version"] = new_ver
                conn.execute(
                    "UPDATE template_market SET versions = ?, current_version = ? WHERE id = ?",
                    (updates.pop("versions"), updates.pop("current_version"), template_id),
                )

            # Status change to published
            if updates.get("status") == "published":
                updates["published_at"] = datetime.now().isoformat()

            updates["updated_at"] = datetime.now().isoformat()

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [template_id]
            conn.execute(
                f"UPDATE template_market SET {set_clause} WHERE id = ?", values
            )
            conn.commit()

            return self.get_template(template_id)

    def delete_template(self, template_id: str) -> bool:
        """软删除（归档）"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM template_market WHERE id = ?", (template_id,)
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE template_market SET status = 'archived', updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), template_id),
            )
            conn.commit()
        return True

    def hard_delete_template(self, template_id: str) -> bool:
        """硬删除模板及关联评分"""
        with self._connect() as conn:
            conn.execute("DELETE FROM template_ratings WHERE template_id = ?", (template_id,))
            cur = conn.execute("DELETE FROM template_market WHERE id = ?", (template_id,))
            conn.commit()
        return cur.rowcount > 0

    def publish_template(self, template_id: str) -> Optional[Template]:
        """发布模板（draft→published）"""
        return self.update_template(template_id, status="published")

    def use_template(self, template_id: str) -> Optional[Template]:
        """使用/下载模板（计数+1）"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM template_market WHERE id = ?", (template_id,)
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE template_market SET download_count = download_count + 1 WHERE id = ?",
                (template_id,),
            )
            conn.commit()
            return self._row_to_template(row)

    # ─── Rating ─────────────────────────────────────────────────────────

    def rate_template(self, template_id: str, user_id: str, score: float,
                      comment: str = "") -> Optional[Template]:
        """评分模板（1-5分，同一用户覆盖旧评分）"""
        score = max(1.0, min(5.0, score))
        now = datetime.now().isoformat()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM template_market WHERE id = ?", (template_id,)
            ).fetchone()
            if not row:
                return None

            existing = conn.execute(
                "SELECT id, score FROM template_ratings WHERE template_id = ? AND user_id = ?",
                (template_id, user_id),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE template_ratings SET score = ?, comment = ?, created_at = ? WHERE id = ?",
                    (score, comment, now, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO template_ratings (template_id, user_id, score, comment, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (template_id, user_id, score, comment, now),
                )

            # Recalculate average rating
            avg = conn.execute(
                "SELECT AVG(score) FROM template_ratings WHERE template_id = ?",
                (template_id,),
            ).fetchone()[0]

            rc = conn.execute(
                "SELECT COUNT(*) FROM template_ratings WHERE template_id = ?",
                (template_id,),
            ).fetchone()[0]

            conn.execute(
                "UPDATE template_market SET rating = ?, rating_count = ? WHERE id = ?",
                (round(avg, 1) if avg else 0.0, rc, template_id),
            )
            conn.commit()

            return self._row_to_template(
                conn.execute("SELECT * FROM template_market WHERE id = ?", (template_id,)).fetchone()
            )

    def get_template_ratings(self, template_id: str) -> List[Dict]:
        """获取模板所有评分"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM template_ratings WHERE template_id = ? ORDER BY created_at DESC",
                (template_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Listing & Search ───────────────────────────────────────────────

    def list_templates(
        self,
        category: Optional[str] = None,
        status: str = "published",
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sort_by: str = "download_count",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """列表查询（分页/搜索/过滤/排序）"""
        allowed_sort = {"download_count", "rating", "view_count", "created_at", "updated_at", "name"}
        if sort_by not in allowed_sort:
            sort_by = "download_count"
        sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"

        conditions = []
        params = []

        if category:
            conditions.append("category = ?")
            params.append(category)

        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1=1"

        with self._connect() as conn:
            # Get total
            total = conn.execute(
                f"SELECT COUNT(*) FROM template_market WHERE {where}", params
            ).fetchone()[0]

            offset = (page - 1) * page_size
            rows = conn.execute(
                f"SELECT * FROM template_market WHERE {where} "
                f"ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?",
                params + [page_size, offset],
            ).fetchall()

        templates = [self._row_to_template(r) for r in rows]

        # 客户端侧搜索/标签过滤（SQLite不支持复杂JSON搜索）
        if search:
            q = search.lower()
            templates = [
                t for t in templates
                if q in t.name.lower()
                or q in t.description.lower()
                or any(q in tag.lower() for tag in t.tags)
            ]
        if tags:
            tag_set = {t.lower() for t in tags}
            templates = [t for t in templates if tag_set & {tg.lower() for tg in t.tags}]

        return {
            "items": [t.to_dict() for t in templates],
            "total": len(templates),
            "total_all": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def search_templates(
        self,
        query: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Template]:
        """全文搜索模板（名称/描述/标签）"""
        result = self.list_templates(
            category=category,
            search=query,
            tags=tags,
            sort_by="rating",
            page=1,
            page_size=limit,
        )
        templates = []
        with self._connect() as conn:
            for item in result["items"]:
                row = conn.execute(
                    "SELECT * FROM template_market WHERE id = ?", (item["id"],)
                ).fetchone()
                if row:
                    templates.append(self._row_to_template(row))
        return templates

    def get_categories(self) -> List[Dict]:
        """获取所有分类及统计"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT category, COUNT(*) as cnt
                   FROM template_market WHERE status = 'published'
                   GROUP BY category ORDER BY cnt DESC"""
            ).fetchall()
        labels = TemplateCategory.labels_zh()
        return [
            {
                "category": r["category"],
                "label": labels.get(r["category"], r["category"]),
                "count": r["cnt"],
            }
            for r in rows
        ]

    def get_popular_templates(self, limit: int = 10) -> List[Dict]:
        """获取热门模板（按下载量）"""
        result = self.list_templates(
            status="published",
            sort_by="download_count",
            page=1,
            page_size=limit,
        )
        return result["items"]

    def get_top_rated_templates(self, limit: int = 10) -> List[Dict]:
        """获取高分模板（按评分）"""
        result = self.list_templates(
            status="published",
            sort_by="rating",
            page=1,
            page_size=limit,
        )
        return result["items"]

    def get_stats(self) -> Dict:
        """获取模板市场统计数据"""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM template_market WHERE status != 'archived'"
            ).fetchone()[0]
            published = conn.execute(
                "SELECT COUNT(*) FROM template_market WHERE status = 'published'"
            ).fetchone()[0]
            total_downloads = conn.execute(
                "SELECT SUM(download_count) FROM template_market"
            ).fetchone()[0] or 0
            total_views = conn.execute(
                "SELECT SUM(view_count) FROM template_market"
            ).fetchone()[0] or 0
            total_ratings = conn.execute(
                "SELECT COUNT(*) FROM template_ratings"
            ).fetchone()[0]

        return {
            "total_templates": total,
            "published_templates": published,
            "total_downloads": total_downloads,
            "total_views": total_views,
            "total_ratings": total_ratings,
            "categories": self.get_categories(),
        }

    def get_versions(self, template_id: str) -> List[Dict]:
        """获取模板所有版本"""
        tmpl = self.get_template(template_id)
        if not tmpl:
            return []
        return [v.to_dict() for v in tmpl.versions]


# ============================================================================
# Singleton
# ============================================================================

_engine: Optional[TemplateMarketEngine] = None


def get_template_market_engine() -> TemplateMarketEngine:
    """获取或创建全局TemplateMarketEngine单例"""
    global _engine
    if _engine is None:
        _engine = TemplateMarketEngine()
    return _engine
