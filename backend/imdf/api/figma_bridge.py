"""
Figma Bridge Connector — 复刻 Penguin Canvas routes/figma.js
==============================================================
发送素材到 Figma 插件
"""
import os
import re
import json
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

from config.global_config import (
    OUTPUT_DIR, INPUT_DIR, PORT, DEFAULT_FIGMA_BRIDGE_BASE,
)

router = APIRouter(prefix="/imdf/figma", tags=["figma"])

FIGMA_TIMEOUT = 8  # seconds


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class FigmaImportItem(BaseModel):
    id: str = ""
    kind: str = "image"
    url: str = ""
    text: str = ""
    name: str = ""


class FigmaImportRequest(BaseModel):
    figma_api_base: Optional[str] = None
    materials: List[FigmaImportItem] = []
    tags: Optional[List[str]] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Internal utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _sanitize_text(value, fallback="", maxlen=1000) -> str:
    return str(value or fallback).strip()[:maxlen]


def _assert_inside(root: str, target: str) -> str:
    r = os.path.realpath(root)
    t = os.path.realpath(target)
    if t != r and not t.startswith(r + os.sep):
        raise ValueError("路径越界")
    return t


def _normalize_local_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.match(r"^https?://", raw, re.I):
        try:
            parsed = urlparse(raw)
            host = parsed.hostname.lower()
            if host not in ("127.0.0.1", "localhost", "::1"):
                return ""
            return parsed.path or ""
        except Exception:
            return ""
    return raw.split("?")[0].split("#")[0]


def _resolve_local(url: str) -> Optional[str]:
    clean = _normalize_local_path(url)
    if not clean:
        return None
    if clean.startswith("/imdf/media/output/"):
        rel = clean[len("/imdf/media/output/"):].lstrip("/")
        return _assert_inside(OUTPUT_DIR, os.path.join(OUTPUT_DIR, rel))
    if clean.startswith("/imdf/media/input/"):
        rel = clean[len("/imdf/media/input/"):].lstrip("/")
        return _assert_inside(INPUT_DIR, os.path.join(INPUT_DIR, rel))
    return None


def _resolve_figma_base(raw: Optional[str]) -> str:
    val = _sanitize_text(raw, os.environ.get("FIGMA_BRIDGE_BASE", DEFAULT_FIGMA_BRIDGE_BASE))
    try:
        parsed = urlparse(val)
        if parsed.scheme != "http":
            raise ValueError("Figma 桥接接口只允许 http")
        host = parsed.hostname.lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Figma 桥接接口只允许本机地址")
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    except ValueError:
        raise
    except Exception:
        return DEFAULT_FIGMA_BRIDGE_BASE


def _normalize_materials(raw: List[Dict]) -> List[Dict]:
    results = []
    for idx, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        kind = _sanitize_text(item.get("kind", ""), "", 30)
        url = _sanitize_text(item.get("url", ""), "", 4000)
        text = str(item.get("text", ""))[:200000]
        if kind == "text" and not text.strip():
            continue
        if kind != "text" and not url:
            continue
        results.append({
            "id": _sanitize_text(item.get("id"), f"item_{idx+1}", 120),
            "kind": kind,
            "url": url,
            "text": text,
            "name": _sanitize_text(item.get("name"), "", 240),
        })
    return results


def _to_absolute(url: str) -> str:
    if not url:
        return ""
    if re.match(r"^https?://", url, re.I):
        return url
    if url.startswith("/"):
        return f"http://127.0.0.1:{PORT}{url}"
    return url


def _to_bridge_item(item: Dict) -> Dict:
    local_path = _resolve_local(item.get("url", ""))
    bridge = {
        "id": item["id"],
        "kind": item["kind"],
        "name": item.get("name") or (f"文本 {item['id']}" if item["kind"] == "text" else os.path.basename(item.get("url", "素材"))),
    }
    if item["kind"] == "text":
        bridge["text"] = item["text"]
    else:
        bridge["url"] = _to_absolute(item.get("url", ""))
        if local_path and os.path.exists(local_path):
            bridge["path"] = local_path
    return bridge


async def _post_to_bridge(base: str, endpoint: str, body: Dict) -> Dict:
    """向 Figma bridge 发送 POST 请求"""
    timeout = httpx.Timeout(FIGMA_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                f"{base}{endpoint}",
                json=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail=f"Figma bridge {endpoint} 超时")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Figma bridge 连接失败: {e}")

        text = resp.text
        data = {}
        try:
            data = json.loads(text) if text else {}
        except Exception as e:
            logger.error(f"Operation failed: {e}")

        if resp.status_code >= 400:
            err = data.get("message") or data.get("error") or f"Figma bridge HTTP {resp.status_code}"
            raise HTTPException(status_code=502, detail=err)
        if isinstance(data, dict) and (data.get("success") is False or data.get("status") == "error"):
            raise HTTPException(status_code=502, detail=data.get("message", data.get("error", "Figma 导入失败")))
        return data


# ═══════════════════════════════════════════════════════════════════════════════
# POST /imdf/figma/import
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/import")
async def figma_import(req: FigmaImportRequest):
    """发送素材到 Figma 插件"""
    base = _resolve_figma_base(req.figma_api_base)
    materials = _normalize_materials([m.dict() for m in req.materials])
    if not materials:
        raise HTTPException(status_code=400, detail="没有可发送到 Figma 的素材")

    tags = [str(t).strip()[:60] for t in (req.tags or []) if str(t).strip()][:20] or ["IMDF", "画布素材"]
    payload = {
        "app": "imdf-canvas",
        "tags": tags,
        "materials": [_to_bridge_item(m) for m in materials],
    }

    # 尝试两个端点
    first_error = None
    for ep in ("/import", "/api/import"):
        try:
            result = await _post_to_bridge(base, ep, payload)
            return {
                "success": True,
                "data": {"base": base, "sent": len(payload["materials"]), "result": result},
            }
        except HTTPException as e:
            if first_error is None:
                first_error = e
            if ep == "/api/import":
                raise first_error
            continue
        except Exception as e:
            if first_error is None:
                first_error = e
            continue

    raise first_error or HTTPException(status_code=502, detail="Figma bridge 导入失败")
