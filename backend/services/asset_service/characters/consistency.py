"""P4-5-W1: Character Consistency Checker — Bernini-style identity drift detection.

Background (借鉴 Bernini):
  * When you generate the same character across many shots / images / videos,
    the identity drifts: face shape changes, hair color shifts, outfit varies.
  * Bernini detects this by comparing each generated frame against the locked
    reference set along 3 axes: face / hair / outfit (and a global CLIP
    embedding).
  * Drift thresholds:
      - score >= 0.95 → ✅ on-character (no action)
      - 0.85 <= score < 0.95 → ⚠️  warn (log + flag, don't regenerate)
      - score < 0.85 → ❌ reject (force regenerate or fail)

This module implements the same 3-axis check:
  * **CLIP embedding similarity** (global semantic match) — backed by a
    deterministic hash-based pseudo-embedding when CLIP isn't available
    so unit tests run hermetically.
  * **Face / hair / outfit dimension matching** — string-keyword + value
    diff on the locked feature dicts. Each axis returns a sub-score in
    [0, 1].

The aggregated ``consistency_score`` is a weighted average:
    score = 0.4 * clip_sim + 0.25 * face_match + 0.20 * hair_match + 0.15 * outfit_match

Public surface:
  * ``CharacterConsistencyChecker.check(asset, generated_image_meta)``
      → ``ConsistencyResult`` (with sub-scores + recommendation)
  * ``score_clip_similarity(features_a, features_b)`` — pure function, unit-testable
  * ``score_face_match(reference_face, candidate_face)`` — pure
  * ``score_hair_match(reference_hair, candidate_hair)`` — pure
  * ``score_outfit_match(reference_outfit, candidate_outfit)`` — pure
  * ``recommend(score)`` — maps score → "accept" / "warn" / "reject"

Design notes:
  * No external services (CLIP, face-recognition) — we use a deterministic
    pseudo-embedding derived from the feature dict so the same input always
    produces the same score. In prod, swap with real CLIP (P4-5-FUTURE).
  * Pure Python — no numpy/scipy dependency, easy to test.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# ─── Constants ────────────────────────────────────────────────────────────────

CLIP_WEIGHT = 0.40
FACE_WEIGHT = 0.25
HAIR_WEIGHT = 0.20
OUTFIT_WEIGHT = 0.15

WARN_THRESHOLD = 0.85
ACCEPT_THRESHOLD = 0.95

# Face keys we care about (normalized lowercase)
FACE_KEYS = {
    "shape", "eye_color", "eye_shape", "nose", "mouth", "brow",
    "skin_tone", "age", "ethnicity", "face_mark", "jawline",
}

# Hair keys
HAIR_KEYS = {
    "color", "length", "style", "texture", "bun", "ponytail", "sideburn",
}

# Outfit keys (note: accessory is its own category in LockedFeature)
OUTFIT_KEYS = {
    "top", "bottom", "shoes", "main_color", "secondary_color", "pattern",
    "fabric", "collar", "sleeve",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConsistencyResult:
    """Outcome of one consistency check."""

    character_id: str
    score: float
    recommendation: str  # "accept" | "warn" | "reject"
    clip_similarity: float
    face_match: float
    hair_match: float
    outfit_match: float
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# Pseudo CLIP embedding (deterministic, no external deps)
# ═══════════════════════════════════════════════════════════════════════════════

def _text_to_pseudo_vector(text: str, dim: int = 64) -> List[float]:
    """Map text → unit vector in R^dim.

    Algorithm: split text into tokens, hash each token to a position in
    [0, dim), add/subtract 1.0 weighted by token frequency. Then L2-normalize.
    Deterministic — same text → same vector.
    """
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    # tokenize on non-word (keep CJK chars as single tokens)
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+|[\u3040-\u30ff]+", text.lower())
    for tok in tokens:
        if not tok:
            continue
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        # 4 bytes → index (mod dim)
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        vec[idx] += sign * (1.0 + (h[5] / 255.0))
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 1e-9:
        vec = [x / norm for x in vec]
    return vec


def _features_to_text(features: Dict[str, Any]) -> str:
    """Flatten a features dict into a text blob for embedding."""
    parts: List[str] = []
    for k in sorted(features.keys()):
        v = features[k]
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            v = " ".join(str(x) for x in v if x is not None)
        parts.append(f"{k}={v}")
    return " ".join(parts)


def score_clip_similarity(features_a: Dict[str, Any], features_b: Dict[str, Any]) -> float:
    """Compute cosine similarity in [0, 1] (clipped from [-1, 1])."""
    if not features_a and not features_b:
        return 1.0
    if not features_a or not features_b:
        return 0.0
    text_a = _features_to_text(features_a)
    text_b = _features_to_text(features_b)
    if not text_a or not text_b:
        return 0.0
    va = _text_to_pseudo_vector(text_a)
    vb = _text_to_pseudo_vector(text_b)
    # cosine = dot(v_a, v_b) since both unit-norm
    dot = sum(a * b for a, b in zip(va, vb))
    # map [-1, 1] → [0, 1]
    return max(0.0, min(1.0, 0.5 * (dot + 1.0)))


# ═══════════════════════════════════════════════════════════════════════════════
# Per-dimension matchers
# ═══════════════════════════════════════════════════════════════════════════════

def _norm(value: Any) -> str:
    """Normalize a feature value for comparison."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple, set)):
        return " ".join(sorted(_norm(x) for x in value))
    if isinstance(value, float):
        # round to 2 decimals
        return f"{value:.2f}"
    return str(value).strip().lower()


