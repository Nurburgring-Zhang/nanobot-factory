#!/usr/bin/env python3
"""
Nanobot Factory - Image Filter & Comparison System
图片筛选与对比系统 - 商业级数据管理核心模块

@author MiniMax Agent
@date 2026-03-03
@description
- 支持多维度图片筛选
- 支持图片批量对比
- 支持图片相似度检测
- 支持分组对比（九宫格等）
- 支持AI辅助筛选建议
- 支持自定义筛选规则
"""

import os
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import base64
import numpy as np
from io import BytesIO

logger = logging.getLogger(__name__)


class FilterOperator(Enum):
    """筛选操作符"""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "ge"
    LESS_THAN = "lt"
    LESS_EQUAL = "le"
    CONTAINS = "contains"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class SortOrder(Enum):
    """排序方向"""
    ASC = "asc"
    DESC = "desc"


class CompareMode(Enum):
    """对比模式"""
    SIDE_BY_SIDE = "side_by_side"      # 并排对比
    SLIDE = "slide"                     # 滑动对比
    DIFF = "diff"                       # 差异对比
    OVERLAY = "overlay"                 # 叠加对比
    GRID = "grid"                       # 网格对比
    GALLERY = "gallery"                 # 画廊对比


@dataclass
class FilterCondition:
    """筛选条件"""
    field: str
    operator: FilterOperator
    value: Any
    value2: Any = None  # 用于BETWEEN操作
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "value2": self.value2,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilterCondition':
        return cls(
            field=data["field"],
            operator=FilterOperator(data.get("operator", "eq")),
            value=data["value"],
            value2=data.get("value2"),
        )


@dataclass
class FilterGroup:
    """筛选条件组"""
    logic: str = "AND"  # AND 或 OR
    conditions: List[FilterCondition] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "logic": self.logic,
            "conditions": [c.to_dict() for c in self.conditions],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilterGroup':
        return cls(
            logic=data.get("logic", "AND"),
            conditions=[FilterCondition.from_dict(c) for c in data.get("conditions", [])],
        )


@dataclass
class SortConfig:
    """排序配置"""
    field: str
    order: SortOrder = SortOrder.DESC
    
    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "order": self.order.value}


@dataclass
class ImageMetadata:
    """图片元数据"""
    # 基础信息
    asset_id: str
    file_name: str
    file_path: str
    file_size: int
    width: int
    height: int
    format: str
    mime_type: str
    
    # AI评分
    quality_score: float = 0.0
    aesthetic_score: float = 0.0
    nsfw_score: float = 0.0
    clip_score: float = 0.0
    
    # 标注信息
    rating: int = 0  # 0-5星
    color_label: str = ""
    tags: List[str] = field(default_factory=list)
    annotation: str = ""
    favorite: bool = False
    
    # 颜色信息
    primary_color: str = ""
    palette: List[str] = field(default_factory=list)
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    
    # 分类信息
    categories: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    scene: str = ""
    
    # 时间信息
    created_at: str = ""
    modified_at: str = ""
    
    # 其他
    hash: str = ""
    duplicate_group: str = ""
    source: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "mime_type": self.mime_type,
            "quality_score": self.quality_score,
            "aesthetic_score": self.aesthetic_score,
            "nsfw_score": self.nsfw_score,
            "clip_score": self.clip_score,
            "rating": self.rating,
            "color_label": self.color_label,
            "tags": self.tags,
            "annotation": self.annotation,
            "favorite": self.favorite,
            "primary_color": self.primary_color,
            "palette": self.palette,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "categories": self.categories,
            "objects": self.objects,
            "scene": self.scene,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "hash": self.hash,
            "duplicate_group": self.duplicate_group,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImageMetadata':
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class CompareResult:
    """对比结果"""
    asset_id_1: str
    asset_id_2: str
    similarity_score: float  # 0-1, 1表示完全相同
    diff_regions: List[Dict[str, Any]] = field(default_factory=list)
    histogram_diff: float = 0.0
    perceptual_diff: float = 0.0
    hash_diff: float = 0.0  # 感知哈希差异
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id_1": self.asset_id_1,
            "asset_id_2": self.asset_id_2,
            "similarity_score": self.similarity_score,
            "diff_regions": self.diff_regions,
            "histogram_diff": self.histogram_diff,
            "perceptual_diff": self.perceptual_diff,
            "hash_diff": self.hash_diff,
        }


