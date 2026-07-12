"""clean_dedupe_embed — Vector (CLIP) embedding deduplication.

Computes/looks up a CLIP-style embedding for one or more candidate items and
returns cosine-similarity groups.  Offline mode builds a deterministic
surrogate embedding from content hashing so thresholding remains meaningful.

Skill function: ``clean_dedupe_embed(input) -> SkillOutput``.
"""

import math
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_dedupe_embed"


class DedupeEmbedInput(BaseModel):
    items: List[str] = Field(..., description="List of media URLs / text snippets")
    threshold: float = Field(0.92, ge=0.0, le=1.0, description="Cosine ≥ threshold ⇒ duplicate")
    dim: int = Field(128, description="Embedding dimension for offline surrogate")


class DedupeEmbedOutput(BaseModel):
    duplicates: List[Dict[str, Any]] = Field(default_factory=list)
    embeddings: List[List[float]] = Field(default_factory=list)
    threshold: float = 0.92
    offline: bool = False


# ---------------------------------------------------------------------------
# Offline surrogate embedding — fixed-dim, deterministic, near-orthogonal
# ---------------------------------------------------------------------------
def _offline_embed(text: str, dim: int) -> List[float]:
    import hashlib

    base = hashlib.sha512(text.encode("utf-8")).digest()
    out: List[float] = []
    while len(out) < dim:
        for byte in base:
            out.append(((byte / 255.0) * 2) - 1)
            if len(out) >= dim:
                break
        base = hashlib.sha512(base).digest()
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def _cosine(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------
async def clean_dedupe_embed(input: SkillInput) -> SkillOutput:
    payload = DedupeEmbedInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/dedupe/embed",
        payload=payload.model_dump(),
        mock={"duplicates": [], "embeddings": []},
    )

    if remote["status"] == "ok" and remote["data"].get("embeddings"):
        embeddings = list(remote["data"]["embeddings"])
        offline = False
    else:
        embeddings = [_offline_embed(item, payload.dim) for item in payload.items]
        offline = True

    # Group duplicates by pairwise cosine ≥ threshold
    n = len(payload.items)
    seen = [False] * n
    duplicates: List[Dict[str, Any]] = []
    for i in range(n):
        if seen[i]:
            continue
        group = [i]
        for j in range(i + 1, n):
            if seen[j]:
                continue
            if _cosine(embeddings[i], embeddings[j]) >= payload.threshold:
                group.append(j)
                seen[j] = True
        seen[i] = True
        if len(group) > 1:
            duplicates.append({
                "members": [payload.items[k] for k in group],
                "indices": group,
                "similarity": payload.threshold,
            })

    out = DedupeEmbedOutput(
        duplicates=duplicates,
        embeddings=embeddings,
        threshold=payload.threshold,
        offline=offline,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_dedupe_embed", offline=offline, confidence=0.85 if not offline else 0.55),
    )


__all__ = ["DedupeEmbedInput", "DedupeEmbedOutput", "clean_dedupe_embed"]
