"""
图像优化增强模块
支持：降噪、锐化、超分、色彩调整

该模块提供了一套完整的图像增强和处理功能，包括：
- ImageEnhanceBackend: 图像增强引擎，支持批量处理、降噪、锐化
- ImageColorEditor: 图像色彩编辑器，支持HSL、饱和度、对比度、亮度调整
- ImageUpscaleEngine: 图像放大引擎，支持多种超分模型

Author: Matrix Agent
Version: 1.0.0
"""

import os
import glob
import logging
from typing import Optional, Callable, Dict, List, Tuple, Union
from pathlib import Path
from enum import Enum
import time
import hashlib

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError as e:
    NUMPY_AVAILABLE = False
    PIL_ERROR = str(e)

# 配置日志记录
logger = logging.getLogger(__name__)


class EnhancementType(Enum):
    """图像增强类型枚举"""
    DENOISE = "denoise"
    SHARPEN = "sharpen"
    SUPER_RESOLUTION = "super_resolution"
    COLOR_CORRECTION = "color_correction"
    ALL = "all"


class UpscaleModel(Enum):
    """超分辨率模型枚举"""
    REAL_ESRGAN = "real_esrgan"
    SWINIR = "swinir"
    LANCZOS = "lanczos"
    BICUBIC = "bicubic"


class ImageEnhanceError(Exception):
    """图像增强模块自定义异常基类"""
    pass


class DenoiseError(ImageEnhanceError):
    """降噪处理错误"""
    pass


class UpscaleError(ImageEnhanceError):
    """图像放大错误"""
    pass


class ColorAdjustError(ImageEnhanceError):
    """色彩调整错误"""
    pass