def _score_dict_match(reference: Dict[str, Any], candidate: Dict[str, Any],
                      relevant_keys: set) -> Tuple[float, Dict[str, Any]]:
    """Score how well candidate matches reference on the relevant keys.

    Returns ``(score, details)`` where score is in [0, 1]:
      * 1.0 = perfect match on every relevant key, or no axes defined
      * 0.0 = every considered key mismatched
      * 0.5 = empty candidate but non-empty reference → 0.5 (drift warning)
      * when **reference has no values for any relevant key** → neutral 1.0
        (no constraints to check, so we don't penalize)
    """
    if not relevant_keys:
        # no axes defined → neutral 1.0
        return 1.0, {"matched": [], "missing": [], "mismatched": []}

    matched: List[str] = []
    mismatched: List[str] = []
    missing: List[str] = []

    for key in sorted(relevant_keys):
        ref_v = reference.get(key)
        cand_v = candidate.get(key)
        if ref_v is None:
            # Reference didn't constrain this axis — skip
            continue
        if cand_v is None:
            missing.append(key)
            continue
        if _norm(ref_v) == _norm(cand_v):
            matched.append(key)
        else:
            mismatched.append(f"{key}:{_norm(ref_v)}!={_norm(cand_v)}")

    # If reference had nothing on this axis, return neutral 1.0
    if not matched and not mismatched and not missing:
        return 1.0, {"matched": [], "missing": [], "mismatched": []}

    considered = max(1, len(matched) + len(mismatched) + len(missing))
    raw = len(matched) / considered
    # missing keys → soft penalty (we may simply not have measured yet)
    if missing and not matched:
        return 0.5, {
            "matched": matched, "missing": missing, "mismatched": mismatched,
        }
    return raw, {
        "matched": matched, "missing": missing, "mismatched": mismatched,
    }


