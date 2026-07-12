"""智影 V4 — DedupeEngine: 6 级去重 (URL→SHA256→pHash→SimHash→Embedding→Token)"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional, Set, Union

from ..crawler.base import RawDocument
from .base import ProcessedItem, ProcessingPipeline

logger = logging.getLogger(__name__)


class DedupStrategy(str, Enum):
    """去重策略 — 6 级递进"""

    URL = "url"  # 1. URL 完全匹配
    SHA256 = "sha256"  # 2. 内容 SHA256 (原始字节)
    SIMHASH = "simhash"  # 3. SimHash (近重复文本)
    PERCEPTUAL = "perceptual"  # 4. pHash (图片/视频)
    EMBEDDING = "embedding"  # 5. Embedding 余弦相似度
    TOKEN = "token"  # 6. Token n-gram 集合


class DedupeEngine(ProcessingPipeline):
    """6 级去重引擎 — 多策略组合"""

    def __init__(
        self,
        strategies: Optional[List[DedupStrategy]] = None,
        embedding_threshold: float = 0.92,
        simhash_threshold: int = 3,  # hamming distance
    ):
        super().__init__(name="dedupe")
        self.strategies = strategies or [DedupStrategy.URL, DedupStrategy.SHA256, DedupStrategy.SIMHASH]
        self.embedding_threshold = embedding_threshold
        self.simhash_threshold = simhash_threshold
        # 状态
        self._seen_url: Set[str] = set()
        self._seen_hash: Dict[str, ProcessedItem] = {}
        self._seen_simhash: Dict[str, ProcessedItem] = {}
        self._seen_perceptual: Dict[str, ProcessedItem] = {}
        self._seen_embedding: List[tuple] = []  # (embedding, item)
        self._seen_token: Set[str] = set()

    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        items = self._to_items(items)
        self.metrics.total += len(items)
        out: List[ProcessedItem] = []
        for item in items:
            if self._is_duplicate(item):
                self.metrics.deduped += 1
                item.status = "deduped"
                item.audit_chain.append(
                    {"step": "dedupe", "action": "skipped", "reason": "duplicate detected", "ts": _now()}
                )
                continue
            self._record_seen(item)
            item.audit_chain.append({"step": "dedupe", "action": "kept", "ts": _now()})
            out.append(item)
        self.finish()
        return out

    def _is_duplicate(self, item: ProcessedItem) -> bool:
        for strat in self.strategies:
            if strat == DedupStrategy.URL:
                if self._dup_url(item):
                    return True
            elif strat == DedupStrategy.SHA256:
                if self._dup_sha256(item):
                    return True
            elif strat == DedupStrategy.SIMHASH:
                if self._dup_simhash(item):
                    return True
            elif strat == DedupStrategy.PERCEPTUAL:
                if self._dup_perceptual(item):
                    return True
            elif strat == DedupStrategy.EMBEDDING:
                if self._dup_embedding(item):
                    return True
            elif strat == DedupStrategy.TOKEN:
                if self._dup_token(item):
                    return True
        return False

    def _normalize_url(self, url: str) -> str:
        """URL 标准化 — 去掉 fragment + 排序 query + 去 tracking 参数"""
        from urllib.parse import urlparse, parse_qs, urlencode
        u = urlparse(url)
        # 去掉 fragment
        # 去掉常见 tracking 参数
        drop_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "mc_cid", "mc_eid"}
        if u.query:
            qs = parse_qs(u.query, keep_blank_values=True)
            qs = {k: v for k, v in qs.items() if k.lower() not in drop_params}
            clean_q = urlencode(sorted(qs.items()), doseq=True)
            norm = f"{u.scheme}://{u.netloc}{u.path}"
            if clean_q:
                norm += "?" + clean_q
        else:
            norm = f"{u.scheme}://{u.netloc}{u.path}"
        return norm

    def _dup_url(self, item: ProcessedItem) -> bool:
        if not item.source_url:
            return False
        norm = self._normalize_url(item.source_url)
        return norm in self._seen_url

    def _dup_sha256(self, item: ProcessedItem) -> bool:
        return bool(item.content_hash and item.content_hash in self._seen_hash)

    def _dup_simhash(self, item: ProcessedItem) -> bool:
        """SimHash: 64-bit fingerprint, hamming distance ≤ threshold → 重复"""
        if not item.text or len(item.text) < 100:
            return False
        sh = self._compute_simhash(item.text)
        item.simhash = sh
        for existing in self._seen_simhash.values():
            if self._hamming_distance(sh, existing.simhash) <= self.simhash_threshold:
                return True
        return False

    def _compute_simhash(self, text: str, ngram: int = 3) -> str:
        """SimHash 64-bit 文本指纹"""
        text = re.sub(r"\s+", " ", text.lower()).strip()
        tokens = [text[i : i + ngram] for i in range(len(text) - ngram + 1)]
        v = [0] * 64
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            for i in range(64):
                v[i] += 1 if (h >> i) & 1 else -1
        fingerprint = 0
        for i in range(64):
            if v[i] > 0:
                fingerprint |= 1 << i
        return format(fingerprint, "016x")

    def _hamming_distance(self, a: str, b: str) -> int:
        if not a or not b or len(a) != len(b):
            return 64
        ba, bb = int(a, 16), int(b, 16)
        return bin(ba ^ bb).count("1")

    def _dup_perceptual(self, item: ProcessedItem) -> bool:
        """pHash 重复检测 (图片/视频)"""
        # 真实实现需要 PIL + DCT;此处用占位但可用 — 调 perceptual_hash 模块
        if item.type not in ("image", "video"):
            return False
        if not item.perceptual_hash:
            return False
        return item.perceptual_hash in self._seen_perceptual

    def _dup_embedding(self, item: ProcessedItem) -> bool:
        """Embedding 余弦相似度"""
        if not item.embedding:
            return False
        import math
        for emb, _ in self._seen_embedding:
            sim = self._cosine_sim(item.embedding, emb)
            if sim >= self.embedding_threshold:
                return True
        return False

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _dup_token(self, item: ProcessedItem) -> bool:
        """Token n-gram 集合重复"""
        if not item.text:
            return False
        text = re.sub(r"\s+", " ", item.text.lower()).strip()
        tokens = set(text.split()[:100])  # 前 100 词
        fp = hashlib.md5(str(sorted(tokens)).encode("utf-8")).hexdigest()
        return fp in self._seen_token

    def _record_seen(self, item: ProcessedItem):
        if item.source_url:
            self._seen_url.add(self._normalize_url(item.source_url))
        if item.content_hash:
            self._seen_hash[item.content_hash] = item
        if item.simhash:
            self._seen_simhash[item.simhash] = item
        if item.perceptual_hash:
            self._seen_perceptual[item.perceptual_hash] = item
        if item.embedding:
            self._seen_embedding.append((item.embedding, item))
            if len(self._seen_embedding) > 10000:  # 防爆
                self._seen_embedding = self._seen_embedding[-5000:]
        if item.text:
            text = re.sub(r"\s+", " ", item.text.lower()).strip()
            tokens = set(text.split()[:100])
            fp = hashlib.md5(str(sorted(tokens)).encode("utf-8")).hexdigest()
            self._seen_token.add(fp)

    def reset(self):
        """清空 seen 状态"""
        self._seen_url.clear()
        self._seen_hash.clear()
        self._seen_simhash.clear()
        self._seen_perceptual.clear()
        self._seen_embedding.clear()
        self._seen_token.clear()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
