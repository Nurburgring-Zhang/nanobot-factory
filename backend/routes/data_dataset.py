"""数据集导出与统计路由 + 桶分配 + Caption Dropout"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# 原有路由
# ============================================================================


@router.post("/api/data/dataset/export")
async def data_dataset_export(request: Request):
    """导出数据集"""
    body = await request.json()
    input_dir = body.get("input_dir", "")
    format_type = body.get("format", "hf_json")
    output_path = body.get("output_path", "./data/dataset_export")
    split_ratios = body.get("split_ratios", [0.8, 0.1, 0.1])

    if not input_dir or not os.path.exists(input_dir):
        raise HTTPException(status_code=400, detail="Input directory not found")

    from data_dataset_manager import DatasetManager

    manager = DatasetManager(base_dir=output_path)
    dataset_entries = manager.create_from_image_dir("exported", input_dir)
    splits = manager.split_dataset(dataset_entries,
                                     train_ratio=split_ratios[0],
                                     val_ratio=split_ratios[1],
                                     test_ratio=split_ratios[2])

    if format_type == "huggingface" or format_type == "hf_json":
        out = manager.create_hf_json("dataset", dataset_entries)
    elif format_type == "webdataset" or format_type == "tar":
        out = manager.create_webdataset("dataset", dataset_entries)
    else:
        out = manager.create_hf_json("dataset", dataset_entries)

    return {"success": True, "output_path": str(out), "total": len(dataset_entries)}


@router.get("/api/data/dataset/stats")
async def data_dataset_stats(request: Request):
    """数据集统计"""
    path = request.query_params.get("path", "./data/dataset_export")

    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail="Dataset path not found")

    from data_dataset_manager import DatasetManager, compute_stats
    manager = DatasetManager()
    path_entries = manager.load_hf_json(path) if os.path.isdir(path) else []
    stats = compute_stats(path_entries)

    # 确保所有值可JSON序列化
    def _ser(obj):
        import pathlib
        if isinstance(obj, pathlib.PosixPath) or isinstance(obj, pathlib.WindowsPath):
            return str(obj)
        if isinstance(obj, dict):
            return {k: _ser(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_ser(i) for i in obj]
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        return obj

    import numpy as np
    stats = _ser(stats)

    return {"success": True, "stats": stats}


# ============================================================================
# 分辨率桶分配
# ============================================================================


@router.post("/api/data/dataset/bucket")
async def data_dataset_bucket(request: Request):
    """分辨率桶分配 — 对齐FLUX/SDXL/DiT标准"""
    body = await request.json()
    width = body.get("width", 0)
    height = body.get("height", 0)
    bucket_type = body.get("bucket_type", "flux")
    images = body.get("images", None)  # 可选: [{"width": w, "height": h}, ...]

    from data_dataset_manager import ResolutionBucketAssigner

    assigner = ResolutionBucketAssigner(bucket_type=bucket_type)

    if images:
        # 批量分配
        dims = [(img["width"], img["height"]) for img in images]
        assignments = assigner.batch_assign(dims)
        stats = assigner.bucket_stats(assignments)
        buckets = assigner.list_buckets()
        results = []
        for i, (img, a) in enumerate(zip(images, assignments)):
            results.append({
                "index": i,
                "width": a.width,
                "height": a.height,
                "bucket_id": a.bucket_id,
                "bucket_width": a.bucket_width,
                "bucket_height": a.bucket_height,
                "padding": a.padding,
                "crop": a.crop,
                "scale": a.scale,
            })
        return {
            "success": True,
            "total": len(results),
            "assignments": results,
            "bucket_stats": stats,
            "buckets": buckets,
        }
    else:
        # 单张分配
        assignment = assigner.assign(width, height)
        return {
            "success": True,
            "width": assignment.width,
            "height": assignment.height,
            "bucket_id": assignment.bucket_id,
            "bucket_width": assignment.bucket_width,
            "bucket_height": assignment.bucket_height,
            "padding": assignment.padding,
            "crop": assignment.crop,
            "scale": assignment.scale,
        }


# ============================================================================
# Caption Dropout
# ============================================================================


@router.post("/api/data/dataset/caption-dropout")
async def data_dataset_caption_dropout(request: Request):
    """Caption Dropout — 增强训练鲁棒性"""
    body = await request.json()
    caption = body.get("caption", "")
    captions = body.get("captions", None)
    full_drop_rate = body.get("full_drop_rate", 0.1)
    word_drop_rate = body.get("word_drop_rate", 0.2)
    shuffle_rate = body.get("shuffle_rate", 0.1)

    from data_dataset_manager import CaptionDropoutProcessor

    processor = CaptionDropoutProcessor(
        full_drop_rate=full_drop_rate,
        word_drop_rate=word_drop_rate,
        shuffle_rate=shuffle_rate,
    )

    if captions is not None:
        # 批量处理
        results = processor.batch_apply(captions)
        stats = processor.stats(results)
        return {
            "success": True,
            "total": len(results),
            "results": [
                {
                    "original": r.original,
                    "dropped": r.dropped,
                    "drop_type": r.drop_type,
                }
                for r in results
            ],
            "stats": stats,
        }
    else:
        # 单条处理
        result = processor.apply(caption)
        return {
            "success": True,
            "original": result.original,
            "dropped": result.dropped,
            "drop_type": result.drop_type,
        }