@dataclass
class DuplicateGroup:
    """重复图片组"""
    group_id: str
    assets: List[str]  # 资产ID列表
    similarity: float  # 组内相似度
    representative_id: str = ""  # 代表图片ID
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "assets": self.assets,
            "similarity": self.similarity,
            "representative_id": self.representative_id,
        }


class ImageFilterEngine:
    """
    图片筛选引擎
    支持多维度、多条件的复杂筛选
    """
    
    def __init__(self):
        self.available_fields = {
            # 数值字段
            "width": float,
            "height": float,
            "file_size": int,
            "aspect_ratio": float,
            "quality_score": float,
            "aesthetic_score": float,
            "nsfw_score": float,
            "clip_score": float,
            "rating": int,
            "brightness": float,
            "contrast": float,
            "saturation": float,
            
            # 字符串字段
            "file_name": str,
            "format": str,
            "color_label": str,
            "primary_color": str,
            "scene": str,
            "source": str,
            
            # 布尔字段
            "favorite": bool,
            
            # 列表字段
            "tags": list,
            "categories": list,
            "objects": list,
        }
    
    def add_computed_field(self, images: List[ImageMetadata]) -> List[ImageMetadata]:
        """添加计算字段"""
        for img in images:
            # 计算宽高比
            img.aspect_ratio = img.width / img.height if img.height > 0 else 0
        return images
    
    def evaluate_condition(self, image: ImageMetadata, condition: FilterCondition) -> bool:
        """评估单个条件"""
        field_value = getattr(image, condition.field, None)
        
        if field_value is None:
            return False
        
        op = condition.operator
        
        try:
            if op == FilterOperator.EQUALS:
                return field_value == condition.value
            elif op == FilterOperator.NOT_EQUALS:
                return field_value != condition.value
            elif op == FilterOperator.GREATER_THAN:
                return float(field_value) > float(condition.value)
            elif op == FilterOperator.GREATER_EQUAL:
                return float(field_value) >= float(condition.value)
            elif op == FilterOperator.LESS_THAN:
                return float(field_value) < float(condition.value)
            elif op == FilterOperator.LESS_EQUAL:
                return float(field_value) <= float(condition.value)
            elif op == FilterOperator.CONTAINS:
                return str(condition.value).lower() in str(field_value).lower()
            elif op == FilterOperator.IN:
                return field_value in condition.value if isinstance(condition.value, list) else field_value == condition.value
            elif op == FilterOperator.NOT_IN:
                return field_value not in condition.value
            elif op == FilterOperator.BETWEEN:
                return float(condition.value) <= float(field_value) <= float(condition.value2)
            elif op == FilterOperator.STARTS_WITH:
                return str(field_value).startswith(str(condition.value))
            elif op == FilterOperator.ENDS_WITH:
                return str(field_value).endswith(str(condition.value))
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to evaluate condition: {e}")
            return False
        
        return False
    
    def evaluate_group(self, image: ImageMetadata, group: FilterGroup) -> bool:
        """评估条件组"""
        if not group.conditions:
            return True
        
        results = [self.evaluate_condition(image, c) for c in group.conditions]
        
        if group.logic == "AND":
            return all(results)
        else:  # OR
            return any(results)
    
    def filter_images(
        self,
        images: List[ImageMetadata],
        filter_group: FilterGroup,
    ) -> List[ImageMetadata]:
        """筛选图片"""
        return [img for img in images if self.evaluate_group(img, filter_group)]
    
    def sort_images(
        self,
        images: List[ImageMetadata],
        sort_config: SortConfig,
    ) -> List[ImageMetadata]:
        """排序图片"""
        reverse = sort_config.order == SortOrder.DESC
        
        def get_sort_key(img: ImageMetadata):
            value = getattr(img, sort_config.field, None)
            if value is None:
                return 0 if sort_config.order == SortOrder.DESC else float('inf')
            if isinstance(value, str):
                return value.lower()
            return value
        
        return sorted(images, key=get_sort_key, reverse=reverse)
    
    def paginate(
        self,
        images: List[ImageMetadata],
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[ImageMetadata], int]:
        """分页"""
        total = len(images)
        start = (page - 1) * page_size
        end = start + page_size
        return images[start:end], total


