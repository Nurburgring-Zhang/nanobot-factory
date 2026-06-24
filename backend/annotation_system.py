#!/usr/bin/env python3
"""
Nanobot Factory - Image/Video Annotation System
图片/视频标注系统 - 商业级数据管理核心模块

@author MiniMax Agent
@date 2026-03-03
@description
- 支持图片和视频的多种标注类型
- 目标检测框标注
- 分类标签标注
- 关键点标注
- 区域/多边形标注
- OCR文字识别标注
- 视频帧标注和时间轴标注
- 标注数据导出为COCO/VOC/JSON格式
- 支持AI辅助标注
"""

import os
import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import base64
from io import BytesIO

logger = logging.getLogger(__name__)


class AnnotationType(Enum):
    """标注类型枚举"""
    BOUNDING_BOX = "bounding_box"           # 目标检测框
    POLYGON = "polygon"                     # 多边形区域
    POLYLINE = "polyline"                   # 折线/路径
    POINT = "point"                         # 关键点
    KEYPOINTS = "keypoints"                 # 骨骼关键点
    CLASSIFICATION = "classification"       # 分类标签
    TEXT = "text"                           # 文字标注/OCR
    MASK = "mask"                           # 分割蒙版
    CUBOID_3D = "cuboid_3d"                # 3D包围盒
    ELLIPSE = "ellipse"                    # 椭圆标注
    LINE = "line"                          # 直线标注
    ARROW = "arrow"                        # 箭头标注
    HIGHLIGHT = "highlight"                 # 高亮区域


class AnnotationStatus(Enum):
    """标注状态"""
    DRAFT = "draft"           # 草稿
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"    # 已完成
    REVIEWED = "reviewed"     # 已审核
    APPROVED = "approved"      # 已批准
    REJECTED = "rejected"      # 已拒绝


class MediaType(Enum):
    """媒体类型"""
    IMAGE = "image"
    VIDEO = "video"
    FRAME = "frame"  # 视频帧


@dataclass
class Point:
    """点坐标"""
    x: float
    y: float
    z: float = 0  # 可选的3D坐标
    visible: bool = True  # 关键点可见性
    
    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z, "visible": self.visible}


@dataclass
class BoundingBox:
    """边界框"""
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0  # 旋转角度
    
    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height, "rotation": self.rotation}


@dataclass
class AnnotationLabel:
    """标注标签"""
    id: str
    name: str
    category: str = ""
    color: str = "#FF0000"
    parent_id: str = ""  # 父标签ID（支持层级）
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(cls, name: str, category: str = "", color: str = "#FF0000") -> 'AnnotationLabel':
        return cls(
            id=str(uuid.uuid4())[:8],
            name=name,
            category=category,
            color=color,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnnotationObject:
    """标注对象"""
    id: str
    annotation_type: AnnotationType
    label: AnnotationLabel
    
    # 位置数据（根据类型不同使用不同字段）
    bbox: Optional[BoundingBox] = None
    points: List[Point] = field(default_factory=list)
    polygon: List[Point] = field(default_factory=list)  # 多边形顶点
    keypoints: List[Point] = field(default_factory=list)  # 骨骼关键点
    text: str = ""  # OCR或文字标注内容
    mask_data: str = ""  # Base64编码的蒙版数据
    confidence: float = 1.0  # AI标注置信度
    
    # 元数据
    attributes: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    occluded: bool = False  # 是否被遮挡
    truncated: bool = False  # 是否被截断
    difficult: bool = False  # 是否难以标注
    
    # 创建信息
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    verified: bool = False
    verified_by: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
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
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnnotationObject':
        label_data = data.get("label", {})
        label = AnnotationLabel(
            id=label_data.get("id", ""),
            name=label_data.get("name", ""),
            category=label_data.get("category", ""),
            color=label_data.get("color", "#FF0000"),
        )
        
        bbox_data = data.get("bbox")
        bbox = BoundingBox(**bbox_data) if bbox_data else None
        
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            annotation_type=AnnotationType(data.get("annotation_type", "bounding_box")),
            label=label,
            bbox=bbox,
            points=[Point(**p) for p in data.get("points", [])],
            polygon=[Point(**p) for p in data.get("polygon", [])],
            keypoints=[Point(**p) for p in data.get("keypoints", [])],
            text=data.get("text", ""),
            mask_data=data.get("mask_data", ""),
            confidence=data.get("confidence", 1.0),
            attributes=data.get("attributes", {}),
            notes=data.get("notes", ""),
            occluded=data.get("occluded", False),
            truncated=data.get("truncated", False),
            difficult=data.get("difficult", False),
            created_by=data.get("created_by", "system"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            verified=data.get("verified", False),
            verified_by=data.get("verified_by", ""),
        )


@dataclass
class FrameAnnotation:
    """视频帧标注"""
    frame_index: int
    timestamp: float  # 毫秒
    annotations: List[AnnotationObject] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "annotations": [a.to_dict() for a in self.annotations],
            "metadata": self.metadata,
        }


