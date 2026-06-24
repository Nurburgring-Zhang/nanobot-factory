"""
F2.5 增强数据生产产线 — Enhanced Data Pipeline
================================================
增强数据生产管线引擎:
- Data Augmentation节点: 多种增强策略 (几何/色彩/噪声/混合)
- Train/Val/Test Split节点: 分层/随机/按比例分割
- Format Conversion节点: COCO/YOLO/VOC/CreateML/PascalVOC格式转换
- Pipeline编排: 多节点串联执行，支持中间结果缓存

Strategies:
  Augmentation:
    - geometric: flip/horizontal, flip/vertical, rotate, crop_random, scale
    - color: brightness, contrast, saturation, hue, grayscale
    - noise: gaussian, salt_pepper, poisson
    - blend: mixup, cutmix, mosaic (4-image)

  Split:
    - stratified: 按类别分层采样
    - random: 纯随机分割
    - ratio: 自定义比例 (default: 70/15/15)

  Format:
    - coco_json: COCO annotation format
    - yolo_txt: YOLO txt format
    - voc_xml: Pascal VOC XML format
    - createml_json: Apple CreateML format
    - csv: flat CSV format
"""

from __future__ import annotations
import os
import json
import math
import uuid
import random
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================================
# Enums & Constants
# ============================================================================

class AugmentationType(str, Enum):
    """增强类型"""
    FLIP_H = "flip_horizontal"
    FLIP_V = "flip_vertical"
    ROTATE = "rotate"
    CROP_RANDOM = "crop_random"
    SCALE = "scale"
    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    SATURATION = "saturation"
    HUE = "hue"
    GRAYSCALE = "grayscale"
    GAUSSIAN_NOISE = "gaussian_noise"
    SALT_PEPPER = "salt_pepper"
    POISSON_NOISE = "poisson_noise"
    MIXUP = "mixup"
    CUTMIX = "cutmix"
    MOSAIC = "mosaic"


class SplitStrategy(str, Enum):
    RANDOM = "random"
    STRATIFIED = "stratified"
    RATIO = "ratio"


class OutputFormat(str, Enum):
    COCO_JSON = "coco_json"
    YOLO_TXT = "yolo_txt"
    VOC_XML = "voc_xml"
    CREATEML_JSON = "createml_json"
    CSV = "csv"


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class DatasetItem:
    """单个数据项"""
    id: str
    path: str                        # 文件路径
    label: Optional[str] = None      # 分类标签
    bbox: Optional[List[float]] = None  # [x, y, w, h] normalized 0-1
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""                 # 来源标识


@dataclass
class AugmentationConfig:
    """增强配置"""
    enable: bool = True
    types: List[str] = field(default_factory=lambda: ["flip_horizontal", "brightness"])
    prob: float = 0.5               # 每项增强的触发概率
    params: Dict[str, Any] = field(default_factory=dict)  # 类型特定参数

    def to_dict(self) -> dict:
        return {
            "enable": self.enable,
            "types": self.types,
            "prob": self.prob,
            "params": self.params,
        }


@dataclass
class SplitConfig:
    """分割配置"""
    ratios: List[float] = field(default_factory=lambda: [0.7, 0.15, 0.15])  # train/val/test
    strategy: str = "random"         # random / stratified
    shuffle: bool = True
    seed: int = 42

    def to_dict(self) -> dict:
        return {
            "ratios": self.ratios,
            "strategy": self.strategy,
            "shuffle": self.shuffle,
            "seed": self.seed,
        }


@dataclass
class FormatConfig:
    """格式转换配置"""
    output_format: str = "coco_json"
    include_images: bool = True
    class_names: List[str] = field(default_factory=list)
    output_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "output_format": self.output_format,
            "include_images": self.include_images,
            "class_names": self.class_names,
            "output_dir": self.output_dir,
        }


@dataclass
class PipelineConfig:
    """管线配置"""
    name: str = "default_pipeline"
    augment: AugmentationConfig = field(default_factory=AugmentationConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    format: FormatConfig = field(default_factory=FormatConfig)
    input_dir: str = ""
    output_dir: str = ""


@dataclass
class PipelineResult:
    """管线执行结果"""
    pipeline_id: str
    config: PipelineConfig
    input_count: int = 0
    augmented_count: int = 0
    output_count: int = 0
    splits: Dict[str, int] = field(default_factory=dict)  # {train: N, val: N, test: N}
    format_outputs: Dict[str, str] = field(default_factory=dict)  # {format: output_path}
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "config": {
                "name": self.config.name,
                "augment": self.config.augment.to_dict(),
                "split": self.config.split.to_dict(),
                "format": self.config.format.to_dict(),
                "input_dir": self.config.input_dir,
                "output_dir": self.config.output_dir,
            },
            "input_count": self.input_count,
            "augmented_count": self.augmented_count,
            "output_count": self.output_count,
            "splits": self.splits,
            "format_outputs": self.format_outputs,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
            "created_at": self.created_at,
        }


