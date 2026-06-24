"""P4-5-W1 — Character consistency checker tests (4 tests).

Coverage:
  1. recommend() threshold mapping — accept / warn / reject
  2. score_clip_similarity — same features → high; different → low
  3. score_face_match / score_hair_match / score_outfit_match — pure matchers
  4. CharacterConsistencyChecker end-to-end on a populated character
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_recommend_thresholds():
    """Map score → recommendation via the public thresholds."""
    from services.asset_service.characters.consistency import (
        ACCEPT_THRESHOLD,
        WARN_THRESHOLD,
        recommend,
    )
    assert ACCEPT_THRESHOLD > WARN_THRESHOLD > 0

    # Accept region (>= ACCEPT_THRESHOLD = 0.95)
    assert recommend(1.0) == "accept"
    assert recommend(ACCEPT_THRESHOLD) == "accept"
    assert recommend(0.96) == "accept"
    # Warn region (WARN..ACCEPT) — exclusive of ACCEPT (otherwise would be "accept")
    assert recommend(0.94) == "warn"
    assert recommend(0.90) == "warn"
    assert recommend(WARN_THRESHOLD) == "warn"
    # Reject region
    assert recommend(0.84) == "reject"
    assert recommend(0.5) == "reject"
    assert recommend(0.0) == "reject"


def test_clip_similarity_self_and_different():
    """score_clip_similarity: same input → 1.0; very different → low."""
    from services.asset_service.characters.consistency import score_clip_similarity

    a = {"face": "oval", "hair_color": "black", "outfit": "navy uniform"}
    # Identical → near-perfect
    assert score_clip_similarity(a, dict(a)) > 0.95
    # Completely different content → low
    b = {"completely": "different", "totally": "unrelated", "stuff": "x"}
    sim_diff = score_clip_similarity(a, b)
    assert sim_diff < 0.7
    # Empty both → 1.0
    assert score_clip_similarity({}, {}) == 1.0
    # Empty vs populated → 0.0
    assert score_clip_similarity({}, {"x": "y"}) == 0.0


def test_face_hair_outfit_matchers():
    """Pure matchers: same → 1.0, partial → proportional, missing → warn-level."""
    from services.asset_service.characters.consistency import (
        score_face_match,
        score_hair_match,
        score_outfit_match,
    )

    # Face — perfect match
    ref = {"shape": "oval", "eye_color": "black", "skin_tone": "fair"}
    cand_ok = {"shape": "oval", "eye_color": "black", "skin_tone": "fair"}
    score, detail = score_face_match(ref, cand_ok)
    assert score == 1.0
    assert detail["matched"] == ["eye_color", "shape", "skin_tone"]
    assert detail["missing"] == []
    assert detail["mismatched"] == []

    # Face — one mismatch
    cand_bad = {"shape": "round", "eye_color": "black", "skin_tone": "fair"}
    score, detail = score_face_match(ref, cand_bad)
    assert 0.0 < score < 1.0
    assert "shape" in detail["mismatched"][0]

    # Hair — pure
    ref_h = {"color": "black", "length": "long", "style": "ponytail"}
    score, _ = score_hair_match(ref_h, ref_h)
    assert score == 1.0

    # Outfit — missing values fall through (0.5 partial)
    ref_o = {"main_color": "navy", "fabric": "cotton"}
    score, detail = score_outfit_match(ref_o, {"fabric": "cotton"})
    assert score == 0.5  # missing → soft 0.5


def test_consistency_checker_end_to_end():
    """CharacterConsistencyChecker.check returns a full ConsistencyResult."""
    from services.asset_service.characters.consistency import (
        CharacterConsistencyChecker,
        recommend,
    )
    from services.asset_service.characters.models import (
        CharacterAsset,
        LockedFeature,
        ReferenceImage,
    )

    character = CharacterAsset(
        name="苏晚晴",
        reference_images=[
            ReferenceImage(angle="front", url="https://x.com/c1f.png"),
            ReferenceImage(angle="side", url="https://x.com/c1s.png"),
        ],
        face_features={
            "shape": "oval", "eye_color": "black",
            "skin_tone": "fair", "age": "20s",
        },
        voice_features={"language": "zh", "pitch": "medium"},
        style_features={
            "art_style": "anime",
            "hair": {"color": "black", "length": "long", "style": "ponytail"},
            "outfit": {"top": "school uniform", "main_color": "navy"},
        },
        locked_features=[
            LockedFeature(category="face", name="oval face", weight=2.0),
            LockedFeature(category="hair", name="black ponytail", weight=2.0),
        ],
    )

    checker = CharacterConsistencyChecker()

    # Perfect match (no generated meta) → high score
    r1 = checker.check(character, None)
    assert 0.0 <= r1.score <= 1.0
    assert r1.character_id == character.id
    assert r1.recommendation in {"accept", "warn"}  # should be accept or warn
    assert 0.0 <= r1.clip_similarity <= 1.0
    assert 0.0 <= r1.face_match <= 1.0
    assert 0.0 <= r1.hair_match <= 1.0
    assert 0.0 <= r1.outfit_match <= 1.0
    # weights are exposed in details
    assert r1.details["weights"]["clip"] == 0.40
    # thresholds exposed
    assert r1.details["thresholds"]["warn"] < r1.details["thresholds"]["accept"]

    # Drifted candidate → lower score
    drifted = {
        "face_features": {
            "shape": "round", "eye_color": "blue",
            "skin_tone": "dark", "age": "40s",
        },
        "style_features": {
            "hair": {"color": "blonde", "length": "short", "style": "bob"},
            "outfit": {"top": "t-shirt", "main_color": "red"},
        },
    }
    r2 = checker.check(character, drifted)
    assert r2.score < r1.score
    assert r2.recommendation in {"warn", "reject"}

    # Result serializes to dict
    d = r2.to_dict()
    assert "character_id" in d
    assert "recommendation" in d
    assert recommend(r2.score) == r2.recommendation
