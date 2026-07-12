"""智影 V4 — ClassifyEngine: 8 业务模态分类 (image/edit/video/drama/picture_book/audio/text/3d)"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..crawler.base import RawDocument
from .base import ProcessedItem, ProcessingPipeline

logger = logging.getLogger(__name__)


class ClassifyTaxonomy(str, Enum):
    """8 业务模态 — 跟平台 V3 业务对齐"""

    IMAGE = "image"  # 原图
    IMAGE_EDIT = "image_edit"  # 编辑
    VIDEO = "video"
    SHORT_DRAMA = "short_drama"  # 短剧
    PICTURE_BOOK = "picture_book"  # 绘本
    AUDIO = "audio"
    TEXT = "text"
    THREE_D = "3d"  # 3D / NeRF / Gaussian Splatting


# 各模态的子分类 (taxonomy 路径)
SUB_TAXONOMIES: Dict[ClassifyTaxonomy, Dict[str, List[str]]] = {
    ClassifyTaxonomy.IMAGE: {
        "Nature": ["landscape", "wildlife", "plant", "flower", "mountain", "ocean", "sky"],
        "Urban": ["building", "street", "city", "interior", "architecture", "vehicle"],
        "Portrait": ["person", "face", "selfie", "group", "fashion", "beauty"],
        "Object": ["product", "food", "art", "logo", "icon", "craft"],
        "Abstract": ["pattern", "texture", "wallpaper", "geometric", "artistic"],
        "Document": ["screenshot", "text", "poster", "infographic", "diagram"],
    },
    ClassifyTaxonomy.IMAGE_EDIT: {
        "Style": ["anime", "cartoon", "oil_painting", "watercolor", "sketch", "pixel_art"],
        "Operation": ["inpainting", "outpainting", "colorize", "deblur", "denoise", "upscale", "restoration"],
        "Effect": ["filter", "hdr", "vintage", "cinematic", "neon"],
    },
    ClassifyTaxonomy.VIDEO: {
        "Type": ["live_action", "animation", "3d", "motion_graphics", "screen_recording", "vlog", "tutorial"],
        "Genre": ["comedy", "drama", "action", "horror", "documentary", "music_video", "advertisement"],
        "Duration": ["short_<60s", "medium_1-10min", "long_>10min"],
    },
    ClassifyTaxonomy.SHORT_DRAMA: {
        "Genre": ["romance", "thriller", "fantasy", "historical", "urban", "mystery", "comedy"],
        "Style": ["live_action", "animation", "hybrid"],
        "Episode": ["single", "series", "limited"],
    },
    ClassifyTaxonomy.PICTURE_BOOK: {
        "Audience": ["children_0-3", "children_3-6", "children_6-12", "teens", "adults"],
        "Style": ["cartoon", "watercolor", "digital", "realistic", "paper_craft"],
        "Topic": ["education", "story", "science", "moral", "bedtime", "adventure"],
    },
    ClassifyTaxonomy.AUDIO: {
        "Type": ["music", "speech", "sound_effect", "ambient", "podcast", "asmr"],
        "Genre": ["pop", "rock", "jazz", "classical", "electronic", "folk", "rap"],
        "Language": ["zh", "en", "ja", "ko", "es", "multi"],
    },
    ClassifyTaxonomy.TEXT: {
        "Type": ["article", "story", "poem", "code", "dialogue", "documentation", "review", "qa", "summary"],
        "Domain": ["tech", "science", "business", "politics", "health", "sports", "entertainment", "education"],
        "Format": ["markdown", "html", "plain", "json", "xml", "code"],
    },
    ClassifyTaxonomy.THREE_D: {
        "Type": ["mesh", "point_cloud", "nerf", "gaussian_splatting", "voxel", "sdf"],
        "Domain": ["object", "scene", "character", "building", "vehicle", "nature"],
        "Source": ["photogrammetry", "lidar", "modeling", "generative", "scan"],
    },
}


class ClassifyEngine(ProcessingPipeline):
    """8 业务模态分类引擎"""

    def __init__(self, primary_only: bool = False):
        super().__init__(name="classify")
        self.primary_only = primary_only

    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        items = self._to_items(items)
        self.metrics.total += len(items)
        out: List[ProcessedItem] = []
        for item in items:
            try:
                self._classify_one(item)
                self.metrics.classified += 1
                item.audit_chain.append(
                    {
                        "step": "classify",
                        "action": "classified",
                        "modality": item.modality,
                        "domain": item.domain,
                        "path": item.taxonomy_path,
                        "ts": _now(),
                    }
                )
                out.append(item)
            except Exception as e:
                self.metrics.rejected += 1
                item.rejection_reason = f"classify_error:{e}"
                logger.warning(f"classify failed for {item.source_url}: {e}")
                out.append(item)
        self.finish()
        return out

    def _classify_one(self, item: ProcessedItem):
        """分类逻辑:
        1. 先根据 type + URL/元数据 → 主模态
        2. 再根据文本/标签 → 子分类
        """
        primary = self._detect_primary_modality(item)
        item.modality = primary.value
        sub = self._detect_subcategory(item, primary)
        item.domain = sub.get("domain", "")
        path = [primary.value]
        for k, v in sub.items():
            if k != "domain":
                path.append(f"{k}:{v}")
        item.taxonomy_path = path[:6]
        item.status = "classified"
        item.updated_at = _now()

    def _detect_primary_modality(self, item: ProcessedItem) -> ClassifyTaxonomy:
        """主模态检测 — 综合 type + URL + 标签 + 文本特征"""
        # 1. type 优先
        if item.type in ("image",):
            if self._is_editing_context(item):
                return ClassifyTaxonomy.IMAGE_EDIT
            return ClassifyTaxonomy.IMAGE
        if item.type in ("video",):
            if self._is_drama_context(item):
                return ClassifyTaxonomy.SHORT_DRAMA
            return ClassifyTaxonomy.VIDEO
        if item.type in ("audio",):
            return ClassifyTaxonomy.AUDIO
        if item.type in ("3d", "model3d", "mesh"):
            return ClassifyTaxonomy.THREE_D
        if item.type in ("picture_book",):
            return ClassifyTaxonomy.PICTURE_BOOK
        # 2. URL 启发
        from urllib.parse import urlparse
        if item.source_url:
            u = urlparse(item.source_url).netloc.lower()
            if "youtube.com" in u or "youtu.be" in u or "vimeo.com" in u:
                if self._is_drama_context(item):
                    return ClassifyTaxonomy.SHORT_DRAMA
                return ClassifyTaxonomy.VIDEO
            if "sketchfab.com" in u or "thingiverse.com" in u:
                return ClassifyTaxonomy.THREE_D
        # 3. 文本特征
        text = ((item.text or "") + " " + (item.title or "")).lower()
        if self._is_editing_context(item):
            return ClassifyTaxonomy.IMAGE_EDIT
        if self._is_drama_context(item):
            return ClassifyTaxonomy.SHORT_DRAMA
        if self._is_picture_book_context(item):
            return ClassifyTaxonomy.PICTURE_BOOK
        if "code" in item.labels or any(re.search(r"```", item.text or "")):
            return ClassifyTaxonomy.TEXT
        # 默认
        if item.images:
            return ClassifyTaxonomy.IMAGE
        return ClassifyTaxonomy.TEXT

    def _is_editing_context(self, item: ProcessedItem) -> bool:
        text = ((item.text or "") + " " + (item.title or "")).lower()
        keywords = ["inpaint", "outpaint", "colorize", "style transfer", "img2img", "edit image", "remove background", "upscale", "denoise", "deblur", "滤镜", "修复", "上色", "扩图"]
        return any(kw in text for kw in keywords)

    def _is_drama_context(self, item: ProcessedItem) -> bool:
        text = ((item.text or "") + " " + (item.title or "")).lower()
        keywords = ["short drama", "miniseries", "episode", "web drama", "短剧", "集", "剧情", "主角", "男主", "女主", "短剧"]
        return any(kw in text for kw in keywords)

    def _is_picture_book_context(self, item: ProcessedItem) -> bool:
        text = ((item.text or "") + " " + (item.title or "")).lower()
        keywords = ["picture book", "illustration", "children book", "绘本", "插画", "儿童故事"]
        return any(kw in text for kw in keywords)

    def _detect_subcategory(self, item: ProcessedItem, primary: ClassifyTaxonomy) -> Dict[str, str]:
        """子分类 — 在 primary 模态下匹配子 taxonomy"""
        text = ((item.text or "") + " " + (item.title or "")).lower()
        sub_tax = SUB_TAXONOMIES.get(primary, {})
        result: Dict[str, str] = {}
        # 启发式
        if primary == ClassifyTaxonomy.IMAGE:
            if any(kw in text for kw in ["landscape", "mountain", "ocean", "sky", "nature", "风景", "山水"]):
                result["domain"] = "Nature"
            elif any(kw in text for kw in ["portrait", "person", "face", "selfie", "人像", "自拍"]):
                result["domain"] = "Portrait"
            elif any(kw in text for kw in ["building", "city", "street", "urban", "城市", "建筑"]):
                result["domain"] = "Urban"
            elif any(kw in text for kw in ["product", "food", "商品", "美食"]):
                result["domain"] = "Object"
            else:
                result["domain"] = "Other"
        elif primary == ClassifyTaxonomy.VIDEO:
            if any(kw in text for kw in ["vlog", "blog", "日常"]):
                result["domain"] = "vlog"
                result["type"] = "vlog"
            elif any(kw in text for kw in ["tutorial", "how to", "教程", "指南"]):
                result["domain"] = "tutorial"
                result["type"] = "tutorial"
            elif any(kw in text for kw in ["music", "song", "mv", "音乐"]):
                result["domain"] = "music_video"
                result["type"] = "music_video"
            else:
                result["domain"] = "other"
                result["type"] = "other"
        elif primary == ClassifyTaxonomy.TEXT:
            if "code" in item.labels or "```" in (item.text or ""):
                result["type"] = "code"
            elif any(kw in text for kw in ["story", "tale", "故事", "小说"]):
                result["type"] = "story"
            elif any(kw in text for kw in ["article", "blog", "文章"]):
                result["type"] = "article"
            else:
                result["type"] = "other"
        return result


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
