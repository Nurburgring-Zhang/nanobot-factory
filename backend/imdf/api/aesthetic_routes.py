"""
F1.11 审美评分 API 路由
=========================
POST /api/aesthetic/score         — 单张图片评分
POST /api/aesthetic/score-batch   — 批量图片评分
POST /api/aesthetic/elo-compare   — Elo 成对比较提交
POST /api/aesthetic/elo-register  — 注册新图片到 Elo
GET  /api/aesthetic/elo-ranking   — Elo 排行榜
GET  /api/aesthetic/elo-stats     — Elo 统计
GET  /api/aesthetic/elo-entry/{image_id} — 单图 Elo 信息
GET  /api/aesthetic/health        — 引擎状态检查

修复(R1-Worker-1, 2026-06-18):
  - 8 个端点全部包 try/except, 任何未捕获异常 → 200 {"success": False, "error": ..., "data": None}
  - 修复 `get_aesthetic_engine` 工厂名 / `await score_image` / `use_llm/llm_models` kwarg 三个核心 bug
  - path 参数 `image_id` 校验: `^[a-zA-Z0-9_\\-]{1,128}$` 不匹配返回 400
  - 4 个 elo 端点调用线程安全的 in-memory 状态(由 RLock 保护)
"""
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel, Field, validator

# 兼容直接 `python aesthetic_routes.py` 与 canvas_web 加载两种入口
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from api._common.validators import validate_id  # noqa: E402

router = APIRouter(prefix="/api/aesthetic", tags=["aesthetic"])


# ─── Constants ──────────────────────────────────────────────────────────────

_VALID_IMAGE_ID = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


def _ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    """统一 200 成功响应"""
    return {"success": True, "data": data, "message": message}


def _fail(error: str, http_status: int = 200) -> Dict[str, Any]:
    """
    统一错误响应

    路由层 try/except 兜底用 200 + structured body(让 8 个端点永远不返回 500)
    显式 4xx(参数错误、image 不存在)由调用方通过 raise HTTPException 处理
    """
    return {"success": False, "error": str(error), "data": None, "status": http_status}


def _validate_image_id(image_id: str) -> Optional[str]:
    """返回 None 通过,否则返回错误信息"""
    if not image_id:
        return "image_id is required"
    if not _VALID_IMAGE_ID.match(image_id):
        return f"image_id must match {_VALID_IMAGE_ID.pattern}"
    return None


# ─── Request/Response Models ────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    image_path: str = Field("", description="图片文件路径(可空, 服务端校验)")
    use_llm: bool = Field(False, description="是否启用 LLM 评分(需 vision-capable 模型)")
    llm_models: Optional[List[str]] = Field(None, description="指定 LLM 模型 ID 列表")


class BatchScoreRequest(BaseModel):
    image_paths: Optional[List[str]] = Field(None, description="图片路径列表")
    directory: Optional[str] = Field(None, description="扫描目录路径")
    extensions: Optional[List[str]] = Field(None, description="文件扩展名过滤")
    use_llm: bool = Field(False, description="是否启用 LLM 评分")


class EloCompareRequest(BaseModel):
    image_a_id: str = Field(..., description="图片 A 的 ID")
    image_b_id: str = Field(..., description="图片 B 的 ID")
    winner: str = Field(..., description="胜者: 'a', 'b', 或 'draw'")
    image_a_name: str = Field("", description="图片 A 名称(可选)")
    image_b_name: str = Field("", description="图片 B 名称(可选)")
    judge_id: Optional[str] = Field(None, description="评委 ID(众包追踪)")

    @validator("winner")
    def _check_winner(cls, v: str) -> str:
        if v not in ("a", "b", "draw"):
            raise ValueError("winner must be 'a', 'b', or 'draw'")
        return v

    @validator("image_a_id", "image_b_id")
    def _check_ids(cls, v: str) -> str:
        if not _VALID_IMAGE_ID.match(v or ""):
            raise ValueError(f"image id must match {_VALID_IMAGE_ID.pattern}")
        return v


