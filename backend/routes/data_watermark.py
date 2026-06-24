"""水印与版权路由 — visible/invisible/detect/copyright"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/watermark/visible")
async def data_watermark_visible(request: Request):
    """添加可见水印"""
    body = await request.json()
    image_path = body.get("image_path", "")
    text = body.get("text", "NanoBot")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_watermark import VisibleWatermark
    from PIL import Image

    img = Image.open(image_path)
    result = VisibleWatermark.add_text_watermark(img, text=text, opacity=0.3)

    output_path = image_path.replace(".", "_watermarked.")
    result.save(output_path)

    return {"success": True, "output_path": output_path}


@router.post("/api/data/watermark/invisible")
async def data_watermark_invisible(request: Request):
    """嵌入不可见水印"""
    body = await request.json()
    image_path = body.get("image_path", "")
    message = body.get("message", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_watermark import InvisibleWatermark
    from PIL import Image

    img = Image.open(image_path)
    result = InvisibleWatermark.embed_dwt(img, message)

    output_path = image_path.replace(".", "_invisible.")
    result.save(output_path)

    return {"success": True, "output_path": output_path}


@router.post("/api/data/watermark/detect")
async def data_watermark_detect(request: Request):
    """检测不可见水印"""
    body = await request.json()
    image_path = body.get("image_path", "")
    message = body.get("message", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_watermark import InvisibleWatermark
    from PIL import Image

    img = Image.open(image_path)
    result = InvisibleWatermark.detect_dwt(img, message)

    return {
        "success": result.success,
        "confidence": round(result.confidence, 4),
        "message": result.message
    }


@router.post("/api/data/copyright/register")
async def data_copyright_register(request: Request):
    """注册版权"""
    body = await request.json()
    image_id = body.get("image_id", "")
    owner = body.get("owner", "default")
    metadata = body.get("metadata", {})

    from data_watermark import CopyrightManager
    cm = CopyrightManager()
    record = cm.register(image_id, owner, metadata)

    return {
        "success": True,
        "watermark_id": record.watermark_id,
        "owner": record.owner,
        "created_at": record.created_at
    }


@router.get("/api/data/copyright/lookup")
async def data_copyright_lookup(image_id: str = ""):
    """查询版权"""
    if not image_id:
        raise HTTPException(status_code=400, detail="image_id required")

    from data_watermark import CopyrightManager
    cm = CopyrightManager()
    record = cm.lookup(image_id)

    if record:
        return {
            "success": True,
            "image_id": record.image_id,
            "owner": record.owner,
            "watermark_id": record.watermark_id,
            "created_at": record.created_at
        }
    return {"success": False, "message": "No record found"}
