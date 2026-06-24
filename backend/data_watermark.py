"""
NanoBot Factory - 数据水印与版权保护引擎
Data Watermark & Copyright Protection

支持：
- 可见水印添加/去除
- 不可见水印嵌入/检测 (DWT-based)
- 版权追溯
- NSFW过滤
"""
import os, json, logging, hashlib, struct, time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import threading

logger = logging.getLogger(__name__)

# ============================================================================
# 水印数据结构
# ============================================================================

@dataclass
class WatermarkResult:
    """水印操作结果"""
    success: bool = False
    output_path: str = ""
    watermark_id: str = ""
    confidence: float = 0.0
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CopyrightRecord:
    """版权记录"""
    image_id: str
    watermark_id: str
    owner: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

# ============================================================================
# 可见水印引擎
# ============================================================================

class VisibleWatermark:
    """可见水印 - 文字/Logo叠加"""
    
    @staticmethod
    def add_text_watermark(
        image: Image.Image,
        text: str = "NanoBot",
        position: str = "bottom-right",
        opacity: float = 0.3,
        font_size: int = 36,
        color: Tuple[int, int, int] = (255, 255, 255),
        rotation: float = 0,
        tile: bool = False
    ) -> Image.Image:
        """添加文字水印"""
        img = image.copy()
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # 尝试加载字体，失败用默认
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]
        font = ImageFont.load_default()
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except (OSError, IOError):
                continue
        
        # 计算文本尺寸
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = 20
        
        # 定位
        positions = {
            "top-left": (margin, margin),
            "top-right": (img.width - text_w - margin, margin),
            "bottom-left": (margin, img.height - text_h - margin),
            "bottom-right": (img.width - text_w - margin, img.height - text_h - margin),
            "center": ((img.width - text_w) // 2, (img.height - text_h) // 2),
        }
        pos = positions.get(position, positions["bottom-right"])
        
        # 绘制文字
        alpha = int(255 * opacity)
        fill_color = (*color, alpha)
        draw.text(pos, text, font=font, fill=fill_color)
        
        # 旋转
        if rotation != 0:
            overlay = overlay.rotate(rotation, expand=False, center=(img.width//2, img.height//2))
        
        # 合成
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        return img
    
    @staticmethod
    def add_logo_watermark(
        image: Image.Image,
        logo: Union[str, Image.Image],
        position: str = "bottom-right",
        opacity: float = 0.5,
        scale: float = 0.15
    ) -> Image.Image:
        """添加Logo水印"""
        img = image.copy().convert("RGBA")
        
        # 加载logo
        if isinstance(logo, str):
            logo = Image.open(logo).convert("RGBA")
        
        # 按比例缩放
        logo_w = int(img.width * scale)
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        
        # 透明度
        logo.putalpha(int(255 * opacity))
        
        # 定位
        margin = 15
        positions = {
            "top-left": (margin, margin),
            "top-right": (img.width - logo_w - margin, margin),
            "bottom-left": (margin, img.height - logo_h - margin),
            "bottom-right": (img.width - logo_w - margin, img.height - logo_h - margin),
            "center": ((img.width - logo_w) // 2, (img.height - logo_h) // 2),
        }
        pos = positions.get(position, positions["bottom-right"])
        
        # 合成
        img.paste(logo, pos, logo)
        return img.convert("RGB")
    
    @staticmethod
    def remove_watermark_inpaint(image: Image.Image, 
                                   region: Optional[Tuple[int,int,int,int]] = None) -> Image.Image:
        """尝试去除水印（简单修补）"""
        import cv2
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        mask = np.zeros(img.shape[:2], np.uint8)
        
        if region:
            x, y, w, h = region
            mask[y:y+h, x:x+w] = 255
        else:
            # 自动检测水印区域（右下角常见）
            h, w = img.shape[:2]
            mask[int(h*0.85):h, int(w*0.7):w] = 255
        
        # 用cv2的inpaint修复
        result = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
        return Image.fromarray(result_rgb)


# ============================================================================
# 不可见水印 (DWT-based / LSB)
# ============================================================================

class InvisibleWatermark:
    """不可见水印 - DWT算法 + LSB混合"""
    
    @staticmethod
    def _compute_signature(message: str) -> np.ndarray:
        """将消息转换为水印签名数组 (64-bit)"""
        sig = np.zeros(64, dtype=np.float32)
        h = hashlib.sha256(message.encode()).digest()
        for i in range(64):
            sig[i] = 1.0 if (h[i // 8] >> (i % 8)) & 1 else -1.0
        return sig
    
    @staticmethod
    def embed_dwt(image: Image.Image, message: str, strength: float = 0.5) -> Image.Image:
        """DWT域不可见水印嵌入
        
        使用OpenCV DWT近似（小波变换域中嵌入签名）
        """
        import cv2
        arr = np.array(image.convert("RGB"), dtype=np.float32)
        
        # 对每个通道做DWT（用DCT代替近似）
        watermark = InvisibleWatermark._compute_signature(message)
        
        result = np.zeros_like(arr)
        
        for c in range(3):
            chan = arr[:, :, c]
            h, w = chan.shape
            
            # 裁剪到偶数大小
            h_even = h - (h % 2)
            w_even = w - (w % 2)
            chan = chan[:h_even, :w_even]
            
            # OpenCV DCT
            dct = cv2.dct(chan)
            
            # 在中频区域嵌入水印
            mid_freq_start = 4
            sig_len = min(64, min(h_even, w_even) - mid_freq_start)
            
            for i in range(sig_len):
                dct[mid_freq_start + i, mid_freq_start] += watermark[i] * strength
            
            # IDCT
            chan_watermarked = cv2.idct(dct)
            
            # 放回
            result[:h_even, :w_even, c] = chan_watermarked
            if h_even < h:
                result[h_even:, :, c] = arr[h_even:, :, c]
            if w_even < w:
                result[:, w_even:, c] = arr[:, w_even:, c]
        
        result = np.clip(result, 0, 255).astype(np.uint8)
        return Image.fromarray(result)
    
    @staticmethod
    def detect_dwt(image: Image.Image, message: str) -> WatermarkResult:
        """DWT域水印检测 - 返回置信度"""
        import cv2
        arr = np.array(image.convert("RGB"), dtype=np.float32)
        watermark = InvisibleWatermark._compute_signature(message)
        
        detections = []
        for c in range(3):
            chan = arr[:, :, c]
            h, w = chan.shape
            chan = chan[:h-(h%2), :w-(w%2)]
            
            dct = cv2.dct(chan)
            
            mid_freq_start = 4
            sig_len = min(64, min(h, w) - mid_freq_start)
            
            detected = np.zeros(sig_len)
            for i in range(sig_len):
                detected[i] = dct[mid_freq_start + i, mid_freq_start]
            
            # 相关性
            correlation = np.dot(detected[:len(watermark)], watermark[:len(detected)])
            correlation /= (np.linalg.norm(detected) * np.linalg.norm(watermark) + 1e-8)
            detections.append(correlation)
        
        confidence = float(np.mean(detections))
        return WatermarkResult(
            success=confidence > 0.3,
            confidence=confidence,
            message=f"Watermark detection confidence: {confidence:.4f}"
        )


# ============================================================================
# LSB 水印（简单但鲁棒性差）
# ============================================================================

class LSBWatermark:
    """LSB隐写水印 - 用于短消息嵌入"""
    
    @staticmethod
    def embed(image: Image.Image, data: bytes) -> Image.Image:
        """在图像LSB中嵌入数据"""
        arr = np.array(image.convert("RGB"))
        flat = arr.flatten()
        
        # 前32bits存储数据长度
        length_bits = len(data).to_bytes(4, 'big')
        payload = length_bits + data
        payload_bits = ''.join(format(b, '08b') for b in payload)
        
        if len(payload_bits) > len(flat):
            raise ValueError(f"Data too long: {len(data)} bytes, max {len(flat)//8 - 4}")
        
        # 嵌入
        for i, bit in enumerate(payload_bits):
            flat[i] = (flat[i] & 0xFE) | int(bit)
        
        return Image.fromarray(flat.reshape(arr.shape).astype(np.uint8))
    
    @staticmethod
    def extract(image: Image.Image) -> bytes:
        """从图像LSB中提取数据"""
        arr = np.array(image.convert("RGB"))
        flat = arr.flatten()
        
        # 提取长度
        length_bits = ''.join(str(flat[i] & 1) for i in range(32))
        data_length = int(length_bits, 2)
        
        if data_length <= 0 or data_length > 1024 * 1024:
            return b""
        
        # 提取数据
        data_bits = ''.join(str(flat[i+32] & 1) for i in range(data_length * 8))
        
        data = bytes(int(data_bits[i*8:(i+1)*8], 2) for i in range(data_length))
        return data


# ============================================================================
# 版权管理
# ============================================================================

class CopyrightManager:
    """版权管理系统"""
    
    def __init__(self, db_path: str = "./data/copyright_db.json"):
        self.db_path = db_path
        self._records: List[CopyrightRecord] = []
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path) as f:
                    data = json.load(f)
                    self._records = [CopyrightRecord(**r) for r in data]
            except Exception as e:
                logger.warning(f"Failed to load copyright DB: {e}")
    
    def _save(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with open(self.db_path, "w") as f:
            json.dump([r.__dict__ for r in self._records], f, indent=2)
    
    def register(self, image_id: str, owner: str, 
                  metadata: Dict = None) -> CopyrightRecord:
        """注册版权"""
        record = CopyrightRecord(
            image_id=image_id,
            watermark_id=hashlib.sha256(f"{image_id}:{owner}:{time.time()}".encode()).hexdigest()[:16],
            owner=owner,
            metadata=metadata or {}
        )
        with self._lock:
            self._records.append(record)
            self._save()
        return record
    
    def lookup(self, image_id: str) -> Optional[CopyrightRecord]:
        """查询版权"""
        for r in self._records:
            if r.image_id == image_id:
                return r
        return None
    
    def list_by_owner(self, owner: str) -> List[CopyrightRecord]:
        """按所有者查询"""
        return [r for r in self._records if r.owner == owner]


# ============================================================================
# 综合水印引擎
# ============================================================================

class WatermarkEngine:
    """综合水印引擎"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.copyright_mgr = CopyrightManager(self.config.get("db_path", "./data/copyright_db.json"))
        
    def process_output(self, image: Image.Image, 
                        owner: str = "default",
                        image_id: str = "",
                        add_visible: bool = True,
                        add_invisible: bool = True) -> Tuple[Image.Image, WatermarkResult]:
        """处理生成输出的完整水印流水线"""
        if not image_id:
            image_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
        
        result = WatermarkResult()
        
        # 1. 可见水印
        if add_visible:
            text = self.config.get("watermark_text", "NanoBot")
            image = VisibleWatermark.add_text_watermark(
                image, text=text, opacity=0.2, font_size=24
            )
        
        # 2. 不可见水印
        if add_invisible:
            msg = f"{image_id}:{owner}"
            image = InvisibleWatermark.embed_dwt(image, msg, strength=0.3)
        
        # 3. 注册版权
        record = self.copyright_mgr.register(
            image_id=image_id,
            owner=owner,
            metadata={"watermark_text": text if add_visible else ""}
        )
        
        result.success = True
        result.watermark_id = record.watermark_id
        
        return image, result
    
    def verify_watermark(self, image: Image.Image, 
                          watermark_id: str) -> bool:
        """验证水印"""
        msg = f":{watermark_id}"
        # 尝试各种可能的所有者
        records = self.copyright_mgr._records
        for r in records:
            if r.watermark_id == watermark_id:
                result = InvisibleWatermark.detect_dwt(image, f"{r.image_id}:{r.owner}")
                return result.confidence > 0.3
        return False
