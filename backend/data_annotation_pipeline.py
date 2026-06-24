"""
NanoBot Factory - 数据标注管线
Data Annotation Pipeline

批量标注 + 格式转换 + CVAT/COCO/YOLO格式支持
"""
import os, json, logging, uuid, hashlib, shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import threading

logger = logging.getLogger(__name__)

# ============================================================================
# 标注格式定义
# ============================================================================

class AnnotationFormat(str, Enum):
    COCO = "coco"
    YOLO = "yolo"
    CVAT = "cvat"           # CVAT XML
    LABEL_STUDIO = "label_studio"
    VOC = "voc"             # PASCAL VOC XML
    FIFTYONE = "fiftyone"


@dataclass
class BoundingBox:
    x: float        # 归一化 0-1
    y: float
    width: float
    height: float
    category: str = ""
    category_id: int = 0
    confidence: float = 1.0
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SegmentationMask:
    points: List[List[float]]  # [[x1,y1], [x2,y2], ...]
    category: str = ""
    category_id: int = 0


@dataclass
class AnnotationItem:
    """单张图像的完整标注"""
    image_id: str
    image_path: str
    width: int = 0
    height: int = 0
    bboxes: List[BoundingBox] = field(default_factory=list)
    segments: List[SegmentationMask] = field(default_factory=list)
    caption: str = ""
    tags: List[str] = field(default_factory=list)
    keypoints: List[Dict] = field(default_factory=list)  # 关键点
    nlp_entities: List[Dict] = field(default_factory=list)  # NLP标注
    quality_score: float = 0.0
    source: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AnnotationDataset:
    name: str
    description: str = ""
    items: List[AnnotationItem] = field(default_factory=list)
    categories: List[Dict] = field(default_factory=list)
    version: str = "1.0"


# ============================================================================
# 格式转换引擎
# ============================================================================

