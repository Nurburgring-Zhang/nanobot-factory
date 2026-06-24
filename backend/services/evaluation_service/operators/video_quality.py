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


def _detect_format(buf: bytes) -> str:
    """Best-effort container detection from the leading bytes.

    Returns one of: ``"mp4"``, ``"mov"``, ``"webm"``, ``"avi"``, ``"flv"``,
    ``"mkv"``, ``"mpeg_ps"``, ``"3gp"``, ``"unknown"``.
    """
    if not buf or len(buf) < 12:
        return "unknown"
    if buf[4:8] == b"ftyp":
        brand = buf[8:12].decode("ascii", errors="replace").lower()
        if brand in ("qt  ", "qt"):
            return "mov"
        return "mp4"
    if buf[:4] == b"\x1aE\xdf\xa3":
        # EBML header — webm vs mkv is decided by DocType element.
        # DocType ID = 0x4282, encoded as VINT (1 byte for IDs < 0x80).
        # Look for the byte sequence 0x42 0x82 in the first 64 bytes.
        head = buf[:64]
        idx = head.find(b"\x42\x82")
        if idx >= 0 and idx + 2 < len(head):
            size_byte = head[idx + 2]
            if size_byte & 0x80:
                length = size_byte & 0x7F
            else:
                length = 1
            start = idx + 3
            doctype = head[start:start + length].decode("ascii", errors="replace").lower()
            if doctype == "webm":
                return "webm"
            if doctype == "matroska":
                return "mkv"
        return "mkv"
    if buf[:3] == b"FLV":
        return "flv"
    if buf[:4] == b"RIFF" and buf[8:12] == b"AVI ":
        return "avi"
    if buf[:2] == b"\x00\x00" and buf[2] in (0x01, 0x02):
        return "mpeg_ps"
    if buf[4:8] == b"moov":
        return "mp4"
    if buf[:4] == b"OggS":
        return "ogg"
    if buf[:3] == b"\x00\x00\x00" and buf[3] == 0x18:
        return "3gp"
    return "unknown"


def _parse_mp4_mvhd_duration(buf: bytes) -> Optional[float]:
    """Find the ``mvhd`` box in an MP4/MOV stream and return duration in seconds.

    Returns ``None`` when the buffer is not a parseable MP4 or the box is
    missing.  Lightweight — handles boxes in the first 1 MB only.
    """
    if len(buf) < 32 or buf[4:8] != b"ftyp":
        return None
    offset = 0
    end = min(len(buf), 1 << 20)  # 1 MB cap
    # Skip the ftyp box first
    try:
        size = int.from_bytes(buf[0:4], "big")
        offset = size if size >= 8 else 8
    except Exception:  # noqa: BLE001
        return None
    while offset + 8 < end:
        try:
            size = int.from_bytes(buf[offset:offset + 4], "big")
            box_type = buf[offset + 4:offset + 8]
        except Exception:  # noqa: BLE001
            return None
        if size < 8:
            return None
        if box_type == b"moov":
            # Walk into moov to find mvhd
            inner_end = min(offset + size, end)
            inner = offset + 8
            while inner + 8 < inner_end:
                try:
                    isize = int.from_bytes(buf[inner:inner + 4], "big")
                    itype = buf[inner + 4:inner + 8]
                except Exception:  # noqa: BLE001
                    return None
                if itype == b"mvhd":
                    mvhd_start = inner + 8
                    if mvhd_start + 4 >= inner + isize:
                        return None
                    version = buf[mvhd_start]
                    if version == 1:
                        if mvhd_start + 8 + 8 + 8 + 4 > inner + isize:
                            return None
                        timescale = int.from_bytes(
                            buf[mvhd_start + 8 + 8 + 8:mvhd_start + 8 + 8 + 8 + 4],
                            "big",
                        )
                        dur_ticks = int.from_bytes(
                            buf[mvhd_start + 8 + 8 + 8 + 4:mvhd_start + 8 + 8 + 8 + 4 + 8],
                            "big",
                        )
                    else:
                        if mvhd_start + 4 + 4 + 4 + 4 > inner + isize:
                            return None
                        timescale = int.from_bytes(
                            buf[mvhd_start + 4 + 4 + 4:mvhd_start + 4 + 4 + 4 + 4],
                            "big",
                        )
                        dur_ticks = int.from_bytes(
                            buf[mvhd_start + 4 + 4 + 4 + 4:mvhd_start + 4 + 4 + 4 + 4 + 4],
                            "big",
                        )
                    if timescale <= 0:
                        return None
                    return float(dur_ticks) / float(timescale)
                if isize < 8:
                    return None
                inner += isize
            return None
        if size == 0:
            return None
        offset += size
    return None


def _score_one(item: Any) -> Dict[str, Any]:
    width = height = fps = duration = bitrate_kbps = None
    frames: List[Any] = []
    codec = ""
    source_format = ""
    extraction_note = ""
    if isinstance(item, dict):
        width = item.get("width")
        height = item.get("height")
        fps = item.get("fps")
        duration = item.get("duration")
        bitrate_kbps = item.get("bitrate_kbps")
        frames = item.get("frames") or []
        codec = item.get("codec", "")
    elif isinstance(item, (bytes, bytearray)):
        # Best-effort header parse — we cannot run ffmpeg in-process here, but
        # we can identify the container and (for MP4/MOV) extract the mvhd
        # timescale+duration to recover duration without external tools.
        buf = bytes(item)
        source_format = _detect_format(buf)
        if source_format in ("mp4", "mov"):
            duration = _parse_mp4_mvhd_duration(buf)
            extraction_note = (
                "extracted_from_mp4_header_only; "
                "resolution/codec/fps require ffmpeg sidecar"
            )
        else:
            extraction_note = (
                f"format={source_format}; "
                "duration/resolution/codec require ffmpeg sidecar"
            )
    elif isinstance(item, str) and item:
        # filesystem path — cannot probe without ffmpeg either, but at least
        # record the path so the caller can run a sidecar probe.
        extraction_note = "path_only; run ffmpeg sidecar to fill metadata"
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
        "source_format": source_format,
        "extraction_note": extraction_note,
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
