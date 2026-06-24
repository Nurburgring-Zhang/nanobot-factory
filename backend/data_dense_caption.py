"""
NanoBot Factory - 密集描述/Dense Caption生成管线
Dense Caption Generation Pipeline

功能:
- 区域级描述 (Region-level captioning)
- 完整图像描述 (Full image captioning)
- 简短标题级描述 (Short captioning)
- BLIP-3风格描述 (短描述+详细描述+关系)
- ShareGPT4V格式保存

所有caption基于图像属性分析生成，无需下载LLM/VLM模型。
"""

import os, json, logging, io, math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import OrderedDict
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
class RegionCaption:
    """区域级描述"""
    region_id: str
    bbox: Tuple[int, int, int, int]  # (x, y, w, h) 像素坐标
    caption: str
    confidence: float = 1.0
    category: str = ""  # object / person / animal / building / etc.


@dataclass
class DenseCaptionResult:
    """密集描述结果"""
    image_path: str = ""
    full_caption: str = ""
    short_caption: str = ""
    blip3_short: str = ""
    blip3_detailed: str = ""
    blip3_relations: str = ""
    region_captions: List[RegionCaption] = field(default_factory=list)
    width: int = 0
    height: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Dense Caption Generator
# ============================================================================

class DenseCaptionGenerator:
    """
    密集描述生成器

    基于图像属性分析（颜色、纹理、物体检测等）生成自然语言描述。
    不需要LLM/VLM模型，全部使用本地轻量算法。

    支持以下风格:
    - 区域级描述 (Region-level)
    - 完整描述 (Full)
    - 简短标题 (Short)
    - BLIP-3风格 (Short + Detailed + Relations)
    - ShareGPT4V格式保存
    """

    # 颜色名称映射 (RGB)
    COLOR_NAMES = OrderedDict([
        ("red", (255, 0, 0)),
        ("green", (0, 128, 0)),
        ("blue", (0, 0, 255)),
        ("yellow", (255, 255, 0)),
        ("orange", (255, 165, 0)),
        ("purple", (128, 0, 128)),
        ("pink", (255, 192, 203)),
        ("brown", (165, 42, 42)),
        ("gray", (128, 128, 128)),
        ("white", (255, 255, 255)),
        ("black", (0, 0, 0)),
        ("cyan", (0, 255, 255)),
        ("magenta", (255, 0, 255)),
        ("teal", (0, 128, 128)),
        ("navy", (0, 0, 128)),
        ("olive", (128, 128, 0)),
        ("maroon", (128, 0, 0)),
        ("silver", (192, 192, 192)),
    ])

    # 场景类型关键词
    SCENE_KEYWORDS = {
        "indoor": ["room", "building", "wall", "furniture", "window", "door"],
        "outdoor": ["sky", "tree", "road", "mountain", "water", "cloud"],
        "portrait": ["face", "person", "human", "portrait"],
        "landscape": ["nature", "landscape", "scenery", "horizon"],
        "urban": ["city", "street", "building", "architecture"],
        "food": ["food", "dish", "meal", "kitchen"],
        "animal": ["animal", "pet", "wildlife"],
        "night": ["night", "dark", "evening", "dim"],
    }

    def __init__(self):
        pass

    def _load_image(self, image: Union[str, Image.Image]) -> Optional[Image.Image]:
        """加载图像为PIL RGB"""
        try:
            if isinstance(image, str):
                if image.startswith(("http://", "https://")):
                    import requests
                    resp = requests.get(image, timeout=10)
                    return Image.open(io.BytesIO(resp.content)).convert("RGB")
                elif image.startswith("data:image"):
                    import base64
                    data = image.split(",")[1]
                    return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
                else:
                    return Image.open(image).convert("RGB")
            elif isinstance(image, Image.Image):
                return image.convert("RGB")
            elif isinstance(image, bytes):
                return Image.open(io.BytesIO(image)).convert("RGB")
        except Exception as e:
            logger.warning(f"Failed to load image: {e}")
            return None

    def _get_dominant_color(self, img: Image.Image, region: Optional[Tuple] = None) -> str:
        """获取主色调名称"""
        if region:
            x, y, w, h = region
            arr = np.array(img.crop((x, y, x + w, y + h)).resize((32, 32)))
        else:
            arr = np.array(img.resize((32, 32)))
        avg_color = np.mean(arr.reshape(-1, 3), axis=0)

        # 找最近的颜色名称
        min_dist = float("inf")
        best_color = "unknown"
        for name, rgb in self.COLOR_NAMES.items():
            dist = np.sqrt((avg_color[0] - rgb[0])**2 +
                           (avg_color[1] - rgb[1])**2 +
                           (avg_color[2] - rgb[2])**2)
            if dist < min_dist:
                min_dist = dist
                best_color = name
        return best_color

    def _detect_scene_type(self, img: Image.Image) -> str:
        """检测场景类型"""
        arr = np.array(img)
        h, w = arr.shape[:2]
        gray = np.mean(arr, axis=2)

        # 天空检测: 上部区域亮度高且偏蓝
        top_strip = arr[:h//4, :, :]
        top_brightness = float(np.mean(top_strip))
        top_blueness = float(np.mean(top_strip[:,:,2].astype(float) - top_strip[:,:,0].astype(float)))

        # 面部检测
        face_count = 0
        if CV2_AVAILABLE:
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                if os.path.exists(cascade_path):
                    face_cascade = cv2.CascadeClassifier(cascade_path)
                    faces = face_cascade.detectMultiScale(
                        cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), 1.1, 5, minSize=(30, 30)
                    )
                    face_count = len(faces)
            except Exception:
                pass

        # 亮度分析
        avg_brightness = float(np.mean(gray)) / 255.0

        # 颜色多样性
        color_std = float(np.std(arr.reshape(-1, 3), axis=0).mean()) / 255.0

        # 场景分类
        if avg_brightness < 0.25:
            return "night"
        if face_count > 0:
            return "portrait"
        if top_brightness > 180 and top_blueness > 10:
            return "landscape"
        if color_std > 0.3:
            return "urban"
        if top_brightness > 150:
            return "outdoor"
        return "indoor"

    def _detect_objects_simple(self, img: Image.Image) -> List[Dict[str, Any]]:
        """
        简易物体检测 (基于轮廓分析)

        使用OpenCV的轮廓检测来识别图像中的主要物体。
        """
        if not CV2_AVAILABLE:
            return []

        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        objects = []

        # 1. 人脸检测
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if os.path.exists(cascade_path):
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            for (fx, fy, fw, fh) in faces:
                objects.append({
                    "bbox": (fx, fy, fw, fh),
                    "category": "person",
                    "confidence": 0.8,
                    "color": self._get_dominant_color(img, (fx, fy, fw, fh)),
                    "size_ratio": (fw * fh) / (w * h),
                })

        # 2. 轮廓检测 (边缘分割)
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
        edges = cv2.Canny(blurred, 30, 100)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            img_area = w * h
            size_ratio = area / img_area if img_area > 0 else 0

            # 过滤掉太小和太大的区域
            if size_ratio < 0.02 or size_ratio > 0.8:
                continue

            x, y, cw, ch = cv2.boundingRect(cnt)
            # 跳过与人脸重叠的
            is_face = False
            for obj in objects:
                fx, fy, fw, fh = obj["bbox"]
                if (x < fx + fw and x + cw > fx and
                    y < fy + fh and y + ch > fy):
                    is_face = True
                    break
            if is_face:
                continue

            # 宽高比分类
            aspect = cw / max(ch, 1)

            # 颜色分析
            color = self._get_dominant_color(img, (x, y, cw, ch))

            # 粗略分类
            if aspect > 2.0:
                category = "horizontal_object"
            elif aspect < 0.5:
                category = "vertical_object"
            elif cw * ch < w * h * 0.1:
                category = "small_object"
            else:
                category = "object"

            objects.append({
                "bbox": (x, y, cw, ch),
                "category": category,
                "confidence": 0.5,
                "color": color,
                "size_ratio": size_ratio,
            })

        return objects

    # ========================================================================
    # 区域级描述
    # ========================================================================

    def generate_region_captions(self, image: Union[str, Image.Image],
                                  regions: Optional[List[Tuple]] = None) -> List[RegionCaption]:
        """
        区域级描述

        对图像的指定区域或自动检测区域生成自然语言描述。

        Args:
            image: 输入图像
            regions: 指定区域 [(x, y, w, h), ...]，None则自动检测

        Returns:
            RegionCaption 列表
        """
        img = self._load_image(image)
        if img is None:
            return []

        if regions is None:
            # 自动检测区域
            objects = self._detect_objects_simple(img)
            regions = [(o["bbox"][0], o["bbox"][1], o["bbox"][2], o["bbox"][3])
                       for o in objects]

        captions = []
        for i, (x, y, w, h) in enumerate(regions):
            # 裁剪区域
            region_img = img.crop((x, y, x + w, y + h))

            # 分析区域属性
            color = self._get_dominant_color(img, (x, y, w, h))
            arr = np.array(region_img)
            gray = np.mean(arr, axis=2)

            brightness = float(np.mean(gray)) / 255.0
            contrast = float(np.std(gray)) / 127.5

            # 分类和生成描述
            aspect = w / max(h, 1)

            # 检测是否为人脸
            is_face = False
            category = "object"
            if CV2_AVAILABLE:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                if os.path.exists(cascade_path):
                    cascade = cv2.CascadeClassifier(cascade_path)
                    faces = cascade.detectMultiScale(
                        cv2.cvtColor(np.array(region_img), cv2.COLOR_RGB2GRAY),
                        1.1, 5, minSize=(20, 20)
                    )
                    if len(faces) > 0:
                        is_face = True
                        category = "person"

            if is_face:
                caption_text = f"A person's face with {color} skin tone"
                if brightness > 0.7:
                    caption_text += ", well-lit"
                elif brightness < 0.3:
                    caption_text += ", in shadow"
                if contrast > 0.6:
                    caption_text += ", high contrast"
            elif aspect > 1.5:
                caption_text = f"A {color} wide {category} spanning across the image"
            elif aspect < 0.67:
                caption_text = f"A {color} tall {category}"
            else:
                size_desc = "small" if w * h < img.width * img.height * 0.05 else "medium"
                caption_text = f"A {size_desc} {color} {category}"

            captions.append(RegionCaption(
                region_id=f"region_{i:04d}",
                bbox=(x, y, w, h),
                caption=caption_text,
                confidence=0.6,
                category=category,
            ))

        return captions

    # ========================================================================
    # 完整图像描述
    # ========================================================================

    def generate_full_caption(self, image: Union[str, Image.Image]) -> str:
        """
        完整图像描述

        生成详细的自然语言描述，涵盖：
        - 场景类型
        - 主要物体/人物
        - 颜色和光照
        - 空间布局
        - 整体氛围
        """
        img = self._load_image(image)
        if img is None:
            return ""

        w, h = img.size
        arr = np.array(img)
        gray = np.mean(arr, axis=2)
        avg_brightness = float(np.mean(gray)) / 255.0

        # 1. 场景类型
        scene = self._detect_scene_type(img)
        scene_descriptions = {
            "indoor": "an indoor scene",
            "outdoor": "an outdoor scene",
            "portrait": "a portrait photograph",
            "landscape": "a landscape view",
            "urban": "an urban scene",
            "food": "a food scene",
            "animal": "an animal scene",
            "night": "a night scene",
        }
        scene_desc = scene_descriptions.get(scene, "a scene")

        # 2. 主色调
        main_color = self._get_dominant_color(img)

        # 3. 亮度和光照
        if avg_brightness > 0.7:
            lighting = "brightly lit"
        elif avg_brightness > 0.4:
            lighting = "moderately lit"
        else:
            lighting = "dimly lit"

        # 4. 检测主要物体
        objects = self._detect_objects_simple(img)
        face_count = sum(1 for o in objects if o["category"] == "person")
        other_objects = [o for o in objects if o["category"] != "person"]

        # 5. 宽高比
        aspect = w / max(h, 1)
        if aspect > 1.3:
            format_desc = "landscape orientation"
        elif aspect < 0.77:
            format_desc = "portrait orientation"
        else:
            format_desc = "square format"

        # 构建描述
        parts = [f"This image shows {scene_desc} in {format_desc}."]
        parts.append(f"The overall tone is {main_color} and {lighting}.")

        if face_count > 0:
            parts.append(f"There {'is' if face_count == 1 else 'are'} "
                        f"{face_count} person{'s' if face_count != 1 else ''} in the frame.")

        if other_objects:
            colors = [o["color"] for o in other_objects[:3]]
            parts.append(f"Notable elements include {', '.join(colors)} objects "
                        f"distributed across the composition.")

        # 对比度和纹理
        contrast = float(np.std(gray)) / 127.5
        if contrast > 0.6:
            parts.append("The image has strong contrast and texture.")
        elif contrast < 0.3:
            parts.append("The image has a soft, uniform appearance.")

        parts.append(f"The image dimensions are {w}x{h} pixels.")

        return " ".join(parts)

    # ========================================================================
    # 简短标题级描述
    # ========================================================================

    def generate_short_caption(self, image: Union[str, Image.Image]) -> str:
        """
        简短标题级描述 (一行, ≤20词)

        用于数据集的简短标题。
        """
        img = self._load_image(image)
        if img is None:
            return ""

        scene = self._detect_scene_type(img)
        main_color = self._get_dominant_color(img)
        arr = np.array(img)
        gray = np.mean(arr, axis=2)
        avg_brightness = float(np.mean(gray)) / 255.0

        scene_labels = {
            "indoor": "indoor",
            "outdoor": "outdoor",
            "portrait": "portrait",
            "landscape": "landscape",
            "urban": "urban",
            "night": "night",
            "food": "food",
            "animal": "animal",
        }
        scene_tag = scene_labels.get(scene, "scene")

        # 检测物体
        objects = self._detect_objects_simple(img)
        face_count = sum(1 for o in objects if o["category"] == "person")

        if face_count > 0:
            subject = f"a person"
        elif objects:
            subject = f"a {objects[0]['color']} {objects[0]['category']}"
        else:
            subject = f"a {main_color} scene"

        # 亮度描述
        if avg_brightness > 0.7:
            light_desc = "bright"
        elif avg_brightness > 0.4:
            light_desc = "well-lit"
        else:
            light_desc = "dark"

        return f"A {light_desc} {scene_tag} photo of {subject} with {main_color} tones"

    # ========================================================================
    # BLIP-3风格描述
    # ========================================================================

    def generate_blip3_style(self, image: Union[str, Image.Image]) -> Dict[str, str]:
        """
        BLIP-3风格描述

        生成三种级别的描述:
        - short_caption: 简短标题 (一句话)
        - detailed_caption: 详细描述 (多句话, 涵盖颜色/形状/位置)
        - relations: 物体间关系描述

        Returns:
            {"short_caption": str, "detailed_caption": str, "relations": str}
        """
        img = self._load_image(image)
        if img is None:
            return {"short_caption": "", "detailed_caption": "", "relations": ""}

        short = self.generate_short_caption(img)
        full = self.generate_full_caption(img)

        # 关系描述
        objects = self._detect_objects_simple(img)
        relations_parts = []

        for i, obj1 in enumerate(objects):
            for j, obj2 in enumerate(objects[i+1:], i+1):
                x1, y1, w1, h1 = obj1["bbox"]
                x2, y2, w2, h2 = obj2["bbox"]

                # 计算空间关系
                cx1, cy1 = x1 + w1/2, y1 + h1/2
                cx2, cy2 = x2 + w2/2, y2 + h2/2

                dx = cx2 - cx1
                dy = cy2 - cy1

                # 关系描述
                cat1 = obj1["category"]
                cat2 = obj2["category"]

                if abs(dx) < w1 * 0.5 and abs(dy) < h1 * 0.5:
                    relations_parts.append(
                        f"The {cat1} overlaps with the {cat2}")
                elif abs(dy) < h1 * 0.5:
                    if dx > 0:
                        relations_parts.append(
                            f"The {cat1} is to the left of the {cat2}")
                    else:
                        relations_parts.append(
                            f"The {cat1} is to the right of the {cat2}")
                elif abs(dx) < w1 * 0.5:
                    if dy > 0:
                        relations_parts.append(
                            f"The {cat1} is above the {cat2}")
                    else:
                        relations_parts.append(
                            f"The {cat1} is below the {cat2}")
                else:
                    if dy > 0 and dx > 0:
                        relations_parts.append(
                            f"The {cat1} is in the upper-left relative to the {cat2}")
                    elif dy > 0 and dx < 0:
                        relations_parts.append(
                            f"The {cat1} is in the upper-right relative to the {cat2}")
                    elif dy < 0 and dx > 0:
                        relations_parts.append(
                            f"The {cat1} is in the lower-left relative to the {cat2}")
                    else:
                        relations_parts.append(
                            f"The {cat1} is in the lower-right relative to the {cat2}")

        if not relations_parts:
            relations_parts.append(
                f"The image contains {len(objects)} main elements "
                f"in a {self._get_dominant_color(img)} composition."
            )

        relations = " ".join(relations_parts[:3])  # 最多3个关系

        return {
            "short_caption": short,
            "detailed_caption": full,
            "relations": relations,
        }

    # ========================================================================
    # 保存为ShareGPT4V格式
    # ========================================================================

    def save_sharegpt4v_format(
        self,
        image: Union[str, Image.Image],
        captions: Optional[Dict[str, str]] = None,
        output_dir: str = "./data/sharegpt4v",
        image_id: str = ""
    ) -> Dict[str, Any]:
        """
        保存为ShareGPT4V标准格式

        ShareGPT4V格式:
        [
            {
                "id": "image_id",
                "image": "path/to/image.jpg",
                "conversations": [
                    {"from": "human", "value": "<image>\\nDescribe this image in detail."},
                    {"from": "gpt", "value": "detailed description..."},
                    {"from": "human", "value": "What is in the image?"},
                    {"from": "gpt", "value": "short caption..."},
                ]
            }
        ]

        Args:
            image: 输入图像
            captions: 可选自定义描述字典
            output_dir: 输出目录
            image_id: 图像ID

        Returns:
            ShareGPT4V格式的JSON条目
        """
        img = self._load_image(image)
        if img is None:
            return {}

        if not image_id:
            import hashlib, time
            image_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]

        if captions is None:
            blip3 = self.generate_blip3_style(img)
            captions = {
                "detailed": blip3.get("detailed_caption", self.generate_full_caption(img)),
                "short": blip3.get("short_caption", self.generate_short_caption(img)),
                "relations": blip3.get("relations", ""),
            }

        # 保存图像
        os.makedirs(output_dir, exist_ok=True)
        img_filename = f"{image_id}.jpg"
        img_path = os.path.join(output_dir, img_filename)
        img.save(img_path, quality=95)

        # 构建ShareGPT4V对话格式
        entry = {
            "id": image_id,
            "image": img_filename,
            "conversations": [
                {
                    "from": "human",
                    "value": "<image>\nDescribe this image in detail."
                },
                {
                    "from": "gpt",
                    "value": captions.get("detailed", "")
                },
                {
                    "from": "human",
                    "value": "Give a short caption for this image."
                },
                {
                    "from": "gpt",
                    "value": captions.get("short", "")
                },
                {
                    "from": "human",
                    "value": "What objects are in this image and how are they related?"
                },
                {
                    "from": "gpt",
                    "value": captions.get("relations", "The image shows a scene with various elements.")
                },
            ]
        }

        # 写入JSON文件
        json_path = os.path.join(output_dir, f"{image_id}.json")
        with open(json_path, "w") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved ShareGPT4V format: {json_path}")

        return entry

    # ========================================================================
    # 批量保存
    # ========================================================================

    def batch_save_sharegpt4v(
        self,
        images: List[Union[str, Image.Image]],
        output_dir: str = "./data/sharegpt4v",
        prefix: str = "dataset"
    ) -> str:
        """
        批量保存为ShareGPT4V格式数据集

        Args:
            images: 图像列表
            output_dir: 输出目录
            prefix: 数据集名称前缀

        Returns:
            数据集JSON路径
        """
        os.makedirs(output_dir, exist_ok=True)

        all_entries = []
        for i, img in enumerate(images):
            try:
                entry = self.save_sharegpt4v_format(
                    img, output_dir=output_dir, image_id=f"{prefix}_{i:06d}"
                )
                if entry:
                    all_entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to process image {i}: {e}")

        # 写完整数据集JSON
        dataset_path = os.path.join(output_dir, "sharegpt4v_dataset.json")
        with open(dataset_path, "w") as f:
            json.dump(all_entries, f, indent=2, ensure_ascii=False)

        logger.info(f"ShareGPT4V dataset saved: {dataset_path} ({len(all_entries)} entries)")
        return dataset_path


# ============================================================================
# Convenience
# ============================================================================

def get_dense_caption_generator() -> DenseCaptionGenerator:
    """获取密集描述生成器实例"""
    return DenseCaptionGenerator()
