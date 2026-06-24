"""
NanoBot Factory - Data Annotation Module
数据标注模块

@author MiniMax Agent
@date 2026-04-11
"""

import os
import json
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class AnnotationType(Enum):
    CLASSIFICATION = "classification"
    BOUNDING_BOX = "bounding_box"
    POLYGON = "polygon"

class AnnotationStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REVIEWED = "reviewed"

@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    label: str = ""
    confidence: float = 1.0

@dataclass
class ImageAnnotation:
    image_id: str
    image_path: str
    classification: Optional[str] = None
    bounding_boxes: List[BoundingBox] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: AnnotationStatus = AnnotationStatus.PENDING
    annotator: Optional[str] = None
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    ai_suggestions: Dict = field(default_factory=dict)

class AnnotationLabelStudio:
    """数据标注管理"""
    
    def __init__(self, storage_path: str = "./annotations"):
        self.storage_path = storage_path
        self.projects: Dict[str, Dict] = {}
        os.makedirs(storage_path, exist_ok=True)
    
    def create_project(self, name: str, categories: List[str]) -> str:
        project_id = str(uuid.uuid4())
        self.projects[project_id] = {
            "id": project_id,
            "name": name,
            "categories": categories,
            "images": [],
            "stats": {"total": 0, "annotated": 0, "reviewed": 0}
        }
        return project_id
    
    def add_image(self, project_id: str, image_path: str) -> str:
        if project_id not in self.projects:
            raise ValueError("Project not found")
        
        image_id = str(uuid.uuid4())
        annotation = ImageAnnotation(
            image_id=image_id,
            image_path=image_path
        )
        self.projects[project_id]["images"].append(annotation)
        self.projects[project_id]["stats"]["total"] += 1
        return image_id
    
    def set_classification(self, project_id: str, image_id: str, category: str) -> bool:
        project = self.projects.get(project_id)
        if not project:
            return False
        for img in project["images"]:
            if img.image_id == image_id:
                img.classification = category
                img.status = AnnotationStatus.COMPLETED
                project["stats"]["annotated"] += 1
                return True
        return False
    
    def add_bounding_box(self, project_id: str, image_id: str, bbox: BoundingBox) -> bool:
        project = self.projects.get(project_id)
        if not project:
            return False
        for img in project["images"]:
            if img.image_id == image_id:
                img.bounding_boxes.append(bbox)
                img.status = AnnotationStatus.IN_PROGRESS
                return True
        return False
    
    def export_coco(self, project_id: str) -> Dict:
        project = self.projects.get(project_id)
        if not project:
            return {}
        
        coco = {
            "categories": [{"id": i, "name": c} for i, c in enumerate(project["categories"])],
            "images": [],
            "annotations": []
        }
        
        ann_id = 1
        for i, img in enumerate(project["images"]):
            if img.status == AnnotationStatus.COMPLETED:
                coco["images"].append({"id": i+1, "file_name": os.path.basename(img.image_path)})
                for bbox in img.bounding_boxes:
                    cat_id = project["categories"].index(bbox.label) if bbox.label in project["categories"] else 0
                    coco["annotations"].append({
                        "id": ann_id,
                        "image_id": i+1,
                        "category_id": cat_id,
                        "bbox": [bbox.x, bbox.y, bbox.width, bbox.height]
                    })
                    ann_id += 1
        
        return coco
    
    def export_json(self, project_id: str) -> Dict:
        project = self.projects.get(project_id)
        if not project:
            return {}
        
        return {
            "project": {"id": project["id"], "name": project["name"]},
            "annotations": [
                {
                    "image_id": img.image_id,
                    "image_path": img.image_path,
                    "classification": img.classification,
                    "bounding_boxes": [
                        {"x": b.x, "y": b.y, "w": b.width, "h": b.height, "label": b.label}
                        for b in img.bounding_boxes
                    ],
                    "tags": img.tags,
                    "status": img.status.value
                }
                for img in project["images"]
            ]
        }

def get_annotation_studio() -> AnnotationLabelStudio:
    return AnnotationLabelStudio()

__all__ = ['AnnotationType', 'AnnotationStatus', 'BoundingBox', 'ImageAnnotation', 'AnnotationLabelStudio', 'get_annotation_studio']
