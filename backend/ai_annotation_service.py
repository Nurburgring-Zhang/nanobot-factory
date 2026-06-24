#!/usr/bin/env python3
"""
NanoBot Factory AI辅助标注服务
AI-Assisted Annotation Service

功能:
- AI预标注 (YOLO, SAM, Grounding DINO)
- 自动质量检测
- 智能推荐
- 批量标注处理

@author Matrix Agent
@date 2026-04-21
@version 2.0.0
"""

import os
import sys
import json
import logging
import hashlib
import asyncio
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from abc import ABC, abstractmethod
import base64
import io

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AIAnnotationService")


# ==================== 枚举类型 ====================

class AnnotationType(Enum):
    """标注类型"""
    BOUNDING_BOX = "bounding_box"
    POLYGON = "polygon"
    KEYPOINTS = "keypoints"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    INSTANCE_SEGMENTATION = "instance_segmentation"
    LINE = "line"
    ELLIPSE = "ellipse"
    CUBOID = "cuboid"
    TEXT = "text"
    CLASSIFICATION = "classification"


class AITaskType(Enum):
    """AI任务类型"""
    OBJECT_DETECTION = "object_detection"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    INSTANCE_SEGMENTATION = "instance_segmentation"
    IMAGE_CLASSIFICATION = "image_classification"
    IMAGE_QUALITY = "image_quality"
    NSFW_DETECTION = "nsfw_detection"
    OCR = "ocr"
    KEYPOINT_DETECTION = "keypoint_detection"


@dataclass
class PreAnnotationResult:
    """预标注结果"""
    annotation_id: str
    annotation_type: AnnotationType
    label: str
    confidence: float
    geometry: Dict[str, Any]  # 标注几何数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    model_name: str = "unknown"
    processing_time_ms: float = 0.0


@dataclass
class QualityCheckResult:
    """质量检查结果"""
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    overall_score: float = 1.0
    blur_score: float = 1.0
    brightness_score: float = 1.0
    nsfw_score: float = 0.0
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass
class AIVisionConfig:
    """AI视觉服务配置"""
    enabled: bool = True
    api_provider: str = "local"  # local, openai, aliyun, huggingface
    api_key: Optional[str] = None
    model_endpoint: str = ""
    device: str = "cpu"  # cpu, cuda
    confidence_threshold: float = 0.5


# ==================== 图像处理工具 ====================

