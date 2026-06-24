"""
Media File Management — 复刻 Penguin Canvas routes/files.js
=============================================================
File upload/下载/缩略图/鸭鸭解码/磁盘保存
"""
import os
import re
import json
import hashlib
import uuid
import time
import struct
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from io import BytesIO

import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Query
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

from config.global_config import (
    INPUT_DIR, OUTPUT_DIR, THUMBNAILS_DIR, THUMBNAIL_SIZE,
    THUMBNAIL_QUALITY, THUMBNAIL_CONCURRENCY,
    MAX_UPLOAD_BYTES, MAX_BASE64_BYTES, MAX_DUCK_BATCH,
    DEFAULT_LOCAL_SAVE_DIR, SETTINGS_FILE, MIME_BY_EXT,
)

# ─── 路由注册 ───────────────────────────────────────────────────────────────
router = APIRouter(prefix="/imdf/media", tags=["media"])

# ─── 缩略图并发控制 ────────────────────────────────────────────────────────
_thumbnail_semaphore = __import__("asyncio").Semaphore(THUMBNAIL_CONCURRENCY)
_thumbnail_cache = {}  # { cache_path: asyncio.Future }

# ─── 正则 ───────────────────────────────────────────────────────────────────
THUMBNAIL_IMAGE_PATTERN = re.compile(r'\.(png|jpe?g|webp|gif|bmp|avif|tiff?)(?:$|\?)', re.I)

# ═══════════════════════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════════════════════

def _format_size_label(bytes_: int) -> str:
    mb = bytes_ / (1024 * 1024)
    return f"{int(mb) if mb == int(mb) else round(mb, 1)}MB"


def _generate_internal_name(prefix: str = "up", ext: str = ".png") -> str:
    ts = int(time.time() * 1000)
    rand = uuid.uuid4().hex[:4]
    return f"{prefix}_{ts}_{rand}{ext}"


def _safe_duck_ext(ext: str) -> str:
    clean = re.sub(r'[^a-z0-9._+\-]', '', ext.strip().lower().lstrip('.'))
    return clean[:40] or 'bin'


def _resolve_local_file(url: str) -> Optional[str]:
    """把 /imdf/media/input/xxx 或 /imdf/media/output/xxx 解析为绝对路径"""
    if not url or not isinstance(url, str):
        return None
    clean = url.split('?')[0].split('#')[0]
    mounts = [
        ('/imdf/media/input/', INPUT_DIR),
        ('/imdf/media/output/', OUTPUT_DIR),
        ('/imdf/media/', OUTPUT_DIR),  # 兼容简写
    ]
    for prefix, directory in mounts:
        if clean.startswith(prefix):
            rel = clean[len(prefix):].lstrip('/')
            resolved = os.path.normpath(os.path.join(directory, rel))
            if resolved.startswith(os.path.normpath(directory)):
                return resolved
    return None


def _clamp_thumbnail_size(value) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return THUMBNAIL_SIZE
    return max(96, min(1024, v))


def _thumbnail_cache_path(source: str, size: int) -> str:
    """根据源文件的 size/mtime 生成缓存 key"""
    stat = os.stat(source)
    key = hashlib.sha1(
        f"{source}|{stat.st_size}|{int(stat.st_mtime * 1000)}|{size}".encode()
    ).hexdigest()[:28]
    os.makedirs(THUMBNAILS_DIR, exist_ok=True)
    return os.path.join(THUMBNAILS_DIR, f"preview_{size}_{key}.webp")


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/media/upload — 上传文件
# ═══════════════════════════════════════════════════════════════════════════════

class UploadResponse(BaseModel):
    filename: str
    url: str
    size: int
    mime: str