@dataclass
class ImageAnnotation:
    """单张图片标注"""
    id: str
    asset_id: str  # 关联的资产ID
    image_path: str
    width: int
    height: int
    
    # 标注数据
    annotations: List[AnnotationObject] = field(default_factory=list)
    global_labels: List[str] = field(default_factory=list)  # 图片级标签
    description: str = ""  # 图片描述
    
    # 状态
    status: AnnotationStatus = AnnotationStatus.DRAFT
    annotation_count: int = 0
    labeled_count: int = 0
    
    # 创建信息
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_by: str = ""
    reviewed_at: str = ""
    
    # 额外数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "image_path": self.image_path,
            "width": self.width,
            "height": self.height,
            "annotations": [a.to_dict() for a in self.annotations],
            "global_labels": self.global_labels,
            "description": self.description,
            "status": self.status.value,
            "annotation_count": len(self.annotations),
            "labeled_count": self.labeled_count,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "metadata": self.metadata,
        }
    
    def get_annotation_summary(self) -> Dict[str, Any]:
        """获取标注摘要"""
        label_counts = {}
        type_counts = {}
        
        for ann in self.annotations:
            label_counts[ann.label.name] = label_counts.get(ann.label.name, 0) + 1
            type_counts[ann.annotation_type.value] = type_counts.get(ann.annotation_type.value, 0) + 1
        
        return {
            "total_annotations": len(self.annotations),
            "label_distribution": label_counts,
            "type_distribution": type_counts,
            "label_categories": list(set(a.label.category for a in self.annotations)),
        }


@dataclass
class VideoAnnotation:
    """视频标注"""
    id: str
    asset_id: str
    video_path: str
    duration: float  # 总时长（秒）
    fps: float
    width: int
    height: int
    total_frames: int
    
    # 帧级标注
    frame_annotations: Dict[int, FrameAnnotation] = field(default_factory=dict)
    
    # 全局标注（适用于整个视频）
    global_annotations: List[AnnotationObject] = field(default_factory=list)
    global_labels: List[str] = field(default_factory=list)
    description: str = ""
    
    # 状态
    status: AnnotationStatus = AnnotationStatus.DRAFT
    annotated_frames: int = 0
    
    # 创建信息
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "video_path": self.video_path,
            "duration": self.duration,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "total_frames": self.total_frames,
            "frame_annotations": {k: v.to_dict() for k, v in self.frame_annotations.items()},
            "global_annotations": [a.to_dict() for a in self.global_annotations],
            "global_labels": self.global_labels,
            "description": self.description,
            "status": self.status.value,
            "annotated_frames": self.annotated_frames,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
    
    def timestamp_to_frame(self, timestamp: float) -> int:
        """时间戳转帧号"""
        return int(timestamp * self.fps)
    
    def frame_to_timestamp(self, frame: int) -> float:
        """帧号转时间戳"""
        return frame / self.fps


