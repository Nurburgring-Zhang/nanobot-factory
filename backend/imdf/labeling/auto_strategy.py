"""V5 FR-6.3 - 4-Strategy Auto-labeling (CLIP / Rule / Active Learning / Consensus).

Strategies:
  * CLIPZeroShotStrategy    - Foundation Model (CLIP zero-shot) - mock top-3
  * RuleBasedStrategy       - Keyword/regex on caption/description
  * ActiveLearningStrategy  - uncertainty_score, routes high-entropy to human
  * ConsensusStrategy       - majority vote of above 3 (>= threshold)

The 4th strategy `ConsensusStrategy` is also the orchestrator's aggregation
mode: AutoLabelingOrchestrator runs all 3 base strategies in parallel via
asyncio.gather, then uses ConsensusStrategy to decide the final label.

When `consensus_threshold=0.8` and 3 of 3 strategies agree on the same
category, the consensus confidence is 1.0 -> label accepted.
With 2 of 3 agreement, confidence = 0.667 -> < 0.8 -> routed to human.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from imdf.labeling.auto_strategy_schemas import (
    Asset,
    LabelCategory,
    LabelConfidence,
    LabelResult,
    StrategyVote,
)

_log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _hash_to_unit_float(seed: str) -> float:
    """Deterministic [0, 1) hash for seeding random mock outputs.

    Used so the CLIP mock returns the same top-3 for the same input
    (testable determinism).
    """
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    n = int.from_bytes(h[:8], "big")
    return (n % 10**9) / 10**9


# --------------------------------------------------------------------------- #
#  Abstract strategy
# --------------------------------------------------------------------------- #
class AutoLabelingStrategy(ABC):
    """Abstract base for all labeling strategies."""

    strategy_name: str = "abstract"

    @abstractmethod
    async def label(self, asset: Asset) -> StrategyVote:
        """Return one vote for the given asset."""


# --------------------------------------------------------------------------- #
#  Strategy 1 - CLIP Zero-Shot (Foundation Model)
# --------------------------------------------------------------------------- #
class CLIPZeroShotStrategy(AutoLabelingStrategy):
    """Strategy 1: CLIP zero-shot classification.

    Real implementation would call transformers CLIPModel and run
    text-image similarity against the 12 LabelCategory prompts.

    Mock implementation: deterministic top-3 derived from a SHA256 of
    (asset_id + caption + description) - testable without GPU/model.
    """

    strategy_name = "clip"

    # CLIP text prompts for each category (real model would embed these)
    CATEGORY_PROMPTS: Dict[LabelCategory, str] = {
        LabelCategory.ANIMAL: "a photo of an animal",
        LabelCategory.PERSON: "a photo of a person",
        LabelCategory.VEHICLE: "a photo of a vehicle",
        LabelCategory.BUILDING: "a photo of a building",
        LabelCategory.NATURE: "a photo of nature, landscape",
        LabelCategory.FOOD: "a photo of food",
        LabelCategory.ART: "a photo of art or painting",
        LabelCategory.TEXT: "a photo containing text",
        LabelCategory.PRODUCT: "a photo of a product",
        LabelCategory.SCENE: "a photo of a scene",
        LabelCategory.ABSTRACT: "an abstract image",
        LabelCategory.OTHER: "other miscellaneous image",
    }

    def __init__(self, model: Optional[Any] = None) -> None:
        # In real use: `model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")`
        # We accept the model handle for test injection; default None = mock.
        self._model = model

    async def label(self, asset: Asset) -> StrategyVote:
        """Return deterministic top-3 (with score = cosine similarity, mocked).

        Mock formula:
          base = SHA256(asset_id + caption) -> [0, 1)
          top1 = base
          top2 = (base + 0.13) % 1.0 (but distinct category)
          top3 = (base + 0.27) % 1.0
          confidence = top1
          uncertainty = 1 - top1
        """
        # Hash the asset id+caption (deterministic)
        seed = f"{asset.asset_id}|{asset.caption}|{asset.description}"
        base = _hash_to_unit_float(seed)

        cats = list(LabelCategory)
        # Pick distinct categories deterministically
        n = len(cats)
        i1 = int(base * n) % n
        i2 = (i1 + int(base * 100) + 1) % n
        i3 = (i2 + int(base * 100) + 2) % n

        top1_score = round(0.55 + base * 0.4, 4)  # [0.55, 0.95]
        top2_score = round(top1_score - 0.18 - base * 0.05, 4)
        top3_score = round(top1_score - 0.30 - base * 0.08, 4)
        # clamp lower
        top2_score = max(0.05, top2_score)
        top3_score = max(0.02, top3_score)

        top_k = [
            LabelConfidence(category=cats[i1], score=top1_score),
            LabelConfidence(category=cats[i2], score=top2_score),
            LabelConfidence(category=cats[i3], score=top3_score),
        ]

        return StrategyVote(
            strategy=self.strategy_name,
            asset_id=asset.asset_id,
            top_k=top_k,
            confidence=top1_score,
            uncertainty=round(1.0 - top1_score, 4),
            needs_human_review=False,
            note="mock CLIP zero-shot",
        )


# --------------------------------------------------------------------------- #
#  Strategy 2 - Rule-based (keyword/regex)
# --------------------------------------------------------------------------- #
class RuleBasedStrategy(AutoLabelingStrategy):
    """Strategy 2: rule-based labeling using keyword/regex on caption/description.

    Default rules cover the 12 categories with simple keyword matching.
    Users can pass custom rules (Dict[LabelCategory, List[str]]).
    """

    strategy_name = "rule"

    DEFAULT_RULES: Dict[LabelCategory, List[str]] = {
        LabelCategory.ANIMAL: [
            r"\b(dog|cat|bird|horse|fish|animal|puppy|kitten|lion|tiger)\b",
        ],
        LabelCategory.PERSON: [
            r"\b(person|man|woman|boy|girl|child|people|human|portrait)\b",
        ],
        LabelCategory.VEHICLE: [
            r"\b(car|truck|bike|bicycle|bus|train|plane|vehicle|automobile)\b",
        ],
        LabelCategory.BUILDING: [
            r"\b(building|house|tower|skyscraper|architecture|church|mosque)\b",
        ],
        LabelCategory.NATURE: [
            r"\b(tree|mountain|forest|river|beach|sunset|sunrise|sky|nature)\b",
        ],
        LabelCategory.FOOD: [
            r"\b(food|meal|restaurant|dish|cake|pizza|burger|sushi|coffee)\b",
        ],
        LabelCategory.ART: [
            r"\b(painting|drawing|art|sketch|illustration|sculpture)\b",
        ],
        LabelCategory.TEXT: [
            r"\b(text|sign|letter|word|document|page|book|caption)\b",
        ],
        LabelCategory.PRODUCT: [
            r"\b(product|item|package|bottle|box|gadget|tool)\b",
        ],
        LabelCategory.SCENE: [
            r"\b(scene|view|landscape|cityscape|panorama|interior)\b",
        ],
        LabelCategory.ABSTRACT: [
            r"\b(abstract|pattern|geometric|texture|gradient)\b",
        ],
    }

    def __init__(self, rules: Optional[Dict[LabelCategory, List[str]]] = None) -> None:
        self._rules = rules or self.DEFAULT_RULES
        # Pre-compile regexes
        self._compiled: Dict[LabelCategory, List[re.Pattern]] = {
            cat: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cat, patterns in self._rules.items()
        }

    async def label(self, asset: Asset) -> StrategyVote:
        """Match caption+description against rules; pick highest-scoring category."""
        text = f"{asset.caption} {asset.description}"

        scores: Dict[LabelCategory, float] = {}
        for cat, patterns in self._compiled.items():
            matched = sum(1 for p in patterns if p.search(text))
            if matched:
                scores[cat] = min(1.0, 0.6 + 0.1 * matched)

        if not scores:
            # No match -> OTHER with low confidence
            top_k = [LabelConfidence(category=LabelCategory.OTHER, score=0.3)]
            return StrategyVote(
                strategy=self.strategy_name,
                asset_id=asset.asset_id,
                top_k=top_k,
                confidence=0.3,
                uncertainty=0.7,
                needs_human_review=True,
                note="no rule match",
            )

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top1_cat, top1_score = ranked[0]
        top2 = ranked[1] if len(ranked) > 1 else (LabelCategory.OTHER, 0.05)
        top3 = ranked[2] if len(ranked) > 2 else (LabelCategory.OTHER, 0.02)

        top_k = [
            LabelConfidence(category=top1_cat, score=round(top1_score, 4)),
            LabelConfidence(category=top2[0], score=round(top2[1], 4)),
            LabelConfidence(category=top3[0], score=round(top3[1], 4)),
        ]

        return StrategyVote(
            strategy=self.strategy_name,
            asset_id=asset.asset_id,
            top_k=top_k,
            confidence=round(top1_score, 4),
            uncertainty=round(1.0 - top1_score, 4),
            needs_human_review=False,
            note="rule match",
        )


# --------------------------------------------------------------------------- #
#  Strategy 3 - Active learning (uncertainty -> human review)
# --------------------------------------------------------------------------- #
class ActiveLearningStrategy(AutoLabelingStrategy):
    """Strategy 3: uncertainty-based active learning.

    Computes uncertainty from the entropy of a (mocked) prediction
    distribution. Assets with uncertainty > threshold are routed to
    a human review queue (needs_human_review=True) and the final label
    is tentative.
    """

    strategy_name = "active"

    def __init__(
        self,
        uncertainty_threshold: float = 0.7,
        entropy_fn: Optional[Any] = None,
    ) -> None:
        if not 0.0 <= uncertainty_threshold <= 1.0:
            raise ValueError(
                f"uncertainty_threshold must be in [0, 1], got {uncertainty_threshold}"
            )
        self._threshold = uncertainty_threshold
        self._entropy_fn = entropy_fn  # allow injection for tests

    async def label(self, asset: Asset) -> StrategyVote:
        """Compute uncertainty deterministically from asset text length.

        Heuristic: longer captions -> more entropy (more categories plausible).
        For real use, this would consume CLIP or BLIP-2 logits and compute
        Shannon entropy over the softmax distribution.
        """
        text_len = len(asset.caption) + len(asset.description)
        # Map text_len -> [0, 1]: capped sigmoid-ish curve
        u = min(1.0, text_len / 200.0)

        # Add deterministic jitter
        jitter = _hash_to_unit_float(f"entropy|{asset.asset_id}")
        u = round(min(1.0, u * 0.7 + jitter * 0.3), 4)

        needs_review = u > self._threshold
        # Tentative label: most likely category by random pick (deterministic)
        cats = list(LabelCategory)
        i = int(_hash_to_unit_float(f"act|{asset.asset_id}") * len(cats)) % len(cats)
        tentative = cats[i]

        top_k = [
            LabelConfidence(category=tentative, score=round(1.0 - u, 4)),
            LabelConfidence(category=LabelCategory.OTHER, score=round(u * 0.5, 4)),
        ]

        return StrategyVote(
            strategy=self.strategy_name,
            asset_id=asset.asset_id,
            top_k=top_k,
            confidence=round(1.0 - u, 4),
            uncertainty=u,
            needs_human_review=needs_review,
            note=(
                "high uncertainty -> human review"
                if needs_review
                else "confident"
            ),
        )


# --------------------------------------------------------------------------- #
#  Strategy 4 - Consensus (multi-strategy vote)
# --------------------------------------------------------------------------- #
class ConsensusStrategy(AutoLabelingStrategy):
    """Strategy 4: weighted consensus of multiple base strategies.

    Accepts pre-computed `votes` from the other 3 strategies and aggregates
    them. Acceptance rule:
        - if the top category has weighted_score >= threshold -> ACCEPT
        - else -> needs_human_review=True

    threshold default 0.8 means >= 80% of weighted evidence must agree.
    With 3 strategies each weighted equally, this is satisfied when all 3
    agree (3/3 = 1.0) but NOT when only 2 of 3 agree (2/3 = 0.667).
    """

    strategy_name = "consensus"

    def __init__(self, consensus_threshold: float = 0.8) -> None:
        if not 0.0 <= consensus_threshold <= 1.0:
            raise ValueError(
                f"consensus_threshold must be in [0, 1], got {consensus_threshold}"
            )
        self._threshold = consensus_threshold

    async def label(
        self,
        asset: Asset,
        votes: Optional[List[StrategyVote]] = None,
    ) -> StrategyVote:
        """Aggregate `votes` into a single consensus vote.

        If `votes` is None, this strategy degrades to a uniform OTHER vote.
        """
        if not votes:
            return StrategyVote(
                strategy=self.strategy_name,
                asset_id=asset.asset_id,
                top_k=[LabelConfidence(category=LabelCategory.OTHER, score=0.0)],
                confidence=0.0,
                uncertainty=1.0,
                needs_human_review=True,
                note="no votes to aggregate",
            )

        # Sum weighted scores per category
        cat_scores: Dict[LabelCategory, float] = {}
        for vote in votes:
            if vote.top_k:
                for lc in vote.top_k:
                    cat_scores[lc.category] = cat_scores.get(lc.category, 0.0) + lc.score

        if not cat_scores:
            return StrategyVote(
                strategy=self.strategy_name,
                asset_id=asset.asset_id,
                top_k=[LabelConfidence(category=LabelCategory.OTHER, score=0.0)],
                confidence=0.0,
                uncertainty=1.0,
                needs_human_review=True,
                note="empty vote scores",
            )

        n = len(votes)
        # Normalize by max possible = n (if all strategies chose same category)
        ranked = sorted(cat_scores.items(), key=lambda x: x[1], reverse=True)
        top1_cat, top1_raw = ranked[0]
        top1_score = top1_raw / n  # normalized to [0, 1]
        top2 = ranked[1] if len(ranked) > 1 else (LabelCategory.OTHER, 0.0)
        top3 = ranked[2] if len(ranked) > 2 else (LabelCategory.OTHER, 0.0)

        top_k = [
            LabelConfidence(category=top1_cat, score=round(top1_score, 4)),
            LabelConfidence(category=top2[0], score=round(top2[1] / n, 4)),
            LabelConfidence(category=top3[0], score=round(top3[1] / n, 4)),
        ]

        needs_review = top1_score < self._threshold
        return StrategyVote(
            strategy=self.strategy_name,
            asset_id=asset.asset_id,
            top_k=top_k,
            confidence=round(top1_score, 4),
            uncertainty=round(1.0 - top1_score, 4),
            needs_human_review=needs_review,
            note=(
                f"consensus {top1_score:.2f} "
                f"{'<' if needs_review else '>='} "
                f"threshold {self._threshold}"
            ),
        )


# --------------------------------------------------------------------------- #
#  Orchestrator - runs all 3 base strategies in parallel + consensus
# --------------------------------------------------------------------------- #
class AutoLabelingOrchestrator:
    """Runs CLIP + Rule + Active Learning in parallel, then Consensus.

    Usage:
        orch = AutoLabelingOrchestrator()
        result = await orch.label_one(asset)         # single asset
        results = await orch.label_batch([a1, a2])   # batch via asyncio.gather
    """

    def __init__(
        self,
        clip: Optional[CLIPZeroShotStrategy] = None,
        rule: Optional[RuleBasedStrategy] = None,
        active: Optional[ActiveLearningStrategy] = None,
        consensus: Optional[ConsensusStrategy] = None,
    ) -> None:
        self.clip = clip or CLIPZeroShotStrategy()
        self.rule = rule or RuleBasedStrategy()
        self.active = active or ActiveLearningStrategy()
        self.consensus = consensus or ConsensusStrategy(consensus_threshold=0.8)

    async def _run_base_strategies(self, asset: Asset) -> List[StrategyVote]:
        """Fan-out: run CLIP + Rule + Active concurrently via asyncio.gather."""
        return await asyncio.gather(
            self.clip.label(asset),
            self.rule.label(asset),
            self.active.label(asset),
        )

    async def label_one(self, asset: Asset) -> LabelResult:
        """Label a single asset using all 4 strategies.

        Returns a LabelResult that may have needs_human_review=True if
        any of (consensus, active learning) is uncertain.
        """
        base_votes = await self._run_base_strategies(asset)
        consensus_vote = await self.consensus.label(asset, votes=base_votes)
        all_votes = list(base_votes) + [consensus_vote]

        # needs_human_review if any base vote OR consensus votes it
        needs_review = any(v.needs_human_review for v in all_votes)

        final_label = consensus_vote.top_k[0].category if consensus_vote.top_k else LabelCategory.OTHER
        confidence = consensus_vote.confidence
        uncertainty = consensus_vote.uncertainty

        return LabelResult(
            asset_id=asset.asset_id,
            final_label=final_label,
            confidence=confidence,
            uncertainty=uncertainty,
            needs_human_review=needs_review,
            strategy_votes=all_votes,
            top_k=consensus_vote.top_k,
        )

    async def label_batch(self, assets: List[Asset]) -> List[LabelResult]:
        """Label a batch of assets via asyncio.gather (per-asset parallel)."""
        if not assets:
            return []
        coros = [self.label_one(a) for a in assets]
        return await asyncio.gather(*coros)


__all__ = [
    "AutoLabelingStrategy",
    "CLIPZeroShotStrategy",
    "RuleBasedStrategy",
    "ActiveLearningStrategy",
    "ConsensusStrategy",
    "AutoLabelingOrchestrator",
    "_hash_to_unit_float",
]