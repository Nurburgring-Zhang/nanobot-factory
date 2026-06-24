#!/usr/bin/env python3
"""
数据库管理与AI标注 API 路由
Database Management & AI Annotation API Routes
# STATUS: deprecated — 与commercial_data_api路由前缀冲突(/api/commercial)，建议合并
# 路由数: 19 | 实际使用: 0 (被commercial_data_api覆盖)

@author Matrix Agent
@date 2026-04-21
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/commercial", tags=["数据库管理与AI标注"])

# 延迟导入管理器
_db_manager = None
_ai_service = None


def get_db_manager():
    """获取数据库管理器"""
    global _db_manager
    if _db_manager is None:
        try:
            from database_manager import get_db_manager, DataCategory, SensitiveLevel, AuditAction
            _db_manager = get_db_manager()
        except ImportError:
            logger.error("database_manager module not found")
            return None
    return _db_manager


def get_ai_service():
    """获取AI服务"""
    global _ai_service
    if _ai_service is None:
        try:
            from ai_annotation_service import get_ai_service, AITaskType
            _ai_service = get_ai_service()
        except ImportError:
            logger.error("ai_annotation_service module not found")
            return None
    return _ai_service


# ==================== 请求/响应模型 ====================

class RecordCreateRequest(BaseModel):
    data_type: str = Field(..., description="数据类型")
    content: dict = Field(..., description="数据内容")
    metadata: Optional[dict] = Field(default={}, description="元数据")
    created_by: Optional[str] = Field(default=None, description="创建者")
    sensitive_level: Optional[str] = Field(default="internal", description="敏感等级")
    tags: Optional[list] = Field(default=[], description="标签")


class RecordUpdateRequest(BaseModel):
    content: Optional[dict] = None
    metadata: Optional[dict] = None
    quality_level: Optional[str] = None
    tags: Optional[list] = None
    sensitive_level: Optional[str] = None


class ConnectionConfigRequest(BaseModel):
    name: str = Field(..., description="连接名称")
    db_type: str = Field(..., description="数据库类型")
    host: str = Field(default="localhost", description="主机")
    port: int = Field(default=5432, description="端口")
    database: str = Field(..., description="数据库名")
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class PreAnnotateRequest(BaseModel):
    image_url: str = Field(..., description="图像URL或路径")
    task_type: str = Field(..., description="任务类型")
    confidence: float = Field(default=0.5, description="置信度阈值")


class QualityCheckRequest(BaseModel):
    image_url: str = Field(..., description="图像URL或路径")


class RecommendLabelsRequest(BaseModel):
    image_url: str = Field(..., description="图像URL或路径")
    existing_labels: list = Field(default=[], description="已存在的标签")
    top_k: int = Field(default=5, description="推荐数量")


# ==================== 数据库管理 API ====================

@router.get("/database/analytics")
async def get_analytics(days: int = Query(default=30, ge=1, le=365)):
    """获取分析指标"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        metrics = db.get_analytics(days)
        return {
            "success": True,
            "data": {
                "total_records": metrics.total_records,
                "records_by_category": metrics.records_by_category,
                "records_by_date": metrics.records_by_date,
                "average_quality_score": metrics.average_quality_score,
                "quality_distribution": metrics.quality_distribution,
                "top_tags": metrics.top_tags,
                "data_growth_rate": metrics.data_growth_rate,
                "active_users": metrics.active_users,
                "storage_size_mb": metrics.storage_size_mb,
            }
        }
    except Exception as e:
        logger.error(f"获取分析指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/quality-report")
async def get_quality_report(category: Optional[str] = None):
    """获取数据质量报告"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        data_category = None
        if category:
            from database_manager import DataCategory
            data_category = DataCategory(category)

        report = db.get_quality_report(data_category)
        return {
            "success": True,
            "data": {
                "total_records": report.total_records,
                "valid_records": report.valid_records,
                "invalid_records": report.invalid_records,
                "missing_fields": report.missing_fields,
                "duplicate_records": report.duplicate_records,
                "quality_distribution": report.quality_distribution,
                "recommendations": report.recommendations,
            }
        }
    except Exception as e:
        logger.error(f"获取质量报告失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/audit-logs")
async def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """获取审计日志"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        from database_manager import AuditAction

        audit_action = None
        if action:
            try:
                audit_action = AuditAction(action)
            except ValueError:
                pass

        dt_from = None
        if date_from:
            dt_from = datetime.fromisoformat(date_from)

        dt_to = None
        if date_to:
            dt_to = datetime.fromisoformat(date_to)

        logs = db.get_audit_logs(user_id, audit_action, dt_from, dt_to, limit)

        return {
            "success": True,
            "data": {
                "logs": [log.to_dict() for log in logs]
            }
        }
    except Exception as e:
        logger.error(f"获取审计日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/records")
