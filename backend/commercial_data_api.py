#!/usr/bin/env python3
"""
商业数据管理 API 路由
Commercial Data Management API Routes
# STATUS: active — 部分路由被前端调用 (oss/upload, oss/status等)
# 路由数: 46 | 实际使用: ~5 (oss/status, oss/upload)

集成以下模块:
- OSS存储管理 (oss_storage.py)
- 标注系统 (annotation_system.py)
- 图片筛选与对比 (image_filter_compare.py)
- 数据集构建 (dataset_builder.py)

@author Matrix Agent
@date 2025
"""

import os
import json
import uuid
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ============================================================================
# 全局变量
# ============================================================================

# 全局管理器实例
_oss_storage_manager = None
_annotation_manager = None
_filter_engine = None
_compare_engine = None
_dataset_builder = None


def get_oss_manager():
    """获取OSS存储管理器"""
    global _oss_storage_manager
    if _oss_storage_manager is None:
        from oss_storage import OSSStorageManager
        _oss_storage_manager = OSSStorageManager()
    return _oss_storage_manager


def get_annotation_manager():
    """获取标注管理器"""
    global _annotation_manager
    if _annotation_manager is None:
        from annotation_system import AnnotationManager
        _annotation_manager = AnnotationManager()
    return _annotation_manager


def get_filter_engine():
    """获取图片筛选引擎"""
    global _filter_engine
    if _filter_engine is None:
        from image_filter_compare import ImageFilterEngine
        _filter_engine = ImageFilterEngine()
    return _filter_engine


def get_compare_engine():
    """获取图片对比引擎"""
    global _compare_engine
    if _compare_engine is None:
        from image_filter_compare import ImageCompareEngine
        _compare_engine = ImageCompareEngine()
    return _compare_engine


def get_dataset_builder():
    """获取数据集构建器"""
    global _dataset_builder
    if _dataset_builder is None:
        from dataset_builder import DatasetBuilder
        _dataset_builder = DatasetBuilder()
    return _dataset_builder


# ============================================================================
# 请求/响应模型
# ============================================================================

class OSSConfigRequest(BaseModel):
    """OSS配置请求"""
    access_key_id: str = Field(..., description="Access Key ID")
    access_key_secret: str = Field(..., description="Access Key Secret")
    bucket_name: str = Field(..., description="Bucket名称")
    endpoint: str = Field(default="oss-cn-hangzhou.aliyuncs.com", description="OSS端点")
    region: str = Field(default="cn-hangzhou", description="区域")
    cdn_domain: Optional[str] = Field(default="", description="CDN域名")
    image_prefix: str = Field(default="assets/images/", description="图片路径前缀")
    video_prefix: str = Field(default="assets/videos/", description="视频路径前缀")


class FilterConditionRequest(BaseModel):
    """筛选条件请求"""
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, contains, starts_with, ends_with, between, in_list, is_empty
    value: Any
    second_value: Optional[Any] = None  # 用于between操作


class FilterGroupRequest(BaseModel):
    """筛选组请求"""
    logic: str = "AND"  # AND 或 OR
    conditions: List[FilterConditionRequest] = []


class AnnotationCreateRequest(BaseModel):
    """标注创建请求"""
    asset_id: str
    annotation_type: str  # bounding_box, polygon, keypoints, classification, text, mask
    label_id: str
    bbox: Optional[Dict[str, float]] = None
    points: Optional[List[Dict[str, float]]] = None
    text: Optional[str] = None
    classification: Optional[str] = None
    confidence: float = 1.0


class AnnotationUpdateRequest(BaseModel):
    """标注更新请求"""
    label_id: Optional[str] = None
    bbox: Optional[Dict[str, float]] = None
    points: Optional[List[Dict[str, float]]] = None
    text: Optional[str] = None
    classification: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    is_verified: Optional[bool] = None


class CompareRequest(BaseModel):
    """对比请求"""
    asset_ids: List[str]
    mode: str = "side_by_side"  # side_by_side, slide, diff, grid
    metric: str = "ssim"  # ssim, histogram, perceptual_hash


