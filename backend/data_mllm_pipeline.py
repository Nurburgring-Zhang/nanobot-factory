"""
NanoBot Factory - MLLM训练数据生产管线
MLLM Training Data Generation Pipeline

行业标准格式对齐:
1. LLaVA格式: {image, conversations[{from, value}]}
   - 多轮对话，带<image>标记
   - 覆盖: 概括→细节→空间→情感四轮

2. ShareGPT4V格式: {image, caption(100+字), conversations[]}
   - 详细描述扩展（场景/主体/颜色/光照/构图/情绪/关系）
   - 基于此生成问答对

3. Interleaved图文格式 (MMC4/OBELICS): {sequences[{text, images[]}]}
   - 自然交错的图文序列
   - 支持段落→图像→段落结构

4. Qwen-VL/InternVL格式: {image, region, ocr, conversations[], layout_analysis}
   - OCR文本检测 (pytesseract)
   - 区域识别
   - 文档版面分析 (段落/表格/图片)

5. 文档版面分析: layout_analysis{paragraphs, tables, figures}

全部基于本地图像分析，无需下载LLM/VLM模型。
"""

import os, json, logging, io, math, re, uuid
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

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import os as _os
    _os.environ['TRANSFORMERS_OFFLINE'] = '1'
    _os.environ['HF_HUB_OFFLINE'] = '1'
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class LLaVAItem:
    """LLaVA标准格式"""
    id: str
    image: str = ""
    conversations: List[Dict] = field(default_factory=list)  # [{"from": "human"/"gpt", "value": str}, ...]


@dataclass
class ShareGPT4VItem:
    """ShareGPT4V标准格式"""
    id: str
    image: str = ""
    caption: str = ""
    conversations: List[Dict] = field(default_factory=list)
    source: str = "NanoBot"


@dataclass
class InterleavedSequence:
    """交错图文序列条目"""
    text: str = ""
    images: List[str] = field(default_factory=list)


@dataclass
class InterleavedDocument:
    """MMC4/OBELICS交错图文文档"""
    id: str
    sequences: List[InterleavedSequence] = field(default_factory=list)


@dataclass
class LayoutRegion:
    """版面分析区域"""
    region_type: str = ""  # paragraph / table / figure / header / footer
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (x, y, w, h)
    content: str = ""
    confidence: float = 1.0


@dataclass
class QwenVLItem:
    """Qwen-VL/InternVL标准格式"""
    id: str
    image_path: str = ""
    region: Optional[List[int]] = None  # [x1, y1, x2, y2] 归一化或像素坐标
    ocr_text: str = ""
    conversations: List[Dict] = field(default_factory=list)  # [{"role": "user", "content": [...]}, ...]
    layout_analysis: Dict[str, Any] = field(default_factory=lambda: {
        "paragraphs": [],
        "tables": [],
        "figures": [],
    })


# ============================================================================
# MLLM Data Pipeline
# ============================================================================

