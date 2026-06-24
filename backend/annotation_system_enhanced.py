#!/usr/bin/env python3
"""
NanoBot Factory - 企业级数据标注系统 (增强版)
Enterprise Data Annotation System - Enhanced Version

完整功能:
- 图片数据管理 (单图/组图/多组图/多轮图/多轮组图/多轮多组图)
- 数据操作 (标注/质检/筛选/对比/增删/召回/回捞/标记)
- 质量管理 (缺陷标注/严重等级/质量评分)
- 版本控制 (数据血缘/变更历史)
- 协作功能 (评论/讨论/任务分配)

@author Matrix Agent
@date 2026-04-22
@version 3.0.0
"""

import os
import sys
import json
import uuid
import logging
import sqlite3
import hashlib
import shutil
from typing import Dict, Any, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import base64
from io import BytesIO
from pathlib import Path
import threading
import queue
import statistics

logger = logging.getLogger(__name__)

# ==================== 枚举类型定义 ====================

class ImageDataType(Enum):
    """图片数据类型"""
    SINGLE_IMAGE = "single_image"           # 单图
    IMAGE_GROUP = "image_group"              # 组图 (同一场景/主题的多张图片)
    MULTI_GROUP = "multi_group"             # 多组图
    MULTI_TURN = "multi_turn"               # 多轮图 (同一初始图的多轮编辑)
    MULTI_TURN_GROUP = "multi_turn_group"    # 多轮组图
    MULTI_TURN_MULTI_GROUP = "multi_turn_multi_group"  # 多轮多组图

class OperationType(Enum):
    """操作类型"""
    # 图片生产
    IMAGE_PRODUCTION = "image_production"
    # 图片采集
    IMAGE_COLLECTION = "image_collection"
    # 图片编辑
    IMAGE_EDITING = "image_editing"
    # 图片多轮编辑
    IMAGE_MULTI_TURN_EDITING = "image_multi_turn_editing"

class DataOperation(Enum):
    """数据操作"""
    ANNOTATE = "annotate"           # 标注
    QUALITY_INSPECT = "quality_inspect"  # 质检
    FILTER = "filter"               # 筛选
    COMPARE = "compare"             # 对比
    DISPLAY = "display"            # 展示
    ADD_DELETE = "add_delete"      # 增删
    RECALL = "recall"              # 召回
    RESURRECT = "resurrect"        # 回捞
    TAG = "tag"                    # 标记

class AnnotationType(Enum):
    """标注类型"""
    BOUNDING_BOX = "bounding_box"
    POLYGON = "polygon"
    POLYLINE = "polyline"
    POINT = "point"
    KEYPOINTS = "keypoints"
    CLASSIFICATION = "classification"
    TEXT = "text"
    MASK = "mask"
    CUBOID_3D = "cuboid_3d"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    HIGHLIGHT = "highlight"
    NORMAL_BOX = "normal_box"       # 常规标注框

class AnnotationStatus(Enum):
    """标注状态"""
    DRAFT = "draft"                # 草稿
    IN_PROGRESS = "in_progress"    # 进行中
    COMPLETED = "completed"        # 已完成
    REVIEWED = "reviewed"          # 已审核
    APPROVED = "approved"          # 已批准
    REJECTED = "rejected"          # 已拒绝
    QUALITY_PASSED = "quality_passed"    # 质检通过
    QUALITY_FAILED = "quality_failed"     # 质检未通过

class MediaType(Enum):
    """媒体类型"""
    IMAGE = "image"
    VIDEO = "video"
    FRAME = "frame"
    DOCUMENT = "document"
    TEXT = "text"

class QualityDefectType(Enum):
    """质量缺陷类型"""
    MISSING_LABEL = "missing_label"       # 漏标
    WRONG_LABEL = "wrong_label"           # 错标
    BOUNDARY_INACCURATE = "boundary_inaccurate"  # 边界不准
    CLASSIFICATION_ERROR = "classification_error"  # 分类错误
    INCOMPLETE_ANNOTATION = "incomplete_annotation"  # 标注不完整

class QualitySeverity(Enum):
    """缺陷严重等级"""
    CRITICAL = "critical"     # 严重
    MAJOR = "major"          # 较大
    MINOR = "minor"          # 一般

class DataSource(Enum):
    """数据来源"""
    AI_GENERATION = "ai_generation"   # AI生成
    MANUAL_CAPTURE = "manual_capture"   # 人工采集
    WEB_SCRAPING = "web_scraping"      # 网页爬取
    DATASET_IMPORT = "dataset_import"  # 数据集导入
    USER_UPLOAD = "user_upload"        # 用户上传

class ReviewStatus(Enum):
    """审核状态"""
    PENDING = "pending"      # 待审核
    PASSED = "passed"        # 通过
    FAILED = "failed"        # 未通过
    REVISION_REQUIRED = "revision_required"  # 需要修改

# ==================== 数据类定义 ====================

@dataclass
class Point:
    """点坐标"""
    x: float
    y: float
    z: float = 0
    visible: bool = True
    name: str = ""  # 关键点名称
    
    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z, "visible": self.visible, "name": self.name}

@dataclass
class BoundingBox:
    """边界框"""
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0
    truncated: bool = False
    occluded: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "rotation": self.rotation, "truncated": self.truncated, "occluded": self.occluded
        }
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

@dataclass
class AnnotationLabel:
    """标注标签"""
    id: str
    name: str
    category: str = ""
    color: str = "#FF0000"
    parent_id: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    hotkey: str = ""  # 快捷键
    
    @classmethod
    def create(cls, name: str, category: str = "", color: str = "#FF0000") -> 'AnnotationLabel':
        return cls(id=str(uuid.uuid4())[:8], name=name, category=category, color=color)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class QualityDefect:
    """质量缺陷"""
    id: str
    defect_type: QualityDefectType
    severity: QualitySeverity
    description: str
    location: Dict[str, Any] = field(default_factory=dict)  # 缺陷位置
    suggested_fix: str = ""
    annotated_by: str = ""
    annotated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_fixed: bool = False
    fixed_by: str = ""
    fixed_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "defect_type": self.defect_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "location": self.location,
            "suggested_fix": self.suggested_fix,
            "annotated_by": self.annotated_by,
            "annotated_at": self.annotated_at,
            "is_fixed": self.is_fixed,
            "fixed_by": self.fixed_by,
            "fixed_at": self.fixed_at,
        }

@dataclass
class AnnotationObject:
    """标注对象"""
    id: str
    annotation_type: AnnotationType
    label: AnnotationLabel
    
    bbox: Optional[BoundingBox] = None
    points: List[Point] = field(default_factory=list)
    polygon: List[Point] = field(default_factory=list)
    keypoints: List[Point] = field(default_factory=list)
    text: str = ""
    mask_data: str = ""
    confidence: float = 1.0
    
    attributes: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    occluded: bool = False
    truncated: bool = False
    difficult: bool = False
    
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    verified: bool = False
    verified_by: str = ""
    
    # 缺陷相关
    has_defect: bool = False
    defects: List[QualityDefect] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "annotation_type": self.annotation_type.value,
            "label": self.label.to_dict(),
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "points": [p.to_dict() for p in self.points],
            "polygon": [p.to_dict() for p in self.polygon],
            "keypoints": [p.to_dict() for p in self.keypoints],
            "text": self.text,
            "mask_data": self.mask_data,
            "confidence": self.confidence,
            "attributes": self.attributes,
            "notes": self.notes,
            "occluded": self.occluded,
            "truncated": self.truncated,
            "difficult": self.difficult,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "verified": self.verified,
            "verified_by": self.verified_by,
            "has_defect": self.has_defect,
            "defects": [d.to_dict() for d in self.defects],
        }
        return result

