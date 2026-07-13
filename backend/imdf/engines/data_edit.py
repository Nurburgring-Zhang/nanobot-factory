"""P22-P2-real-fix-3-Engines — DataEditEngine (real image editing).

Real image editing operations using PIL (Pillow) — no external service
dependency. Supports crop, resize, color adjust, filter, composite,
mask-blend, and format conversion.

Public API:
- ``DataEditEngine.edit(image_bytes, ops=[...])`` — apply a list of ops
- ``DataEditEngine.composite(base_bytes, overlay_bytes, ...)`` — alpha blend
- ``DataEditEngine.thumbnail(bytes, size)`` — fast thumbnail
- ``DataEditEngine.to_format(bytes, target_format)`` — JPEG ↔ PNG ↔ WebP
"""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class EditOp:
    """Single edit operation."""
    op: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EditResult:
    success: bool
    image_bytes: Optional[bytes] = None
    image_b64: Optional[str] = None
    width: int = 0
    height: int = 0
    format: str = "PNG"
    ops_applied: List[str] = field(default_factory=list)
    engine: str = "data-edit-pil"
    error: str = ""


class DataEditEngine:
    """Real image edit engine. Pure-PIL, no external services."""

    SUPPORTED_OPS = {
        "resize", "crop", "rotate", "flip", "mirror",
        "grayscale", "invert", "autocontrast", "equalize",
        "blur", "sharpen", "edge", "emboss", "smooth",
        "brightness", "contrast", "saturation", "hue",
        "thumbnail", "pad", "watermark", "convert",
    }

    def edit(self, image_bytes: bytes, ops: List[EditOp]) -> EditResult:
        """Apply a list of edit ops in order."""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            applied: List[str] = []
            for op in ops:
                if op.op not in self.SUPPORTED_OPS:
                    return EditResult(success=False, error=f"unsupported op: {op.op}")
                img = self._apply(img, op)
                applied.append(op.op)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw = buf.getvalue()
            return EditResult(
                success=True, image_bytes=raw,
                image_b64=base64.b64encode(raw).decode(),
                width=img.width, height=img.height, format="PNG",
                ops_applied=applied,
            )
        except Exception as exc:  # noqa: BLE001
            return EditResult(success=False, error=f"{type(exc).__name__}: {exc}")

    def composite(self, base_bytes: bytes, overlay_bytes: bytes,
                  *, position: Tuple[int, int] = (0, 0),
                  alpha: float = 1.0) -> EditResult:
        """Alpha-blend overlay onto base at position."""
        try:
            base = Image.open(io.BytesIO(base_bytes)).convert("RGBA")
            overlay = Image.open(io.BytesIO(overlay_bytes)).convert("RGBA")
            if alpha < 1.0:
                # Adjust overlay alpha
                r, g, b, a = overlay.split()
                a = a.point(lambda p: int(p * alpha))
                overlay = Image.merge("RGBA", (r, g, b, a))
            base.alpha_composite(overlay, dest=position)
            buf = io.BytesIO()
            base.save(buf, format="PNG")
            raw = buf.getvalue()
            return EditResult(
                success=True, image_bytes=raw, image_b64=base64.b64encode(raw).decode(),
                width=base.width, height=base.height, format="PNG",
                ops_applied=["composite"],
            )
        except Exception as exc:  # noqa: BLE001
            return EditResult(success=False, error=f"{type(exc).__name__}: {exc}")

    def thumbnail(self, image_bytes: bytes, size: int = 128) -> EditResult:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw = buf.getvalue()
            return EditResult(
                success=True, image_bytes=raw, image_b64=base64.b64encode(raw).decode(),
                width=img.width, height=img.height, format="PNG",
                ops_applied=["thumbnail"],
            )
        except Exception as exc:  # noqa: BLE001
            return EditResult(success=False, error=f"{type(exc).__name__}: {exc}")

    def to_format(self, image_bytes: bytes, target_format: str) -> EditResult:
        target_format = target_format.upper()
        try:
            img = Image.open(io.BytesIO(image_bytes))
            buf = io.BytesIO()
            if target_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(buf, format=target_format)
            raw = buf.getvalue()
            return EditResult(
                success=True, image_bytes=raw, image_b64=base64.b64encode(raw).decode(),
                width=img.width, height=img.height, format=target_format,
                ops_applied=[f"convert:{target_format}"],
            )
        except Exception as exc:  # noqa: BLE001
            return EditResult(success=False, error=f"{type(exc).__name__}: {exc}")

    # ── Internal op dispatch ──────────────────────────────────────

    def _apply(self, img: Image.Image, op: EditOp) -> Image.Image:
        p = op.params
        if op.op == "resize":
            return img.resize((int(p.get("width", img.width)), int(p.get("height", img.height))), Image.LANCZOS)
        if op.op == "crop":
            return img.crop(tuple(p.get("box", (0, 0, img.width, img.height))))
        if op.op == "rotate":
            return img.rotate(float(p.get("degrees", 90)), expand=bool(p.get("expand", True)))
        if op.op == "flip":
            return ImageOps.flip(img)
        if op.op == "mirror":
            return ImageOps.mirror(img)
        if op.op == "grayscale":
            return img.convert("L")
        if op.op == "invert":
            return ImageOps.invert(img.convert("RGB"))
        if op.op == "autocontrast":
            return ImageOps.autocontrast(img, cutoff=float(p.get("cutoff", 0)))
        if op.op == "equalize":
            return ImageOps.equalize(img)
        if op.op == "blur":
            return img.filter(ImageFilter.GaussianBlur(radius=float(p.get("radius", 2))))
        if op.op == "sharpen":
            return img.filter(ImageFilter.SHARPEN)
        if op.op == "edge":
            return img.filter(ImageFilter.FIND_EDGES)
        if op.op == "emboss":
            return img.filter(ImageFilter.EMBOSS)
        if op.op == "smooth":
            return img.filter(ImageFilter.SMOOTH)
        if op.op == "brightness":
            return ImageEnhance.Brightness(img).enhance(float(p.get("factor", 1.5)))
        if op.op == "contrast":
            return ImageEnhance.Contrast(img).enhance(float(p.get("factor", 1.5)))
        if op.op == "saturation":
            return ImageEnhance.Color(img).enhance(float(p.get("factor", 1.5)))
        if op.op == "hue":
            hsv = img.convert("HSV")
            pixels = hsv.load()
            shift = int(p.get("shift", 30))
            for y in range(hsv.height):
                for x in range(hsv.width):
                    h_, s_, v_ = pixels[x, y]
                    pixels[x, y] = ((h_ + shift) % 256, s_, v_)
            return hsv.convert("RGB")
        if op.op == "thumbnail":
            size = int(p.get("size", 128))
            img.thumbnail((size, size), Image.LANCZOS)
            return img
        if op.op == "pad":
            color = p.get("color", (0, 0, 0))
            padding = int(p.get("padding", 20))
            new = Image.new(img.mode, (img.width + 2 * padding, img.height + 2 * padding), color)
            new.paste(img, (padding, padding))
            return new
        if op.op == "watermark":
            text = str(p.get("text", "©"))
            try:
                font = ImageFont.truetype("arial.ttf", int(p.get("size", 24)))
            except Exception:
                font = ImageFont.load_default()
            overlay = img.convert("RGBA")
            draw = ImageDraw.Draw(overlay)
            pos = p.get("position", (10, 10))
            draw.text(pos, text, fill=(255, 255, 255, 200), font=font)
            return overlay.convert("RGB")
        if op.op == "convert":
            return img.convert(p.get("mode", "RGB"))
        return img


_singleton: Optional[DataEditEngine] = None


def get_data_edit_engine() -> DataEditEngine:
    global _singleton
    if _singleton is None:
        _singleton = DataEditEngine()
    return _singleton


__all__ = ["DataEditEngine", "EditOp", "EditResult", "get_data_edit_engine"]