class ImageProcessor:
    """图像处理工具类"""

    @staticmethod
    def load_image(image_source: Union[str, bytes, io.BytesIO]) -> Optional[Any]:
        """
        加载图像
        支持: 文件路径, URL, Base64, bytes
        """
        try:
            import numpy as np
            from PIL import Image
            import cv2

            if isinstance(image_source, str):
                # 文件路径或URL
                if image_source.startswith(('http://', 'https://')):
                    import requests
                    response = requests.get(image_source)
                    image_array = np.frombuffer(response.content, dtype=np.uint8)
                    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                else:
                    img = cv2.imread(image_source)
            elif isinstance(image_source, bytes):
                # 字节数据
                image_array = np.frombuffer(image_source, dtype=np.uint8)
                img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            elif isinstance(image_source, io.BytesIO):
                # BytesIO对象
                image_array = np.frombuffer(image_source.getvalue(), dtype=np.uint8)
                img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            else:
                return None

            return img
        except Exception as e:
            logger.error(f"Failed to load image: {e}")
            return None

    @staticmethod
    def calculate_blur_score(image: Any) -> float:
        """计算图像模糊度 (Laplacian方差)"""
        try:
            import cv2
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            variance = laplacian.var()
            # 归一化到0-1, 方差越大越清晰
            score = min(1.0, variance / 500)
            return score
        except Exception:
            return 0.5

    @staticmethod
    def calculate_brightness_score(image: Any) -> float:
        """计算图像亮度分数"""
        try:
            import cv2
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            brightness = hsv[:, :, 2].mean()
            # 理想亮度在100-150之间
            if 100 <= brightness <= 150:
                return 1.0
            elif brightness < 50 or brightness > 200:
                return 0.3
            else:
                return 0.7
        except Exception:
            return 0.5

    @staticmethod
    def detect_edges(image: Any) -> List:
        """边缘检测"""
        try:
            import cv2
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            return contours
        except Exception:
            return []

    @staticmethod
    def compute_image_hash(image: Any, hash_size: int = 8) -> str:
        """计算图像感知哈希"""
        try:
            import cv2
            import numpy as np

            # 缩放图像
            resized = cv2.resize(image, (hash_size + 1, hash_size))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

            # 计算差异
            diff = gray[:, 1:] > gray[:, :-1]

            # 生成哈希
            hash_value = sum([2 ** i for i, v in enumerate(diff.flatten()) if v])
            return format(hash_value, '0{}x'.format(hash_size * hash_size // 4))
        except Exception:
            return ""

    @staticmethod
    def calculate_ssim(image1: Any, image2: Any) -> float:
        """计算结构相似度"""
        try:
            import cv2
            from skimage.metrics import structural_similarity

            gray1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)

            score = structural_similarity(gray1, gray2)
            return score
        except Exception:
            return 0.0


# ==================== AI模型接口 ====================

class BaseAIModel(ABC):
    """AI模型基类"""

    @abstractmethod
    def predict(self, image: Any, **kwargs) -> List[PreAnnotationResult]:
        """执行预测"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查模型是否可用"""
        pass


class YOLOModel(BaseAIModel):
    """
    YOLO目标检测模型
    支持: YOLOv5, YOLOv8, YOLOv11
    """

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu"):
        self.model_path = model_path
        self.device = device
        self.model = None
        self._load_model()

    def _load_model(self):
        """加载模型"""
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self.model.to(self.device)
            logger.info(f"YOLO model loaded: {self.model_path}")
        except ImportError:
            logger.warning("ultralytics not installed, using mock model")
            self.model = None
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.model = None

    def predict(self, image: Any, confidence: float = 0.5) -> List[PreAnnotationResult]:
        """执行目标检测"""
        if self.model is None:
            return self._mock_predict(image, confidence)

        try:
            import cv2
            results = self.model(image, verbose=False, conf=confidence)

            annotations = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for box in boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    label = result.names[cls_id]

                    annotation = PreAnnotationResult(
                        annotation_id=f"anno_{uuid.uuid4().hex[:8]}",
                        annotation_type=AnnotationType.BOUNDING_BOX,
                        label=label,
                        confidence=conf,
                        geometry={
                            "x1": float(xyxy[0]),
                            "y1": float(xyxy[1]),
                            "x2": float(xyxy[2]),
                            "y2": float(xyxy[3]),
                            "width": float(xyxy[2] - xyxy[0]),
                            "height": float(xyxy[3] - xyxy[1]),
                        },
                        model_name="YOLO",
                    )
                    annotations.append(annotation)

            return annotations
        except Exception as e:
            logger.error(f"YOLO prediction failed: {e}")
            return []

    def is_available(self) -> bool:
        return self.model is not None


class SAMModel(BaseAIModel):
    """
    Segment Anything Model (SAM)
    用于交互式分割
    """

    def __init__(self, model_type: str = "sam2.1_b.pt", device: str = "cpu"):
        self.model_type = model_type
        self.device = device
        self.model = None
        self.predictor = None
        self._load_model()

    def _load_model(self):
        """加载SAM模型"""
        try:
            from segment_anything import sam_model_registry, SamPredictor
            self.model = sam_model_registry[self.model_type](checkpoint=self.model_type)
            self.model.to(self.device)
            self.predictor = SamPredictor(self.model)
            logger.info(f"SAM model loaded: {self.model_type}")
        except ImportError:
            logger.warning("segment_anything not installed, using mock model")
        except Exception as e:
            logger.error(f"Failed to load SAM model: {e}")

    def predict(self, image: Any, points: List[Tuple[int, int]] = None,
                labels: List[int] = None) -> List[PreAnnotationResult]:
        """执行分割预测"""
        if self.predictor is None or image is None:
            return self._mock_predict(image)

        try:
            import cv2
            # 设置图像
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            self.predictor.set_image(image_rgb)

            if points and labels:
                # 点提示分割
                input_points = np.array(points)
                input_labels = np.array(labels)

                masks, scores, _ = self.predictor.predict(
                    point_coords=input_points,
                    point_labels=input_labels,
                    multimask_output=False
                )

                annotations = []
                for i, mask in enumerate(masks):
                    # 找到mask的边界
                    contours, _ = cv2.findContours(
                        (mask * 255).astype(np.uint8),
                        cv2.RETR_EXTERNAL,
                        cv2.CHAIN_APPROX_SIMPLE
                    )

                    if contours:
                        largest_contour = max(contours, key=cv2.contourArea)
                        polygon = largest_contour.squeeze().tolist()

                        annotation = PreAnnotationResult(
                            annotation_id=f"anno_{uuid.uuid4().hex[:8]}",
                            annotation_type=AnnotationType.POLYGON,
                            label="segment",
                            confidence=float(scores[i]),
                            geometry={"points": polygon},
                            model_name="SAM",
                        )
                        annotations.append(annotation)

                return annotations

            return []
        except Exception as e:
            logger.error(f"SAM prediction failed: {e}")
            return []

    def is_available(self) -> bool:
        return self.predictor is not None


class ImageClassificationModel(BaseAIModel):
    """图像分类模型"""

    def __init__(self, model_name: str = "resnet50"):
        self.model_name = model_name
        self.model = None
        self.labels = None
        self._load_model()

    def _load_model(self):
        """加载分类模型"""
        try:
            import torch
            import torchvision.models as models
            import torchvision.transforms as transforms

            self.model = models.resnet50(pretrained=True)
            self.model.eval()

            # 加载ImageNet标签
            self.labels = self._load_imagenet_labels()

            logger.info(f"Classification model loaded: {self.model_name}")
        except ImportError:
            logger.warning("torch not installed, using mock model")
        except Exception as e:
            logger.error(f"Failed to load classification model: {e}")

    def _load_imagenet_labels(self) -> List[str]:
        """加载ImageNet标签"""
        return [
            "tench", "goldfish", "great_white_shark", "tiger_shark", "hammerhead",
            # ... 简化版本,实际应用中应加载完整的1000类标签
        ]

    def predict(self, image: Any, top_k: int = 5) -> List[PreAnnotationResult]:
        """执行图像分类"""
        if self.model is None:
            return self._mock_predict(image)

        try:
            import torch
            import torchvision.transforms as transforms
            from PIL import Image
            import cv2

            # 预处理
            transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            # 转换图像
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(image_rgb)
            input_tensor = transform(pil_image).unsqueeze(0)

            # 推理
            with torch.no_grad():
                outputs = self.model(input_tensor)
                probs = torch.nn.functional.softmax(outputs[0], dim=0)

            # 获取Top-K结果
            top_probs, top_indices = torch.topk(probs, min(top_k, len(probs)))

            annotations = []
            for prob, idx in zip(top_probs, top_indices):
                label = self.labels[idx.item()] if idx.item() < len(self.labels) else f"class_{idx.item()}"

                annotation = PreAnnotationResult(
                    annotation_id=f"anno_{uuid.uuid4().hex[:8]}",
                    annotation_type=AnnotationType.CLASSIFICATION,
                    label=label,
                    confidence=prob.item(),
                    geometry={},  # 分类不需要几何数据
                    model_name="ResNet50",
                )
                annotations.append(annotation)

            return annotations
        except Exception as e:
            logger.error(f"Classification prediction failed: {e}")
            return []

    def is_available(self) -> bool:
        return self.model is not None


class NSFWDetector:
    """NSFW内容检测"""

    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        """加载NSFW检测模型"""
        try:
            # 使用OpenNSFW或类似模型
            logger.info("NSFW detector initialized")
        except Exception as e:
            logger.warning(f"Failed to load NSFW model: {e}")

    def predict(self, image: Any) -> float:
        """
        检测NSFW分数
        返回0-1之间的分数,越高表示越可能包含不当内容
        """
        if image is None:
            return 0.0

        try:
            # 简化实现 - 实际应使用专门的NSFW模型
            # 这里可以集成 OpenNSFW, nsfw_detector 等库
            blur_score = ImageProcessor.calculate_blur_score(image)

            # 简化的启发式检测
            # 实际应用中应使用深度学习模型
            if blur_score < 0.3:
                return 0.8  # 模糊图像可能是试图规避检测

            return 0.0
        except Exception:
            return 0.0

    def is_available(self) -> bool:
        return True  # 简化版本始终可用


class AestheticsScorer:
    """美学评分"""

    def __init__(self):
        self.model = None

    def score(self, image: Any) -> Dict[str, float]:
        """
        计算美学评分
        返回多维度分数
        """
        if image is None:
            return {"overall": 0.5, "composition": 0.5, "lighting": 0.5, "color": 0.5}

        try:
            blur_score = ImageProcessor.calculate_blur_score(image)
            brightness_score = ImageProcessor.calculate_brightness_score(image)

            # 简化评分 - 实际应使用美学评估模型
            scores = {
                "sharpness": blur_score,
                "brightness": brightness_score,
                "composition": 0.7,  # 需要更复杂的分析
                "lighting": brightness_score,
                "color": 0.7,  # 需要颜色分析
            }

            # 计算综合分数
            scores["overall"] = sum(scores.values()) / len(scores)

            return scores
        except Exception as e:
            logger.error(f"Aesthetics scoring failed: {e}")
            return {"overall": 0.5, "composition": 0.5, "lighting": 0.5, "color": 0.5}


# ==================== AI标注服务主类 ====================

class AIAnnotationService:
    """
    AI辅助标注服务
    提供预标注、质量检测、智能推荐等功能
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.config = AIVisionConfig()
        self.models: Dict[str, BaseAIModel] = {}
        self.nsfw_detector = NSFWDetector()
        self.aesthetics_scorer = AestheticsScorer()
        self._init_models()

        logger.info("AIAnnotationService initialized")

    def _init_models(self):
        """初始化AI模型"""
        # 延迟加载模型,避免启动时占用太多资源
        self.models = {
            "yolo": None,
            "sam": None,
            "classification": None,
        }

    def load_model(self, model_type: str, **kwargs) -> bool:
        """动态加载模型"""
        try:
            if model_type == "yolo":
                model_path = kwargs.get("model_path", "yolov8n.pt")
                device = kwargs.get("device", "cpu")
                self.models["yolo"] = YOLOModel(model_path, device)
                return self.models["yolo"].is_available()

            elif model_type == "sam":
                model_type_sam = kwargs.get("model_type", "sam2.1_b.pt")
                device = kwargs.get("device", "cpu")
                self.models["sam"] = SAMModel(model_type_sam, device)
                return self.models["sam"].is_available()

            elif model_type == "classification":
                model_name = kwargs.get("model_name", "resnet50")
                self.models["classification"] = ImageClassificationModel(model_name)
                return self.models["classification"].is_available()

            return False
        except Exception as e:
            logger.error(f"Failed to load model {model_type}: {e}")
            return False

    def get_model_status(self) -> Dict[str, bool]:
        """获取各模型状态"""
        status = {}
        for name in ["yolo", "sam", "classification"]:
            model = self.models.get(name)
            status[name] = model.is_available() if model else False
        return status

    # ==================== 预标注功能 ====================

    def pre_annotate(
        self,
        image: Any,
        task_type: AITaskType,
        **kwargs
    ) -> List[PreAnnotationResult]:
        """
        执行AI预标注

        Args:
            image: 图像数据
            task_type: AI任务类型
            **kwargs: 任务特定参数

        Returns:
            预标注结果列表
        """
        confidence_threshold = kwargs.get("confidence", self.config.confidence_threshold)

        if task_type == AITaskType.OBJECT_DETECTION:
            return self._detect_objects(image, confidence_threshold)
        elif task_type == AITaskType.SEMANTIC_SEGMENTATION:
            return self._semantic_segment(image, confidence_threshold)
        elif task_type == AITaskType.INSTANCE_SEGMENTATION:
            return self._instance_segment(image, confidence_threshold)
        elif task_type == AITaskType.IMAGE_CLASSIFICATION:
            return self._classify_image(image, confidence_threshold)
        elif task_type == AITaskType.KEYPOINT_DETECTION:
            return self._detect_keypoints(image, confidence_threshold)
        else:
            logger.warning(f"Unsupported task type: {task_type}")
            return []

    def _detect_objects(self, image: Any, confidence: float) -> List[PreAnnotationResult]:
        """目标检测预标注"""
        # 延迟加载YOLO模型
        if self.models.get("yolo") is None:
            self.load_model("yolo")

        model = self.models.get("yolo")
        if model and model.is_available():
            return model.predict(image, confidence)

        # 返回模拟结果
        return self._mock_object_detection(image, confidence)

    def _semantic_segment(self, image: Any, confidence: float) -> List[PreAnnotationResult]:
        """语义分割预标注"""
        # 简化实现 - 实际应使用DeepLabV3, UNet等模型
        return self._mock_segmentation(image, confidence, "semantic")

    def _instance_segment(self, image: Any, confidence: float) -> List[PreAnnotationResult]:
        """实例分割预标注"""
        # 延迟加载SAM模型
        if self.models.get("sam") is None:
            self.load_model("sam")

        model = self.models.get("sam")
        if model and model.is_available():
            # 需要点提示,这里返回空列表
            # 实际使用中应由用户点击或使用Grounding DINO生成点提示
            return []

        return self._mock_segmentation(image, confidence, "instance")

    def _classify_image(self, image: Any, confidence: float) -> List[PreAnnotationResult]:
        """图像分类预标注"""
        # 延迟加载分类模型
        if self.models.get("classification") is None:
            self.load_model("classification")

        model = self.models.get("classification")
        if model and model.is_available():
            return model.predict(image)

        return self._mock_classification(image)

    def _detect_keypoints(self, image: Any, confidence: float) -> List[PreAnnotationResult]:
        """关键点检测预标注"""
        # 需要专门的关键点检测模型如HRNet, OpenPose
        return []

    # ==================== 质量检测 ====================

    def check_quality(self, image: Any) -> QualityCheckResult:
        """
        执行图像质量检测

        检测项目:
        - 模糊度
        - 亮度
        - NSFW内容
        - 分辨率
        """
        if image is None:
            return QualityCheckResult(
                is_valid=False,
                issues=["无法加载图像"],
                overall_score=0.0,
            )

        issues = []
        overall_score = 1.0

        # 模糊度检测
        blur_score = ImageProcessor.calculate_blur_score(image)
        if blur_score < 0.3:
            issues.append(f"图像过于模糊 (清晰度分数: {blur_score:.2f})")
            overall_score *= 0.5
        elif blur_score < 0.5:
            issues.append(f"图像清晰度一般 (清晰度分数: {blur_score:.2f})")
            overall_score *= 0.8

        # 亮度检测
        brightness_score = ImageProcessor.calculate_brightness_score(image)
        if brightness_score < 0.5:
            issues.append(f"图像过暗或过亮 (亮度分数: {brightness_score:.2f})")
            overall_score *= 0.7

        # NSFW检测
        nsfw_score = self.nsfw_detector.predict(image)
        if nsfw_score > 0.7:
            issues.append(f"检测到疑似不当内容 (NSFW分数: {nsfw_score:.2f})")
            overall_score *= 0.2
        elif nsfw_score > 0.3:
            issues.append(f"可能包含部分敏感内容 (NSFW分数: {nsfw_score:.2f})")
            overall_score *= 0.8

        # 分辨率检测
        try:
            import cv2
            h, w = image.shape[:2]
            if min(h, w) < 256:
                issues.append(f"分辨率过低 ({w}x{h})")
                overall_score *= 0.7
            elif max(h, w) > 4096:
                issues.append(f"分辨率过高 ({w}x{h}),建议缩放后处理")
        except Exception:
            pass

        is_valid = overall_score >= 0.5 and nsfw_score < 0.7

        return QualityCheckResult(
            is_valid=is_valid,
            issues=issues,
            overall_score=round(overall_score, 3),
            blur_score=round(blur_score, 3),
            brightness_score=round(brightness_score, 3),
            nsfw_score=round(nsfw_score, 3),
        )

    # ==================== 智能推荐 ====================

    def recommend_labels(
        self,
        image: Any,
        existing_labels: List[str],
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        智能推荐标签
        基于图像分析和现有标签库
        """
        recommendations = []

        try:
            # 图像分类
            classifications = self._classify_image(image, 0.3)

            # 过滤已存在的标签
            for cls in classifications[:top_k * 2]:
                if cls.label not in existing_labels:
                    recommendations.append((cls.label, cls.confidence))
                    if len(recommendations) >= top_k:
                        break

            # 添加相关性标签
            related_tags = self._get_related_tags(existing_labels)
            for tag in related_tags[:3]:
                if tag not in existing_labels:
                    recommendations.append((tag, 0.6))

        except Exception as e:
            logger.error(f"Label recommendation failed: {e}")

        return recommendations

    def _get_related_tags(self, tags: List[str]) -> List[str]:
        """获取相关标签"""
        # 标签关系映射
        tag_relations = {
            "cat": ["animal", "pet", "feline", "mammal"],
            "dog": ["animal", "pet", "canine", "mammal"],
            "car": ["vehicle", "transport", "automobile"],
            "person": ["human", "man", "woman", "people"],
        }

        related = []
        for tag in tags:
            if tag.lower() in tag_relations:
                related.extend(tag_relations[tag.lower()])

        return list(set(related))

    # ==================== 批量处理 ====================

    def batch_pre_annotate(
        self,
        images: List[Any],
        task_type: AITaskType,
        progress_callback: Optional[Callable] = None
    ) -> List[List[PreAnnotationResult]]:
        """
        批量预标注
        """
        results = []

        for i, image in enumerate(images):
            result = self.pre_annotate(image, task_type)
            results.append(result)

            if progress_callback:
                progress_callback((i + 1) / len(images), i + 1, len(images))

        return results

    def batch_quality_check(
        self,
        images: List[Any],
        progress_callback: Optional[Callable] = None
    ) -> List[QualityCheckResult]:
        """
        批量质量检测
        """
        results = []

        for i, image in enumerate(images):
            result = self.check_quality(image)
            results.append(result)

            if progress_callback:
                progress_callback((i + 1) / len(images), i + 1, len(images))

        return results

    # ==================== 模拟/测试数据 ====================

    def _mock_object_detection(
        self,
        image: Any,
        confidence: float
    ) -> List[PreAnnotationResult]:
        """生成模拟目标检测结果"""
        try:
            import cv2
            h, w = image.shape[:2]

            # 随机生成2-5个检测框
            import random
            num_objects = random.randint(2, 5)
            labels = ["person", "car", "dog", "cat", "chair", "bottle", "cup"]

            annotations = []
            for _ in range(num_objects):
                x1 = random.randint(0, w - 100)
                y1 = random.randint(0, h - 100)
                x2 = x1 + random.randint(50, min(200, w - x1))
                y2 = y1 + random.randint(50, min(200, h - y1))

                annotation = PreAnnotationResult(
                    annotation_id=f"anno_{uuid.uuid4().hex[:8]}",
                    annotation_type=AnnotationType.BOUNDING_BOX,
                    label=random.choice(labels),
                    confidence=random.uniform(confidence, 0.95),
                    geometry={
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        "width": x2 - x1, "height": y2 - y1,
                    },
                    model_name="Mock-YOLO",
                    processing_time_ms=50.0,
                )
                annotations.append(annotation)

            return annotations
        except Exception:
            return []

    def _mock_segmentation(
        self,
        image: Any,
        confidence: float,
        seg_type: str
    ) -> List[PreAnnotationResult]:
        """生成模拟分割结果"""
        try:
            import cv2
            import numpy as np

            h, w = image.shape[:2]

            # 生成随机多边形
            import random
            num_points = random.randint(4, 8)
            points = []
            cx, cy = w // 2, h // 2
            for i in range(num_points):
                angle = 2 * 3.14159 * i / num_points
                r = random.randint(min(h, w) // 4, min(h, w) // 2)
                x = int(cx + r * 0.5 * random.uniform(0.8, 1.2) * (0.5 + 0.5 * (i % 2)) * (1 if i % 2 == 0 else -1) * abs(math.cos(angle)))
                y = int(cy + r * 0.5 * random.uniform(0.8, 1.2) * (0.5 + 0.5 * (i % 2)) * abs(math.sin(angle)))
                x = max(0, min(w - 1, x))
                y = max(0, min(h - 1, y))
                points.append([x, y])

            annotation = PreAnnotationResult(
                annotation_id=f"anno_{uuid.uuid4().hex[:8]}",
                annotation_type=AnnotationType.POLYGON,
                label=f"{seg_type}_object",
                confidence=random.uniform(confidence, 0.95),
                geometry={"points": points},
                model_name="Mock-SAM",
            )

            return [annotation]
        except Exception:
            return []

    def _mock_classification(self, image: Any) -> List[PreAnnotationResult]:
        """生成模拟分类结果"""
        import random
        labels = ["indoor", "outdoor", "natural", "artificial", "photo", "graphic"]

        annotations = []
        for label in random.sample(labels, min(3, len(labels))):
            annotation = PreAnnotationResult(
                annotation_id=f"anno_{uuid.uuid4().hex[:8]}",
                annotation_type=AnnotationType.CLASSIFICATION,
                label=label,
                confidence=random.uniform(0.5, 0.9),
                geometry={},
                model_name="Mock-ResNet",
            )
            annotations.append(annotation)

        return annotations


# ==================== 全局实例 ====================

_ai_service = None


def get_ai_service() -> AIAnnotationService:
    """获取AI服务全局实例"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIAnnotationService()
    return _ai_service


# ==================== 测试代码 ====================

if __name__ == "__main__":
    import cv2
    import math

    print("=== AI辅助标注服务测试 ===")

    # 初始化服务
    ai_service = get_ai_service()

    # 检查模型状态
    status = ai_service.get_model_status()
    print(f"模型状态: {status}")

    # 创建测试图像
    test_image = cv2.imread(r"D:\minimax\nanobot-factory\nanobot-factory\test_image.jpg")
    if test_image is None:
        # 创建空白测试图像
        test_image = cv2.imread(cv2.samples.findFile("lena.jpg"))

    if test_image is not None:
        print(f"测试图像尺寸: {test_image.shape}")

        # 质量检测
        quality = ai_service.check_quality(test_image)
        print(f"质量检测结果: 有效={quality.is_valid}, 分数={quality.overall_score}")
        if quality.issues:
            print(f"  问题: {quality.issues}")

        # 预标注
        results = ai_service.pre_annotate(test_image, AITaskType.OBJECT_DETECTION)
        print(f"目标检测结果: {len(results)}个对象")
        for r in results[:3]:
            print(f"  - {r.label}: {r.confidence:.2f}")

        # 分类
        classifications = ai_service.pre_annotate(test_image, AITaskType.IMAGE_CLASSIFICATION)
        print(f"图像分类结果: {len(classifications)}个类别")
        for c in classifications[:3]:
            print(f"  - {c.label}: {c.confidence:.2f}")

    else:
        print("未找到测试图像")

    print("=== 测试完成 ===")