class DatasetExportRequest(BaseModel):
    """数据集导出请求"""
    name: str
    format: str = "coco"  # coco, yolo, imagenet, voc, csv, json
    split_mode: str = "random"  # random, stratified, time_based, k_fold
    train_ratio: float = 0.7
    val_ratio: float = 0.2
    test_ratio: float = 0.1
    asset_ids: Optional[List[str]] = None
    filter_config: Optional[FilterGroupRequest] = None
    output_dir: str = "./exports"


# ============================================================================
# 路由器
# ============================================================================

router = APIRouter(prefix="/api/commercial", tags=["商业数据管理"])


# ============================================================================
# OSS 存储管理 API
# ============================================================================

@router.get("/oss/config")
async def get_oss_config():
    """获取OSS配置状态"""
    try:
        manager = get_oss_manager()
        config = manager.get_config()
        return {
            "enabled": config.enabled,
            "bucket_name": config.bucket_name,
            "endpoint": config.endpoint,
            "region": config.region,
            "cdn_domain": config.cdn_domain,
            "image_prefix": config.image_prefix,
            "video_prefix": config.video_prefix
        }
    except Exception as e:
        logger.error(f"获取OSS配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/oss/config")
async def configure_oss(request: OSSConfigRequest):
    """配置OSS存储"""
    try:
        from oss_storage import OSSConfig, OSSStorageManager
        
        config = OSSConfig(
            access_key_id=request.access_key_id,
            access_key_secret=request.access_key_secret,
            bucket_name=request.bucket_name,
            endpoint=request.endpoint,
            region=request.region,
            cdn_domain=request.cdn_domain,
            image_prefix=request.image_prefix,
            video_prefix=request.video_prefix,
            enabled=True
        )
        
        global _oss_storage_manager
        _oss_storage_manager = OSSStorageManager(config)
        
        # 保存配置到文件
        config_path = Path.home() / ".nanobot-factory" / "oss_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        config_data = {
            "access_key_id": request.access_key_id,
            "access_key_secret": request.access_key_secret,
            "bucket_name": request.bucket_name,
            "endpoint": request.endpoint,
            "region": request.region,
            "cdn_domain": request.cdn_domain,
            "image_prefix": request.image_prefix,
            "video_prefix": request.video_prefix,
            "enabled": True
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return {"success": True, "message": "OSS配置成功"}
    except Exception as e:
        logger.error(f"OSS配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/oss/upload")
async def upload_to_oss(
    file: UploadFile = File(...),
    asset_type: str = Form("image"),
    folder: str = Form("")
):
    """上传文件到OSS"""
    try:
        manager = get_oss_manager()
        
        # 读取文件内容
        content = await file.read()
        
        # 上传
        result = await manager.upload_file(
            file_data=content,
            file_name=file.filename,
            asset_type=asset_type,
            folder=folder
        )
        
        return {
            "success": True,
            "file_name": result.get("file_name"),
            "oss_key": result.get("oss_key"),
            "url": result.get("url"),
            "size": len(content)
        }
    except Exception as e:
        logger.error(f"上传到OSS失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oss/download/{oss_key:path}")
async def download_from_oss(oss_key: str):
    """从OSS下载文件"""
    try:
        manager = get_oss_manager()
        file_data, content_type = await manager.download_file(oss_key)
        
        return StreamingResponse(
            iter([file_data]),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={os.path.basename(oss_key)}"}
        )
    except Exception as e:
        logger.error(f"从OSS下载失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oss/url/{oss_key:path}")
async def get_oss_url(oss_key: str, expires: int = 3600):
    """获取OSS文件访问URL"""
    try:
        manager = get_oss_manager()
        url = await manager.get_signed_url(oss_key, expires=expires)
        return {"url": url, "expires": expires}
    except Exception as e:
        logger.error(f"获取OSS URL失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oss/buckets")
async def list_oss_buckets():
    """列出OSS存储桶"""
    try:
        manager = get_oss_manager()
        buckets = await manager.list_buckets()
        return {"buckets": buckets}
    except Exception as e:
        logger.error(f"列出OSS存储桶失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oss/files")
async def list_oss_files(
    prefix: str = "",
    max_keys: int = 100,
    marker: str = ""
):
    """列出OSS文件"""
    try:
        manager = get_oss_manager()
        files = await manager.list_files(prefix, max_keys, marker)
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"列出OSS文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/oss/file/{oss_key:path}")
async def delete_oss_file(oss_key: str):
    """删除OSS文件"""
    try:
        manager = get_oss_manager()
        success = await manager.delete_file(oss_key)
        return {"success": success}
    except Exception as e:
        logger.error(f"删除OSS文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oss/stats")