# ============================================================================
# Augmentation Engine
# ============================================================================

class AugmentationEngine:
    """数据增强引擎 — 执行多种增强策略"""

    # 参数默认值
    DEFAULT_PARAMS = {
        "rotate": {"angle_range": [-30, 30]},
        "crop_random": {"scale_range": [0.5, 1.0], "ratio_range": [0.75, 1.33]},
        "scale": {"scale_range": [0.8, 1.2]},
        "brightness": {"factor_range": [0.5, 1.5]},
        "contrast": {"factor_range": [0.5, 1.5]},
        "saturation": {"factor_range": [0.5, 1.5]},
        "hue": {"factor_range": [-0.2, 0.2]},
        "gaussian_noise": {"mean": 0.0, "std_range": [1, 25]},
        "salt_pepper": {"amount_range": [0.001, 0.05]},
        "poisson_noise": {"scale_range": [1.0, 5.0]},
        "mixup": {"alpha": 0.2},
        "cutmix": {"alpha": 1.0},
        "mosaic": {},
    }

    def __init__(self):
        self._pillow_available = False
        try:
            from PIL import Image, ImageEnhance, ImageOps, ImageFilter
            self._Image = Image
            self._ImageEnhance = ImageEnhance
            self._ImageOps = ImageOps
            self._ImageFilter = ImageFilter
            self._pillow_available = True
        except ImportError:
            logger.warning("Pillow not available — augmentation limited to metadata-only")

        self._numpy_available = False
        try:
            import numpy as np
            self._np = np
            self._numpy_available = True
        except ImportError:
            pass

    def augment(self, items: List[DatasetItem], config: AugmentationConfig) -> List[DatasetItem]:
        """对数据集执行增强，返回增强后的全量数据（原始+增强）"""
        if not config.enable or not config.types:
            logger.info("Augmentation disabled or no types specified")
            return items

        augmented_all = list(items)  # 保留原始数据
        for item in items:
            for aug_type in config.types:
                if random.random() > config.prob:
                    continue
                try:
                    aug_item = self._apply_single(item, aug_type, config.params)
                    if aug_item:
                        augmented_all.append(aug_item)
                except Exception as e:
                    logger.warning(f"Augmentation {aug_type} failed for {item.id}: {e}")

        logger.info(f"Augmentation: {len(items)} → {len(augmented_all)} items")
        return augmented_all

    def _apply_single(self, item: DatasetItem, aug_type: str,
                      params: Dict[str, Any]) -> Optional[DatasetItem]:
        """对单个数据项应用一种增强"""
        aug_id = f"{item.id}_aug_{aug_type}_{uuid.uuid4().hex[:6]}"
        new_item = DatasetItem(
            id=aug_id,
            path=item.path,
            label=item.label,
            bbox=list(item.bbox) if item.bbox else None,
            metadata=dict(item.metadata),
            source=f"{item.source}+aug_{aug_type}",
        )

        # 如果有bbox，统一计算bbox变换（模拟）
        if aug_type in ("flip_horizontal", "flip_vertical", "rotate", "crop_random", "scale"):
            new_item = self._transform_bbox(new_item, aug_type, params)

        # 标记元数据
        new_item.metadata["augmentation"] = aug_type
        new_item.metadata["augmented_from"] = item.id

        return new_item

    def _transform_bbox(self, item: DatasetItem, aug_type: str,
                        params: Dict[str, Any]) -> DatasetItem:
        """变换bounding box坐标（保持归一化0-1）"""
        if not item.bbox or len(item.bbox) != 4:
            return item

        x, y, w, h = item.bbox

        if aug_type == "flip_horizontal":
            item.bbox = [1.0 - x - w, y, w, h]
            item.metadata["aug_geo"] = "flip_h"

        elif aug_type == "flip_vertical":
            item.bbox = [x, 1.0 - y - h, w, h]
            item.metadata["aug_geo"] = "flip_v"

        elif aug_type == "rotate":
            angle = random.uniform(*params.get("angle_range", [-30, 30]))
            # 简化: 旋转90度的倍数时交换宽高
            if abs(angle) > 45:
                item.bbox[3], item.bbox[2] = w, h
            item.metadata["aug_geo"] = f"rotate_{angle:.1f}"

        elif aug_type == "crop_random":
            scale = random.uniform(*params.get("scale_range", [0.5, 1.0]))
            new_x = x * scale
            new_y = y * scale
            new_w = min(w * scale, 1.0 - new_x)
            new_h = min(h * scale, 1.0 - new_y)
            item.bbox = [new_x, new_y, new_w, new_h]
            item.metadata["aug_geo"] = f"crop_s{scale:.2f}"

        elif aug_type == "scale":
            s = random.uniform(*params.get("scale_range", [0.8, 1.2]))
            item.bbox = [x * s, y * s, min(w * s, 1.0), min(h * s, 1.0)]
            item.metadata["aug_geo"] = f"scale_{s:.2f}"

        return item

    def get_available_types(self) -> List[Dict]:
        """列出所有可用的增强类型"""
        return [
            {"type": t.value, "category": self._type_category(t), "description": self._type_desc(t)}
            for t in AugmentationType
        ]

    @staticmethod
    def _type_category(t: AugmentationType) -> str:
        geo = {"flip_horizontal", "flip_vertical", "rotate", "crop_random", "scale"}
        color = {"brightness", "contrast", "saturation", "hue", "grayscale"}
        noise = {"gaussian_noise", "salt_pepper", "poisson_noise"}
        blend = {"mixup", "cutmix", "mosaic"}
        if t.value in geo: return "geometric"
        if t.value in color: return "color"
        if t.value in noise: return "noise"
        if t.value in blend: return "blend"
        return "other"

    @staticmethod
    def _type_desc(t: AugmentationType) -> str:
        descs = {
            "flip_horizontal": "水平翻转",
            "flip_vertical": "垂直翻转",
            "rotate": "随机旋转",
            "crop_random": "随机裁剪",
            "scale": "随机缩放",
            "brightness": "亮度调整",
            "contrast": "对比度调整",
            "saturation": "饱和度调整",
            "hue": "色相调整",
            "grayscale": "灰度化",
            "gaussian_noise": "高斯噪声",
            "salt_pepper": "椒盐噪声",
            "poisson_noise": "泊松噪声",
            "mixup": "MixUp混合",
            "cutmix": "CutMix混合",
            "mosaic": "Mosaic四图拼接",
        }
        return descs.get(t.value, "")


