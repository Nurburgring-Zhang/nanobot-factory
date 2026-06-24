"""
NanoBot Factory - 编辑指令自动生成管线
Edit Instruction Data Generation Pipeline

对齐行业最新标准:
- InstructPix2Pix: {input_image, edited_image, instruction}
- UltraEdit: {original_image, edited_image, instruction, source_caption, target_caption}
- AnyEdit: {source, target, instruction, edit_type}

核心能力（全部用模板+本地算法）:
1. 自动生成20种编辑类型
2. 每种编辑类型有对应指令模板
3. 用PIL/OpenCV模拟编辑效果（实际生成在ComfyUI/API中执行）
4. 输出标准JSONL
"""

import os, json, logging, io, math, random, uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps, ImageChops
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
class EditInstructionItem:
    """编辑指令数据条目——对齐InstructPix2Pix/UltraEdit标准"""
    id: str = ""
    source_image: str = ""          # 原始图像路径
    edited_image: str = ""          # 编辑后图像路径
    instruction: str = ""           # 编辑指令文本
    edit_type: str = ""             # 编辑类型
    source_caption: str = ""        # 原始描述（UltraEdit格式）
    target_caption: str = ""        # 目标描述（UltraEdit格式）
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# 编辑类型Taxonomy
# ============================================================================

EDIT_TYPE_TAXONOMY = {
    # ===== 颜色/外观 =====
    "color_change": {
        "description": "改变物体颜色",
        "templates": [
            "Make the {object} {color}",
            "Change the color of the {object} to {color}",
            "Recolor the {object} in {color}",
            "Turn the {object} into {color}",
        ],
    },
    "color_saturation": {
        "description": "改变饱和度",
        "templates": [
            "Increase the saturation of the image",
            "Make the colors more vibrant",
            "Desaturate the image",
            "Convert to black and white",
        ],
    },
    "color_temperature": {
        "description": "改变色温",
        "templates": [
            "Make the image warmer (add more yellow/orange tones)",
            "Make the image cooler (add more blue tones)",
            "Apply a warm color filter",
            "Apply a cold color filter",
        ],
    },

    # ===== 背景 =====
    "background_replace": {
        "description": "替换背景",
        "templates": [
            "Replace the background with {new_bg}",
            "Change the background to {new_bg}",
            "Put the subject in front of {new_bg}",
            "Swap the background with {new_bg}",
        ],
    },
    "background_blur": {
        "description": "背景模糊（模拟景深）",
        "templates": [
            "Blur the background to create bokeh effect",
            "Add shallow depth of field, blur the background",
            "Make the background out of focus",
            "Apply portrait mode with background blur",
        ],
    },
    "background_remove": {
        "description": "移除背景",
        "templates": [
            "Remove the background, keep only the subject",
            "Make the background transparent",
            "Isolate the main subject by removing the background",
            "Cut out the subject from its background",
        ],
    },

    # ===== 物体操作 =====
    "object_add": {
        "description": "添加物体",
        "templates": [
            "Add {object} to the scene",
            "Place {object} in the image",
            "Insert {object} into the composition",
            "Add a {object} in the foreground",
        ],
    },
    "object_remove": {
        "description": "移除物体",
        "templates": [
            "Remove the {object} from the image",
            "Delete the {object} from the scene",
            "Erase the {object}",
            "Take out the {object}",
        ],
    },
    "object_replace": {
        "description": "替换物体",
        "templates": [
            "Replace the {object} with {new_object}",
            "Swap the {object} for {new_object}",
            "Change the {object} into {new_object}",
            "Turn the {object} into {new_object}",
        ],
    },
    "object_resize": {
        "description": "改变物体大小",
        "templates": [
            "Make the {object} larger",
            "Make the {object} smaller",
            "Enlarge the {object}",
            "Shrink the {object}",
        ],
    },
    "object_move": {
        "description": "移动物体位置",
        "templates": [
            "Move the {object} to the {position}",
            "Reposition the {object} to the {position} side",
            "Shift the {object} to the {position}",
            "Place the {object} on the {position} side of the frame",
        ],
    },

    # ===== 风格 =====
    "style_transfer": {
        "description": "风格迁移",
        "templates": [
            "Apply {style} style to the image",
            "Render the image in {style} style",
            "Transform the image with {style} aesthetics",
            "Make this image look like {style}",
        ],
    },
    "style_cartoon": {
        "description": "卡通化",
        "templates": [
            "Turn this into a cartoon",
            "Apply a cartoon filter",
            "Make the image look like an anime",
            "Convert to comic book style",
        ],
    },
    "style_painting": {
        "description": "绘画风格",
        "templates": [
            "Make this look like an oil painting",
            "Apply a watercolor effect",
            "Turn this into a pencil sketch",
            "Convert to a charcoal drawing",
        ],
    },

    # ===== 季节/时间 =====
    "season_change": {
        "description": "季节变换",
        "templates": [
            "Change the season to {season}",
            "Make it look like {season}",
            "Transform the scene to {season}",
            "Apply {season} atmosphere to the image",
        ],
    },
    "time_change": {
        "description": "时间变换",
        "templates": [
            "Change the time to {time_of_day}",
            "Make it look like {time_of_day}",
            "Transform the lighting to {time_of_day}",
            "Apply {time_of_day} lighting conditions",
        ],
    },

    # ===== 材质/纹理 =====
    "material_change": {
        "description": "材质变化",
        "templates": [
            "Change the {object} material to {material}",
            "Make the {object} look like {material}",
            "Apply {material} texture to the {object}",
            "Transform the surface of the {object} to {material}",
        ],
    },

    # ===== 天气 =====
    "weather_change": {
        "description": "天气变化",
        "templates": [
            "Change the weather to {weather}",
            "Make it {weather} outside",
            "Apply {weather} weather conditions",
            "Show the scene in {weather} weather",
        ],
    },

    # ===== 光照 =====
    "lighting_adjust": {
        "description": "光照调整",
        "templates": [
            "Adjust lighting to {lighting_type}",
            "Make the lighting {lighting_type}",
            "Apply {lighting_type} lighting to the scene",
            "Change the illumination to {lighting_type}",
        ],
    },
    "lighting_dramatic": {
        "description": "戏剧化光照",
        "templates": [
            "Add dramatic lighting effects",
            "Create strong chiaroscuro lighting",
            "Apply dramatic shadows and highlights",
            "Make the lighting more dramatic with strong contrasts",
        ],
    },
}

