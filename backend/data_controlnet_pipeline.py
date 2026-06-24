"""
NanoBot Factory - ControlNet条件数据生成管线
ControlNet Conditional Data Generation Pipeline

功能:
- Canny边缘检测 (基于OpenCV)
- 深度图估计 (灰度梯度近似，无需MiDaS)
- 姿态骨架 (简化版OpenPose，基于OpenCV)
- 语义分割 (K-means近似，无需SAM)
- 一键生成所有条件+原始图对
- 保存ControlNet标准训练格式
"""

import os, json, logging, io, base64
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class ControlPair:
    """一张图像的完整ControlNet条件对"""
    image_id: str
    source_image_path: str          # 原始图像路径
    canny_path: str = ""            # Canny边缘图路径
    depth_path: str = ""            # 深度图路径
    pose_path: str = ""             # 姿态骨架路径
    segmentation_path: str = ""     # 语义分割路径
    caption: str = ""               # 文本描述
    width: int = 0
    height: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ControlDataset:
    """ControlNet标准训练数据集"""
    name: str
    pairs: List[ControlPair] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    total: int = 0
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# ControlNet Processor
# ============================================================================

class ControlNetProcessor:
    """
    ControlNet条件数据生成处理器

    生成4种条件图:
    - canny: Canny边缘检测
    - depth: 深度图估计 (灰度梯度近似)
    - pose: 姿态骨架 (OpenCV Haar Cascade + 简化骨架)
    - segmentation: 语义分割 (K-means聚类近似)

    全部使用本地OpenCV实现，无需下载外部模型。
    """

    SUPPORTED_CONDITIONS = ["canny", "depth", "pose", "segmentation"]

    def __init__(self, output_dir: str = "./data/controlnet"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_image(self, image: Union[str, Image.Image, np.ndarray]) -> Optional[np.ndarray]:
        """加载为OpenCV BGR格式"""
        try:
            if isinstance(image, str):
                if not os.path.exists(image):
                    logger.warning(f"Image not found: {image}")
                    return None
                return cv2.imread(image)
            elif isinstance(image, Image.Image):
                return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
            elif isinstance(image, np.ndarray):
                return image
        except Exception as e:
            logger.warning(f"Failed to load image: {e}")
            return None

    def _to_pil(self, img: np.ndarray) -> Image.Image:
        """OpenCV BGR → PIL RGB"""
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    def _save_image(self, img: np.ndarray, path: str) -> str:
        """保存图像并返回路径"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cv2.imwrite(path, img)
        return path

    # ========================================================================
    # Canny Edge Detection
    # ========================================================================

    def canny_edge(self, image: Union[str, Image.Image, np.ndarray],
                   low_threshold: float = 50,
                   high_threshold: float = 150,
                   invert: bool = True) -> np.ndarray:
        """
        Canny边缘检测

        Args:
            image: 输入图像
            low_threshold: 低阈值
            high_threshold: 高阈值
            invert: 是否反转 (ControlNet标准: 白底黑线)

        Returns:
            边缘图 (BGR格式)
        """
        if not CV2_AVAILABLE:
            raise RuntimeError("OpenCV (cv2) is required for canny_edge")

        img = self._load_image(image)
        if img is None:
            raise ValueError("Cannot load image")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 去噪
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
        edges = cv2.Canny(blurred, low_threshold, high_threshold)

        if invert:
            edges = cv2.bitwise_not(edges)

        # 转回BGR 3通道
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    # ========================================================================
    # Depth Map Estimation
    # ========================================================================

    def depth_map(self, image: Union[str, Image.Image, np.ndarray]) -> np.ndarray:
        """
        深度图估计 (灰度梯度近似)

        使用图像梯度+局部对比度来近似深度图。
        不需要MiDaS或任何深度学习模型。

        ControlNet标准: 单通道灰度图, 近处亮远处暗。
        """
        if not CV2_AVAILABLE:
            raise RuntimeError("OpenCV (cv2) is required for depth_map")

        img = self._load_image(image)
        if img is None:
            raise ValueError("Cannot load image")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape

        # 1. 大气透视近似: 远处区域对比度低
        # 将图像分成网格，计算每个网格的局部对比度
        grid_size = 16
        depth_contrast = np.zeros_like(gray)
        for y in range(0, h, grid_size):
            for x in range(0, w, grid_size):
                y_end = min(y + grid_size, h)
                x_end = min(x + grid_size, w)
                patch = gray[y:y_end, x:x_end]
                local_std = float(np.std(patch))
                depth_contrast[y:y_end, x:x_end] = local_std

        # 归一化: 高对比度 = 近处 (亮)
        depth_contrast = cv2.normalize(depth_contrast, None, 0, 255, cv2.NORM_MINMAX)

        # 2. 梯度多尺度分析
        # 计算x和y方向的梯度幅值
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_mag = np.sqrt(grad_x**2 + grad_y**2)
        gradient_mag = cv2.normalize(gradient_mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)

        # 3. 亮度先验: 通常下部亮度更高的区域更近
        y_weight = np.tile(
            np.linspace(1.0, 0.5, h).reshape(-1, 1), (1, w)
        ).astype(np.float32)
        depth_brightness = gray * y_weight
        depth_brightness = cv2.normalize(depth_brightness, None, 0, 255, cv2.NORM_MINMAX)

        # 融合: 加权平均
        depth = depth_contrast * 0.4 + gradient_mag * 0.3 + depth_brightness * 0.3
        depth = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # 高斯平滑
        depth = cv2.GaussianBlur(depth, (7, 7), 2.0)

        return cv2.cvtColor(depth, cv2.COLOR_GRAY2BGR)

    # ========================================================================
    # Pose Skeleton (简化版OpenPose)
    # ========================================================================

    def openpose_pose(self, image: Union[str, Image.Image, np.ndarray]) -> np.ndarray:
        """
        姿态骨架 (简化版)

        使用OpenCV Haar Cascade检测人脸，然后绘制简化骨架。
        真实OpenPose需要下载模型，此版本作为轻量替代。

        ControlNet标准: 黑底彩色骨架线。
        """
        if not CV2_AVAILABLE:
            raise RuntimeError("OpenCV (cv2) is required for openpose_pose")

        img = self._load_image(image)
        if img is None:
            raise ValueError("Cannot load image")

        h, w = img.shape[:2]
        # 创建黑底画布
        canvas = np.zeros((h, w, 3), dtype=np.uint8)

        # 1. 人脸检测
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if os.path.exists(face_cascade_path):
            face_cascade = cv2.CascadeClassifier(face_cascade_path)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))

            for (fx, fy, fw, fh) in faces:
                # 人脸中心
                face_cx = fx + fw // 2
                face_cy = fy + fh // 2
                face_radius = min(fw, fh) // 2

                # 画头部 (圆圈)
                cv2.circle(canvas, (face_cx, face_cy), face_radius, (0, 255, 0), 2)

                # 身体中线 (从人脸向下)
                body_top = face_cy + face_radius
                body_bottom = min(h - 1, body_top + int(h * 0.4))
                cv2.line(canvas, (face_cx, body_top), (face_cx, body_bottom), (0, 255, 0), 2)

                # 肩膀
                shoulder_y = body_top + int(h * 0.08)
                shoulder_width = int(w * 0.15)
                cv2.line(canvas,
                        (max(0, face_cx - shoulder_width), shoulder_y),
                        (min(w, face_cx + shoulder_width), shoulder_y),
                        (255, 0, 0), 2)

                # 左臂
                arm_end_y = shoulder_y + int(h * 0.2)
                cv2.line(canvas,
                        (face_cx - shoulder_width, shoulder_y),
                        (max(0, face_cx - shoulder_width - int(w * 0.05)), arm_end_y),
                        (255, 0, 0), 2)

                # 右臂
                cv2.line(canvas,
                        (face_cx + shoulder_width, shoulder_y),
                        (min(w, face_cx + shoulder_width + int(w * 0.05)), arm_end_y),
                        (255, 0, 0), 2)

                # 眼睛
                eye_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_eye.xml"
                )
                face_roi = gray[fy:fy+fh, fx:fx+fw]
                eyes = eye_cascade.detectMultiScale(face_roi, 1.1, 5, minSize=(5, 5))
                for (ex, ey, ew, eh) in eyes:
                    eye_cx = fx + ex + ew // 2
                    eye_cy = fy + ey + eh // 2
                    cv2.circle(canvas, (eye_cx, eye_cy), max(1, ew // 4), (0, 0, 255), -1)

        # 全身姿态检测 (使用身体检测)
        body_cascade_path = cv2.data.haarcascades + "haarcascade_fullbody.xml"
        if os.path.exists(body_cascade_path):
            body_cascade = cv2.CascadeClassifier(body_cascade_path)
            bodies = body_cascade.detectMultiScale(gray, 1.1, 3, minSize=(60, 120))

            for (bx, by, bw, bh) in bodies:
                # 身体矩形
                cv2.rectangle(canvas, (bx, by), (bx + bw, by + bh), (255, 165, 0), 2)
                # 身体中心线
                cx_body = bx + bw // 2
                cv2.line(canvas, (cx_body, by), (cx_body, by + bh), (255, 165, 0), 1)

        return canvas

    # ========================================================================
    # Segmentation Map (K-means近似)
    # ========================================================================

    def segmentation_map(self, image: Union[str, Image.Image, np.ndarray],
                          num_clusters: int = 8) -> np.ndarray:
        """
        语义分割图 (K-means聚类近似)

        使用K-means颜色聚类来近似语义分割。
        不需要SAM或任何分割模型。

        ControlNet标准: 彩色分割图, 每个区域一种颜色。
        """
        if not CV2_AVAILABLE:
            raise RuntimeError("OpenCV (cv2) is required for segmentation_map")

        img = self._load_image(image)
        if img is None:
            raise ValueError("Cannot load image")

        h, w = img.shape[:2]

        # 下采样以加速
        scale = min(256.0 / max(h, w), 1.0)
        if scale < 1.0:
            small = cv2.resize(img, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)
        else:
            small = img.copy()

        # 重塑为像素列表
        pixels = small.reshape(-1, 3).astype(np.float32)

        # K-means聚类
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, labels, centers = cv2.kmeans(
            pixels, num_clusters, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
        )

        # 为每个聚类分配不同的颜色
        # 使用一组区分度高的颜色
        palette = np.array([
            [128, 0, 0], [0, 128, 0], [0, 0, 128],
            [128, 128, 0], [128, 0, 128], [0, 128, 128],
            [255, 128, 0], [128, 255, 0], [0, 255, 128],
            [128, 0, 255], [255, 0, 128], [0, 128, 255],
            [64, 64, 64], [200, 200, 200], [100, 100, 200],
        ], dtype=np.uint8)

        # 映射到颜色
        colored = palette[labels.flatten().astype(int) % len(palette)]
        seg_small = colored.reshape(small.shape)

        # 缩放到原尺寸
        if scale < 1.0:
            seg = cv2.resize(seg_small, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            seg = seg_small

        return seg

    # ========================================================================
    # 一键生成所有条件图
    # ========================================================================

    def generate_control_pairs(
        self,
        image: Union[str, Image.Image, np.ndarray],
        conditions: Optional[List[str]] = None,
        caption: str = "",
        image_id: str = "",
        save: bool = True,
        output_subdir: str = ""
    ) -> ControlPair:
        """
        一键生成所有条件图 + 原始图对

        Args:
            image: 输入图像
            conditions: 要生成的条件类型 (默认: 全部)
            caption: 文本描述
            image_id: 图像ID
            save: 是否保存到磁盘
            output_subdir: 输出子目录

        Returns:
            ControlPair 包含所有生成的图路径
        """
        if conditions is None:
            conditions = self.SUPPORTED_CONDITIONS

        img = self._load_image(image)
        if img is None:
            raise ValueError("Cannot load image")

        h, w = img.shape[:2]

        if not image_id:
            import hashlib, time
            image_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]

        pair = ControlPair(
            image_id=image_id,
            source_image_path="",
            caption=caption,
            width=w,
            height=h,
        )

        if not save:
            # 只在内存中生成
            for cond in conditions:
                if cond == "canny":
                    pair.canny_path = "memory"
                elif cond == "depth":
                    pair.depth_path = "memory"
                elif cond == "pose":
                    pair.pose_path = "memory"
                elif cond == "segmentation":
                    pair.segmentation_path = "memory"
            return pair

        # 保存到磁盘
        subdir = self.output_dir / output_subdir if output_subdir else self.output_dir
        source_dir = subdir / "source"
        cond_dir = subdir / "conditions"
        source_dir.mkdir(parents=True, exist_ok=True)
        cond_dir.mkdir(parents=True, exist_ok=True)

        # 保存原图
        source_path = str(source_dir / f"{image_id}.png")
        cv2.imwrite(source_path, img)
        pair.source_image_path = source_path

        # 生成并保存条件图
        for cond in conditions:
            if cond == "canny":
                cond_img = self.canny_edge(img)
                out_path = str(cond_dir / f"{image_id}_canny.png")
                self._save_image(cond_img, out_path)
                pair.canny_path = out_path

            elif cond == "depth":
                cond_img = self.depth_map(img)
                out_path = str(cond_dir / f"{image_id}_depth.png")
                self._save_image(cond_img, out_path)
                pair.depth_path = out_path

            elif cond == "pose":
                cond_img = self.openpose_pose(img)
                out_path = str(cond_dir / f"{image_id}_pose.png")
                self._save_image(cond_img, out_path)
                pair.pose_path = out_path

            elif cond == "segmentation":
                cond_img = self.segmentation_map(img)
                out_path = str(cond_dir / f"{image_id}_segmentation.png")
                self._save_image(cond_img, out_path)
                pair.segmentation_path = out_path

        return pair

    # ========================================================================
    # 批量生成
    # ========================================================================

    def generate_batch(
        self,
        images: List[Union[str, Image.Image, np.ndarray]],
        captions: Optional[List[str]] = None,
        conditions: Optional[List[str]] = None,
        output_subdir: str = "batch"
    ) -> ControlDataset:
        """
        批量生成ControlNet条件数据

        Args:
            images: 输入图像列表
            captions: 对应的文本描述列表
            conditions: 要生成的条件类型
            output_subdir: 输出子目录

        Returns:
            ControlDataset
        """
        if captions is None:
            captions = [""] * len(images)

        dataset = ControlDataset(
            name=output_subdir,
            conditions=conditions or self.SUPPORTED_CONDITIONS,
        )

        for i, img in enumerate(images):
            caption = captions[i] if i < len(captions) else ""
            try:
                pair = self.generate_control_pairs(
                    img, conditions=conditions,
                    caption=caption,
                    image_id=f"img_{i:06d}",
                    save=True,
                    output_subdir=output_subdir
                )
                dataset.pairs.append(pair)
            except Exception as e:
                logger.warning(f"Failed to generate control pairs for image {i}: {e}")

        dataset.total = len(dataset.pairs)

        # 保存数据集元数据
        meta_path = self.output_dir / output_subdir / "dataset.json"
        if dataset.pairs:
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            with open(meta_path, "w") as f:
                json.dump({
                    "name": dataset.name,
                    "conditions": dataset.conditions,
                    "total": dataset.total,
                    "pairs": [asdict(p) for p in dataset.pairs],
                    "created_at": dataset.created_at,
                }, f, indent=2, default=str)

        return dataset

    # ========================================================================
    # 保存为标准ControlNet格式
    # ========================================================================

    def save_control_dataset(
        self,
        dataset: ControlDataset,
        output_dir: str = "",
        format: str = "controlnet"
    ) -> str:
        """
        保存为ControlNet标准训练格式

        ControlNet标准格式:
        output_dir/
            source/           # 原始图像
            canny/            # Canny条件图
            depth/            # 深度条件图
            pose/             # 姿态条件图
            segmentation/     # 分割条件图
            train.json        # 训练数据索引 (JSONL)
                {"source": "source/xxx.png", "condition": "canny/xxx.png", "caption": "..."}

        Args:
            dataset: ControlNet数据集
            output_dir: 输出目录
            format: 格式类型 (目前仅支持 "controlnet")

        Returns:
            输出目录路径
        """
        if not output_dir:
            output_dir = str(self.output_dir / "controlnet_dataset")
        os.makedirs(output_dir, exist_ok=True)

        if format == "controlnet":
            # 创建子目录
            for cond in ["source"] + dataset.conditions:
                (Path(output_dir) / cond).mkdir(parents=True, exist_ok=True)

            # 写入JSONL文件
            jsonl_path = Path(output_dir) / "train.jsonl"
            shard_size = 0

            with open(jsonl_path, "w") as f:
                for pair in dataset.pairs:
                    # 复制/链接图像到标准目录
                    entry = {"caption": pair.caption}

                    # 源图像
                    entry["source"] = f"source/{pair.image_id}.png"
                    if pair.source_image_path and os.path.exists(pair.source_image_path):
                        import shutil
                        dst = Path(output_dir) / "source" / f"{pair.image_id}.png"
                        if not dst.exists():
                            shutil.copy2(pair.source_image_path, str(dst))

                    # 条件图
                    for cond in dataset.conditions:
                        cond_attr = f"{cond}_path"
                        cond_path = getattr(pair, cond_attr, "")
                        if cond_path and os.path.exists(cond_path):
                            dst = Path(output_dir) / cond / f"{pair.image_id}.png"
                            if not dst.exists():
                                shutil.copy2(cond_path, str(dst))
                            entry[cond] = f"{cond}/{pair.image_id}.png"

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            logger.info(f"ControlNet dataset saved to {output_dir} "
                       f"({len(dataset.pairs)} pairs, conditions: {dataset.conditions})")

        return output_dir


# ============================================================================
# Convenience
# ============================================================================

def get_controlnet_processor(output_dir: str = "./data/controlnet") -> ControlNetProcessor:
    """获取ControlNet处理器实例"""
    return ControlNetProcessor(output_dir=output_dir)
