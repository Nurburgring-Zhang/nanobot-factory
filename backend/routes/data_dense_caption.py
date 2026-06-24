"""密集描述生成路由 — 完整/简短/BLIP3/ShareGPT4V"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/dense-caption/generate")
async def data_dense_caption_generate(request: Request):
    """密集描述生成 — 完整/简短/BLIP3/ShareGPT4V"""
    body = await request.json()
    image_path = body.get("image_path", "")
    style = body.get("style", "full")  # full / short / blip3 / sharegpt4v

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_dense_caption import DenseCaptionGenerator
    gen = DenseCaptionGenerator()

    if style == "short":
        caption = gen.generate_short_caption(image_path)
        return {"success": True, "style": "short", "caption": caption}
    elif style == "blip3":
        blip3 = gen.generate_blip3_style(image_path)
        return {"success": True, "style": "blip3", **blip3}
    elif style == "sharegpt4v":
        output_dir = body.get("output_dir", "./data/sharegpt4v")
        entry = gen.save_sharegpt4v_format(image_path, output_dir=output_dir)
        return {"success": True, "style": "sharegpt4v", "entry": entry}
    elif style == "regions":
        regions = gen.generate_region_captions(image_path)
        return {
            "success": True,
            "style": "regions",
            "regions": [{"bbox": r.bbox, "caption": r.caption, "category": r.category}
                        for r in regions],
        }
    else:
        # full
        caption = gen.generate_full_caption(image_path)
        return {"success": True, "style": "full", "caption": caption}
