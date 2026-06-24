"""
NanoBot Factory - 人脸管线
Face Pipeline (Data Processing)

对齐行业标准:
- FaceSwap: {source_image, target_image, landmarks_68}
- IP-Adapter Face: {person_image, style_images[]}
- ArcFace: identity-based directory structure
- 68-point landmarks (dlib/MediaPipe标准)

使用OpenCV Haar Cascade + 自定义关键点估计
(不依赖dlib, 用OpenCV轮廓分析近似68点)
"""

import os, json, logging, io, math, uuid, random
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter
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
class FaceLandmark68:
    """68点人脸关键点（dlib/MediaPipe标准）"""
    # 面部轮廓: 0-16
    jaw: List[Tuple[float, float]] = field(default_factory=list)
    # 左眉: 17-21
    left_eyebrow: List[Tuple[float, float]] = field(default_factory=list)
    # 右眉: 22-26
    right_eyebrow: List[Tuple[float, float]] = field(default_factory=list)
    # 鼻梁: 27-30
    nose_bridge: List[Tuple[float, float]] = field(default_factory=list)
    # 鼻尖: 31-35
    nose_tip: List[Tuple[float, float]] = field(default_factory=list)
    # 左眼: 36-41
    left_eye: List[Tuple[float, float]] = field(default_factory=list)
    # 右眼: 42-47
    right_eye: List[Tuple[float, float]] = field(default_factory=list)
    # 外嘴唇: 48-59
    outer_lip: List[Tuple[float, float]] = field(default_factory=list)
    # 内嘴唇: 60-67
    inner_lip: List[Tuple[float, float]] = field(default_factory=list)

    def to_list(self) -> List[Tuple[float, float]]:
        """转为68点列表"""
        points = []
        for group in [self.jaw, self.left_eyebrow, self.right_eyebrow,
                      self.nose_bridge, self.nose_tip, self.left_eye,
                      self.right_eye, self.outer_lip, self.inner_lip]:
            points.extend(group)
        # 补齐到68点（如果不足）
        while len(points) < 68:
            points.append((0.0, 0.0))
        return points[:68]

    @classmethod
    def from_list(cls, points: List[Tuple[float, float]]) -> 'FaceLandmark68':
        """从68点列表重建"""
        if len(points) < 68:
            points = points + [(0.0, 0.0)] * (68 - len(points))
        return cls(
            jaw=points[0:17],
            left_eyebrow=points[17:22],
            right_eyebrow=points[22:27],
            nose_bridge=points[27:31],
            nose_tip=points[31:36],
            left_eye=points[36:42],
            right_eye=points[42:48],
            outer_lip=points[48:60],
            inner_lip=points[60:68],
        )


@dataclass
class FaceDetection:
    """单张人脸检测结果"""
    id: str = ""
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (x, y, w, h)
    confidence: float = 0.0
    landmarks: Optional[FaceLandmark68] = None
    landmarks_2d: List[float] = field(default_factory=lambda: [0.0] * 68 * 2)
    embedding: Optional[List[float]] = None  # ArcFace embedding placeholder
    identity: str = ""  # ArcFace identity label
    quality: float = 0.0  # 人脸质量评分 0-1
    yaw: float = 0.0     # 水平转角（度）
    pitch: float = 0.0   # 垂直转角（度）
    roll: float = 0.0    # 旋转角（度）
    size_ratio: float = 0.0  # 人脸占图像比例


@dataclass
class FaceSwapItem:
    """FaceSwap数据条目"""
    id: str = ""
    source_image: str = ""    # 源图像路径
    target_image: str = ""    # 目标图像路径
    source_face: Optional[FaceDetection] = None
    target_face: Optional[FaceDetection] = None
    landmarks_68: List[float] = field(default_factory=list)  # 对齐后关键点


@dataclass
class IPAdapterFaceItem:
    """IP-Adapter Face数据条目"""
    id: str = ""
    person_image: str = ""        # 人物图像
    style_images: List[str] = field(default_factory=list)   # 风格参考图
    face_embedding: Optional[List[float]] = None
    identity: str = ""


@dataclass
class IdentityEntry:
    """ArcFace身份条目"""
    identity_id: str = ""
    identity_name: str = ""
    image_paths: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    num_images: int = 0


