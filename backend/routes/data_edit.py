"""编辑指令自动生成管线路由"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/edit/generate")
async def data_edit_generate(request: Request):
    """为单张图像生成编辑指令数据"""
    body = await request.json()
    image_path = body.get("image_path", "")
    edit_type = body.get("edit_type", None)
    params = body.get("params", None)

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_edit_pipeline import EditInstructionPipeline
    pipeline = EditInstructionPipeline()
    item = pipeline.generate_edit(image_path, edit_type=edit_type, params=params)

    if item is None:
        raise HTTPException(status_code=500, detail="Failed to generate edit instruction")

    return {
        "success": True,
        "id": item.id,
        "source_image": item.source_image,
        "instruction": item.instruction,
        "edit_type": item.edit_type,
        "source_caption": item.source_caption,
        "target_caption": item.target_caption,
        "metadata": item.metadata,
    }


@router.post("/api/data/edit/batch")
async def data_edit_batch(request: Request):
    """批量生成编辑指令"""
    body = await request.json()
    images = body.get("images", [])
    edit_types = body.get("edit_types", None)
    n_per_image = body.get("n_per_image", 1)

    if not images:
        raise HTTPException(status_code=400, detail="No images provided")

    from data_edit_pipeline import EditInstructionPipeline
    pipeline = EditInstructionPipeline()
    items = pipeline.batch_generate(images, edit_types=edit_types, n_per_image=n_per_image)

    results = []
    for item in items:
        results.append({
            "id": item.id,
            "source_image": item.source_image,
            "instruction": item.instruction,
            "edit_type": item.edit_type,
            "source_caption": item.source_caption,
            "target_caption": item.target_caption,
        })

    return {
        "success": True,
        "total": len(results),
        "items": results,
    }