def score_face_match(reference: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Compare face feature dicts."""
    return _score_dict_match(reference or {}, candidate or {}, FACE_KEYS)


def score_hair_match(reference: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    return _score_dict_match(reference or {}, candidate or {}, HAIR_KEYS)


def score_outfit_match(reference: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    return _score_dict_match(reference or {}, candidate or {}, OUTFIT_KEYS)


# ═══════════════════════════════════════════════════════════════════════════════
# Recommendation + aggregate
# ═══════════════════════════════════════════════════════════════════════════════

def recommend(score: float) -> str:
    """Map a score to a recommendation."""
    if score >= ACCEPT_THRESHOLD:
        return "accept"
    if score >= WARN_THRESHOLD:
        return "warn"
    return "reject"


def aggregate(clip_sim: float, face: float, hair: float, outfit: float) -> float:
    """Weighted average consistency score."""
    score = (
        CLIP_WEIGHT * clip_sim
        + FACE_WEIGHT * face
        + HAIR_WEIGHT * hair
        + OUTFIT_WEIGHT * outfit
    )
    return round(max(0.0, min(1.0, score)), 4)


# ═══════════════════════════════════════════════════════════════════════════════
# Public checker
# ═══════════════════════════════════════════════════════════════════════════════

class CharacterConsistencyChecker:
    """Bernini-style consistency checker.

    Usage::

        checker = CharacterConsistencyChecker()
        result = checker.check(character_asset, generated_metadata)
        if result.recommendation == "reject":
            raise HTTPException(409, "character drift too large — regenerate")
    """

    def __init__(
        self,
        *,
        warn_threshold: float = WARN_THRESHOLD,
        accept_threshold: float = ACCEPT_THRESHOLD,
    ) -> None:
        self.warn_threshold = float(warn_threshold)
        self.accept_threshold = float(accept_threshold)

    def check(
        self,
        character: Any,  # CharacterAsset-like (duck-typed)
        generated_meta: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyResult:
        """Score a freshly generated artifact against the locked character.

        ``generated_meta`` is a dict with optional keys:
          ``face_features``, ``voice_features``, ``body_features``,
          ``style_features``, ``image_url``, ``prompt``, ``model``.
        Missing keys fall back to the character's own features (i.e. perfect
        match is implied when nothing is supplied — useful for /lock pre-check).
        """
        gen = generated_meta or {}

        # Reference = locked features (these are the ground truth)
        ref_face = (character.face_features or {})
        ref_hair = (character.style_features or {}).get("hair", {}) or {}
        ref_outfit = (character.style_features or {}).get("outfit", {}) or {}

        # Candidate = what was just generated (or ref if missing)
        cand_face = gen.get("face_features") or character.face_features or {}
        cand_hair = gen.get("style_features", {}).get("hair") or (character.style_features or {}).get("hair", {}) or {}
        cand_outfit = gen.get("style_features", {}).get("outfit") or (character.style_features or {}).get("outfit", {}) or {}

        # CLIP-like embedding on full feature dicts
        ref_all = {
            "face": ref_face, "hair": ref_hair, "outfit": ref_outfit,
            "locked": [f"{lf.category}:{lf.name}" for lf in (character.locked_features or [])],
        }
        cand_all = {
            "face": cand_face, "hair": cand_hair, "outfit": cand_outfit,
            "locked": [f"{lf.category}:{lf.name}" for lf in (character.locked_features or [])],
        }
        clip_sim = score_clip_similarity(ref_all, cand_all)

        face, face_detail = score_face_match(ref_face, cand_face)
        hair, hair_detail = score_hair_match(ref_hair, cand_hair)
        outfit, outfit_detail = score_outfit_match(ref_outfit, cand_outfit)

        score = aggregate(clip_sim, face, hair, outfit)
        rec = self._recommend(score)

        return ConsistencyResult(
            character_id=character.id,
            score=score,
            recommendation=rec,
            clip_similarity=round(clip_sim, 4),
            face_match=round(face, 4),
            hair_match=round(hair, 4),
            outfit_match=round(outfit, 4),
            details={
                "face": face_detail,
                "hair": hair_detail,
                "outfit": outfit_detail,
                "generated_meta_keys": sorted(gen.keys()),
                "thresholds": {
                    "warn": self.warn_threshold,
                    "accept": self.accept_threshold,
                },
                "weights": {
                    "clip": CLIP_WEIGHT, "face": FACE_WEIGHT,
                    "hair": HAIR_WEIGHT, "outfit": OUTFIT_WEIGHT,
                },
            },
        )

    def _recommend(self, score: float) -> str:
        if score >= self.accept_threshold:
            return "accept"
        if score >= self.warn_threshold:
            return "warn"
        return "reject"


# ═══════════════════════════════════════════════════════════════════════════════
# Module exports
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ConsistencyResult",
    "CharacterConsistencyChecker",
    "score_clip_similarity",
    "score_face_match",
    "score_hair_match",
    "score_outfit_match",
    "aggregate",
    "recommend",
    "WARN_THRESHOLD",
    "ACCEPT_THRESHOLD",
]