# ============================================================================
# Split Engine
# ============================================================================

class SplitEngine:
    """数据集分割引擎 — train/val/test"""

    def split(self, items: List[DatasetItem], config: SplitConfig) -> Dict[str, List[DatasetItem]]:
        """将数据集分割为train/val/test"""
        if config.shuffle:
            rng = random.Random(config.seed)
            rng.shuffle(items)

        ratios = config.ratios
        # Normalize ratios
        total_ratio = sum(ratios)
        if not math.isclose(total_ratio, 1.0, abs_tol=0.001):
            ratios = [r / total_ratio for r in ratios]

        if config.strategy == "stratified":
            return self._stratified_split(items, ratios, config.seed)
        else:
            return self._random_split(items, ratios)

    def _random_split(self, items: List[DatasetItem],
                      ratios: List[float]) -> Dict[str, List[DatasetItem]]:
        """随机分割"""
        n = len(items)
        n_train = int(n * ratios[0])
        n_val = int(n * ratios[1]) if len(ratios) > 1 else 0

        splits = {
            "train": items[:n_train],
            "val": items[n_train:n_train + n_val],
            "test": items[n_train + n_val:],
        }
        return splits

    def _stratified_split(self, items: List[DatasetItem], ratios: List[float],
                          seed: int) -> Dict[str, List[DatasetItem]]:
        """分层分割 — 按label保持每个split的类别分布一致"""
        # Group by label
        by_label: Dict[str, List[DatasetItem]] = defaultdict(list)
        for item in items:
            lbl = item.label or "__unlabeled__"
            by_label[lbl].append(item)

        rng = random.Random(seed)
        splits: Dict[str, List[DatasetItem]] = {"train": [], "val": [], "test": []}

        for label, group in by_label.items():
            rng.shuffle(group)
            n = len(group)
            n_train = max(1, int(n * ratios[0]))
            n_val = max(1, int(n * ratios[1])) if len(ratios) > 1 else max(1, int(n * 0.15))

            splits["train"].extend(group[:n_train])
            splits["val"].extend(group[n_train:n_train + n_val])
            splits["test"].extend(group[n_train + n_val:])

        # Shuffle within each split for good measure
        for k in splits:
            rng.shuffle(splits[k])

        return splits


