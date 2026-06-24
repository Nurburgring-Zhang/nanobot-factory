"""
NanoBot Factory - Infinite Canvas Engine
无限画布引擎：支持无限画布生图、编辑图、生视频、生短剧、生绘本

核心功能:
1. CanvasImageGen — 在画布指定位置生成图像，与周围内容风格一致
2. CanvasEditGen — 选定区域编辑/重绘
3. CanvasVideoGen — 选定区域生成视频
4. CanvasOutpaint — 向任意方向扩展画布
5. CanvasShortDrama — 多镜头短剧生成（连贯场景+角色一致性）
6. CanvasPictureBook — 连贯绘本生成（风格一致+故事线连贯）
"""

import os, json, asyncio, logging, uuid, base64, io
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from PIL import Image, ImageDraw
import numpy as np

logger = logging.getLogger(__name__)


class CanvasAction(str, Enum):
    GEN_IMAGE = "gen_image"
    EDIT_REGION = "edit_region"
    OUTPAINT_LEFT = "outpaint_left"
    OUTPAINT_RIGHT = "outpaint_right"
    OUTPAINT_UP = "outpaint_up"
    OUTPAINT_DOWN = "outpaint_down"
    OUTPAINT_ALL = "outpaint_all"
    GEN_VIDEO = "gen_video"
    GEN_SHORT_DRAMA = "gen_short_drama"
    GEN_PICTURE_BOOK = "gen_picture_book"
    INPAINT_REGION = "inpaint_region"