class ImageEnhanceBackend:
    """
    图像增强引擎

    提供完整的图像增强功能，包括降噪、锐化、细节恢复等。
    支持单张图像处理和批量处理。

    Attributes:
        config (dict): 配置参数字典
        denoise_level (int): 降噪级别 (1-10)
        sharpen_strength (float): 锐化强度 (0.0-3.0)

    Example:
        >>> backend = ImageEnhanceBackend({"denoise_level": 5})
        >>> backend.enhance_image("input.png", "output.png", {"denoise": True, "sharpen": True})
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化图像增强引擎

        Args:
            config: 配置字典，包含以下可选键：
                - denoise_level (int): 降噪级别，范围1-10，默认5
                - sharpen_strength (float): 锐化强度，范围0.0-3.0，默认1.5
                - detail_enhance (bool): 是否启用细节增强，默认True
                - edge_preserve (bool): 是否保留边缘，默认True
        """
        if not NUMPY_AVAILABLE:
            raise ImportError(f"Required dependency not available: {PIL_ERROR}")

        self.config = config or {}
        self.denoise_level = self.config.get("denoise_level", 5)
        self.sharpen_strength = self.config.get("sharpen_strength", 1.5)
        self.detail_enhance = self.config.get("detail_enhance", True)
        self.edge_preserve = self.config.get("edge_preserve", True)

        # 验证参数范围
        self._validate_params()

        logger.info(f"ImageEnhanceBackend initialized with config: {self.config}")

    def _validate_params(self):
        """验证参数是否在有效范围内"""
        if not 1 <= self.denoise_level <= 10:
            raise ValueError(f"denoise_level must be between 1 and 10, got {self.denoise_level}")
        if not 0.0 <= self.sharpen_strength <= 3.0:
            raise ValueError(f"sharpen_strength must be between 0.0 and 3.0, got {self.sharpen_strength}")

    def _get_denoise_filter(self, level: int) -> ImageFilter.Filter:
        """
        根据降噪级别获取对应的滤波器

        Args:
            level: 降噪级别 (1-10)

        Returns:
            PIL ImageFilter对象
        """
        if level <= 3:
            return ImageFilter.SMOOTH
        elif level <= 6:
            return ImageFilter.SMOOTH_MORE
        else:
            return ImageFilter.MedianFilter(size=3)

    def _create_sharpen_kernel(self, strength: float) -> np.ndarray:
        """
        创建锐化卷积核

        Args:
            strength: 锐化强度

        Returns:
            numpy数组，锐化核
        """
        kernel = np.array([
            [-1, -1, -1],
            [-1,  9, -1],
            [-1, -1, -1]
        ], dtype=np.float32)
        # 根据强度调整中心权重
        kernel[1, 1] = 1 + (strength - 1) * 2
        return kernel

    def _edge_preserving_smooth(self, image: Image.Image, strength: int = 2) -> Image.Image:
        """
        边缘保留平滑处理

        Args:
            image: 输入图像
            strength: 平滑强度

        Returns:
            处理后的图像
        """
        # 转换为numpy数组进行处理
        img_array = np.array(image)
        smoothed = self._bilateral_filter(img_array, d=strength, sigma_color=50, sigma_space=50)
        return Image.fromarray(smoothed)

    def _bilateral_filter(self, img_array: np.ndarray, d: int = 5,
                          sigma_color: float = 50, sigma_space: float = 50) -> np.ndarray:
        """
        双边滤波实现

        双边滤波可以在保持边缘的同时进行平滑处理

        Args:
            img_array: 输入图像数组
            d: 滤波半径
            sigma_color: 颜色空间标准差
            sigma_space: 坐标空间标准差

        Returns:
            滤波后的图像数组
        """
        h, w = img_array.shape[:2]
        result = np.zeros_like(img_array)

        # 对每个通道分别处理
        for c in range(img_array.shape[2]):
            channel = img_array[:, :, c].copy()
            for i in range(h):
                for j in range(w):
                    i_min = max(0, i - d)
                    i_max = min(h, i + d + 1)
                    j_min = max(0, j - d)
                    j_max = min(w, j + d + 1)

                    patch = channel[i_min:i_max, j_min:j_max]
                    center_val = channel[i, j]

                    # 计算空间权重和颜色权重
                    space_dist = np.fromfunction(
                        lambda u, v: (u - (i - i_min))**2 + (v - (j - j_min))**2,
                        patch.shape, dtype=float
                    )
                    color_dist = (patch - center_val) ** 2

                    weights = np.exp(-space_dist / (2 * sigma_space**2) -
                                    color_dist / (2 * sigma_color**2))

                    result[i, j, c] = np.sum(patch * weights) / np.sum(weights) if c < img_array.shape[2] else 0

        # 处理灰度图
        if len(img_array.shape) == 2:
            return result[:, :, 0]
        return result

    def _unsharp_mask(self, image: Image.Image, radius: int = 2,
                      amount: float = 1.5, threshold: int = 0) -> Image.Image:
        """
        USM锐化实现

        Args:
            image: 输入图像
            radius: 模糊半径
            amount: 锐化量
            threshold: 锐化阈值

        Returns:
            锐化后的图像
        """
        return image.filter(ImageFilter.UnsharpMask(
            radius=radius, percent=int(amount * 100), threshold=threshold
        ))

    def _detail_enhance(self, image: Image.Image) -> Image.Image:
        """
        细节增强处理

        Args:
            image: 输入图像

        Returns:
            增强后的图像
        """
        # 使用细节增强滤波器
        enhanced = image.filter(ImageFilter.DETAIL)
        # 叠加原始图像增强细节
        return Image.blend(image, enhanced, 0.3)

    def _edge_enhance(self, image: Image.Image) -> Image.Image:
        """
        边缘增强处理

        Args:
            image: 输入图像

        Returns:
            增强后的图像
        """
        return image.filter(ImageFilter.EDGE_ENHANCE)

    def enhance_image(self, image_path: Union[str, Path],
                     output_path: Union[str, Path],
                     options: Optional[Dict] = None,
                     progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        增强单张图像

        Args:
            image_path: 输入图像路径
output_path: 输出图像路径
            options: 增强选项字典，包含：
                - denoise (bool): 是否启用降噪，默认True
                - sharpen (bool): 是否启用锐化，默认True
                - denoise_level (int): 降噪级别，覆盖默认配置
                - sharpen_strength (float): 锐化强度，覆盖默认配置
                - detail_enhance (bool): 是否启用细节增强
                - edge_preserve (bool): 是否启用边缘保留
            progress_callback: 进度回调函数，签名为 (progress: float, status: str) -> None

        Returns:
            bool: 处理成功返回True

        Raises:
            FileNotFoundError: 输入文件不存在
            DenoiseError: 降噪处理失败
            ValueError: 参数无效

        Example:
            >>> def callback(progress, status):
            ...     print(f"{progress:.1%} - {status}")
            >>> backend.enhance_image("input.jpg", "output.jpg",
            ...     {"denoise": True, "sharpen": True}, callback)
        """
        if progress_callback:
            progress_callback(0.0, "Loading image...")

        # 验证输入文件
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        # 合并配置
        opts = {**self.config, **(options or {})}
        denoise = opts.get("denoise", True)
        sharpen = opts.get("sharpen", True)
        denoise_level = opts.get("denoise_level", self.denoise_level)
        sharpen_strength = opts.get("sharpen_strength", self.sharpen_strength)
        detail_enhance = opts.get("detail_enhance", self.detail_enhance)
        edge_preserve = opts.get("edge_preserve", self.edge_preserve)

        try:
            # 加载图像
            if progress_callback:
                progress_callback(0.1, "Loading image...")
            image = Image.open(image_path)

            # 转换为RGB模式（处理PNG等可能有Alpha通道的格式）
            if image.mode != "RGB":
                image = image.convert("RGB")

            total_steps = sum([denoise, sharpen, detail_enhance, edge_preserve])
            current_step = 0

            # 降噪处理
            if denoise:
                if progress_callback:
                    progress_callback(0.2 + 0.5 * current_step / total_steps, "Applying denoising...")
                try:
                    if edge_preserve:
                        image = self._edge_preserving_smooth(image, strength=denoise_level)
                    else:
                        filter_obj = self._get_denoise_filter(denoise_level)
                        image = image.filter(filter_obj)
                    current_step += 1
                except Exception as e:
                    raise DenoiseError(f"Denoising failed: {str(e)}")

            # 锐化处理
            if sharpen:
                if progress_callback:
                    progress_callback(0.2 + 0.5 * current_step / total_steps, "Applying sharpening...")
                try:
                    image = self._unsharp_mask(image, amount=sharpen_strength)
                    current_step += 1
                except Exception as e:
                    raise DenoiseError(f"Sharpening failed: {str(e)}")

            # 细节增强
            if detail_enhance:
                if progress_callback:
                    progress_callback(0.2 + 0.5 * current_step / total_steps, "Enhancing details...")
                try:
                    image = self._detail_enhance(image)
                    current_step += 1
                except Exception as e:
                    raise DenoiseError(f"Detail enhancement failed: {str(e)}")

            # 确保输出目录存在
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存结果
            if progress_callback:
                progress_callback(0.9, "Saving result...")
            image.save(output_path, quality=95)

            if progress_callback:
                progress_callback(1.0, "Completed!")

            logger.info(f"Image enhanced successfully: {image_path} -> {output_path}")
            return True

        except (FileNotFoundError, DenoiseError, ValueError):
            raise
        except Exception as e:
            raise DenoiseError(f"Enhancement failed: {str(e)}")

    def batch_enhance(self, input_dir: Union[str, Path],
                      output_dir: Union[str, Path],
                      pattern: str = "*.png",
                      **options) -> Dict[str, bool]:
        """
        批量增强图像

        Args:
            input_dir: 输入目录路径
            output_dir: 输出目录路径
            pattern: 文件匹配模式，默认 "*.png"
            **options: 传递给enhance_image的选项

        Returns:
            dict: 处理结果字典，键为文件名，值为是否成功

        Raises:
            FileNotFoundError: 输入目录不存在

        Example:
            >>> results = backend.batch_enhance("input/", "output/", "*.jpg",
            ...     denoise=True, sharpen=True)
            >>> print(f"Processed {sum(results.values())}/{len(results)} images")
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)

        # 查找匹配的文件
        image_files = list(input_dir.glob(pattern))
        # 也搜索jpg格式
        if pattern == "*.png":
            image_files.extend(input_dir.glob("*.jpg"))
            image_files.extend(input_dir.glob("*.jpeg"))

        logger.info(f"Found {len(image_files)} images to process in {input_dir}")

        results = {}
        for i, image_path in enumerate(image_files):
            output_path = output_dir / image_path.name
            try:
                self.enhance_image(image_path, output_path, options)
                results[image_path.name] = True
            except Exception as e:
                logger.error(f"Failed to process {image_path.name}: {str(e)}")
                results[image_path.name] = False

        success_count = sum(results.values())
        logger.info(f"Batch enhancement completed: {success_count}/{len(results)} successful")

        return results

    def get_supported_formats(self) -> List[str]:
        """
        获取支持的图像格式列表

        Returns:
            list: 支持的文件扩展名列表
        """
        return [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]

    def validate_image(self, image_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
        """
        验证图像文件是否有效

        Args:
            image_path: 图像文件路径

        Returns:
            tuple: (是否有效, 错误信息或None)
        """
        try:
            path = Path(image_path)
            if not path.exists():
                return False, "File does not exist"
            if path.suffix.lower() not in self.get_supported_formats():
                return False, f"Unsupported format: {path.suffix}"
            with Image.open(path) as img:
                img.verify()
            return True, None
        except Exception as e:
            return False, str(e)


class ImageColorEditor:
    """
    图像色彩编辑器

    提供全面的色彩调整功能，包括HSL调整、饱和度、对比度、亮度等。
    支持基于numpy的高效处理和批量处理。

    Attributes:
        config (dict): 配置参数字典

    Example:
        >>> editor = ImageColorEditor()
        >>> # 调整亮度和饱和度
        >>> editor.adjust_color(image, brightness=1.2, saturation=1.3)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化色彩编辑器

        Args:
            config: 配置字典，包含以下可选键：
                - default_saturation (float): 默认饱和度调整，默认1.0
                - default_contrast (float): 默认对比度调整，默认1.0
                - default_brightness (float): 默认亮度调整，默认1.0
                - preserve_hue (bool): 是否保留色相，默认True
        """
        if not NUMPY_AVAILABLE:
            raise ImportError(f"Required dependency not available: {PIL_ERROR}")

        self.config = config or {}
        self.default_saturation = self.config.get("default_saturation", 1.0)
        self.default_contrast = self.config.get("default_contrast", 1.0)
        self.default_brightness = self.config.get("default_brightness", 1.0)
        self.preserve_hue = self.config.get("preserve_hue", True)

        logger.info(f"ImageColorEditor initialized with config: {self.config}")

    def _rgb_to_hsl(self, r: np.ndarray, g: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        RGB转HSL颜色空间

        Args:
            r, g, b: RGB通道值 (0-255)

        Returns:
            tuple: (h, s, l) 色调、饱和度、亮度 (0-1)
        """
        r = r / 255.0
        g = g / 255.0
        b = b / 255.0

        max_val = np.maximum(np.maximum(r, g), b)
        min_val = np.minimum(np.minimum(r, g), b)
        l = (max_val + min_val) / 2.0

        # 计算饱和度
        diff = max_val - min_val
        s = np.where(diff == 0, 0, diff / (1 - np.abs(2 * l - 1)))

        # 计算色调
        h = np.zeros_like(l)
        mask_r = (max_val == r) & (diff > 0)
        mask_g = (max_val == g) & (diff > 0)
        mask_b = (max_val == b) & (diff > 0)

        h[mask_r] = ((g[mask_r] - b[mask_r]) / diff[mask_r]) % 6
        h[mask_g] = (b[mask_g] - r[mask_g]) / diff[mask_g] + 2
        h[mask_b] = (r[mask_b] - g[mask_b]) / diff[mask_b] + 4

        h = h / 6.0
        h = np.clip(h, 0, 1)

        return h, s, l

    def _hsl_to_rgb(self, h: np.ndarray, s: np.ndarray, l: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        HSL转RGB颜色空间

        Args:
            h, s, l: 色调、饱和度、亮度 (0-1)

        Returns:
            tuple: (r, g, b) RGB通道值 (0-255)
        """
        def hue_to_rgb(p, q, t):
            t = np.mod(t, 1)
            t = np.where(t < 1/6, p + (q - p) * 6 * t,
                        np.where(t < 1/2, q,
                                np.where(t < 2/3, p + (q - p) * (2/3 - t) * 6, p)))
            return np.clip(t, 0, 1)

        q = np.where(l < 0.5, l * (1 + s), l + s - l * s)
        p = 2 * l - q

        r = hue_to_rgb(p, q, h + 1/3) * 255
        g = hue_to_rgb(p, q, h) * 255
        b = hue_to_rgb(p, q, h - 1/3) * 255

        return r, g, b

    def adjust_hsl(self, image: Image.Image,
                   hue: float = 0.0,
                   saturation: float = 1.0,
                   lightness: float = 1.0) -> Image.Image:
        """
        调整图像的HSL值

        Args:
            image: 输入图像
            hue: 色相调整值 (-1.0 to 1.0, 0表示不变)
            saturation: 饱和度调整值 (0.0 to 2.0, 1表示不变)
            lightness: 亮度调整值 (0.0 to 2.0, 1表示不变)

        Returns:
            Image: 调整后的图像
        """
        img_array = np.array(image)

        if len(img_array.shape) == 2:
            # 灰度图，转为RGB处理
            img_array = np.stack([img_array, img_array, img_array], axis=-1)

        r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]

        h, s, l = self._rgb_to_hsl(r, g, b)

        # 应用调整
        if hue != 0.0:
            if self.preserve_hue:
                h = np.mod(h + hue, 1.0)
            else:
                h = np.mod(h + (hue + 1) / 2, 1.0)

        s = np.clip(s * saturation, 0, 1)
        l = np.clip(l * lightness, 0, 1)

        # 转回RGB
        new_r, new_g, new_b = self._hsl_to_rgb(h, s, l)

        result = np.stack([new_r, new_g, new_b], axis=-1).astype(np.uint8)
        return Image.fromarray(result)

    def adjust_saturation(self, image: Image.Image, factor: float = 1.0) -> Image.Image:
        """
        调整图像饱和度

        Args:
            image: 输入图像
            factor: 饱和度因子 (0.0 = 灰度, 1.0 = 原始, 2.0 = 双倍饱和)

        Returns:
            Image: 调整后的图像
        """
        enhancer = ImageEnhance.Color(image)
        return enhancer.enhance(factor)

    def adjust_contrast(self, image: Image.Image, factor: float = 1.0) -> Image.Image:
        """
        调整图像对比度

        Args:
            image: 输入图像
            factor: 对比度因子 (0.0 = 全灰, 1.0 = 原始, 2.0 = 高对比)

        Returns:
            Image: 调整后的图像
        """
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)

    def adjust_brightness(self, image: Image.Image, factor: float = 1.0) -> Image.Image:
        """
        调整图像亮度

        Args:
            image: 输入图像
            factor: 亮度因子 (0.0 = 全黑, 1.0 = 原始, 2.0 = 双倍亮度)

        Returns:
            Image: 调整后的图像
        """
        enhancer = ImageEnhance.Brightness(image)
        return enhancer.enhance(factor)

    def adjust_sharpness(self, image: Image.Image, factor: float = 1.0) -> Image.Image:
        """
        调整图像锐度

        Args:
            image: 输入图像
            factor: 锐度因子 (0.0 = 模糊, 1.0 = 原始, 2.0 = 更锐利)

        Returns:
            Image: 调整后的图像
        """
        enhancer = ImageEnhance.Sharpness(image)
        return enhancer.enhance(factor)

    def adjust_color(self,
                    image: Union[Image.Image, str, Path],
                    hsl: Optional[Dict[str, float]] = None,
                    saturation: float = 1.0,
                    contrast: float = 1.0,
                    brightness: float = 1.0) -> Image.Image:
        """
        综合色彩调整

        可以同时调整HSL、饱和度、对比度和亮度

        Args:
            image: 输入图像（PIL Image对象或图像路径）
            hsl: HSL调整字典，包含：
                - hue (float): 色相调整 (-1.0 to 1.0)
                - saturation (float): 饱和度调整 (0.0 to 2.0)
                - lightness (float): 亮度调整 (0.0 to 2.0)
            saturation: 额外的饱和度调整因子
            contrast: 对比度调整因子
            brightness: 亮度调整因子

        Returns:
            Image: 调整后的图像

        Raises:
            ColorAdjustError: 色彩调整失败
            FileNotFoundError: 输入文件不存在

        Example:
            >>> editor = ImageColorEditor()
            >>> result = editor.adjust_color("photo.jpg",
            ...     hsl={"hue": 0.1, "saturation": 1.2},
            ...     brightness=1.1)
        """
        try:
            # 如果是路径，加载图像
            if isinstance(image, (str, Path)):
                image = Image.open(image)

            # 转换RGB模式
            if image.mode != "RGB":
                image = image.convert("RGB")

            result = image

            # 应用HSL调整
            if hsl:
                h = hsl.get("hue", 0.0)
                s = hsl.get("saturation", 1.0)
                l = hsl.get("lightness", 1.0)
                result = self.adjust_hsl(result, h, s, l)

            # 应用饱和度调整
            if saturation != 1.0:
                result = self.adjust_saturation(result, saturation)

            # 应用对比度调整
            if contrast != 1.0:
                result = self.adjust_contrast(result, contrast)

            # 应用亮度调整
            if brightness != 1.0:
                result = self.adjust_brightness(result, brightness)

            return result

        except FileNotFoundError:
            raise
        except Exception as e:
            raise ColorAdjustError(f"Color adjustment failed: {str(e)}")

    def batch_adjust(self,
                    input_dir: Union[str, Path],
                    output_dir: Union[str, Path],
                    pattern: str = "*.png",
                    **color_params) -> Dict[str, bool]:
        """
        批量调整图像色彩

        Args:
            input_dir: 输入目录路径
            output_dir: 输出目录路径
            pattern: 文件匹配模式
            **color_params: 传递给adjust_color的参数：
                - hsl (dict): HSL调整参数
                - saturation (float): 饱和度
                - contrast (float): 对比度
                - brightness (float): 亮度

        Returns:
            dict: 处理结果字典

        Example:
            >>> results = editor.batch_adjust("input/", "output/",
            ...     saturation=1.3, brightness=1.1)
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        output_dir.mkdir(parents=True, exist_ok=True)

        # 查找匹配的文件
        image_files = list(input_dir.glob(pattern))
        if pattern == "*.png":
            image_files.extend(input_dir.glob("*.jpg"))
            image_files.extend(input_dir.glob("*.jpeg"))

        logger.info(f"Found {len(image_files)} images to adjust in {input_dir}")

        results = {}
        for image_path in image_files:
            output_path = output_dir / image_path.name
            try:
                adjusted = self.adjust_color(image_path, **color_params)
                adjusted.save(output_path, quality=95)
                results[image_path.name] = True
            except Exception as e:
                logger.error(f"Failed to adjust {image_path.name}: {str(e)}")
                results[image_path.name] = False

        return results

    def auto_color_balance(self, image: Image.Image) -> Image.Image:
        """
        自动色彩平衡

        基于灰色世界假设进行自动白平衡

        Args:
            image: 输入图像

        Returns:
            Image: 自动白平衡后的图像
        """
        img_array = np.array(image).astype(np.float32)

        if len(img_array.shape) == 2:
            img_array = np.stack([img_array, img_array, img_array], axis=-1)

        # 计算每个通道的平均值
        r_mean = np.mean(img_array[:, :, 0])
        g_mean = np.mean(img_array[:, :, 1])
        b_mean = np.mean(img_array[:, :, 2])

        # 计算缩放因子使所有通道均值相等
        gray_mean = (r_mean + g_mean + b_mean) / 3

        img_array[:, :, 0] = np.clip(img_array[:, :, 0] * gray_mean / r_mean, 0, 255)
        img_array[:, :, 1] = np.clip(img_array[:, :, 1] * gray_mean / g_mean, 0, 255)
        img_array[:, :, 2] = np.clip(img_array[:, :, 2] * gray_mean / b_mean, 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    def temperature_adjust(self, image: Image.Image, temperature: float = 0.0) -> Image.Image:
        """
        调整色温

        Args:
            image: 输入图像
            temperature: 温度值 (-1.0冷色调, 0.0中性, 1.0暖色调)

        Returns:
            Image: 调整后的图像
        """
        img_array = np.array(image).astype(np.float32)

        if temperature > 0:
            # 暖色调：增加红色，减少蓝色
            img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 + temperature * 0.3), 0, 255)
            img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - temperature * 0.3), 0, 255)
        else:
            # 冷色调：增加蓝色，减少红色
            img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 + temperature * 0.3), 0, 255)
            img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - temperature * 0.3), 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))


class ImageUpscaleEngine:
    """
    图像放大引擎

    支持多种超分辨率算法进行图像放大：
    - Real-ESRGAN: 高质量深度学习超分
    - SwinIR: 基于Transformer的深度学习超分
    - Lanczos: 传统高质量插值

    Attributes:
        config (dict): 配置参数字典
        model_cache (dict): 模型缓存

    Example:
        >>> engine = ImageUpscaleEngine()
        >>> engine.upscale_image("input.png", "output_2x.png", scale=2, model="lanczos")
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化图像放大引擎

        Args:
            config: 配置字典，包含以下可选键：
                - tile_size (int): 分块处理大小，默认512
                - tile_pad (int): 分块重叠区域，默认16
                - pre_pad (int): 预处理填充，默认0
                - gpu_id (int): GPU设备ID，默认0
                - cpu_mode (bool): 是否使用CPU模式，默认False
        """
        if not NUMPY_AVAILABLE:
            raise ImportError(f"Required dependency not available: {PIL_ERROR}")

        self.config = config or {}
        self.tile_size = self.config.get("tile_size", 512)
        self.tile_pad = self.config.get("tile_pad", 16)
        self.pre_pad = self.config.get("pre_pad", 0)
        self.gpu_id = self.config.get("gpu_id", 0)
        self.cpu_mode = self.config.get("cpu_mode", False)
        self.model_cache = {}

        logger.info(f"ImageUpscaleEngine initialized with config: {self.config}")

    def _lanczos_resample(self, image: Image.Image, scale: int) -> Image.Image:
        """
        Lanczos插值放大

        Args:
            image: 输入图像
            scale: 放大倍数

        Returns:
            Image: 放大后的图像
        """
        new_size = (image.width * scale, image.height * scale)
        return image.resize(new_size, Image.Resampling.LANCZOS)

    def _bicubic_resample(self, image: Image.Image, scale: int) -> Image.Image:
        """
        双立方插值放大

        Args:
            image: 输入图像
            scale: 放大倍数

        Returns:
            Image: 放大后的图像
        """
        new_size = (image.width * scale, image.height * scale)
        return image.resize(new_size, Image.Resampling.BICUBIC)

    def _nearest_neighbor(self, image: Image.Image, scale: int) -> Image.Image:
        """
        最近邻插值放大

        Args:
            image: 输入图像
            scale: 放大倍数

        Returns:
            Image: 放大后的图像
        """
        new_size = (image.width * scale, image.height * scale)
        return image.resize(new_size, Image.Resampling.NEAREST)

    def _box_resample(self, image: Image.Image, scale: int) -> Image.Image:
        """
        Box平均插值放大

        Args:
            image: 输入图像
            scale: 放大倍数

        Returns:
            Image: 放大后的图像
        """
        new_size = (image.width * scale, image.height * scale)
        return image.resize(new_size, Image.Resampling.BOX)

    def _tile_based_processing(self, image: Image.Image,
                               process_func: Callable[[np.ndarray], np.ndarray],
                               scale: int) -> Image.Image:
        """
        基于分块的处理流程，用于处理超大图像

        Args:
            image: 输入图像
            process_func: 处理函数，接收numpy数组返回numpy数组
            scale: 放大倍数

        Returns:
            Image: 处理后的图像
        """
        img_array = np.array(image)
        h, w = img_array.shape[:2]
        out_h, out_w = h * scale, w * scale

        # 计算分块数量
        tile_size = self.tile_size
        pad = self.tile_pad

        # 输出数组
        output = np.zeros((out_h, out_w, img_array.shape[2] if len(img_array.shape) == 3 else 1),
                         dtype=img_array.dtype)

        for i in range(0, h, tile_size - pad):
            for j in range(0, w, tile_size - pad):
                # 确定边界
                i_end = min(i + tile_size, h)
                j_end = min(j + tile_size, w)

                # 提取块（带重叠）
                i_start = max(0, i_end - tile_size)
                j_start = max(0, j_end - tile_size)

                tile = img_array[i_start:i_end, j_start:j_end]

                # 处理块
                processed = process_func(tile)

                # 计算输出位置
                out_i_start = i_start * scale
                out_j_start = j_start * scale
                out_i_end = i_end * scale
                out_j_end = j_end * scale

                # 去除重叠区域（简单平均融合）
                if pad > 0:
                    overlap = pad * scale
                    # 简单策略：直接赋值（后续可优化为加权融合）
                    output[out_i_start:out_i_end, out_j_start:out_j_end] = processed
                else:
                    output[out_i_start:out_i_end, out_j_start:out_j_end] = processed

        if len(img_array.shape) == 2:
            return Image.fromarray(output[:, :, 0])
        return Image.fromarray(output)

    def _simulate_real_esrgan(self, image: Image.Image) -> Image.Image:
        """
        模拟Real-ESRGAN效果

        由于实际Real-ESRGAN需要额外依赖，这里提供一个基于深度学习的模拟实现
        实际使用时建议集成真实的Real-ESRGAN模型

        Args:
            image: 输入图像

        Returns:
            Image: 超分后的图像
        """
        # 转换为numpy数组
        img_array = np.array(image).astype(np.float32) / 255.0

        # 应用增强滤波器模拟深度学习超分效果
        # 1. 首先进行边缘增强
        kernel_sharpen = np.array([
            [-1, -1, -1],
            [-1,  9, -1],
            [-1, -1, -1]
        ], dtype=np.float32) * 0.7

        kernel_enhance = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ], dtype=np.float32) * 0.3

        kernel = kernel_sharpen + kernel_enhance

        # 对每个通道应用卷积
        result = np.zeros_like(img_array)
        for c in range(img_array.shape[2]):
            channel = img_array[:, :, c]
            # 简单的2D卷积实现
            from scipy.ndimage import convolve
            result[:, :, c] = convolve(channel, kernel, mode='reflect')

        result = np.clip(result * 255, 0, 255).astype(np.uint8)
        return Image.fromarray(result)

    def _simulate_swinir(self, image: Image.Image) -> Image.Image:
        """
        模拟SwinIR效果

        由于实际SwinIR需要额外依赖，这里提供一个基于Transformer风格滤波的模拟实现
        实际使用时建议集成真实的SwinIR模型

        Args:
            image: 输入图像

        Returns:
            Image: 超分后的图像
        """
        # 使用多尺度锐化来模拟Transformer的超分效果
        img_array = np.array(image)

        # 应用细节增强
        from scipy.ndimage import gaussian_filter

        # 提取高频细节
        blurred = gaussian_filter(img_array.astype(float), sigma=1)
        detail = img_array.astype(float) - blurred

        # 增强细节并叠加
        enhanced = img_array.astype(float) + detail * 0.5

        # 应用轻微的全局锐化
        enhanced = Image.fromarray(np.clip(enhanced, 0, 255).astype(np.uint8))
        enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=150))

        return enhanced

    def upscale_image(self,
                     image_path: Union[str, Path],
                     output_path: Union[str, Path],
                     scale: int = 2,
                     model: str = "lanczos") -> bool:
        """
        放大单张图像

        Args:
            image_path: 输入图像路径
            output_path: 输出图像路径
            scale: 放大倍数 (2, 3, 4)
            model: 超分模型，可选：
                - "real_esrgan": 高质量深度学习超分（模拟）
                - "swinir": Transformer深度学习超分（模拟）
                - "lanczos": Lanczos插值（高质量传统方法）
                - "bicubic": 双立方插值
                - "nearest": 最近邻插值（快速但质量较低）

        Returns:
            bool: 处理成功返回True

        Raises:
            FileNotFoundError: 输入文件不存在
            UpscaleError: 放大处理失败
            ValueError: 无效的scale或model参数

        Example:
            >>> engine = ImageUpscaleEngine()
            >>> engine.upscale_image("input.jpg", "output_4x.jpg", scale=4, model="lanczos")
        """
        # 验证输入
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        if scale not in [2, 3, 4]:
            raise ValueError(f"scale must be 2, 3, or 4, got {scale}")

        model = model.lower()
        valid_models = ["real_esrgan", "swinir", "lanczos", "bicubic", "nearest"]
        if model not in valid_models:
            raise ValueError(f"model must be one of {valid_models}, got {model}")

        try:
            # 加载图像
            image = Image.open(image_path)

            # 转换为RGB
            if image.mode != "RGB":
                image = image.convert("RGB")

            # 根据模型选择放大方法
            if model == "lanczos":
                result = self._lanczos_resample(image, scale)
            elif model == "bicubic":
                result = self._bicubic_resample(image, scale)
            elif model == "nearest":
                result = self._nearest_neighbor(image, scale)
            elif model == "real_esrgan":
                # 使用模拟的Real-ESRGAN
                result = self._simulate_real_esrgan(image)
                # 放大到目标尺寸
                result = self._lanczos_resample(result, scale)
            elif model == "swinir":
                # 使用模拟的SwinIR
                result = self._simulate_swinir(image)
                # 放大到目标尺寸
                result = self._lanczos_resample(result, scale)

            # 确保输出目录存在
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存结果
            result.save(output_path, quality=95)

            logger.info(f"Image upscaled: {image_path} -> {output_path} (scale={scale}, model={model})")
            return True

        except FileNotFoundError:
            raise
        except Exception as e:
            raise UpscaleError(f"Upscaling failed: {str(e)}")

    def batch_upscale(self,
                     input_dir: Union[str, Path],
                     output_dir: Union[str, Path],
                     scale: int = 2,
                     model: str = "lanczos",
                     progress_callback: Optional[Callable[[float, str], None]] = None) -> Dict[str, bool]:
        """
        批量放大图像

        Args:
            input_dir: 输入目录路径
            output_dir: 输出目录路径
            scale: 放大倍数 (2, 3, 4)
            model: 超分模型名称
            progress_callback: 进度回调函数

        Returns:
            dict: 处理结果字典

        Example:
            >>> def callback(progress, status):
            ...     print(f"{progress:.1%} - {status}")
            >>> engine.batch_upscale("input/", "output/", scale=2, model="lanczos",
            ...     progress_callback=callback)
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        output_dir.mkdir(parents=True, exist_ok=True)

        # 查找图像文件
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff"]
        image_files = []
        for p in patterns:
            image_files.extend(input_dir.glob(p))

        logger.info(f"Found {len(image_files)} images to upscale")

        results = {}
        for i, image_path in enumerate(image_files):
            if progress_callback:
                progress_callback(i / len(image_files), f"Processing {image_path.name}...")

            output_path = output_dir / image_path.name
            try:
                self.upscale_image(image_path, output_path, scale, model)
                results[image_path.name] = True
            except Exception as e:
                logger.error(f"Failed to upscale {image_path.name}: {str(e)}")
                results[image_path.name] = False

        if progress_callback:
            progress_callback(1.0, "Completed!")

        return results

    def get_estimated_output_size(self, image_path: Union[str, Path], scale: int) -> Tuple[int, int]:
        """
        获取估计的输出图像尺寸

        Args:
            image_path: 输入图像路径
            scale: 放大倍数

        Returns:
            tuple: (宽度, 高度)
        """
        with Image.open(image_path) as img:
            return (img.width * scale, img.height * scale)