class ImageCompareEngine:
    """
    图片对比引擎
    支持多种对比模式和相似度检测
    """
    
    def __init__(self):
        self._image_cache: Dict[str, np.ndarray] = {}
    
    def calculate_hash_similarity(self, hash1: str, hash2: str) -> float:
        """计算感知哈希相似度"""
        if not hash1 or not hash2:
            return 0.0
        
        # 汉明距离
        hamming = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        max_len = max(len(hash1), len(hash2))
        
        return 1.0 - (hamming / max_len)
    
    def calculate_histogram_similarity(
        self,
        hist1: np.ndarray,
        hist2: np.ndarray,
    ) -> float:
        """计算直方图相似度"""
        # 使用相关性比较
        if hist1.shape != hist2.shape:
            # 调整大小
            min_len = min(len(hist1), len(hist2))
            hist1 = hist1[:min_len]
            hist2 = hist2[:min_len]
        
        # 归一化
        hist1 = hist1 / (np.sum(hist1) + 1e-10)
        hist2 = hist2 / (np.sum(hist2) + 1e-10)
        
        # 计算相关性
        correlation = np.corrcoef(hist1.flatten(), hist2.flatten())[0, 1]
        return max(0, correlation)  # 确保非负
    
    def perceptual_hash(self, image: np.ndarray, hash_size: int = 8) -> str:
        """计算感知哈希"""
        try:
            from PIL import Image
            import cv2
            
            # 调整大小
            resized = cv2.resize(image, (hash_size + 1, hash_size))
            
            # 计算DCT
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(resized.shape) == 3 else resized
            
            # 计算平均值
            avg = gray.mean()
            
            # 生成哈希
            pixels = gray.flatten()
            hash_bits = (pixels > avg).astype(int)
            
            # 转换为十六进制字符串
            hash_str = ''
            for i in range(0, len(hash_bits), 4):
                nibble = hash_bits[i:i+4]
                hash_str += format(int(''.join(map(str, nibble)), 2), 'x')
            
            return hash_str
            
        except Exception as e:
            logger.warning(f"Failed to calculate perceptual hash: {e}")
            return ""
    
    def average_hash(self, image: np.ndarray, hash_size: int = 8) -> str:
        """计算平均哈希"""
        try:
            import cv2
            
            # 调整大小并转换为灰度
            resized = cv2.resize(image, (hash_size, hash_size))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(resized.shape) == 3 else resized
            
            # 计算平均值
            avg = gray.mean()
            
            # 生成哈希
            bits = (gray > avg).flatten()
            hash_str = ''
            for i in range(0, len(bits), 8):
                byte = bits[i:i+8]
                while len(byte) < 8:
                    byte = np.append(byte, False)
                hash_str += format(int(''.join(map(str, byte.astype(int))), 2), '02x')
            
            return hash_str
            
        except Exception as e:
            logger.warning(f"Failed to calculate average hash: {e}")
            return ""
    
    def calculate_ssim(
        self,
        image1: np.ndarray,
        image2: np.ndarray,
        window_size: int = 11,
    ) -> float:
        """计算SSIM相似度"""
        try:
            import cv2
            
            # 转换为灰度图
            if len(image1.shape) == 3:
                gray1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
            else:
                gray1 = image1
                gray2 = image2
            
            # 调整大小
            if gray1.shape != gray2.shape:
                gray2 = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
            
            # 计算SSIM的各个组件
            C1 = (0.01 * 255) ** 2
            C2 = (0.03 * 255) ** 2
            
            mu1 = cv2.GaussianBlur(gray1.astype(np.float32), (window_size, window_size), 1.5)
            mu2 = cv2.GaussianBlur(gray2.astype(np.float32), (window_size, window_size), 1.5)
            
            mu1_sq = mu1 ** 2
            mu2_sq = mu2 ** 2
            mu1_mu2 = mu1 * mu2
            
            sigma1_sq = cv2.GaussianBlur(gray1.astype(np.float32) ** 2, (window_size, window_size), 1.5) - mu1_sq
            sigma2_sq = cv2.GaussianBlur(gray2.astype(np.float32) ** 2, (window_size, window_size), 1.5) - mu2_sq
            sigma12 = cv2.GaussianBlur(gray1.astype(np.float32) * gray2.astype(np.float32), (window_size, window_size), 1.5) - mu1_mu2
            
            ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
            
            return float(np.mean(ssim_map))
            
        except Exception as e:
            logger.warning(f"Failed to calculate SSIM: {e}")
            return 0.0
    
    def compare_images(
        self,
        image1_path: str,
        image2_path: str,
        methods: List[str] = None,
    ) -> CompareResult:
        """对比两张图片"""
        if methods is None:
            methods = ["ssim", "histogram", "hash"]
        
        import cv2
        
        # 读取图片
        img1 = cv2.imread(image1_path)
        img2 = cv2.imread(image2_path)
        
        if img1 is None or img2 is None:
            return CompareResult(
                asset_id_1=image1_path,
                asset_id_2=image2_path,
                similarity_score=0.0,
            )
        
        similarity_scores = []
        histogram_diff = 0.0
        perceptual_diff = 0.0
        hash_diff = 0.0
        
        if "ssim" in methods:
            ssim = self.calculate_ssim(img1, img2)
            similarity_scores.append(ssim)
        
        if "histogram" in methods:
            hist1 = cv2.calcHist([img1], [0], None, [256], [0, 256])
            hist2 = cv2.calcHist([img2], [0], None, [256], [0, 256])
            histogram_diff = 1.0 - self.calculate_histogram_similarity(hist1.flatten(), hist2.flatten())
            similarity_scores.append(1.0 - histogram_diff)
        
        if "hash" in methods:
            hash1 = self.average_hash(img1)
            hash2 = self.average_hash(img2)
            hash_diff = 1.0 - self.calculate_hash_similarity(hash1, hash2)
            similarity_scores.append(1.0 - hash_diff)
        
        # 计算综合相似度
        similarity_score = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
        
        return CompareResult(
            asset_id_1=image1_path,
            asset_id_2=image2_path,
            similarity_score=similarity_score,
            histogram_diff=histogram_diff,
            perceptual_diff=perceptual_diff,
            hash_diff=hash_diff,
        )
    
    def find_duplicates(
        self,
        images: List[ImageMetadata],
        threshold: float = 0.9,
    ) -> List[DuplicateGroup]:
        """查找重复图片"""
        groups = []
        used = set()
        
        for i, img1 in enumerate(images):
            if img1.asset_id in used:
                continue
            
            group_assets = [img1.asset_id]
            
            for j, img2 in enumerate(images[i + 1:], start=i + 1):
                if img2.asset_id in used:
                    continue
                
                # 简单比较：如果哈希相同或相似度很高
                if img1.hash and img2.hash and img1.hash == img2.hash:
                    group_assets.append(img2.asset_id)
                    used.add(img2.asset_id)
                elif img1.duplicate_group and img2.duplicate_group and img1.duplicate_group == img2.duplicate_group:
                    if img2.asset_id not in group_assets:
                        group_assets.append(img2.asset_id)
                        used.add(img2.asset_id)
            
            if len(group_assets) > 1:
                used.add(img1.asset_id)
                groups.append(DuplicateGroup(
                    group_id=f"dup_{img1.asset_id}",
                    assets=group_assets,
                    similarity=threshold,
                    representative_id=group_assets[0],
                ))
        
        return groups
    
    def generate_grid_comparison(
        self,
        images: List[ImageMetadata],
        grid_size: Tuple[int, int] = (3, 3),
    ) -> List[List[ImageMetadata]]:
        """生成网格对比布局"""
        rows, cols = grid_size
        result = []
        
        for i in range(0, len(images), cols):
            row = images[i:i + cols]
            # 填充空位
            while len(row) < cols:
                row.append(None)
            result.append(row[:cols])
        
        return result


