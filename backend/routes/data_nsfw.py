"""NSFW分类器路由"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

# P21 P2 P2 — wire Injection.validate_path (R2-NEW-04 fix)
from backend.common.path_dep import validated_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/nsfw/classify")
async def data_nsfw_classify(request: Request):
    """NSFW分类 — 对齐LAION/DataComp标准"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    image_path = validated_path(body.get("image_path", ""))

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_nsfw_classifier import classify_nsfw
    result = classify_nsfw(image_path)

    return {
        "success": True,
        "nsfw_score": result.get("nsfw_score", 0.0),
        "nsfw_category": result.get("nsfw_category", "safe"),
        "probability_safe": result.get("probability_safe", 0.0),
        "probability_nsfw": result.get("probability_nsfw", 0.0),
        "skin_area_ratio": result.get("skin_area_ratio", 0.0),
        "method": result.get("method", ""),
    }


@router.post("/api/data/nsfw/filter")
async def data_nsfw_filter(request: Request):
    """DataComp标准NSFW过滤"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    image_path = validated_path(body.get("image_path", ""))

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_nsfw_classifier import datacomp_nsfw_check
    result = datacomp_nsfw_check(image_path)

    return {
        "success": True,
        "nsfw_score": result.get("nsfw_score", 0.0),
        "datacomp_reject": result.get("datacomp_reject", False),
        "datacomp_threshold": 0.5,
        "nsfw_category": result.get("nsfw_category", "safe"),
    }