async def get_oss_stats():
    """获取OSS存储统计"""
    try:
        manager = get_oss_manager()
        stats = await manager.get_bucket_stats()
        return stats
    except Exception as e:
        logger.error(f"获取OSS统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 标注系统 API
# ============================================================================

@router.get("/annotations/labels")
async def get_annotation_labels():
    """获取所有标注标签"""
    try:
        manager = get_annotation_manager()
        labels = manager.get_labels()
        return {"labels": labels}
    except Exception as e:
        logger.error(f"获取标注标签失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotations/labels")
async def create_annotation_label(request: Dict[str, Any]):
    """创建标注标签"""
    try:
        manager = get_annotation_manager()
        label_id = request.get("id", str(uuid.uuid4()))
        name = request.get("name", "")
        color = request.get("color", "#FF5733")
        category = request.get("category", "default")
        description = request.get("description", "")
        
        label = manager.create_label(label_id, name, color, category, description)
        
        return {"success": True, "label": label}
    except Exception as e:
        logger.error(f"创建标注标签失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/annotations/labels/{label_id}")
async def delete_annotation_label(label_id: str):
    """删除标注标签"""
    try:
        manager = get_annotation_manager()
        success = manager.delete_label(label_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"删除标注标签失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/annotations/asset/{asset_id}")
async def get_asset_annotations(asset_id: str):
    """获取资产的标注"""
    try:
        manager = get_annotation_manager()
        annotations = manager.get_asset_annotations(asset_id)
        return {"annotations": annotations}
    except Exception as e:
        logger.error(f"获取资产标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotations")
async def create_annotation(request: AnnotationCreateRequest):
    """创建标注"""
    try:
        manager = get_annotation_manager()
        
        annotation = manager.create_annotation(
            asset_id=request.asset_id,
            annotation_type=request.annotation_type,
            label_id=request.label_id,
            bbox=request.bbox,
            points=request.points,
            text=request.text,
            classification=request.classification,
            confidence=request.confidence
        )
        
        return {"success": True, "annotation": annotation}
    except Exception as e:
        logger.error(f"创建标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/annotations/{annotation_id}")
async def update_annotation(annotation_id: str, request: AnnotationUpdateRequest):
    """更新标注"""
    try:
        manager = get_annotation_manager()
        
        update_data = {}
        if request.label_id is not None:
            update_data["label_id"] = request.label_id
        if request.bbox is not None:
            update_data["bbox"] = request.bbox
        if request.points is not None:
            update_data["points"] = request.points
        if request.text is not None:
            update_data["text"] = request.text
        if request.classification is not None:
            update_data["classification"] = request.classification
        if request.confidence is not None:
            update_data["confidence"] = request.confidence
        if request.notes is not None:
            update_data["notes"] = request.notes
        if request.is_verified is not None:
            update_data["is_verified"] = request.is_verified
        
        success = manager.update_annotation(annotation_id, update_data)
        return {"success": success}
    except Exception as e:
        logger.error(f"更新标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """删除标注"""
    try:
        manager = get_annotation_manager()
        success = manager.delete_annotation(annotation_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"删除标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotations/{annotation_id}/verify")
async def verify_annotation(annotation_id: str):
    """验证标注"""
    try:
        manager = get_annotation_manager()
        success = manager.verify_annotation(annotation_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"验证标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotations/{annotation_id}/approve")
async def approve_annotation(annotation_id: str):
    """批准标注"""
    try:
        manager = get_annotation_manager()
        success = manager.approve_annotation(annotation_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"批准标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotations/{annotation_id}/reject")
async def reject_annotation(annotation_id: str, reason: str = ""):
    """拒绝标注"""
    try:
        manager = get_annotation_manager()
        success = manager.reject_annotation(annotation_id, reason)
        return {"success": success}
    except Exception as e:
        logger.error(f"拒绝标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/annotations/export")
async def export_annotations(
    asset_ids: List[str],
    format: str = "coco"
):
    """导出标注"""
    try:
        manager = get_annotation_manager()
        
        if format == "coco":
            result = manager.export_coco(asset_ids)
        elif format == "yolo":
            result = manager.export_yolo(asset_ids)
        elif format == "voc":
            result = manager.export_voc(asset_ids)
        else:
            raise ValueError(f"不支持的导出格式: {format}")
        
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"导出标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 图片筛选 API
# ============================================================================

@router.post("/filter/assets")
async def filter_assets(
    request: FilterGroupRequest,
    limit: int = 100,
    offset: int = 0
):
    """筛选资产"""
    try:
        engine = get_filter_engine()
        
        # 转换请求为引擎可用的格式
        from image_filter_compare import FilterGroup, FilterCondition, FilterOperator
        
        conditions = []
        for cond in request.conditions:
            try:
                op = FilterOperator(cond.operator)
            except ValueError:
                op = FilterOperator.EQUALS
            
            conditions.append(FilterCondition(
                field=cond.field,
                operator=op,
                value=cond.value,
                second_value=cond.second_value
            ))
        
        filter_group = FilterGroup(
            logic=getattr(import_module('image_filter_compare'), 'LogicOperator').AND if request.logic == "AND" 
                   else getattr(import_module('image_filter_compare'), 'LogicOperator').OR,
            conditions=conditions
        )
        
        assets = engine.filter_assets(filter_group, limit, offset)
        
        return {"assets": assets, "count": len(assets)}
    except Exception as e:
        logger.error(f"筛选资产失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/filter/presets")
async def apply_filter_preset(
    preset_name: str,
    limit: int = 100
):
    """应用预设筛选"""
    try:
        engine = get_filter_engine()
        assets = engine.apply_preset(preset_name, limit)
        return {"assets": assets, "count": len(assets)}
    except Exception as e:
        logger.error(f"应用预设筛选失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/filter/presets")
async def get_filter_presets():
    """获取所有预设筛选"""
    try:
        from image_filter_compare import SmartFilterBuilder
        builder = SmartFilterBuilder()
        presets = builder.get_presets()
        return {"presets": presets}
    except Exception as e:
        logger.error(f"获取预设筛选失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/filter/fields")
async def get_filter_fields():
    """获取可用的筛选字段"""
    try:
        engine = get_filter_engine()
        fields = engine.get_available_fields()
        return {"fields": fields}
    except Exception as e:
        logger.error(f"获取筛选字段失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/filter/stats")
async def get_filter_stats():
    """获取筛选统计"""
    try:
        engine = get_filter_engine()
        stats = engine.get_stats()
        return stats
    except Exception as e:
        logger.error(f"获取筛选统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 图片对比 API
# ============================================================================

@router.post("/compare")
async def compare_images(request: CompareRequest):
    """对比图片"""
    try:
        engine = get_compare_engine()
        
        if len(request.asset_ids) < 2:
            raise ValueError("至少需要2个资产进行对比")
        
        if request.mode == "side_by_side":
            result = engine.compare_side_by_side(request.asset_ids)
        elif request.mode == "grid":
            result = engine.compare_grid(request.asset_ids)
        elif request.mode == "diff":
            result = engine.compare_diff(request.asset_ids[0], request.asset_ids[1])
        else:
            raise ValueError(f"不支持的对比模式: {request.mode}")
        
        return {
            "success": True,
            "mode": request.mode,
            "result": result
        }
    except Exception as e:
        logger.error(f"对比图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare/similarity")
async def compare_similarity(asset_id1: str, asset_id2: str, metric: str = "ssim"):
    """计算图片相似度"""
    try:
        engine = get_compare_engine()
        
        if metric == "ssim":
            similarity = engine.compare_ssim(asset_id1, asset_id2)
        elif metric == "histogram":
            similarity = engine.compare_histogram(asset_id1, asset_id2)
        elif metric == "perceptual_hash":
            similarity = engine.compare_perceptual_hash(asset_id1, asset_id2)
        else:
            raise ValueError(f"不支持的相似度度量: {metric}")
        
        return {
            "asset_id1": asset_id1,
            "asset_id2": asset_id2,
            "metric": metric,
            "similarity": similarity
        }
    except Exception as e:
        logger.error(f"计算相似度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare/slide")
async def generate_slide_comparison(asset_id1: str, asset_id2: str):
    """生成分屏对比"""
    try:
        engine = get_compare_engine()
        result = engine.generate_slide_comparison(asset_id1, asset_id2)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"生成分屏对比失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare/diff")
async def generate_diff_image(asset_id1: str, asset_id2: str):
    """生成差异图像"""
    try:
        engine = get_compare_engine()
        result = engine.generate_diff_image(asset_id1, asset_id2)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"生成差异图像失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare/modes")
async def get_compare_modes():
    """获取支持的对比模式"""
    return {
        "modes": [
            {"id": "side_by_side", "name": "并排对比", "description": "左右并排显示两张图片"},
            {"id": "grid", "name": "网格对比", "description": "以网格形式展示多张图片"},
            {"id": "slide", "name": "滑块对比", "description": "使用滑块分割两张图片"},
            {"id": "diff", "name": "差异对比", "description": "高亮显示两张图片的差异"}
        ]
    }


# ============================================================================
# 数据集构建 API
# ============================================================================

@router.get("/datasets")
async def list_datasets():
    """列出所有数据集"""
    try:
        builder = get_dataset_builder()
        datasets = builder.list_datasets()
        return {"datasets": datasets}
    except Exception as e:
        logger.error(f"列出数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets")
async def create_dataset(request: Dict[str, Any]):
    """创建数据集"""
    try:
        builder = get_dataset_builder()
        
        dataset_id = request.get("id", str(uuid.uuid4()))
        name = request.get("name", "")
        description = request.get("description", "")
        format_type = request.get("format", "coco")
        
        dataset = builder.create_dataset(
            dataset_id=dataset_id,
            name=name,
            description=description,
            format_type=format_type
        )
        
        return {"success": True, "dataset": dataset}
    except Exception as e:
        logger.error(f"创建数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    """获取数据集详情"""
    try:
        builder = get_dataset_builder()
        dataset = builder.get_dataset(dataset_id)
        
        if not dataset:
            raise HTTPException(status_code=404, detail="数据集不存在")
        
        return dataset
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """删除数据集"""
    try:
        builder = get_dataset_builder()
        success = builder.delete_dataset(dataset_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"删除数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets/{dataset_id}/assets")
async def add_assets_to_dataset(
    dataset_id: str,
    request: Dict[str, Any]
):
    """添加资产到数据集"""
    try:
        builder = get_dataset_builder()
        
        asset_ids = request.get("asset_ids", [])
        if not asset_ids:
            raise ValueError("asset_ids不能为空")
        
        success = builder.add_assets(dataset_id, asset_ids)
        return {"success": success, "added": len(asset_ids)}
    except Exception as e:
        logger.error(f"添加资产到数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/datasets/{dataset_id}/assets")
async def remove_assets_from_dataset(
    dataset_id: str,
    request: Dict[str, Any]
):
    """从数据集移除资产"""
    try:
        builder = get_dataset_builder()
        
        asset_ids = request.get("asset_ids", [])
        success = builder.remove_assets(dataset_id, asset_ids)
        return {"success": success}
    except Exception as e:
        logger.error(f"从数据集移除资产失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: str,
    request: DatasetExportRequest
):
    """导出数据集"""
    try:
        builder = get_dataset_builder()
        
        # 获取数据集
        dataset = builder.get_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="数据集不存在")
        
        # 执行导出
        if request.format == "coco":
            result = builder.export_coco(dataset_id, request.output_dir)
        elif request.format == "yolo":
            result = builder.export_yolo(dataset_id, request.output_dir)
        elif request.format == "imagenet":
            result = builder.export_imagenet(dataset_id, request.output_dir)
        elif request.format == "voc":
            result = builder.export_voc(dataset_id, request.output_dir)
        elif request.format == "csv":
            result = builder.export_csv(dataset_id, request.output_dir)
        elif request.format == "json":
            result = builder.export_json(dataset_id, request.output_dir)
        else:
            raise ValueError(f"不支持的导出格式: {request.format}")
        
        return {
            "success": True,
            "format": request.format,
            "output_dir": request.output_dir,
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets/{dataset_id}/split")
async def split_dataset(
    dataset_id: str,
    request: DatasetExportRequest
):
    """划分数据集"""
    try:
        builder = get_dataset_builder()
        
        from dataset_builder import SplitMode
        split_mode = SplitMode(request.split_mode)
        
        result = builder.split_dataset(
            dataset_id=dataset_id,
            split_mode=split_mode,
            train_ratio=request.train_ratio,
            val_ratio=request.val_ratio,
            test_ratio=request.test_ratio
        )
        
        return {
            "success": True,
            "split": result
        }
    except Exception as e:
        logger.error(f"划分数据集失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}/stats")
async def get_dataset_stats(dataset_id: str):
    """获取数据集统计"""
    try:
        builder = get_dataset_builder()
        stats = builder.get_dataset_stats(dataset_id)
        return stats
    except Exception as e:
        logger.error(f"获取数据集统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/formats")
async def get_dataset_formats():
    """获取支持的导出格式"""
    return {
        "formats": [
            {"id": "coco", "name": "COCO", "description": "COCO数据集格式，适用于目标检测、分割等任务"},
            {"id": "yolo", "name": "YOLO", "description": "YOLO格式，适用于YOLO系列模型训练"},
            {"id": "imagenet", "name": "ImageNet", "description": "ImageNet格式，适用于图像分类任务"},
            {"id": "voc", "name": "VOC", "description": "Pascal VOC格式，适用于目标检测和分割"},
            {"id": "csv", "name": "CSV", "description": "CSV格式，通用表格数据格式"},
            {"id": "json", "name": "JSON", "description": "JSON格式，通用数据交换格式"}
        ]
    }


@router.get("/datasets/split-modes")
async def get_split_modes():
    """获取数据划分模式"""
    return {
        "split_modes": [
            {"id": "random", "name": "随机划分", "description": "随机将数据划分为训练集、验证集、测试集"},
            {"id": "stratified", "name": "分层抽样", "description": "按标签比例进行划分，保持各类别比例一致"},
            {"id": "time_based", "name": "时间划分", "description": "按时间顺序划分，常用于时序数据"},
            {"id": "k_fold", "name": "K折交叉验证", "description": "将数据分成K份，用于交叉验证"}
        ]
    }


@router.post("/datasets/{dataset_id}/deduplicate")
async def deduplicate_dataset(dataset_id: str, threshold: float = 0.9):
    """数据集去重"""
    try:
        builder = get_dataset_builder()
        result = builder.deduplicate(dataset_id, threshold)
        return {
            "success": True,
            "removed_count": result.get("removed", 0),
            "remaining_count": result.get("remaining", 0)
        }
    except Exception as e:
        logger.error(f"数据集去重失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}/versions")
async def get_dataset_versions(dataset_id: str):
    """获取数据集版本历史"""
    try:
        builder = get_dataset_builder()
        versions = builder.get_versions(dataset_id)
        return {"versions": versions}
    except Exception as e:
        logger.error(f"获取数据集版本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets/{dataset_id}/versions")
async def create_dataset_version(dataset_id: str, version_name: str = ""):
    """创建数据集版本快照"""
    try:
        builder = get_dataset_builder()
        version = builder.create_version(dataset_id, version_name)
        return {"success": True, "version": version}
    except Exception as e:
        logger.error(f"创建数据集版本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 重复检测 API
# ============================================================================

@router.post("/duplicates/find")
async def find_duplicates(
    asset_ids: List[str],
    threshold: float = 0.9,
    metric: str = "perceptual_hash"
):
    """查找重复资产"""
    try:
        engine = get_compare_engine()
        
        from image_filter_compare import ImageCompareEngine
        duplicate_groups = engine.find_duplicates(
            asset_ids=asset_ids,
            threshold=threshold,
            metric=metric
        )
        
        return {
            "success": True,
            "duplicate_groups": duplicate_groups,
            "count": len(duplicate_groups)
        }
    except Exception as e:
        logger.error(f"查找重复资产失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/duplicates/merge")
async def merge_duplicates(
    primary_id: str,
    duplicate_ids: List[str]
):
    """合并重复资产"""
    try:
        builder = get_dataset_builder()
        success = builder.merge_duplicate_assets(primary_id, duplicate_ids)
        return {"success": success}
    except Exception as e:
        logger.error(f"合并重复资产失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 工具函数
# ============================================================================

def import_module_attr(module_name: str, attr_name: str):
    """动态导入模块属性"""
    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


# 添加缺失的导入
from importlib import import_module