class EloRegisterRequest(BaseModel):
    image_id: str = Field(..., description="图片唯一标识")
    image_name: str = Field("", description="图片名称")
    initial_rating: float = Field(1500.0, description="初始 Elo 分")

    @validator("image_id")
    def _check_id(cls, v: str) -> str:
        if not _VALID_IMAGE_ID.match(v or ""):
            raise ValueError(f"image_id must match {_VALID_IMAGE_ID.pattern}")
        return v


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/score")
async def score_single(req: ScoreRequest):
    """
    对单张图片进行审美评分

    Returns 六维度评分 + 聚合分数 + 启发式评分 + 问题检测

    Example:
        POST /api/aesthetic/score
        {"image_path": "/path/to/photo.jpg"}
    """
    try:
        from engines.aesthetic_engine import get_aesthetic_engine

        path = (req.image_path or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="image_path is required")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"Image not found: {path}")

        engine = get_aesthetic_engine()
        result = await engine.score_image(
            image_path=path,
            use_llm=req.use_llm,
            llm_models=req.llm_models,
        )

        if not result.get("success"):
            return _fail(result.get("error") or "scoring failed")

        return _ok(
            data=result,
            message=f"Aesthetic scoring complete — Score: {result['overall_score']}, "
                    f"Confidence: {result['confidence']}",
        )
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"score_single failed: {e}")


@router.post("/score-batch")
async def score_batch(req: BatchScoreRequest):
    """
    批量图片评分: 支持路径列表或目录扫描

    Example:
        POST /api/aesthetic/score-batch
        {"directory": "/data/photos/", "extensions": [".jpg", ".png"]}
    """
    try:
        from engines.aesthetic_engine import get_aesthetic_engine

        if not req.image_paths and not req.directory:
            raise HTTPException(status_code=400, detail="Provide image_paths or directory")

        engine = get_aesthetic_engine()

        if req.image_paths:
            results = await engine.score_batch(req.image_paths, use_llm=req.use_llm)
        else:
            exts = tuple(req.extensions) if req.extensions else (
                '.jpg', '.jpeg', '.png', '.webp', '.bmp',
            )
            results = await engine.score_directory(
                req.directory, extensions=exts, use_llm=req.use_llm,
            )

        summary = engine.batch_summary(results)
        return _ok(
            data={"results": results, "summary": summary},
            message=f"Batch scoring complete: {summary['scored']}/{summary['total']} scored",
        )
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"score_batch failed: {e}")


# ─── Elo Routes ──────────────────────────────────────────────────────────────

@router.post("/elo-compare")
async def elo_compare(req: EloCompareRequest):
    """
    Elo 成对比较 — 提交一次比较结果

    两张图片二选一(或平局), 系统自动调整 Elo 分数。

    Example:
        POST /api/aesthetic/elo-compare
        {
            "image_a_id": "img_001",
            "image_b_id": "img_002",
            "winner": "a",
            "image_a_name": "sunset.jpg",
            "image_b_name": "portrait.jpg",
            "judge_id": "user_123"
        }
    """
    try:
        from engines.aesthetic_engine import get_aesthetic_engine

        engine = get_aesthetic_engine()
        result = engine.elo_compare(
            image_a_id=req.image_a_id,
            image_b_id=req.image_b_id,
            winner=req.winner,
            image_a_name=req.image_a_name,
            image_b_name=req.image_b_name,
        )

        if result is None:
            raise HTTPException(status_code=400, detail="Invalid comparison parameters")

        return _ok(
            data={"comparison": result.to_dict(), "judge_id": req.judge_id},
            message=f"Elo comparison recorded — delta: {result.elo_delta}",
        )
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"elo_compare failed: {e}")


