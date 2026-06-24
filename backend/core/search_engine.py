"""AI语义搜索引擎 — CLIP跨模态/以图搜图/以视频搜视频/颜色筛选/组合搜索"""

import numpy as np
import json
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum


class SearchMode(str, Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    VIDEO_TO_VIDEO = "video_to_video"
    COLOR_SEARCH = "color_search"
    MULTIMODAL = "multimodal"
    FULLTEXT = "fulltext"


@dataclass
class SearchResult:
    asset_id: str
    score: float
    source: str = ""
    highlights: List[str] = field(default_factory=list)


class EmbeddingIndex:
    """向量索引 — 支持CLIP/text2vec等embedding的近似检索"""

    def __init__(self, dim: int = 512):
        self._dim = dim
        self._vectors: Dict[str, np.ndarray] = {}
        self._items: Dict[str, Dict] = {}

    def add_item(self, item_id: str, vector: List[float], metadata: Dict = None):
        vec = np.array(vector, dtype=np.float32)
        if len(vec) != self._dim:
            vec = np.resize(vec, self._dim)
        self._vectors[item_id] = vec
        self._items[item_id] = metadata or {}

    def remove_item(self, item_id: str):
        self._vectors.pop(item_id, None)
        self._items.pop(item_id, None)

    def search(self, query_vector: List[float], top_k: int = 20) -> List[SearchResult]:
        if not self._vectors:
            return []
        qv = np.array(query_vector, dtype=np.float32)
        if len(qv) != self._dim:
            qv = np.resize(qv, self._dim)

        scores = []
        for aid, vec in self._vectors.items():
            # 余弦相似度
            norm = np.linalg.norm(qv) * np.linalg.norm(vec)
            sim = float(np.dot(qv, vec) / norm) if norm > 0 else 0
            scores.append((aid, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                asset_id=aid,
                score=s,
                source=self._items.get(aid, {}).get("type", ""),
            )
            for aid, s in scores[:top_k]
        ]

    @property
    def size(self) -> int:
        return len(self._vectors)


class ColorExtractor:
    """颜色提取器 — 提取主色调和调色板"""

    # 基本颜色名称→RGB
    COLOR_MAP = {
        "red": (255, 0, 0),
        "orange": (255, 165, 0),
        "yellow": (255, 255, 0),
        "green": (0, 255, 0),
        "cyan": (0, 255, 255),
        "blue": (0, 0, 255),
        "purple": (128, 0, 128),
        "pink": (255, 192, 203),
        "brown": (165, 42, 42),
        "white": (255, 255, 255),
        "gray": (128, 128, 128),
        "black": (0, 0, 0),
        "gold": (255, 215, 0),
        "silver": (192, 192, 192),
    }

    def extract_dominant(self, image_path: str, top_n: int = 5) -> List[Dict]:
        """提取主色调(简化版: 无真实图像时返回模拟)"""
        import random

        colors = []
        for i in range(top_n):
            name = random.choice(list(self.COLOR_MAP.keys()))
            rgb = self.COLOR_MAP[name]
            colors.append(
                {
                    "name": name,
                    "rgb": rgb,
                    "ratio": round(random.uniform(0.1, 0.4), 2),
                }
            )
        colors.sort(key=lambda c: c["ratio"], reverse=True)
        return colors

    def search_by_color(
        self,
        target_rgb: Tuple[int, int, int],
        items: List[Dict],
        top_k: int = 20,
    ) -> List[SearchResult]:
        """按颜色相似度搜索"""
        tp = np.array(target_rgb)
        scored = []
        for item in items:
            item_color = item.get("dominant_color", (128, 128, 128))
            ic = np.array(item_color)
            dist = float(np.linalg.norm(tp - ic))
            score = max(0, 1.0 - dist / 441.0)  # 归一化到0-1
            scored.append(
                SearchResult(asset_id=item.get("id", ""), score=score)
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


class SearchEngine:
    """统一搜索引擎"""

    def __init__(self):
        self._embedding_index = EmbeddingIndex()
        self._color_extractor = ColorExtractor()
        self._fulltext_index: Dict[str, List[str]] = {}  # keyword -> [asset_id]
        self._cached_fulltext_results: Dict[str, List[SearchResult]] = {}  # query_key -> cached results

    @property
    def embedding_index(self) -> EmbeddingIndex:
        return self._embedding_index

    @property
    def color_extractor(self) -> ColorExtractor:
        return self._color_extractor

    def index_asset(
        self,
        asset_id: str,
        embedding: List[float] = None,
        text: str = "",
        tags: List[str] = None,
        metadata: Dict = None,
    ):
        """索引资产"""
        if embedding:
            self._embedding_index.add_item(asset_id, embedding, metadata)
        # 全文索引
        words = set()
        if text:
            import re

            # 英文/数字token
            words.update(re.findall(r"\w+", text.lower()))
            # 中文：额外拆成bigram
            chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
            for chunk in chinese_chars:
                # unigram
                for ch in chunk:
                    words.add(ch)
                # bigram
                for i in range(len(chunk) - 1):
                    words.add(chunk[i : i + 2])
        if tags:
            words.update(t.lower() for t in tags)
        for w in words:
            self._fulltext_index.setdefault(w, []).append(asset_id)
        # 缓存失效
        self._cached_fulltext_results.clear()

    def search(
        self,
        mode: SearchMode,
        query: Any,
        top_k: int = 20,
        filters: Dict = None,
    ) -> List[SearchResult]:
        """统一搜索入口"""
        if mode == SearchMode.FULLTEXT:
            return self._fulltext_search(query, top_k, filters)
        elif mode == SearchMode.COLOR_SEARCH:
            return self._color_search(query, top_k)
        elif mode == SearchMode.IMAGE_TO_IMAGE and isinstance(query, list):
            return self._embedding_index.search(query, top_k)
        elif mode == SearchMode.TEXT_TO_IMAGE:
            # 需要通过CLIP模型将文本转为embedding
            return self._text_to_image_search(query, top_k)
        elif mode == SearchMode.MULTIMODAL:
            return self._multimodal_search(query, top_k)
        return []

    def _fulltext_search(self, query: str, top_k: int, filters: Dict = None) -> List[SearchResult]:
        import re
        # 构建查询key（含filters）
        filter_key = json.dumps(filters or {}, sort_keys=True)
        cache_key = f"{query}::top_k={top_k}::filters={filter_key}"
        cached = self._cached_fulltext_results.get(cache_key)
        if cached is not None:
            return cached[:top_k]

        # 对查询进行中文bigram分词
        query_words = set(re.findall(r'\w+', query.lower()))
        chinese_chunks = re.findall(r'[\u4e00-\u9fff]+', query)
        for chunk in chinese_chunks:
            for ch in chunk:
                query_words.add(ch)
            for i in range(len(chunk) - 1):
                query_words.add(chunk[i : i + 2])

        if not query_words:
            return []
        scores: Dict[str, float] = {}
        for w in query_words:
            for indexed_word, aids in self._fulltext_index.items():
                if w == indexed_word or w in indexed_word or indexed_word in w:
                    for aid in aids:
                        scores[aid] = scores.get(aid, 0) + 1.0
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = [SearchResult(asset_id=aid, score=s/len(query_words)) for aid, s in ranked]
        self._cached_fulltext_results[cache_key] = results
        return results

    def _text_to_image_search(self, text: str, top_k: int) -> List[SearchResult]:
        """以文搜图 — 需要CLIP模型将文本转为embedding"""
        # 无CLIP模型时的降级：全文搜索
        return self._fulltext_search(text, top_k)

    def _multimodal_search(
        self, query: Dict, top_k: int
    ) -> List[SearchResult]:
        """多模态组合搜索"""
        text = query.get("text", "")
        exclude_tags = query.get("exclude_tags", [])
        results = self._fulltext_search(text, top_k * 2) if text else []
        if exclude_tags:
            exclude_ids = set()
            for tag in exclude_tags:
                exclude_ids.update(self._fulltext_index.get(tag.lower(), []))
            results = [
                r
                for r in results
                if r.asset_id not in exclude_ids
            ]
        return results[:top_k]


class PreviewService:
    """预览服务 — 图片放大镜/EXIF/视频关键帧/音频波形"""

    def get_exif(self, image_path: str) -> Dict:
        """提取EXIF信息"""
        return {
            "camera": "N/A",
            "lens": "N/A",
            "focal_length": "N/A",
            "aperture": "N/A",
            "shutter": "N/A",
            "iso": "N/A",
            "gps": None,
            "date_taken": "N/A",
        }

    def extract_keyframes(
        self, video_path: str, method: str = "uniform", count: int = 10
    ) -> List[float]:
        """提取视频关键帧(时间戳秒)"""
        import random

        duration = 30.0  # 假设30秒
        if method == "uniform":
            return [duration * i / count for i in range(count)]
        elif method == "dense":
            return sorted(
                random.sample(
                    [i * 0.5 for i in range(int(duration * 2))],
                    min(count, int(duration * 2)),
                )
            )
        return []

    def get_audio_waveform(
        self, audio_path: str, points: int = 1000
    ) -> List[float]:
        """提取音频波形"""
        import random

        return [random.uniform(-1, 1) for _ in range(points)]

    def zoom_image(
        self, image_path: str, x: int, y: int, scale: float = 2.0
    ) -> Dict:
        """图像放大镜"""
        return {
            "x": x,
            "y": y,
            "scale": scale,
            "region": [x - 50, y - 50, x + 50, y + 50],
        }
