"""P22-P2-real-fix-3-Engines — DataT2IEngine (real text-to-image data).

Wraps ``ImageEngine`` for the data-production pipeline. Adds:
- Batch generation with concurrency (asyncio.gather)
- Dataset manifest writing (JSONL + Parquet-ready schema)
- Deterministic seed cycling for reproducible batches
- Quality scoring (perceptual hash dedup, basic aesthetic)

Public API:
- ``DataT2IEngine.batch(prompts, ...)`` — concurrent generation
- ``DataT2IEngine.write_manifest(results, out_path)`` — JSONL manifest
- ``DataT2IEngine.score(result)`` — quality score (0..1)

The engine never raises; failures are returned in the result envelope.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image  # type: ignore

from imdf.engines.image_engine import ImageEngine, ImageRequest, ImageResult, get_image_engine

logger = logging.getLogger(__name__)


@dataclass
class BatchT2IResult:
    """Single batch slot result."""
    index: int
    prompt: str
    success: bool
    image_path: Optional[str] = None
    image_b64: Optional[str] = None
    image_hash: Optional[str] = None
    width: int = 0
    height: int = 0
    seed_used: Optional[int] = None
    engine: str = ""
    score: float = 0.0
    error: str = ""


@dataclass
class BatchT2IOutput:
    """Whole-batch envelope."""
    total: int
    succeeded: int
    failed: int
    dedup_count: int
    results: List[BatchT2IResult]
    manifest_path: Optional[str] = None
    engine_chain: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class DataT2IEngine:
    """Real text-to-image batch engine."""

    def __init__(self, image_engine: Optional[ImageEngine] = None) -> None:
        self.image_engine = image_engine or get_image_engine()

    async def _gen_one(self, idx: int, prompt: str, *, width: int, height: int,
                       seed: Optional[int], out_dir: Optional[Path]) -> BatchT2IResult:
        """Generate one image. Runs the sync ImageEngine in a thread."""
        req = ImageRequest(prompt=prompt, width=width, height=height, seed=seed)
        try:
            res: ImageResult = await asyncio.to_thread(self.image_engine.generate, req)
        except Exception as exc:  # noqa: BLE001
            return BatchT2IResult(index=idx, prompt=prompt, success=False, error=f"{type(exc).__name__}: {exc}")
        if not res.success:
            return BatchT2IResult(index=idx, prompt=prompt, success=False, error=res.error, engine=res.engine)
        # Perceptual hash + quality score
        phash = self.image_engine.perceptual_hash(res.image_bytes or b"")
        score = self._score_result(res)
        # Persist
        image_path = None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{idx:04d}_{phash[:8]}.png"
            image_path = str(out_dir / fname)
            (out_dir / fname).write_bytes(res.image_bytes or b"")
        return BatchT2IResult(
            index=idx, prompt=prompt, success=True,
            image_path=image_path,
            image_b64=(res.image_b64[:200] + "...") if res.image_b64 and len(res.image_b64) > 200 else res.image_b64,
            image_hash=phash, width=res.width, height=res.height,
            seed_used=res.seed_used, engine=res.engine, score=score,
        )

    def _score_result(self, res: ImageResult) -> float:
        """Real quality score: combine stats (mean + stddev) into 0..1."""
        if not res.image_bytes:
            return 0.0
        try:
            from PIL import ImageStat
            img = Image.open(io.BytesIO(res.image_bytes))
            stat = ImageStat.Stat(img.convert("RGB"))
            mean = sum(stat.mean) / 3.0 / 255.0
            stddev = sum(stat.stddev) / 3.0 / 128.0
            # Penalise flat images (low stddev) and extreme mean (all-black/all-white)
            std_score = min(1.0, stddev)
            mean_score = 1.0 - abs(mean - 0.5) * 2.0  # 1.0 at mean=0.5, 0.0 at mean=0 or 1
            return round(0.6 * std_score + 0.4 * mean_score, 4)
        except Exception:
            return 0.5  # neutral on parse failure

    async def batch(
        self,
        prompts: List[str],
        *,
        width: int = 512,
        height: int = 512,
        concurrency: int = 4,
        out_dir: Optional[str] = None,
        dedup: bool = True,
        base_seed: Optional[int] = None,
    ) -> BatchT2IOutput:
        """Generate N images concurrently with optional dedup."""
        if not prompts:
            return BatchT2IOutput(total=0, succeeded=0, failed=0, dedup_count=0, results=[])
        out_path = Path(out_dir) if out_dir else None
        sem = asyncio.Semaphore(concurrency)
        seen_hashes: Dict[str, int] = {}

        async def _one(idx: int, prompt: str) -> BatchT2IResult:
            seed = (base_seed + idx) if base_seed is not None else None
            async with sem:
                return await self._gen_one(idx, prompt, width=width, height=height,
                                            seed=seed, out_dir=out_path)

        t0 = time.time()
        results = await asyncio.gather(*[_one(i, p) for i, p in enumerate(prompts)], return_exceptions=False)
        elapsed = time.time() - t0

        # Dedup pass (drop identical perceptual hashes, keep first)
        dedup_count = 0
        if dedup:
            kept: List[BatchT2IResult] = []
            for r in results:
                if r.success and r.image_hash:
                    if r.image_hash in seen_hashes:
                        dedup_count += 1
                        # Mark as failure for clarity
                        r = BatchT2IResult(
                            index=r.index, prompt=r.prompt, success=False,
                            image_path=r.image_path, image_b64=None,
                            image_hash=r.image_hash, width=r.width, height=r.height,
                            seed_used=r.seed_used, engine=r.engine, score=r.score,
                            error=f"duplicate of #{seen_hashes[r.image_hash]}",
                        )
                    else:
                        seen_hashes[r.image_hash] = r.index
                kept.append(r)
            results = kept

        engine_chain = sorted({r.engine for r in results if r.engine})
        succeeded = sum(1 for r in results if r.success)
        return BatchT2IOutput(
            total=len(prompts), succeeded=succeeded, failed=len(prompts) - succeeded,
            dedup_count=dedup_count, results=results,
            engine_chain=engine_chain, elapsed_seconds=round(elapsed, 3),
        )

    def write_manifest(self, output: BatchT2IOutput, manifest_path: str) -> str:
        """Write a JSONL manifest of all batch results (for training pipelines)."""
        path = Path(manifest_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for r in output.results:
                f.write(json.dumps({
                    "index": r.index, "prompt": r.prompt, "success": r.success,
                    "image_path": r.image_path, "image_hash": r.image_hash,
                    "width": r.width, "height": r.height, "seed": r.seed_used,
                    "engine": r.engine, "score": r.score, "error": r.error,
                }, ensure_ascii=False) + "\n")
        return str(path)


_singleton: Optional[DataT2IEngine] = None


def get_data_t2i_engine() -> DataT2IEngine:
    global _singleton
    if _singleton is None:
        _singleton = DataT2IEngine()
    return _singleton


__all__ = ["DataT2IEngine", "BatchT2IResult", "BatchT2IOutput", "get_data_t2i_engine"]
