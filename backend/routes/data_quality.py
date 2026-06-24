"""数据质量引擎路由 — 数据生产管线"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/data/quality-engine/status")
async def data_quality_engine_status():
    """数据质量引擎状态"""
    try:
        from data_quality_engine import get_quality_engine
        engine = get_quality_engine(skip_model_init=False)
        return {
            "status": "ok",
            "ready": engine._ready,
            "loaded_models": engine._loaded_models,
            "device": engine._device
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/data/quality-engine/score")
async def data_quality_score(request: Request):
    """图像质量评分"""
    body = await request.json()
    image_path = body.get("image_path", "")
    caption = body.get("caption", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_quality_engine import get_quality_engine
    engine = get_quality_engine(skip_model_init=False)

    score = engine.score_image(image_path, caption)

    def _float(v):
        return float(v) if v is not None else 0.0

    return {
        "success": True,
        "overall_score": _float(score.overall_score),
        "aesthetic_score": _float(score.aesthetic_score),
        "technical_quality": _float(score.technical_quality),
        "clip_score": _float(score.clip_score),
        "sharpness": round(_float(score.sharpness), 4),
        "brightness": round(_float(score.brightness), 4),
        "contrast": round(_float(score.contrast), 4),
        "colorfulness": round(_float(score.colorfulness), 4),
        "noise_level": round(_float(score.noise_level), 4),
        "face_count": int(score.face_count),
        "width": int(score.width),
        "height": int(score.height),
        "aspect_ratio": round(_float(score.aspect_ratio), 4)
    }


@router.post("/api/data/quality-engine/batch-score")
async def data_quality_batch_score(request: Request):
    """批量质量评分"""
    body = await request.json()
    items = body.get("items", [])
    threshold = body.get("threshold", 0.5)

    if not items:
        raise HTTPException(status_code=400, detail="No items provided")

    from data_quality_engine import get_quality_engine
    engine = get_quality_engine(skip_model_init=False)
    report = engine.score_batch(items, image_key="image_path",
                                 caption_key="caption", threshold=threshold)

    return {
        "success": True,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "avg_scores": report.avg_scores,
        "passed_ids": report.passed_ids,
        "failed_ids": report.failed_ids
    }