@dataclass
class ImageRecord:
    """单张图片记录"""
    data_id: str
    asset_id: str
    image_path: str
    width: int
    height: int
    thumbnail_path: str = ""
    file_size: int = 0
    file_hash: str = ""
    
    # 图片组合类型
    data_type: ImageDataType = ImageDataType.SINGLE_IMAGE
    group_id: str = ""  # 组ID
    turn_index: int = 0  # 轮次索引 (多轮图用)
    
    # 来源信息
    source: DataSource = DataSource.USER_UPLOAD
    source_url: str = ""
    operation_type: OperationType = OperationType.IMAGE_COLLECTION
    
    # 标注数据
    annotations: List[AnnotationObject] = field(default_factory=list)
    global_labels: List[str] = field(default_factory=list)
    description: str = ""
    
    # 状态
    status: AnnotationStatus = AnnotationStatus.DRAFT
    review_status: ReviewStatus = ReviewStatus.PENDING
    annotation_count: int = 0
    labeled_count: int = 0
    
    # 质量
    quality_score: float = 0.0
    quality_defects: List[QualityDefect] = field(default_factory=list)
    
    # 标签与标记
    tags: List[str] = field(default_factory=list)
    is_starred: bool = False
    is_bookmarked: bool = False
    
    # 版本与血缘
    parent_id: str = ""  # 父版本ID (用于多轮编辑)
    version: int = 1
    lineage: List[str] = field(default_factory=list)  # 数据血缘链
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 创建信息
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_by: str = ""
    reviewed_at: str = ""
    
    # 软删除
    is_deleted: bool = False
    deleted_at: str = ""
    deleted_by: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_id": self.data_id,
            "asset_id": self.asset_id,
            "image_path": self.image_path,
            "thumbnail_path": self.thumbnail_path,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "data_type": self.data_type.value,
            "group_id": self.group_id,
            "turn_index": self.turn_index,
            "source": self.source.value,
            "source_url": self.source_url,
            "operation_type": self.operation_type.value,
            "annotations": [a.to_dict() for a in self.annotations],
            "global_labels": self.global_labels,
            "description": self.description,
            "status": self.status.value,
            "review_status": self.review_status.value,
            "annotation_count": len(self.annotations),
            "labeled_count": self.labeled_count,
            "quality_score": self.quality_score,
            "quality_defects": [d.to_dict() for d in self.quality_defects],
            "tags": self.tags,
            "is_starred": self.is_starred,
            "is_bookmarked": self.is_bookmarked,
            "parent_id": self.parent_id,
            "version": self.version,
            "lineage": self.lineage,
            "metadata": self.metadata,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at,
            "deleted_by": self.deleted_by,
        }

@dataclass
class ImageGroup:
    """图片组"""
    group_id: str
    group_name: str
    data_type: ImageDataType
    
    # 组内图片
    images: List[str] = field(default_factory=list)  # data_id列表
    
    # 组属性
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 统计
    total_images: int = 0
    annotated_images: int = 0
    approved_images: int = 0
    
    # 多轮属性
    turn_count: int = 0  # 多轮编辑轮次
    parent_group_id: str = ""  # 父组ID
    
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "data_type": self.data_type.value,
            "images": self.images,
            "description": self.description,
            "tags": self.tags,
            "metadata": self.metadata,
            "total_images": len(self.images),
            "annotated_images": self.annotated_images,
            "approved_images": self.approved_images,
            "turn_count": self.turn_count,
            "parent_group_id": self.parent_group_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass
class QualityInspection:
    """质检记录"""
    inspection_id: str
    data_id: str
    inspector: str
    result: str  # pass/fail
    score: float = 0.0
    
    defects: List[QualityDefect] = field(default_factory=list)
    comments: str = ""
    
    checked_items: Dict[str, bool] = field(default_factory=dict)
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "inspection_id": self.inspection_id,
            "data_id": self.data_id,
            "inspector": self.inspector,
            "result": self.result,
            "score": self.score,
            "defects": [d.to_dict() for d in self.defects],
            "comments": self.comments,
            "checked_items": self.checked_items,
            "created_at": self.created_at,
        }

@dataclass
class Comment:
    """评论/讨论"""
    comment_id: str
    data_id: str
    user_id: str
    user_name: str
    content: str
    mentions: List[str] = field(default_factory=list)  # @提及的用户
    parent_id: str = ""  # 回复的评论ID
    annotation_id: str = ""  # 关联的标注ID
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_resolved: bool = False
    resolved_by: str = ""
    resolved_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "data_id": self.data_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "content": self.content,
            "mentions": self.mentions,
            "parent_id": self.parent_id,
            "annotation_id": self.annotation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_resolved": self.is_resolved,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
        }

@dataclass
class TagRecord:
    """标记记录"""
    tag_id: str
    data_id: str
    tag_name: str
    tag_type: str = "custom"  # custom/system/auto
    
    tagged_by: str = "system"
    tagged_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag_id": self.tag_id,
            "data_id": self.data_id,
            "tag_name": self.tag_name,
            "tag_type": self.tag_type,
            "tagged_by": self.tagged_by,
            "tagged_at": self.tagged_at,
        }

# ==================== 标注项目管理 ====================

@dataclass
class AnnotationProject:
    """标注项目"""
    project_id: str
    name: str
    description: str = ""
    
    # 标签配置
    labels: List[AnnotationLabel] = field(default_factory=list)
    label_categories: Dict[str, List[str]] = field(default_factory=dict)
    
    # 标注类型
    annotation_types: List[AnnotationType] = field(default_factory=list)
    keypoint_skeleton: List[Tuple[int, int]] = field(default_factory=list)
    keypoint_names: List[str] = field(default_factory=list)
    
    # 项目配置
    quality_threshold: float = 0.8
    require_review: bool = True
    allow_ai_preannotation: bool = True
    
    # 统计
    total_items: int = 0
    annotated_items: int = 0
    approved_items: int = 0
    
# 设置
    settings: Dict[str, Any] = field(default_factory=dict)
    
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "labels": [l.to_dict() for l in self.labels],
            "label_categories": self.label_categories,
            "annotation_types": [t.value for t in self.annotation_types],
            "keypoint_skeleton": self.keypoint_skeleton,
            "keypoint_skeleton_names": self.keypoint_names,
            "quality_threshold": self.quality_threshold,
            "require_review": self.require_review,
            "allow_ai_preannotation": self.allow_ai_preannotation,
            "total_items": self.total_items,
            "annotated_items": self.annotated_items,
            "approved_items": self.approved_items,
            "settings": self.settings,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

# ==================== 增强版标注管理器 ====================