class AnnotationProject:
    """标注项目 - 管理一组相关的标注任务"""
    
    def __init__(self, project_id: str, name: str):
        self.id = project_id
        self.name = name
        self.labels: List[AnnotationLabel] = []
        self.label_categories: Dict[str, List[str]] = {}  # 分类: [标签列表]
        
        # 标注配置
        self.annotation_types: List[AnnotationType] = [AnnotationType.BOUNDING_BOX]
        self.keypoint_skeleton: List[Tuple[int, int]] = []  # 骨骼连接关系
        self.keypoint_names: List[str] = []  # 关键点名称
        
        # 导出配置
        self.export_formats: List[str] = ["coco", "voc", "yolo"]
        
        # 统计
        self.total_images: int = 0
        self.annotated_images: int = 0
        self.total_annotations: int = 0
        
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def add_label(self, label: AnnotationLabel):
        """添加标签"""
        self.labels.append(label)
        if label.category and label.category not in self.label_categories:
            self.label_categories[label.category] = []
        if label.category:
            self.label_categories[label.category].append(label.name)
    
    def get_label_by_name(self, name: str) -> Optional[AnnotationLabel]:
        """根据名称获取标签"""
        for label in self.labels:
            if label.name == name:
                return label
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "labels": [l.to_dict() for l in self.labels],
            "label_categories": self.label_categories,
            "annotation_types": [t.value for t in self.annotation_types],
            "keypoint_skeleton": self.keypoint_skeleton,
            "keypoint_names": self.keypoint_names,
            "export_formats": self.export_formats,
            "total_images": self.total_images,
            "annotated_images": self.annotated_images,
            "total_annotations": self.total_annotations,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AnnotationManager:
    """
    标注管理器 - 核心标注系统
    """
    
    def __init__(self, storage_path: str = "./annotations"):
        self.storage_path = storage_path
        self.annotations: Dict[str, ImageAnnotation] = {}  # image_id -> ImageAnnotation
        self.video_annotations: Dict[str, VideoAnnotation] = {}  # video_id -> VideoAnnotation
        self.projects: Dict[str, AnnotationProject] = {}
        
        os.makedirs(storage_path, exist_ok=True)
        self._load_metadata()
    
    def _load_metadata(self):
        """加载标注元数据"""
        metadata_file = os.path.join(self.storage_path, "metadata.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 加载项目
                for proj_data in data.get("projects", []):
                    proj = AnnotationProject(proj_data["id"], proj_data["name"])
                    proj.labels = [AnnotationLabel(**l) for l in proj_data.get("labels", [])]
                    proj.label_categories = proj_data.get("label_categories", {})
                    proj.annotation_types = [AnnotationType(t) for t in proj_data.get("annotation_types", [])]
                    proj.keypoint_skeleton = proj_data.get("keypoint_skeleton", [])
                    proj.keypoint_names = proj_data.get("keypoint_names", [])
                    proj.export_formats = proj_data.get("export_formats", ["coco", "voc", "yolo"])
                    self.projects[proj.id] = proj
                    
            except Exception as e:
                logger.error(f"Failed to load annotation metadata: {e}")
    
    def _save_metadata(self):
        """保存标注元数据"""
        metadata_file = os.path.join(self.storage_path, "metadata.json")
        data = {
            "projects": [p.to_dict() for p in self.projects.values()],
            "updated_at": datetime.now().isoformat(),
        }
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_project(self, name: str, annotation_types: List[str] = None) -> AnnotationProject:
        """创建标注项目"""
        project_id = str(uuid.uuid4())[:8]
        project = AnnotationProject(project_id, name)
        
        if annotation_types:
            project.annotation_types = [AnnotationType(t) for t in annotation_types]
        
        self.projects[project_id] = project
        self._save_metadata()
        return project
    
    def add_label_to_project(self, project_id: str, label: AnnotationLabel) -> bool:
        """向项目添加标签"""
        if project_id not in self.projects:
            return False
        self.projects[project_id].add_label(label)
        self._save_metadata()
        return True
    
    def create_image_annotation(
        self,
        asset_id: str,
        image_path: str,
        width: int,
        height: int,
    ) -> ImageAnnotation:
        """创建图片标注"""
        ann_id = str(uuid.uuid4())[:8]
        annotation = ImageAnnotation(
            id=ann_id,
            asset_id=asset_id,
            image_path=image_path,
            width=width,
            height=height,
        )
        self.annotations[asset_id] = annotation
        return annotation
    
    def add_annotation(
        self,
        asset_id: str,
        annotation: AnnotationObject,
    ) -> bool:
        """添加标注对象"""
        if asset_id not in self.annotations:
            logger.error(f"Annotation not found for asset: {asset_id}")
            return False
        
        self.annotations[asset_id].annotations.append(annotation)
        self.annotations[asset_id].updated_at = datetime.now().isoformat()
        self.annotations[asset_id].annotation_count = len(self.annotations[asset_id].annotations)
        
        self._save_annotation(asset_id)
        return True
    
    def update_annotation(
        self,
        asset_id: str,
        annotation_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """更新标注对象"""
        if asset_id not in self.annotations:
            return False
        
        for ann in self.annotations[asset_id].annotations:
            if ann.id == annotation_id:
                for key, value in updates.items():
                    if hasattr(ann, key):
                        setattr(ann, key, value)
                ann.updated_at = datetime.now().isoformat()
                self.annotations[asset_id].updated_at = datetime.now().isoformat()
                self._save_annotation(asset_id)
                return True
        return False
    
    def delete_annotation(
        self,
        asset_id: str,
        annotation_id: str,
    ) -> bool:
        """删除标注对象"""
        if asset_id not in self.annotations:
            return False
        
        original_count = len(self.annotations[asset_id].annotations)
        self.annotations[asset_id].annotations = [
            a for a in self.annotations[asset_id].annotations if a.id != annotation_id
        ]
        
        if len(self.annotations[asset_id].annotations) < original_count:
            self.annotations[asset_id].updated_at = datetime.now().isoformat()
            self.annotations[asset_id].annotation_count = len(self.annotations[asset_id].annotations)
            self._save_annotation(asset_id)
            return True
        return False
    
    def get_annotation(self, asset_id: str) -> Optional[ImageAnnotation]:
        """获取标注"""
        return self.annotations.get(asset_id)
    
    def get_video_annotation(self, asset_id: str) -> Optional[VideoAnnotation]:
        """获取视频标注"""
        return self.video_annotations.get(asset_id)
    
    def _save_annotation(self, asset_id: str):
        """保存标注到文件"""
        if asset_id in self.annotations:
            ann = self.annotations[asset_id]
            ann_file = os.path.join(self.storage_path, f"{asset_id}.json")
            with open(ann_file, 'w', encoding='utf-8') as f:
                json.dump(ann.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_annotation(self, asset_id: str) -> Optional[ImageAnnotation]:
        """从文件加载标注"""
        ann_file = os.path.join(self.storage_path, f"{asset_id}.json")
        if os.path.exists(ann_file):
            try:
                with open(ann_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.annotations[asset_id] = ImageAnnotation(**{
                    k: v for k, v in data.items()
                    if k in ImageAnnotation.__annotations__
                })
                return self.annotations[asset_id]
            except Exception as e:
                logger.error(f"Failed to load annotation: {e}")
        return None
    
    def export_coco_format(self, asset_ids: List[str] = None, output_path: str = None) -> Dict[str, Any]:
        """
        导出为COCO格式
        COCO格式: {images: [], annotations: [], categories: []}
        """
        if asset_ids is None:
            asset_ids = list(self.annotations.keys())
        
        images = []
        annotations = []
        categories = set()
        ann_id_counter = 1
        
        for idx, asset_id in enumerate(asset_ids):
            ann = self.annotations.get(asset_id)
            if not ann:
                continue
            
            # 添加图片信息
            images.append({
                "id": idx + 1,
                "file_name": ann.image_path,
                "width": ann.width,
                "height": ann.height,
            })
            
            # 添加标注信息
            for obj in ann.annotations:
                categories.add(obj.label.name)
                
                if obj.bbox:
                    # 转换为COCO bbox格式 [x, y, width, height]
                    bbox = [obj.bbox.x, obj.bbox.y, obj.bbox.width, obj.bbox.height]
                    area = obj.bbox.width * obj.bbox.height
                    
                    annotations.append({
                        "id": ann_id_counter,
                        "image_id": idx + 1,
                        "category_id": list(categories).index(obj.label.name) + 1,
                        "bbox": bbox,
                        "area": area,
                        "iscrowd": 0,
                        "segmentation": [[p.x, p.y] for p in obj.polygon] if obj.polygon else [],
                        "keypoints": [[p.x, p.y, int(p.visible)] for p in obj.keypoints] if obj.keypoints else [],
                    })
                    ann_id_counter += 1
        
        # 构建categories
        coco_categories = [
            {"id": i + 1, "name": cat, "supercategory": ""}
            for i, cat in enumerate(sorted(categories))
        ]
        
        result = {
            "images": images,
            "annotations": annotations,
            "categories": coco_categories,
            "info": {
                "description": "Exported from Nanobot Factory",
                "version": "1.0",
                "date_created": datetime.now().isoformat(),
            }
        }
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        
        return result
    
    def export_voc_format(self, asset_id: str, output_dir: str) -> bool:
        """
        导出为Pascal VOC格式
        """
        ann = self.annotations.get(asset_id)
        if not ann:
            return False
        
        import xml.etree.ElementTree as ET
        
        # 创建XML结构
        annotation = ET.Element('annotation')
        
        # 添加图片信息
        folder = ET.SubElement(annotation, 'folder')
        folder.text = 'images'
        
        filename = ET.SubElement(annotation, 'filename')
        filename.text = os.path.basename(ann.image_path)
        
        size = ET.SubElement(annotation, 'size')
        width_el = ET.SubElement(size, 'width')
        width_el.text = str(ann.width)
        height_el = ET.SubElement(size, 'height')
        height_el.text = str(ann.height)
        depth = ET.SubElement(size, 'depth')
        depth.text = '3'
        
        # 添加标注
        for obj in ann.annotations:
            if obj.bbox:
                obj_el = ET.SubElement(annotation, 'object')
                
                name = ET.SubElement(obj_el, 'name')
                name.text = obj.label.name
                
                difficult = ET.SubElement(obj_el, 'difficult')
                difficult.text = '1' if obj.difficult else '0'
                
                bndbox = ET.SubElement(obj_el, 'bndbox')
                xmin = ET.SubElement(bndbox, 'xmin')
                xmin.text = str(int(obj.bbox.x))
                ymin = ET.SubElement(bndbox, 'ymin')
                ymin.text = str(int(obj.bbox.y))
                xmax = ET.SubElement(bndbox, 'xmax')
                xmax.text = str(int(obj.bbox.x + obj.bbox.width))
                ymax = ET.SubElement(bndbox, 'ymax')
                ymax.text = str(int(obj.bbox.y + obj.bbox.height))
        
        # 保存XML
        xml_filename = os.path.splitext(os.path.basename(ann.image_path))[0] + '.xml'
        xml_path = os.path.join(output_dir, xml_filename)
        
        tree = ET.ElementTree(annotation)
        tree.write(xml_path, encoding='utf-8', xml_declaration=True)
        
        return True
    
    def export_yolo_format(self, asset_id: str, output_dir: str, categories: List[str]) -> bool:
        """
        导出为YOLO格式
        YOLO格式: 每行一个目标 "category_id x_center y_center width height" (归一化)
        """
        ann = self.annotations.get(asset_id)
        if not ann:
            return False
        
        with open(os.path.join(output_dir, f"{asset_id}.txt"), 'w') as f:
            for obj in ann.annotations:
                if obj.bbox:
                    if obj.label.name not in categories:
                        continue
                    
                    cat_id = categories.index(obj.label.name)
                    
                    # 计算归一化坐标
                    x_center = (obj.bbox.x + obj.bbox.width / 2) / ann.width
                    y_center = (obj.bbox.y + obj.bbox.height / 2) / ann.height
                    w = obj.bbox.width / ann.width
                    h = obj.bbox.height / ann.height
                    
                    f.write(f"{cat_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}\n")
        
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取标注统计信息"""
        total_images = len(self.annotations)
        annotated_images = sum(1 for a in self.annotations.values() if a.annotations)
        total_annotations = sum(len(a.annotations) for a in self.annotations.values())
        
        # 按类型统计
        type_stats = {}
        for ann in self.annotations.values():
            for obj in ann.annotations:
                type_name = obj.annotation_type.value
                type_stats[type_name] = type_stats.get(type_name, 0) + 1
        
        # 按标签统计
        label_stats = {}
        for ann in self.annotations.values():
            for obj in ann.annotations:
                label_name = obj.label.name
                label_stats[label_name] = label_stats.get(label_name, 0) + 1
        
        return {
            "total_images": total_images,
            "annotated_images": annotated_images,
            "annotation_rate": annotated_images / total_images if total_images > 0 else 0,
            "total_annotations": total_annotations,
            "by_type": type_stats,
            "by_label": label_stats,
            "projects_count": len(self.projects),
        }


# 全局标注管理器实例
_annotation_manager: Optional[AnnotationManager] = None


def get_annotation_manager(storage_path: str = "./annotations") -> AnnotationManager:
    """获取全局标注管理器"""
    global _annotation_manager
    if _annotation_manager is None:
        _annotation_manager = AnnotationManager(storage_path)
    return _annotation_manager


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 创建标注管理器
    manager = AnnotationManager("./test_annotations")
    
    # 创建项目
    project = manager.create_project("人物检测", ["bounding_box", "keypoints"])
    
    # 添加标签
    manager.add_label_to_project(project.id, AnnotationLabel.create("person", "human", "#FF0000"))
    manager.add_label_to_project(project.id, AnnotationLabel.create("car", "vehicle", "#00FF00"))
    manager.add_label_to_project(project.id, AnnotationLabel.create("face", "human", "#0000FF"))
    
    # 设置人体关键点
    project.keypoint_names = ["nose", "left_eye", "right_eye", "left_ear", "right_ear",
                             "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                             "left_wrist", "right_wrist", "left_hip", "right_hip",
                             "left_knee", "right_knee", "left_ankle", "right_ankle"]
    project.keypoint_skeleton = [
        (0, 1), (0, 2), (1, 3), (2, 4),  # 头部
        (5, 6), (5, 11), (6, 12), (11, 12),  # 躯干
        (5, 7), (7, 9), (6, 8), (8, 10),  # 手臂
        (11, 13), (13, 15), (12, 14), (14, 16)  # 腿
    ]
    
    # 创建图片标注
    img_ann = manager.create_image_annotation(
        asset_id="test_img_001",
        image_path="/path/to/image.jpg",
        width=1920,
        height=1080
    )
    
    # 添加目标检测标注
    obj1 = AnnotationObject(
        id=str(uuid.uuid4())[:8],
        annotation_type=AnnotationType.BOUNDING_BOX,
        label=AnnotationLabel.create("person", "human"),
        bbox=BoundingBox(x=100, y=50, width=200, height=400),
    )
    manager.add_annotation("test_img_001", obj1)
    
    # 添加关键点标注
    keypoints = [
        Point(x=200, y=80),   # nose
        Point(x=195, y=75), # left_eye
        Point(x=205, y=75), # right_eye
        Point(x=190, y=78), # left_ear
        Point(x=210, y=78), # right_ear
    ]
    obj2 = AnnotationObject(
        id=str(uuid.uuid4())[:8],
        annotation_type=AnnotationType.KEYPOINTS,
        label=AnnotationLabel.create("person", "human"),
        keypoints=keypoints,
    )
    manager.add_annotation("test_img_001", obj2)
    
    # 导出COCO格式
    result = manager.export_coco_format(["test_img_001"])
    print(f"Exported COCO format: {json.dumps(result, indent=2)}")
    
    # 获取统计
    stats = manager.get_statistics()
    print(f"Statistics: {json.dumps(stats, indent=2)}")