# 常用颜色值
EDIT_COLORS = {
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
    "green": (0, 128, 0),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "gold": (255, 215, 0),
    "silver": (192, 192, 192),
    "teal": (0, 128, 128),
}

# 季节参数
SEASON_PARAMS = {
    "spring": {"brightness": 1.1, "saturation": 1.15, "warmth": 1.05, "haze": 0.05},
    "summer": {"brightness": 1.2, "saturation": 1.2, "warmth": 1.1, "haze": 0.1},
    "autumn": {"brightness": 0.9, "saturation": 1.3, "warmth": 1.3, "haze": 0.0},
    "winter": {"brightness": 1.0, "saturation": 0.7, "warmth": 0.8, "haze": 0.2},
}

# 时间段参数
TIME_PARAMS = {
    "sunrise": {"brightness": 0.8, "warmth": 1.4, "contrast": 1.2},
    "noon": {"brightness": 1.2, "warmth": 1.0, "contrast": 1.0},
    "sunset": {"brightness": 0.7, "warmth": 1.6, "contrast": 1.3},
    "night": {"brightness": 0.3, "warmth": 0.7, "contrast": 1.4},
    "golden_hour": {"brightness": 0.9, "warmth": 1.8, "contrast": 1.2},
}

# 天气参数
WEATHER_PARAMS = {
    "sunny": {"brightness": 1.2, "saturation": 1.1, "contrast": 1.15},
    "cloudy": {"brightness": 0.75, "saturation": 0.8, "contrast": 0.7},
    "rainy": {"brightness": 0.65, "saturation": 0.9, "contrast": 0.8, "blur": 0.5},
    "foggy": {"brightness": 0.8, "saturation": 0.6, "contrast": 0.5, "haze": 1.0},
    "snowy": {"brightness": 1.15, "saturation": 0.5, "contrast": 0.9, "haze": 0.3},
    "stormy": {"brightness": 0.5, "saturation": 0.9, "contrast": 1.3, "blur": 0.3},
}