@router.post("/elo-register")
async def elo_register(req: EloRegisterRequest):
    """
    注册新图片到 Elo 排行榜

    Example:
        POST /api/aesthetic/elo-register
        {"image_id": "img_003", "image_name": "landscape.jpg", "initial_rating": 1500}
    """
    try:
        from engines.aesthetic_engine import get_aesthetic_engine

        engine = get_aesthetic_engine()
        entry = engine.elo_register(req.image_id, req.image_name, req.initial_rating)

        return _ok(
            data=entry.to_dict(),
            message=f"Image '{entry.image_name}' registered with Elo {entry.rating}",
        )
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"elo_register failed: {e}")


@router.get("/elo-ranking")
async def elo_ranking(
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """
    获取 Elo 排行榜(按分数降序)

    Example:
        GET /api/aesthetic/elo-ranking?limit=20
    """
    try:
        from engines.aesthetic_engine import get_aesthetic_engine

        engine = get_aesthetic_engine()
        ranking = engine.elo_ranking(limit=limit, offset=offset)
        # 读 len 时也走锁内
        stats = engine.elo_stats()

        return _ok(
            data={
                "ranking": ranking,
                "total": stats["total_entries"],
                "limit": limit,
                "offset": offset,
            },
            message=f"Elo ranking: {len(ranking)} entries returned",
        )
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"elo_ranking failed: {e}")


@router.get("/elo-stats")
async def elo_stats():
    """
    获取 Elo 系统统计信息

    Example:
        GET /api/aesthetic/elo-stats
    """
    try:
        from engines.aesthetic_engine import get_aesthetic_engine

        engine = get_aesthetic_engine()
        stats = engine.elo_stats()

        return _ok(data=stats, message="Elo statistics retrieved")
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"elo_stats failed: {e}")


@router.get("/elo-entry/{image_id}")
async def elo_get_entry(image_id: str):
    """
    获取单个图片的 Elo 信息

    Example:
        GET /api/aesthetic/elo-entry/img_001
    """
    try:
        # R1-Worker-2: 用共享校验器替代内联 _validate_image_id,
        # 失败直接 raise HTTPException(400), 通过则继续。
        validate_id(image_id, "image_id")

        from engines.aesthetic_engine import get_aesthetic_engine

        engine = get_aesthetic_engine()
        # 字典查找包 try/except, 任何异常 → 200 {"success": False, ...}
        try:
            entry = engine.elo_get_entry(image_id)
        except Exception as e:
            return _fail(f"elo lookup failed: {e}")

        if entry is None:
            raise HTTPException(status_code=404, detail=f"Elo entry not found: {image_id}")

        return _ok(data=entry.to_dict(), message="Elo entry found")
    except HTTPException:
        raise
    except Exception as e:
        return _fail(f"elo_get_entry failed: {e}")


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def aesthetic_health():
    """检查审美评分引擎状态"""
    try:
        try:
            from PIL import Image
            has_pillow = True
        except ImportError:
            has_pillow = False

        models: List[Dict[str, Any]] = []
        vision_models: List[Dict[str, Any]] = []
        try:
            from engines.model_gateway import get_gateway
            gateway = get_gateway()
            if gateway:
                raw = await gateway.list_models()
                models = list(raw) if raw else []
                vision_models = [m for m in models if "vision" in (m.get("capabilities") or [])]
        except Exception:
            # gateway 不可用 — 不影响 health 端点返回
            pass

        from engines.aesthetic_engine import get_aesthetic_engine
        engine = get_aesthetic_engine()
        elo = engine.elo_stats()

        return _ok(
            data={
                "engine": "aesthetic_engine v3.1",
                "pillow_available": has_pillow,
                "status": "ready" if has_pillow else "degraded",
                "scoring_methods": {
                    "heuristic": has_pillow,
                    "llm_vision": len(vision_models) > 0,
                    "elo": True,
                },
                "available_models": len(models),
                "vision_models": len(vision_models),
                "elo": elo,
                # R4-W4-others: 最高SRCC 真实值, 来源 aesthetic_engine.py L60-64 (Q-Align 0.885)
                "max_srcc": 0.885,
            },
            message="Engine is ready" if has_pillow else "Pillow missing — install: pip install Pillow",
        )
    except Exception as e:
        return _fail(f"aesthetic_health failed: {e}")
