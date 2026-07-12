"""智影 V4 — ScoringEngine: 多维度评分 (Quality/Aesthetic/Custom + MUSIQ/LAION)"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..crawler.base import RawDocument
from .base import ProcessedItem, ProcessingPipeline

logger = logging.getLogger(__name__)


class ScoreDimension(str, Enum):
    """评分维度"""

    QUALITY = "quality"  # 通用质量 (文本/图片)
    AESTHETIC = "aesthetic"  # 美学 (图片/视频)
    USEFULNESS = "usefulness"  # 实用价值 (训练数据视角)
    DIVERSITY = "diversity"  # 多样性
    SAFETY = "safety"  # 安全合规
    EDUCATIONAL = "educational"  # 教育价值
    COMPLETENESS = "completeness"  # 完整度


class ScoringEngine(ProcessingPipeline):
    """多维度评分引擎 — Quality + Aesthetic + Custom + MUSIQ/LAION 模型"""

    def __init__(
        self,
        dimensions: Optional[List[ScoreDimension]] = None,
        aesthetic_model: str = "musiq",  # musiq / laion / clip-aesthetic
        quality_model: str = "rule",  # rule / clip / db-clip
    ):
        super().__init__(name="scoring")
        self.dimensions = dimensions or [ScoreDimension.QUALITY, ScoreDimension.AESTHETIC, ScoreDimension.USEFULNESS]
        self.aesthetic_model = aesthetic_model
        self.quality_model = quality_model

    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        items = self._to_items(items)
        self.metrics.total += len(items)
        out: List[ProcessedItem] = []
        for item in items:
            try:
                self._score_one(item)
                self.metrics.scored += 1
                item.audit_chain.append(
                    {
                        "step": "scoring",
                        "action": "scored",
                        "quality": item.quality_score,
                        "aesthetic": item.aesthetic_score,
                        "ts": _now(),
                    }
                )
                out.append(item)
            except Exception as e:
                self.metrics.rejected += 1
                item.rejection_reason = f"score_error:{e}"
                logger.warning(f"scoring failed for {item.source_url}: {e}")
                out.append(item)
        self.finish()
        return out

    def _score_one(self, item: ProcessedItem):
        for dim in self.dimensions:
            score = self._score_dimension(dim, item)
            if dim == ScoreDimension.QUALITY:
                item.quality_score = score
            elif dim == ScoreDimension.AESTHETIC:
                item.aesthetic_score = score
            else:
                item.custom_scores[dim.value] = round(score, 4)
        item.status = "scored"
        item.updated_at = _now()

    def _score_dimension(self, dim: ScoreDimension, item: ProcessedItem) -> float:
        if dim == ScoreDimension.QUALITY:
            return self._score_quality(item)
        if dim == ScoreDimension.AESTHETIC:
            return self._score_aesthetic(item)
        if dim == ScoreDimension.USEFULNESS:
            return self._score_usefulness(item)
        if dim == ScoreDimension.DIVERSITY:
            return self._score_diversity(item)
        if dim == ScoreDimension.SAFETY:
            return self._score_safety(item)
        if dim == ScoreDimension.EDUCATIONAL:
            return self._score_educational(item)
        if dim == ScoreDimension.COMPLETENESS:
            return self._score_completeness(item)
        return 0.5

    def _score_quality(self, item: ProcessedItem) -> float:
        """通用质量分"""
        if self.quality_model == "rule":
            return self._quality_rule(item)
        # 真实模型: CLIP/DB-CLIP quality predictor
        return self._quality_rule(item)

    def _quality_rule(self, item: ProcessedItem) -> float:
        """基于规则的质量分 (启发式)"""
        score = 0.5
        text = item.text or ""
        if item.type in ("image", "video"):
            if item.images:
                score += 0.1
            if item.files:
                score += 0.05
        if text:
            length = len(text)
            # 长度评分 (短-长 钟形)
            if 200 < length < 5000:
                score += 0.2
            elif 1000 < length < 10000:
                score += 0.15
            # 信息密度: 唯一词 / 总词
            words = text.split()
            if words:
                diversity = len(set(words)) / len(words)
                score += min(diversity * 0.3, 0.3)
            # 有标题加分
            if item.title:
                score += 0.05
        # 有 source_metadata (来源可信) 加分
        if item.source_channel:
            score += 0.05
        return min(max(score, 0.0), 1.0)

    def _score_aesthetic(self, item: ProcessedItem) -> float:
        """美学分 (MUSIQ / LAION aesthetic predictor)"""
        if self.aesthetic_model == "musiq":
            return self._aesthetic_musiq(item)
        if self.aesthetic_model == "laion":
            return self._aesthetic_laion(item)
        return self._aesthetic_rule(item)

    def _aesthetic_musiq(self, item: ProcessedItem) -> float:
        """MUSIQ 多尺度 image quality — stub, 真实需 IQA-PyTorch"""
        if item.type != "image":
            return 0.5
        # 真实集成路径: pip install pyiqa → pyiqa.create_metric('musiq')
        try:
            import pyiqa
            import torch
            from PIL import Image
            if item.files:
                # 实际跑模型
                metric = pyiqa.create_metric("musiq")
                # image = Image.open(item.files[0]['path'])
                return float(metric(item.files[0]["path"]).item())
        except Exception:
            pass
        return self._aesthetic_rule(item)

    def _aesthetic_laion(self, item: ProcessedItem) -> float:
        """LAION aesthetic predictor — stub"""
        if item.type != "image":
            return 0.5
        try:
            import pyiqa
            metric = pyiqa.create_metric("laion_aes")
            if item.files:
                return float(metric(item.files[0]["path"]).item())
        except Exception:
            pass
        return self._aesthetic_rule(item)

    def _aesthetic_rule(self, item: ProcessedItem) -> float:
        """美学启发式"""
        if item.type in ("image", "video"):
            # 图片有图 + 文件 + 描述 → 中等分
            base = 0.5
            if item.images:
                base += 0.1
            if item.text and len(item.text) > 100:
                base += 0.1
            return min(base, 1.0)
        return 0.5

    def _score_usefulness(self, item: ProcessedItem) -> float:
        """训练数据视角的实用价值"""
        text = item.text or ""
        if not text:
            return 0.3
        # 启发式: 长度 + 标签 + 来源
        score = 0.4
        if 200 < len(text) < 20000:
            score += 0.2
        if item.labels:
            score += min(len(item.labels) * 0.05, 0.2)
        if item.source_channel in ("arxiv", "github", "wikipedia", "openreview"):
            score += 0.1
        return min(score, 1.0)

    def _score_diversity(self, item: ProcessedItem) -> float:
        """多样性 (基于词元唯一性)"""
        text = item.text or ""
        if not text:
            return 0.0
        words = re.findall(r"\w+", text.lower())
        if not words:
            return 0.0
        return min(len(set(words)) / len(words), 1.0)

    def _score_safety(self, item: ProcessedItem) -> float:
        """安全合规 — 1.0 = 干净"""
        text = (item.text or "").lower()
        if not text:
            return 1.0
        score = 1.0
        # 减分项
        bad_patterns = [
            (r"\b(viagra|cialis|casino|porn)\b", 0.3),
            (r"\b(buy now|click here|free trial)\b", 0.1),
            (r"\b(earn \$\d+|\$\d+ per (day|hour|week))\b", 0.4),
        ]
        for pat, penalty in bad_patterns:
            if re.search(pat, text, re.IGNORECASE):
                score -= penalty
        return max(score, 0.0)

    def _score_educational(self, item: ProcessedItem) -> float:
        """教育价值"""
        text = (item.text or "").lower()
        if not text:
            return 0.3
        score = 0.3
        edu_keywords = ["tutorial", "guide", "how to", "explanation", "example", "concept", "principle", "learn", "understand", "definition"]
        hits = sum(1 for kw in edu_keywords if kw in text)
        score += min(hits * 0.1, 0.6)
        if item.source_channel in ("arxiv", "wikipedia", "openreview", "github"):
            score += 0.1
        return min(score, 1.0)

    def _score_completeness(self, item: ProcessedItem) -> float:
        """完整度"""
        score = 0.0
        if item.title:
            score += 0.2
        if item.text and len(item.text) > 100:
            score += 0.3
        if item.images:
            score += 0.2
        if item.source_url:
            score += 0.15
        if item.source_metadata:
            score += 0.15
        return min(score, 1.0)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
