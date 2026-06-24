#!/usr/bin/env python3
"""
多模态标注 API 路由
Multimodal Annotation API Routes
# STATUS: planned — 多模态标注v2，前端未调用 (Phase 2: 视频帧标注 + 音频波形标注)

Phase 2: 视频帧标注 + 音频波形标注 + 标注CRUD
"""

import logging
import os
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/v2/annotations", tags=["多模态标注"])

# 延迟导入管理器
_annotation_manager = None


def get_annotation_manager():
    """获取多模态标注管理器"""
    global _annotation_manager
    if _annotation_manager is None:
        try:
            from core.multimodal_annotation import (
                MultimodalAnnotationManager, MediaType, AnnotationType,
                VideoAnnotation, AudioAnnotation, get_annotation_manager
            )
            _annotation_manager = get_annotation_manager()
        except ImportError as e:
            logger.error(f"multimodal_annotation module not found: {e}")
            return None
    return _annotation_manager


# ==================== 请求/响应模型 ====================

class ExtractFramesRequest(BaseModel):
    video_path: str = Field(..., description="视频文件路径")
    interval: int = Field(default=30, description="帧提取间隔（帧数）")


class TranscribeRequest(BaseModel):
    audio_path: str = Field(..., description="音频文件路径")


class CreateAnnotationRequest(BaseModel):
    media_id: str = Field(..., description="媒体ID")
    media_type: str = Field(..., description="媒体类型: image/video/audio/text")
    annotation_type: str = Field(..., description="标注类型: bbox/polygon/keypoint/segmentation/transcript/classification")
    data: dict = Field(..., description="标注数据")


class UpdateAnnotationRequest(BaseModel):
    data: dict = Field(..., description="更新后的标注数据")


# ==================== 视频标注端点 ====================

@router.post("/video/extract-frames")
async def extract_frames(req: ExtractFramesRequest):
    """视频帧提取——从视频中按间隔提取帧"""
    try:
        from core.multimodal_annotation import VideoAnnotation
        frames_raw = VideoAnnotation.extract_frames(req.video_path, req.interval)
        # numpy array不可序列化，转为元数据
        frames_meta = []
        for f in frames_raw:
            frames_meta.append({
                "frame_index": f["frame_index"],
                "timestamp": f["timestamp"],
                "width": f["width"],
                "height": f["height"]
            })
        return {
            "success": True,
            "data": {
                "total_frames": len(frames_meta),
                "interval": req.interval,
                "frames": frames_meta
            }
        }
    except Exception as e:
        logger.exception("Failed to extract frames")
        return {"success": False, "error": str(e)}


# ==================== 音频标注端点 ====================

@router.post("/audio/transcribe")
async def transcribe_audio(req: TranscribeRequest):
    """音频转写——音频文本识别"""
    try:
        from core.multimodal_annotation import AudioAnnotation
        result = AudioAnnotation.transcribe(req.audio_path)
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.exception("Failed to transcribe audio")
        return {"success": False, "error": str(e)}


@router.post("/audio/waveform")
async def get_audio_waveform(
    audio_path: str = Body(..., embed=True),
    samples: int = Body(200, embed=True)
):
    """音频波形——提取音频波形数据"""
    try:
        from core.multimodal_annotation import AudioAnnotation
        waveform = AudioAnnotation.get_waveform(audio_path, samples)
        return {
            "success": True,
            "data": {
                "waveform": waveform,
                "samples": len(waveform)
            }
        }
    except Exception as e:
        logger.exception("Failed to get waveform")
        return {"success": False, "error": str(e)}


# ==================== 标注CRUD端点 ====================

@router.post("/create")
async def create_annotation(req: CreateAnnotationRequest):
    """创建标注"""
    try:
        mgr = get_annotation_manager()
        if mgr is None:
            return {"success": False, "error": "Annotation manager not available"}
        from core.multimodal_annotation import MediaType, AnnotationType
        ann_id = mgr.create_annotation(
            media_id=req.media_id,
            media_type=MediaType(req.media_type),
            annotation_type=AnnotationType(req.annotation_type),
            data=req.data
        )
        return {"success": True, "data": {"annotation_id": ann_id}}
    except Exception as e:
        logger.exception("Failed to create annotation")
        return {"success": False, "error": str(e)}


@router.get("/{media_id}")
async def get_annotations(media_id: str):
    """获取媒体ID对应的标注列表"""
    try:
        mgr = get_annotation_manager()
        if mgr is None:
            return {"success": False, "error": "Annotation manager not available"}
        annotations = mgr.get_annotations(media_id)
        return {"success": True, "data": annotations, "count": len(annotations)}
    except Exception as e:
        logger.exception("Failed to get annotations")
        return {"success": False, "error": str(e)}


@router.put("/{ann_id}")
async def update_annotation(ann_id: str, req: UpdateAnnotationRequest):
    """更新标注"""
    try:
        mgr = get_annotation_manager()
        if mgr is None:
            return {"success": False, "error": "Annotation manager not available"}
        ok = mgr.update_annotation(ann_id, req.data)
        if ok:
            return {"success": True, "message": f"Annotation {ann_id} updated"}
        return {"success": False, "error": f"Annotation {ann_id} not found"}
    except Exception as e:
        logger.exception("Failed to update annotation")
        return {"success": False, "error": str(e)}


@router.delete("/{ann_id}")
async def delete_annotation(ann_id: str):
    """删除标注"""
    try:
        mgr = get_annotation_manager()
        if mgr is None:
            return {"success": False, "error": "Annotation manager not available"}
        ok = mgr.delete_annotation(ann_id)
        if ok:
            return {"success": True, "message": f"Annotation {ann_id} deleted"}
        return {"success": False, "error": f"Annotation {ann_id} not found"}
    except Exception as e:
        logger.exception("Failed to delete annotation")
        return {"success": False, "error": str(e)}
