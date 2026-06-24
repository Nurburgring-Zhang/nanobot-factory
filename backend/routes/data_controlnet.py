"""ControlNet条件图生成路由"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/controlnet/generate")
async def data_controlnet_generate(request: Request):
    """ControlNet条件图生成 — 边缘/深度/姿态/分割"""
    body = await request.json()
    image_path = body.get("image_path", "")
    conditions = body.get("conditions", ["canny", "depth", "pose", "segmentation"])
    caption = body.get("caption", "")
    output_dir = body.get("output_dir", "./data/controlnet")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_controlnet_pipeline import ControlNetProcessor
    processor = ControlNetProcessor(output_dir=output_dir)

    pair = processor.generate_control_pairs(
        image_path, conditions=conditions, caption=caption, save=True
    )

    return {
        "success": True,
        "image_id": pair.image_id,
        "source_image": pair.source_image_path,
        "canny": pair.canny_path,
        "depth": pair.depth_path,
        "pose": pair.pose_path,
        "segmentation": pair.segmentation_path,
        "width": pair.width,
        "height": pair.height,
    }


@router.post("/api/data/controlnet/batch")
async def data_controlnet_batch(request: Request):
    """批量ControlNet条件图生成"""
    body = await request.json()
    image_dir = body.get("image_dir", "")
    conditions = body.get("conditions", ["canny", "depth", "pose", "segmentation"])
    output_dir = body.get("output_dir", "./data/controlnet/batch")

    if not image_dir or not os.path.exists(image_dir):
        raise HTTPException(status_code=400, detail="Image directory not found")

    from data_controlnet_pipeline import ControlNetProcessor
    processor = ControlNetProcessor()

    # 收集图像
    import glob
    extensions = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
    images = []
    for ext in extensions:
        images.extend(sorted(glob.glob(os.path.join(image_dir, ext))))

    if not images:
        raise HTTPException(status_code=400, detail="No images found in directory")

    captions = [""] * len(images)
    dataset = processor.generate_batch(images, captions=captions,
                                        conditions=conditions,
                                        output_subdir=os.path.basename(output_dir))

    # 保存为标准格式
    out_path = processor.save_control_dataset(dataset, output_dir=output_dir)

    return {
        "success": True,
        "output_dir": out_path,
        "total_pairs": dataset.total,
        "conditions": dataset.conditions,
    }
