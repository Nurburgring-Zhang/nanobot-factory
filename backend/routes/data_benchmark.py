"""多模态评测数据生成路由 — MMMU/VQA/LLaVA/VBench"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/benchmark/generate")
async def data_benchmark_generate(request: Request):
    """多模态评测数据生成 — MMMU/VQA/LLaVA/VBench"""
    body = await request.json()
    dataset_name = body.get("name", "multimodal_benchmark")
    image_path = body.get("image_path", "")
    subjects = body.get("subjects", None)
    num_vqa = body.get("num_vqa", 10)
    output_dir = body.get("output_dir", "./data/benchmark")

    from data_multimodal_benchmark import get_benchmark_generator
    gen = get_benchmark_generator()

    # 验证图像
    img = None
    if image_path and os.path.exists(image_path):
        img = image_path

    dataset = gen.generate_full_benchmark(
        name=dataset_name,
        image=img,
        subjects=subjects,
        num_vqa=num_vqa,
    )

    out_path = gen.save_hf_format(dataset, output_dir=output_dir)

    return {
        "success": True,
        "output_dir": out_path,
        "stats": {
            "questions": len(dataset.questions),
            "vqa_pairs": len(dataset.vqa_pairs),
            "conversations": len(dataset.conversations),
            "vbench_items": len(dataset.vbench_items),
        },
    }