# 光照类型参数
LIGHTING_PARAMS = {
    "soft": {"contrast": 0.6, "brightness": 0.9, "sharpen": 0.0},
    "hard": {"contrast": 1.4, "brightness": 1.1, "sharpen": 0.5},
    "warm": {"warmth": 1.3, "brightness": 1.0, "saturation": 1.1},
    "cool": {"warmth": 0.7, "brightness": 0.9, "saturation": 0.9},
    "neon": {"saturation": 1.5, "contrast": 1.3, "brightness": 1.1},
    "studio": {"brightness": 1.1, "contrast": 1.0, "saturation": 1.0},
    "backlit": {"brightness": 0.8, "contrast": 1.5, "highlights": 1.3},
}

# 风格选项
STYLE_OPTIONS = [
    "vintage", "cinematic", "noir", "pop art", "minimalist",
    "retro", "cyberpunk", "steampunk", "baroque", "impressionist",
    "expressionist", "surrealist", "abstract", "photorealistic",
    "anime", "ukiyo-e", "art deco", "bauhaus", "gothic",
]
MATERIAL_OPTIONS = [
    "metal", "wood", "glass", "stone", "plastic",
    "ceramic", "fabric", "leather", "paper", "concrete",
    "marble", "gold", "rusty metal", "polished chrome", "frosted glass",
]

# 基本物体列表（用于object_add/remove占位）
COMMON_OBJECTS = [
    "a cat", "a dog", "a bird", "a flower", "a tree",
    "a car", "a bicycle", "a chair", "a table", "a lamp",
    "a book", "a coffee cup", "a vase", "a clock", "a mirror",
    "a painting", "a rug", "a cushion", "a plant", "a ball",
]
POSITION_OPTIONS = ["left", "right", "top", "bottom", "center", "corner"]

# 新增编辑类型 (subtype不是独立taxonomy, 是fallback对象)
NEW_BG_OPTIONS = [
    "a beach", "a forest", "a mountain landscape", "a city street",
    "a cozy room", "a garden", "a desert", "a snowy landscape",
    "a starry night", "a sunset sky", "a modern office", "a park",
]

# 背景填充色
BG_COLORS = ["#87CEEB", "#98FB98", "#F5F5DC", "#E6E6FA", "#FFE4B5", "#B0C4DE"]


# ============================================================================
# Edit Pipeline
# ============================================================================

