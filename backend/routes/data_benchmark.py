"""多模态评测数据生成路由 — MMMU/VQA/LLaVA/VBench"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

# P21 P2 P2 — wire Injection.validate_path (R2-NEW-04 fix)
from backend.common.path_dep import validated_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/benchmark/generate")
async def data_benchmark_generate(request: Request):
    """多模态评测数据生成 — MMMU/VQA/LLaVA/VBench"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard on image_path and output_dir.
    dataset_name = body.get("name", "multimodal_benchmark")
    image_path = validated_path(body.get("image_path", ""))
    subjects = body.get("subjects", None)
    num_vqa = body.get("num_vqa", 10)
    output_dir = validated_path(body.get("output_dir", "./data/benchmark"))

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
