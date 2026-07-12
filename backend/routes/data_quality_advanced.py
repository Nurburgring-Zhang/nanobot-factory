"""高级质量评分路由 — 美学/NSFW/人脸质量/水印检测"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

# P21 P2 P2 — wire Injection.validate_path (R2-NEW-04 fix)
from backend.common.path_dep import validated_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/quality/advanced")
async def data_quality_advanced(request: Request):
    """高级质量评分 — 美学/NSFW/人脸质量/水印检测全覆盖"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    image_path = validated_path(body.get("image_path", ""))
    caption = body.get("caption", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_quality_advanced import get_advanced_scorer
    scorer = get_advanced_scorer()

    report = scorer.comprehensive_report(image_path, caption=caption)
    wm = scorer.watermark_detect(image_path)
    fq = scorer.face_quality(image_path)

    return {
        "success": True,
        "aesthetic_score": report.aesthetic,
        "clip_score": report.clip_score,
        "nsfw_score": report.nsfw_score,
        "face_quality": fq["quality"],
        "face_count": fq["count"],
        "watermark_detect": wm["confidence"],
        "watermark_pattern": wm["pattern"],
        "score_mean": report.score_mean,
        "score_std": report.score_std,
        "width": report.width,
        "height": report.height,
    }


@router.post("/api/data/quality/advanced/batch")
async def data_quality_advanced_batch(request: Request):
    """批量高级质量评分 + 分布分析"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard on every element of the list.
    raw_paths = body.get("image_paths", [])
    image_paths = [validated_path(p) for p in raw_paths]
    captions = body.get("captions", [])

    if not image_paths:
        raise HTTPException(status_code=400, detail="No image paths provided")

    from data_quality_advanced import get_advanced_scorer
    scorer = get_advanced_scorer()

    # 每张图分析
    results = []
    for i, path in enumerate(image_paths):
        cap = captions[i] if i < len(captions) else ""
        if os.path.exists(path):
            report = scorer.comprehensive_report(path, caption=cap)
            fq = scorer.face_quality(path)
            wm = scorer.watermark_detect(path)
            results.append({
                "image_path": path,
                "aesthetic": report.aesthetic,
                "nsfw": report.nsfw_score,
                "face_quality": fq["quality"],
                "face_count": fq["count"],
                "watermark": wm["confidence"],
            })

    # 分布分析
    gap_analysis = scorer.scoring_gap_analysis(image_paths)

    return {
        "success": True,
        "total": len(results),
        "results": results,
        "distribution": gap_analysis,
    }