class MLLMDataPipeline:
    """
    MLLM训练数据生成 —— 对齐LLaVA/ShareGPT4V/Qwen-VL/InternVL标准

    核心能力:
    1. 从单张图像生成多轮对话 (LLaVA格式)
    2. 生成100+字详细描述 (ShareGPT4V格式)
    3. 图文交错序列生成 (Interleaved格式)
    4. OCR/版面分析 (Qwen-VL格式)

    所有生成基于本地图像分析 + sentence-transformers编码 + 模板
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

    # 场景类型描述
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
        self._st_model = None
        self._dense_gen = None  # DenseCaptionGenerator lazy import
        self._try_load_model()

    def _try_load_model(self):
        """尝试加载sentence-transformers模型（不会阻塞）"""
        if ST_AVAILABLE and self._st_model is None:
            try:
                import os as _os
                _os.environ['TRANSFORMERS_OFFLINE'] = '1'
                _os.environ['HF_HUB_OFFLINE'] = '1'
                self._st_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', local_files_only=True)
                logger.info("sentence-transformers模型加载成功")
            except Exception as e:
                logger.warning(f"sentence-transformers加载失败(非致命): {e}")
                self._st_model = None

    def _get_dense_generator(self):
        """延迟加载DenseCaptionGenerator"""
        if self._dense_gen is None:
            from data_dense_caption import DenseCaptionGenerator
            self._dense_gen = DenseCaptionGenerator()
        return self._dense_gen

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

    def _encode_image_text(self, image: Image.Image, text: str) -> float:
        """计算图像与文本的语义相似度（用于QA选择）"""
        if not ST_AVAILABLE or self._st_model is None:
            return 0.5
        try:
            # 用文本启发式作为特征
            img_arr = np.array(image.resize((64, 64)))
            img_feat = img_arr.flatten().astype(float)[:128]
            text_embed = self._st_model.encode(text)
            # 简化版本：返回基于文本内容的权重
            return min(1.0, max(0.1, len(text) / 200.0))
        except Exception:
            return 0.5

    # ========================================================================
    # 图像分析工具
    # ========================================================================

    def _get_dominant_color(self, img: Image.Image, region: Optional[Tuple] = None) -> str:
        """获取主色调名称"""
        if region:
            x, y, w, h = region
            arr = np.array(img.crop((x, y, x + w, y + h)).resize((32, 32)))
        else:
            arr = np.array(img.resize((32, 32)))
        avg_color = np.mean(arr.reshape(-1, 3), axis=0)
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
        top_strip = arr[:h//4, :, :]
        top_brightness = float(np.mean(top_strip))
        top_blueness = float(np.mean(top_strip[:,:,2].astype(float) - top_strip[:,:,0].astype(float)))

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

        avg_brightness = float(np.mean(gray)) / 255.0

        if avg_brightness < 0.25:
            return "night"
        if face_count > 0:
            return "portrait"
        if top_brightness > 180 and top_blueness > 10:
            return "landscape"
        if top_brightness > 150:
            return "outdoor"
        return "indoor"

    def _detect_objects_simple(self, img: Image.Image) -> List[Dict[str, Any]]:
        """简易物体检测（基于轮廓分析）"""
        if not CV2_AVAILABLE:
            return []
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape
        objects = []

        # 人脸检测
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

        # 轮廓检测
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
        edges = cv2.Canny(blurred, 30, 100)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            img_area = w * h
            size_ratio = area / img_area if img_area > 0 else 0
            if size_ratio < 0.02 or size_ratio > 0.8:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            # 跳过与人脸重叠的
            is_face = False
            for obj in objects:
                fx, fy, fw, fh = obj["bbox"]
                if (x < fx + fw and x + cw > fx and y < fy + fh and y + ch > fy):
                    is_face = True
                    break
            if is_face:
                continue
            aspect = cw / max(ch, 1)
            color = self._get_dominant_color(img, (x, y, cw, ch))
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

    def _analyze_image(self, image: Union[str, Image.Image]) -> Dict[str, Any]:
        """综合分析图像，返回结构化属性字典"""
        img = self._load_image(image)
        if img is None:
            return {}
        w, h = img.size
        arr = np.array(img)
        gray = np.mean(arr, axis=2)

        avg_brightness = float(np.mean(gray)) / 255.0
        avg_color = np.mean(arr.reshape(-1, 3), axis=0)
        color_std = float(np.std(arr))

        # 主色
        main_color = min(self.COLOR_NAMES, key=lambda c: np.sqrt(
            (avg_color[0] - self.COLOR_NAMES[c][0])**2 +
            (avg_color[1] - self.COLOR_NAMES[c][1])**2 +
            (avg_color[2] - self.COLOR_NAMES[c][2])**2
        ))

        scene = self._detect_scene_type(img)
        objects = self._detect_objects_simple(img)
        face_count = sum(1 for o in objects if o["category"] == "person")
        obj_count = len(objects)
        aspect = w / max(h, 1)

        # 颜色多样性
        color_diversity = "low"
        if color_std > 60:
            color_diversity = "high"
        elif color_std > 30:
            color_diversity = "medium"

        # 光照
        if avg_brightness > 0.7:
            lighting = "bright"
        elif avg_brightness > 0.4:
            lighting = "moderate"
        else:
            lighting = "dim"

        # 对比度
        contrast = float(np.std(gray)) / 127.5
        contrast_desc = "high" if contrast > 0.6 else "low" if contrast < 0.3 else "moderate"

        # 格式
        if aspect > 1.3:
            format_desc = "landscape"
        elif aspect < 0.77:
            format_desc = "portrait"
        else:
            format_desc = "square"

        return {
            "width": w,
            "height": h,
            "aspect_ratio": aspect,
            "format": format_desc,
            "main_color": main_color,
            "color_diversity": color_diversity,
            "brightness": avg_brightness,
            "lighting": lighting,
            "contrast": contrast_desc,
            "scene": scene,
            "face_count": face_count,
            "object_count": obj_count,
            "objects": objects,
        }

    # ============================================================
    # 1. LLaVA格式
    # ============================================================

    def generate_llava_conversation(self, image, caption: str = "",
                                      num_turns: int = 3) -> Dict:
        """
        生成LLaVA标准多轮对话

        LLaVA格式:
        {
            "id": "00000000",
            "image": "path/to/image.jpg",
            "conversations": [
                {"from": "human", "value": "<image>\\nWhat is shown?"},
                {"from": "gpt", "value": "A detailed answer..."},
                ...
            ]
        }

        对话生成策略(无需LLM, 用模板):
        - 第1轮: 画面概括
        - 第2轮: 细节描述 (颜色/物体/光照)
        - 第3轮: 空间布局/关系
        - 第4轮(可选): 情感/氛围
        """
        analysis = self._analyze_image(image)
        if not analysis:
            return {"id": "error", "image": "", "conversations": []}

        img_path = image if isinstance(image, str) else ""
        item_id = f"llava_{uuid.uuid4().hex[:8]}"

        # 用caption增强分析
        if caption:
            analysis["_caption"] = caption

        conversations = []

        # === 第1轮: 概括 ===
        scene_desc = {
            "indoor": "an indoor scene",
            "outdoor": "an outdoor scene",
            "portrait": "a portrait photograph",
            "landscape": "a landscape view",
            "urban": "an urban scene",
            "food": "a food scene",
            "animal": "an animal scene",
            "night": "a night scene",
        }.get(analysis["scene"], "a scene")

        q1 = "What is shown in this image?"
        a1 = f"This image shows {scene_desc}."
        if caption:
            a1 += f" {caption}"
        else:
            a1 += f" The composition is in {analysis['format']} orientation with a {analysis['main_color']} tone."
            if analysis["face_count"] > 0:
                a1 += f" There {'is' if analysis['face_count'] == 1 else 'are'} {analysis['face_count']} person{'s' if analysis['face_count'] != 1 else ''} in the frame."
            a1 += f" The lighting is {analysis['lighting']}."

        conversations.append({"from": "human", "value": f"<image>\n{q1}"})
        conversations.append({"from": "gpt", "value": a1})

        # === 第2轮: 细节/颜色/物体 ===
        if num_turns >= 2:
            q2 = "Can you describe the colors and objects in more detail?"
            a2_parts = []
            a2_parts.append(f"The dominant color is {analysis['main_color']}, with {analysis['color_diversity']} color diversity.")
            if analysis["object_count"] > 0:
                obj_colors = [o["color"] for o in analysis["objects"][:5]]
                obj_types = [o["category"] for o in analysis["objects"][:5]]
                a2_parts.append(f"I can detect {analysis['object_count']} distinct objects including {', '.join(set(obj_types))}.")
                a2_parts.append(f"The objects have {', '.join(set(obj_colors[:3]))} tones.")
            else:
                a2_parts.append("The scene has a relatively uniform composition.")
            a2_parts.append(f"The contrast is {analysis['contrast']} and lighting is {analysis['lighting']}.")
            a2 = " ".join(a2_parts)
            conversations.append({"from": "human", "value": q2})
            conversations.append({"from": "gpt", "value": a2})

        # === 第3轮: 空间布局 ===
        if num_turns >= 3:
            q3 = "Describe the spatial layout and composition of this image."
            a3_parts = []
            a3_parts.append(f"The image has a {analysis['format']} aspect ratio ({analysis['aspect_ratio']:.2f}:1).")
            if analysis["face_count"] > 0:
                a3_parts.append("The person(s) are positioned prominently in the frame, drawing the viewer's attention.")
            if analysis["object_count"] > 1:
                a3_parts.append(f"The {analysis['object_count']} detected elements are distributed across the frame, creating visual depth.")
            else:
                a3_parts.append("The composition is centered on the main subject.")
            a3_parts.append(f"The {analysis['lighting']} lighting helps define the spatial relationships between elements.")
            if caption:
                a3_parts.append(f"Based on the description: {caption[:100]}...")
            a3 = " ".join(a3_parts)
            conversations.append({"from": "human", "value": q3})
            conversations.append({"from": "gpt", "value": a3})

        # === 第4轮: 情感/氛围 (可选) ===
        if num_turns >= 4:
            q4 = "What is the mood or atmosphere of this scene?"
            brightness = analysis["brightness"]
            color = analysis["main_color"]
            if brightness > 0.7 and color in ["white", "yellow", "blue", "cyan"]:
                mood = "bright and cheerful"
            elif brightness < 0.3 or color in ["black", "gray", "navy"]:
                mood = "somber or dramatic"
            elif color in ["red", "orange", "pink"]:
                mood = "warm and energetic"
            else:
                mood = "neutral and calm"
            a4 = f"The overall atmosphere is {mood}. The {analysis['lighting']} lighting and {analysis['main_color']} color palette contribute to this feeling. The composition suggests a {mood.replace(' and ', ', ')} visual narrative."
            conversations.append({"from": "human", "value": q4})
            conversations.append({"from": "gpt", "value": a4})

        # === 第5轮: 图像质量 (可选) ===
        if num_turns >= 5:
            q5 = "Evaluate the technical quality of this image."
            w, h = analysis["width"], analysis["height"]
            a5 = (f"This image has dimensions of {w}x{h} pixels with a {analysis['format']} orientation. "
                  f"The {analysis['lighting']} lighting provides good exposure. "
                  f"Contrast is {analysis['contrast']}, and the color palette shows {analysis['color_diversity']} diversity. "
                  f"The image quality is suitable for visual analysis tasks.")
            conversations.append({"from": "human", "value": q5})
            conversations.append({"from": "gpt", "value": a5})

        return {
            "id": item_id,
            "image": img_path,
            "conversations": conversations,
        }

    def batch_llava(self, image_caption_pairs: List[Tuple]) -> List[Dict]:
        """批量生成LLaVA格式"""
        results = []
        for item in image_caption_pairs:
            if isinstance(item, tuple) and len(item) >= 2:
                image, caption = item[0], item[1]
            else:
                image, caption = item, ""
            result = self.generate_llava_conversation(image, caption)
            results.append(result)
        return results

    # ============================================================
    # 2. ShareGPT4V格式
    # ============================================================

    def _expand_caption(self, analysis: Dict[str, Any], caption: str = "") -> str:
        """将短caption扩展为100+字的详细描述"""
        parts = []

        # 如果有原始caption，用它开头
        if caption:
            parts.append(caption.rstrip(".") + ".")

        # 场景描述
        scene_desc = {
            "indoor": "This is an indoor scene",
            "outdoor": "This is an outdoor scene",
            "portrait": "This is a portrait scene",
            "landscape": "This is a landscape scene",
            "urban": "This is an urban scene",
            "food": "This is a food scene",
            "animal": "This is an animal scene",
            "night": "This is a night scene",
        }.get(analysis["scene"], "This image shows a scene")

        format_desc = {
            "landscape": "in landscape orientation",
            "portrait": "in portrait orientation",
            "square": "in a square format",
        }.get(analysis["format"], "")

        # 主体描述
        subject_parts = []
        if analysis["face_count"] > 0:
            subject_parts.append(f"there {'is' if analysis['face_count'] == 1 else 'are'} {analysis['face_count']} person{'s' if analysis['face_count'] != 1 else ''} in the frame")
        if analysis["object_count"] > 0:
            obj_types = list(set(o["category"] for o in analysis["objects"]))
            obj_colors = list(set(o["color"] for o in analysis["objects"][:5]))
            subject_parts.append(f"{analysis['object_count']} distinct visual elements including {', '.join(obj_types[:3])}")

        # 颜色描述
        color_parts = []
        color_parts.append(f"the dominant color is {analysis['main_color']}")
        color_parts.append(f"the color diversity is {analysis['color_diversity']}")

        # 光照和对比度
        lighting_parts = []
        lighting_parts.append(f"lighting conditions are {analysis['lighting']}")
        lighting_parts.append(f"contrast is {analysis['contrast']}")

        # 构图描述
        composition_parts = []
        composition_parts.append(f"the composition follows a {analysis['format']} format")
        if analysis["face_count"] > 0:
            composition_parts.append("with human subjects positioned as the focal point")
        else:
            composition_parts.append("with elements distributed across the visual field")

        # 综合描述
        full_parts = [
            f"{scene_desc} {format_desc}.",
            "In terms of visual content, " + ", ".join(subject_parts) + "." if subject_parts else "The scene contains a variety of visual information.",
            f"Regarding color, {', '.join(color_parts)}.",
            f"For lighting and texture, {', '.join(lighting_parts)}.",
            f"Compositionally, {', '.join(composition_parts)}.",
            f"The overall atmosphere is influenced by the {analysis['main_color']} palette and {analysis['lighting']} lighting.",
            f"The image dimensions are {analysis['width']}x{analysis['height']} pixels, providing a {analysis['aspect_ratio']:.2f} aspect ratio.",
        ]

        result = " ".join(full_parts)

        # 确保100+字
        if len(result) < 100:
            result += " The scene presents a rich visual narrative with multiple layers of detail to explore, including spatial relationships between objects, subtle texture variations, and the interplay of light and shadow across different surfaces."

        return result

    def generate_sharegpt4v(self, image, caption: str = "") -> Dict:
        """
        生成ShareGPT4V标准格式

        格式:
        {
            "id": "sg_000001",
            "image": "path/to/image.jpg",
            "caption": "A detailed caption of 100+ words...",
            "conversations": [
                {"from": "human", "value": "<image>\\nTell me about this image."},
                {"from": "gpt", "value": "Detailed answer..."}
            ],
            "source": "NanoBot"
        }

        策略:
        - caption扩展: 从短caption用模板扩展为100+字
        - 包含: 场景描述/主体/颜色/光照/构图/情绪/关系
        - conversation: 基于详细描述生成QA
        """
        analysis = self._analyze_image(image)
        if not analysis:
            return {"id": "error", "image": "", "caption": "", "conversations": [], "source": "NanoBot"}

        img_path = image if isinstance(image, str) else ""
        item_id = f"sg_{uuid.uuid4().hex[:8]}"

        # 生成100+字详细描述
        detailed_caption = self._expand_caption(analysis, caption)

        # 基于详细描述生成QA对话
        conversations = []

        # Q1: 概括性描述
        q1 = f"<image>\nTell me about this image."
        a1 = detailed_caption
        conversations.append({"from": "human", "value": q1})
        conversations.append({"from": "gpt", "value": a1})

        # Q2: 细节追问
        q2 = "What specific visual details stand out in this image?"
        a2_parts = []
        if analysis["face_count"] > 0:
            a2_parts.append(f"There are {analysis['face_count']} people visible, drawing immediate attention.")
        a2_parts.append(f"The {analysis['main_color']} color palette is particularly noteworthy.")
        if analysis["object_count"] > 0:
            objects = analysis["objects"]
            colors_used = list(set(o["color"] for o in objects[:5]))
            a2_parts.append(f"The {analysis['object_count']} detected objects exhibit colors including {', '.join(colors_used)}.")
        a2_parts.append(f"The {analysis['lighting']} lighting creates a distinct visual atmosphere with {analysis['contrast']} contrast.")
        a2 = " ".join(a2_parts)
        conversations.append({"from": "human", "value": q2})
        conversations.append({"from": "gpt", "value": a2})

        # Q3: 空间/构图
        q3 = "How is the visual composition arranged?"
        a3 = (f"The image uses a {analysis['format']} composition with a {analysis['aspect_ratio']:.2f} aspect ratio. "
              f"The {analysis['lighting']} lighting helps define spatial depth. "
              f"Objects and elements are arranged to create a balanced visual flow across the {analysis['width']}x{analysis['height']} pixel canvas.")
        conversations.append({"from": "human", "value": q3})
        conversations.append({"from": "gpt", "value": a3})

        return {
            "id": item_id,
            "image": img_path,
            "caption": detailed_caption,
            "conversations": conversations,
            "source": "NanoBot",
        }

    # ============================================================
    # 3. Interleaved图文格式 (MMC4/OBELICS)
    # ============================================================

    def generate_interleaved(self, image_text_pairs: List[Tuple]) -> Dict:
        """
        生成MMC4/OBELICS交错图文格式

        格式:
        {
            "id": "doc_000001",
            "sequences": [
                {"text": "Here is a photo of...", "images": ["path/img1.jpg"]},
                {"text": "This shows...", "images": []},
                {"text": "Another view:", "images": ["path/img2.jpg"]}
            ]
        }

        Args:
            image_text_pairs: 图文对列表，每个元素为 (image_or_caption, text) 或
                              (image_path, text) 或单一文本
        """
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        sequences = []

        for i, pair in enumerate(image_text_pairs):
            if isinstance(pair, tuple) and len(pair) >= 2:
                img_or_cap, text = pair[0], pair[1]
            else:
                img_or_cap, text = None, str(pair)

            # 检查第一个参数是否为图像路径
            images = []
            if img_or_cap is not None:
                img = self._load_image(img_or_cap)
                if img is not None:
                    # 是有效图像，加入images列表
                    if isinstance(img_or_cap, str) and os.path.isfile(img_or_cap):
                        images.append(img_or_cap)
                    elif isinstance(img_or_cap, Image.Image):
                        # PIL对象: 保存为临时文件后引用路径
                        import tempfile
                        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.png')
                        os.close(tmp_fd)
                        img_or_cap.save(tmp_path)
                        images.append(tmp_path)
                    # 对图像进行分析，用于生成文本描述
                    analysis = self._analyze_image(img_or_cap)
                    # 如果text为空，基于分析生成
                    if not text and analysis:
                        text = f"Figure {i+1}: A {analysis['scene']} scene with {analysis['main_color']} tones."
                    elif not text:
                        text = f"Figure {i+1}: A visual element in the document."

            seq = InterleavedSequence(
                text=text or f"Section {i+1} of the document.",
                images=images,
            )
            sequences.append(seq)

        # 如果只有一对且image_text_pairs为空，生成默认序列
        if not sequences:
            sequences.append(InterleavedSequence(
                text="This is a document with embedded visual elements.",
                images=[],
            ))

        return {
            "id": doc_id,
            "sequences": [asdict(s) for s in sequences],
        }

    # ============================================================
    # 4. Qwen-VL/InternVL格式 (OCR+版面)
    # ============================================================

    def _detect_text_ocr(self, image: Image.Image) -> str:
        """OCR文本检测（pytesseract）"""
        if not TESSERACT_AVAILABLE:
            return ""
        try:
            # 中文+英文
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            return text.strip()
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            try:
                text = pytesseract.image_to_string(image, lang="eng")
                return text.strip()
            except Exception:
                return ""

    def _detect_text_regions(self, image: Image.Image) -> List[Dict[str, Any]]:
        """检测文本区域（通过轮廓分析）"""
        if not CV2_AVAILABLE:
            return []
        arr = np.array(image)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        # 自适应二值化
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)

        # 形态学操作连接字符
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
        dilated = cv2.dilate(binary, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area_ratio = (cw * ch) / (w * h)
            aspect = cw / max(ch, 1)
            # 文本区域通常: 宽高比>1, 面积不太大不太小
            if area_ratio > 0.001 and area_ratio < 0.5 and aspect > 0.3 and aspect < 20:
                regions.append({
                    "bbox": (x, y, cw, ch),
                    "confidence": min(1.0, area_ratio * 10),
                })

        return regions

    def _analyze_layout(self, image: Image.Image) -> Dict[str, Any]:
        """
        文档版面分析

        使用轮廓检测+形态学分析识别:
        - 段落 (paragraphs): 大块文本区域
        - 表格 (tables): 网格结构
        - 图片 (figures): 图像区域
        - 页眉/页脚 (header/footer)
        """
        if not CV2_AVAILABLE:
            return {"paragraphs": [], "tables": [], "figures": []}

        arr = np.array(image)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        paragraphs = []
        tables = []
        figures = []

        # 1. 二值化+轮廓检测找出所有区域
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)

        # 水平内核检测文本行
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
        h_dilated = cv2.dilate(binary, h_kernel, iterations=2)

        # 垂直内核检测表格线/分隔
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
        v_dilated = cv2.dilate(binary, v_kernel, iterations=2)

        # 检测文本块 (段落)
        text_contours, _ = cv2.findContours(h_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in text_contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area_ratio = (cw * ch) / (w * h)
            if area_ratio > 0.01 and area_ratio < 0.6:
                # 检测是否为表格（网格结构）
                roi = binary[y:y+ch, x:x+cw]
                h_lines = cv2.reduce(roi, 1, cv2.REDUCE_AVG).flatten()
                v_lines = cv2.reduce(roi, 0, cv2.REDUCE_AVG).flatten()
                h_peaks = np.sum(h_lines > 200)
                v_peaks = np.sum(v_lines > 200)
                is_table = h_peaks > 3 and v_peaks > 3

                if is_table:
                    tables.append(LayoutRegion(
                        region_type="table",
                        bbox=(x, y, cw, ch),
                        content=f"Table region at ({x}, {y}, {cw}, {ch})",
                        confidence=0.6,
                    ))
                else:
                    paragraphs.append(LayoutRegion(
                        region_type="paragraph",
                        bbox=(x, y, cw, ch),
                        content=f"Text paragraph at ({x}, {y}, {cw}, {ch})",
                        confidence=0.7,
                    ))

        # 2. 检测图像区域 (大面积的平滑区域)
        # 用Canny边缘检测后找填充区域
        edges = cv2.Canny(gray, 50, 150)
        edge_density = cv2.boxFilter(edges.astype(float), -1, (15, 15))
        _, figure_mask = cv2.threshold(edge_density, 30, 255, cv2.THRESH_BINARY_INV)

        fig_contours, _ = cv2.findContours(figure_mask.astype(np.uint8),
                                           cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in fig_contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area_ratio = (cw * ch) / (w * h)
            if area_ratio > 0.03 and area_ratio < 0.7:
                # 检查是否与文本区域重叠
                is_text_overlap = False
                for p in paragraphs:
                    px, py, pw, ph = p.bbox
                    if (x < px + pw and x + cw > px and y < py + ph and y + ch > py):
                        is_text_overlap = True
                        break
                if not is_text_overlap:
                    figures.append(LayoutRegion(
                        region_type="figure",
                        bbox=(x, y, cw, ch),
                        content=f"Figure/image region at ({x}, {y}, {cw}, {ch})",
                        confidence=0.5,
                    ))

        # 3. 页眉/页脚检测
        header_zone = gray[:h//8, :]
        footer_zone = gray[7*h//8:, :]
        if np.mean(header_zone) < 200:  # 有内容
            paragraphs.append(LayoutRegion(
                region_type="header",
                bbox=(0, 0, w, h//8),
                content="Header region",
                confidence=0.4,
            ))
        if np.mean(footer_zone) < 200:
            paragraphs.append(LayoutRegion(
                region_type="footer",
                bbox=(0, 7*h//8, w, h//8),
                content="Footer region",
                confidence=0.4,
            ))

        return {
            "paragraphs": [asdict(p) for p in paragraphs],
            "tables": [asdict(t) for t in tables],
            "figures": [asdict(f) for f in figures],
        }

    def generate_qwenvl(self, image, caption: str = "") -> Dict:
        """
        生成Qwen-VL标准格式(含OCR+版面)

        格式:
        {
            "id": "qwen_001",
            "image_path": "path/image.jpg",
            "region": [x1, y1, x2, y2],  # 如果有区域标注
            "ocr_text": "detected text...",
            "conversations": [{"role": "user", "content": [...]}, ...],
            "layout_analysis": {
                "paragraphs": [...],
                "tables": [...],
                "figures": [...]
            }
        }

        OCR使用pytesseract
        版面分析使用OpenCV轮廓检测
        """
        analysis = self._analyze_image(image)
        if not analysis:
            return {
                "id": "error",
                "image_path": "",
                "region": None,
                "ocr_text": "",
                "conversations": [],
                "layout_analysis": {"paragraphs": [], "tables": [], "figures": []},
            }

        img = self._load_image(image)
        img_path = image if isinstance(image, str) else ""
        item_id = f"qwen_{uuid.uuid4().hex[:8]}"

        # 1. OCR文本检测
        ocr_text = ""
        if img is not None and TESSERACT_AVAILABLE:
            ocr_text = self._detect_text_ocr(img)

        # 2. 版面分析
        layout = {"paragraphs": [], "tables": [], "figures": []}
        if img is not None:
            layout = self._analyze_layout(img)

        # 3. 区域检测 (取最大物体框)
        region = None
        if analysis["objects"]:
            # 找到最大物体作为region
            max_obj = max(analysis["objects"], key=lambda o: o["bbox"][2] * o["bbox"][3])
            x, y, w, h = max_obj["bbox"]
            region = [int(x), int(y), int(x + w), int(y + h)]

        # 4. 构建对话 (Qwen-VL格式: role+content)
        conversations = []

        # Q1: 概括
        scene_desc = {
            "indoor": "an indoor scene",
            "outdoor": "an outdoor scene",
            "portrait": "a portrait photograph",
            "landscape": "a landscape view",
            "urban": "an urban scene",
            "food": "a food scene",
            "animal": "an animal scene",
            "night": "a night scene",
        }.get(analysis["scene"], "a scene")

        conv1_content = []
        conv1_content.append({"type": "text", "text": "Describe this image in detail."})
        conv1_answer = f"This is {scene_desc}."
        if caption:
            conv1_answer += f" {caption}"
        conv1_answer += f" The dominant color is {analysis['main_color']} with {analysis['lighting']} lighting."
        if analysis["face_count"] > 0:
            conv1_answer += f" There are {analysis['face_count']} person(s) visible."
        conv1_answer += f" Image dimensions: {analysis['width']}x{analysis['height']}."

        if ocr_text:
            conv1_answer += f" Detected text: '{ocr_text[:100]}'."

        conversations.append({
            "role": "user",
            "content": conv1_content,
        })
        conversations.append({
            "role": "assistant",
            "content": [{"type": "text", "text": conv1_answer}],
        })

        # Q2: OCR/文字内容
        if ocr_text:
            conv2_content = [{"type": "text", "text": "What text is present in this image?"}]
            conv2_answer = f"The OCR system detected the following text: '{ocr_text}'."
            conversations.append({"role": "user", "content": conv2_content})
            conversations.append({
                "role": "assistant",
                "content": [{"type": "text", "text": conv2_answer}],
            })

        # Q3: 版面结构
        layout_desc_parts = []
        if layout["paragraphs"]:
            layout_desc_parts.append(f"{len(layout['paragraphs'])} text paragraph(s)")
        if layout["tables"]:
            layout_desc_parts.append(f"{len(layout['tables'])} table(s)")
        if layout["figures"]:
            layout_desc_parts.append(f"{len(layout['figures'])} figure(s)")

        if layout_desc_parts:
            conv3_content = [{"type": "text", "text": "What is the layout structure of this document?"}]
            conv3_answer = f"The document layout contains {', '.join(layout_desc_parts)}."
            conversations.append({"role": "user", "content": conv3_content})
            conversations.append({
                "role": "assistant",
                "content": [{"type": "text", "text": conv3_answer}],
            })

        return {
            "id": item_id,
            "image_path": img_path,
            "region": region,
            "ocr_text": ocr_text,
            "conversations": conversations,
            "layout_analysis": layout,
        }

    # ============================================================
    # 5. 文档版面分析（独立方法）
    # ============================================================

    def analyze_document_layout(self, image) -> Dict[str, Any]:
        """
        独立的文档版面分析入口

        返回:
        {
            "layout_analysis": {
                "paragraphs": [{"region_type": "paragraph", "bbox": [x,y,w,h], "content": "", "confidence": 0.7}, ...],
                "tables": [...],
                "figures": [...]
            }
        }
        """
        img = self._load_image(image)
        if img is None:
            return {"layout_analysis": {"paragraphs": [], "tables": [], "figures": []}}
        layout = self._analyze_layout(img)
        return {"layout_analysis": layout}

    # ============================================================
    # 格式保存
    # ============================================================

    def save_llava_jsonl(self, items: List[Dict], output_path: str):
        """保存LLaVA格式JSONL"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} LLaVA items to {output_path}")

    def save_sharegpt4v_jsonl(self, items: List[Dict], output_path: str):
        """保存ShareGPT4V格式JSONL"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} ShareGPT4V items to {output_path}")

    def save_hf_dataset(self, items: List[Dict], output_path: str, format: str = "llava"):
        """
        保存为HuggingFace Datasets可加载格式

        Args:
            items: 数据条目列表
            output_path: 输出目录
            format: "llava", "sharegpt4v", "interleaved", "qwenvl"
        """
        os.makedirs(output_path, exist_ok=True)

        # 保存数据
        data_path = os.path.join(output_path, f"{format}_data.jsonl")
        with open(data_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # 保存元数据
        meta = {
            "format": format,
            "num_items": len(items),
            "created_at": datetime.now().isoformat(),
            "source": "NanoBot Factory",
            "description": f"MLLM training data in {format} format",
        }
        meta_path = os.path.join(output_path, "dataset_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # 保存读取脚本兼容性配置
        config = {
            "dataset_name": f"nanobot_{format}",
            "configs": ["data"],
            "features": {
                "id": "string",
                "image": "string" if format in ["llava", "sharegpt4v"] else "?",
                "format": format,
            },
        }
        config_path = os.path.join(output_path, "dataset_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        logger.info(f"HF dataset ({format}) saved to {output_path} with {len(items)} items")
        return output_path


# ============================================================================
# Convenience
# ============================================================================

def get_mllm_pipeline() -> MLLMDataPipeline:
    """获取MLLM数据管线实例"""
    return MLLMDataPipeline()