@router.post("/upload")
async def handle_upload(file: UploadFile = File(...)):
    """单File upload，存储在 input 目录"""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "error": f"文件超过上传上限 {_format_size_label(MAX_UPLOAD_BYTES)}，请压缩后重试",
                "limit": MAX_UPLOAD_BYTES,
            }
        )
    ext = os.path.splitext(file.filename or "file")[1] or ".png"
    name = _generate_internal_name("up", ext)
    dest = os.path.join(INPUT_DIR, name)
    with open(dest, "wb") as f:
        f.write(content)
    mime = file.content_type or MIME_BY_EXT.get(ext.lower(), "application/octet-stream")
    return {
        "success": True,
        "data": {
            "filename": name,
            "url": f"/imdf/media/input/{name}",
            "size": len(content),
            "mime": mime,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GET /imdf/media/list — 列出 output 目录
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/list")
async def list_output_files(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """列出 output 目录下的媒体文件"""
    if not os.path.exists(OUTPUT_DIR):
        return {"success": True, "data": [], "limit": limit, "offset": offset}
    pattern = re.compile(r'\.(png|jpe?g|webp|gif|mp4|webm|mp3|wav)$', re.I)
    files = []
    for fname in os.listdir(OUTPUT_DIR):
        if not pattern.search(fname):
            continue
        fpath = os.path.join(OUTPUT_DIR, fname)
        stat = os.stat(fpath)
        files.append({
            "filename": fname,
            "url": f"/imdf/media/output/{fname}",
            "size": stat.st_size,
            "mtime": int(stat.st_mtime * 1000),
        })
    if q:
        files = [f for f in files if q.lower() in f["filename"].lower()]
    files.sort(key=lambda x: x["mtime"], reverse=True)
    total = len(files)
    page = files[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/media/upload-base64 — 从 base64 dataURL 保存
# ═══════════════════════════════════════════════════════════════════════════════

class Base64UploadRequest(BaseModel):
    data_url: str = Field(..., description="data:image/...;base64,...")
    prefix: str = "draw"


@router.post("/upload-base64")
async def upload_base64(req: Base64UploadRequest):
    """base64 dataURL → 保存到 output 目录"""
    match = re.match(r'^data:image/(png|jpeg|jpg|webp);base64,(.+)$', req.data_url, re.I)
    if not match:
        raise HTTPException(status_code=400, detail="dataUrl 格式不支持")
    ext_raw = match.group(1).lower()
    ext = "png" if ext_raw == "jpeg" else ext_raw
    raw_data = match.group(2)
    try:
        buf = __import__("base64").b64decode(raw_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"base64 解码失败: {e}")
    if len(buf) > MAX_BASE64_BYTES:
        raise HTTPException(status_code=413, detail="base64 数据超过 20MB 限制")
    tag = re.sub(r'[^a-z0-9\-]', '', req.prefix)[:16] or "draw"
    name = f"{tag}_{int(time.time()*1000)}_{uuid.uuid4().hex[:4]}.{ext}"
    dest = os.path.join(OUTPUT_DIR, name)
    with open(dest, "wb") as f:
        f.write(buf)
    return {
        "success": True,
        "data": {
            "filename": name,
            "url": f"/imdf/media/output/{name}",
            "size": len(buf),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GET /imdf/media/thumbnail — 缩略图
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/thumbnail")
async def get_thumbnail(url: str, size: int = THUMBNAIL_SIZE):
    """为本地图片生成缩略图"""
    clean_url = url.strip()
    if not clean_url or not THUMBNAIL_IMAGE_PATTERN.search(clean_url.split('?')[0]):
        raise HTTPException(status_code=400, detail="不支持的图片预览地址")
    source = _resolve_local_file(clean_url)
    if not source:
        raise HTTPException(status_code=400, detail="只支持本地 input/output 图片缩略图")
    if not os.path.exists(source):
        raise HTTPException(status_code=404, detail="源图片不存在")
    thumb_size = _clamp_thumbnail_size(size)
    cache_path = _thumbnail_cache_path(source, thumb_size)

    # 缓存命中
    if os.path.exists(cache_path):
        return __import__("fastapi.responses", fromlist=["FileResponse"]).FileResponse(
            cache_path, media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    # 并发锁
    if cache_path in _thumbnail_cache:
        fut = _thumbnail_cache[cache_path]
        result = await fut
        return __import__("fastapi.responses", fromlist=["FileResponse"]).FileResponse(
            result, media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    async def _generate():
        try:
            import asyncio
            # 用 subprocess sharp 替代 (而不是 Python PIL, 保持与原版 sharp 一致)
            # 这里使用 Pillow 作为备选
            from PIL import Image
            img = Image.open(source)
            img = img.convert("RGB")
            img.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            img.save(cache_path, "WEBP", quality=THUMBNAIL_QUALITY)
            return cache_path
        except Exception:
            raise

    loop = __import__("asyncio").get_event_loop()
    fut = loop.create_future()
    _thumbnail_cache[cache_path] = fut
    try:
        async with _thumbnail_semaphore:
            result = await _generate()
            fut.set_result(result)
        return __import__("fastapi.responses", fromlist=["FileResponse"]).FileResponse(
            result, media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )
    except Exception as e:
        fut.set_exception(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _thumbnail_cache.pop(cache_path, None)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/media/duck-decode — 鸭鸭图解码
# ═══════════════════════════════════════════════════════════════════════════════

class DuckDecodeRequest(BaseModel):
    urls: List[str] = []


@router.post("/duck-decode")
async def duck_decode(req: DuckDecodeRequest):
    """尝试解码 SS_tools 无密码鸭鸭图"""
    if not req.urls:
        raise HTTPException(status_code=400, detail="缺少 urls")
    limited = req.urls[:MAX_DUCK_BATCH]
    items = []
    for i, source_url in enumerate(limited):
        try:
            fp = _resolve_local_file(source_url)
            if not fp or not os.path.exists(fp):
                items.append({"sourceUrl": source_url, "decoded": False, "reason": "local_file_not_found"})
                continue
            with open(fp, "rb") as f:
                buf = f.read()
            decoded = _try_decode_duck_payload(buf)
            if not decoded or not decoded.get("decoded") or not decoded.get("buffer"):
                items.append({
                    "sourceUrl": source_url, "decoded": False,
                    "isDuck": bool(decoded and decoded.get("isDuck")),
                    "passwordProtected": bool(decoded and decoded.get("passwordProtected")),
                    "reason": "password_protected" if (decoded and decoded.get("passwordProtected")) else "not_duck",
                })
                continue
            if decoded["kind"] not in ("image", "video", "audio"):
                items.append({"sourceUrl": source_url, "decoded": False, "isDuck": True, "reason": "unsupported_kind"})
                continue
            ext = _safe_duck_ext(decoded.get("ext", "bin"))
            fname = f"duck_{int(time.time()*1000)}_{i}_{uuid.uuid4().hex[:5]}.{ext}"
            dest = os.path.join(OUTPUT_DIR, fname)
            with open(dest, "wb") as f:
                f.write(decoded["buffer"])
            items.append({
                "sourceUrl": source_url, "decoded": True,
                "filename": fname,
                "url": f"/imdf/media/output/{fname}",
                "size": len(decoded["buffer"]),
                "kind": decoded["kind"],
                "mime": decoded.get("mime", ""),
                "originalExt": decoded.get("originalExt", ""),
                "ext": ext,
                "lsbBits": decoded.get("lsbBits", 0),
            })
        except Exception as e:
            items.append({"sourceUrl": source_url, "decoded": False, "reason": str(e)})
    return {
        "success": True,
        "data": {
            "items": items,
            "decodedCount": sum(1 for i in items if i.get("decoded")),
        },
    }


def _try_decode_duck_payload(data: bytes) -> Optional[Dict[str, Any]]:
    """简易鸭鸭图解码 (PNG LSB 隐写)"""
    # 这是一个 placeholder — 真正的 duck 解码需要 SS_tools 库
    # 这里实现基本的 PNG LSB 检测
    if len(data) < 32 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return {"decoded": False, "isDuck": False, "passwordProtected": False}
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        pixels = list(img.getdata())
        # LSB: 取前 16 像素的 B 通道 LSB 组成 magic
        magic_bits = []
        for i in range(min(16, len(pixels))):
            magic_bits.append(str(pixels[i][2] & 1))
        magic = "".join(magic_bits)
        if magic == "0111010000111000":  # "t8" 的 8-bit
            return {"decoded": True, "buffer": data, "kind": "image",
                    "ext": "png", "mime": "image/png", "originalExt": "png",
                    "lsbBits": 1, "isDuck": True, "passwordProtected": False}
        return {"decoded": False, "isDuck": False, "passwordProtected": False}
    except Exception:
        return {"decoded": False, "isDuck": False, "passwordProtected": False}


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/media/save-to-disk — 保存到本地路径
# ═══════════════════════════════════════════════════════════════════════════════

class SaveToDiskRequest(BaseModel):
    url: str
    filename: Optional[str] = None


@router.post("/save-to-disk")
async def save_to_disk(req: SaveToDiskRequest):
    """从 URL 保存文件到用户配置的本地路径"""
    if not req.url:
        raise HTTPException(status_code=400, detail="缺少 url")
    save_path = _load_save_path()
    if not save_path:
        raise HTTPException(status_code=400, detail="未配置 fileSavePath")
    os.makedirs(save_path, exist_ok=True)

    target = _infer_save_target(req.url, req.filename, save_path)
    if os.path.exists(target):
        return {"success": True, "data": {"path": target, "exist": True}}

    # 本地复制
    if req.url.startswith("/imdf/media/output/"):
        rel = req.url.replace("/imdf/media/output/", "")
        src = os.path.join(OUTPUT_DIR, rel)
        if not os.path.exists(src):
            raise HTTPException(status_code=404, detail=f"源文件不存在: {src}")
        __import__("shutil").copy2(src, target)
        return {"success": True, "data": {"path": target, "exist": False, "source": "copy"}}

    if req.url.startswith("/imdf/media/input/"):
        rel = req.url.replace("/imdf/media/input/", "")
        src = os.path.join(INPUT_DIR, rel)
        if not os.path.exists(src):
            raise HTTPException(status_code=404, detail=f"源文件不存在: {src}")
        __import__("shutil").copy2(src, target)
        return {"success": True, "data": {"path": target, "exist": False, "source": "copy"}}

    # 远端拉取
    if re.match(r'^https?://', req.url, re.I):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(req.url, follow_redirects=True)
                resp.raise_for_status()
                with open(target, "wb") as f:
                    f.write(resp.content)
            return {"success": True, "data": {"path": target, "exist": False, "source": "fetch"}}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"拉取远端资源出错: {e}")

    raise HTTPException(status_code=400, detail="不支持的 url 协议")


def _load_save_path() -> str:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                s = json.load(f)
            p = s.get("fileSavePath", "").strip()
            if p:
                return p
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return DEFAULT_LOCAL_SAVE_DIR


def _infer_save_target(url: str, filename: Optional[str], base: str) -> str:
    if filename:
        safe = re.sub(r'[\\/:*?"<>|]', '_', filename)
        return os.path.join(base, safe)
    try:
        if url.startswith("http"):
            parsed = __import__("urllib.parse").urlparse(url)
            base_name = os.path.basename(parsed.path) or f"out_{int(time.time())}"
        else:
            base_name = os.path.basename(url.split('?')[0]) or f"out_{int(time.time())}"
        safe = re.sub(r'[\\/:*?"<>|]', '_', base_name)
        return os.path.join(base, safe)
    except Exception:
        return os.path.join(base, f"out_{int(time.time())}")