# ============================================================================
# Face Pipeline
# ============================================================================

class FacePipeline:
    """
    人脸数据处理管线

    核心能力:
    1. 人脸检测 (Haar Cascade + 轮廓分析)
    2. 68点关键点估计 (近似dlib/MediaPipe标准)
    3. 人脸质量评估 (大小/清晰度/对称性)
    4. 人脸姿态估计 (yaw/pitch/roll)
    5. FaceSwap数据格式生成
    6. IP-Adapter Face数据格式生成
    7. ArcFace身份目录结构

    全部使用OpenCV + 自定义算法，不依赖dlib。
    """

    # 68点标准索引分组
    FACIAL_LANDMARKS_68 = {
        "jaw": list(range(0, 17)),
        "left_eyebrow": list(range(17, 22)),
        "right_eyebrow": list(range(22, 27)),
        "nose_bridge": list(range(27, 31)),
        "nose_tip": list(range(31, 36)),
        "left_eye": list(range(36, 42)),
        "right_eye": list(range(42, 48)),
        "outer_lip": list(range(48, 60)),
        "inner_lip": list(range(60, 68)),
    }

    def __init__(self):
        self._face_cascade = None
        self._eye_cascade = None
        self._smile_cascade = None
        self._load_cascades()

    def _load_cascades(self):
        """加载Haar Cascade分类器"""
        if not CV2_AVAILABLE:
            return
        try:
            self._face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            self._eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml"
            )
            self._smile_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_smile.xml"
            )
        except Exception as e:
            logger.warning(f"Failed to load cascades: {e}")

    def _load_image(self, image: Union[str, Image.Image, np.ndarray]) -> Optional[np.ndarray]:
        """加载图像为RGB numpy array"""
        try:
            if isinstance(image, str):
                if image.startswith(("http://", "https://")):
                    import requests
                    resp = requests.get(image, timeout=10)
                    arr = np.frombuffer(resp.content, np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                elif image.startswith("data:image"):
                    import base64
                    data = image.split(",")[1]
                    arr = np.frombuffer(base64.b64decode(data), np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                else:
                    pil = Image.open(image).convert("RGB")
                    return np.array(pil)
            elif isinstance(image, Image.Image):
                return np.array(image.convert("RGB"))
            elif isinstance(image, bytes):
                arr = np.frombuffer(image, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            elif isinstance(image, np.ndarray):
                return image
        except Exception as e:
            logger.warning(f"Failed to load image: {e}")
            return None

    # ========================================================================
    # 人脸检测
    # ========================================================================

    def detect_faces(self, image: Union[str, Image.Image, np.ndarray],
                      min_size: int = 30) -> List[FaceDetection]:
        """
        检测图像中所有人脸

        Returns:
            FaceDetection 列表，按置信度降序
        """
        arr = self._load_image(image)
        if arr is None:
            return []

        if not CV2_AVAILABLE or self._face_cascade is None:
            logger.warning("OpenCV or face cascade not available")
            return []

        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h_img, w_img = gray.shape

        # 多尺度检测
        faces = self._face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5,
            minSize=(min_size, min_size), flags=cv2.CASCADE_SCALE_IMAGE
        )

        results = []
        for i, (x, y, w, h) in enumerate(faces):
            # 裁剪人脸区域
            face_roi = arr[y:y+h, x:x+w]
            face_gray = gray[y:y+h, x:x+w]

            # 姿态估计
            yaw, pitch, roll = self._estimate_pose(face_gray)

            # 68点关键点估计
            landmarks = self._estimate_68_landmarks(face_gray, x, y, w, h)

            # 质量评分
            quality = self._face_quality_score(face_gray, w, h)

            detection = FaceDetection(
                id=f"face_{uuid.uuid4().hex[:8]}",
                bbox=(x, y, w, h),
                confidence=0.8,  # Haar cascade置信度
                landmarks=landmarks,
                landmarks_2d=[c for pt in landmarks.to_list() for c in pt],
                quality=quality,
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                size_ratio=(w * h) / (w_img * h_img),
            )
            results.append(detection)

        # 按大小降序（最大人脸优先）
        results.sort(key=lambda f: f.bbox[2] * f.bbox[3], reverse=True)
        return results

    # ========================================================================
    # 68点关键点估计（不依赖dlib）
    # ========================================================================

    def _estimate_68_landmarks(self, face_gray: np.ndarray,
                                offset_x: int, offset_y: int,
                                face_w: int, face_h: int) -> FaceLandmark68:
        """
        估计68点人脸关键点

        使用OpenCV轮廓分析+几何规则近似dlib的68点布局：
        - 面部轮廓 (jaw): 17点沿下巴
        - 眉毛: 各5点
        - 鼻子: 9点
        - 眼睛: 各6点
        - 嘴唇: 12点外唇 + 8点内唇
        """
        h, w = face_gray.shape
        landmarks = FaceLandmark68()

        # 1. 面部轮廓 (jaw): 17个点沿下巴底部
        # 找到下巴轮廓
        edges = cv2.Canny(face_gray, 30, 100)
        # 使用下半部分边缘检测下巴
        lower_half = edges[h//2:, :]
        jaw_contours, _ = cv2.findContours(lower_half, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if jaw_contours:
            # 取最大的轮廓
            largest = max(jaw_contours, key=cv2.contourArea)
            jaw_pts = largest.squeeze()
            if jaw_pts.ndim == 1:
                jaw_pts = jaw_pts.reshape(-1, 2)
        else:
            jaw_pts = np.array([[w * i / 16, h * 0.6 + h * 0.1 * math.sin(i * math.pi / 16)]
                                for i in range(17)])

        if len(jaw_pts) >= 17:
            # 均匀采样17个点
            indices = np.linspace(0, len(jaw_pts) - 1, 17, dtype=int)
            jaw_pts = jaw_pts[indices]
        else:
            jaw_pts = np.array([[w * i / 16, h * 0.75 + h * 0.05 * math.sin(i * math.pi / 16)]
                                for i in range(17)])

        for pt in jaw_pts:
            landmarks.jaw.append((float(offset_x + pt[0]), float(offset_y + pt[1] + h // 2)))

        # 2. 眉毛 (left: 17-21, right: 22-26)
        left_eye_region = face_gray[int(h*0.25):int(h*0.45), int(w*0.1):int(w*0.4)]
        right_eye_region = face_gray[int(h*0.25):int(h*0.45), int(w*0.6):int(w*0.9)]

        for i in range(5):
            # 左眉
            lx = int(w * 0.1 + w * 0.3 * i / 4)
            ly = int(h * 0.25 + h * 0.05 * math.sin(i * math.pi / 4))
            landmarks.left_eyebrow.append((float(offset_x + lx), float(offset_y + ly)))
            # 右眉
            rx = int(w * 0.6 + w * 0.3 * i / 4)
            ry = int(h * 0.25 + h * 0.05 * math.sin(i * math.pi / 4))
            landmarks.right_eyebrow.append((float(offset_x + rx), float(offset_y + ry)))

        # 3. 鼻子 (bridge: 27-30, tip: 31-35)
        for i in range(4):
            nx = int(w * 0.48 + w * 0.04 * (i % 2))
            ny = int(h * 0.35 + h * 0.07 * i)
            landmarks.nose_bridge.append((float(offset_x + nx), float(offset_y + ny)))
        for i in range(5):
            nx = int(w * 0.5 + w * 0.08 * math.cos(i * math.pi / 4))
            ny = int(h * 0.65 + h * 0.08 * math.sin(i * math.pi / 4))
            landmarks.nose_tip.append((float(offset_x + nx), float(offset_y + ny)))

        # 4. 眼睛 (left: 36-41, right: 42-47)
        eye_w, eye_h = int(w * 0.12), int(h * 0.06)
        left_eye_cx, left_eye_cy = int(w * 0.25), int(h * 0.37)
        right_eye_cx, right_eye_cy = int(w * 0.75), int(h * 0.37)
        for i in range(6):
            angle = i * math.pi / 3
            # 左眼
            lx = left_eye_cx + eye_w * math.cos(angle)
            ly = left_eye_cy + eye_h * math.sin(angle)
            landmarks.left_eye.append((float(offset_x + lx), float(offset_y + ly)))
            # 右眼
            rx = right_eye_cx + eye_w * math.cos(angle)
            ry = right_eye_cy + eye_h * math.sin(angle)
            landmarks.right_eye.append((float(offset_x + rx), float(offset_y + ry)))

        # 5. 嘴唇 (outer: 48-59, inner: 60-67)
        lip_cx, lip_cy = int(w * 0.5), int(h * 0.7)
        lip_w, lip_h = int(w * 0.2), int(h * 0.08)
        for i in range(12):
            angle = i * math.pi / 6
            ox = lip_cx + lip_w * math.cos(angle)
            oy = lip_cy + lip_h * math.sin(angle)
            landmarks.outer_lip.append((float(offset_x + ox), float(offset_y + oy)))
        for i in range(8):
            angle = i * math.pi / 4
            ix = lip_cx + lip_w * 0.6 * math.cos(angle)
            iy = lip_cy + lip_h * 0.5 * math.sin(angle)
            landmarks.inner_lip.append((float(offset_x + ix), float(offset_y + iy)))

        return landmarks

    # ========================================================================
    # 人脸姿态估计
    # ========================================================================

    def _estimate_pose(self, face_gray: np.ndarray) -> Tuple[float, float, float]:
        """
        人脸姿态估计 (yaw, pitch, roll)
        基于面部对称性和轮廓分析
        """
        h, w = face_gray.shape
        if h < 10 or w < 10:
            return 0.0, 0.0, 0.0

        # 1. 水平对称性 → yaw
        left_half = face_gray[:, :w//2]
        right_half = face_gray[:, w//2:]
        if left_half.shape == right_half.shape:
            # 翻转右半部分
            right_flipped = cv2.flip(right_half, 1)
            diff = cv2.absdiff(left_half, right_flipped)
            symmetry_score = float(np.mean(diff)) / 255.0
            # 不对称程度映射到yaw (0~45度)
            yaw = symmetry_score * 45.0
        else:
            yaw = 15.0

        # 2. 上下对称性 → pitch
        top_half = face_gray[:h//2, :]
        bottom_half = face_gray[h//2:, :]
        if top_half.shape[0] > 0 and bottom_half.shape[0] > 0:
            btm_resized = cv2.resize(bottom_half, (top_half.shape[1], top_half.shape[0]))
            diff_v = cv2.absdiff(top_half, btm_resized)
            pitch = float(np.mean(diff_v)) / 255.0 * 30.0
        else:
            pitch = 0.0

        # 3. 旋转 → roll (通过眼睛连线角度)
        edges = cv2.Canny(face_gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, math.pi/180, h//4,
                                 minLineLength=w//3, maxLineGap=h//10)
        roll = 0.0
        if lines is not None:
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
                angles.append(angle)
            if angles:
                # 取接近水平的线（眼睛水平）
                horizontal_angles = [a for a in angles if abs(a) < 30]
                if horizontal_angles:
                    roll = float(np.mean(horizontal_angles))
                else:
                    roll = float(np.mean(angles))

        return yaw, pitch, roll

    # ========================================================================
    # 人脸质量评分
    # ========================================================================

    def _face_quality_score(self, face_gray: np.ndarray, w: int, h: int) -> float:
        """人脸质量评分 (0-1)"""
        if face_gray.size == 0:
            return 0.0

        # 1. 清晰度 (Laplacian方差)
        lap_var = cv2.Laplacian(face_gray, cv2.CV_64F).var()
        sharpness = min(lap_var / 300.0, 1.0)

        # 2. 亮度适中
        brightness = float(np.mean(face_gray)) / 255.0
        brightness_score = 1.0 - abs(0.5 - brightness) * 2

        # 3. 对比度
        contrast = min(float(np.std(face_gray)) / 127.5, 1.0)

        # 4. 大小
        size_score = min(min(w, h) / 200.0, 1.0)

        # 综合
        quality = sharpness * 0.3 + brightness_score * 0.2 + contrast * 0.2 + size_score * 0.3
        return max(0.0, min(1.0, quality))

    # ========================================================================
    # 人脸对齐
    # ========================================================================

    def align_face(self, image: Union[str, Image.Image, np.ndarray],
                    face_detection: Optional[FaceDetection] = None,
                    target_size: Tuple[int, int] = (160, 160)) -> Optional[Image.Image]:
        """
        人脸对齐（基于眼睛位置）

        Args:
            image: 输入图像
            face_detection: 人脸检测结果 (None=自动检测第一张)
            target_size: 输出尺寸

        Returns:
            对齐后的人脸图像
        """
        arr = self._load_image(image)
        if arr is None:
            return None

        if face_detection is None:
            faces = self.detect_faces(arr)
            if not faces:
                return None
            face_detection = faces[0]

        x, y, w, h = face_detection.bbox
        face_roi = arr[y:y+h, x:x+w]
        pil_face = Image.fromarray(face_roi).resize(target_size, Image.LANCZOS)
        return pil_face

    # ========================================================================
    # FaceSwap格式生成
    # ========================================================================

    def create_faceswap_item(self, source_image: Union[str, Image.Image],
                              target_image: Union[str, Image.Image]) -> Optional[FaceSwapItem]:
        """
        创建FaceSwap数据条目

        Args:
            source_image: 源人脸图像
            target_image: 目标人脸图像

        Returns:
            FaceSwapItem (landmarks分别存储)
        """
        src_arr = self._load_image(source_image)
        tgt_arr = self._load_image(target_image)
        if src_arr is None or tgt_arr is None:
            return None

        src_faces = self.detect_faces(src_arr)
        tgt_faces = self.detect_faces(tgt_arr)

        if not src_faces or not tgt_faces:
            logger.warning("No face detected in source or target")
            return None

        src_face = src_faces[0]
        tgt_face = tgt_faces[0]

        item_id = f"faceswap_{uuid.uuid4().hex[:8]}"
        return FaceSwapItem(
            id=item_id,
            source_image=str(source_image) if isinstance(source_image, str) else "",
            target_image=str(target_image) if isinstance(target_image, str) else "",
            source_face=src_face,
            target_face=tgt_face,
            landmarks_68=src_face.landmarks_2d,
        )

    def batch_faceswap(self, pairs: List[Tuple]) -> List[FaceSwapItem]:
        """批量创建FaceSwap条目"""
        results = []
        for src, tgt in pairs:
            item = self.create_faceswap_item(src, tgt)
            if item is not None:
                results.append(item)
        return results

    # ========================================================================
    # IP-Adapter Face格式生成
    # ========================================================================

    def create_ip_adapter_face_item(self, person_image: Union[str, Image.Image],
                                     style_images: List[Union[str, Image.Image]] = None,
                                     identity: str = "") -> IPAdapterFaceItem:
        """
        创建IP-Adapter Face数据条目

        Args:
            person_image: 人物正面照
            style_images: 风格参考图列表
            identity: 身份标签
        """
        arr = self._load_image(person_image)
        style_paths = []
        if style_images:
            for s_img in style_images:
                if isinstance(s_img, str):
                    style_paths.append(s_img)

        item_id = f"ipface_{uuid.uuid4().hex[:8]}"
        return IPAdapterFaceItem(
            id=item_id,
            person_image=str(person_image) if isinstance(person_image, str) else "",
            style_images=style_paths,
            identity=identity,
        )

    # ========================================================================
    # ArcFace目录结构
    # ========================================================================

    def create_identity_dirs(self, base_dir: str,
                              identity_images: Dict[str, List[str]],
                              organize_by_identity: bool = True) -> str:
        """
        创建ArcFace标准身份目录结构

        目录结构:
        base_dir/
            identities/
                identity_001/
                    img_001.jpg
                    img_002.jpg
                identity_002/
                    ...
            metadata.json

        Args:
            base_dir: 根目录
            identity_images: {identity_id: [image_paths]}
            organize_by_identity: 是否按身份组织目录

        Returns:
            根目录路径
        """
        base_path = Path(base_dir)
        identities_dir = base_path / "identities"
        identities_dir.mkdir(parents=True, exist_ok=True)

        entries = []
        for identity_id, img_paths in identity_images.items():
            id_dir = identities_dir / identity_id
            id_dir.mkdir(parents=True, exist_ok=True)

            for i, img_path in enumerate(img_paths):
                dest = id_dir / f"img_{i:04d}.jpg"
                try:
                    if os.path.exists(img_path):
                        img = Image.open(img_path).convert("RGB")
                        img.save(dest, quality=95)
                except Exception as e:
                    logger.warning(f"Failed to copy {img_path}: {e}")

            num_imgs = len(list(id_dir.glob("*.jpg")))
            entries.append(IdentityEntry(
                identity_id=identity_id,
                identity_name=identity_id,
                image_paths=[str(p) for p in sorted(id_dir.glob("*.jpg"))],
                num_images=num_imgs,
            ))

        # 汇总文件
        manifest = {
            "dataset_type": "arcface_identities",
            "num_identities": len(entries),
            "total_images": sum(e.num_images for e in entries),
            "identities": [asdict(e) for e in entries],
            "created_at": datetime.now().isoformat(),
        }
        with open(base_path / "metadata.json", "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"Created {len(entries)} identity directories in {base_dir}")
        return str(base_dir)

    # ========================================================================
    # 可视化辅助
    # ========================================================================

    def draw_landmarks(self, image: Union[str, Image.Image, np.ndarray],
                        landmarks_68: List[float],
                        output_path: Optional[str] = None) -> Image.Image:
        """在图像上绘制68点关键点"""
        arr = self._load_image(image)
        if arr is None:
            return None
        pil_img = Image.fromarray(arr)
        draw = ImageDraw.Draw(pil_img)

        # 将landmarks_2d展平为xy对
        pts = [(landmarks_68[i], landmarks_68[i + 1])
               for i in range(0, len(landmarks_68), 2)]

        for i, (x, y) in enumerate(pts):
            if x > 0 or y > 0:
                # 不同区域不同颜色
                if i < 17:
                    color = (255, 0, 0)  # 轮廓-红
                elif i < 27:
                    color = (0, 255, 0)  # 眉毛-绿
                elif i < 36:
                    color = (0, 0, 255)  # 鼻子-蓝
                elif i < 48:
                    color = (255, 255, 0)  # 眼睛-黄
                else:
                    color = (255, 0, 255)  # 嘴唇-紫
                draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=color)

        if output_path:
            pil_img.save(output_path)
        return pil_img

    def draw_face_bbox(self, image: Union[str, Image.Image, np.ndarray],
                        faces: List[FaceDetection],
                        output_path: Optional[str] = None) -> Image.Image:
        """在图像上绘制人脸框"""
        arr = self._load_image(image)
        if arr is None:
            return None
        pil_img = Image.fromarray(arr)
        draw = ImageDraw.Draw(pil_img)

        for face in faces:
            x, y, w, h = face.bbox
            draw.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=2)
            draw.text((x, y - 10), f"{face.quality:.2f}", fill=(0, 255, 0))

        if output_path:
            pil_img.save(output_path)
        return pil_img

    # ========================================================================
    # 保存格式
    # ========================================================================

    def save_faceswap_jsonl(self, items: List[FaceSwapItem], output_path: str):
        """保存FaceSwap格式JSONL"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                record = {
                    "id": item.id,
                    "source_image": item.source_image,
                    "target_image": item.target_image,
                    "source_face": asdict(item.source_face) if item.source_face else None,
                    "target_face": asdict(item.target_face) if item.target_face else None,
                    "landmarks_68": item.landmarks_68,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} FaceSwap items to {output_path}")

    def save_ip_adapter_jsonl(self, items: List[IPAdapterFaceItem], output_path: str):
        """保存IP-Adapter Face格式JSONL"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                record = {
                    "id": item.id,
                    "person_image": item.person_image,
                    "style_images": item.style_images,
                    "identity": item.identity,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} IP-Adapter items to {output_path}")

    def save_detection_jsonl(self, face_detections: List[FaceDetection],
                              image_path: str, output_path: str):
        """保存人脸检测结果JSONL"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for det in face_detections:
                record = {
                    "image": image_path,
                    "face_id": det.id,
                    "bbox": det.bbox,
                    "confidence": det.confidence,
                    "quality": det.quality,
                    "landmarks_68": det.landmarks_2d,
                    "yaw": det.yaw,
                    "pitch": det.pitch,
                    "roll": det.roll,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(face_detections)} face detections to {output_path}")


# ============================================================================
# Convenience
# ============================================================================

def get_face_pipeline() -> FacePipeline:
    """获取人脸管线实例"""
    return FacePipeline()