class EnhancedAnnotationManager:
    """
    增强版标注管理器
    支持完整的图片组合管理、数据操作、质检、版本控制等功能
    """
    
    def __init__(self, storage_path: str = "./annotations_enhanced", db_path: str = None):
        self.storage_path = storage_path
        self.db_path = db_path or os.path.join(storage_path, "annotation_system.db")
        
        # 内存存储
        self.images: Dict[str, ImageRecord] = {}
        self.groups: Dict[str, ImageGroup] = {}
        self.projects: Dict[str, AnnotationProject] = {}
        self.inspections: Dict[str, QualityInspection] = {}
        self.comments: Dict[str, List[Comment]] = defaultdict(list)
        self.tags: Dict[str, List[TagRecord]] = defaultdict(list)
        
        # 索引
        self._index_by_group: Dict[str, List[str]] = defaultdict(list)
        self._index_by_status: Dict[AnnotationStatus, List[str]] = defaultdict(list)
        self._index_by_tag: Dict[str, List[str]] = defaultdict(list)
        self._deleted_items: Dict[str, ImageRecord] = {}  # 已删除但可召回的数据
        
        os.makedirs(storage_path, exist_ok=True)
        self._init_database()
        self._load_metadata()
    
    def _init_database(self):
        """初始化SQLite数据库"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # 创建表
        cursor = self.conn.cursor()
        
        # 图片数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                data_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                image_path TEXT NOT NULL,
                thumbnail_path TEXT,
                width INTEGER,
                height INTEGER,
                file_size INTEGER,
                file_hash TEXT,
                data_type TEXT,
                group_id TEXT,
                turn_index INTEGER DEFAULT 0,
                source TEXT,
                source_url TEXT,
                operation_type TEXT,
                description TEXT,
                status TEXT,
                review_status TEXT,
                quality_score REAL DEFAULT 0,
                tags TEXT,
                is_starred INTEGER DEFAULT 0,
                is_bookmarked INTEGER DEFAULT 0,
                parent_id TEXT,
                version INTEGER DEFAULT 1,
                lineage TEXT,
                metadata TEXT,
                created_by TEXT,
                created_at TEXT,
                updated_at TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT,
                deleted_by TEXT
            )
        """)
        
        # 标注对象表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS annotations (
                annotation_id TEXT PRIMARY KEY,
                data_id TEXT NOT NULL,
                annotation_type TEXT NOT NULL,
                label_id TEXT,
                label_name TEXT,
                label_category TEXT,
                label_color TEXT,
                bbox TEXT,
                points TEXT,
                polygon TEXT,
                keypoints TEXT,
                text_content TEXT,
                mask_data TEXT,
                confidence REAL,
                attributes TEXT,
                notes TEXT,
                occluded INTEGER,
                truncated INTEGER,
                difficult INTEGER,
                has_defect INTEGER,
                created_by TEXT,
                created_at TEXT,
                updated_at TEXT,
                verified INTEGER,
                verified_by TEXT
            )
        """)
        
        # 图片组表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_groups (
                group_id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                data_type TEXT,
                description TEXT,
                tags TEXT,
                metadata TEXT,
                turn_count INTEGER DEFAULT 0,
                parent_group_id TEXT,
                created_by TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # 质检记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_inspections (
                inspection_id TEXT PRIMARY KEY,
                data_id TEXT NOT NULL,
                inspector TEXT,
                result TEXT,
                score REAL,
                defects TEXT,
                comments TEXT,
                checked_items TEXT,
                created_at TEXT
            )
        """)
        
        # 质量缺陷表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_defects (
                defect_id TEXT PRIMARY KEY,
                data_id TEXT NOT NULL,
                annotation_id TEXT,
                defect_type TEXT,
                severity TEXT,
                description TEXT,
                location TEXT,
                suggested_fix TEXT,
                annotated_by TEXT,
                annotated_at TEXT,
                is_fixed INTEGER DEFAULT 0,
                fixed_by TEXT,
                fixed_at TEXT
            )
        """)
        
        # 评论表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                data_id TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                content TEXT,
                mentions TEXT,
                parent_id TEXT,
                annotation_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                is_resolved INTEGER DEFAULT 0,
                resolved_by TEXT,
                resolved_at TEXT
            )
        """)
        
        # 标签表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                tag_id TEXT PRIMARY KEY,
                data_id TEXT NOT NULL,
                tag_name TEXT,
                tag_type TEXT,
                tagged_by TEXT,
                tagged_at TEXT
            )
        """)
        
        # 项目表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                labels TEXT,
                label_categories TEXT,
                annotation_types TEXT,
                keypoint_skeleton TEXT,
                keypoint_names TEXT,
                quality_threshold REAL,
                require_review INTEGER,
                allow_ai_preannotation INTEGER,
                settings TEXT,
                created_by TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_group_id ON images(group_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_status ON images(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_deleted ON images(is_deleted)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_annotations_data_id ON annotations(data_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_data_id ON comments(data_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_data_id ON tags(data_id)")
        
        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")
    
    def _load_metadata(self):
        """加载元数据"""
        metadata_file = os.path.join(self.storage_path, "metadata.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded metadata from {metadata_file}")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")
    
    def _save_metadata(self):
        """保存元数据"""
        metadata_file = os.path.join(self.storage_path, "metadata.json")
        data = {
            "projects": [p.to_dict() for p in self.projects.values()],
            "groups_count": len(self.groups),
            "images_count": len(self.images),
            "updated_at": datetime.now().isoformat(),
        }
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    # ==================== 图片数据管理 ====================
    
    def create_single_image(
        self,
        asset_id: str,
        image_path: str,
        width: int,
        height: int,
        source: DataSource = DataSource.USER_UPLOAD,
        operation_type: OperationType = OperationType.IMAGE_COLLECTION,
        created_by: str = "system",
        metadata: Dict = None
    ) -> ImageRecord:
        """创建单张图片记录"""
        data_id = str(uuid.uuid4())[:12]
        
        image = ImageRecord(
            data_id=data_id,
            asset_id=asset_id,
            image_path=image_path,
            width=width,
            height=height,
            data_type=ImageDataType.SINGLE_IMAGE,
            source=source,
            operation_type=operation_type,
            created_by=created_by,
            metadata=metadata or {},
        )
        
        # 计算文件哈希
        if os.path.exists(image_path):
            image.file_size = os.path.getsize(image_path)
            with open(image_path, 'rb') as f:
                image.file_hash = hashlib.md5(f.read()).hexdigest()
        
        self.images[data_id] = image
        self._index_by_status[image.status].append(data_id)
        self._save_image_to_db(image)
        
        logger.info(f"Created single image: {data_id}")
        return image
    
    def create_image_group(
        self,
        group_name: str,
        image_paths: List[str],
        data_type: ImageDataType = ImageDataType.IMAGE_GROUP,
        created_by: str = "system",
        metadata: Dict = None
    ) -> Tuple[ImageGroup, List[ImageRecord]]:
        """创建图片组"""
        group_id = str(uuid.uuid4())[:12]
        
        # 创建组
        group = ImageGroup(
            group_id=group_id,
            group_name=group_name,
            data_type=data_type,
            created_by=created_by,
            metadata=metadata or {},
        )
        
        # 创建组内图片
        images = []
        for idx, path in enumerate(image_paths):
            asset_id = f"asset_{group_id}_{idx}"
            
            # 获取图片尺寸
            width, height = self._get_image_size(path)
            
            image = self.create_single_image(
                asset_id=asset_id,
                image_path=path,
                width=width,
                height=height,
                created_by=created_by,
            )
            
            # 设置为组图类型
            image.data_type = data_type
            image.group_id = group_id
            
            self.images[image.data_id] = image
            group.images.append(image.data_id)
            self._index_by_group[group_id].append(image.data_id)
            images.append(image)
        
        group.total_images = len(images)
        self.groups[group_id] = group
        
        # 保存组信息到数据库
        self._save_group_to_db(group)
        
        logger.info(f"Created image group: {group_id} with {len(images)} images")
        return group, images
    
    def create_multi_turn_images(
        self,
        original_image_path: str,
        edited_image_paths: List[str],
        group_name: str = "",
        created_by: str = "system"
    ) -> Tuple[ImageGroup, List[ImageRecord]]:
        """创建多轮编辑图片组"""
        group_id = str(uuid.uuid4())[:12]
        
        # 创建原始图片
        original_asset_id = f"asset_{group_id}_original"
        width, height = self._get_image_size(original_image_path)
        
        original_image = self.create_single_image(
            asset_id=original_asset_id,
            image_path=original_image_path,
            width=width,
            height=height,
            created_by=created_by,
        )
        
        # 设置为多轮图
        original_image.data_type = ImageDataType.MULTI_TURN
        original_image.group_id = group_id
        original_image.turn_index = 0
        self.images[original_image.data_id] = original_image
        
        all_images = [original_image]
        lineage = [original_image.data_id]
        
        # 创建编辑轮次图片
        for idx, edit_path in enumerate(edited_image_paths):
            edit_asset_id = f"asset_{group_id}_edit_{idx}"
            edit_width, edit_height = self._get_image_size(edit_path)
            
            edit_image = self.create_single_image(
                asset_id=edit_asset_id,
                image_path=edit_path,
                width=edit_width,
                height=edit_height,
                created_by=created_by,
            )
            
            edit_image.data_type = ImageDataType.MULTI_TURN
            edit_image.group_id = group_id
            edit_image.turn_index = idx + 1
            edit_image.parent_id = lineage[-1]  # 指向上一轮
            edit_image.lineage = lineage.copy()
            
            self.images[edit_image.data_id] = edit_image
            all_images.append(edit_image)
            lineage.append(edit_image.data_id)
        
        # 创建组
        group = ImageGroup(
            group_id=group_id,
            group_name=group_name or f"Multi-turn {group_id}",
            data_type=ImageDataType.MULTI_TURN,
            images=[img.data_id for img in all_images],
            turn_count=len(edited_image_paths),
            created_by=created_by,
        )
        
        self.groups[group_id] = group
        
        # 更新索引
        for img in all_images:
            self._index_by_group[group_id].append(img.data_id)
        
        self._save_group_to_db(group)
        
        logger.info(f"Created multi-turn group: {group_id} with {len(all_images)} turns")
        return group, all_images
    
    def _get_image_size(self, image_path: str) -> Tuple[int, int]:
        """获取图片尺寸"""
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.size
        except ImportError:
            # 尝试使用cv2
            try:
                import cv2
                img = cv2.imread(image_path)
                if img is not None:
                    h, w = img.shape[:2]
                    return w, h
            except Exception:
                logger.warning(f"cv2 failed to read image: {image_path}")
                pass
        except Exception as e:
            logger.warning(f"Failed to get image size: {e}")
        return 0, 0
    
    def _save_image_to_db(self, image: ImageRecord):
        """保存图片到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO images (
                data_id, asset_id, image_path, thumbnail_path, width, height,
                file_size, file_hash, data_type, group_id, turn_index,
                source, source_url, operation_type, description, status, review_status,
                quality_score, tags, is_starred, is_bookmarked, parent_id, version,
                lineage, metadata, created_by, created_at, updated_at,
                reviewed_by, reviewed_at, is_deleted, deleted_at, deleted_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            image.data_id, image.asset_id, image.image_path, image.thumbnail_path,
            image.width, image.height, image.file_size, image.file_hash,
            image.data_type.value, image.group_id, image.turn_index,
            image.source.value, image.source_url, image.operation_type.value,
            image.description, image.status.value, image.review_status.value,
            image.quality_score, json.dumps(image.tags), image.is_starred, image.is_bookmarked,
            image.parent_id, image.version, json.dumps(image.lineage),
            json.dumps(image.metadata), image.created_by, image.created_at, image.updated_at,
            image.reviewed_by, image.reviewed_at, image.is_deleted, image.deleted_at, image.deleted_by
        ))
        self.conn.commit()
    
    def _save_group_to_db(self, group: ImageGroup):
        """保存组到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO image_groups (
                group_id, group_name, data_type, description, tags,
                metadata, turn_count, parent_group_id, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            group.group_id, group.group_name, group.data_type.value,
            group.description, json.dumps(group.tags), json.dumps(group.metadata),
            group.turn_count, group.parent_group_id, group.created_by,
            group.created_at, group.updated_at
        ))
        self.conn.commit()
    
    # ==================== 标注操作 ====================
    
    def add_annotation(
        self,
        data_id: str,
        annotation: AnnotationObject,
    ) -> bool:
        """添加标注对象"""
        if data_id not in self.images:
            logger.error(f"Image not found: {data_id}")
            return False
        
        image = self.images[data_id]
        annotation.id = str(uuid.uuid4())[:12]
        annotation.created_at = datetime.now().isoformat()
        annotation.updated_at = datetime.now().isoformat()
        
        image.annotations.append(annotation)
        image.annotation_count = len(image.annotations)
        image.updated_at = datetime.now().isoformat()
        
        # 更新状态
        if image.status == AnnotationStatus.DRAFT:
            image.status = AnnotationStatus.IN_PROGRESS
        
        self._save_annotation_to_db(data_id, annotation)
        self._save_image_to_db(image)
        
        logger.info(f"Added annotation {annotation.id} to {data_id}")
        return True
    
    def _save_annotation_to_db(self, data_id: str, annotation: AnnotationObject):
        """保存标注到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO annotations (
                annotation_id, data_id, annotation_type, label_id, label_name,
                label_category, label_color, bbox, points, polygon, keypoints,
                text_content, mask_data, confidence, attributes, notes,
                occluded, truncated, difficult, has_defect, created_by,
                created_at, updated_at, verified, verified_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            annotation.id, data_id, annotation.annotation_type.value,
            annotation.label.id, annotation.label.name,
            annotation.label.category, annotation.label.color,
            json.dumps(annotation.bbox.to_dict() if annotation.bbox else None),
            json.dumps([p.to_dict() for p in annotation.points]),
            json.dumps([p.to_dict() for p in annotation.polygon]),
            json.dumps([p.to_dict() for p in annotation.keypoints]),
            annotation.text, annotation.mask_data, annotation.confidence,
            json.dumps(annotation.attributes), annotation.notes,
            annotation.occluded, annotation.truncated, annotation.difficult,
            annotation.has_defect, annotation.created_by,
            annotation.created_at, annotation.updated_at, annotation.verified, annotation.verified_by
        ))
        self.conn.commit()
    
    def update_annotation(
        self,
        data_id: str,
        annotation_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """更新标注对象"""
        if data_id not in self.images:
            return False
        
        image = self.images[data_id]
        for ann in image.annotations:
            if ann.id == annotation_id:
                for key, value in updates.items():
                    if hasattr(ann, key):
                        setattr(ann, key, value)
                ann.updated_at = datetime.now().isoformat()
                image.updated_at = datetime.now().isoformat()
                self._save_image_to_db(image)
                logger.info(f"Updated annotation {annotation_id}")
                return True
        return False
    
    def delete_annotation(
        self,
        data_id: str,
        annotation_id: str,
    ) -> bool:
        """删除标注对象"""
        if data_id not in self.images:
            return False
        
        image = self.images[data_id]
        original_count = len(image.annotations)
        image.annotations = [a for a in image.annotations if a.id != annotation_id]
        
        if len(image.annotations) < original_count:
            image.annotation_count = len(image.annotations)
            image.updated_at = datetime.now().isoformat()
            
            # 从数据库删除
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM annotations WHERE annotation_id = ?", (annotation_id,))
            self.conn.commit()
            
            self._save_image_to_db(image)
            logger.info(f"Deleted annotation {annotation_id}")
            return True
        return False
    
    # ==================== 质检操作 ====================
    
    def perform_quality_inspection(
        self,
        data_id: str,
        inspector: str,
        result: str,
        score: float = 0.0,
        defects: List[QualityDefect] = None,
        comments: str = "",
        checked_items: Dict[str, bool] = None,
    ) -> QualityInspection:
        """执行质检"""
        if data_id not in self.images:
            raise ValueError(f"Image not found: {data_id}")
        
        inspection_id = str(uuid.uuid4())[:12]
        
        inspection = QualityInspection(
            inspection_id=inspection_id,
            data_id=data_id,
            inspector=inspector,
            result=result,
            score=score,
            defects=defects or [],
            comments=comments,
            checked_items=checked_items or {},
        )
        
        self.inspections[inspection_id] = inspection
        
        # 更新图片状态
        image = self.images[data_id]
        image.quality_score = score
        
        if defects:
            image.quality_defects = defects.copy()
            # 检查是否有严重缺陷
            has_critical = any(d.severity == QualitySeverity.CRITICAL for d in defects)
            if has_critical or score < 0.6:
                image.status = AnnotationStatus.QUALITY_FAILED
                image.review_status = ReviewStatus.FAILED
            else:
                image.status = AnnotationStatus.QUALITY_PASSED
                image.review_status = ReviewStatus.APPROVED
        else:
            image.status = AnnotationStatus.QUALITY_PASSED
            image.review_status = ReviewStatus.APPROVED
        
        # 保存到数据库
        self._save_inspection_to_db(inspection)
        self._save_image_to_db(image)
        
        logger.info(f"Quality inspection completed for {data_id}: {result} (score: {score})")
        return inspection
    
    def _save_inspection_to_db(self, inspection: QualityInspection):
        """保存质检记录到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO quality_inspections (
                inspection_id, data_id, inspector, result, score,
                defects, comments, checked_items, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inspection.inspection_id, inspection.data_id, inspection.inspector,
            inspection.result, inspection.score, json.dumps([d.to_dict() for d in inspection.defects]),
            inspection.comments, json.dumps(inspection.checked_items), inspection.created_at
        ))
        self.conn.commit()
    
    def add_defect(
        self,
        data_id: str,
        annotation_id: str,
        defect_type: QualityDefectType,
        severity: QualitySeverity,
        description: str,
        location: Dict = None,
        suggested_fix: str = "",
        annotated_by: str = "",
    ) -> bool:
        """添加缺陷标注"""
        if data_id not in self.images:
            return False
        
        defect = QualityDefect(
            id=str(uuid.uuid4())[:12],
            defect_type=defect_type,
            severity=severity,
            description=description,
            location=location or {},
            suggested_fix=suggested_fix,
            annotated_by=annotated_by,
        )
        
        image = self.images[data_id]
        
        if annotation_id:
            # 关联到特定标注
            for ann in image.annotations:
                if ann.id == annotation_id:
                    ann.has_defect = True
                    ann.defects.append(defect)
                    break
        
        image.quality_defects.append(defect)
        
        # 保存到数据库
        self._save_defect_to_db(defect, data_id, annotation_id)
        self._save_image_to_db(image)
        
        logger.info(f"Added defect {defect.id} to {data_id}/{annotation_id}")
        return True
    
    def _save_defect_to_db(self, defect: QualityDefect, data_id: str, annotation_id: str):
        """保存缺陷到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO quality_defects (
                defect_id, data_id, annotation_id, defect_type, severity,
                description, location, suggested_fix, annotated_by, annotated_at,
                is_fixed, fixed_by, fixed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            defect.id, data_id, annotation_id, defect.defect_type.value,
            defect.severity.value, defect.description, json.dumps(defect.location),
            defect.suggested_fix, defect.annotated_by, defect.annotated_at,
            defect.is_fixed, defect.fixed_by, defect.fixed_at
        ))
        self.conn.commit()
    
    def fix_defect(self, defect_id: str, fixed_by: str) -> bool:
        """标记缺陷已修复"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM quality_defects WHERE defect_id = ?", (defect_id,))
        row = cursor.fetchone()
        
        if not row:
            return False
        
        fixed_at = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE quality_defects SET is_fixed = 1, fixed_by = ?, fixed_at = ? WHERE defect_id = ?
        """, (fixed_by, fixed_at, defect_id))
        self.conn.commit()
        
        logger.info(f"Defect {defect_id} marked as fixed by {fixed_by}")
        return True
    
    # ==================== 筛选与对比 ====================
    
    def filter_images(
        self,
        data_types: List[ImageDataType] = None,
        statuses: List[AnnotationStatus] = None,
        sources: List[DataSource] = None,
        tags: List[str] = None,
        group_id: str = None,
        quality_score_min: float = None,
        quality_score_max: float = None,
        date_from: str = None,
        date_to: str = None,
        is_starred: bool = None,
        is_bookmarked: bool = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ImageRecord]:
        """筛选图片"""
        results = []
        
        for data_id, image in self.images.items():
            # 检查是否已删除
            if image.is_deleted and not include_deleted:
                continue
            
            # 检查数据类型
            if data_types and image.data_type not in data_types:
                continue
            
            # 检查状态
            if statuses and image.status not in statuses:
                continue
            
            # 检查来源
            if sources and image.source not in sources:
                continue
            
            # 检查标签
            if tags:
                if not any(t in image.tags for t in tags):
                    continue
            
            # 检查组ID
            if group_id and image.group_id != group_id:
                continue
            
            # 检查质量分数
            if quality_score_min is not None and image.quality_score < quality_score_min:
                continue
            if quality_score_max is not None and image.quality_score > quality_score_max:
                continue
            
            # 检查日期
            if date_from and image.created_at < date_from:
                continue
            if date_to and image.created_at > date_to:
                continue
            
            # 检查收藏
            if is_starred is not None and image.is_starred != is_starred:
                continue
            if is_bookmarked is not None and image.is_bookmarked != is_bookmarked:
                continue
            
            results.append(image)
        
        # 分页
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[offset:offset + limit]
    
    def compare_images(
        self,
        data_ids: List[str],
        compare_annotations: bool = True,
        compare_quality: bool = True,
    ) -> Dict[str, Any]:
        """对比多张图片"""
        images = []
        for data_id in data_ids:
            if data_id in self.images:
                images.append(self.images[data_id])
        
        if len(images) < 2:
            raise ValueError("Need at least 2 images to compare")
        
        result = {
            "images": [img.to_dict() for img in images],
            "comparison": {},
        }
        
        if compare_annotations:
            # 标注对比
            annotation_counts = [len(img.annotations) for img in images]
            label_distribution = {}
            for img in images:
                for ann in img.annotations:
                    label_name = ann.label.name
                    if label_name not in label_distribution:
                        label_distribution[label_name] = [0] * len(images)
                    label_distribution[label_name][images.index(img)] += 1
            
            result["comparison"]["annotations"] = {
                "counts": annotation_counts,
                "labels": label_distribution,
            }
        
        if compare_quality:
            # 质量对比
            quality_scores = [img.quality_score for img in images]
            defect_counts = [len(img.quality_defects) for img in images]
            
            result["comparison"]["quality"] = {
                "scores": quality_scores,
                "defect_counts": defect_counts,
                "average_score": sum(quality_scores) / len(quality_scores),
            }
        
        logger.info(f"Compared {len(images)} images")
        return result
    
    # ==================== 召回与回捞 ====================
    
    def soft_delete_image(self, data_id: str, deleted_by: str = "system") -> bool:
        """软删除图片"""
        if data_id not in self.images:
            return False
        
        image = self.images[data_id]
        image.is_deleted = True
        image.deleted_at = datetime.now().isoformat()
        image.deleted_by = deleted_by
        
        # 移动到已删除索引
        self._deleted_items[data_id] = image
        
        self._save_image_to_db(image)
        logger.info(f"Soft deleted image: {data_id}")
        return True
    
    def recall_deleted(
        self,
        data_id: str,
        restored_by: str = "system",
    ) -> bool:
        """召回已删除的数据"""
        if data_id not in self._deleted_items:
            logger.error(f"Deleted image not found: {data_id}")
            return False
        
        image = self._deleted_items.pop(data_id)
        image.is_deleted = False
        image.deleted_at = ""
        image.deleted_by = ""
        image.updated_at = datetime.now().isoformat()
        
        self.images[data_id] = image
        self._save_image_to_db(image)
        
        logger.info(f"Recalled image: {data_id}")
        return True
    
    def resurrect_batch(
        self,
        data_ids: List[str],
        tag_name: str = "resurrected",
        restored_by: str = "system",
    ) -> List[str]:
        """批量回捞数据"""
        resurrected = []
        
        for data_id in data_ids:
            if self.recall_deleted(data_id, restored_by):
                # 添加回捞标记
                self.add_tag(data_id, tag_name, "system")
                resurrected.append(data_id)
        
        logger.info(f"Resurrected {len(resurrected)} images")
        return resurrected
    
    def get_deleted_items(self, limit: int = 100) -> List[ImageRecord]:
        """获取已删除的数据"""
        deleted = list(self._deleted_items.values())
        deleted.sort(key=lambda x: x.deleted_at, reverse=True)
        return deleted[:limit]
    
    # ==================== 标签与标记 ====================
    
    def add_tag(
        self,
        data_id: str,
        tag_name: str,
        tag_type: str = "custom",
        tagged_by: str = "system",
    ) -> bool:
        """添加标签"""
        if data_id not in self.images:
            return False
        
        # 添加到图片记录
        if tag_name not in self.images[data_id].tags:
            self.images[data_id].tags.append(tag_name)
        
        # 创建标签记录
        tag = TagRecord(
            tag_id=str(uuid.uuid4())[:12],
            data_id=data_id,
            tag_name=tag_name,
            tag_type=tag_type,
            tagged_by=tagged_by,
        )
        
        self.tags[data_id].append(tag)
        self._index_by_tag[tag_name].append(data_id)
        
        # 保存到数据库
        self._save_tag_to_db(tag)
        self._save_image_to_db(self.images[data_id])
        
        logger.info(f"Added tag '{tag_name}' to {data_id}")
        return True
    
    def _save_tag_to_db(self, tag: TagRecord):
        """保存标签到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO tags (tag_id, data_id, tag_name, tag_type, tagged_by, tagged_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tag.tag_id, tag.data_id, tag.tag_name, tag.tag_type, tag.tagged_by, tag.tagged_at))
        self.conn.commit()
    
    def remove_tag(self, data_id: str, tag_name: str) -> bool:
        """移除标签"""
        if data_id not in self.images:
            return False
        
        if tag_name in self.images[data_id].tags:
            self.images[data_id].tags.remove(tag_name)
        
        # 从索引移除
        if data_id in self._index_by_tag.get(tag_name, []):
            self._index_by_tag[tag_name].remove(data_id)
        
        # 从数据库删除
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tags WHERE data_id = ? AND tag_name = ?", (data_id, tag_name))
        self.conn.commit()
        
        self._save_image_to_db(self.images[data_id])
        return True
    
    def star_image(self, data_id: str) -> bool:
        """收藏图片"""
        if data_id not in self.images:
            return False
        
        self.images[data_id].is_starred = True
        self.images[data_id].updated_at = datetime.now().isoformat()
        self._save_image_to_db(self.images[data_id])
        return True
    
    def unstar_image(self, data_id: str) -> bool:
        """取消收藏"""
        if data_id not in self.images:
            return False
        
        self.images[data_id].is_starred = False
        self.images[data_id].updated_at = datetime.now().isoformat()
        self._save_image_to_db(self.images[data_id])
        return True
    
    def bookmark_image(self, data_id: str) -> bool:
        """标记书签"""
        if data_id not in self.images:
            return False
        
        self.images[data_id].is_bookmarked = True
        self.images[data_id].updated_at = datetime.now().isoformat()
        self._save_image_to_db(self.images[data_id])
        return True
    
    # ==================== 评论与讨论 ====================
    
    def add_comment(
        self,
        data_id: str,
        user_id: str,
        user_name: str,
        content: str,
        mentions: List[str] = None,
        parent_id: str = "",
        annotation_id: str = "",
    ) -> Comment:
        """添加评论"""
        if data_id not in self.images:
            raise ValueError(f"Image not found: {data_id}")
        
        comment = Comment(
            comment_id=str(uuid.uuid4())[:12],
            data_id=data_id,
            user_id=user_id,
            user_name=user_name,
            content=content,
            mentions=mentions or [],
            parent_id=parent_id,
            annotation_id=annotation_id,
        )
        
        self.comments[data_id].append(comment)
        
        # 保存到数据库
        self._save_comment_to_db(comment)
        
        logger.info(f"Added comment {comment.comment_id} to {data_id}")
        return comment
    
    def _save_comment_to_db(self, comment: Comment):
        """保存评论到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO comments (
                comment_id,data_id, user_id, user_name, content,
                mentions, parent_id, annotation_id, created_at, updated_at,
                is_resolved, resolved_by, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comment.comment_id, comment.data_id, comment.user_id, comment.user_name,
            comment.content, json.dumps(comment.mentions), comment.parent_id,
            comment.annotation_id, comment.created_at, comment.updated_at,
            comment.is_resolved, comment.resolved_by, comment.resolved_at
        ))
        self.conn.commit()
    
    def get_comments(self, data_id: str) -> List[Comment]:
        """获取评论列表"""
        return self.comments.get(data_id, [])
    
    def resolve_comment(self, comment_id: str, resolved_by: str) -> bool:
        """标记评论已解决"""
        for comments in self.comments.values():
            for comment in comments:
                if comment.comment_id == comment_id:
                    comment.is_resolved = True
                    comment.resolved_by = resolved_by
                    comment.resolved_at = datetime.now().isoformat()
                    
                    # 更新数据库
                    cursor = self.conn.cursor()
                    cursor.execute("""
                        UPDATE comments SET is_resolved = 1, resolved_by = ?, resolved_at = ?
                        WHERE comment_id = ?
                    """, (resolved_by, comment.resolved_at, comment_id))
                    self.conn.commit()
                    
                    return True
        return False
    
    # ==================== 项目管理 ====================
    
    def create_project(
        self,
        name: str,
        description: str = "",
        created_by: str = "system",
    ) -> AnnotationProject:
        """创建标注项目"""
        project_id = str(uuid.uuid4())[:12]
        
        project = AnnotationProject(
            project_id=project_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        
        self.projects[project_id] = project
        self._save_project_to_db(project)
        self._save_metadata()
        
        logger.info(f"Created project: {project_id}")
        return project
    
    def _save_project_to_db(self, project: AnnotationProject):
        """保存项目到数据库"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO projects (
                project_id, name, description, labels, label_categories,
                annotation_types, keypoint_skeleton, keypoint_names,
                quality_threshold, require_review, allow_ai_preannotation,
                settings, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project.project_id, project.name, project.description,
            json.dumps([l.to_dict() for l in project.labels]),
            json.dumps(project.label_categories),
            json.dumps([t.value for t in project.annotation_types]),
            json.dumps(project.keypoint_skeleton),
            json.dumps(project.keypoint_names),
            project.quality_threshold, project.require_review,
            project.allow_ai_preannotation, json.dumps(project.settings),
            project.created_by, project.created_at, project.updated_at
        ))
        self.conn.commit()
    
    def add_label_to_project(
        self,
        project_id: str,
        label: AnnotationLabel,
    ) -> bool:
        """向项目添加标签"""
        if project_id not in self.projects:
            return False
        
        project = self.projects[project_id]
        project.labels.append(label)
        
        if label.category and label.category not in project.label_categories:
            project.label_categories[label.category] = []
        if label.category:
            project.label_categories[label.category].append(label.name)
        
        project.updated_at = datetime.now().isoformat()
        self._save_project_to_db(project)
        
        return True
    
    def get_project_labels(self, project_id: str) -> List[AnnotationLabel]:
        """获取项目标签"""
        if project_id not in self.projects:
            return []
        return self.projects[project_id].labels
    
    # ==================== 统计与导出 ====================
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_images = len(self.images)
        deleted_images = len(self._deleted_items)
        active_images = total_images - deleted_images
        
        # 按状态统计
        status_counts = defaultdict(int)
        type_counts = defaultdict(int)
        source_counts = defaultdict(int)
        total_quality_score = 0
        images_with_quality = 0
        
        for image in self.images.values():
            if not image.is_deleted:
                status_counts[image.status.value] += 1
                type_counts[image.data_type.value] += 1
                source_counts[image.source.value] += 1
                
                if image.quality_score > 0:
                    total_quality_score += image.quality_score
                    images_with_quality += 1
        
        # 标签统计
        tag_counts = defaultdict(int)
        for image in self.images.values():
            for tag in image.tags:
                tag_counts[tag] += 1
        
        # 组统计
        group_stats = {
            "total_groups": len(self.groups),
            "by_type": defaultdict(int),
        }
        for group in self.groups.values():
            group_stats["by_type"][group.data_type.value] += 1
        
        return {
            "total_images": total_images,
            "active_images": active_images,
            "deleted_images": deleted_images,
            "total_groups": len(self.groups),
            "total_projects": len(self.projects),
            "by_status": dict(status_counts),
            "by_data_type": dict(type_counts),
            "by_source": dict(source_counts),
            "average_quality_score": total_quality_score / images_with_quality if images_with_quality > 0 else 0,
            "top_tags": dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
            "group_stats": group_stats,
        }
    
    def export_coco_format(self, data_ids: List[str] = None) -> Dict[str, Any]:
        """导出为COCO格式"""
        if data_ids is None:
            data_ids = [d_id for d_id, img in self.images.items() if not img.is_deleted]
        
        images = []
        annotations = []
        categories = set()
        ann_id_counter = 1
        
        for idx, data_id in enumerate(data_ids):
            if data_id not in self.images:
                continue
            
            image = self.images[data_id]
            
            images.append({
                "id": idx + 1,
                "file_name": image.image_path,
                "width": image.width,
                "height": image.height,
            })
            
            for ann in image.annotations:
                categories.add(ann.label.name)
                
                if ann.bbox:
                    bbox = [ann.bbox.x, ann.bbox.y, ann.bbox.width, ann.bbox.height]
                    area = ann.bbox.area
                    
                    annotations.append({
                        "id": ann_id_counter,
                        "image_id": idx + 1,
                        "category_id": list(categories).index(ann.label.name) + 1,
                        "bbox": bbox,
                        "area": area,
                        "iscrowd": 0,
                        "segmentation": [[p.x, p.y] for p in ann.polygon] if ann.polygon else [],
                        "keypoints": [[p.x, p.y, int(p.visible)] for p in ann.keypoints] if ann.keypoints else [],
                    })
                    ann_id_counter += 1
        
        coco_categories = [
            {"id": i + 1, "name": cat, "supercategory": ""}
            for i, cat in enumerate(sorted(categories))
        ]
        
        return {
            "images": images,
            "annotations": annotations,
            "categories": coco_categories,
            "info": {
                "description": "Exported from NanoBot Factory Enhanced Annotation System",
                "version": "3.0.0",
                "date_created": datetime.now().isoformat(),
            }
        }
    
    def export_yolo_format(self, data_ids: List[str] = None, output_dir: str = None) -> bool:
        """导出为YOLO格式"""
        if output_dir is None:
            output_dir = os.path.join(self.storage_path, "yolo_export")
        os.makedirs(output_dir, exist_ok=True)
        
        if data_ids is None:
            data_ids = [d_id for d_id, img in self.images.items() if not img.is_deleted]
        
        # 收集所有类别
        all_labels = set()
        for data_id in data_ids:
            if data_id in self.images:
                for ann in self.images[data_id].annotations:
                    all_labels.add(ann.label.name)
        
        categories = sorted(list(all_labels))
        
        # 保存类别文件
        with open(os.path.join(output_dir, "classes.txt"), "w") as f:
            f.write("\n".join(categories))
        
        # 保存每个图片的标注
        for data_id in data_ids:
            if data_id not in self.images:
                continue
            
            image = self.images[data_id]
            
            with open(os.path.join(output_dir, f"{data_id}.txt"), "w") as f:
                for ann in image.annotations:
                    if ann.bbox and ann.label.name in categories:
                        cat_id = categories.index(ann.label.name)
                        
                        # 归一化坐标
                        x_center = (ann.bbox.x + ann.bbox.width / 2) / image.width
                        y_center = (ann.bbox.y + ann.bbox.height / 2) / image.height
                        w = ann.bbox.width / image.width
                        h = ann.bbox.height / image.height
                        
                        f.write(f"{cat_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}\n")
        
        logger.info(f"Exported {len(data_ids)} images to YOLO format in {output_dir}")
        return True
    
    # ==================== 批量操作 ====================
    
    def batch_update_status(
        self,
        data_ids: List[str],
        status: AnnotationStatus,
        updated_by: str = "system",
    ) -> int:
        """批量更新状态"""
        updated_count = 0
        
        for data_id in data_ids:
            if data_id in self.images and not self.images[data_id].is_deleted:
                self.images[data_id].status = status
                self.images[data_id].updated_at = datetime.now().isoformat()
                self._save_image_to_db(self.images[data_id])
                updated_count += 1
        
        logger.info(f"Batch updated status for {updated_count} images")
        return updated_count
    
    def batch_add_tag(
        self,
        data_ids: List[str],
        tag_name: str,
        tagged_by: str = "system",
    ) -> int:
        """批量添加标签"""
        tagged_count = 0
        
        for data_id in data_ids:
            if self.add_tag(data_id, tag_name, "system", tagged_by):
                tagged_count += 1
        
        logger.info(f"Batch added tag to {tagged_count} images")
        return tagged_count
    
    def batch_add_to_group(
        self,
        data_ids: List[str],
        group_id: str,
    ) -> int:
        """批量添加到组"""
        if group_id not in self.groups:
            logger.error(f"Group not found: {group_id}")
            return 0
        
        added_count = 0
        group = self.groups[group_id]
        
        for data_id in data_ids:
            if data_id in self.images and not self.images[data_id].is_deleted:
                image = self.images[data_id]
                image.group_id = group_id
                image.data_type = group.data_type
                
                if data_id not in group.images:
                    group.images.append(data_id)
                
                self._index_by_group[group_id].append(data_id)
                self._save_image_to_db(image)
                added_count += 1
        
        group.total_images = len(group.images)
        self._save_group_to_db(group)
        
        logger.info(f"Batch added {added_count} images to group {group_id}")
        return added_count
    
    # ==================== 查询操作 ====================
    
    def get_image(self, data_id: str) -> Optional[ImageRecord]:
        """获取图片记录"""
        return self.images.get(data_id)
    
    def get_group(self, group_id: str) -> Optional[ImageGroup]:
        """获取图片组"""
        return self.groups.get(group_id)
    
    def get_group_images(self, group_id: str) -> List[ImageRecord]:
        """获取组内所有图片"""
        if group_id not in self.groups:
            return []
        
        group = self.groups[group_id]
        return [self.images[d_id] for d_id in group.images if d_id in self.images]
    
    def get_image_by_asset_id(self, asset_id: str) -> Optional[ImageRecord]:
        """根据资产ID获取图片"""
        for image in self.images.values():
            if image.asset_id == asset_id:
                return image
        return None
    
    def search_images(
        self,
        keyword: str,
        search_fields: List[str] = None,
        limit: int = 50,
    ) -> List[ImageRecord]:
        """搜索图片"""
        if search_fields is None:
            search_fields = ["description", "tags", "metadata"]
        
        results = []
        keyword_lower = keyword.lower()
        
        for image in self.images.values():
            if image.is_deleted:
                continue
            
            matched = False
            
            for field in search_fields:
                if field == "description" and keyword_lower in image.description.lower():
                    matched = True
                    break
                elif field == "tags" and any(keyword_lower in tag.lower() for tag in image.tags):
                    matched = True
                    break
                elif field == "metadata":
                    metadata_str = json.dumps(image.metadata).lower()
                    if keyword_lower in metadata_str:
                        matched = True
                        break
            
            if matched:
                results.append(image)
        
        return results[:limit]
    
    def get_recent_images(self, limit: int = 20) -> List[ImageRecord]:
        """获取最近添加的图片"""
        images = [img for img in self.images.values() if not img.is_deleted]
        images.sort(key=lambda x: x.created_at, reverse=True)
        return images[:limit]
    
    def get_pending_review_items(self, limit: int = 50) -> List[ImageRecord]:
        """获取待审核项目"""
        pending = []
        
        for image in self.images.values():
            if not image.is_deleted and image.review_status == ReviewStatus.PENDING:
                pending.append(image)
        
        pending.sort(key=lambda x: x.created_at)
        return pending[:limit]
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'conn'):
            self.conn.close()
        logger.info("Annotation system closed")


# ==================== 全局实例管理 ====================

_annotation_manager: Optional[EnhancedAnnotationManager] = None

def get_annotation_manager(
    storage_path: str = "./annotations_enhanced",
    db_path: str = None
) -> EnhancedAnnotationManager:
    """获取全局标注管理器实例"""
    global _annotation_manager
    if _annotation_manager is None:
        _annotation_manager = EnhancedAnnotationManager(storage_path, db_path)
    return _annotation_manager

# ==================== 主程序测试 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 创建增强版标注管理器
    manager = EnhancedAnnotationManager("./test_annotations_enhanced")
    
    # 测试创建单张图片
    print("\n=== 测试单图创建 ===")
    # 注意: 实际使用需要真实图片路径
    # image = manager.create_single_image(
    #     asset_id="test_001",
    #     image_path="/path/to/image.jpg",
    #     width=1920,
    #     height=1080,
    #     source=DataSource.USER_UPLOAD,
    # )
    # print(f"Created: {image.data_id}")
    
    # 测试创建项目
    print("\n=== 测试项目创建 ===")
    project = manager.create_project(
        name="人物检测数据集",
        description="用于训练人物检测模型的标注数据集",
    )
    
    # 添加标签
    manager.add_label_to_project(
        project.project_id,
        AnnotationLabel.create("person", "human", "#FF0000")
    )
    manager.add_label_to_project(
        project.project_id,
        AnnotationLabel.create("car", "vehicle", "#00FF00")
    )
    manager.add_label_to_project(
        project.project_id,
        AnnotationLabel.create("face", "human", "#0000FF")
    )
    
    print(f"Created project: {project.project_id}")
    print(f"Labels: {[l.name for l in project.labels]}")
    
    # 测试筛选功能
    print("\n=== 测试筛选功能 ===")
    # results = manager.filter_images(
    #     statuses=[AnnotationStatus.IN_PROGRESS],
    #     tags=["important"],
    #     limit=10,
    # )
    # print(f"Found {len(results)} images")
    
    # 测试统计
    print("\n=== 测试统计功能 ===")
    stats = manager.get_statistics()
    print(f"Statistics: {json.dumps(stats, indent=2, ensure_ascii=False)}")
    
    manager.close()
    print("\n=== 测试完成 ===")


# ==================== 向后兼容别名 ====================
# 为了与 database_manager.py 的导入保持兼容

# ImageRecord 作为 ImageData 的别名
ImageData = ImageRecord
ImageTag = TagRecord  # ImageTag 指向 TagRecord

# AnnotationRecord 作为 AnnotationData 的别名  
AnnotationRecord = AnnotationObject
AnnotationData = AnnotationObject

# AnnotationComment 指向 Comment (实际类名是 Comment)
AnnotationComment = Comment

# ReviewStatus 可能需要定义
class ReviewStatus(Enum):
    """审核状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_NEEDED = "revision_needed"
