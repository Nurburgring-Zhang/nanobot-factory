"""
Theme Template Manager — 复刻 Penguin Canvas routes/themes.js
===============================================================
自定义主题模板: 视觉风格/音乐/模式 CRUD
"""
import os
import re
import json
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

from config.global_config import (
    SETTINGS_FILE, DEFAULT_THEME_TEMPLATE_DIR,
)

router = APIRouter(prefix="/imdf/theme", tags=["theme"])

# ─── 常量 ───────────────────────────────────────────────────────────────────
SCHEMA = "imdf-theme-template"
VERSION = 2

VISUAL_STYLES = frozenset([
    "plain", "tech", "pixel", "op", "rh", "naruto", "eva", "yyh",
    "slamdunk", "soccer-hero", "dragon-ball", "saint-seiya",
])
INTENSITIES = frozenset(["subtle", "medium", "strong"])
ICON_PACKS = frozenset([
    "default", "op", "naruto", "eva", "yyh", "slamdunk", "soccer",
    "dragon-ball", "saint-seiya",
])
CANVAS_PATTERNS = frozenset([
    "none", "dots", "map", "circuit", "confetti", "hub", "chakra",
    "eva-grid", "spirit-map", "court", "pitch", "dragon-radar",
    "sanctuary-zodiac",
])
NODE_FRAMES = frozenset([
    "plain", "glass", "sticker", "wanted", "hub-card", "shinobi-scroll",
    "eva-panel", "spirit-case", "scoreboard-card", "match-card",
    "capsule-card", "cloth-box-card",
])
MUSIC_PRESETS = frozenset([
    "tech-pulse", "pixel-pop", "grand-line-adventure", "rh-pulse",
    "shinobi-flame", "eva-sync", "spirit-gun", "buzzer-beater",
    "golden-goal", "ki-burst", "shenron-aura", "pegasus-cosmos",
    "hades-eclipse",
])
MUSIC_SOURCES = frozenset(["synth", "url", "upload"])

_STYLE_TO_ICON = {
    "op": "op", "rh": "default", "naruto": "naruto", "eva": "eva",
    "yyh": "yyh", "slamdunk": "slamdunk", "soccer-hero": "soccer",
    "dragon-ball": "dragon-ball", "saint-seiya": "saint-seiya",
    "tech": "default", "pixel": "default", "plain": "default",
}

_STYLE_TO_PATTERN = {
    "op": "map", "rh": "hub", "naruto": "chakra", "eva": "eva-grid",
    "yyh": "spirit-map", "slamdunk": "court", "soccer-hero": "pitch",
    "dragon-ball": "dragon-radar", "saint-seiya": "sanctuary-zodiac",
    "tech": "circuit", "pixel": "dots", "plain": "none",
}

