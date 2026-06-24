#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Style Filters Module - High-Quality Style Filter Processing
风格滤镜模块 - 高质量风格滤镜处理
"""

import logging
import math
from typing import List, Optional, Tuple, Union
from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageChops
import cv2

logger = logging.getLogger(__name__)


class ColorAdjustment:
    """Color Adjustment Class - 色彩调整类"""

    def __init__(self):
        """Initialize ColorAdjustment"""
        logger.debug("ColorAdjustment initialized")

    def adjust_hsl(
        self, image: Image.Image, hue: float = 0, saturation: float = 0, lightness: float = 0
    ) -> Image.Image:
        """
        Adjust HSL (Hue, Saturation, Lightness) of an image.
        调整图像的HSL(色相、饱和度、亮度)

        Args:
            image: Input PIL Image
            hue: Hue adjustment (-180 to 180, default 0)
            saturation: Saturation adjustment (-100 to 100, default 0)
            lightness: Lightness adjustment (-100 to 100, default 0)

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting HSL: hue={hue}, saturation={saturation}, lightness={lightness}")

        # Convert to HSV color space for efficient HSL adjustment
        img_array = np.array(image)
        img_hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV).astype(np.float32)

        # Adjust Lightness/Value
        if lightness != 0:
            lightness_scale = lightness / 100.0
            img_hsv[:, :, 2] = np.clip(img_hsv[:, :, 2] * (1 + lightness_scale), 0, 255)

        # Adjust Saturation
        if saturation != 0:
            saturation_scale = 1 + (saturation / 100.0)
            img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * saturation_scale, 0, 255)

        # Adjust Hue
        if hue != 0:
            hue_scale = hue / 180.0 * 255
            img_hsv[:, :, 0] = (img_hsv[:, :, 0] + hue_scale) % 255

        img_hsv = img_hsv.astype(np.uint8)
        img_rgb = cv2.cvtColor(img_hsv, cv2.COLOR_HSV2RGB)

        logger.debug("HSL adjustment completed")
        return Image.fromarray(img_rgb)

    def adjust_brightness(self, image: Image.Image, value: float) -> Image.Image:
        """
        Adjust brightness of an image.
        调整图像亮度

        Args:
            image: Input PIL Image
            value: Brightness adjustment factor (-100 to 100)
                   Negative values darken, positive values brighten

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting brightness: value={value}")

        # Convert value from -100..100 to a scale factor
        if value == 0:
            return image

        scale = 1.0 + (value / 100.0)
        enhancer = ImageEnhance.Brightness(image)
        result = enhancer.enhance(scale)

        logger.debug(f"Brightness adjustment completed: scale={scale:.2f}")
        return result

    def adjust_contrast(self, image: Image.Image, value: float) -> Image.Image:
        """
        Adjust contrast of an image.
        调整图像对比度

        Args:
            image: Input PIL Image
            value: Contrast adjustment factor (-100 to 100)

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting contrast: value={value}")

        if value == 0:
            return image

        scale = 1.0 + (value / 100.0)
        enhancer = ImageEnhance.Contrast(image)
        result = enhancer.enhance(scale)

        logger.debug(f"Contrast adjustment completed: scale={scale:.2f}")
        return result

    def adjust_exposure(self, image: Image.Image, value: float) -> Image.Image:
        """
        Adjust exposure of an image using gamma correction.
        调整图像曝光度

        Args:
            image: Input PIL Image
            value: Exposure adjustment factor (-100 to 100)

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting exposure: value={value}")

        if value == 0:
            return image

        # Convert to numpy array for gamma correction
        img_array = np.array(image).astype(np.float32) / 255.0

        # Calculate gamma from exposure value
        # Positive value = more exposure, negative = less exposure
        gamma = 1.0 - (value / 100.0) * 0.5
        gamma = max(0.2, min(5.0, gamma))

        # Apply gamma correction
        img_exposed = np.power(img_array, gamma)

        # Scale back to 0-255
        img_exposed = (img_exposed * 255).astype(np.uint8)

        logger.debug(f"Exposure adjustment completed: gamma={gamma:.2f}")
        return Image.fromarray(img_exposed)

    def adjust_saturation(self, image: Image.Image, value: float) -> Image.Image:
        """
        Adjust saturation of an image.
        调整图像饱和度

        Args:
            image: Input PIL Image
            value: Saturation adjustment factor (-100 to 100)

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting saturation: value={value}")

        if value == 0:
            return image

        scale = 1.0 + (value / 100.0)
        enhancer = ImageEnhance.Color(image)
        result = enhancer.enhance(scale)

        logger.debug(f"Saturation adjustment completed: scale={scale:.2f}")
        return result

    def adjust_temperature(self, image: Image.Image, value: float) -> Image.Image:
        """
        Adjust color temperature (warm/cool).
        调整色温(暖/冷色调)

        Args:
            image: Input PIL Image
            value: Temperature adjustment (-100 to 100)
                   Positive = warmer, Negative = cooler

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting temperature: value={value}")

        if value == 0:
            return image

        img_array = np.array(image).astype(np.float32)

        # For warmer: increase red, decrease blue
        # For cooler: decrease red, increase blue
        temp_scale = value / 100.0

        # Adjust red channel
        if temp_scale > 0:
            img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 + temp_scale * 0.3), 0, 255)
            img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - temp_scale * 0.3), 0, 255)
        else:
            img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 + temp_scale * 0.3), 0, 255)
            img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - temp_scale * 0.3), 0, 255)

        result = Image.fromarray(img_array.astype(np.uint8))

        logger.debug("Temperature adjustment completed")
        return result

    def adjust_tint(self, image: Image.Image, value: float) -> Image.Image:
        """
        Adjust tint (green/magenta shift).
        调整色调(绿/品红偏移)

        Args:
            image: Input PIL Image
            value: Tint adjustment (-100 to 100)
                   Positive = more magenta, Negative = more green

        Returns:
            Adjusted PIL Image
        """
        logger.debug(f"Adjusting tint: value={value}")

        if value == 0:
            return image

        img_array = np.array(image).astype(np.float32)

        # Adjust green and magenta channels
        tint_scale = value / 100.0 * 30

        # Green channel adjustment (index 1)
        if tint_scale > 0:
            img_array[:, :, 1] = np.clip(img_array[:, :, 1] * (1 - tint_scale / 255), 0, 255)
        else:
            img_array[:, :, 1] = np.clip(img_array[:, :, 1] * (1 - tint_scale / 255), 0, 255)

        result = Image.fromarray(img_array.astype(np.uint8))

        logger.debug("Tint adjustment completed")
        return result

    def sharpen(self, image: Image.Image, amount: float) -> Image.Image:
        """
        Sharpen an image.
        锐化图像

        Args:
            image: Input PIL Image
            amount: Sharpening amount (0.0 to 10.0)

        Returns:
            Sharpened PIL Image
        """
        logger.debug(f"Sharpening image: amount={amount}")

        if amount <= 0:
            return image

        # Use unsharp mask for high-quality sharpening
        img_array = np.array(image)

        # Create blurred version
        blurred = cv2.GaussianBlur(img_array, (0, 0), 3)
        blurred_float = blurred.astype(np.float32)

        # Calculate sharpening mask
        sharpened = img_array.astype(np.float32) + amount * (img_array.astype(np.float32) - blurred_float)

        # Clamp and convert
        sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

        logger.debug("Sharpening completed")
        return Image.fromarray(sharpened)

    def blur(self, image: Image.Image, radius: float) -> Image.Image:
        """
        Blur an image.
        模糊图像

        Args:
            image: Input PIL Image
            radius: Blur radius in pixels

        Returns:
            Blurred PIL Image
        """
        logger.debug(f"Blurring image: radius={radius}")

        if radius <= 0:
            return image

        # Use Gaussian blur for smooth results
        img_array = np.array(image)
        blurred = cv2.GaussianBlur(img_array, (0, 0), radius)

        logger.debug("Blur completed")
        return Image.fromarray(blurred)


class StyleFilterEngine:
    """Style Filter Engine - 风格滤镜引擎"""

    # Filter definitions with parameters
    FILTER_PRESETS = {
        "cinematic": {
            "description": "电影感滤镜 - Cinematic look with teal shadows and orange highlights",
            "contrast": 15,
            "saturation": -10,
            "temperature": 5,
            "tone_effect": "teal_shadows",
        },
        "vintage": {
            "description": "复古滤镜 - Warm nostalgic look with faded edges",
            "brightness": -5,
            "contrast": -10,
            "saturation": -20,
            "temperature": 15,
            "vignette": 0.3,
            "grain": 0.1,
        },
        "watercolor": {
            "description": "水彩滤镜 - Soft artistic watercolor effect",
            "blur": 2.0,
            "saturation": 10,
            "brightness": 5,
            "edge_enhance": 0.3,
        },
        "anime": {
            "description": "动漫滤镜 - Vibrant anime-style colors with edge enhancement",
            "saturation": 25,
            "contrast": 20,
            "sharpness": 1.5,
            "color_boost": (0.1, 0.2, 0.1),  # RGB boost
        },
        "realistic": {
            "description": "写实滤镜 - Natural realistic photography look",
            "contrast": 5,
            "saturation": 5,
            "sharpness": 0.3,
            "tone_mapping": True,
        },
        "noir": {
            "description": "黑白滤镜 - Classic black and white with high contrast",
            "grayscale": True,
            "contrast": 30,
            "brightness": -10,
        },
        "warm": {
            "description": "暖色调滤镜 - Warm golden tones",
            "temperature": 30,
            "saturation": 10,
            "brightness": 5,
        },
        "cool": {
            "description": "冷色调滤镜 - Cool blue tones",
            "temperature": -30,
            "saturation": 5,
            "brightness": -5,
        },
        "HDR": {
            "description": "HDR滤镜 - High dynamic range effect",
            "contrast": 25,
            "saturation": 15,
            "sharpness": 1.2,
            "local_contrast": 1.5,
        },
        "portrait": {
            "description": "人像滤镜 - Soft skin tones with subtle sharpening",
            "brightness": 5,
            "contrast": -5,
            "saturation": -10,
            "soft_skin": 0.5,
            "sharpness": 0.3,
        },
    }

    def __init__(self):
        """Initialize StyleFilterEngine"""
        self.color_adj = ColorAdjustment()
        self._filter_cache = {}
        logger.info("StyleFilterEngine initialized")

    def get_available_filters(self) -> List[str]:
        """
        Get list of available filter names.
        获取可用的滤镜名称列表

        Returns:
            List of filter names
        """
        filters = list(self.FILTER_PRESETS.keys())
        logger.debug(f"Available filters: {filters}")
        return filters

    def apply_filter(
        self, image: Image.Image, filter_name: str, intensity: float = 1.0
    ) -> Image.Image:
        """
        Apply a named filter to an image.
        应用滤镜到图像

        Args:
            image: Input PIL Image
            filter_name: Name of the filter to apply
            intensity: Filter intensity (0.0 to 2.0, default 1.0)

        Returns:
            Filtered PIL Image
        """
        logger.info(f"Applying filter '{filter_name}' with intensity={intensity}")

        if filter_name not in self.FILTER_PRESETS:
            logger.warning(f"Unknown filter '{filter_name}', returning original image")
            return image

        if intensity <= 0:
            logger.debug("Intensity <= 0, returning original image")
            return image

        # Apply the filter
        result = self._apply_filter_preset(image, filter_name)

        # Apply intensity blending with original if needed
        if intensity != 1.0 and intensity > 0:
            # Use blend for smooth intensity control
            result = Image.blend(image, result, intensity)

        logger.info(f"Filter '{filter_name}' applied successfully")
        return result

    def _apply_filter_preset(self, image: Image.Image, filter_name: str) -> Image.Image:
        """
        Internal method to apply a filter preset.
        内部方法:应用滤镜预设

        Args:
            image: Input PIL Image
            filter_name: Name of the filter preset

        Returns:
            Filtered PIL Image
        """
        preset = self.FILTER_PRESETS[filter_name]
        result = image.copy()

        # Apply brightness adjustment
        if "brightness" in preset:
            result = self.color_adj.adjust_brightness(result, preset["brightness"])

        # Apply contrast adjustment
        if "contrast" in preset:
            result = self.color_adj.adjust_contrast(result, preset["contrast"])

        # Apply saturation adjustment
        if "saturation" in preset:
            result = self.color_adj.adjust_saturation(result, preset["saturation"])

        # Apply temperature adjustment
        if "temperature" in preset:
            result = self.color_adj.adjust_temperature(result, preset["temperature"])

        # Apply tint adjustment
        if "tint" in preset:
            result = self.color_adj.adjust_tint(result, preset["tint"])

        # Apply sharpening
        if "sharpness" in preset:
            result = self.color_adj.sharpen(result, preset["sharpness"])

        # Apply blur
        if "blur" in preset:
            result = self.color_adj.blur(result, preset["blur"])

        # Apply grayscale (for noir)
        if preset.get("grayscale", False):
            result = ImageOps.grayscale(result)
            result = result.convert("RGB")

        # Apply vignette effect
        if "vignette" in preset:
            result = self._apply_vignette(result, preset["vignette"])

        # Apply grain effect
        if "grain" in preset:
            result = self._apply_grain(result, preset["grain"])

        # Apply teal shadows effect (for cinematic)
        if preset.get("tone_effect") == "teal_shadows":
            result = self._apply_teal_shadows(result)

        # Apply local contrast (for HDR)
        if "local_contrast" in preset:
            result = self._apply_local_contrast(result, preset["local_contrast"])

        # Apply color boost (for anime)
        if "color_boost" in preset:
            result = self._apply_color_boost(result, preset["color_boost"])

        # Apply soft skin effect (for portrait)
        if "soft_skin" in preset:
            result = self._apply_soft_skin(result, preset["soft_skin"])

        # Apply edge enhancement (for watercolor)
        if "edge_enhance" in preset:
            result = self._apply_edge_enhance(result, preset["edge_enhance"])

        # Apply tone mapping
        if preset.get("tone_mapping", False):
            result = self._apply_tone_mapping(result)

        return result

    def _apply_vignette(self, image: Image.Image, intensity: float) -> Image.Image:
        """
        Apply vignette effect (darkened edges).
        应用暗角效果

        Args:
            image: Input image
            intensity: Vignette intensity (0.0 to 1.0)

        Returns:
            Image with vignette
        """
        img_array = np.array(image).astype(np.float32)
        h, w = img_array.shape[:2]

        # Create vignette mask
        x = np.linspace(-1, 1, w)
        y = np.linspace(-1, 1, h)
        xx, yy = np.meshgrid(x, y)

        # Radial distance from center
        r = np.sqrt(xx**2 + yy**2)
        vignette = 1 - np.clip(r * intensity, 0, 1)

# Apply vignette
        if len(img_array.shape) == 3:
            vignette = vignette[:, :, np.newaxis]

        img_array = img_array * vignette
        return Image.fromarray(np.clip(img_array, 0, 255).astype(np.uint8))

    def _apply_grain(self, image: Image.Image, intensity: float) -> Image.Image:
        """
        Apply film grain effect.
        应用胶片颗粒效果

        Args:
            image: Input image
            intensity: Grain intensity (0.0 to 1.0)

        Returns:
            Image with grain
        """
        img_array = np.array(image).astype(np.float32)
        h, w = img_array.shape[:2]

        # Generate random grain noise
        grain = np.random.normal(0, intensity * 50, (h, w, 3))

        # Add grain to image
        img_array = img_array + grain
        return Image.fromarray(np.clip(img_array, 0, 255).astype(np.uint8))

    def _apply_teal_shadows(self, image: Image.Image) -> Image.Image:
        """
        Apply teal shadows effect (cinematic look).
        应用青色阴影效果

        Args:
            image: Input image

        Returns:
            Image with teal shadows
        """
        img_array = np.array(image).astype(np.float32)
        img_hsv = cv2.cvtColor(img_array.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)

        # Reduce saturation in shadows and add cyan tint
        shadow_mask = (img_hsv[:, :, 2] < 100).astype(float)
        shadow_mask = shadow_mask[:, :, np.newaxis]

        # Add cyan tint to shadows
        img_array[:, :, 0] = np.clip(img_array[:, :, 0] - 20 * shadow_mask[:, :, 0], 0, 255)
        img_array[:, :, 2] = np.clip(img_array[:, :, 2] + 15 * shadow_mask[:, :, 0], 0, 255)

        return Image.fromarray(np.clip(img_array, 0, 255).astype(np.uint8))

    def _apply_local_contrast(self, image: Image.Image, amount: float) -> Image.Image:
        """
        Apply local contrast enhancement (CLAHE-like).
        应用局部对比度增强

        Args:
            image: Input image
            amount: Contrast enhancement amount

        Returns:
            Image with enhanced local contrast
        """
        img_array = np.array(image)

        # Convert to LAB color space
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)

        # Blend original and enhanced
        l_blended = (l_channel * (1 - amount * 0.5) + l_enhanced * amount * 0.5).astype(np.uint8)

        # Merge channels and convert back
        lab_enhanced = cv2.merge([l_blended, a_channel, b_channel])
        result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)

        return Image.fromarray(result)

    def _apply_color_boost(
        self, image: Image.Image, boost: Tuple[float, float, float]
    ) -> Image.Image:
        """
        Apply selective color boost.
        应用选择性色彩增强

        Args:
            image: Input image
            boost: RGB boost values

        Returns:
            Image with boosted colors
        """
        img_array = np.array(image).astype(np.float32)

        # Apply per-channel boost
        for i, b in enumerate(boost):
            if b != 0:
                img_array[:, :, i] = np.clip(img_array[:, :, i] * (1 + b), 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    def _apply_soft_skin(self, image: Image.Image, amount: float) -> Image.Image:
        """
        Apply soft skin effect (portrait smoothing).
        应用柔肤效果

        Args:
            image: Input image
            amount: Softening amount (0.0 to 1.0)

        Returns:
            Image with softened skin
        """
        img_array = np.array(image)

        # Apply bilateral filter for edge-preserving smoothing
        # This maintains important edges while smoothing skin
        smoothed = cv2.bilateralFilter(img_array, 9, 75, 75)

        # Blend original and smoothed
        result = cv2.addWeighted(
            img_array, 1 - amount * 0.5, smoothed, amount * 0.5, 0
        )

        return Image.fromarray(result)

    def _apply_edge_enhance(self, image: Image.Image, amount: float) -> Image.Image:
        """
        Apply edge enhancement for watercolor effect.
        应用边缘增强

        Args:
            image: Input image
            amount: Edge enhancement amount

        Returns:
            Image with enhanced edges
        """
        img_array = np.array(image)

        # Detect edges
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 100, 200)

        # Dilate edges slightly
        kernel = np.ones((2, 2), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Create edge overlay
        edge_overlay = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
        edge_overlay = edge_overlay.astype(np.float32) * amount * 0.3

        # Enhance edges in original
        img_float = img_array.astype(np.float32)
        enhanced = img_float + edge_overlay

        return Image.fromarray(np.clip(enhanced, 0, 255).astype(np.uint8))

    def _apply_tone_mapping(self, image: Image.Image) -> Image.Image:
        """
        Apply tone mapping for natural look.
        应用色调映射

        Args:
            image: Input image

        Returns:
            Image with tone mapping applied
        """
        img_array = np.array(image).astype(np.float32) / 255.0

        # Apply simple Reinhard tone mapping
        # dst = src / (1 + src)
        tone_mapped = img_array / (1.0 + img_array)

        # Normalize back to 0-255
        tone_mapped = (tone_mapped * 255).astype(np.uint8)

        return Image.fromarray(tone_mapped)

    def apply_video_filter(
        self, video_path: Union[str, Path], filter_name: str, output_path: Union[str, Path]
    ) -> str:
        """
        Apply a filter to a video.
        对视频应用滤镜

        Args:
            video_path: Path to input video
            filter_name: Name of the filter to apply
            output_path: Path to output video

        Returns:
            Path to the output video
        """
        logger.info(f"Applying filter '{filter_name}' to video: {video_path}")

        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if filter_name not in self.FILTER_PRESETS:
            logger.warning(f"Unknown filter '{filter_name}'")
            raise ValueError(f"Unknown filter: {filter_name}")

        try:
            import subprocess

            # Try to use ffmpeg for video processing
            ffmpeg_available = self._check_ffmpeg()

            if ffmpeg_available:
                output_path = self._apply_video_filter_ffmpeg(
                    video_path, filter_name, output_path
                )
            else:
                # Fallback: process keyframes and create video
                output_path = self._apply_video_filter_frames(
                    video_path, filter_name, output_path
                )

            logger.info(f"Video filter applied successfully: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to apply video filter: {e}")
            raise

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=False,
            )
            return True
        except FileNotFoundError:
            return False

    def _apply_video_filter_ffmpeg(
        self, video_path: Path, filter_name: str, output_path: Path
    ) -> Path:
        """
        Apply filter to video using ffmpeg.
        使用ffmpeg应用视频滤镜

        Args:
            video_path: Input video path
            filter_name: Filter name
            output_path: Output video path

        Returns:
            Output video path
        """
        preset = self.FILTER_PRESETS[filter_name]
        filters = []

        # Build ffmpeg filter string based on preset
        if "contrast" in preset:
            filters.append(f"eq=contrast={1 + preset['contrast']/100:.2f}")

        if "brightness" in preset:
            filters.append(f"eq=brightness={preset['brightness']/100:.2f}")

        if "saturation" in preset:
            filters.append(f"eq=saturation={1 + preset['saturation']/100:.2f}")

        # Apply vintage grain effect via ffmpeg
        if "grain" in preset and preset.get("grain", 0) > 0:
            noise = preset["grain"] * 100
            filters.append(f"noise=alls={noise}:allf=t")

        # Combine filters
        if filters:
            filter_str = ",".join(filters)
            cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vf",
                filter_str,
                "-c:a",
                "copy",
                "-y",
                str(output_path),
            ]
        else:
            # No filters, just copy
            cmd = ["ffmpeg", "-i", str(video_path), "-c", "copy", "-y", str(output_path)]

        logger.debug(f"Running ffmpeg command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.warning(f"ffmpeg processing failed, trying alternative: {result.stderr}")
            # Fallback to frame-based processing
            return self._apply_video_filter_frames(video_path, filter_name, output_path)

        return output_path

    def _apply_video_filter_frames(
        self, video_path: Path, filter_name: str, output_path: Path
    ) -> Path:
        """
        Apply filter to video by processing frames.
        通过处理帧来应用视频滤镜

        Args:
            video_path: Input video path
            filter_name: Filter name
            output_path: Output video path

        Returns:
            Output video path
        """
        import subprocess
        import tempfile

        logger.info("Processing video frames (fallback method)")

        # Create temp directory for frames
        temp_dir = Path(tempfile.mkdtemp())
        frame_pattern = temp_dir / "frame_%04d.png"

        try:
            # Extract frames
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(video_path),
                    "-vf",
                    "fps=30",
                    "-y",
                    str(frame_pattern),
                ],
                capture_output=True,
                check=True,
            )

            # Get frame files
            frames = sorted(temp_dir.glob("frame_*.png"))
            logger.info(f"Extracted {len(frames)} frames")

            if not frames:
                raise RuntimeError("No frames extracted from video")

            # Process frames with filter
            processed_frames = []
            for frame_path in frames:
                img = Image.open(frame_path)
                filtered = self.apply_filter(img, filter_name, 1.0)
                processed_path = frame_path.with_name(
                    frame_path.name.replace("frame_", "filtered_")
                )
                filtered.save(processed_path)
                processed_frames.append(processed_path)

            # Create video from processed frames
            # Use first frame for size info
            first_frame = Image.open(processed_frames[0])
            width, height = first_frame.size

            subprocess.run(
                [
                    "ffmpeg",
                    "-framerate",
                    "30",
                    "-i",
                    str(temp_dir / "filtered_%04d.png"),
                    "-vf",
                    f"scale={width}:{height}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                check=True,
            )

            logger.info(f"Video created: {output_path}")
            return output_path

        finally:
            # Cleanup temp files
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def get_filter_info(self, filter_name: str) -> dict:
        """
        Get information about a specific filter.
        获取滤镜信息

        Args:
            filter_name: Name of the filter

        Returns:
            Dictionary with filter information
        """
        if filter_name not in self.FILTER_PRESETS:
            return {}

        preset = self.FILTER_PRESETS[filter_name]
        return {
            "name": filter_name,
            "description": preset.get("description", ""),
            "parameters": {
                k: v
                for k, v in preset.items()
                if k not in ["description", "tone_effect"]
            },
        }

    def list_filters_with_info(self) -> List[dict]:
        """
        List all available filters with their information.
        列出所有可用滤镜及其信息

        Returns:
            List of filter info dictionaries
        """
        return [
            {"name": name, **preset}
            for name, preset in self.FILTER_PRESETS.items()
        ]


# Convenience functions for quick access
def apply_style_filter(
    image: Image.Image, filter_name: str, intensity: float = 1.0
) -> Image.Image:
    """
    Apply a style filter to an image (convenience function).
    应用风格滤镜(便捷函数)

    Args:
        image: Input PIL Image
        filter_name: Name of the filter
        intensity: Filter intensity (0.0 to 2.0)

    Returns:
        Filtered PIL Image
    """
    engine = StyleFilterEngine()
    return engine.apply_filter(image, filter_name, intensity)


def adjust_image_colors(
    image: Image.Image,
    hue: float = 0,
    saturation: float = 0,
    lightness: float = 0,
    brightness: float = 0,
    contrast: float = 0,
    exposure: float = 0,
    temperature: float = 0,
    tint: float = 0,
) -> Image.Image:
    """
    Apply multiple color adjustments at once (convenience function).
    一次性应用多种色彩调整(便捷函数)

    Args:
        image: Input PIL Image
        hue: Hue adjustment (-180 to 180)
        saturation: Saturation adjustment (-100 to 100)
        lightness: Lightness adjustment (-100 to 100)
        brightness: Brightness adjustment (-100 to 100)
        contrast: Contrast adjustment (-100 to 100)
        exposure: Exposure adjustment (-100 to 100)
        temperature: Temperature adjustment (-100 to 100)
        tint: Tint adjustment (-100 to 100)

    Returns:
        Adjusted PIL Image
    """
    color_adj = ColorAdjustment()
    result = image

    if hue != 0 or saturation != 0 or lightness != 0:
        result = color_adj.adjust_hsl(result, hue, saturation, lightness)
    if brightness != 0:
        result = color_adj.adjust_brightness(result, brightness)
    if contrast != 0:
        result = color_adj.adjust_contrast(result, contrast)
    if exposure != 0:
        result = color_adj.adjust_exposure(result, exposure)
    if saturation != 0:
        result = color_adj.adjust_saturation(result, saturation)
    if temperature != 0:
        result = color_adj.adjust_temperature(result, temperature)
    if tint != 0:
        result = color_adj.adjust_tint(result, tint)

    return result