class AnnotationConverter:
    """标注格式转换器 - 在各种标注格式之间互转"""

    @staticmethod
    def to_coco(dataset: AnnotationDataset) -> Dict:
        """转换为 COCO JSON 格式"""
        coco = {
            "info": {
                "description": dataset.description or dataset.name,
                "version": dataset.version,
                "year": datetime.now().year,
                "date_created": datetime.now().isoformat()
            },
            "licenses": [{"id": 1, "name": "NanoBot Factory", "url": ""}],
            "categories": [],
            "images": [],
            "annotations": []
        }

        # categories
        cat_map = {}
        for i, cat in enumerate(dataset.categories):
            coco["categories"].append({
                "id": i + 1,
                "name": cat.get("name", f"class_{i}"),
                "supercategory": cat.get("supercategory", "")
            })
            cat_map[cat.get("name", f"class_{i}")] = i + 1
        
        if not cat_map:
            # 从标注中自动提取category
            for item in dataset.items:
                for bbox in item.bboxes:
                    if bbox.category and bbox.category not in cat_map:
                        cat_id = len(cat_map) + 1
                        cat_map[bbox.category] = cat_id
                        coco["categories"].append({
                            "id": cat_id, "name": bbox.category, "supercategory": ""
                        })

        ann_id = 1
        for item in dataset.items:
            coco["images"].append({
                "id": item.image_id,
                "file_name": os.path.basename(item.image_path),
                "width": item.width,
                "height": item.height
            })
            
            for bbox in item.bboxes:
                # COCO格式: [x, y, width, height] (像素坐标)
                x_px = bbox.x * item.width
                y_px = bbox.y * item.height
                w_px = bbox.width * item.width
                h_px = bbox.height * item.height
                
                coco["annotations"].append({
                    "id": ann_id,
                    "image_id": item.image_id,
                    "category_id": cat_map.get(bbox.category, 1),
                    "bbox": [x_px, y_px, w_px, h_px],
                    "area": w_px * h_px,
                    "iscrowd": 0,
                    "segmentation": [],
                    "attributes": bbox.attributes
                })
                ann_id += 1

        return coco

    @staticmethod
    def to_yolo(dataset: AnnotationDataset, output_dir: str):
        """转换为 YOLO TXT 格式
        
        输出:
            output_dir/
                data.yaml
                train/images/*.jpg
                train/labels/*.txt
        """
        os.makedirs(f"{output_dir}/train/images", exist_ok=True)
        os.makedirs(f"{output_dir}/train/labels", exist_ok=True)
        
        # categories -> names
        names = []
        for cat in dataset.categories:
            names.append(cat.get("name", ""))
        
        # data.yaml
        yaml_content = f"""
# YOLO Dataset - {dataset.name}
# Generated by NanoBot Factory
path: {output_dir}
train: train/images
val: train/images
nc: {len(names)}
names: {json.dumps(names)}
"""
        with open(f"{output_dir}/data.yaml", "w") as f:
            f.write(yaml_content.strip())

        # 每个图像一个label文件
        for item in dataset.items:
            img_name = os.path.basename(item.image_path)
            base_name = os.path.splitext(img_name)[0]
            
            # 复制图像
            src = item.image_path
            dst = f"{output_dir}/train/images/{img_name}"
            if os.path.exists(src) and src != dst:
                shutil.copy2(src, dst)
            
            # 写label文件
            label_path = f"{output_dir}/train/labels/{base_name}.txt"
            with open(label_path, "w") as f:
                for bbox in item.bboxes:
                    # YOLO格式: class_id x_center y_center width height (归一化)
                    cat_id = bbox.category_id
                    # 如果没有category_id，从categories查找
                    if cat_id == 0 and bbox.category:
                        for i, cat in enumerate(dataset.categories):
                            if cat.get("name") == bbox.category:
                                cat_id = i
                                break
                    f.write(f"{cat_id} {bbox.x:.6f} {bbox.y:.6f} {bbox.width:.6f} {bbox.height:.6f}\n")

        return output_dir

    @staticmethod
    def to_label_studio(dataset: AnnotationDataset) -> Dict:
        """转换为 Label Studio JSON 格式"""
        ls_result = []
        for item in dataset.items:
            annotations = []
            for bbox in item.bboxes:
                annotations.append({
                    "original_width": item.width,
                    "original_height": item.height,
                    "image_rotation": 0,
                    "value": {
                        "x": bbox.x * 100,
                        "y": bbox.y * 100,
                        "width": bbox.width * 100,
                        "height": bbox.height * 100,
                        "rotation": 0,
                        "rectanglelabels": [bbox.category or f"class_{bbox.category_id}"]
                    },
                    "type": "rectangle",
                    "id": str(uuid.uuid4())
                })

            ls_result.append({
                "id": item.image_id,
                "data": {"image": item.image_path},
                "annotations": [{
                    "id": len(annotations),
                    "result": annotations,
                    "ground_truth": False
                }]
            })
        return ls_result

    @staticmethod
    def to_cvat_xml(dataset: AnnotationDataset) -> str:
        """转换为 CVAT XML 格式"""
        import xml.etree.ElementTree as ET
        from xml.dom import minidom

        ann = ET.Element("annotations")

        for item in dataset.items:
            image_el = ET.SubElement(ann, "image")
            image_el.set("id", str(item.image_id))
            image_el.set("name", os.path.basename(item.image_path))
            image_el.set("width", str(item.width))
            image_el.set("height", str(item.height))

            for bbox in item.bboxes:
                box_el = ET.SubElement(image_el, "box")
                box_el.set("label", bbox.category)
                box_el.set("occluded", "0")
                box_el.set("source", "manual")
                # CVAT使用像素坐标
                box_el.set("xtl", str(bbox.x * item.width))
                box_el.set("ytl", str(bbox.y * item.height))
                box_el.set("xbr", str((bbox.x + bbox.width) * item.width))
                box_el.set("ybr", str((bbox.y + bbox.height) * item.height))

        rough_string = ET.tostring(ann, encoding="unicode")
        return minidom.parseString(rough_string).toprettyxml(indent="  ")

    @staticmethod
    def from_cvat_json(cvat_items: List[Dict]) -> AnnotationDataset:
        """从CVAT JSON导入标注"""
        dataset = AnnotationDataset(name="imported_from_cvat")
        for item in cvat_items:
            ai = AnnotationItem(
                image_id=item.get("id", str(uuid.uuid4())),
                image_path=item.get("file_name", ""),
                width=item.get("width", 0),
                height=item.get("height", 0)
            )
            for ann in item.get("annotations", []):
                if ann.get("type") == "rectangle":
                    bbox = ann.get("bbox", {})
                    ai.bboxes.append(BoundingBox(
                        x=bbox.get("x", 0),
                        y=bbox.get("y", 0),
                        width=bbox.get("width", 0),
                        height=bbox.get("height", 0),
                        category=ann.get("category_id", ""),
                        confidence=ann.get("score", 1.0)
                    ))
            dataset.items.append(ai)
        return dataset


# ============================================================================
# 批量标注工具
# ============================================================================