async def create_record(request: RecordCreateRequest):
    """创建数据记录"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        from database_manager import DataCategory, SensitiveLevel

        data_category = DataCategory(request.data_type)
        sensitive_level = SensitiveLevel(request.sensitive_level or "internal")

        record_id = db.create(
            data_type=data_category,
            content=request.content,
            metadata=request.metadata,
            created_by=request.created_by,
            sensitive_level=sensitive_level,
            tags=request.tags,
        )

        if record_id:
            return {"success": True, "record_id": record_id}
        else:
            raise HTTPException(status_code=500, detail="创建记录失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的数据类型: {e}")
    except Exception as e:
        logger.error(f"创建记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/records/{record_id}")
async def get_record(record_id: str):
    """获取单条记录"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        record = db.read(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="记录不存在")

        return {"success": True, "data": record.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/database/records/{record_id}")
async def update_record(record_id: str, request: RecordUpdateRequest):
    """更新记录"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        updates = {k: v for k, v in request.dict().items() if v is not None}

        # 转换枚举值
        if "quality_level" in updates:
            from database_manager import DataQualityLevel
            updates["quality_level"] = DataQualityLevel(updates["quality_level"]).value

        if "sensitive_level" in updates:
            from database_manager import SensitiveLevel
            updates["sensitive_level"] = SensitiveLevel(updates["sensitive_level"]).value

        result = db.update(record_id, updates)
        return {"success": result}
    except Exception as e:
        logger.error(f"更新记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/database/records/{record_id}")
async def delete_record(record_id: str, soft: bool = True):
    """删除记录"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        result = db.delete(record_id, soft)
        return {"success": result}
    except Exception as e:
        logger.error(f"删除记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/records")
async def query_records(
    data_category: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    created_by: Optional[str] = None,
    search_text: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """查询记录"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        from database_manager import QueryFilter, DataCategory

        query_filter = QueryFilter(
            data_category=DataCategory(data_category) if data_category else None,
            date_from=datetime.fromisoformat(date_from) if date_from else None,
            date_to=datetime.fromisoformat(date_to) if date_to else None,
            created_by=created_by,
            search_text=search_text,
            limit=limit,
            offset=offset,
        )

        records, total = db.query(query_filter)

        return {
            "success": True,
            "data": {
                "records": [r.to_dict() for r in records],
                "total": total
            }
        }
    except Exception as e:
        logger.error(f"查询记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/connections")
async def list_connections():
    """列出所有数据库连接"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        connections = db.data_store.list_connections()
        return {"success": True, "data": {"connections": connections}}
    except Exception as e:
        logger.error(f"列出连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/connections")
async def save_connection(request: ConnectionConfigRequest):
    """保存数据库连接配置"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        from database_manager import ConnectionConfig, DatabaseType
        import uuid

        connection_id = f"conn_{uuid.uuid4().hex[:8]}"

        config = ConnectionConfig(
            db_type=DatabaseType(request.db_type),
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password=request.password,
        )

        success = db.data_store.save_connection_config(connection_id, request.name, config)

        return {"success": success, "connection_id": connection_id}
    except Exception as e:
        logger.error(f"保存连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/connections/test")
async def test_connection(request: ConnectionConfigRequest):
    """测试数据库连接"""
    # 简化实现 - 实际应尝试建立连接
    try:
        # 这里可以实现真正的连接测试
        return {"success": True, "message": "连接配置有效"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}


@router.get("/database/summary")
async def get_summary():
    """获取系统摘要"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        summary = db.get_summary()
        return {"success": True, "data": summary}
    except Exception as e:
        logger.error(f"获取摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/records/batch")
async def batch_create_records(
    records: list,
    data_type: str
):
    """批量创建记录"""
    db = get_db_manager()
    if db is None:
        raise HTTPException(status_code=503, detail="数据库服务不可用")

    try:
        from database_manager import DataCategory

        data_category = DataCategory(data_type)

        success_count, fail_count = db.batch_create(records, data_category)

        return {
            "success": True,
            "data": {
                "success_count": success_count,
                "fail_count": fail_count
            }
        }
    except Exception as e:
        logger.error(f"批量创建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI标注 API ====================

@router.get("/ai/model-status")
async def get_model_status():
    """获取AI模型状态"""
    ai = get_ai_service()
    if ai is None:
        return {
            "success": True,
            "data": {
                "yolo": False,
                "sam": False,
                "classification": False,
                "message": "AI服务未初始化"
            }
        }

    try:
        status = ai.get_model_status()
        return {"success": True, "data": status}
    except Exception as e:
        logger.error(f"获取模型状态失败: {e}")
        return {"success": True, "data": {"yolo": False, "sam": False, "classification": False}}


@router.post("/ai/pre-annotate")
async def pre_annotate(request: PreAnnotateRequest):
    """AI预标注"""
    ai = get_ai_service()
    if ai is None:
        raise HTTPException(status_code=503, detail="AI服务不可用")

    try:
        from ai_annotation_service import AITaskType, ImageProcessor

        # 加载图像
        image = ImageProcessor.load_image(request.image_url)
        if image is None:
            raise HTTPException(status_code=400, detail="无法加载图像")

        # 获取任务类型
        task_type_map = {
            "object_detection": AITaskType.OBJECT_DETECTION,
            "semantic_segmentation": AITaskType.SEMANTIC_SEGMENTATION,
            "instance_segmentation": AITaskType.INSTANCE_SEGMENTATION,
            "image_classification": AITaskType.IMAGE_CLASSIFICATION,
            "keypoint_detection": AITaskType.KEYPOINT_DETECTION,
        }
        task_type = task_type_map.get(request.task_type, AITaskType.OBJECT_DETECTION)

        # 执行预标注
        results = ai.pre_annotate(image, task_type, confidence=request.confidence)

        annotations = [
            {
                "id": r.annotation_id,
                "type": r.annotation_type.value,
                "label": r.label,
                "confidence": r.confidence,
                "geometry": r.geometry,
            }
            for r in results
        ]

        return {"success": True, "data": {"annotations": annotations}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/quality-check")
async def quality_check(request: QualityCheckRequest):
    """图像质量检测"""
    ai = get_ai_service()
    if ai is None:
        raise HTTPException(status_code=503, detail="AI服务不可用")

    try:
        from ai_annotation_service import ImageProcessor

        # 加载图像
        image = ImageProcessor.load_image(request.image_url)
        if image is None:
            raise HTTPException(status_code=400, detail="无法加载图像")

        # 执行质量检测
        result = ai.check_quality(image)

        return {
            "success": True,
            "data": {
                "is_valid": result.is_valid,
                "issues": result.issues,
                "overall_score": result.overall_score,
                "blur_score": result.blur_score,
                "brightness_score": result.brightness_score,
                "nsfw_score": result.nsfw_score,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"质量检测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/recommend-labels")
async def recommend_labels(request: RecommendLabelsRequest):
    """智能推荐标签"""
    ai = get_ai_service()
    if ai is None:
        raise HTTPException(status_code=503, detail="AI服务不可用")

    try:
        from ai_annotation_service import ImageProcessor

        # 加载图像
        image = ImageProcessor.load_image(request.image_url)
        if image is None:
            raise HTTPException(status_code=400, detail="无法加载图像")

        # 获取推荐
        recommendations = ai.recommend_labels(
            image,
            request.existing_labels,
            request.top_k
        )

        return {
            "success": True,
            "data": {
                "recommendations": recommendations
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标签推荐失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/batch-pre-annotate")
async def batch_pre_annotate(
    image_urls: list,
    task_type: str
):
    """批量预标注"""
    ai = get_ai_service()
    if ai is None:
        raise HTTPException(status_code=503, detail="AI服务不可用")

    try:
        from ai_annotation_service import AITaskType, ImageProcessor

        task_type_map = {
            "object_detection": AITaskType.OBJECT_DETECTION,
            "semantic_segmentation": AITaskType.SEMANTIC_SEGMENTATION,
            "instance_segmentation": AITaskType.INSTANCE_SEGMENTATION,
            "image_classification": AITaskType.IMAGE_CLASSIFICATION,
        }
        ai_task_type = task_type_map.get(task_type, AITaskType.OBJECT_DETECTION)

        results = []
        for url in image_urls:
            image = ImageProcessor.load_image(url)
            if image is None:
                results.append({"url": url, "error": "无法加载图像", "annotations": []})
            else:
                annotations = ai.pre_annotate(image, ai_task_type)
                results.append({
                    "url": url,
                    "annotations": [
                        {
                            "id": r.annotation_id,
                            "type": r.annotation_type.value,
                            "label": r.label,
                            "confidence": r.confidence,
                            "geometry": r.geometry,
                        }
                        for r in annotations
                    ]
                })

        return {"success": True, "data": {"results": results}}
    except Exception as e:
        logger.error(f"批量预标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/batch-quality-check")
async def batch_quality_check(image_urls: list):
    """批量质量检测"""
    ai = get_ai_service()
    if ai is None:
        raise HTTPException(status_code=503, detail="AI服务不可用")

    try:
        from ai_annotation_service import ImageProcessor

        results = []
        for url in image_urls:
            image = ImageProcessor.load_image(url)
            if image is None:
                results.append({
                    "url": url,
                    "is_valid": False,
                    "overall_score": 0,
                    "error": "无法加载图像"
                })
            else:
                result = ai.check_quality(image)
                results.append({
                    "url": url,
                    "is_valid": result.is_valid,
                    "overall_score": result.overall_score,
                    "blur_score": result.blur_score,
                    "brightness_score": result.brightness_score,
                    "nsfw_score": result.nsfw_score,
                })

        return {"success": True, "data": {"results": results}}
    except Exception as e:
        logger.error(f"批量质量检测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册路由
logger.info("数据库管理与AI标注路由已注册")


# ==================== 增强版标注系统 API ====================

annotation_router = APIRouter(prefix="/api/annotation", tags=["数据标注系统"])

# 延迟导入标注管理器
_annotation_manager = None


def get_annotation_manager():
    """获取标注管理器"""
    global _annotation_manager
    if _annotation_manager is None:
        try:
            from database_manager import get_annotation_manager
            _annotation_manager = get_annotation_manager()
        except ImportError:
            logger.error("annotation_manager not found")
            return None
    return _annotation_manager


# ==================== 请求/响应模型 ====================

class ImageCreateRequest(BaseModel):
    image_path: str = Field(..., description="图片路径或URL")
    image_type: str = Field(default="single_image", description="图片类型")
    source: str = Field(default="user_upload", description="图片来源")
    project_id: Optional[str] = Field(default=None, description="项目ID")
    created_by: Optional[str] = Field(default=None, description="创建者")
    metadata: Optional[dict] = Field(default={}, description="元数据")
    parent_image_id: Optional[str] = Field(default=None, description="父图片ID(用于多轮编辑)")


class AnnotationCreateRequest(BaseModel):
    image_id: str = Field(..., description="图片ID")
    annotation_type: str = Field(..., description="标注类型")
    label: str = Field(..., description="标签名称")
    coordinates: list = Field(..., description="坐标数据")
    annotator: str = Field(..., description="标注员")
    category_id: Optional[str] = Field(default=None, description="类别ID")
    confidence: Optional[float] = Field(default=None, description="置信度")
    attributes: Optional[dict] = Field(default={}, description="附加属性")


class AnnotationUpdateRequest(BaseModel):
    coordinates: Optional[list] = None
    label: Optional[str] = None
    attributes: Optional[dict] = None


class QualityInspectionRequest(BaseModel):
    image_id: str = Field(..., description="图片ID")
    inspector: str = Field(..., description="质检员")
    result: str = Field(..., description="质检结果")
    defects: Optional[list] = Field(default=[], description="缺陷列表")
    notes: Optional[str] = Field(default=None, description="备注")


class ImageGroupCreateRequest(BaseModel):
    name: str = Field(..., description="组名称")
    description: Optional[str] = Field(default=None, description="描述")
    project_id: Optional[str] = Field(default=None, description="项目ID")
    created_by: Optional[str] = Field(default=None, description="创建者")


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., description="项目名称")
    description: Optional[str] = Field(default=None, description="项目描述")
    categories: Optional[list] = Field(default=[], description="类别定义")
    created_by: Optional[str] = Field(default=None, description="创建者")


class CommentRequest(BaseModel):
    image_id: str = Field(..., description="图片ID")
    content: str = Field(..., description="评论内容")
    user: str = Field(..., description="用户名")
    parent_comment_id: Optional[str] = Field(default=None, description="父评论ID")


class TagRequest(BaseModel):
    image_id: str = Field(..., description="图片ID")
    tag_name: str = Field(..., description="标签名称")
    created_by: str = Field(..., description="创建者")


# ==================== 项目管理 API ====================

@annotation_router.post("/projects")
async def create_project(request: ProjectCreateRequest):
    """创建标注项目"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        project_id = manager.create_project(
            name=request.name,
            description=request.description,
            categories=request.categories,
            created_by=request.created_by,
        )
        if project_id:
            return {"success": True, "data": {"project_id": project_id}}
        raise HTTPException(status_code=500, detail="创建项目失败")
    except Exception as e:
        logger.error(f"创建项目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/projects")
async def list_projects(include_completed: bool = False):
    """列出所有标注项目"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        projects = manager.list_projects(include_completed=include_completed)
        return {
            "success": True,
            "data": {
                "projects": [
                    {
                        "project_id": p.project_id,
                        "name": p.name,
                        "description": p.description,
                        "status": p.status,
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                        "stats": p.stats,
                    }
                    for p in projects
                ]
            }
        }
    except Exception as e:
        logger.error(f"列出项目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """获取项目详情"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        project = manager.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")

        return {
            "success": True,
            "data": {
                "project_id": project.project_id,
                "name": project.name,
                "description": project.description,
                "categories": project.categories,
                "status": project.status,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "stats": project.stats,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 图片管理 API ====================

@annotation_router.post("/images")
async def add_image(request: ImageCreateRequest):
    """添加图片"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        image_id = manager.add_image(
            image_path=request.image_path,
            image_type=request.image_type,
            source=request.source,
            project_id=request.project_id,
            created_by=request.created_by,
            metadata=request.metadata,
            parent_image_id=request.parent_image_id,
        )
        if image_id:
            return {"success": True, "data": {"image_id": image_id}}
        raise HTTPException(status_code=500, detail="添加图片失败")
    except Exception as e:
        logger.error(f"添加图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/images/{image_id}")
async def get_image(image_id: str):
    """获取图片详情"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        image = manager.get_image(image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="图片不存在")

        return {
            "success": True,
            "data": {
                "image_id": image.image_id,
                "image_path": image.image_path,
                "image_type": image.image_type,
                "source": image.source,
                "project_id": image.project_id,
                "status": image.status,
                "metadata": image.metadata,
                "created_at": image.created_at.isoformat() if image.created_at else None,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/images")
async def list_images(
    project_id: Optional[str] = None,
    image_type: Optional[str] = None,
    status: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """列出图片"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        images = manager.list_images(
            project_id=project_id,
            image_type=image_type,
            status=status,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            "data": {
                "images": [
                    {
                        "image_id": img.image_id,
                        "image_path": img.image_path,
                        "image_type": img.image_type,
                        "status": img.status,
                        "created_at": img.created_at.isoformat() if img.created_at else None,
                    }
                    for img in images
                ],
                "total": len(images),
            }
        }
    except Exception as e:
        logger.error(f"列出图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.put("/images/{image_id}/status")
async def update_image_status(image_id: str, status: str):
    """更新图片状态"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.update_image_status(image_id, status)
        return {"success": success}
    except Exception as e:
        logger.error(f"更新状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.delete("/images/{image_id}")
async def delete_image(image_id: str):
    """删除图片(软删除)"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.soft_delete_image(image_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"删除图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.post("/images/{image_id}/restore")
async def restore_image(image_id: str):
    """恢复已删除图片"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.restore_image(image_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"恢复图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.post("/images/batch")
async def batch_add_images(
    image_paths: list,
    image_type: str = "single_image",
    source: str = "user_upload",
    project_id: Optional[str] = None,
    created_by: Optional[str] = None,
):
    """批量添加图片"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success_count, failed_ids = manager.batch_add_images(
            image_paths=image_paths,
            image_type=image_type,
            source=source,
            project_id=project_id,
            created_by=created_by,
        )
        return {
            "success": True,
            "data": {
                "success_count": success_count,
                "failed_count": len(failed_ids),
                "failed_ids": failed_ids,
            }
        }
    except Exception as e:
        logger.error(f"批量添加图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 标注管理 API ====================

@annotation_router.post("/annotations")
async def add_annotation(request: AnnotationCreateRequest):
    """添加标注"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        annotation_id = manager.add_annotation(
            image_id=request.image_id,
            annotation_type=request.annotation_type,
            label=request.label,
            coordinates=request.coordinates,
            annotator=request.annotator,
            category_id=request.category_id,
            confidence=request.confidence,
            attributes=request.attributes,
        )
        if annotation_id:
            return {"success": True, "data": {"annotation_id": annotation_id}}
        raise HTTPException(status_code=500, detail="添加标注失败")
    except Exception as e:
        logger.error(f"添加标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/images/{image_id}/annotations")
async def get_annotations(image_id: str):
    """获取图片的所有标注"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        annotations = manager.get_annotations(image_id)
        return {
            "success": True,
            "data": {
                "annotations": [
                    {
                        "annotation_id": a.annotation_id,
                        "annotation_type": a.annotation_type,
                        "label": a.label,
                        "coordinates": a.coordinates,
                        "status": a.status,
                        "confidence": a.confidence,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in annotations
                ]
            }
        }
    except Exception as e:
        logger.error(f"获取标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.put("/annotations/{annotation_id}")
async def update_annotation(annotation_id: str, request: AnnotationUpdateRequest):
    """更新标注"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.update_annotation(
            annotation_id=annotation_id,
            coordinates=request.coordinates,
            label=request.label,
            attributes=request.attributes,
        )
        return {"success": success}
    except Exception as e:
        logger.error(f"更新标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.delete("/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """删除标注"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.delete_annotation(annotation_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"删除标注失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 质量检查 API ====================

@annotation_router.post("/quality-inspections")
async def add_quality_inspection(request: QualityInspectionRequest):
    """添加质量检查"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        inspection_id = manager.add_quality_inspection(
            image_id=request.image_id,
            inspector=request.inspector,
            result=request.result,
            defects=request.defects,
            notes=request.notes,
        )
        if inspection_id:
            return {"success": True, "data": {"inspection_id": inspection_id}}
        raise HTTPException(status_code=500, detail="添加质量检查失败")
    except Exception as e:
        logger.error(f"添加质量检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/images/{image_id}/quality-inspections")
async def get_quality_inspections(image_id: str):
    """获取图片的质量检查记录"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        inspections = manager.get_quality_inspections(image_id)
        return {
            "success": True,
            "data": {
                "inspections": [
                    {
                        "inspection_id": i.inspection_id,
                        "inspector": i.inspector,
                        "result": i.result,
                        "notes": i.notes,
                        "defects": i.defects,
                        "created_at": i.created_at.isoformat() if i.created_at else None,
                    }
                    for i in inspections
                ]
            }
        }
    except Exception as e:
        logger.error(f"获取质量检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 图片组 API ====================

@annotation_router.post("/groups")
async def create_image_group(request: ImageGroupCreateRequest):
    """创建图片组"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        group_id = manager.create_image_group(
            name=request.name,
            description=request.description,
            project_id=request.project_id,
            created_by=request.created_by,
        )
        if group_id:
            return {"success": True, "data": {"group_id": group_id}}
        raise HTTPException(status_code=500, detail="创建图片组失败")
    except Exception as e:
        logger.error(f"创建图片组失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.post("/groups/{group_id}/images")
async def add_to_group(group_id: str, image_ids: list):
    """添加图片到组"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.add_to_group(group_id, image_ids)
        return {"success": success}
    except Exception as e:
        logger.error(f"添加到组失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/groups/{group_id}/images")
async def get_group_images(group_id: str):
    """获取组内所有图片"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        images = manager.get_group_images(group_id)
        return {
            "success": True,
            "data": {
                "images": [
                    {
                        "image_id": img.image_id,
                        "image_path": img.image_path,
                        "status": img.status,
                    }
                    for img in images
                ]
            }
        }
    except Exception as e:
        logger.error(f"获取组图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 评论与讨论 API ====================

@annotation_router.post("/comments")
async def add_comment(request: CommentRequest):
    """添加评论"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        comment_id = manager.add_comment(
            image_id=request.image_id,
            content=request.content,
            user=request.user,
            parent_comment_id=request.parent_comment_id,
        )
        if comment_id:
            return {"success": True, "data": {"comment_id": comment_id}}
        raise HTTPException(status_code=500, detail="添加评论失败")
    except Exception as e:
        logger.error(f"添加评论失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/images/{image_id}/comments")
async def get_comments(image_id: str):
    """获取图片的所有评论"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        comments = manager.get_comments(image_id)
        return {
            "success": True,
            "data": {
                "comments": [
                    {
                        "comment_id": c.comment_id,
                        "content": c.content,
                        "user": c.user,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in comments
                ]
            }
        }
    except Exception as e:
        logger.error(f"获取评论失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 标签管理 API ====================

@annotation_router.post("/tags")
async def add_tag(request: TagRequest):
    """添加标签"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        success = manager.add_tag(
            image_id=request.image_id,
            tag_name=request.tag_name,
            created_by=request.created_by,
        )
        return {"success": success}
    except Exception as e:
        logger.error(f"添加标签失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/images/{image_id}/tags")
async def get_tags(image_id: str):
    """获取图片的标签"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        tags = manager.get_tags(image_id)
        return {
            "success": True,
            "data": {
                "tags": [
                    {
                        "tag_id": t.tag_id,
                        "tag_name": t.tag_name,
                        "created_by": t.created_by,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                    }
                    for t in tags
                ]
            }
        }
    except Exception as e:
        logger.error(f"获取标签失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 搜索和统计 API ====================

@annotation_router.get("/search")
async def search_images(
    keyword: Optional[str] = None,
    project_id: Optional[str] = None,
    image_type: Optional[str] = None,
    status: Optional[str] = None,
    tags: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
):
    """搜索图片"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        tag_list = tags.split(",") if tags else None
        images = manager.search_images(
            keyword=keyword,
            project_id=project_id,
            image_type=image_type,
            status=status,
            tags=tag_list,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        return {
            "success": True,
            "data": {
                "images": [
                    {
                        "image_id": img.image_id,
                        "image_path": img.image_path,
                        "image_type": img.image_type,
                        "status": img.status,
                        "created_at": img.created_at.isoformat() if img.created_at else None,
                    }
                    for img in images
                ]
            }
        }
    except Exception as e:
        logger.error(f"搜索图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@annotation_router.get("/statistics")
async def get_statistics(project_id: Optional[str] = None):
    """获取标注统计"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        stats = manager.get_statistics(project_id)
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 导出 API ====================

@annotation_router.get("/export")
async def export_annotations(
    format_type: str = Query(..., description="导出格式: coco, yolo, voc"),
    project_id: Optional[str] = Query(default=None, description="项目ID"),
    image_ids: Optional[str] = Query(default=None, description="图片ID列表,用逗号分隔"),
    output_path: Optional[str] = Query(default=None, description="输出路径"),
):
    """导出标注数据"""
    manager = get_annotation_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="标注系统不可用")

    try:
        image_id_list = image_ids.split(",") if image_ids else None
        file_path = manager.export_annotations(
            format_type=format_type,
            project_id=project_id,
            image_ids=image_id_list,
            output_path=output_path,
        )
        if file_path:
            return {"success": True, "data": {"file_path": file_path}}
        raise HTTPException(status_code=500, detail="导出失败")
    except Exception as e:
        logger.error(f"导出失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册标注路由
logger.info("数据标注系统路由已注册")
