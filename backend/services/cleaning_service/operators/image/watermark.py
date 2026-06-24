"""clean.image.watermark — detect / embed image watermark via imdf watermark_engine.

Reuses imdf.engines.watermark_engine.WatermarkEngine when available;
falls back to a noop with a note when unavailable.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List

from .._image_utils import _HAS_PIL, _load_image

try:
    from imdf.engines.watermark_engine import get_engine as _get_wm_engine
    _HAS_WM = True
except Exception:  # noqa: BLE001
    _HAS_WM = False


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Embed a text watermark into each image and return the bytes.

    params:
        text: str = "nanobot-factory"
        position: str = "bottom_right"
        opacity: float = 0.5
    """
    text = str(params.get("text", "nanobot-factory"))
    position = str(params.get("position", "bottom_right"))
    opacity = float(params.get("opacity", 0.5))
    out: List[Dict[str, Any]] = []
    if not _HAS_WM:
        return [{"item": x, "watermarked": False,
                 "note": "watermark_engine unavailable; pass-through"} for x in items]
    engine = _get_wm_engine()
    for x in items:
        try:
            img, _ = _load_image(x)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": str(e)})
            continue
        if img is None:
            out.append({"item": x, "error": "load_failed"})
            continue
        try:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            png_bytes = buf.getvalue()
            result = engine.add_image_watermark(
                source=png_bytes,
                text=text,
                position=position,
                opacity=opacity,
                output_format="png",
            )
            out.append({
                "item": x,
                "watermarked": True,
                "image_bytes": result if isinstance(result, (bytes, bytearray)) else None,
                "engine": "imdf.watermark_engine",
            })
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"watermark_failed: {e}"})
    return out