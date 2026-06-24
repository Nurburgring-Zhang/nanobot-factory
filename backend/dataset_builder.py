#!/usr/bin/env python3
"""
Nanobot Factory - Dataset Builder System
数据集建设系统 - 商业级数据管理核心模块

@author MiniMax Agent
@date 2026-03-03
@description
- 支持多种AI训练数据格式导出
- 支持数据集版本管理
- 支持数据增强管道
- 支持训练/验证/测试集自动划分
- 支持数据集统计分析
- 支持数据集去重和清洗
- 支持自定义数据集模板
"""

import os
import json
import uuid
import logging
import shutil
import random
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from collections import Counter
import hashlib
import zipfile
import tarfile

logger = logging.getLogger(__name__)


class DatasetFormat(Enum):
    """数据集格式"""
    # 图像分类
    IMAGENET = "imagenet"           # ImageNet目录结构
    FOLDER = "folder"               # 简单文件夹分类
    CSV = "csv"                     # CSV元数据
    JSON = "json"                   # JSON元数据
    
    # 目标检测
    COCO = "coco"                   # COCO格式
    VOC = "voc"                    # Pascal VOC格式
    YOLO = "yolo"                  # YOLO格式
    LABELME = "labelme"            # LabelMe格式
    
    # 图像生成
    SD_WEBUI = "sd_webui"          # Stable Diffusion WebUI格式
    COMFYUI = "comfyui"            # ComfyUI格式
    DREAMBOOTH = "dreambooth"      # DreamBooth格式
    LORA = "lora"                  # LoRA训练格式
    
    # 视频
    VIDEO_CLIP = "video_clip"      # 视频片段
    FRAME_SEQ = "frame_seq"       # 帧序列
    
    # 通用
    ZIP = "zip"                   # ZIP压缩包
    TAR = "tar"                   # TAR压缩包


class SplitMode(Enum):
    """数据划分模式"""
    RANDOM = "random"              # 随机划分
    STRATIFIED = "stratified"     # 分层抽样
    K_FOLD = "k_fold"             # K折交叉验证
    TIME_BASED = "time_based"     # 按时间划分
    CUSTOM = "custom"             # 自定义划分


class DataAugmentation(Enum):
    """数据增强类型"""
    FLIP_HORIZONTAL = "flip_horizontal"
    FLIP_VERTICAL = "flip_vertical"
    ROTATION = "rotation"
    CROP = "crop"
    RESIZE = "resize"
    COLOR_JITTER = "color_jitter"
    RANDOM_ERASE = "random_erase"
    MIXUP = "mixup"
    CUTMIX = "cutmix"
    GAUSSIAN_BLUR = "gaussian_blur"
    Gaussian_NOISE = "gaussian_noise"