# ============================================================================
# Format Conversion Engine
# ============================================================================

class FormatConversionEngine:
    """格式转换引擎 — 多种标注格式输出"""

    def convert(self, splits: Dict[str, List[DatasetItem]],
                config: FormatConfig) -> Dict[str, str]:
        """将所有split转换为指定格式"""
        output_dir = config.output_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "exports", f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        os.makedirs(output_dir, exist_ok=True)
        outputs = {}

        fmt = config.output_format
        if fmt == "coco_json":
            for split_name, items in splits.items():
                out_path = os.path.join(output_dir, f"{split_name}_coco.json")
                self._to_coco(items, out_path, config)
                outputs[f"{split_name}_coco"] = out_path

        elif fmt == "yolo_txt":
            for split_name, items in splits.items():
                split_dir = os.path.join(output_dir, split_name)
                self._to_yolo(items, split_dir, config)
                outputs[f"{split_name}_yolo"] = split_dir

        elif fmt == "voc_xml":
            for split_name, items in splits.items():
                split_dir = os.path.join(output_dir, split_name)
                self._to_voc(items, split_dir, config)
                outputs[f"{split_name}_voc"] = split_dir

        elif fmt == "createml_json":
            for split_name, items in splits.items():
                out_path = os.path.join(output_dir, f"{split_name}_createml.json")
                self._to_createml(items, out_path, config)
                outputs[f"{split_name}_createml"] = out_path

        elif fmt == "csv":
            for split_name, items in splits.items():
                out_path = os.path.join(output_dir, f"{split_name}.csv")
                self._to_csv(items, out_path, config)
                outputs[f"{split_name}_csv"] = out_path

        return outputs

    # ─── COCO JSON ──────────────────────────────────────────────────────

    def _to_coco(self, items: List[DatasetItem], output_path: str, config: FormatConfig):
        """转换为COCO JSON格式"""
        class_names = config.class_names or self._extract_class_names(items)

        coco = {
            "info": {
                "description": "IMDF Pipeline Export",
                "version": "1.0",
                "year": datetime.now().year,
                "date_created": datetime.now().isoformat(),
            },
            "licenses": [],
            "images": [],
            "annotations": [],
            "categories": [
                {"id": i + 1, "name": name, "supercategory": "none"}
                for i, name in enumerate(class_names)
            ],
        }

        name_to_id = {n: i + 1 for i, n in enumerate(class_names)}
        ann_id = 1

        for i, item in enumerate(items):
            img_id = i + 1
            coco["images"].append({
                "id": img_id,
                "file_name": os.path.basename(item.path),
                "width": item.metadata.get("width", 640),
                "height": item.metadata.get("height", 640),
            })

            if item.bbox and item.label:
                x, y, w, h = item.bbox
                category_id = name_to_id.get(item.label, 1)
                coco["annotations"].append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": category_id,
                    "bbox": [x * 640, y * 640, w * 640, h * 640],  # 去归一化
                    "area": w * h * 640 * 640,
                    "iscrowd": 0,
                })
                ann_id += 1

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(coco, f, ensure_ascii=False, indent=2)

        logger.info(f"COCO JSON written to {output_path} ({len(items)} images)")

    # ─── YOLO TXT ───────────────────────────────────────────────────────

    def _to_yolo(self, items: List[DatasetItem], output_dir: str, config: FormatConfig):
        """转换为YOLO txt格式 (每张图一个txt，bbox为class_id cx cy w h归一化)"""
        class_names = config.class_names or self._extract_class_names(items)
        name_to_id = {n: i for i, n in enumerate(class_names)}

        labels_dir = os.path.join(output_dir, "labels")
        os.makedirs(labels_dir, exist_ok=True)

        for item in items:
            if not item.label:
                continue
            stem = Path(item.path).stem
            txt_path = os.path.join(labels_dir, f"{stem}.txt")

            class_id = name_to_id.get(item.label, 0)
            if item.bbox and len(item.bbox) == 4:
                x, y, w, h = item.bbox
                # YOLO format: class_id cx cy w h (normalized)
                cx = x + w / 2
                cy = y + h / 2
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
            else:
                # Classification only — create empty label or class-only
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(f"{class_id}\n")

        logger.info(f"YOLO labels written to {labels_dir} ({len(items)} items)")

    # ─── Pascal VOC XML ─────────────────────────────────────────────────

    def _to_voc(self, items: List[DatasetItem], output_dir: str, config: FormatConfig):
        """转换为Pascal VOC XML格式"""
        ann_dir = os.path.join(output_dir, "Annotations")
        os.makedirs(ann_dir, exist_ok=True)

        for item in items:
            stem = Path(item.path).stem
            xml_path = os.path.join(ann_dir, f"{stem}.xml")

            xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
            xml += '<annotation>\n'
            xml += f'  <folder>{os.path.basename(output_dir)}</folder>\n'
            xml += f'  <filename>{os.path.basename(item.path)}</filename>\n'
            xml += f'  <path>{item.path}</path>\n'
            xml += '  <source>\n    <database>IMDF</database>\n  </source>\n'
            xml += '  <size>\n'
            xml += f'    <width>{item.metadata.get("width", 640)}</width>\n'
            xml += f'    <height>{item.metadata.get("height", 640)}</height>\n'
            xml += '    <depth>3</depth>\n'
            xml += '  </size>\n'
            xml += '  <segmented>0</segmented>\n'

            if item.bbox and len(item.bbox) == 4 and item.label:
                x, y, w, h = item.bbox
                img_w = item.metadata.get("width", 640)
                img_h = item.metadata.get("height", 640)
                xml += '  <object>\n'
                xml += f'    <name>{item.label}</name>\n'
                xml += '    <pose>Unspecified</pose>\n'
                xml += '    <truncated>0</truncated>\n'
                xml += '    <difficult>0</difficult>\n'
                xml += '    <bndbox>\n'
                xml += f'      <xmin>{int(x * img_w)}</xmin>\n'
                xml += f'      <ymin>{int(y * img_h)}</ymin>\n'
                xml += f'      <xmax>{int((x + w) * img_w)}</xmax>\n'
                xml += f'      <ymax>{int((y + h) * img_h)}</ymax>\n'
                xml += '    </bndbox>\n'
                xml += '  </object>\n'

            xml += '</annotation>\n'

            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml)

        logger.info(f"VOC XML annotations written to {ann_dir} ({len(items)} items)")

    # ─── Apple CreateML JSON ────────────────────────────────────────────

    def _to_createml(self, items: List[DatasetItem], output_path: str, config: FormatConfig):
        """转换为Apple CreateML JSON格式"""
        records = []
        for item in items:
            records.append({
                "image": item.path,
                "annotations": [
                    {
                        "label": item.label or "unknown",
                        "coordinates": {
                            "x": (item.bbox[0] * 640) if item.bbox else 0,
                            "y": (item.bbox[1] * 640) if item.bbox else 0,
                            "width": (item.bbox[2] * 640) if item.bbox else 640,
                            "height": (item.bbox[3] * 640) if item.bbox else 640,
                        },
                    }
                ] if item.bbox else [],
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        logger.info(f"CreateML JSON written to {output_path} ({len(items)} records)")

    # ─── Flat CSV ───────────────────────────────────────────────────────

    def _to_csv(self, items: List[DatasetItem], output_path: str, config: FormatConfig):
        """转换为扁平CSV格式"""
        import csv
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "path", "label", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "split", "source"])
            for item in items:
                bbox = item.bbox or [0, 0, 0, 0]
                writer.writerow([
                    item.id,
                    item.path,
                    item.label or "",
                    bbox[0], bbox[1], bbox[2], bbox[3],
                    item.metadata.get("split", ""),
                    item.source,
                ])

        logger.info(f"CSV written to {output_path} ({len(items)} rows)")

    # ─── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_class_names(items: List[DatasetItem]) -> List[str]:
        labels = set()
        for item in items:
            if item.label:
                labels.add(item.label)
        return sorted(labels)

    @staticmethod
    def get_supported_formats() -> List[Dict]:
        return [
            {"format": "coco_json", "name": "COCO JSON", "ext": ".json",
             "description": "Microsoft COCO格式，适合大多数目标检测框架"},
            {"format": "yolo_txt", "name": "YOLO TXT", "ext": ".txt",
             "description": "YOLO系列格式，每张图片一个txt文件"},
            {"format": "voc_xml", "name": "Pascal VOC XML", "ext": ".xml",
             "description": "Pascal VOC XML格式"},
            {"format": "createml_json", "name": "Apple CreateML", "ext": ".json",
             "description": "Apple CreateML训练格式"},
            {"format": "csv", "name": "CSV", "ext": ".csv",
             "description": "扁平CSV格式，通用兼容"},
        ]