_STYLE_TO_FRAME = {
    "op": "wanted", "rh": "hub-card", "naruto": "shinobi-scroll",
    "eva": "eva-panel", "yyh": "spirit-case", "slamdunk": "scoreboard-card",
    "soccer-hero": "match-card", "dragon-ball": "capsule-card",
    "saint-seiya": "cloth-box-card", "tech": "glass", "pixel": "sticker",
    "plain": "plain",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Internal utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _load_settings() -> Dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return {}


def _get_theme_dir(required: bool = False) -> str:
    s = _load_settings()
    raw = str(s.get("themeTemplatePath") or DEFAULT_THEME_TEMPLATE_DIR or "").strip()
    d = raw or DEFAULT_THEME_TEMPLATE_DIR
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as e:
        if required:
            raise e
    return d


def _safe_id(value: str) -> str:
    clean = re.sub(r'[^a-z0-9_-]', "-", str(value or "").strip().lower())
    clean = re.sub(r"-+", "-", clean).strip("-")
    return clean[:64]


def _template_file(tid: str) -> str:
    clean = _safe_id(tid)
    if not clean:
        raise ValueError("模板 ID 不能为空")
    return os.path.join(_get_theme_dir(required=True), f"{clean}.json")


def _load_template(path: str) -> Dict:
    with open(path, "r") as f:
        raw = json.load(f)
    return _normalize_template(raw, os.path.basename(path).replace(".json", ""))


def _list_templates() -> List[Dict]:
    d = _get_theme_dir()
    if not os.path.exists(d):
        return []
    results = []
    for fname in os.listdir(d):
        if not fname.lower().endswith(".json"):
            continue
        try:
            results.append(_load_template(os.path.join(d, fname)))
        except Exception as e:
            logger.error(f"Operation failed: {e}")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 规范化函数
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_visuals(raw: Optional[Dict], legacy_style: str) -> Dict:
    source = raw if isinstance(raw, dict) else {}
    fallback = "tech" if legacy_style == "tech" else "pixel"
    style = source.get("style") if source.get("style") in VISUAL_STYLES else fallback
    return {
        "style": style,
        "intensity": source.get("intensity") if source.get("intensity") in INTENSITIES else "medium",
        "iconPack": source.get("iconPack") if source.get("iconPack") in ICON_PACKS else _STYLE_TO_ICON.get(style, "default"),
        "canvasPattern": source.get("canvasPattern") if source.get("canvasPattern") in CANVAS_PATTERNS else _STYLE_TO_PATTERN.get(style, "dots"),
        "nodeFrame": source.get("nodeFrame") if source.get("nodeFrame") in NODE_FRAMES else _STYLE_TO_FRAME.get(style, "sticker"),
        "headerMark": str(source.get("headerMark", ""))[:40],
    }


def _default_music(legacy_style: str, visuals: Dict) -> Dict:
    style = visuals.get("style")
    presets = {
        "op": ("Grand Line Adventure Loop", "grand-line-adventure", 0.16, 96),
        "rh": ("潮鸣", "rh-pulse", 0.14, 104),
        "naruto": ("Shinobi Flame Loop", "shinobi-flame", 0.16, 146),
        "eva": ("MAGI Sync Loop", "eva-sync", 0.16, 152),
        "yyh": ("Spirit Gun Pulse", "spirit-gun", 0.16, 138),
        "slamdunk": ("Buzzer Beater Warmup", "buzzer-beater", 0.16, 104),
        "soccer-hero": ("Golden Goal Loop", "golden-goal", 0.16, 150),
        "dragon-ball": ("Ki Burst Radar Loop", "ki-burst", 0.16, 156),
        "saint-seiya": ("Pegasus Cosmos Loop", "pegasus-cosmos", 0.16, 148),
        "tech": ("Neon Circuit Pulse", "tech-pulse", 0.16, 112),
    }
    p = presets.get(style) or ("Candy Bit Bounce", "pixel-pop", 0.15, 128)
    return {"title": p[0], "preset": p[1], "source": "synth", "volume": p[2], "bpm": p[3]}


def _normalize_music(raw: Optional[Dict], legacy_style: str, visuals: Dict) -> Dict:
    fallback = _default_music(legacy_style, visuals)
    source = raw if isinstance(raw, dict) else {}
    vol = _clamp(float(source.get("volume", fallback["volume"])), 0, 0.5)
    bpm = _clamp(int(source.get("bpm", fallback["bpm"])), 40, 220)
    url = str(source.get("url", "")).strip()
    safe_url = url if (url.startswith("data:audio/") or re.match(r"^https?://", url)) else ""
    return {
        "title": str(source.get("title", fallback["title"])).strip()[:80] or fallback["title"],
        "preset": source.get("preset") if source.get("preset") in MUSIC_PRESETS else fallback["preset"],
        "source": source.get("source") if source.get("source") in MUSIC_SOURCES else fallback["source"],
        "url": safe_url[:45000000],
        "volume": vol,
        "bpm": bpm,
    }


def _clamp(value, lo, hi):
    if isinstance(value, (int, float)):
        return max(lo, min(hi, value))
    return lo


def _normalize_template(raw: Dict, fallback_id: str) -> Dict:
    if not isinstance(raw, dict):
        raise ValueError("主题模板必须是 JSON 对象")
    tid = _safe_id(raw.get("id", fallback_id))
    if not tid:
        raise ValueError("主题模板缺少 id")
    name = str(raw.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("主题模板缺少名称")
    legacy_style = "tech" if raw.get("legacyStyle") == "tech" else "pixel"
    modes = raw.get("modes", {})
    if not isinstance(modes, dict):
        raise ValueError("modes 必须是对象")
    for mode in ("light", "dark"):
        m = modes.get(mode)
        if not isinstance(m, dict) or "tokens" not in m:
            raise ValueError(f"主题模板缺少 {mode} tokens")
    visuals = _normalize_visuals(raw.get("visuals"), legacy_style)
    return {
        "schema": SCHEMA, "version": VERSION,
        "id": tid, "name": name,
        "description": str(raw.get("description", ""))[:300],
        "author": str(raw.get("author", ""))[:80],
        "builtIn": False,
        "legacyStyle": legacy_style,
        "visuals": visuals,
        "music": _normalize_music(raw.get("music"), legacy_style, visuals),
        "modes": {
            "light": {"tokens": modes["light"]["tokens"]},
            "dark": {"tokens": modes["dark"]["tokens"]},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/templates")
async def list_theme_templates(
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
    try:
        return {
            "success": True,
            "data": {"path": _get_theme_dir(), "templates": _list_templates()},
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/import")
async def import_theme_template(payload: Dict):
    try:
        template = _normalize_template(payload.get("template") or payload, "")
        path = _template_file(template["id"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        return {"success": True, "data": template}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/templates/{tid}")
async def update_theme_template(tid: str, payload: Dict):
    try:
        merged = {**payload, "id": tid}
        template = _normalize_template(merged, tid)
        path = _template_file(tid)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        return {"success": True, "data": template}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/templates/{tid}/export")
async def export_theme_template(tid: str):
    try:
        path = _template_file(tid)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="模板不存在")
        template = _load_template(path)
        return {"success": True, "data": template}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/templates/{tid}")
async def delete_theme_template(tid: str):
    try:
        path = _template_file(tid)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="模板不存在")
        os.remove(path)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