class ImageProcessingPipeline:
    """
    图像处理流水线

    整合多个图像处理模块，实现一站式的图像增强流程

    Example:
        >>> pipeline = ImageProcessingPipeline()
        >>> pipeline.add_step("enhance", {"denoise": True, "sharpen": True})
        >>> pipeline.add_step("color", {"saturation": 1.2})
        >>> pipeline.add_step("upscale", {"scale": 2, "model": "lanczos"})
        >>> pipeline.process("input.jpg", "output.jpg")
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化处理流水线

        Args:
            config: 全局配置字典
        """
        self.config = config or {}
        self.steps = []
        self.enhance_backend = ImageEnhanceBackend(self.config.get("enhance"))
        self.color_editor = ImageColorEditor(self.config.get("color"))
        self.upscale_engine = ImageUpscaleEngine(self.config.get("upscale"))

        logger.info("ImageProcessingPipeline initialized")

    def add_step(self, step_type: str, options: Dict):
        """
        添加处理步骤

        Args:
            step_type: 步骤类型，可选：
                - "enhance": 图像增强
                - "color": 色彩调整
                - "upscale": 图像放大
            options: 步骤配置
        """
        self.steps.append({"type": step_type, "options": options})
        logger.info(f"Added pipeline step: {step_type}")

    def clear_steps(self):
        """清除所有处理步骤"""
        self.steps = []
        logger.info("Pipeline steps cleared")

    def process(self,
               input_path: Union[str, Path],
               output_path: Union[str, Path],
               progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        执行处理流水线

        Args:
            input_path: 输入图像路径
            output_path: 输出图像路径
            progress_callback: 进度回调

        Returns:
            bool: 处理成功返回True
        """
        if not self.steps:
            logger.warning("No steps in pipeline, copying file directly")
            import shutil
            shutil.copy(input_path, output_path)
            return True

        current_path = input_path
        temp_paths = []

        try:
            for i, step in enumerate(self.steps):
                if progress_callback:
                    progress_callback(i / len(self.steps), f"Step {i+1}: {step['type']}")

                step_type = step["type"]
                options = step["options"]

                if step_type == "enhance":
                    temp_output = Path(f"__temp_{i}_{hashlib.md5(str(time.time()).encode()).hexdigest()}.png")
                    temp_paths.append(temp_output)
                    self.enhance_backend.enhance_image(current_path, temp_output, options)

                elif step_type == "color":
                    temp_output = Path(f"__temp_{i}_{hashlib.md5(str(time.time()).encode()).hexdigest()}.png")
                    temp_paths.append(temp_output)
                    image = self.color_editor.adjust_color(current_path, **options)
                    image.save(temp_output)

                elif step_type == "upscale":
                    temp_output = Path(f"__temp_{i}_{hashlib.md5(str(time.time()).encode()).hexdigest()}.png")
                    temp_paths.append(temp_output)
                    self.upscale_engine.upscale_image(
                        current_path, temp_output,
                        options.get("scale", 2),
                        options.get("model", "lanczos")
                    )

                current_path = temp_output

            # 复制最终结果到输出路径
            import shutil
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(current_path, output_path)

            if progress_callback:
                progress_callback(1.0, "Completed!")

            return True

        finally:
            # 清理临时文件
            for temp_path in temp_paths:
                if temp_path.exists():
                    temp_path.unlink()


# 便捷函数
def enhance_image(image_path: Union[str, Path],
                 output_path: Union[str, Path],
                 **options) -> bool:
    """
    便捷函数：增强单张图像

    Args:
        image_path: 输入路径
        output_path: 输出路径
        **options: 增强选项

    Returns:
        bool: 是否成功
    """
    backend = ImageEnhanceBackend()
    return backend.enhance_image(image_path, output_path, options)


def adjust_image_color(image_path: Union[str, Path],
                       output_path: Union[str, Path],
                       **color_params) -> bool:
    """
    便捷函数：调整图像色彩

    Args:
        image_path: 输入路径
        output_path: 输出路径
        **color_params: 色彩参数

    Returns:
        bool: 是否成功
    """
    editor = ImageColorEditor()
    result = editor.adjust_color(image_path, **color_params)
    result.save(output_path)
    return True


def upscale_image(image_path: Union[str, Path],
                 output_path: Union[str, Path],
                 scale: int = 2,
                 model: str = "lanczos") -> bool:
    """
    便捷函数：放大图像

    Args:
        image_path: 输入路径
        output_path: 输出路径
        scale: 放大倍数
        model: 超分模型

    Returns:
        bool: 是否成功
    """
    engine = ImageUpscaleEngine()
    return engine.upscale_image(image_path, output_path, scale, model)


if __name__ == "__main__":
    # 简单测试
    print("Image Enhancement Backend Module")
    print("Available classes:")
    print("  - ImageEnhanceBackend: Image enhancement (denoise, sharpen)")
    print("  - ImageColorEditor: Color adjustment (HSL, saturation, contrast, brightness)")
    print("  - ImageUpscaleEngine: Image upscaling (Real-ESRGAN, SwinIR, Lanczos)")
    print("  - ImageProcessingPipeline: Combined processing pipeline")
    print("\nUsage example:")
    print("  backend = ImageEnhanceBackend()")
    print("  backend.enhance_image('input.jpg', 'output.jpg', {'denoise': True})")