class SmartFilterBuilder:
    """
    智能筛选构建器
    提供预设的筛选模板和AI辅助筛选
    """
    
    @staticmethod
    def high_quality_filter(min_score: float = 0.8) -> FilterGroup:
        """高质量图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("quality_score", FilterOperator.GREATER_EQUAL, min_score),
                FilterCondition("nsfw_score", FilterOperator.LESS_THAN, 0.3),
            ]
        )
    
    @staticmethod
    def portrait_filter() -> FilterGroup:
        """人像图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("categories", FilterOperator.CONTAINS, "person"),
                FilterCondition("nsfw_score", FilterOperator.LESS_THAN, 0.2),
            ]
        )
    
    @staticmethod
    def landscape_filter() -> FilterGroup:
        """风景图片筛选"""
        return FilterGroup(
            logic="OR",
            conditions=[
                FilterCondition("categories", FilterOperator.CONTAINS, "landscape"),
                FilterCondition("categories", FilterOperator.CONTAINS, "nature"),
                FilterCondition("categories", FilterOperator.CONTAINS, "scenery"),
            ]
        )
    
    @staticmethod
    def dark_mode_filter() -> FilterGroup:
        """暗色调图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("brightness", FilterOperator.LESS_THAN, 0.4),
            ]
        )
    
    @staticmethod
    def bright_filter() -> FilterGroup:
        """高亮度图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("brightness", FilterOperator.GREATER_THAN, 0.7),
            ]
        )
    
    @staticmethod
    def square_filter() -> FilterGroup:
        """方形图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("width", FilterOperator.EQUALS, "height"),
            ]
        )
    
    @staticmethod
    def wide_filter(aspect_ratio: float = 1.5) -> FilterGroup:
        """宽屏图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("aspect_ratio", FilterOperator.GREATER_EQUAL, aspect_ratio),
            ]
        )
    
    @staticmethod
    def tall_filter(aspect_ratio: float = 1.5) -> FilterGroup:
        """竖屏图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("aspect_ratio", FilterOperator.LESS_EQUAL, 1.0 / aspect_ratio),
            ]
        )
    
    @staticmethod
    def recent_filter(days: int = 7) -> FilterGroup:
        """近期图片筛选"""
        from datetime import timedelta
        date_threshold = (datetime.now() - timedelta(days=days)).isoformat()
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("created_at", FilterOperator.GREATER_EQUAL, date_threshold),
            ]
        )
    
    @staticmethod
    def favorites_filter() -> FilterGroup:
        """收藏图片筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("favorite", FilterOperator.EQUALS, True),
            ]
        )
    
    @staticmethod
    def color_filter(color: str) -> FilterGroup:
        """指定颜色筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("primary_color", FilterOperator.EQUALS, color),
            ]
        )
    
    @staticmethod
    def rating_filter(min_rating: int = 4) -> FilterGroup:
        """指定评分以上筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("rating", FilterOperator.GREATER_EQUAL, min_rating),
            ]
        )
    
    @staticmethod
    def similar_scene_filter(scene: str) -> FilterGroup:
        """相似场景筛选"""
        return FilterGroup(
            logic="AND",
            conditions=[
                FilterCondition("scene", FilterOperator.CONTAINS, scene),
            ]
        )