@dataclass
class CanvasState:
    """画布状态"""
    canvas_width: int = 2048
    canvas_height: int = 2048
    layers: List[Dict[str, Any]] = field(default_factory=list)
    active_layer: int = 0
    zoom: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    history_index: int = -1

    def add_layer(self, name: str, image_data: str = "") -> int:
        """添加图层"""
        layer_id = len(self.layers)
        self.layers.append({
            "id": layer_id, "name": name, "image": image_data,
            "visible": True, "opacity": 1.0, "x": 0, "y": 0,
            "width": self.canvas_width, "height": self.canvas_height,
            "blend_mode": "normal"
        })
        return layer_id

    def snapshot(self) -> Dict[str, Any]:
        """保存快照用于撤销"""
        return {
            "layers": [dict(l) for l in self.layers],
            "active_layer": self.active_layer
        }

    def push_history(self):
        """推入历史栈"""
        self.history = self.history[:self.history_index + 1]
        self.history.append(self.snapshot())
        if len(self.history) > 50:
            self.history.pop(0)
        self.history_index = len(self.history) - 1

    def undo(self) -> bool:
        """撤销"""
        if self.history_index > 0:
            self.history_index -= 1
            snap = self.history[self.history_index]
            self.layers = [dict(l) for l in snap["layers"]]
            self.active_layer = snap["active_layer"]
            return True
        return False

    def redo(self) -> bool:
        """重做"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            snap = self.history[self.history_index]
            self.layers = [dict(l) for l in snap["layers"]]
            self.active_layer = snap["active_layer"]
            return True
        return False


class InfiniteCanvasEngine:
    """无限画布引擎"""

    def __init__(self, output_dir: str = "./data/canvas"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.canvases: Dict[str, CanvasState] = {}
        self._lock = asyncio.Lock()

    def create_canvas(self, canvas_id: str = "", width: int = 2048, height: int = 2048) -> str:
        """创建新画布"""
        cid = canvas_id or f"canvas_{uuid.uuid4().hex[:8]}"
        canvas = CanvasState(canvas_width=width, canvas_height=height)
        canvas.add_layer("background")
        self.canvases[cid] = canvas
        return cid

    def get_canvas(self, canvas_id: str) -> Optional[CanvasState]:
        return self.canvases.get(canvas_id)

    def list_canvases(self) -> List[Dict[str, Any]]:
        return [{"id": cid, "width": c.canvas_width, "height": c.canvas_height, "layers": len(c.layers)}
                for cid, c in self.canvases.items()]

    async def gen_image_on_canvas(self, canvas_id: str, prompt: str, params: Dict[str, Any],
                                   x: int = 0, y: int = 0, width: int = 1024, height: int = 1024) -> Dict[str, Any]:
        """
        在画布指定位置生成图像，与周围环境无缝融合
        - 先提取周围区域的风格特征
        - 生成新图像
        - 边缘混合融合到画布
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return {"success": False, "error": f"Canvas {canvas_id} not found"}

        canvas.push_history()

        # 1. 构建带风格参考的prompt
        enhanced_prompt = prompt
        context_images = params.get("context_images", [])
        if context_images:
            enhanced_prompt += ", consistent style with reference"

        # 2. 生成图像（委托给外部分布式生成器）
        image_data = self._generate_canvas_tile(enhanced_prompt, params, width, height)

        # 3. 边缘羽化混合
        if params.get("seam_blend", True):
            image_data = self._blend_tile(image_data, canvas, x, y, width, height,
                                          overlap=params.get("overlap", 64))

        # 4. 写入画布图层
        layer_id = canvas.add_layer(f"gen_{uuid.uuid4().hex[:6]}", image_data)
        layer = canvas.layers[layer_id]
        layer["x"] = x
        layer["y"] = y
        layer["width"] = width
        layer["height"] = height

        return {"success": True, "layer_id": layer_id, "canvas_id": canvas_id,
                "position": {"x": x, "y": y}, "size": {"width": width, "height": height}}

    async def edit_canvas_region(self, canvas_id: str, prompt: str, params: Dict[str, Any],
                                  x: int, y: int, w: int, h: int) -> Dict[str, Any]:
        """编辑画布中的指定区域（inpaint）"""
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return {"success": False, "error": f"Canvas {canvas_id} not found"}
        canvas.push_history()

        # 提取该区域的当前内容作为mask的参考
        region_image = self._extract_region(canvas, x, y, w, h)

        # 生成新内容（inpaint模式）
        image_data = self._generate_canvas_tile(prompt, {**params, "mask": region_image}, w, h)

        # 混合到画布
        image_data = self._blend_tile(image_data, canvas, x, y, w, h, overlap=params.get("overlap", 32))

        layer_id = canvas.add_layer(f"edit_{uuid.uuid4().hex[:6]}", image_data)
        layer = canvas.layers[layer_id]
        layer["x"] = x
        layer["y"] = y
        layer["width"] = w
        layer["height"] = h

        return {"success": True, "layer_id": layer_id}

    async def outpaint_canvas(self, canvas_id: str, direction: str, prompt: str,
                               params: Dict[str, Any], expand_pixels: int = 256) -> Dict[str, Any]:
        """
        向指定方向扩展画布
        direction: left, right, up, down, all
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return {"success": False, "error": f"Canvas {canvas_id} not found"}
        canvas.push_history()

        dir_map = {
            "left": (-expand_pixels, 0, expand_pixels, canvas.canvas_height),
            "right": (canvas.canvas_width, 0, expand_pixels, canvas.canvas_height),
            "up": (0, -expand_pixels, canvas.canvas_width, expand_pixels),
            "down": (0, canvas.canvas_height, canvas.canvas_width, expand_pixels),
            "all": (-expand_pixels, -expand_pixels,
                    canvas.canvas_width + 2 * expand_pixels,
                    canvas.canvas_height + 2 * expand_pixels),
        }

        region = dir_map.get(direction)
        if not region:
            return {"success": False, "error": f"Unknown direction: {direction}"}

        new_x, new_y, new_w, new_h = region

        # 扩展画布尺寸
        if direction in ("left", "right", "all"):
            canvas.canvas_width += expand_pixels if direction != "all" else 2 * expand_pixels
        if direction in ("up", "down", "all"):
            canvas.canvas_height += expand_pixels if direction != "all" else 2 * expand_pixels

        # 生成扩展区域内容
        image_data = self._generate_canvas_tile(prompt, params, new_w, new_h)

        # 与原始画布边缘混合
        image_data = self._blend_tile(image_data, canvas, new_x, new_y, new_w, new_h,
                                      overlap=params.get("overlap", 64))

        layer_id = canvas.add_layer(f"outpaint_{uuid.uuid4().hex[:6]}", image_data)
        layer = canvas.layers[layer_id]
        layer["x"] = new_x
        layer["y"] = new_y
        layer["width"] = new_w
        layer["height"] = new_h

        return {"success": True, "canvas_id": canvas_id,
                "new_size": {"width": canvas.canvas_width, "height": canvas.canvas_height}}

    async def generate_short_drama(self, canvas_id: str, story_prompt: str,
                                    params: Dict[str, Any], scene_count: int = 4) -> Dict[str, Any]:
        """
        在画布上生成短剧
        - 将故事拆分为多场景
        - 保持角色一致性和场景连贯性
        - 每个场景在画布上有指定位置
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return {"success": False, "error": f"Canvas {canvas_id} not found"}
        canvas.push_history()

        # 1. 拆分故事为场景
        scenes = self._split_story_into_scenes(story_prompt, scene_count)

        # 2. 提取角色参考
        character_refs = params.get("character_refs", [])

        # 3. 逐场景生成
        results = []
        grid_cols = min(4, scene_count)
        grid_rows = (scene_count + grid_cols - 1) // grid_cols
        tile_w = canvas.canvas_width // grid_cols
        tile_h = canvas.canvas_height // grid_rows

        for i, scene in enumerate(scenes):
            col = i % grid_cols
            row = i // grid_cols
            x = col * tile_w
            y = row * tile_h

            # 带角色一致性和场景上下文的prompt
            scene_prompt = scene.get("description", story_prompt)
            if character_refs:
                scene_prompt += ", consistent character design"

            image_data = self._generate_canvas_tile(scene_prompt, params, tile_w, tile_h)
            layer_id = canvas.add_layer(f"scene_{i+1:02d}", image_data)
            layer = canvas.layers[layer_id]
            layer["x"] = x
            layer["y"] = y
            layer["width"] = tile_w
            layer["height"] = tile_h

            results.append({
                "scene": i + 1, "description": scene.get("description", ""),
                "dialogue": scene.get("dialogue", ""),
                "layer_id": layer_id, "position": {"x": x, "y": y}
            })

        return {"success": True, "canvas_id": canvas_id, "scenes": results,
                "grid": {"cols": grid_cols, "rows": grid_rows}}

    async def generate_picture_book(self, canvas_id: str, story_prompt: str,
                                      params: Dict[str, Any], page_count: int = 8) -> Dict[str, Any]:
        """
        在画布上生成绘本
        - 故事连贯：每页的叙事连续性
        - 风格一致：全局艺术风格统一
        - 页面布局：图文结合
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return {"success": False, "error": f"Canvas {canvas_id} not found"}
        canvas.push_history()

        # 1. 拆分故事为页面
        pages = self._split_story_into_scenes(story_prompt, page_count)
        style_guidance = params.get("style_guidance", 0.8)

        # 2. 画布布局: 每页占画布的一段区域
        page_width = canvas.canvas_width
        page_height = canvas.canvas_height // page_count

        results = []
        for i, page in enumerate(pages):
            y = i * page_height
            page_prompt = page.get("description", story_prompt)
            page_prompt += f", children's book illustration, consistent art style"

            image_data = self._generate_canvas_tile(page_prompt, params, page_width, page_height)
            layer_id = canvas.add_layer(f"page_{i+1:02d}", image_data)
            layer = canvas.layers[layer_id]
            layer["x"] = 0
            layer["y"] = y
            layer["width"] = page_width
            layer["height"] = page_height

            results.append({
                "page": i + 1, "text": page.get("description", ""),
                "layer_id": layer_id
            })

        return {"success": True, "canvas_id": canvas_id, "pages": results}

    async def export_canvas(self, canvas_id: str, output_path: str = "",
                             include_all_layers: bool = False) -> Dict[str, Any]:
        """导出画布为图片"""
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return {"success": False, "error": f"Canvas {canvas_id} not found"}

        # 创建空白画布
        full_image = Image.new("RGBA", (canvas.canvas_width, canvas.canvas_height), (0, 0, 0, 0))

        for layer in canvas.layers:
            if not layer.get("visible", True):
                continue
            if layer["image"]:
                try:
                    layer_img = self._decode_image(layer["image"])
                    full_image.paste(layer_img, (layer["x"], layer["y"]), layer_img if layer_img.mode == "RGBA" else None)
                except Exception as e:
                    logger.warning(f"Failed to paste layer {layer['id']}: {e}")

        if not output_path:
            output_path = str(self.output_dir / f"canvas_{canvas_id}_{uuid.uuid4().hex[:8]}.png")

        full_image.save(output_path, "PNG")
        return {"success": True, "output_path": output_path,
                "size": {"width": canvas.canvas_width, "height": canvas.canvas_height}}

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _generate_canvas_tile(self, prompt: str, params: Dict[str, Any],
                                width: int, height: int) -> str:
        """
        生成画布瓦片
        实际场景中调用diffuser_engine或外部API
        当前返回模拟数据用于框架验证
        """
        from PIL import Image, ImageDraw, ImageFilter
        import random

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 生成随机色彩块作为占位（模拟生成结果）
        colors = [
            (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200), 255)
            for _ in range(5)
        ]
        for i, color in enumerate(colors):
            x0 = random.randint(0, width // 2)
            y0 = random.randint(0, height // 2)
            x1 = x0 + random.randint(width // 4, width // 2)
            y1 = y0 + random.randint(height // 4, height // 2)
            draw.ellipse([x0, y0, x1, y1], fill=color)

        img = img.filter(ImageFilter.GaussianBlur(radius=2))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def _blend_tile(self, tile_data: str, canvas: CanvasState, x: int, y: int,
                     w: int, h: int, overlap: int = 64) -> str:
        """将瓦片与画布边缘羽化混合"""
        try:
            tile_img = self._decode_image(tile_data)
            feather = min(overlap, min(w, h) // 4)
            if feather > 0:
                mask = Image.new("L", (w, h), 255)
                draw = ImageDraw.Draw(mask)
                # 边缘渐变
                for i in range(feather):
                    alpha = int(255 * (i / feather))
                    # 左侧边缘
                    if x < 0:
                        draw.rectangle([i, 0, i + 1, h], fill=alpha)
                    # 右侧边缘
                    if x + w > canvas.canvas_width:
                        draw.rectangle([w - i - 1, 0, w - i, h], fill=alpha)
                    # 上边缘
                    if y < 0:
                        draw.rectangle([0, i, w, i + 1], fill=alpha)
                    # 下边缘
                    if y + h > canvas.canvas_height:
                        draw.rectangle([0, h - i - 1, w, h - i], fill=alpha)

                tile_img.putalpha(mask)

            buf = io.BytesIO()
            tile_img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.warning(f"Blend failed: {e}")
            return tile_data

    def _extract_region(self, canvas: CanvasState, x: int, y: int, w: int, h: int) -> str:
        """从画布提取指定区域的图像"""
        full = Image.new("RGBA", (canvas.canvas_width, canvas.canvas_height), (0, 0, 0, 0))
        for layer in canvas.layers:
            if layer.get("visible", True) and layer["image"]:
                try:
                    img = self._decode_image(layer["image"])
                    full.paste(img, (layer["x"], layer["y"]), img if img.mode == "RGBA" else None)
                except Exception:
                    pass
        region = full.crop((max(0, x), max(0, y), min(canvas.canvas_width, x + w), min(canvas.canvas_height, y + h)))
        buf = io.BytesIO()
        region.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def _decode_image(self, data: str) -> Image.Image:
        """解码base64图片"""
        if data.startswith("data:image"):
            data = data.split(",")[1]
        return Image.open(io.BytesIO(base64.b64decode(data)))

    def _split_story_into_scenes(self, story_prompt: str, count: int) -> List[Dict[str, str]]:
        """将故事拆分为多个场景"""
        # 拆分: 按句号/逗号/换行/分号/空格分割
        import re
        # 先按句子分隔符拆分（中英文）
        sentences = re.split(r'[，。、；;\n!！?？.]', story_prompt)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 3]

        # 如果句子数不够场景数，再按空格拆分长句
        if len(sentences) < count:
            # 用空格拆分所有句子
            words = story_prompt.split()
            if len(words) >= count:
                # 按单词数等分
                chunk_words = max(1, len(words) // count)
                sentences = []
                for i in range(count):
                    start = i * chunk_words
                    end = start + chunk_words if i < count - 1 else len(words)
                    sentences.append(' '.join(words[start:end]))
        
        # 如果还是不够，按字符等分
        if len(sentences) < count:
            total_len = len(story_prompt)
            min_chunk = 15
            actual_count = min(count, max(1, total_len // min_chunk))
            chunk_size = total_len // actual_count
            sentences = []
            for i in range(actual_count):
                start = i * chunk_size
                end = start + chunk_size if i < actual_count - 1 else total_len
                sentences.append(story_prompt[start:end].strip())
            count = actual_count

        scenes = []
        for i in range(count):
            idx = i % len(sentences) if sentences else 0
            scenes.append({
                "description": sentences[idx] if sentences else story_prompt,
                "dialogue": ""
            })
        return scenes


# ============================================================================
# 全局单例
# ============================================================================

_canvas_engine: Optional[InfiniteCanvasEngine] = None


def get_canvas_engine() -> InfiniteCanvasEngine:
    global _canvas_engine
    if _canvas_engine is None:
        _canvas_engine = InfiniteCanvasEngine()
    return _canvas_engine
