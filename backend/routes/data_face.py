"""人脸管线路由"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/face/detect")
async def data_face_detect(request: Request):
    """人脸检测"""
    body = await request.json()
    image_path = body.get("image_path", "")
    min_size = body.get("min_size", 30)

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_face_pipeline import FacePipeline
    pipeline = FacePipeline()
    faces = pipeline.detect_faces(image_path, min_size=min_size)

    results = []
    for face in faces:
        results.append({
            "id": face.id,
            "bbox": list(face.bbox),
            "confidence": face.confidence,
            "quality": face.quality,
            "yaw": face.yaw,
            "pitch": face.pitch,
            "roll": getattr(face, "roll", 0.0),
            "landmarks_68": face.landmarks_2d if face.landmarks_2d else [],
        })

    return {
        "success": True,
        "total_faces": len(results),
        "faces": results,
    }


@router.post("/api/data/face/landmarks")
async def data_face_landmarks(request: Request):
    """人脸关键点（68点）"""
    body = await request.json()
    image_path = body.get("image_path", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_face_pipeline import FacePipeline
    pipeline = FacePipeline()
    faces = pipeline.detect_faces(image_path)
    if not faces:
        return {"success": True, "total_faces": 0, "landmarks": []}

    results = []
    for face in faces[:1]:  # 主脸
        landmarks = face.landmarks
        if landmarks:
            points = landmarks.to_list()
            results.append({
                "face_id": face.id,
                "bbox": list(face.bbox),
                "landmarks_68": [(float(x), float(y)) for x, y in points],
                "confidence": face.confidence,
            })

    return {
        "success": True,
        "total_faces": len(results),
        "landmarks": results,
    }


@router.post("/api/data/face/format")
async def data_face_format(request: Request):
    """人脸格式转换 (IP-Adapter / ArcFace / FaceSwap)"""
    body = await request.json()
    image_path = body.get("image_path", "")
    format_type = body.get("format", "ip_adapter")
    output_path = body.get("output_path", "./data/face_output")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_face_pipeline import FacePipeline
    pipeline = FacePipeline()
    faces = pipeline.detect_faces(image_path)

    os.makedirs(output_path, exist_ok=True)

    if format_type == "ip_adapter":
        items = []
        for face in faces:
            from data_face_pipeline import IPAdapterFaceItem
            items.append(IPAdapterFaceItem(
                id=face.id,
                person_image=image_path,
                style_images=[image_path],
                identity=face.id,
            ))
        out_file = os.path.join(output_path, "ip_adapter_output.jsonl")
        pipeline.save_ip_adapter_jsonl(items, out_file)

    elif format_type == "arcface":
        for face in faces:
            import shutil
            face_dir = os.path.join(output_path, f"identity_{face.id}")
            os.makedirs(face_dir, exist_ok=True)
            dest = os.path.join(face_dir, os.path.basename(image_path))
            shutil.copy2(image_path, dest)
        out_file = output_path

    elif format_type == "faceswap":
        items = []
        for face in faces:
            from data_face_pipeline import FaceSwapItem
            items.append(FaceSwapItem(
                id=face.id,
                source_image=image_path,
                target_image=image_path,
                source_face=face,
                target_face=face,
                landmarks_68=face.landmarks_2d if face.landmarks_2d else [],
            ))
        out_file = os.path.join(output_path, "faceswap_output.jsonl")
        pipeline.save_faceswap_jsonl(items, out_file)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format_type}")

    return {
        "success": True,
        "format": format_type,
        "output_path": str(out_file),
        "total_faces": len(faces),
    }