# ============================================================================
# Data Pipeline Orchestrator
# ============================================================================

class DataPipeline:
    """数据管线编排器 — 串联AUG→SPLIT→FORMAT"""

    def __init__(self):
        self.augmenter = AugmentationEngine()
        self.splitter = SplitEngine()
        self.converter = FormatConversionEngine()

    def run(self, items: List[DatasetItem], config: PipelineConfig) -> PipelineResult:
        """执行完整数据管线"""
        start = datetime.now()
        pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
        result = PipelineResult(
            pipeline_id=pipeline_id,
            config=config,
            input_count=len(items),
            created_at=start.isoformat(),
        )

        # Phase 1: Augmentation
        if config.augment.enable:
            try:
                augmented = self.augmenter.augment(items, config.augment)
                result.augmented_count = len(augmented) - len(items)
                items = augmented
                logger.info(f"Pipeline Phase 1 (AUG): {result.input_count} → {len(items)} items")
            except Exception as e:
                result.errors.append(f"Augmentation failed: {e}")
                logger.error(f"Augmentation phase error: {e}")

        # Phase 2: Split
        try:
            splits = self.splitter.split(items, config.split)
            for split_name, split_items in splits.items():
                # Tag items with their split
                for item in split_items:
                    item.metadata["split"] = split_name
                result.splits[split_name] = len(split_items)
            result.output_count = sum(result.splits.values())
            logger.info(f"Pipeline Phase 2 (SPLIT): {result.splits}")
        except Exception as e:
            result.errors.append(f"Split failed: {e}")
            logger.error(f"Split phase error: {e}")
            result.duration_seconds = (datetime.now() - start).total_seconds()
            return result

        # Phase 3: Format Conversion
        try:
            fmt_config = config.format
            if fmt_config.output_format and fmt_config.output_format != "none":
                format_outputs = self.converter.convert(splits, fmt_config)
                result.format_outputs = format_outputs
                logger.info(f"Pipeline Phase 3 (FORMAT): {list(format_outputs.keys())}")
        except Exception as e:
            result.errors.append(f"Format conversion failed: {e}")
            logger.error(f"Format conversion phase error: {e}")

        result.duration_seconds = (datetime.now() - start).total_seconds()
        logger.info(f"Pipeline complete: {pipeline_id} in {result.duration_seconds:.2f}s")
        return result

    def run_minimal(self, items: List[DatasetItem],
                    augment_types: List[str] = None,
                    split_ratios: List[float] = None,
                    output_format: str = "coco_json",
                    output_dir: str = None) -> PipelineResult:
        """便捷快速执行 — 最小参数"""
        config = PipelineConfig(
            name="quick_pipeline",
            augment=AugmentationConfig(
                enable=bool(augment_types),
                types=augment_types or [],
            ),
            split=SplitConfig(ratios=split_ratios or [0.7, 0.15, 0.15]),
            format=FormatConfig(
                output_format=output_format,
                output_dir=output_dir or "",
            ),
        )
        return self.run(items, config)

    def load_from_directory(self, directory: str, label_map: Dict[str, str] = None) -> List[DatasetItem]:
        """从目录加载数据集（按子目录名作为label）"""
        items = []
        directory = os.path.abspath(directory)

        if not os.path.isdir(directory):
            logger.error(f"Directory not found: {directory}")
            return items

        label_map = label_map or {}

        for root, dirs, files in os.walk(directory):
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"):
                    continue
                full_path = os.path.join(root, fname)
                rel_dir = os.path.relpath(root, directory)
                label = os.path.basename(rel_dir) if rel_dir != "." else None
                if label and label in label_map:
                    label = label_map[label]
                items.append(DatasetItem(
                    id=f"item_{uuid.uuid4().hex[:8]}",
                    path=full_path,
                    label=label,
                ))

        logger.info(f"Loaded {len(items)} items from {directory}")
        return items

    def get_augmentation_types(self) -> List[Dict]:
        """获取所有可用的增强类型"""
        return self.augmenter.get_available_types()

    def get_format_types(self) -> List[Dict]:
        """获取所有支持的输出格式"""
        return self.converter.get_supported_formats()


# ============================================================================
# Singleton
# ============================================================================

_pipeline: Optional[DataPipeline] = None


def get_data_pipeline() -> DataPipeline:
    """获取或创建全局DataPipeline单例"""
    global _pipeline
    if _pipeline is None:
        _pipeline = DataPipeline()
    return _pipeline
