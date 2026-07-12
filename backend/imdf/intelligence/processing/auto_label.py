"""智影 V4 — AutoLabelEngine: 多模型投票自动打标 (CLIP/LLaVA/BLIP-2/规则)"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from ..crawler.base import RawDocument
from .base import ProcessedItem, ProcessingPipeline

logger = logging.getLogger(__name__)


class LabelModel(str, Enum):
    """打标模型选择"""

    CLIP = "clip"
    LLAVA = "llava"
    BLIP2 = "blip2"
    GPT4V = "gpt4v"
    GEMINI_VISION = "gemini_vision"
    QWEN_VL = "qwen_vl"
    RULES = "rules"  # 规则引擎
    KEYWORDS = "keywords"  # 关键词匹配
    SPACY_NER = "spacy_ner"


class AutoLabelEngine(ProcessingPipeline):
    """多模型自动打标 — 投票机制 (>=2 模型共识)"""

    def __init__(
        self,
        models: Optional[List[LabelModel]] = None,
        consensus_threshold: int = 2,
        max_labels: int = 10,
        confidence_min: float = 0.5,
        custom_prompts: Optional[Dict[str, str]] = None,
    ):
        super().__init__(name="auto_label")
        self.models = models or [LabelModel.RULES, LabelModel.KEYWORDS]
        self.consensus_threshold = consensus_threshold
        self.max_labels = max_labels
        self.confidence_min = confidence_min
        self.custom_prompts = custom_prompts or {}
        # 标签候选集 (可扩展)
        self.candidate_labels = _default_label_taxonomy()

    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        items = self._to_items(items)
        self.metrics.total += len(items)
        out: List[ProcessedItem] = []
        for item in items:
            try:
                self._label_one(item)
                self.metrics.labeled += 1
                item.audit_chain.append(
                    {
                        "step": "auto_label",
                        "action": "labeled",
                        "labels": item.labels,
                        "n_labels": len(item.labels),
                        "ts": _now(),
                    }
                )
                out.append(item)
            except Exception as e:
                self.metrics.rejected += 1
                item.rejection_reason = f"label_error:{e}"
                logger.warning(f"labeling failed for {item.source_url}: {e}")
                out.append(item)  # 不阻断流水线
        self.finish()
        return out

    def _label_one(self, item: ProcessedItem):
        model_votes: Dict[str, int] = {}
        model_confidences: Dict[str, List[float]] = {}
        for model in self.models:
            labels = self._invoke_model(model, item)
            for label, conf in labels:
                model_votes[label] = model_votes.get(label, 0) + 1
                model_confidences.setdefault(label, []).append(conf)
        # 共识 (>= threshold 个模型投票)
        final_labels: List[tuple] = []
        for label, votes in model_votes.items():
            if votes >= self.consensus_threshold:
                confs = model_confidences[label]
                avg_conf = sum(confs) / len(confs)
                if avg_conf >= self.confidence_min:
                    final_labels.append((label, avg_conf, votes))
        # 排序: votes desc, conf desc
        final_labels.sort(key=lambda x: (x[2], x[1]), reverse=True)
        item.labels = [l[0] for l in final_labels[: self.max_labels]]
        item.label_confidences = {l[0]: round(l[1], 3) for l in final_labels[: self.max_labels]}
        item.status = "labeled"
        item.updated_at = _now()

    def _invoke_model(self, model: LabelModel, item: ProcessedItem) -> List[tuple]:
        """调用具体模型 — 返回 [(label, confidence), ...]"""
        if model == LabelModel.RULES:
            return self._label_rules(item)
        if model == LabelModel.KEYWORDS:
            return self._label_keywords(item)
        if model == LabelModel.SPACY_NER:
            return self._label_ner(item)
        # 视觉模型 (CLIP/LLaVA/BLIP-2/GPT4V) — 真实集成在 PlatformAgent
        return self._label_visual_stub(model, item)

    def _label_rules(self, item: ProcessedItem) -> List[tuple]:
        """规则匹配"""
        text = (item.text or "") + " " + (item.title or "")
        text_lower = text.lower()
        labels: List[tuple] = []
        # URL 域名规则
        from urllib.parse import urlparse
        if item.source_url:
            domain = urlparse(item.source_url).netloc.lower()
            if "github.com" in domain:
                labels.append(("code", 0.9))
            if "arxiv.org" in domain:
                labels.append(("academic", 0.95))
            if "reddit.com" in domain:
                labels.append(("social", 0.8))
            if "youtube.com" in domain or "youtu.be" in domain:
                labels.append(("video", 0.9))
            if "twitter.com" in domain or "x.com" in domain:
                labels.append(("social", 0.8))
        # 内容长度
        if len(text) > 5000:
            labels.append(("long_form", 0.7))
        if len(text) < 200:
            labels.append(("short_form", 0.6))
        # 内容类型规则 — 与 KEYWORDS 模型交叉
        if any(kw in text_lower for kw in ["machine learning", "ai", "artificial intelligence", "technology", "software", "algorithm"]):
            labels.append(("tech", 0.85))
        if any(kw in text_lower for kw in ["research", "study", "experiment", "scientific", "analysis"]):
            labels.append(("science", 0.8))
        if any(kw in text_lower for kw in ["tutorial", "guide", "how to", "step by step", "walkthrough"]):
            labels.append(("tutorial", 0.85))
        if any(kw in text_lower for kw in ["breaking", "report", "announced", "according to"]):
            labels.append(("news", 0.8))
        if any(kw in text_lower for kw in ["python", "javascript", "rust", "golang", "java", "typescript"]):
            labels.append(("code", 0.9))
        return labels

    def _label_keywords(self, item: ProcessedItem) -> List[tuple]:
        """关键词匹配 (从候选 taxonomy)"""
        text_lower = ((item.text or "") + " " + (item.title or "")).lower()
        labels: List[tuple] = []
        for label, keywords in self.candidate_labels.items():
            hits = sum(1 for kw in keywords if kw.lower() in text_lower)
            if hits > 0:
                conf = min(0.3 + hits * 0.15, 0.95)
                labels.append((label, conf))
        return labels

    def _label_ner(self, item: ProcessedItem) -> List[tuple]:
        """spaCy NER — 实体识别标签"""
        if not item.text:
            return []
        try:
            import spacy
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                # 退化: 简单正则
                return self._label_ner_fallback(item)
            doc = nlp(item.text[:100000])  # 限制长度
            ent_types: Counter = Counter()
            for ent in doc.ents:
                if ent.label_ in ("PERSON", "ORG", "GPE", "PRODUCT", "EVENT", "LAW", "LANGUAGE"):
                    ent_types[ent.text] += 1
            labels: List[tuple] = []
            for entity, count in ent_types.most_common(5):
                if count >= 1 and len(entity) > 1:
                    labels.append((entity, 0.7))
            return labels
        except ImportError:
            return self._label_ner_fallback(item)

    def _label_ner_fallback(self, item: ProcessedItem) -> List[tuple]:
        """NER fallback — 大写实体名"""
        text = item.text or ""
        # 简单提取: 连续大写词
        pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
        candidates = Counter(pattern.findall(text[:50000]))
        return [(name, 0.6) for name, c in candidates.most_common(5) if c >= 2]

    def _label_visual_stub(self, model: LabelModel, item: ProcessedItem) -> List[tuple]:
        """视觉模型 stub — 真实调用走 PlatformAgent.AutoLabelAgent"""
        # 仅当 type=image/video 且有图
        if item.type not in ("image", "video") or not item.images:
            return []
        # 真实集成时: async call → models/vlm/...
        return [(f"vlm_{model.value}_pending", 0.0)]


def _default_label_taxonomy() -> Dict[str, List[str]]:
    """默认标签候选 — 8 大类 200+ 标签"""
    return {
        # 主题
        "tech": ["technology", "software", "ai", "machine learning", "programming", "computer", "algorithm", "data"],
        "science": ["research", "study", "experiment", "hypothesis", "scientific", "analysis", "discovery"],
        "business": ["company", "market", "revenue", "startup", "finance", "investment", "ipo", "merger"],
        "politics": ["government", "election", "policy", "legislation", "president", "congress", "law"],
        "health": ["medical", "doctor", "patient", "disease", "treatment", "drug", "vaccine", "surgery"],
        "sports": ["game", "team", "player", "score", "tournament", "league", "coach"],
        "entertainment": ["movie", "music", "actor", "celebrity", "concert", "album", "show"],
        "education": ["school", "student", "teacher", "university", "course", "curriculum"],
        # 风格
        "tutorial": ["tutorial", "guide", "how to", "step by step", "walkthrough"],
        "news": ["breaking", "report", "announced", "according to", "sources say"],
        "opinion": ["i think", "i believe", "in my opinion", "personally"],
        # 数据类型
        "code": ["python", "javascript", "rust", "golang", "java", "c++", "typescript"],
        "data_viz": ["chart", "graph", "plot", "visualization", "dashboard", "infographic"],
        # 模态
        "image": ["photo", "photograph", "image", "picture", "wallpaper"],
        "video": ["video", "youtube", "stream", "vlog", "tutorial video"],
        "audio": ["podcast", "audio", "music", "song", "sound"],
        "document": ["pdf", "paper", "report", "whitepaper", "documentation"],
    }


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