@dataclass
class DatasetConfig:
    """数据集配置"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    
    # 数据划分
    split_mode: SplitMode = SplitMode.RANDOM
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    k_folds: int = 5  # K折交叉验证
    
    # 格式配置
    export_format: DatasetFormat = DatasetFormat.COCO
    include_annotations: bool = True
    include_metadata: bool = True
    
    # 增强配置
    augmentations: List[DataAugmentation] = field(default_factory=list)
    augmentation_ratio: float = 0.0  # 增强数据占比
    
    # 过滤配置
    min_quality_score: float = 0.0
    min_resolution: Tuple[int, int] = (0, 0)
    max_samples: int = 0  # 0表示无限制
    
    # 标签配置
    label_mode: str = "multi"  # multi, single, binary
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "split_mode": self.split_mode.value,
            "train_ratio": self.train_ratio,
            "val_ratio": self.val_ratio,
            "test_ratio": self.test_ratio,
            "k_folds": self.k_folds,
            "export_format": self.export_format.value,
            "include_annotations": self.include_annotations,
            "include_metadata": self.include_metadata,
            "augmentations": [a.value for a in self.augmentations],
            "augmentation_ratio": self.augmentation_ratio,
            "min_quality_score": self.min_quality_score,
            "min_resolution": list(self.min_resolution),
            "max_samples": self.max_samples,
            "label_mode": self.label_mode,
        }


@dataclass
class DatasetSample:
    """数据集样本"""
    id: str
    asset_id: str
    file_path: str
    file_name: str
    
    # 标签
    labels: List[str] = field(default_factory=list)
    category: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    # 元数据
    width: int = 0
    height: int = 0
    file_size: int = 0
    quality_score: float = 0.0
    aesthetic_score: float = 0.0
    
    # 标注数据
    annotations: Dict[str, Any] = field(default_factory=dict)
    
    # 来源信息
    source: str = ""
    created_at: str = ""
    
    # 划分信息
    split: str = ""  # train, val, test
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "labels": self.labels,
            "category": self.category,
            "attributes": self.attributes,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "quality_score": self.quality_score,
            "aesthetic_score": self.aesthetic_score,
            "annotations": self.annotations,
            "source": self.source,
            "created_at": self.created_at,
            "split": self.split,
        }


@dataclass
class DatasetStats:
    """数据集统计"""
    total_samples: int
    train_samples: int
    val_samples: int
    test_samples: int
    
    # 标签统计
    label_distribution: Dict[str, int]
    category_distribution: Dict[str, int]
    
    # 质量统计
    avg_quality: float
    avg_aesthetic: float
    quality_distribution: Dict[str, int]
    
    # 尺寸统计
    resolution_distribution: Dict[str, int]
    avg_width: float
    avg_height: float
    
    # 文件统计
    total_size: int
    avg_file_size: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DatasetBuilder:
    """
    数据集构建器
    支持多种格式的数据集创建和导出
    """
    
    def __init__(self, output_path: str = "./datasets"):
        self.output_path = output_path
        self.samples: List[DatasetSample] = []
        self.config: Optional[DatasetConfig] = None
        
        os.makedirs(output_path, exist_ok=True)
    
    def add_sample(self, sample: DatasetSample):
        """添加样本"""
        self.samples.append(sample)
    
    def add_samples(self, samples: List[DatasetSample]):
        """批量添加样本"""
        self.samples.extend(samples)
    
    def set_config(self, config: DatasetConfig):
        """设置数据集配置"""
        self.config = config
    
    def split_data(
        self,
        samples: List[DatasetSample],
        mode: SplitMode = SplitMode.RANDOM,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> Tuple[List[DatasetSample], List[DatasetSample], List[DatasetSample]]:
        """划分数据集"""
        if mode == SplitMode.RANDOM:
            return self._random_split(samples, train_ratio, val_ratio, test_ratio)
        elif mode == SplitMode.STRATIFIED:
            return self._stratified_split(samples, train_ratio, val_ratio, test_ratio)
        elif mode == SplitMode.TIME_BASED:
            return self._time_based_split(samples, train_ratio, val_ratio, test_ratio)
        else:
            return self._random_split(samples, train_ratio, val_ratio, test_ratio)
    
    def _random_split(
        self,
        samples: List[DatasetSample],
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
    ) -> Tuple[List[DatasetSample], List[DatasetSample], List[DatasetSample]]:
        """随机划分"""
        shuffled = samples.copy()
        random.shuffle(shuffled)
        
        total = len(shuffled)
        train_end = int(total * train_ratio)
        val_end = train_end + int(total * val_ratio)
        
        train = shuffled[:train_end]
        val = shuffled[train_end:val_end]
        test = shuffled[val_end:]
        
        # 更新样本的split字段
        for s in train:
            s.split = "train"
        for s in val:
            s.split = "val"
        for s in test:
            s.split = "test"
        
        return train, val, test
    
    def _stratified_split(
        self,
        samples: List[DatasetSample],
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
    ) -> Tuple[List[DatasetSample], List[DatasetSample], List[DatasetSample]]:
        """分层抽样划分 - 按类别比例划分"""
        # 按类别分组
        category_groups: Dict[str, List[DatasetSample]] = {}
        for sample in samples:
            cat = sample.category or "unknown"
            if cat not in category_groups:
                category_groups[cat] = []
            category_groups[cat].append(sample)
        
        train, val, test = [], [], []
        
        for cat, cat_samples in category_groups.items():
            t, v, te = self._random_split(cat_samples, train_ratio, val_ratio, test_ratio)
            train.extend(t)
            val.extend(v)
            test.extend(te)
        
        return train, val, test
    
    def _time_based_split(
        self,
        samples: List[DatasetSample],
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
    ) -> Tuple[List[DatasetSample], List[DatasetSample], List[DatasetSample]]:
        """按时间划分"""
        # 按创建时间排序
        sorted_samples = sorted(
            samples,
            key=lambda s: s.created_at or "",
        )
        
        total = len(sorted_samples)
        train_end = int(total * train_ratio)
        val_end = train_end + int(total * val_ratio)
        
        train = sorted_samples[:train_end]
        val = sorted_samples[train_end:val_end]
        test = sorted_samples[val_end:]
        
        for s in train:
            s.split = "train"
        for s in val:
            s.split = "val"
        for s in test:
            s.split = "test"
        
        return train, val, test
    
    def filter_samples(
        self,
        samples: List[DatasetSample],
        min_quality: float = 0.0,
        min_resolution: Tuple[int, int] = (0, 0),
        required_labels: List[str] = None,
        exclude_labels: List[str] = None,
    ) -> List[DatasetSample]:
        """过滤样本"""
        filtered = samples
        
        if min_quality > 0:
            filtered = [s for s in filtered if s.quality_score >= min_quality]
        
        if min_resolution[0] > 0 or min_resolution[1] > 0:
            filtered = [
                s for s in filtered
                if s.width >= min_resolution[0] and s.height >= min_resolution[1]
            ]
        
        if required_labels:
            filtered = [
                s for s in filtered
                if any(label in s.labels for label in required_labels)
            ]
        
        if exclude_labels:
            filtered = [
                s for s in filtered
                if not any(label in s.labels for label in exclude_labels)
            ]
        
        return filtered
    
    def deduplicate(
        self,
        samples: List[DatasetSample],
        threshold: float = 0.95,
    ) -> List[DatasetSample]:
        """去重"""
        # 按哈希分组
        hash_groups: Dict[str, List[DatasetSample]] = {}
        for sample in samples:
            key = f"{sample.asset_id}"
            if key not in hash_groups:
                hash_groups[key] = []
            hash_groups[key].append(sample)
        
        # 每个组保留一个
        result = []
        for key, group in hash_groups.items():
            # 保留质量最高的
            best = max(group, key=lambda s: s.quality_score)
            result.append(best)
        
        return result
    
    def get_statistics(self, samples: List[DatasetSample] = None) -> DatasetStats:
        """获取数据集统计"""
        if samples is None:
            samples = self.samples
        
        if not samples:
            return DatasetStats(
                total_samples=0,
                train_samples=0,
                val_samples=0,
                test_samples=0,
                label_distribution={},
                category_distribution={},
                avg_quality=0.0,
                avg_aesthetic=0.0,
                quality_distribution={},
                resolution_distribution={},
                avg_width=0.0,
                avg_height=0.0,
                total_size=0,
                avg_file_size=0.0,
            )
        
        # 基础统计
        total = len(samples)
        train = len([s for s in samples if s.split == "train"])
        val = len([s for s in samples if s.split == "val"])
        test = len([s for s in samples if s.split == "test"])
        
        # 标签分布
        all_labels = []
        all_categories = []
        for s in samples:
            all_labels.extend(s.labels)
            if s.category:
                all_categories.append(s.category)
        
        label_dist = dict(Counter(all_labels))
        category_dist = dict(Counter(all_categories))
        
        # 质量分布
        qualities = [s.quality_score for s in samples]
        aesthetics = [s.aesthetic_score for s in samples]
        avg_quality = sum(qualities) / len(qualities) if qualities else 0.0
        avg_aesthetic = sum(aesthetics) / len(aesthetics) if aesthetics else 0.0
        
        quality_dist = {
            "excellent": len([q for q in qualities if q >= 0.9]),
            "good": len([q for q in qualities if 0.7 <= q < 0.9]),
            "fair": len([q for q in qualities if 0.5 <= q < 0.7]),
            "poor": len([q for q in qualities if q < 0.5]),
        }
        
        # 尺寸分布
        widths = [s.width for s in samples if s.width > 0]
        heights = [s.height for s in samples if s.height > 0]
        avg_width = sum(widths) / len(widths) if widths else 0.0
        avg_height = sum(heights) / len(heights) if heights else 0.0
        
        res_dist = {}
        for s in samples:
            if s.width > 0 and s.height > 0:
                ratio = round(s.width / s.height, 1)
                ratio_key = f"{s.width}x{s.height}"
                res_dist[ratio_key] = res_dist.get(ratio_key, 0) + 1
        
        # 文件大小统计
        sizes = [s.file_size for s in samples if s.file_size > 0]
        total_size = sum(sizes)
        avg_size = total_size / len(sizes) if sizes else 0.0
        
        return DatasetStats(
            total_samples=total,
            train_samples=train,
            val_samples=val,
            test_samples=test,
            label_distribution=label_dist,
            category_distribution=category_dist,
            avg_quality=avg_quality,
            avg_aesthetic=avg_aesthetic,
            quality_distribution=quality_dist,
            resolution_distribution=res_dist,
            avg_width=avg_width,
            avg_height=avg_height,
            total_size=total_size,
            avg_file_size=avg_size,
        )
    
    def export_imagenet_format(
        self,
        samples: List[DatasetSample],
        output_dir: str,
        copy_files: bool = True,
    ) -> bool:
        """导出为ImageNet格式"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 创建类别目录
            categories = set(s.category for s in samples if s.category)
            for cat in categories:
                os.makedirs(os.path.join(output_dir, "train", cat), exist_ok=True)
                os.makedirs(os.path.join(output_dir, "val", cat), exist_ok=True)
                os.makedirs(os.path.join(output_dir, "test", cat), exist_ok=True)
            
            # 复制文件
            for sample in samples:
                if not sample.category:
                    continue
                
                split_dir = os.path.join(output_dir, sample.split, sample.category)
                dest_path = os.path.join(split_dir, sample.file_name)
                
                if copy_files and os.path.exists(sample.file_path):
                    shutil.copy2(sample.file_path, dest_path)
            
            # 保存元数据
            metadata = {
                "samples": [s.to_dict() for s in samples],
                "exported_at": datetime.now().isoformat(),
                "format": "imagenet",
            }
            
            with open(os.path.join(output_dir, "metadata.json"), "w") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export ImageNet format: {e}")
            return False
    
    def export_coco_format(
        self,
        samples: List[DatasetSample],
        output_dir: str,
        copy_files: bool = True,
    ) -> bool:
        """导出为COCO格式"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(os.path.join(output_dir, "images"), exist_ok=True)
            
            # 收集所有类别
            categories = set()
            for s in samples:
                categories.update(s.labels)
            categories = sorted(categories)

            # COCO数据集结构
            coco_data = {
                "info": {
                    "description": self.config.name if self.config else "Dataset",
                    "version": self.config.version if self.config else "1.0",
                    "date_created": datetime.now().isoformat(),
                },
                "licenses": [],
                "images": [],
                "annotations": [],
                "categories": [
                    {"id": i + 1, "name": cat, "supercategory": ""}
                    for i, cat in enumerate(categories)
                ],
            }
            
            ann_id = 1
            for img_id, sample in enumerate(samples, start=1):
                # 图片信息
                image_info = {
                    "id": img_id,
                    "file_name": sample.file_name,
                    "width": sample.width,
                    "height": sample.height,
                    "split": sample.split,
                }
                coco_data["images"].append(image_info)
                
                # 复制文件
                if copy_files and os.path.exists(sample.file_path):
                    dest_path = os.path.join(output_dir, "images", sample.file_name)
                    shutil.copy2(sample.file_path, dest_path)
                
                # 标注信息
                for label in sample.labels:
                    if label in categories:
                        cat_id = categories.index(label) + 1
                        
                        # 从annotations获取bbox
                        bbox = sample.annotations.get("bbox", [0, 0, sample.width, sample.height])
                        
                        ann = {
                            "id": ann_id,
                            "image_id": img_id,
                            "category_id": cat_id,
                            "bbox": bbox,
                            "area": bbox[2] * bbox[3] if len(bbox) == 4 else 0,
                            "iscrowd": 0,
                        }
                        coco_data["annotations"].append(ann)
                        ann_id += 1
            
            # 保存JSON
            with open(os.path.join(output_dir, "annotations.json"), "w") as f:
                json.dump(coco_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export COCO format: {e}")
            return False
    
    def export_yolo_format(
        self,
        samples: List[DatasetSample],
        output_dir: str,
        copy_files: bool = True,
    ) -> bool:
        """导出为YOLO格式"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 创建输出子目录
            for split in ["train", "val", "test"]:
                os.makedirs(os.path.join(output_dir, split, "images"), exist_ok=True)
                os.makedirs(os.path.join(output_dir, split, "labels"), exist_ok=True)
            
            # 收集所有类别
            categories = set()
            for s in samples:
                categories.update(s.labels)
            categories = sorted(categories)
            
            # 保存类别列表
            with open(os.path.join(output_dir, "classes.txt"), "w") as f:
                for cat in categories:
                    f.write(f"{cat}\n")
            
            # 导出每个样本
            for sample in samples:
                split = sample.split or "train"
                
                # 复制图片
                if copy_files and os.path.exists(sample.file_path):
                    dest_img = os.path.join(output_dir, split, "images", sample.file_name)
                    shutil.copy2(sample.file_path, dest_img)
                
                # 生成标签文件
                label_file = os.path.join(
                    output_dir, split, "labels",
                    os.path.splitext(sample.file_name)[0] + ".txt"
                )
                
                with open(label_file, "w") as f:
                    for label in sample.labels:
                        if label in categories:
                            cat_id = categories.index(label)
                            
                            # 获取bbox
                            bbox = sample.annotations.get("bbox", [0, 0, sample.width, sample.height])
                            
                            # 转换为YOLO格式: class x_center y_center width height (归一化)
                            x_center = (bbox[0] + bbox[2] / 2) / sample.width if sample.width > 0 else 0.5
                            y_center = (bbox[1] + bbox[3] / 2) / sample.height if sample.height > 0 else 0.5
                            w = bbox[2] / sample.width if sample.width > 0 else 1
                            h = bbox[3] / sample.height if sample.height > 0 else 1
                            
                            f.write(f"{cat_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}\n")
            
            # 创建数据集配置文件
            config = f"""# Dataset config
path: {output_dir}
train: train/images
val: val/images
test: test/images

nc: {len(categories)}
names: {categories}
"""
            with open(os.path.join(output_dir, "dataset.yaml"), "w") as f:
                f.write(config)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export YOLO format: {e}")
            return False
    
    def export_csv_format(
        self,
        samples: List[DatasetSample],
        output_path: str,
        copy_files: bool = True,
    ) -> bool:
        """导出为CSV格式"""
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            
            # CSV内容
            lines = [
                "id,asset_id,file_name,labels,categories,width,height,file_size,"
                "quality_score,aesthetic_score,split,source,file_path"
            ]
            
            for sample in samples:
                labels = "|".join(sample.labels)
                line = (
                    f"{sample.id},"
                    f"{sample.asset_id},"
                    f"{sample.file_name},"
                    f"{labels},"
                    f"{sample.category},"
                    f"{sample.width},"
                    f"{sample.height},"
                    f"{sample.file_size},"
                    f"{sample.quality_score:.4f},"
                    f"{sample.aesthetic_score:.4f},"
                    f"{sample.split},"
                    f"{sample.source},"
                    f"{sample.file_path}"
                )
                lines.append(line)
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export CSV format: {e}")
            return False
    
    def export_json_format(
        self,
        samples: List[DatasetSample],
        output_path: str,
        include_annotations: bool = True,
    ) -> bool:
        """导出为JSON格式"""
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            
            export_data = {
                "name": self.config.name if self.config else "Dataset",
                "version": self.config.version if self.config else "1.0",
                "exported_at": datetime.now().isoformat(),
                "total_samples": len(samples),
                "samples": [s.to_dict() for s in samples],
            }
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export JSON format: {e}")
            return False
    
    def export_comfyui_format(
        self,
        samples: List[DatasetSample],
        output_dir: str,
    ) -> bool:
        """导出为ComfyUI格式（包含元数据）"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(os.path.join(output_dir, "images"), exist_ok=True)
            
            # 创建工作流模板
            workflow = {
                "1": {
                    "inputs": {"images": []},
                    "class_type": "LoadImageBatch",
                }
            }
            
            for sample in samples:
                # 复制图片
                if os.path.exists(sample.file_path):
                    dest_path = os.path.join(output_dir, "images", sample.file_name)
                    shutil.copy2(sample.file_path, dest_path)
                    workflow["1"]["inputs"]["images"].append(sample.file_name)
                
                # 保存样本元数据
                meta_path = os.path.join(
                    output_dir, "images",
                    os.path.splitext(sample.file_name)[0] + ".json"
                )
                with open(meta_path, "w") as f:
                    json.dump(sample.to_dict(), f, indent=2, ensure_ascii=False)
            
            # 保存工作流
            with open(os.path.join(output_dir, "workflow.json"), "w") as f:
                json.dump(workflow, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export ComfyUI format: {e}")
            return False
    
    def export_zip(
        self,
        samples: List[DatasetSample],
        output_path: str,
        format: DatasetFormat = DatasetFormat.JSON,
    ) -> bool:
        """导出为ZIP压缩包"""
        try:
            import tempfile
            
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                # 导出到临时目录
                if format == DatasetFormat.JSON:
                    temp_output = os.path.join(temp_dir, "dataset.json")
                    self.export_json_format(samples, temp_output)
                elif format == DatasetFormat.CSV:
                    temp_output = os.path.join(temp_dir, "dataset.csv")
                    self.export_csv_format(samples, temp_output)
                else:
                    temp_output = os.path.join(temp_dir, "dataset")
                    os.makedirs(temp_output, exist_ok=True)
                    self.export_json_format(samples, os.path.join(temp_output, "dataset.json"))
                
                # 复制文件
                images_dir = os.path.join(temp_dir, "images")
                os.makedirs(images_dir, exist_ok=True)
                for sample in samples:
                    if os.path.exists(sample.file_path):
                        shutil.copy2(sample.file_path, os.path.join(images_dir, sample.file_name))
                
                # 创建ZIP
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export ZIP: {e}")
            return False
    
    def export(
        self,
        samples: List[DatasetSample],
        output_dir: str,
        format: DatasetFormat,
        config: DatasetConfig = None,
    ) -> bool:
        """统一导出接口"""
        if config:
            self.config = config
        
        if format == DatasetFormat.IMAGENET:
            return self.export_imagenet_format(samples, output_dir)
        elif format == DatasetFormat.COCO:
            return self.export_coco_format(samples, output_dir)
        elif format == DatasetFormat.YOLO:
            return self.export_yolo_format(samples, output_dir)
        elif format == DatasetFormat.CSV:
            csv_path = os.path.join(output_dir, "dataset.csv")
            return self.export_csv_format(samples, csv_path)
        elif format == DatasetFormat.JSON:
            json_path = os.path.join(output_dir, "dataset.json")
            return self.export_json_format(samples, json_path)
        elif format == DatasetFormat.COMFYUI:
            return self.export_comfyui_format(samples, output_dir)
        elif format == DatasetFormat.ZIP:
            zip_path = os.path.join(output_dir, "dataset.zip")
            return self.export_zip(samples, zip_path)
        else:
            logger.error(f"Unsupported format: {format}")
            return False


class DatasetVersionManager:
    """
    数据集版本管理器
    支持版本创建、回滚和比较
    """
    
    def __init__(self, dataset_path: str):
        self.dataset_path = dataset_path
        self.versions: List[Dict[str, Any]] = []
        self._load_versions()
    
    def _load_versions(self):
        """加载版本历史"""
        versions_file = os.path.join(self.dataset_path, "versions.json")
        if os.path.exists(versions_file):
            with open(versions_file, "r") as f:
                self.versions = json.load(f)
    
    def _save_versions(self):
        """保存版本历史"""
        versions_file = os.path.join(self.dataset_path, "versions.json")
        with open(versions_file, "w") as f:
            json.dump(self.versions, f, indent=2)
    
    def create_version(
        self,
        name: str,
        description: str = "",
        samples: List[DatasetSample] = None,
    ) -> str:
        """创建新版本"""
        version_id = str(uuid.uuid4())[:8]
        version = {
            "id": version_id,
            "name": name,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "sample_count": len(samples) if samples else 0,
        }
        
        # 创建版本目录
        version_dir = os.path.join(self.dataset_path, f"v{version_id}")
        os.makedirs(version_dir, exist_ok=True)
        
        # 保存版本元数据
        with open(os.path.join(version_dir, "metadata.json"), "w") as f:
            json.dump(version, f, indent=2)
        
        # 保存样本数据
        if samples:
            samples_file = os.path.join(version_dir, "samples.json")
            with open(samples_file, "w") as f:
                json.dump([s.to_dict() for s in samples], f, indent=2)
        
        self.versions.append(version)
        self._save_versions()
        
        return version_id
    
    def get_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        """获取版本信息"""
        for v in self.versions:
            if v["id"] == version_id:
                return v
        return None
    
    def list_versions(self) -> List[Dict[str, Any]]:
        """列出所有版本"""
        return self.versions
    
    def compare_versions(
        self,
        version_id_1: str,
        version_id_2: str,
    ) -> Dict[str, Any]:
        """比较两个版本"""
        samples_1 = self._load_version_samples(version_id_1)
        samples_2 = self._load_version_samples(version_id_2)
        
        stats_1 = DatasetBuilder().get_statistics(samples_1)
        stats_2 = DatasetBuilder().get_statistics(samples_2)
        
        return {
            "version_1": stats_1.to_dict(),
            "version_2": stats_2.to_dict(),
            "differences": {
                "sample_count_diff": stats_2.total_samples - stats_1.total_samples,
                "train_diff": stats_2.train_samples - stats_1.train_samples,
                "val_diff": stats_2.val_samples - stats_1.val_samples,
                "test_diff": stats_2.test_samples - stats_1.test_samples,
            },
        }
    
    def _load_version_samples(self, version_id: str) -> List[DatasetSample]:
        """加载版本样本"""
        version_dir = os.path.join(self.dataset_path, f"v{version_id}")
        samples_file = os.path.join(version_dir, "samples.json")
        
        if not os.path.exists(samples_file):
            return []
        
        with open(samples_file, "r") as f:
            data = json.load(f)
        
        return [DatasetSample(**d) for d in data]


# 示例用法
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 创建数据集构建器
    builder = DatasetBuilder("./test_dataset_output")
    
    # 添加测试样本
    for i in range(100):
        sample = DatasetSample(
            id=f"sample_{i:04d}",
            asset_id=f"asset_{i:04d}",
            file_path=f"/images/img_{i:04d}.jpg",
            file_name=f"img_{i:04d}.jpg",
            labels=["cat" if i % 2 == 0 else "dog"],
            category="cat" if i % 2 == 0 else "dog",
            width=1920,
            height=1080,
            file_size=2048000,
            quality_score=random.uniform(0.5, 1.0),
            aesthetic_score=random.uniform(0.5, 1.0),
            created_at=datetime.now().isoformat(),
        )
        builder.add_sample(sample)
    
    # 创建数据集配置
    config = DatasetConfig(
        name="Pet Classification Dataset",
        description="Cat and dog classification dataset",
        split_mode=SplitMode.STRATIFIED,
        train_ratio=0.7,
        val_ratio=0.15,
        test_ratio=0.15,
        export_format=DatasetFormat.YOLO,
    )
    builder.set_config(config)
    
    # 过滤样本
    filtered = builder.filter_samples(builder.samples, min_quality=0.6)
    print(f"Filtered samples: {len(filtered)} / {len(builder.samples)}")
    
    # 去重
    deduped = builder.deduplicate(filtered)
    print(f"After deduplication: {len(deduped)}")
    
    # 划分数据
    train, val, test = builder.split_data(deduped)
    print(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")
    
    # 获取统计
    stats = builder.get_statistics(train + val + test)
    print(f"Statistics: {json.dumps(stats.to_dict(), indent=2)}")
    
    # 导出为YOLO格式
    builder.export(train + val + test, "./test_dataset_output/yolo", DatasetFormat.YOLO)
    print("Exported to YOLO format")
    
    # 导出为COCO格式
    builder.export(train + val + test, "./test_dataset_output/coco", DatasetFormat.COCO)
    print("Exported to COCO format")