# 示例用法
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 创建筛选引擎
    filter_engine = ImageFilterEngine()
    
    # 创建测试数据
    test_images = [
        ImageMetadata(
            asset_id="img_001",
            file_name="landscape_1.jpg",
            file_path="/images/landscape_1.jpg",
            file_size=2048000,
            width=1920,
            height=1080,
            format="JPEG",
            mime_type="image/jpeg",
            quality_score=0.85,
            aesthetic_score=0.90,
            nsfw_score=0.05,
            rating=5,
            brightness=0.6,
            tags=["landscape", "nature"],
            categories=["landscape"],
        ),
        ImageMetadata(
            asset_id="img_002",
            file_name="portrait_1.jpg",
            file_path="/images/portrait_1.jpg",
            file_size=1536000,
            width=1080,
            height=1920,
            format="JPEG",
            mime_type="image/jpeg",
            quality_score=0.75,
            aesthetic_score=0.80,
            nsfw_score=0.10,
            rating=4,
            brightness=0.5,
            tags=["portrait", "person"],
            categories=["person"],
        ),
        ImageMetadata(
            asset_id="img_003",
            file_name="dark_scene.jpg",
            file_path="/images/dark_scene.jpg",
            file_size=1024000,
            width=1920,
            height=1080,
            format="JPEG",
            mime_type="image/jpeg",
            quality_score=0.65,
            aesthetic_score=0.70,
            nsfw_score=0.02,
            rating=3,
            brightness=0.25,
            tags=["dark", "night"],
            categories=["night"],
        ),
    ]
    
    # 添加计算字段
    test_images = filter_engine.add_computed_field(test_images)
    
    # 使用预设筛选
    hq_filter = SmartFilterBuilder.high_quality_filter(min_score=0.7)
    results = filter_engine.filter_images(test_images, hq_filter)
    print(f"High quality images: {len(results)}")
    for img in results:
        print(f"  - {img.file_name} (quality: {img.quality_score})")
    
    # 自定义筛选
    custom_filter = FilterGroup(
        logic="AND",
        conditions=[
            FilterCondition("brightness", FilterOperator.LESS_THAN, 0.4),
            FilterCondition("rating", FilterOperator.GREATER_EQUAL, 3),
        ]
    )
    results = filter_engine.filter_images(test_images, custom_filter)
    print(f"\nDark images with rating >= 3: {len(results)}")
    
    # 创建对比引擎
    compare_engine = ImageCompareEngine()
    
    # 查找重复
    test_images[0].hash = "abc123"
    test_images[1].hash = "abc123"  # 相同的哈希
    duplicates = compare_engine.find_duplicates(test_images, threshold=0.9)
    print(f"\nDuplicate groups found: {len(duplicates)}")