class BatchLabeler:
    """批量标注器 - 自动标注 + 结果保存"""
    
    def __init__(self, auto_label_fn=None):
        """
        auto_label_fn: callable(image_path) -> [BoundingBox, ...]
        """
        self.auto_label_fn = auto_label_fn

    def create_dataset_from_images(self, image_dir: str, 
                                     recursive: bool = True,
                                     extensions: Tuple[str] = (".jpg", ".jpeg", ".png", ".webp", ".bmp")) -> AnnotationDataset:
        """从图像目录创建数据集"""
        dataset = AnnotationDataset(name=f"dataset_{Path(image_dir).name}")
        image_dir = Path(image_dir)
        
        if recursive:
            files = sorted(image_dir.rglob("*"))
        else:
            files = sorted(image_dir.glob("*"))
        
        for fpath in files:
            if fpath.suffix.lower() in extensions:
                try:
                    from PIL import Image
                    img = Image.open(fpath)
                    w, h = img.size
                    item = AnnotationItem(
                        image_id=str(len(dataset.items) + 1),
                        image_path=str(fpath),
                        width=w, height=h
                    )
                    dataset.items.append(item)
                except Exception as e:
                    logger.warning(f"Cannot open {fpath}: {e}")
        
        logger.info(f"Created dataset with {len(dataset.items)} images from {image_dir}")
        return dataset

    def auto_label_dataset(self, dataset: AnnotationDataset, 
                             update_existing: bool = False) -> AnnotationDataset:
        """自动标注数据集"""
        if not self.auto_label_fn:
            logger.warning("No auto_label_fn provided, returning dataset unchanged")
            return dataset
        
        for item in dataset.items:
            if item.bboxes and not update_existing:
                continue
            try:
                bboxes = self.auto_label_fn(item.image_path)
                if bboxes:
                    item.bboxes = bboxes
            except Exception as e:
                logger.warning(f"Auto-label failed for {item.image_path}: {e}")
        
        logger.info(f"Auto-labeled {len(dataset.items)} images, {sum(len(i.bboxes) for i in dataset.items)} total boxes")
        return dataset

    @staticmethod
    def merge_datasets(datasets: List[AnnotationDataset], new_name: str = "merged") -> AnnotationDataset:
        """合并多个数据集"""
        merged = AnnotationDataset(name=new_name)
        categories_seen = {}
        
        for ds in datasets:
            for cat in ds.categories:
                name = cat.get("name")
                if name and name not in categories_seen:
                    categories_seen[name] = cat
                    merged.categories.append(cat)
            
            for item in ds.items:
                merged.items.append(item)
        
        return merged


# ============================================================================
# 标注管线编排
# ============================================================================

class AnnotationPipeline:
    """标注全流程管线 - 目录扫描→标注→格式转换→保存"""
    
    def __init__(self, output_dir: str = "./data/annotations"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.labeler = BatchLabeler()
        self.converter = AnnotationConverter()
    
    def run_pipeline(self, image_dir: str, 
                      formats: List[AnnotationFormat] = None,
                      auto_label: bool = False,
                      auto_label_fn = None) -> Dict[str, str]:
        """运行完整标注管线"""
        if formats is None:
            formats = [AnnotationFormat.COCO]
        
        # 1. 创建数据集
        logger.info(f"Scanning {image_dir} for images...")
        dataset = self.labeler.create_dataset_from_images(image_dir)
        
        if len(dataset.items) == 0:
            return {"status": "no_images", "dir": image_dir}
        
        # 2. 自动标注
        if auto_label and auto_label_fn:
            self.labeler.auto_label_fn = auto_label_fn
            dataset = self.labeler.auto_label_dataset(dataset)
        
        # 3. 格式转换
        output_files = {}
        for fmt in formats:
            out_path = self._export_format(dataset, fmt)
            if out_path:
                output_files[fmt.value] = out_path
        
        # 4. 保存原始数据统计
        stats = {
            "total_images": len(dataset.items),
            "total_annotations": sum(len(i.bboxes) for i in dataset.items),
            "output_formats": list(output_files.keys()),
            "output_files": output_files,
            "status": "completed"
        }
        
        stats_path = self.output_dir / "pipeline_stats.json"
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)
        
        logger.info(f"Pipeline complete: {stats}")
        return stats
    
    def _export_format(self, dataset: AnnotationDataset, fmt: AnnotationFormat) -> str:
        """导出指定格式"""
        base_path = self.output_dir / dataset.name
        
        if fmt == AnnotationFormat.COCO:
            out = f"{base_path}/annotations.json"
            os.makedirs(os.path.dirname(out), exist_ok=True)
            coco = self.converter.to_coco(dataset)
            with open(out, "w") as f:
                json.dump(coco, f, indent=2)
            return out
        
        elif fmt == AnnotationFormat.YOLO:
            out_dir = f"{base_path}/yolo"
            self.converter.to_yolo(dataset, out_dir)
            return out_dir
        
        elif fmt == AnnotationFormat.LABEL_STUDIO:
            out = f"{base_path}/label_studio.json"
            os.makedirs(os.path.dirname(out), exist_ok=True)
            ls = self.converter.to_label_studio(dataset)
            with open(out, "w") as f:
                json.dump(ls, f, indent=2)
            return out
        
        elif fmt == AnnotationFormat.CVAT:
            out = f"{base_path}/annotations.xml"
            os.makedirs(os.path.dirname(out), exist_ok=True)
            xml = self.converter.to_cvat_xml(dataset)
            with open(out, "w") as f:
                f.write(xml)
            return out
        
        return ""
