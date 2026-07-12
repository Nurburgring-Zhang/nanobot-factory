"""视频质量管线路由 — 对齐Open-Sora/Panda-70M标准"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

# P21 P2 P2 — wire Injection.validate_path (R2-NEW-04 fix)
from backend.common.path_dep import validated_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/video/assess")
async def data_video_assess(request: Request):
    """视频质量全面评估"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    video_path = validated_path(body.get("video_path", ""))
    caption = body.get("caption", "")

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Video path not found")

    from data_video_quality import get_video_quality_assessor
    assessor = get_video_quality_assessor()
    assessment = assessor.assess(video_path, caption)

    # 确保可JSON序列化
    def _ser(v):
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        return v

    import numpy as np
    result = {}
    for k, v in assessment.items():
        try:
            json.dumps(v)
            result[k] = v
        except (TypeError, OverflowError):
            result[k] = _ser(v)

    return {
        "success": True,
        **result,
    }


@router.post("/api/data/video/filter")
async def data_video_filter(request: Request):
    """视频过滤（对齐Open-Sora标准）"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    video_path = validated_path(body.get("video_path", ""))
    caption = body.get("caption", "")

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Video path not found")

    from data_video_quality import get_video_quality_assessor
    assessor = get_video_quality_assessor()
    result = assessor.filter(video_path, caption)

    return {
        "success": True,
        **result,
    }


@router.post("/api/data/video/dedup")
async def data_video_dedup(request: Request):
    """视频去重（placeholder — 使用视频hash近似检测）"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard on every element of the list.
    raw_paths = body.get("video_paths", [])
    video_paths = [validated_path(p) for p in raw_paths]

    if not video_paths:
        raise HTTPException(status_code=400, detail="No video paths provided")

    # 简单的基于文件大小和首帧hash的去重
    import hashlib
    seen_hashes = set()
    unique = []
    duplicates = []

    for vp in video_paths:
        if not os.path.exists(vp):
            continue
        try:
            file_stat = os.stat(vp)
            # 首帧hash
            import cv2
            cap = cv2.VideoCapture(vp)
            ret, frame = cap.read()
            cap.release()
            if ret:
                import numpy as np
                frame_hash = hashlib.md5(frame.tobytes()).hexdigest()
            else:
                frame_hash = ""
            sig = f"{file_stat.st_size}_{frame_hash}"
            if sig in seen_hashes:
                duplicates.append(vp)
            else:
                seen_hashes.add(sig)
                unique.append(vp)
        except Exception as e:
            unique.append(vp)
            logger.warning(f"Error processing {vp}: {e}")

    return {
        "success": True,
        "total": len(video_paths),
        "unique": len(unique),
        "duplicates": len(duplicates),
        "unique_paths": unique,
        "duplicate_paths": duplicates,
    }


@router.post("/api/data/video/export-jsonl")
async def data_video_export_jsonl(request: Request):
    """导出JSONL（Open-Sora / Panda-70M格式）"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard on both video_path and output_path.
    video_path = validated_path(body.get("video_path", ""))
    caption = body.get("caption", "")
    format_type = body.get("format", "opensora")
    output_path = validated_path(body.get("output_path", ""))

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Video path not found")

    from data_video_quality import get_video_quality_assessor
    assessor = get_video_quality_assessor()

    if format_type == "opensora":
        record = assessor.to_opensora_jsonl(video_path, caption)
    elif format_type == "panda70m":
        record = assessor.to_panda70m_jsonl(video_path, caption)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format_type}")

    if output_path:
        import json
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "success": True,
        "format": format_type,
        "record": record,
        "output_path": output_path or None,
    }