class EditInstructionPipeline:
    """
    编辑指令自动生成管线

    对齐:
    - InstructPix2Pix: {input_image, edited_image, instruction}
    - UltraEdit: {original_image, edited_image, instruction, source_caption, target_caption}
    - AnyEdit: {source, target, instruction, edit_type}

    编辑效果使用PIL/OpenCV本地模拟，实际生成在ComfyUI/API中执行。
    输出为标准JSONL格式。
    """

    def __init__(self):
        self.edit_types = list(EDIT_TYPE_TAXONOMY.keys())

    def _load_image(self, image: Union[str, Image.Image, np.ndarray]) -> Optional[Image.Image]:
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
            elif isinstance(image, np.ndarray):
                return Image.fromarray(image).convert("RGB")
        except Exception as e:
            logger.warning(f"Failed to load image: {e}")
            return None

    def _get_image_info(self, image: Image.Image) -> Dict[str, Any]:
        """获取图像基本信息用于生成描述"""
        arr = np.array(image)
        h, w = arr.shape[:2]
        gray = np.mean(arr, axis=2)
        avg_brightness = float(np.mean(gray)) / 255.0
        avg_color = np.mean(arr.reshape(-1, 3), axis=0)
        return {
            "width": w,
            "height": h,
            "brightness": avg_brightness,
            "avg_color": avg_color.tolist(),
        }

    # ========================================================================
    # 编辑效果模拟
    # ========================================================================

    def _simulate_color_change(self, img: Image.Image, target_color: str = "red",
                                object_desc: str = "main subject") -> Image.Image:
        """模拟颜色变化——给图像施加色调偏移"""
        img = img.copy()
        color_rgb = EDIT_COLORS.get(target_color, (255, 0, 0))
        # 创建纯色图层
        color_layer = Image.new("RGB", img.size, color_rgb)
        # 混合（半透明叠加）
        blended = Image.blend(img, color_layer, 0.3)
        return blended

    def _simulate_saturation_change(self, img: Image.Image, increase: bool = True) -> Image.Image:
        """模拟饱和度变化"""
        enhancer = ImageEnhance.Color(img)
        factor = 1.8 if increase else 0.2
        return enhancer.enhance(factor)

    def _simulate_temperature_change(self, img: Image.Image, warmer: bool = True) -> Image.Image:
        """模拟色温变化"""
        img = img.copy()
        arr = np.array(img).astype(np.float32)
        if warmer:
            arr[:, :, 0] *= 0.9  # 减蓝
            arr[:, :, 2] *= 1.15  # 增红
        else:
            arr[:, :, 0] *= 1.15  # 增蓝
            arr[:, :, 2] *= 0.9  # 减红
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        return Image.fromarray(arr)

    def _simulate_background_blur(self, img: Image.Image, blur_radius: int = 10) -> Image.Image:
        """模拟背景模糊（保留中心清晰区域）"""
        w, h = img.size
        # 创建径向渐变mask: 中心清晰, 边缘模糊
        center_x, center_y = w // 2, h // 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        for y in range(h):
            for x in range(w):
                dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                val = max(0, int(255 * (1 - dist / max_dist)))
                draw.point((x, y), fill=val)
        # 模糊整体
        blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        # 合成
        result = Image.composite(img, blurred, mask)
        return result

    def _simulate_background_remove(self, img: Image.Image) -> Image.Image:
        """模拟背景移除——用纯色背景替代"""
        img = img.copy()
        bg_color = random.choice(BG_COLORS)
        # 简单实现：边缘检测后填充背景
        arr = np.array(img)
        gray = np.mean(arr, axis=2)
        # 在边缘区域模糊
        blurred = img.filter(ImageFilter.GaussianBlur(radius=15))
        # 合成：中心保留，边缘模糊（近似抠图效果）
        w, h = img.size
        cx, cy = w // 2, h // 2
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([cx - w//3, cy - h//3, cx + w//3, cy + h//3], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=20))
        result = Image.composite(img, blurred, mask)
        return result

    def _simulate_object_remove(self, img: Image.Image) -> Image.Image:
        """模拟物体移除——用inpainting近似（区域模糊）"""
        w, h = img.size
        # 在随机位置添加模糊块（模拟移除）
        img = img.copy()
        x = random.randint(w // 4, w // 2)
        y = random.randint(h // 4, h // 2)
        rw, rh = random.randint(30, 80), random.randint(30, 80)
        region = img.crop((x, y, x + rw, y + rh))
        # 模糊该区域
        region_blurred = region.filter(ImageFilter.GaussianBlur(radius=12))
        img.paste(region_blurred, (x, y))
        return img

    def _simulate_style_transfer(self, img: Image.Image, style: str = "vintage") -> Image.Image:
        """模拟风格迁移效果"""
        img = img.copy()
        if style == "vintage":
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(0.6)
            arr = np.array(img).astype(np.float32)
            arr[:, :, 0] *= 0.85  # 减蓝
            arr[:, :, 2] *= 1.1  # 增红
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)
        elif style == "noir":
            img = img.convert("L").convert("RGB")
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.8)
        elif style == "cartoon" or style == "anime":
            img = self._simulate_cartoon(img)
        elif style == "cinematic":
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            arr = np.array(img).astype(np.float32)
            # 加黑边（宽银幕）
            h, w = arr.shape[:2]
            band_h = int(h * 0.08)
            arr[:band_h] *= 0.0
            arr[h-band_h:] *= 0.0
            arr[:, :, 2] *= 1.1  # 暖色调
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)
        else:
            # 通用风格: 增加饱和度+对比度
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.3)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
        return img

    def _simulate_cartoon(self, img: Image.Image) -> Image.Image:
        """卡通化效果"""
        if not CV2_AVAILABLE:
            return self._simulate_style_transfer(img, "vintage")
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # 边缘检测
        edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY, 9, 2)
        # 双边滤波（平滑保留边缘）
        color = cv2.bilateralFilter(arr, 9, 200, 200)
        # 叠加边缘
        edges_rgb = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
        cartoon = cv2.bitwise_and(color, edges_rgb)
        return Image.fromarray(cartoon)

    def _simulate_season_change(self, img: Image.Image, season: str = "autumn") -> Image.Image:
        """模拟季节变化"""
        params = SEASON_PARAMS.get(season, SEASON_PARAMS["summer"])
        img = img.copy()
        # 亮度
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(params.get("brightness", 1.0))
        # 饱和度
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(params.get("saturation", 1.0))
        # 色温（通过颜色通道调整）
        warmth = params.get("warmth", 1.0)
        arr = np.array(img).astype(np.float32)
        arr[:, :, 0] *= (2.0 - warmth)  # B通道
        arr[:, :, 2] *= warmth  # R通道
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
        # 雾/霾效果
        haze = params.get("haze", 0.0)
        if haze > 0.01:
            haze_layer = Image.new("RGB", img.size, (200, 200, 200))
            img = Image.blend(img, haze_layer, haze)
        return img

    def _simulate_time_change(self, img: Image.Image, time_of_day: str = "sunset") -> Image.Image:
        """模拟时间变化（光照变化）"""
        params = TIME_PARAMS.get(time_of_day, TIME_PARAMS["noon"])
        img = img.copy()
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(params.get("brightness", 1.0))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(params.get("contrast", 1.0))
        warmth = params.get("warmth", 1.0)
        arr = np.array(img).astype(np.float32)
        arr[:, :, 0] *= (2.0 - warmth)
        arr[:, :, 2] *= warmth
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
        return img

    def _simulate_weather_change(self, img: Image.Image, weather: str = "rainy") -> Image.Image:
        """模拟天气变化"""
        params = WEATHER_PARAMS.get(weather, WEATHER_PARAMS["cloudy"])
        img = img.copy()
        # 亮度和饱和度
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(params.get("brightness", 1.0))
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(params.get("saturation", 1.0))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(params.get("contrast", 1.0))
        # 模糊
        blur = params.get("blur", 0.0)
        if blur > 0.01:
            r = max(1, int(blur * 3))
            img = img.filter(ImageFilter.GaussianBlur(radius=r))
        # 雾/霾
        haze = params.get("haze", 0.0)
        if haze > 0.01:
            haze_layer = Image.new("RGB", img.size, (220, 220, 230))
            img = Image.blend(img, haze_layer, min(haze, 0.8))
        return img

    def _simulate_material_change(self, img: Image.Image, material: str = "metal",
                                   object_desc: str = "object") -> Image.Image:
        """模拟材质变化"""
        img = img.copy()
        if material in ("metal", "gold", "silver", "chrome", "polished chrome"):
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(2.0)
            # 添加金属光泽（水平条纹）
            arr = np.array(img).astype(np.float32)
            h, w = arr.shape[:2]
            for i in range(h):
                factor = 1.0 + 0.1 * math.sin(i * 0.1)
                arr[i, :] = np.clip(arr[i, :] * factor, 0, 255)
            arr = arr.astype(np.uint8)
            img = Image.fromarray(arr)
        elif material in ("wood", "paper", "fabric", "leather"):
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(0.8)
            # 添加纹理噪声
            arr = np.array(img).astype(np.float32)
            noise = np.random.normal(0, 15, arr.shape).astype(np.float32)
            arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)
        elif material in ("glass", "frosted glass"):
            img = img.filter(ImageFilter.GaussianBlur(radius=2))
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.1)
        elif material == "concrete":
            arr = np.array(img).astype(np.float32)
            gray = np.mean(arr, axis=2, keepdims=True)
            gray = np.tile(gray, (1, 1, 3))
            # 加纹理噪声
            noise = np.random.normal(0, 20, gray.shape).astype(np.float32)
            gray = np.clip(gray + noise, 0, 255).astype(np.uint8)
            img = Image.fromarray(gray)
        return img

    def _simulate_lighting_change(self, img: Image.Image, lighting_type: str = "soft") -> Image.Image:
        """模拟光照变化"""
        params = LIGHTING_PARAMS.get(lighting_type, LIGHTING_PARAMS["soft"])
        img = img.copy()
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(params.get("brightness", 1.0))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(params.get("contrast", 1.0))
        if "saturation" in params:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(params["saturation"])
        if "warmth" in params:
            arr = np.array(img).astype(np.float32)
            arr[:, :, 0] *= (2.0 - params["warmth"])
            arr[:, :, 2] *= params["warmth"]
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)
        if "sharpen" in params and params["sharpen"] > 0:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.0 + params["sharpen"])
        return img

    def _simulate_object_add(self, img: Image.Image, object_desc: str = "a flower") -> Image.Image:
        """模拟添加物体——在图像上画简单形状"""
        img = img.copy()
        draw = ImageDraw.Draw(img)
        w, h = img.size
        # 在随机位置画简单形状
        x = random.randint(w // 4, 3 * w // 4)
        y = random.randint(h // 4, 3 * h // 4)
        size = random.randint(15, 40)
        color = random.choice(list(EDIT_COLORS.values()))
        shape_type = random.choice(["ellipse", "rectangle", "polygon"])
        if shape_type == "ellipse":
            draw.ellipse([x - size, y - size, x + size, y + size], fill=color, outline=(0, 0, 0))
        elif shape_type == "rectangle":
            draw.rectangle([x - size, y - size, x + size, y + size], fill=color, outline=(0, 0, 0))
        else:
            pts = [(x, y - size), (x + size, y + size // 2), (x - size, y + size // 2)]
            draw.polygon(pts, fill=color, outline=(0, 0, 0))
        return img

    def _simulate_object_resize(self, img: Image.Image, larger: bool = True) -> Image.Image:
        """模拟物体放大/缩小——中心裁剪或填充"""
        w, h = img.size
        if larger:
            # 放大：中心裁剪放大
            scale = 0.7
            nw, nh = int(w * scale), int(h * scale)
            x = (w - nw) // 2
            y = (h - nh) // 2
            cropped = img.crop((x, y, x + nw, y + nh))
            return cropped.resize((w, h), Image.LANCZOS)
        else:
            # 缩小：缩小后居中放在画布上
            scale = 0.7
            nw, nh = int(w * scale), int(h * scale)
            resized = img.resize((nw, nh), Image.LANCZOS)
            result = Image.new("RGB", (w, h), (128, 128, 128))
            x, y = (w - nw) // 2, (h - nh) // 2
            result.paste(resized, (x, y))
            return result

    def _simulate_object_move(self, img: Image.Image, position: str = "left") -> Image.Image:
        """模拟物体移动——平移图像内容"""
        w, h = img.size
        shift_x, shift_y = 0, 0
        if position == "left":
            shift_x = -w // 4
        elif position == "right":
            shift_x = w // 4
        elif position == "top":
            shift_y = -h // 4
        elif position == "bottom":
            shift_y = h // 4
        elif position == "corner":
            shift_x, shift_y = w // 4, h // 4
        # 使用偏移变换
        result = Image.new("RGB", (w, h), (128, 128, 128))
        result.paste(img, (shift_x, shift_y))
        return result

    def _simulate_lighting_dramatic(self, img: Image.Image) -> Image.Image:
        """模拟戏剧化光照（强明暗对比）"""
        img = img.copy()
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.8)
        # 添加径向渐暗效果（暗角）
        w, h = img.size
        mask = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(mask)
        cx, cy = w // 2, h // 2
        max_r = math.sqrt(cx**2 + cy**2)
        for y in range(h):
            for x in range(w):
                dist = math.sqrt((x - cx)**2 + (y - cy)**2)
                factor = max(0, 1 - (dist / max_r) * 0.6)
                draw.point((x, y), fill=int(255 * factor))
        dark = Image.new("RGB", (w, h), (0, 0, 0))
        img = Image.composite(img, dark, mask)
        return img

    # ========================================================================
    # 指令生成
    # ========================================================================

    def _generate_instruction(self, edit_type: str, template_vars: Dict[str, str] = None) -> str:
        """从模板生成编辑指令"""
        if edit_type not in EDIT_TYPE_TAXONOMY:
            return f"Apply {edit_type} edit to the image"
        templates = EDIT_TYPE_TAXONOMY[edit_type]["templates"]
        template = random.choice(templates)
        if template_vars:
            try:
                return template.format(**template_vars)
            except KeyError:
                pass
        return template

    def _generate_caption(self, img: Image.Image, edit_type: str, params: Dict[str, Any]) -> str:
        """基于编辑类型生成原始/目标描述"""
        info = self._get_image_info(img)
        if edit_type == "color_change":
            target_color = params.get("color", "red")
            return f"An image with its dominant color shifted to {target_color}"
        elif edit_type == "background_replace":
            bg = params.get("new_bg", "a beach")
            return f"An image with the background replaced by {bg}"
        elif edit_type == "style_transfer":
            style = params.get("style", "vintage")
            return f"An image transformed with {style} style"
        elif edit_type == "season_change":
            season = params.get("season", "autumn")
            return f"A scene transformed to {season}"
        elif edit_type == "time_change":
            time_of_day = params.get("time_of_day", "sunset")
            return f"A scene with {time_of_day} lighting"
        elif edit_type == "weather_change":
            weather = params.get("weather", "rainy")
            return f"A scene with {weather} weather"
        else:
            brightness_desc = "bright" if info["brightness"] > 0.6 else "dark" if info["brightness"] < 0.3 else "moderately lit"
            return f"An image with {edit_type} applied, {brightness_desc}, {info['width']}x{info['height']}"

    # ========================================================================
    # 主要入口：为单张图像生成编辑指令
    # ========================================================================

    def generate_edit(
        self,
        source_image: Union[str, Image.Image, np.ndarray],
        edit_type: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[EditInstructionItem]:
        """
        为单张图像生成一条编辑指令数据

        Args:
            source_image: 输入图像
            edit_type: 编辑类型 (None=随机选择)
            params: 编辑参数 (None=自动生成)

        Returns:
            EditInstructionItem or None
        """
        img = self._load_image(source_image)
        if img is None:
            return None

        if edit_type is None:
            edit_type = random.choice(self.edit_types)
        if params is None:
            params = self._generate_params(edit_type)

        # 生成模拟编辑效果
        edited = self._apply_edit(img, edit_type, params)
        if edited is None:
            return None

        # 生成指令
        instruction = self._generate_instruction(edit_type, params)

        # 生成caption
        source_caption = self._generate_caption(img, edit_type, params)
        target_caption = self._generate_caption(edited, edit_type, params)

        item_id = f"edit_{uuid.uuid4().hex[:8]}"

        return EditInstructionItem(
            id=item_id,
            source_image=str(source_image) if isinstance(source_image, str) else "",
            edited_image="",  # 实际使用时由ComfyUI/API填充
            instruction=instruction,
            edit_type=edit_type,
            source_caption=source_caption,
            target_caption=target_caption,
            metadata={
                "width": img.width,
                "height": img.height,
                "params": params,
            },
        )

    def _generate_params(self, edit_type: str) -> Dict[str, Any]:
        """为编辑类型自动生成参数"""
        params = {}
        if edit_type == "color_change":
            params["color"] = random.choice(list(EDIT_COLORS.keys()))
            params["object"] = random.choice(COMMON_OBJECTS)
        elif edit_type == "background_replace":
            params["new_bg"] = random.choice(NEW_BG_OPTIONS)
        elif edit_type == "background_blur":
            params["blur_radius"] = random.randint(5, 20)
        elif edit_type in ("object_add", "object_remove", "object_replace"):
            params["object"] = random.choice(COMMON_OBJECTS)
            if edit_type == "object_replace":
                params["new_object"] = random.choice(COMMON_OBJECTS)
        elif edit_type == "object_resize":
            params["object"] = random.choice(COMMON_OBJECTS)
            params["direction"] = random.choice(["larger", "smaller"])
        elif edit_type == "object_move":
            params["object"] = random.choice(COMMON_OBJECTS)
            params["position"] = random.choice(POSITION_OPTIONS)
        elif edit_type == "style_transfer":
            params["style"] = random.choice(STYLE_OPTIONS)
        elif edit_type == "season_change":
            params["season"] = random.choice(list(SEASON_PARAMS.keys()))
        elif edit_type == "time_change":
            params["time_of_day"] = random.choice(list(TIME_PARAMS.keys()))
        elif edit_type == "material_change":
            params["object"] = random.choice(COMMON_OBJECTS)
            params["material"] = random.choice(MATERIAL_OPTIONS)
        elif edit_type == "weather_change":
            params["weather"] = random.choice(list(WEATHER_PARAMS.keys()))
        elif edit_type == "lighting_adjust":
            params["lighting_type"] = random.choice(list(LIGHTING_PARAMS.keys()))
        elif edit_type in ("color_saturation", "color_temperature"):
            params["direction"] = random.choice(["increase", "decrease"])
        return params

    def _apply_edit(self, img: Image.Image, edit_type: str,
                     params: Dict[str, Any]) -> Optional[Image.Image]:
        """应用编辑效果到图像"""
        if edit_type == "color_change":
            return self._simulate_color_change(img, params.get("color", "red"),
                                                params.get("object", "object"))
        elif edit_type == "color_saturation":
            increase = params.get("direction", "increase") == "increase"
            return self._simulate_saturation_change(img, increase)
        elif edit_type == "color_temperature":
            warmer = params.get("direction", "increase") == "increase"
            return self._simulate_temperature_change(img, warmer)
        elif edit_type == "background_replace":
            return self._simulate_background_remove(img)
        elif edit_type == "background_blur":
            return self._simulate_background_blur(img, params.get("blur_radius", 10))
        elif edit_type == "background_remove":
            return self._simulate_background_remove(img)
        elif edit_type == "object_add":
            return self._simulate_object_add(img, params.get("object", "a flower"))
        elif edit_type == "object_remove":
            return self._simulate_object_remove(img)
        elif edit_type == "object_replace":
            return self._simulate_object_add(img, params.get("new_object", "a new object"))
        elif edit_type == "object_resize":
            larger = params.get("direction", "larger") == "larger"
            return self._simulate_object_resize(img, larger)
        elif edit_type == "object_move":
            return self._simulate_object_move(img, params.get("position", "left"))
        elif edit_type == "style_transfer":
            return self._simulate_style_transfer(img, params.get("style", "vintage"))
        elif edit_type in ("style_cartoon",):
            return self._simulate_cartoon(img)
        elif edit_type == "style_painting":
            return self._simulate_style_transfer(img, "vintage")
        elif edit_type == "season_change":
            return self._simulate_season_change(img, params.get("season", "autumn"))
        elif edit_type == "time_change":
            return self._simulate_time_change(img, params.get("time_of_day", "sunset"))
        elif edit_type == "material_change":
            return self._simulate_material_change(img, params.get("material", "metal"),
                                                   params.get("object", "object"))
        elif edit_type == "weather_change":
            return self._simulate_weather_change(img, params.get("weather", "rainy"))
        elif edit_type == "lighting_adjust":
            return self._simulate_lighting_change(img, params.get("lighting_type", "soft"))
        elif edit_type == "lighting_dramatic":
            return self._simulate_lighting_dramatic(img)
        else:
            logger.warning(f"Unknown edit type: {edit_type}")
            return None

    # ========================================================================
    # 批量生成
    # ========================================================================

    def batch_generate(self, images: List[Union[str, Image.Image]],
                       edit_types: Optional[List[str]] = None,
                       n_per_image: int = 1) -> List[EditInstructionItem]:
        """
        批量生成编辑指令

        Args:
            images: 图像列表
            edit_types: 编辑类型列表 (None=全部类型)
            n_per_image: 每张图像生成数

        Returns:
            EditInstructionItem 列表
        """
        results = []
        if edit_types is None:
            edit_types = self.edit_types
        for img in images:
            for _ in range(n_per_image):
                edit_type = random.choice(edit_types)
                item = self.generate_edit(img, edit_type)
                if item is not None:
                    results.append(item)
        return results

    def generate_all_types(self, image: Union[str, Image.Image]) -> List[EditInstructionItem]:
        """为单张图像生成所有编辑类型的指令"""
        results = []
        for edit_type in self.edit_types:
            item = self.generate_edit(image, edit_type)
            if item is not None:
                results.append(item)
        return results

    # ========================================================================
    # 保存格式
    # ========================================================================

    def save_instructpix2pix_jsonl(self, items: List[EditInstructionItem], output_path: str):
        """
        保存为InstructPix2Pix格式JSONL

        格式: {input_image, edited_image, instruction}
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                record = {
                    "input_image": item.source_image,
                    "edited_image": item.edited_image,
                    "instruction": item.instruction,
                    "edit_type": item.edit_type,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} InstructPix2Pix items to {output_path}")

    def save_ultraedit_jsonl(self, items: List[EditInstructionItem], output_path: str):
        """
        保存为UltraEdit格式JSONL

        格式: {original_image, edited_image, instruction, source_caption, target_caption}
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                record = {
                    "original_image": item.source_image,
                    "edited_image": item.edited_image,
                    "instruction": item.instruction,
                    "source_caption": item.source_caption,
                    "target_caption": item.target_caption,
                    "edit_type": item.edit_type,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} UltraEdit items to {output_path}")

    def save_anyedit_jsonl(self, items: List[EditInstructionItem], output_path: str):
        """
        保存为AnyEdit格式JSONL

        格式: {source, target, instruction, edit_type}
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                record = {
                    "source": item.source_image,
                    "target": item.edited_image,
                    "instruction": item.instruction,
                    "edit_type": item.edit_type,
                    "source_caption": item.source_caption,
                    "target_caption": item.target_caption,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Saved {len(items)} AnyEdit items to {output_path}")


# ============================================================================
# Convenience
# ============================================================================

def get_edit_pipeline() -> EditInstructionPipeline:
    """获取编辑指令管线实例"""
    return EditInstructionPipeline()
