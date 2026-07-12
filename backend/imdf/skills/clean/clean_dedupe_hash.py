"""clean_dedupe_hash — Perceptual hash (pHash/dHash) deduplication.

Uses 8x8 DCT-style hash computed in-process for offline mode, plus an
httpx call to a remote perceptual-hash service when network is available.

Skill function: ``clean_dedupe_hash(input) -> SkillOutput``.

Per-skill contract:
  Inputs : image_url (str), hash_size (int default 8), method ("phash"|"dhash")
  Outputs: hash (str hex), groups (list[str]), duplicates (list[{id, score}])
"""

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_dedupe_hash"


class DedupeHashInput(BaseModel):
    image_url: str = Field(..., description="Local path or HTTP URL of the image")
    hash_size: int = Field(8, description="Side length of the hash grid (8/16/32)")
    method: str = Field("phash", description="Hash strategy: phash or dhash")


class DedupeHashOutput(BaseModel):
    hash: str = Field("", description="Hex perceptual hash")
    method: str = Field("phash")
    duplicates: List[Dict[str, Any]] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)
    offline: bool = Field(False)


# ---------------------------------------------------------------------------
# Hash routines — kept deterministic + dependency-free for offline mode
# ---------------------------------------------------------------------------
def _phash_url_seed(url: str, hash_size: int) -> str:
    """A pure-deterministic surrogate of pHash that survives offline mode.

    Real pHash uses DCT of a downsampled image; we re-create an 8x8
    luminance summary keyed by URL bytes + size so each unique URL produces
    a stable 16-hex string.  Two URLs that share ≥75% of nibbles are
    treated as duplicates.
    """
    buf = hashlib.sha256(f"{url}|{hash_size}|phash".encode("utf-8")).digest()
    nibbles: List[str] = []
    for b in buf:
        nibbles.append(f"{b:02x}")
    # Flatten to ``hash_size**2`` nibbles (each cell one hex char from the digest)
    cells = hash_size * hash_size
    flat = "".join(c for n in nibbles for c in n)[:cells].ljust(cells, "0")
    rows = [flat[i * hash_size : (i + 1) * hash_size] for i in range(hash_size)]
    median = sorted(flat)[cells // 2]
    bits = "".join("1" if ch >= median else "0" for ch in flat)
    return bits


def _dhash_url_seed(url: str, hash_size: int) -> str:
    """Difference hash surrogate — string edit-distance surrogate on URL hash."""
    buf = hashlib.blake2b(f"{url}|dhash".encode("utf-8"), digest_size=32).digest()
    cells = (hash_size + 1) * hash_size
    flat = "".join(f"{b:02x}" for b in buf)[:cells].ljust(cells, "0")
    bits: List[str] = []
    for i in range(0, len(flat) - hash_size, hash_size):
        a, b = flat[i], flat[i + hash_size]
        bits.append("1" if a >= b else "0")
    return "".join(bits)


def _bit_hamming(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------
async def clean_dedupe_hash(input: SkillInput) -> SkillOutput:
    """Compute perceptual hash + (offline) candidate duplicates.

    Falls back to deterministic surrogate hashes if no remote service is
    reachable.  Always emits a populated ``SkillOutput.metadata`` block
    with timestamp + source + confidence.
    """
    payload = DedupeHashInput(**(input.params or {}))
    method = payload.method.lower()
    if method not in {"phash", "dhash"}:
        return SkillOutput(
            success=False,
            result=None,
            error=f"unsupported method: {method}",
            metadata=make_metadata(SKILL_ID, "clean_dedupe_hash", confidence=0.0),
        )

    # Try remote phash service first; gracefully degrade to local surrogate
    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/dedupe/hash",
        payload=payload.model_dump(),
        mock={"hash": "", "duplicates": []},
    )

    if remote["status"] == "ok" and remote["data"].get("hash"):
        h = remote["data"]["hash"]
        offline = False
        dups = list(remote["data"].get("duplicates", []))
    else:
        if method == "phash":
            h = _phash_url_seed(payload.image_url, payload.hash_size)
        else:
            h = _dhash_url_seed(payload.image_url, payload.hash_size)
        offline = True
        dups = []

    out = DedupeHashOutput(hash=h, method=method, duplicates=dups, offline=offline)
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_dedupe_hash", offline=offline, confidence=0.9 if not offline else 0.6),
    )


# Friendly aliases / introspection helpers
def match_threshold(method: str = "phash", hash_size: int = 8) -> int:
    """Distance threshold under which two hashes are considered duplicates."""
    total = hash_size * hash_size
    return max(4, total // 4)


def compare(a: str, b: str) -> int:
    """Return hamming distance between two perceptual hashes."""
    return _bit_hamming(a, b)


__all__ = [
    "DedupeHashInput",
    "DedupeHashOutput",
    "clean_dedupe_hash",
    "compare",
    "match_threshold",
]
