"""MLLM训练数据生产管线路由"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

# P21 P2 P2 — wire Injection.validate_path (R2-NEW-04 fix)
from backend.common.path_dep import validated_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/mllm/llava")
async def data_mllm_llava(request: Request):
    """生成LLaVA标准多轮对话"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    image_path = validated_path(body.get("image_path", ""))
    caption = body.get("caption", "")
    num_turns = body.get("num_turns", 3)

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_mllm_pipeline import MLLMDataPipeline
    pipeline = MLLMDataPipeline()
    result = pipeline.generate_llava_conversation(image_path, caption=caption, num_turns=num_turns)

    return {
        "success": True,
        "id": result.get("id", ""),
        "image": result.get("image", image_path),
        "conversations": result.get("conversations", []),
    }


@router.post("/api/data/mllm/sharegpt4v")
async def data_mllm_sharegpt4v(request: Request):
    """生成ShareGPT4V格式详细描述"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    image_path = validated_path(body.get("image_path", ""))
    caption = body.get("caption", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_mllm_pipeline import MLLMDataPipeline
    pipeline = MLLMDataPipeline()
    result = pipeline.generate_sharegpt4v(image_path, caption=caption)

    return {
        "success": True,
        "id": result.get("id", ""),
        "image": result.get("image", image_path),
        "caption": result.get("caption", ""),
        "conversations": result.get("conversations", []),
    }


@router.post("/api/data/mllm/interleaved")
async def data_mllm_interleaved(request: Request):
    """生成交错图文格式"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard on every nested ``image`` field.
    raw_items = body.get("items", [])
    items = [
        {**it, "image": validated_path(it.get("image", ""))}
        if isinstance(it, dict) and "image" in it
        else it
        for it in raw_items
    ]
    # items: [{"text": "...", "image": "path"}, ...]

    if not items:
        raise HTTPException(status_code=400, detail="No items provided")

    from data_mllm_pipeline import MLLMDataPipeline
    pipeline = MLLMDataPipeline()

    # 转换为(image, text)对
    image_text_pairs = []
    for item in items:
        img_path = item.get("image", "")
        text = item.get("text", "")
        if img_path and os.path.exists(img_path) and text:
            image_text_pairs.append((img_path, text))

    if not image_text_pairs:
        raise HTTPException(status_code=400, detail="No valid image-text pairs")

    result = pipeline.generate_interleaved(image_text_pairs)

    return {
        "success": True,
        "result": result,
    }


@router.post("/api/data/mllm/qwenvl")
async def data_mllm_qwenvl(request: Request):
    """生成Qwen-VL格式（含OCR/版面分析）"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard.
    image_path = validated_path(body.get("image_path", ""))
    caption = body.get("caption", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_mllm_pipeline import MLLMDataPipeline
    pipeline = MLLMDataPipeline()
    result = pipeline.generate_qwenvl(image_path, caption=caption)

    return {
        "success": True,
        "id": result.get("id", ""),
        "image_path": result.get("image_path", image_path),
        "ocr_text": result.get("ocr_text", ""),
        "conversations": result.get("conversations", []),
        "layout_analysis": result.get("layout_analysis", {}),
    }
