"""eval.video_quality — Video quality assessment (heuristic).

Inputs: items where each item is either a video path/bytes OR a dict with
optional extracted metadata:
    {path, width, height, fps, duration, frames?, codec?}

If frames are NOT provided we return None for frame-derived metrics but
still report resolution / fps / duration / codec.

Metrics (0.0 - 1.0 unless noted):
  - resolution_score: width * height vs reference (default 1280*720 = 1.0)
  - fps_score: clip(avg_fps / 30, 0, 1)
  - bitrate_score: bitrate / 5 Mbps normalized
  - sharpness_score: avg laplacian variance of sampled frames
  - stability_score: 1 - std of inter-frame diff
  - black_ratio: avg black-frame ratio
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List


def _try_pil_from_frame(frame: Any):
    try:
        from PIL import Image
        import numpy as np
        if isinstance(frame, (bytes, bytearray)):
            return Image.open(io.BytesIO(frame)).convert("L")
        if isinstance(frame, str):
            return Image.open(frame).convert("L")
        if isinstance(frame, np.ndarray):
            return Image.fromarray(frame.astype("uint8")).convert("L")
    except Exception:  # noqa: BLE001
        return None
    return None


def _frame_diff_std(frames: List[Any]) -> float:
    """Average inter-frame absolute diff std (0 = identical)."""
    import numpy as np
    prev = None
    diffs = []
    for f in frames[:32]:
        im = _try_pil_from_frame(f)
        if im is None:
            continue
        a = np.asarray(im, dtype=np.float32) / 255.0
        if prev is not None and prev.shape == a.shape:
            diffs.append(float(np.abs(prev - a).mean()))
        prev = a
    if not diffs:
        return 0.0
    return float(np.std(diffs))


def _black_ratio(frames: List[Any]) -> float:
    vals: List[float] = []
    for f in frames[:32]:
        im = _try_pil_from_frame(f)
        if im is None:
            continue
        import numpy as np
        a = np.asarray(im, dtype=np.float32) / 255.0
        vals.append(float((a < 0.05).mean()))
    return float(sum(vals) / max(1, len(vals)))


def _sharpness(frames: List[Any]) -> float:
    import numpy as np
    vals: List[float] = []
    for f in frames[:16]:
        im = _try_pil_from_frame(f)
        if im is None:
            continue
        a = np.asarray(im, dtype=np.float32)
        h, w = a.shape
        if h < 3 or w < 3:
            continue
        lap = (
            a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4 * a[1:-1, 1:-1]
        )
        vals.append(float(lap.var()))
    return float(sum(vals) / max(1, len(vals)))


def _score_one(item: Any) -> Dict[str, Any]:
    width = height = fps = duration = bitrate_kbps = None
    frames: List[Any] = []
    codec = ""
    if isinstance(item, dict):
        width = item.get("width")
        height = item.get("height")
        fps = item.get("fps")
        duration = item.get("duration")
        bitrate_kbps = item.get("bitrate_kbps")
        frames = item.get("frames") or []
        codec = item.get("codec", "")
    elif isinstance(item, (bytes, bytearray)):
        # can't extract without ffmpeg; return partial
        pass
    # Resolution
    res_score = 0.0
    if width and height:
        pixels = width * height
        ref = 1280 * 720
        res_score = max(0.0, min(1.0, pixels / ref))
    fps_score = 0.0
    if fps:
        fps_score = max(0.0, min(1.0, float(fps) / 30.0))
    bitrate_score = 0.0
    if bitrate_kbps:
        bitrate_score = max(0.0, min(1.0, float(bitrate_kbps) / 5000.0))
    stab = _frame_diff_std(frames) if frames else None
    stability_score = (max(0.0, 1.0 - stab * 4.0) if stab is not None else None)
    sharpness_v = _sharpness(frames) if frames else None
    sharpness_score = (
        max(0.0, min(1.0, sharpness_v / 400.0)) if sharpness_v is not None else None
    )
    blk = _black_ratio(frames) if frames else None
    # composite
    present = [v for v in (res_score, fps_score, bitrate_score,
                           stability_score, sharpness_score) if v is not None]
    composite = sum(present) / max(1, len(present)) if present else 0.0
    return {
        "resolution": {"w": width, "h": height, "score": round(res_score, 3)},
        "fps": {"value": fps, "score": round(fps_score, 3)},
        "bitrate": {"kbps": bitrate_kbps, "score": round(bitrate_score, 3)},
        "stability": {"std": stab, "score": round(stability_score, 3) if stability_score is not None else None},
        "sharpness": {"var": sharpness_v, "score": round(sharpness_score, 3) if sharpness_score is not None else None},
        "black_ratio": blk,
        "duration": duration,
        "codec": codec,
        "composite": round(composite, 3),
    }


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.5))
    out: List[Dict[str, Any]] = []
    composites: List[float] = []
    for i, it in enumerate(items):
        s = _score_one(it)
        composites.append(s["composite"])
        out.append({"sample_id": i, "video_quality": s,
                    "above_threshold": s["composite"] >= threshold})
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        out = [{
            "count": len(composites),
            "composite_mean": round(sum(composites) / max(1, len(composites)), 3),
        }]
    return out


__all__ = ["run"]
