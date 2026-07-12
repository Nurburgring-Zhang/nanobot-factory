"""标注管线路由 — pipeline与格式转换"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

# P21 P2 P2 — wire Injection.validate_path (R2-NEW-04 fix)
from backend.common.path_dep import validated_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/annotation/pipeline")
async def data_annotation_run(request: Request):
    """运行标注管线"""
    body = await request.json()
    # P21 P2 P2 — path-traversal guard on image_dir and output_dir.
    image_dir = validated_path(body.get("image_dir", ""))
    formats = body.get("formats", ["coco"])
    auto_label = body.get("auto_label", False)
    output_dir = validated_path(body.get("output_dir", "./data/annotations"))

    if not image_dir or not os.path.exists(image_dir):
        raise HTTPException(status_code=400, detail="Image directory not found")

    from data_annotation_pipeline import AnnotationPipeline, AnnotationFormat
    pipeline = AnnotationPipeline(output_dir=output_dir)

    fmt_list = []
    for f in formats:
        try:
            fmt_list.append(AnnotationFormat(f))
        except ValueError:
            pass

    result = pipeline.run_pipeline(image_dir, fmt_list, auto_label)
    return {"success": True, "result": result}


@router.post("/api/data/annotation/convert")
async def data_annotation_convert(request: Request):
    """标注格式转换"""
    body = await request.json()
    input_format = body.get("input_format", "coco")
    output_format = body.get("output_format", "yolo")
    # P21 P2 P2 — path-traversal guard on input_path and output_dir.
    input_path = validated_path(body.get("input_path", ""))
    output_dir = validated_path(body.get("output_dir", "./data/annotations"))

    from data_annotation_pipeline import AnnotationConverter, AnnotationDataset, AnnotationFormat

    converter = AnnotationConverter()

    if input_format == "coco" and os.path.exists(input_path):
        import json
        with open(input_path) as f:
            data = json.load(f)

        dataset = AnnotationDataset(name="converted")
        for img in data.get("images", []):
            from data_annotation_pipeline import AnnotationItem
            item = AnnotationItem(
                image_id=str(img["id"]),
                image_path=img.get("file_name", ""),
                width=img.get("width", 0),
                height=img.get("height", 0)
            )
            for ann in data.get("annotations", []):
                if ann["image_id"] == img["id"]:
                    from data_annotation_pipeline import BoundingBox
                    b = ann.get("bbox", [0, 0, 0, 0])
                    w = img.get("width", 1)
                    h = img.get("height", 1)
                    item.bboxes.append(BoundingBox(
                        x=b[0]/w, y=b[1]/h, width=b[2]/w, height=b[3]/h
                    ))
            dataset.items.append(item)

        if output_format == "yolo":
            out_path = converter.to_yolo(dataset, output_dir)
        elif output_format == "label_studio":
            ls = converter.to_label_studio(dataset)
            import json
            os.makedirs(output_dir, exist_ok=True)
            out_path = f"{output_dir}/label_studio.json"
            with open(out_path, "w") as f:
                json.dump(ls, f, indent=2)
        else:
            out_path = ""

        return {"success": True, "output": out_path, "items": len(dataset.items)}

    return {"success": False, "error": "Unsupported conversion"}
