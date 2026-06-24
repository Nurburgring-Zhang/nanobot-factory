"""
Image Processing Pipeline — 复刻 Penguin Canvas routes/imageOps.js
====================================================================
图像 resize / crop / grid-compose / compare / 各种 sharp 操作
"""
import os
import re
import math
import time
import uuid
from typing import Optional, List, Dict, Any, Tuple
from io import BytesIO
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import logging

logger = logging.getLogger(__name__)

from config.global_config import (
    OUTPUT_DIR, INPUT_DIR, SETTINGS_FILE,
    DEFAULT_RESOURCE_LIBRARY_DIR, RESOURCE_LIBRARY_DB,
)

router = APIRouter(prefix="/imdf/image", tags=["image_ops"])

# ─── SVG 工具 ───────────────────────────────────────────────────────────────

def _escape_svg(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def _make_index_badge(index: int) -> bytes:
    text = str(index)
    w = max(26, 18 + len(text) * 8)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="24" viewBox="0 0 {w} 24">'
        f'<rect x="0.5" y="0.5" width="{w-1}" height="23" rx="6" fill="rgba(17,24,39,.78)" stroke="rgba(255,255,255,.74)"/>'
        f'<text x="{w/2}" y="16" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#fff7ed">{text}</text>'
        f'</svg>'
    )
    return svg.encode("utf-8")


def _make_caption_bar(caption: str, width: int, height: int,
                       text_color: str = "#fff7ed", bg_color: str = "#111827") -> bytes:
    text = _escape_svg(str(caption or "")[:80])
    font_size = max(12, min(34, int(height * 0.42)))
    max_text_w = max(1, width - 24)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="{bg_color}"/>'
        f'<text x="{width/2}" y="{round(height/2 + font_size*0.34)}" text-anchor="middle" '
        f'font-family="Arial,\'Microsoft YaHei\',sans-serif" font-size="{font_size}" '
        f'font-weight="700" fill="{text_color}" textLength="{max_text_w}" lengthAdjust="spacingAndGlyphs">{text}</text>'
        f'</svg>'
    )
    return svg.encode("utf-8")


def _hex_color(v: str, fallback: str = "#111827") -> str:
    s = str(v or "").strip()
    if re.match(r"^#[0-9a-f]{3}$", s, re.I) or re.match(r"^#[0-9a-f]{6}$", s, re.I):
        return s
    return fallback


# ═══════════════════════════════════════════════════════════════════════════════
# 图片获取/保存
# ═══════════════════════════════════════════════════════════════════════════════

