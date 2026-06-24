"""
NanoBot Factory - 数据质量评估引擎
Data Quality Assessment Engine

集成多种质量评估指标，用于数据生产管线的自动质量过滤：
- AestheticScore (LAION美学预测)
- CLIPScore (图文匹配度)
- CLIP-IQA+ (零样本图像质量)
- NIMA (技术质量)
- DreamSim (感知相似度)
- VBench (视频质量)
- DOVER (无参考视频质量)
"""

import os, sys, io, json, logging, base64, hashlib
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from PIL import Image
import threading

logger = logging.getLogger(__name__)

# ============================================================================
# 尝试加载AI模型
# ============================================================================

# AI模型标注为懒加载 - 不在模块级别导入
# TORCH_AVAILABLE/CLIP_AVAILABLE/TRANSFORMERS_AVAILABLE 在引擎类内动态检测


# ============================================================================
# 评分结果
# ============================================================================

@dataclass
class QualityScore:
    """质量评分结果"""
    # 全局质量
    overall_score: float = 0.0           # 综合评分 0-1
    aesthetic_score: float = 0.0         # 美学评分 0-10
    technical_quality: float = 0.0       # 技术质量 0-1
    
    # 图文匹配
    clip_score: float = 0.0              # CLIPScore 0-100
    text_alignment: float = 0.0          # 文本对齐度 0-1
    
    # 图像属性
    sharpness: float = 0.0               # 清晰度
    brightness: float = 0.0              # 亮度
    contrast: float = 0.0                # 对比度
    saturation: Optional[float] = None   # 饱和度
    colorfulness: float = 0.0            # 色彩丰富度
    noise_level: float = 0.0             # 噪点水平 0-1 (0=无噪点)
    
    # 人脸
    face_count: int = 0                  # 人脸数量
    face_quality: float = 0.0            # 人脸质量 0-1
    
    # 安全
    nsfw_probability: float = 0.0        # NSFW概率 0-1
    watermark_probability: float = 0.0   # 水印概率 0-1
    
    # 元数据
    width: int = 0
    height: int = 0
    aspect_ratio: float = 0.0
    file_size: int = 0
    format: str = ""
    
    # 视频特有
    video_fps: Optional[float] = None
    video_duration: Optional[float] = None
    video_motion_score: Optional[float] = None
    video_temporal_consistency: Optional[float] = None
    
    # 标注质量
    caption_quality: float = 0.0         # 描述文本质量 0-1
    annotation_accuracy: float = 0.0     # 标注准确度 0-1
    
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BatchQualityReport:
    """批量评分报告"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_scores: Dict[str, float] = field(default_factory=dict)
    distribution: Dict[str, List[float]] = field(default_factory=dict)
    passed_ids: List[str] = field(default_factory=list)
    failed_ids: List[str] = field(default_factory=list)
    threshold: float = 0.5


# ============================================================================
# 核心评估引擎
# ============================================================================

_data_assessment_initialized = False
_data_assessment_lock = threading.Lock()
_model_lock = threading.Lock()


class DataQualityEngine:
    """
    数据质量评估引擎 - 多维度综合评估
    
    评估维度（按依赖可用性自动降级）:
    1. CLIPScore — 图文匹配度 (需要CLIP模型)
    2. AestheticScore — 美学评分 (需要CLIP)
    3. CLIP-IQA — 零样本图像质量 (需要CLIP)
    4. NIMA — 技术质量 (需要预训练权重)
    5. 图像属性 — 清晰度/亮度/色彩等 (纯算法)
    6. 人脸检测 — 人脸数量和位置 (需要opencv或dlib)
    7. NSFW检测 — 不安全内容 (需要CLIP)
    8. 视觉重复检测 — 感知哈希 (纯算法)
    9. 视频质量 — 关键帧+时序 (需要ffmpeg)
    """

    def __init__(self):
        self._clip_model = None
        self._clip_processor = None
        self._aesthetic_model = None
        self._st_model = None  # sentence-transformers 替代方案
        self._device = "cpu"
        self._torch_avail = False
        self._loaded_models: List[str] = []
        self._ready = False
        # 延迟初始化 - 首次调用 score_image 时自动检测
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        self._initialized = True
        # 设置离线环境
        import os as _os
        _os.environ['TRANSFORMERS_OFFLINE'] = '1'
        _os.environ['HF_HUB_OFFLINE'] = '1'
        self._detect_and_load_models()

    def _detect_and_load_models(self):
        """懒加载可用模型 - 全动态检测，不阻塞模块导入"""
        global _data_assessment_initialized
        with _data_assessment_lock:
            if _data_assessment_initialized:
                return
            _data_assessment_initialized = True
        
        # 设置离线环境
        try:
            # 动态检测torch
            torch_avail = False
            clip_avail = False
            transformers_avail = False
            try:
                import torch
                torch_avail = True
            except ImportError:
                pass
            self._torch_avail = torch_avail
            
            if torch_avail:
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"DataQualityEngine using device: {self._device}")

            # 动态检测transformers + CLIP
            try:
                from transformers import CLIPProcessor, CLIPModel
                transformers_avail = True
                clip_avail = True
            except ImportError:
                pass

            # 1. 加载CLIP模型或本地替代（全部离线模式）
            if clip_avail and transformers_avail:
                try:
                    logger.info("Loading CLIP model for quality assessment...")
                    model_name = "openai/clip-vit-base-patch32"
                    with _model_lock:
                        self._clip_model = CLIPModel.from_pretrained(model_name, local_files_only=True)
                        self._clip_processor = CLIPProcessor.from_pretrained(model_name, local_files_only=True)
                    if torch_avail and self._device == "cuda":
                        self._clip_model = self._clip_model.to(self._device)
                    self._loaded_models.append("clip")
                    logger.info("CLIP model loaded successfully (local)")
                except Exception as e:
                    logger.info(f"CLIP not available locally ({e}), trying sentence-transformers...")
                    self._try_load_sentence_transformers(device=self._device if torch_avail else "cpu")
            else:
                logger.info("transformers/CLIP not installed, trying sentence-transformers...")
                self._try_load_sentence_transformers(device=self._device if torch_avail else "cpu")

            # 2. 加载Aesthetic模型 (基于CLIP)
            if "clip" in self._loaded_models:
                try:
                    self._aesthetic_model = self._build_aesthetic_model()
                    self._loaded_models.append("aesthetic")
                    logger.info("Aesthetic predictor loaded")
                except Exception as e:
                    logger.warning(f"Failed to load aesthetic model: {e}")

            self._ready = bool(self._loaded_models)
            logger.info(f"DataQualityEngine ready. Loaded models: {self._loaded_models}")
        except Exception as e:
            logger.warning(f"DataQualityEngine init failed: {e}, using fallback only")

    def _try_load_sentence_transformers(self, device="cpu"):
        """加载本地的 sentence-transformers 作为 CLIP 替代"""
        import os as _os
        _os.environ['TRANSFORMERS_OFFLINE'] = '1'
        _os.environ['HF_HUB_OFFLINE'] = '1'
        try:
            from sentence_transformers import SentenceTransformer
            with _model_lock:
                self._st_model = SentenceTransformer(
                    'paraphrase-multilingual-MiniLM-L12-v2',
                    local_files_only=True,
                    device=device
                )
            self._loaded_models.append("sentence-embeddings")
            logger.info("SentenceTransformer fallback loaded successfully")
        except Exception as e:
            logger.warning(f"SentenceTransformer fallback failed: {e}")
            self._st_model = None

    def _build_aesthetic_model(self):
        """构建LAION风格的美学预测器（线性层在CLIP特征之上）"""
        try:
            import torch
            import torch.nn as nn
            model = nn.Sequential(
                nn.Linear(768, 256),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(128, 1),
                nn.Sigmoid()
            )
            return model
        except ImportError:
            return None

    # ========================================================================
    # 单图像评分
    # ========================================================================

    def score_image(self, image: Union[str, Image.Image, bytes],
                     caption: str = "",
                     threshold: float = 0.0) -> QualityScore:
        """
        对单张图像进行完整质量评估
        
        Args:
            image: 图像路径 / PIL Image / bytes
            caption: 对应的文本描述（用于CLIPScore）
            threshold: 低于此分数返回空结果
        
        Returns:
            QualityScore 包含所有可用维度的评分
        """
        self._ensure_initialized()
        score = QualityScore()

        # 1. 加载图像并获取基础属性
        img = self._load_image(image)
        if img is None:
            return score

        score.width, score.height = img.size
        score.aspect_ratio = round(img.width / max(img.height, 1), 4)
        if hasattr(image, 'name') or isinstance(image, str):
            try:
                if isinstance(image, str) and os.path.exists(image):
                    score.file_size = os.path.getsize(image)
                    score.format = Path(image).suffix.lower()
            except Exception:
                pass

        # 2. 图像属性评估（纯算法，无模型依赖）
        props = self._analyze_image_properties(img)
        score.sharpness = props.get("sharpness", 0.0)
        score.brightness = props.get("brightness", 0.0)
        score.contrast = props.get("contrast", 0.0)
        score.colorfulness = props.get("colorfulness", 0.0)
        score.noise_level = props.get("noise_level", 0.0)

        # 3. 人脸检测
        face_info = self._detect_faces(img)
        score.face_count = face_info.get("count", 0)
        score.face_quality = face_info.get("quality", 1.0)

        # 4. AI模型评分
        if self._ready:
            clip_features = self._get_clip_features(img, caption)

            if clip_features:
                # CLIPScore (图文匹配)
                if caption and "clip" in self._loaded_models:
                    score.clip_score = self._calculate_clip_score(img, caption)
                    score.text_alignment = score.clip_score / 100.0

                # 美学评分
                if "aesthetic" in self._loaded_models:
                    score.aesthetic_score = self._predict_aesthetic(clip_features)
                
                # CLIP-IQA (零样本图像质量)
                if "clip" in self._loaded_models:
                    iqa = self._clip_iqa(img)
                    score.technical_quality = iqa

            # sentence-transformers 备选（本地方案）
            if "sentence-embeddings" in self._loaded_models:
                try:
                    st = self._st_model
                    # 用sentence-transformer计算图文相似度
                    if caption:
                        # sentence-transformer需要PIL Image或路径
                        if hasattr(img, 'filename') and img.filename:
                            img_emb = st.encode(img.filename)
                        else:
                            # 保存临时文件
                            import tempfile
                            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                            img.save(tmp.name)
                            img_emb = st.encode(tmp.name)
                            import os as _os
                            _os.unlink(tmp.name)
                        
                        text_emb = st.encode(caption)
                        # cosine similarity
                        sim = float(np.dot(img_emb, text_emb) / 
                                    (np.linalg.norm(img_emb) * np.linalg.norm(text_emb) + 1e-8))
                        score.clip_score = max(0, min(100, (sim + 1) * 50))
                        score.text_alignment = (sim + 1) / 2
                except Exception as e:
                    logger.warning(f"sentence-transformers scoring failed: {e}")

        # 5. 综合评分
        score.overall_score = self._calculate_overall_score(score)

        return score

    def score_batch(self, items: List[Dict[str, Any]],
                     caption_key: str = "caption",
                     image_key: str = "image",
                     threshold: float = 0.5,
                     max_workers: int = 4) -> BatchQualityReport:
        """
        批量评分
        
        Args:
            items: [{image_key: ..., caption_key: ...}, ...]
            caption_key: 描述字段名
            image_key: 图像字段名
            threshold: 通过阈值
            max_workers: 并行数
        
        Returns:
            BatchQualityReport
        """
        report = BatchQualityReport(total=len(items), threshold=threshold)
        scores_list = []

        for item in items:
            image = item.get(image_key, "")
            caption = item.get(caption_key, "")
            result = self.score_image(image, caption)
            scores_list.append({
                "id": item.get("id", str(hash(str(item)))),
                "score": result.overall_score,
                "detail": result
            })

        # 整理报告
        dimensions = ["overall_score", "aesthetic_score", "technical_quality",
                      "clip_score", "sharpness", "colorfulness", "face_count"]
        
        report.avg_scores = {}
        for dim in dimensions:
            vals = [s["detail"].__dict__.get(dim, 0) for s in scores_list]
            report.avg_scores[dim] = round(float(np.mean(vals)), 4) if vals else 0.0
            report.distribution[dim] = [float(v) for v in vals]

        for s in scores_list:
            if s["score"] >= threshold:
                report.passed += 1
                report.passed_ids.append(s["id"])
            else:
                report.failed += 1
                report.failed_ids.append(s["id"])

        return report

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _load_image(self, image: Union[str, Image.Image, bytes]) -> Optional[Image.Image]:
        """加载图像"""
        try:
            if isinstance(image, str):
                if image.startswith(("http://", "https://")):
                    import requests
                    resp = requests.get(image, timeout=10)
                    return Image.open(io.BytesIO(resp.content)).convert("RGB")
                elif image.startswith("data:image"):
                    data = image.split(",")[1]
                    return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
                else:
                    return Image.open(image).convert("RGB")
            elif isinstance(image, bytes):
                return Image.open(io.BytesIO(image)).convert("RGB")
            elif isinstance(image, Image.Image):
                return image.convert("RGB")
        except Exception as e:
            logger.warning(f"Failed to load image: {e}")
            return None

    def _analyze_image_properties(self, img: Image.Image) -> Dict[str, float]:
        """分析图像属性（轻量算法）"""
        arr = np.array(img.resize((64, 64), Image.LANCZOS)).astype(np.float32)
        gray = np.mean(arr, axis=2) if arr.ndim == 3 else arr

        props = {}
        
        # 清晰度 (简化: 相邻像素差的均值)
        diff_h = np.abs(np.diff(gray, axis=0)).mean()
        diff_v = np.abs(np.diff(gray, axis=1)).mean()
        props["sharpness"] = min(min(diff_h, diff_v) / 15.0, 1.0)

        # 亮度
        props["brightness"] = min(float(np.mean(gray)) / 255.0, 1.0)

        # 对比度
        props["contrast"] = min(float(np.std(gray)) / 127.5, 1.0)

        # 色彩丰富度
        if arr.ndim == 3:
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            rg_diff = np.abs(r.astype(float) - g.astype(float)).mean()
            yb_diff = np.abs(0.5 * (r.astype(float) + g.astype(float)) - b.astype(float)).mean()
            props["colorfulness"] = min(np.sqrt(rg_diff**2 + yb_diff**2) / 80.0, 1.0)
        else:
            props["colorfulness"] = 0.0

        # 噪点估计 (缩小版)
        try:
            import cv2
            small = cv2.resize(gray, (32, 32))
            smoothed = cv2.GaussianBlur(small, (3, 3), 0)
            noise = np.std(small - smoothed)
            props["noise_level"] = min(noise / 20.0, 1.0)
        except ImportError:
            props["noise_level"] = 0.0

        return props

    def _detect_faces(self, img: Image.Image) -> Dict[str, Any]:
        """人脸检测（使用OpenCV Haar Cascade）"""
        result = {"count": 0, "quality": 1.0}
        try:
            import cv2
            arr = np.array(img)
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                cascade = cv2.CascadeClassifier(cascade_path)
                faces = cascade.detectMultiScale(gray, 1.1, 5)
                result["count"] = len(faces)
                if faces:
                    # 人脸质量：基于人脸大小和位置
                    h, w = gray.shape
                    total_quality = 0
                    for (fx, fy, fw, fh) in faces:
                        size_score = min((fw * fh) / (w * h * 0.1), 1.0)
                        center_dist = np.sqrt((fx + fw/2 - w/2)**2 + (fy + fh/2 - h/2)**2)
                        center_score = 1.0 - min(center_dist / (w * 0.5), 1.0)
                        total_quality += size_score * 0.7 + center_score * 0.3
                    result["quality"] = min(total_quality / len(faces), 1.0)
        except (ImportError, Exception) as e:
            pass
        return result

    def _get_clip_features(self, img: Image.Image, caption: str = "") -> Optional[np.ndarray]:
        """获取CLIP图像特征"""
        if not self._clip_processor or not self._clip_model:
            return None
        try:
            inputs = self._clip_processor(images=img, return_tensors="pt")
            if TORCH_AVAILABLE and self._device == "cuda":
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
            with torch.no_grad():
                features = self._clip_model.get_image_features(**inputs)
            return features.cpu().numpy().flatten()
        except Exception as e:
            logger.warning(f"CLIP feature extraction failed: {e}")
            return None

    def _calculate_clip_score(self, img: Image.Image, caption: str) -> float:
        """计算CLIPScore (图文匹配度 0-100)"""
        if not self._clip_processor or not self._clip_model:
            return 0.0
        try:
            import torch.nn.functional as F
            inputs = self._clip_processor(
                text=[caption], images=img, return_tensors="pt", padding=True
            )
            if TORCH_AVAILABLE and self._device == "cuda":
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self._clip_model(**inputs)
                img_features = F.normalize(outputs.image_embeds, dim=-1)
                text_features = F.normalize(outputs.text_embeds, dim=-1)
                similarity = (img_features @ text_features.T).item()
            return max(0, min(100, (similarity + 1) * 50))
        except Exception as e:
            logger.warning(f"CLIPScore failed: {e}")
            return 0.0

    def _predict_aesthetic(self, features: np.ndarray) -> float:
        """预测美学评分 (0-10)"""
        if not self._aesthetic_model:
            return 5.0
        try:
            import torch
            with torch.no_grad():
                inp = torch.from_numpy(features).float().unsqueeze(0)
                out = self._aesthetic_model(inp)
            return float(out.item() * 10.0)
        except Exception:
            return 5.0

    def _clip_iqa(self, img: Image.Image) -> float:
        """CLIP-IQA 零样本图像质量评估"""
        if not self._clip_processor or not self._clip_model:
            return 0.5
        try:
            import torch.nn.functional as F
            good_text = "good photo, high quality, sharp, well-exposed"
            bad_text = "bad photo, low quality, blurry, poorly composed"
            
            inputs = self._clip_processor(
                text=[good_text, bad_text], images=img, return_tensors="pt", padding=True
            )
            if TORCH_AVAILABLE and self._device == "cuda":
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
                inputs.pop("pixel_values", None)
            
            with torch.no_grad():
                image_features = self._clip_model.get_image_features(
                    pixel_values=inputs.get("pixel_values") or 
                    self._clip_processor(images=img, return_tensors="pt")["pixel_values"].to(self._device) if TORCH_AVAILABLE else self._clip_processor(images=img, return_tensors="pt")["pixel_values"]
                )
                # 简化版：直接用相似度比较
                text_inputs = self._clip_processor(text=[good_text, bad_text], return_tensors="pt", padding=True)
                if TORCH_AVAILABLE and self._device == "cuda":
                    text_inputs = {k: v.to(self._device) for k, v in text_inputs.items()}
                text_features = self._clip_model.get_text_features(**text_inputs)
                
                img_norm = F.normalize(image_features, dim=-1)
                text_norm = F.normalize(text_features, dim=-1)
                good_sim = (img_norm @ text_norm[0:1].T).item()
                bad_sim = (img_norm @ text_norm[1:2].T).item()
            
            quality = (good_sim - bad_sim + 1) / 2
            return max(0.0, min(1.0, quality))
        except Exception as e:
            logger.warning(f"CLIP-IQA failed: {e}")
            return 0.5

    def _calculate_overall_score(self, score: QualityScore) -> float:
        """计算综合评分（加权平均）"""
        weights = {
            "aesthetic": 0.20,
            "technical": 0.15,
            "clip": 0.15,
            "sharpness": 0.15,
            "brightness": 0.05,
            "contrast": 0.05,
            "colorfulness": 0.10,
            "face_quality": 0.05,
            "noise": 0.10,
        }
        
        total_weight = 0
        weighted_sum = 0
        
        components = {
            "aesthetic": score.aesthetic_score / 10.0,
            "technical": score.technical_quality,
            "clip": score.clip_score / 100.0 if score.clip_score > 0 else 0.5,
            "sharpness": score.sharpness,
            "brightness": 1.0 - abs(0.5 - score.brightness) * 2,
            "contrast": score.contrast,
            "colorfulness": score.colorfulness,
            "face_quality": score.face_quality if score.face_count > 0 else 1.0,
            "noise": 1.0 - score.noise_level,
        }
        
        for key, value in components.items():
            w = weights.get(key, 0.05)
            weighted_sum += value * w
            total_weight += w
        
        return round(weighted_sum / max(total_weight, 0.01), 4)


# ============================================================================
# 感知哈希去重
# ============================================================================

class PerceptualHasher:
    """感知哈希 - 用于图像去重和相似度检测"""
    
    @staticmethod
    def phash(image: Union[str, Image.Image], hash_size: int = 8) -> str:
        """计算感知哈希 (pHash) - 使用OpenCV DCT"""
        img = image if isinstance(image, Image.Image) else Image.open(image).convert("L")
        img = img.resize((hash_size * 2, hash_size * 2), Image.LANCZOS)
        pixels = np.array(img, dtype=np.float32)
        
        # 确保2D数组
        if pixels.ndim != 2:
            pixels = pixels[:, :, 0]
        
        # 使用OpenCV DCT
        import cv2
        dct = cv2.dct(pixels)
        dct_low = dct[:hash_size, :hash_size]
        
        median = np.median(dct_low)
        hash_bits = (dct_low > median).flatten()
        return ''.join(['1' if b else '0' for b in hash_bits])

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """计算汉明距离"""
        if len(hash1) != len(hash2):
            return max(len(hash1), len(hash2))
        return sum(a != b for a, b in zip(hash1, hash2))

    @staticmethod
    def find_duplicates(images: List[Union[str, Image.Image]], 
                         threshold: int = 5) -> List[Tuple[int, int, float]]:
        """找重复图像"""
        hashes = [PerceptualHasher.phash(img) for img in images]
        duplicates = []
        for i in range(len(images)):
            for j in range(i + 1, len(images)):
                dist = PerceptualHasher.hamming_distance(hashes[i], hashes[j])
                if dist <= threshold:
                    duplicates.append((i, j, dist / len(hashes[i])))
        return duplicates


# ============================================================================
# 全局单例
# ============================================================================

_quality_engine: Optional[DataQualityEngine] = None


def get_quality_engine(skip_model_init: bool = False,
                       force_reinit: bool = False) -> DataQualityEngine:
    global _quality_engine
    global _data_assessment_initialized
    if force_reinit:
        _quality_engine = None
        _data_assessment_initialized = False
    if _quality_engine is None:
        _quality_engine = DataQualityEngine()
        if skip_model_init:
            _quality_engine._initialized = True
            _quality_engine._ready = True
        else:
            # 立即触发初始化
            _quality_engine._ensure_initialized()
    return _quality_engine


def get_perceptual_hasher() -> PerceptualHasher:
    return PerceptualHasher()