async def _fetch_image(source_url: str) -> bytes:
    """从 URL 或本地路径获取图片"""
    if not source_url:
        raise ValueError("imageUrl 为空")
    # 本地路径
    local = _resolve_local(source_url)
    if local and os.path.exists(local):
        with open(local, "rb") as f:
            return f.read()
    # data URI
    dm = re.match(r"^data:image/[a-z+]+;base64,(.+)$", source_url, re.I)
    if dm:
        return __import__("base64").b64decode(dm.group(1))
    # 远端
    if re.match(r"^https?://", source_url, re.I):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(source_url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
    # 资源库
    m = re.match(r"^/imdf/library/file/([^/?#]+)", source_url)
    if m:
        local2 = _resolve_library_item(m.group(1))
        if local2:
            with open(local2, "rb") as f:
                return f.read()
    raise ValueError(f"无法解析图像源: {source_url[:80]}")


def _resolve_local(url: str) -> Optional[str]:
    """解析本地 URL 到文件路径"""
    if not url:
        return None
    clean = url.split("?")[0].split("#")[0]
    mounts = [
        ("/imdf/media/output/", OUTPUT_DIR),
        ("/imdf/media/input/", INPUT_DIR),
        ("/imdf/media/", OUTPUT_DIR),
    ]
    for prefix, directory in mounts:
        if clean.startswith(prefix):
            rel = clean[len(prefix):].lstrip("/")
            fp = os.path.normpath(os.path.join(directory, rel))
            if fp.startswith(os.path.normpath(directory)):
                return fp
    return None


def _resolve_library_item(item_id: str) -> Optional[str]:
    """从资源库查找文件路径"""
    root = _get_library_root()
    if not root:
        return None
    db_path = os.path.join(root, RESOURCE_LIBRARY_DB)
    if not os.path.exists(db_path):
        return None
    try:
        with open(db_path, "r") as f:
            db = json.load(f)
        items = db.get("items", [])
        item = next((x for x in items if x.get("id") == item_id), None)
        if item and item.get("fileRel"):
            return _assert_inside(root, os.path.join(root, item["fileRel"]))
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return None


def _get_library_root() -> str:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                s = json.load(f)
            root = str(s.get("resourceLibraryPath", "")).strip()
            if root:
                return root
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return DEFAULT_RESOURCE_LIBRARY_DIR if os.path.exists(DEFAULT_RESOURCE_LIBRARY_DIR) else ""


def _assert_inside(base: str, target: str) -> str:
    b = os.path.realpath(base)
    t = os.path.realpath(target)
    if t != b and not t.startswith(b + os.sep):
        raise ValueError("路径越界")
    return t


def _save_result(buf: bytes, ext: str = "png") -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fname = f"op_{int(time.time()*1000)}_{uuid.uuid4().hex[:4]}.{ext}"
    fpath = os.path.join(OUTPUT_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(buf)
    return f"/imdf/media/output/{fname}"


def _clamp(v, lo, hi, fallback):
    try:
        n = int(v)
        return max(lo, min(hi, n))
    except (TypeError, ValueError):
        return fallback


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class ResizeRequest(BaseModel):
    image_url: str = ""
    width: int = 1024
    height: int = 1024
    fit: str = "contain"  # contain / cover / fill


class CropRequest(BaseModel):
    image_url: str = ""
    left: int = 0
    top: int = 0
    width: int = 512
    height: int = 512


class GridCell(BaseModel):
    image_url: str = ""
    caption: str = ""


class GridComposeRequest(BaseModel):
    rows: int = 3
    cols: int = 3
    width: int = 1200
    height: int = 1200
    gap: int = 0
    background: str = "#111827"
    fit: str = "adaptive"
    show_indexes: bool = False
    show_captions: bool = False
    caption_height: int = 56
    caption_text_color: str = "#fff7ed"
    caption_background: str = "#111827"
    cells: List[GridCell] = []


class CompareRequest(BaseModel):
    image_url_a: str = ""
    image_url_b: str = ""
    width: int = 1024
    height: int = 1024
    align: str = "contain"
    compare_mode: str = "slider"  # slider/side-by-side/overlay/blink/heatmap/focus
    threshold: int = 24
    opacity: float = 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/image/resize
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/resize")
async def resize_image(req: ResizeRequest):
    buf = await _fetch_image(req.image_url)
    img = Image.open(BytesIO(buf))
    img = img.convert("RGBA")
    w = _clamp(req.width, 16, 8192, img.width)
    h = _clamp(req.height, 16, 8192, img.height)
    fit = req.fit if req.fit in ("contain", "cover", "fill") else "contain"

    if fit == "fill":
        resized = img.resize((w, h), Image.LANCZOS)
    elif fit == "cover":
        ratio = max(w / img.width, h / img.height)
        new_w = round(img.width * ratio)
        new_h = round(img.height * ratio)
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        resized = resized.crop((left, top, left + w, top + h))
    else:  # contain
        resized = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img.thumbnail((w, h), Image.LANCZOS)
        x = (w - img.width) // 2
        y = (h - img.height) // 2
        resized.paste(img, (x, y), img)

    out_buf = BytesIO()
    resized.save(out_buf, "PNG")
    url = _save_result(out_buf.getvalue(), "png")
    return {"success": True, "data": {"url": url, "width": w, "height": h}}


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/image/crop
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/crop")
async def crop_image(req: CropRequest):
    buf = await _fetch_image(req.image_url)
    img = Image.open(BytesIO(buf)).convert("RGBA")
    l = max(0, min(req.left, img.width - 1))
    t = max(0, min(req.top, img.height - 1))
    w = max(1, min(req.width, img.width - l))
    h = max(1, min(req.height, img.height - t))
    cropped = img.crop((l, t, l + w, t + h))
    out_buf = BytesIO()
    cropped.save(out_buf, "PNG")
    url = _save_result(out_buf.getvalue(), "png")
    return {"success": True, "data": {"url": url, "width": w, "height": h}}


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/image/grid-compose
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/grid-compose")
async def grid_compose(req: GridComposeRequest):
    rows = _clamp(req.rows, 1, 12, 3)
    cols = _clamp(req.cols, 1, 12, 3)
    width = _clamp(req.width, 64, 4096, 1200)
    height = _clamp(req.height, 64, 4096, 1200)
    gap = max(0, min(160, req.gap))
    bg = _hex_color(req.background)
    caption_h = _clamp(req.caption_height, 24, 240, 56)

    content_w = width - gap * max(0, cols - 1)
    content_h = height - gap * max(0, rows - 1)
    if content_w < cols or content_h < rows:
        raise HTTPException(status_code=400, detail="宫格间距过大")

    col_widths = _distribute(content_w, cols)
    row_heights = _distribute(content_h, rows)
    col_lefts = [sum(col_widths[:i]) + i * gap for i in range(cols)]
    row_tops = [sum(row_heights[:i]) + i * gap for i in range(rows)]

    result = Image.new("RGBA", (width, height), _hex_to_rgb(bg))
    total_cells = rows * cols
    cells = req.cells[:total_cells]

    for idx in range(total_cells):
        if idx >= len(cells) or not cells[idx].image_url:
            continue
        row, col = divmod(idx, cols)
        cw, ch = col_widths[col], row_heights[row]
        try:
            cell_buf = await _fetch_image(cells[idx].image_url)
        except Exception:
            continue
        cell_img = Image.open(BytesIO(cell_buf)).convert("RGBA")

        has_caption = req.show_captions and cells[idx].caption and ch >= 32
        cap_h = min(caption_h, max(16, int(ch * 0.45)), ch - 1) if has_caption else 0
        img_h = max(1, ch - cap_h)

        # 缩放
        cell_fit = "contain"
        if cell_fit == "cover":
            cell_img_resized = _cover_resize(cell_img, cw, img_h)
        else:
            cell_img_resized = Image.new("RGBA", (cw, img_h), (0, 0, 0, 0))
            cell_img.thumbnail((cw, img_h), Image.LANCZOS)
            cell_img_resized.paste(cell_img, ((cw - cell_img.width) // 2, (img_h - cell_img.height) // 2), cell_img)

        if has_caption:
            composite = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            composite.paste(cell_img_resized, (0, 0))
            cap_bar = _render_caption_bar(cells[idx].caption, cw, cap_h,
                                          _hex_color(req.caption_text_color, "#fff7ed"),
                                          _hex_color(req.caption_background, "#111827"))
            composite.paste(cap_bar, (0, img_h))
        else:
            composite = cell_img_resized

        if req.show_indexes:
            badge = _render_index_badge(idx + 1)
            composite.paste(badge, (6, 6), badge)

        result.paste(composite, (col_lefts[col], row_tops[row]), composite)

    out_buf = BytesIO()
    result.save(out_buf, "PNG")
    url = _save_result(out_buf.getvalue(), "png")
    return {"success": True, "data": {"url": url, "width": width, "height": height}}


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/image/compare
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/compare")
async def compare_images(req: CompareRequest):
    buf_a = await _fetch_image(req.image_url_a)
    buf_b = await _fetch_image(req.image_url_b)
    w = _clamp(req.width, 64, 4096, 1024)
    h = _clamp(req.height, 64, 4096, 1024)
    align = req.align if req.align in ("contain", "cover", "fill") else "contain"
    mode = req.compare_mode
    threshold = max(1, min(255, req.threshold or 24))

    img_a = Image.open(BytesIO(buf_a)).convert("RGBA")
    img_b = Image.open(BytesIO(buf_b)).convert("RGBA")
    img_a_resized = _resize_to(img_a, w, h, align)
    img_b_resized = _resize_to(img_b, w, h, align)

    if mode == "side-by-side":
        combined = Image.new("RGBA", (w * 2, h))
        combined.paste(img_a_resized, (0, 0))
        combined.paste(img_b_resized, (w, 0))
        buf = _pil_to_bytes(combined)
        url = _save_result(buf, "png")
        return {"success": True, "data": {"url": url, "width": w * 2, "height": h}}

    if mode == "blink":
        # 返回两个 URL，前端交替显示
        url_a = _save_result(_pil_to_bytes(img_a_resized), "png")
        url_b = _save_result(_pil_to_bytes(img_b_resized), "png")
        return {"success": True, "data": {"urlA": url_a, "urlB": url_b, "width": w, "height": h}}

    if mode == "heatmap":
        diff = _heatmap_image(img_a_resized, img_b_resized, threshold)
        buf = _pil_to_bytes(diff)
        url = _save_result(buf, "png")
        return {"success": True, "data": {"url": url, "width": w, "height": h}}

    if mode == "focus":
        diff = _focus_image(img_a_resized, img_b_resized, threshold)
        buf = _pil_to_bytes(diff)
        url = _save_result(buf, "png")
        return {"success": True, "data": {"url": url, "width": w, "height": h}}

    # 默认: overlay
    blended = Image.blend(img_a_resized, img_b_resized, _clamp(req.opacity, 0, 1, 0.5))
    buf = _pil_to_bytes(blended)
    url = _save_result(buf, "png")
    return {"success": True, "data": {"url": url, "width": w, "height": h}}


# ═══════════════════════════════════════════════════════════════════════════════
# 内部作图函数
# ═══════════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (255,) if len(h) == 6 else (17, 24, 39, 255)


def _distribute(total: int, count: int) -> List[int]:
    base = total // count
    rest = total - base * count
    return [base + (1 if i < rest else 0) for i in range(count)]


def _resize_to(img: Image.Image, w: int, h: int, fit: str) -> Image.Image:
    if fit == "fill":
        return img.resize((w, h), Image.LANCZOS)
    if fit == "cover":
        return _cover_resize(img, w, h)
    result = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.thumbnail((w, h), Image.LANCZOS)
    result.paste(img, ((w - img.width) // 2, (h - img.height) // 2), img)
    return result


def _cover_resize(img: Image.Image, w: int, h: int) -> Image.Image:
    ratio = max(w / img.width, h / img.height)
    new = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)
    left = (new.width - w) // 2
    top = (new.height - h) // 2
    return new.crop((left, top, left + w, top + h))


def _render_index_badge(index: int) -> Image.Image:
    svg_bytes = _make_index_badge(index)
    from io import BytesIO
    return Image.open(BytesIO(svg_bytes)).convert("RGBA")


def _render_caption_bar(text: str, w: int, h: int, text_color: str, bg_color: str) -> Image.Image:
    svg_bytes = _make_caption_bar(text, w, h, text_color, bg_color)
    return Image.open(BytesIO(svg_bytes)).convert("RGBA")


def _heatmap_image(img_a: Image.Image, img_b: Image.Image, threshold: int) -> Image.Image:
    pa = img_a.load()
    pb = img_b.load()
    out = Image.new("RGBA", img_a.size)
    po = out.load()
    w, h = img_a.size
    for y in range(h):
        for x in range(w):
            ra, ga, ba, aa = pa[x, y]
            rb, gb, bb, ab = pb[x, y]
            diff = (abs(ra - rb) + abs(ga - gb) + abs(ba - bb)) / 3
            intensity = max(0, min(1, (diff - threshold) / max(1, 255 - threshold)))
            if diff < threshold:
                mix = 0
            else:
                mix = max(0.3, intensity * 0.82)
            hr, hg, hb = 255, round(232 * (1 - intensity) + 48 * intensity), round(60 * (1 - intensity))
            base_mix = 0.86 if diff < threshold else 0.62
            out_r = round(ra * base_mix * (1 - mix) + hr * mix)
            out_g = round(ga * base_mix * (1 - mix) + hg * mix)
            out_b = round(ba * base_mix * (1 - mix) + hb * mix)
            po[x, y] = (min(255, out_r), min(255, out_g), min(255, out_b), 255)
    return out


def _focus_image(img_a: Image.Image, img_b: Image.Image, threshold: int) -> Image.Image:
    pa = img_a.load()
    pb = img_b.load()
    out = Image.new("RGBA", img_a.size)
    po = out.load()
    w, h = img_a.size
    for y in range(h):
        for x in range(w):
            ra, ga, ba, aa = pa[x, y]
            rb, gb, bb, ab = pb[x, y]
            diff = (abs(ra - rb) + abs(ga - gb) + abs(ba - bb)) / 3
            if diff < threshold:
                gray = ra * 0.299 + ga * 0.587 + ba * 0.114
                po[x, y] = (round(gray * 0.58), round(gray * 0.58), round(gray * 0.58), 255)
            else:
                intensity = max(0, min(1, (diff - threshold) / max(1, 255 - threshold)))
                mix = max(0.18, intensity * 0.36)
                out_r = round(rb * (1 - mix) + 255 * mix)
                out_g = round(gb * (1 - mix) + 148 * mix)
                out_b = round(bb * (1 - mix) + 36 * mix)
                po[x, y] = (min(255, out_r), min(255, out_g), min(255, out_b), 255)
    return out


def _pil_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()
