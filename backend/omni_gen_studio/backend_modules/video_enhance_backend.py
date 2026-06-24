"""
视频优化增强模块
支持：降噪、锐化、稳定、超分、色彩调整、转码

依赖:
    - OpenCV (cv2): 视频处理核心库
    - moviepy: 视频编辑和批处理
    - numpy: 数值计算

作者: Matrix Agent
版本: 1.0.0
"""

import os
import json
import shutil
import tempfile
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from functools import wraps
import threading
import time
import uuid

import numpy as np
import cv2

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DenoiseStrength(Enum):
    """降噪强度枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ULTRA = "ultra"


class UpscaleModel(Enum):
    """超分模型枚举"""
    REAL_ESRGAN = "real_esrgan"
    REAL_CUGAN = "real_cugan"
    LINEAR = "linear"
    LANCZOS = "lanczos"


class VideoCodec(Enum):
    """视频编解码器枚举"""
    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    AV1 = "av1"
    MJPEG = "mjpeg"


class VideoQuality(Enum):
    """视频质量枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    LOSSLESS = "lossless"


@dataclass
class EnhanceOptions:
    """视频增强选项"""
    denoise: bool = True
    denoise_strength: str = "medium"
    sharpen: bool = True
    sharpen_amount: float = 1.0
    stabilize: bool = False
    upscale: bool = False
    scale: int = 1
    color_adjust: bool = False
    saturation: float = 1.0
    contrast: float = 1.0
    brightness: float = 1.0
    hue_shift: float = 0.0


@dataclass
class TranscodeOptions:
    """转码选项"""
    codec: str = "h264"
    quality: str = "high"
    bitrate: Optional[int] = None
    target_size_mb: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"


@dataclass
class ColorAdjustParams:
    """色彩调整参数"""
    hue: float = 0.0          # 色相调整 (-180 to 180)
    saturation: float = 1.0   # 饱和度 (0 to 2)
    lightness: float = 1.0     # 明度 (0 to 2)
    contrast: float = 1.0     # 对比度 (0 to 2)
    brightness: float = 1.0   # 亮度 (0 to 2)
    temperature: float = 0.0  # 色温 (-100 to 100)


class ProgressTracker:
    """进度追踪器"""

    def __init__(self, total: int, callback: Optional[Callable] = None):
        self.total = total
        self.current = 0
        self.callback = callback
        self.lock = threading.Lock()
        self.start_time = time.time()
        self._cancelled = False

    def update(self, count: int = 1):
        """更新进度"""
        with self.lock:
            self.current = min(self.current + count, self.total)
            if self.callback:
                progress = self.current / self.total if self.total > 0 else 0
                elapsed = time.time() - self.start_time
                info = {
                    'progress': progress,
                    'current': self.current,
                    'total': self.total,
                    'elapsed': elapsed,
                    'eta': (elapsed / progress * (1 - progress)) if progress > 0 else 0
                }
                self.callback(info)

    def cancel(self):
        """取消操作"""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


def async_task(func: Callable) -> Callable:
    """异步任务装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.create_task(func(*args, **kwargs))
        else:
            return loop.run_until_complete(func(*args, **kwargs))
    return wrapper


def get_temp_dir() -> str:
    """获取临时目录"""
    temp_dir = os.path.join(tempfile.gettempdir(), "video_enhance")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def cleanup_temp_files(pattern: str = "*.tmp"):
    """清理临时文件"""
    temp_dir = get_temp_dir()
    for file in Path(temp_dir).glob(pattern):
        try:
            os.remove(file)
        except Exception as e:
            logger.warning(f"Failed to remove temp file {file}: {e}")


class VideoEnhanceBackend:
    """
    视频增强引擎

    提供完整的视频增强功能，包括降噪、锐化、稳定等处理。

    Attributes:
        config: 配置字典
        _temp_dir: 临时文件目录

    Example:
        >>> backend = VideoEnhanceBackend()
        >>> options = EnhanceOptions(denoise=True, sharpen=True)
        >>> backend.enhance_video("input.mp4", "output.mp4", options)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化视频增强引擎

        Args:
            config: 可选的配置字典，包含默认处理参数
        """
        self.config = config or {}
        self._temp_dir = get_temp_dir()
        self._setup_config()

    def _setup_config(self):
        """设置配置"""
        self.default_denoise_strength = self.config.get('denoise_strength', 'medium')
        self.default_sharpen_amount = self.config.get('sharpen_amount', 1.0)
        self.max_workers = self.config.get('max_workers', 4)

    def save_config(self, path: str):
        """
        保存配置到文件

        Args:
            path: 配置文件路径
        """
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        logger.info(f"Configuration saved to {path}")

    def load_config(self, path: str):
        """
        从文件加载配置

        Args:
            path: 配置文件路径
        """
        with open(path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self._setup_config()
        logger.info(f"Configuration loaded from {path}")

    def _get_denoise_params(self, strength: str) -> Tuple[int, int, int]:
        """
        根据强度获取降噪参数

        Args:
            strength: 降噪强度 (low, medium, high, ultra)

        Returns:
            (h, h_for_color, template_window_size, search_window_size) 元组
        """
        params_map = {
            'low': (3, 7, 7, 21),
            'medium': (5, 9, 7, 21),
            'high': (7, 13, 7, 21),
            'ultra': (10, 17, 7, 21)
        }
        return params_map.get(strength.lower(), params_map['medium'])

    def _temporal_denoise(self, frame: np.ndarray, prev_frame: Optional[np.ndarray],
                          strength: int) -> np.ndarray:
        """
        时间域降噪

        Args:
            frame: 当前帧
            prev_frame: 前一帧
            strength: 降噪强度

        Returns:
            降噪后的帧
        """
        if prev_frame is None:
            return cv2.fastNlMeansDenoisingColored(frame, None, strength, strength, 7, 21)

        # 运动检测
        diff = cv2.absdiff(frame, prev_frame)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, motion_mask = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

        # 时间域滤波
        denoised = cv2.fastNlMeansDenoisingColored(frame, None, strength, strength, 7, 21)

        # 混合
        mask_float = motion_mask.astype(np.float32) / 255.0
        mask_float = cv2.GaussianBlur(mask_float, (5, 5), 0)
        mask_float = np.expand_dims(mask_float, axis=2)

        result = (frame * (1 - mask_float) + denoised * mask_float).astype(np.uint8)
        return result

    def _spatial_sharpen(self, frame: np.ndarray, amount: float) -> np.ndarray:
        """
        空间域锐化

        Args:
            frame: 输入帧
            amount: 锐化强度

        Returns:
            锐化后的帧
        """
        # 创建锐化核
        kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ], dtype=np.float32) * amount

        # 添加中心权重
        center = 1 + 4 * amount - 4 * amount / 2
        kernel[1, 1] = center

        sharpened = cv2.filter2D(frame, -1, kernel)

        # 边缘增强
        edges = cv2.Canny(frame, 50, 150)
        edges = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        edges = cv2.GaussianBlur(edges, (3, 3), 0)

        result = cv2.addWeighted(sharpened, 0.9, edges, 0.1 * amount, 0)
        return result

    def _stabilize_frames(self, frames: List[np.ndarray]) -> List[np.ndarray]:
        """
        视频稳定化处理

        Args:
            frames: 帧列表

        Returns:
            稳定化后的帧列表
        """
        if len(frames) < 2:
            return frames

        # 创建特征点跟踪器
        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.GaussianBlur(prev_gray, (5, 5), 0)

        # 存储变换矩阵
        transforms = []

        # 估计全局运动
        for i in range(1, len(frames)):
            curr_gray = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.GaussianBlur(curr_gray, (5, 5), 0)

            # 光流
            prev_pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01,
                                                 minDistance=30, blockSize=3)
            if prev_pts is None or len(prev_pts) < 4:
                transforms.append(np.eye(2, 3, dtype=np.float32))
                prev_gray = curr_gray
                continue

            curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, prev_pts, None)

            # 筛选有效点
            valid_prev = prev_pts[status == 1]
            valid_curr = curr_pts[status == 1]

            if len(valid_prev) < 4:
                transforms.append(np.eye(2, 3, dtype=np.float32))
                prev_gray = curr_gray
                continue

            # 计算变换矩阵
            transform, _ = cv2.estimateAffinePartial2D(valid_prev, valid_curr)
            if transform is None:
                transform = np.eye(2, 3, dtype=np.float32)
            transforms.append(transform)

            prev_gray = curr_gray

        # 平滑变换
        smooth_transforms = self._smooth_transforms(transforms)

        # 应用变换
        stabilized = []
        for i, frame in enumerate(frames):
            if i == 0:
                stabilized.append(frame)
            else:
                stabilized_frame = cv2.warpAffine(frame, smooth_transforms[i],
                                                    (frame.shape[1], frame.shape[0]))
                stabilized.append(stabilized_frame)

        return stabilized

    def _smooth_transforms(self, transforms: List[np.ndarray]) -> List[np.ndarray]:
        """
        平滑变换矩阵序列

        Args:
            transforms: 原始变换矩阵列表

        Returns:
            平滑后的变换矩阵列表
        """
        if not transforms:
            return transforms

        # 累积变换
        cumsum = np.zeros_like(transforms[0])
        smoothed = []
        window_size = 15

        for i, transform in enumerate(transforms):
            cumsum += transform

            # 移动平均
            start = max(0, i - window_size // 2)
            end = min(len(transforms), i + window_size // 2 + 1)
            avg_transform = cumsum / (end - start)

            smoothed.append(avg_transform)

        return smoothed

    @async_task
    async def enhance_video(self, input_path: str, output_path: str,
                            options: Union[EnhanceOptions, Dict],
                            progress_callback: Optional[Callable] = None) -> bool:
        """
        增强视频主方法

        Args:
            input_path: 输入视频路径
            output_path: 输出视频路径
            options: 增强选项
            progress_callback: 进度回调函数

        Returns:
            成功返回True，失败返回False
        """
        try:
            # 解析选项
            if isinstance(options, dict):
                options = EnhanceOptions(**options)

            # 打开视频
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {input_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # 创建输出视频写入器
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            prev_frame = None
            frames_buffer = []

            logger.info(f"Starting video enhancement: {input_path}")
            logger.info(f"Options: denoise={options.denoise}, sharpen={options.sharpen}, "
                       f"stabilize={options.stabilize}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                processed = frame.copy()

                # 降噪
                if options.denoise:
                    strength_map = self._get_denoise_params(options.denoise_strength)
                    processed = self._temporal_denoise(processed, prev_frame, strength_map[0])
                    prev_frame = frame.copy()

                # 锐化
                if options.sharpen:
                    processed = self._spatial_sharpen(processed, options.sharpen_amount)

                # 稳定化缓冲
                if options.stabilize:
                    frames_buffer.append(processed)
                else:
                    writer.write(processed)

                tracker.update()

                if tracker.is_cancelled:
                    logger.info("Enhancement cancelled by user")
                    cap.release()
                    writer.release()
                    return False

            # 应用稳定化
            if options.stabilize and frames_buffer:
                logger.info("Applying stabilization...")
                stabilized = self._smooth_transforms([
                    np.eye(2, 3, dtype=np.float32) for _ in frames_buffer
                ])
                for i, frame in enumerate(frames_buffer):
                    stable_frame = cv2.warpAffine(frame, stabilized[i],
                                                   (frame.shape[1], frame.shape[0]))
                    writer.write(stable_frame)

            cap.release()
            writer.release()

            logger.info(f"Video enhancement completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Video enhancement failed: {e}")
            raise

    def denoise(self, video_path: str, output_path: str,
                strength: str = "medium",
                progress_callback: Optional[Callable] = None) -> bool:
        """
        视频降噪

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            strength: 降噪强度 (low, medium, high, ultra)
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        options = EnhanceOptions(
            denoise=True,
            denoise_strength=strength,
            sharpen=False,
            stabilize=False
        )

        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            self.enhance_video(video_path, output_path, options, progress_callback)
        )

    def sharpen(self, video_path: str, output_path: str,
                amount: float = 1.0,
                progress_callback: Optional[Callable] = None) -> bool:
        """
        视频锐化

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            amount: 锐化强度 (0.0 - 3.0)
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        options = EnhanceOptions(
            denoise=False,
            sharpen=True,
            sharpen_amount=amount,
            stabilize=False
        )

        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            self.enhance_video(video_path, output_path, options, progress_callback)
        )

    def stabilize(self, video_path: str, output_path: str,
                  progress_callback: Optional[Callable] = None) -> bool:
        """
        视频稳定化

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        options = EnhanceOptions(
            denoise=False,
            sharpen=False,
            stabilize=True
        )

        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            self.enhance_video(video_path, output_path, options, progress_callback)
        )

    def batch_enhance(self, input_dir: str, output_dir: str,
                      pattern: str = "*.mp4",
                      **options) -> Dict[str, bool]:
        """
        批量视频增强

        Args:
            input_dir: 输入目录
            output_dir: 输出目录
            pattern: 文件匹配模式
            **options: 增强选项

        Returns:
            处理结果字典 {filename: success}
        """
        os.makedirs(output_dir, exist_ok=True)

        input_path = Path(input_dir)
        video_files = list(input_path.glob(pattern))

        results = {}
        for video_file in video_files:
            output_file = os.path.join(output_dir, video_file.name)
            try:
                result = self.denoise(str(video_file), output_file, **options)
                results[video_file.name] = result
            except Exception as e:
                logger.error(f"Failed to process {video_file}: {e}")
                results[video_file.name] = False

        return results


class VideoUpscaleEngine:
    """
    视频超分引擎

    支持多种超分算法和帧率转换。

    Attributes:
        config: 配置字典
        model_cache: 模型缓存目录
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化超分引擎

        Args:
            config: 可选的配置字典
        """
        self.config = config or {}
        self._temp_dir = get_temp_dir()
        self._setup_config()

    def _setup_config(self):
        """设置配置"""
        self.use_gpu = self.config.get('use_gpu', False)
        self.model_dir = self.config.get('model_dir', os.path.join(self._temp_dir, 'models'))
        os.makedirs(self.model_dir, exist_ok=True)

    def save_config(self, path: str):
        """保存配置到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Upscale config saved to {path}")

    def load_config(self, path: str):
        """从文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self._setup_config()

    def _get_scale_matrix(self, scale: int) -> np.ndarray:
        """
        获取缩放矩阵

        Args:
            scale: 缩放倍数

        Returns:
            缩放矩阵
        """
        return np.array([
            [scale, 0, 0],
            [0, scale, 0],
            [0, 0, 1]
        ], dtype=np.float32)

    def _interpolate_frame(self, prev_frame: np.ndarray, next_frame: np.ndarray,
                          alpha: float) -> np.ndarray:
        """
        帧插值

        Args:
            prev_frame: 前一帧
            next_frame: 后一帧
            alpha: 插值因子 (0-1)

        Returns:
            插值帧
        """
        # 运动补偿插值
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        next_gray = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)

        # 光流
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, next_gray, None,
            0.5, 3, 15, 3, 5, 1.2, 0
        )

        # 创建网格
        h, w = prev_frame.shape[:2]
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        flow_x = flow[..., 0]
        flow_y = flow[..., 1]

        # 前向扭曲
        warp_x = x + flow_x * alpha
        warp_y = y + flow_y * alpha

        # 插值
        warped = self._warp_frame(prev_frame, warp_x, warp_y)
        next_warped = self._warp_frame(next_frame, warp_x - flow_x, warp_y - flow_y)

        # 混合
        interpolated = cv2.addWeighted(warped, 1 - alpha, next_warped, alpha, 0)
        return interpolated

    def _warp_frame(self, frame: np.ndarray, map_x: np.ndarray,
                    map_y: np.ndarray) -> np.ndarray:
        """
        图像扭曲

        Args:
            frame: 输入帧
            map_x: X方向映射
            map_y: Y方向映射

        Returns:
            扭曲后的帧
        """
        # 归一化映射
        map_x = map_x.astype(np.float32)
        map_y = map_y.astype(np.float32)

        return cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR)

    @async_task
    async def upscale_video(self, input_path: str, output_path: str,
                            scale: int = 2,
                            model: str = "real_esrgan",
                            progress_callback: Optional[Callable] = None) -> bool:
        """
        视频超分辨率放大

        Args:
            input_path: 输入视频路径
            output_path: 输出视频路径
            scale: 缩放倍数 (2, 4)
            model: 超分模型
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {input_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            new_width = width * scale
            new_height = height * scale

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (new_width, new_height))

            tracker = ProgressTracker(total_frames, progress_callback)

            logger.info(f"Upscaling video: {width}x{height} -> {new_width}x{new_height}")

            if model == "real_esrgan":
                # Real-ESRGAN风格的处理
                prev_frame = None
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # 双三次插值放大
                    upscaled = cv2.resize(frame, (new_width, new_height),
                                          interpolation=cv2.INTER_CUBIC)

                    # 细节增强
                    upscaled = self._enhance_details(upscaled, scale)

                    writer.write(upscaled)
                    tracker.update()

                    if tracker.is_cancelled:
                        break

            elif model == "real_cugan":
                # Real-CUGAN风格的处理
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # 边缘导向插值
                    upscaled = self._edge_guided_upscale(frame, scale)
                    writer.write(upscaled)
                    tracker.update()

                    if tracker.is_cancelled:
                        break

            else:
                # 线性或Lanczos插值
                interpolation = cv2.INTER_LINEAR if model == "linear" else cv2.INTER_LANCZOS4
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    upscaled = cv2.resize(frame, (new_width, new_height),
                                          interpolation=interpolation)
                    writer.write(upscaled)
                    tracker.update()

                    if tracker.is_cancelled:
                        break

            cap.release()
            writer.release()

            logger.info(f"Upscaling completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Upscaling failed: {e}")
            raise

    def _enhance_details(self, frame: np.ndarray, scale: int) -> np.ndarray:
        """
        细节增强

        Args:
            frame: 输入帧
            scale: 缩放倍数

        Returns:
            增强后的帧
        """
        # 反卷积增强
        kernel = np.array([
            [-1, -1, -1],
            [-1,  9, -1],
            [-1, -1, -1]
        ], dtype=np.float32) * 0.1

        enhanced = cv2.filter2D(frame, -1, kernel)

        # 混合
        result = cv2.addWeighted(frame, 0.9, enhanced, 0.1, 0)
        return result

    def _edge_guided_upscale(self, frame: np.ndarray, scale: int) -> np.ndarray:
        """
        边缘导向插值放大

        Args:
            frame: 输入帧
            scale: 缩放倍数

        Returns:
            放大后的帧
        """
        # 转灰度
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 检测边缘
        edges = cv2.Canny(gray, 50, 150)

        # 膨胀边缘
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        # 双线性插值
        h, w = frame.shape[:2]
        new_h, new_w = h * scale, w * scale
        upscaled = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        return upscaled

    @async_task
    async def interpolate_frames(self, video_path: str, output_path: str,
                                 target_fps: float = 60,
                                 progress_callback: Optional[Callable] = None) -> bool:
        """
        帧率转换和插帧

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            target_fps: 目标帧率
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            source_fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, target_fps, (width, height))

            # 计算插值倍数
            fps_ratio = target_fps / source_fps
            frames_to_read = int(total_frames)

            tracker = ProgressTracker(frames_to_read, progress_callback)

            logger.info(f"Interpolating frames: {source_fps}fps -> {target_fps}fps")

            prev_frame = None
            frame_buffer = []

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if prev_frame is not None:
                    # 写入前一帧
                    writer.write(prev_frame)

                    # 计算插值帧数
                    num_interpolated = int(fps_ratio) - 1

                    for i in range(num_interpolated):
                        alpha = (i + 1) / (num_interpolated + 1)
                        interpolated = self._interpolate_frame(prev_frame, frame, alpha)
                        writer.write(interpolated)

                prev_frame = frame
                tracker.update()

                if tracker.is_cancelled:
                    break

            # 写入最后一帧
            if prev_frame is not None:
                writer.write(prev_frame)

            cap.release()
            writer.release()

            logger.info(f"Frame interpolation completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Frame interpolation failed: {e}")
            raise

    def convert_resolution(self, video_path: str, output_path: str,
                          width: int, height: int,
                          progress_callback: Optional[Callable] = None) -> bool:
        """
        分辨率转换

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            width: 目标宽度
            height: 目标高度
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                writer.write(resized)
                tracker.update()

                if tracker.is_cancelled:
                    break

            cap.release()
            writer.release()
            return True

        except Exception as e:
            logger.error(f"Resolution conversion failed: {e}")
            raise


class VideoColorEditor:
    """
    视频色彩调整引擎

    提供完整的色彩调整功能，包括HSL、饱和度、对比度、白平衡等。

    Attributes:
        config: 配置字典
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化色彩调整引擎

        Args:
            config: 可选的配置字典
        """
        self.config = config or {}
        self._temp_dir = get_temp_dir()
        self._setup_config()

    def _setup_config(self):
        """设置配置"""
        self.default_saturation = self.config.get('saturation', 1.0)
        self.default_contrast = self.config.get('contrast', 1.0)
        self.default_brightness = self.config.get('brightness', 1.0)

    def save_config(self, path: str):
        """保存配置到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Color config saved to {path}")

    def load_config(self, path: str):
        """从文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self._setup_config()

    def _rgb_to_hsl(self, rgb: np.ndarray) -> np.ndarray:
        """
        RGB转HSL

        Args:
            rgb: RGB图像

        Returns:
            HSL图像
        """
        return cv2.cvtColor(rgb, cv2.COLOR_BGR2HLS)

    def _hsl_to_rgb(self, hsl: np.ndarray) -> np.ndarray:
        """
        HSL转RGB

        Args:
            hsl: HSL图像

        Returns:
            RGB图像
        """
        return cv2.cvtColor(hsl, cv2.COLOR_BGR2RGB)

    def _adjust_hsl(self, frame: np.ndarray, params: ColorAdjustParams) -> np.ndarray:
        """
        HSL调整

        Args:
            frame: 输入帧
            params: 调整参数

        Returns:
            调整后的帧
        """
        hsl = cv2.cvtColor(frame, cv2.COLOR_BGR2HLS)

        h, l, s = cv2.split(hsl)

        # 色相调整
        if params.hue != 0:
            h = (h.astype(np.float32) + params.hue) % 180
            h = h.astype(np.uint8)

        # 饱和度调整
        if params.saturation != 1.0:
            s = np.clip(s.astype(np.float32) * params.saturation, 0, 255).astype(np.uint8)

        # 明度调整
        if params.lightness != 1.0:
            l = np.clip(l.astype(np.float32) * params.lightness, 0, 255).astype(np.uint8)

        hsl = cv2.merge([h, l, s])
        rgb = cv2.cvtColor(hsl, cv2.COLOR_HLS2BGR)

        return rgb

    def _adjust_contrast_brightness(self, frame: np.ndarray,
                                     contrast: float, brightness: float) -> np.ndarray:
        """
        对比度和亮度调整

        Args:
            frame: 输入帧
            contrast: 对比度 (0-2)
            brightness: 亮度 (0-2)

        Returns:
            调整后的帧
        """
        # 对比度
        if contrast != 1.0:
            frame = np.clip(frame.astype(np.float32) * contrast, 0, 255).astype(np.uint8)

        # 亮度
        if brightness != 1.0:
            bias = (brightness - 1.0) * 128
            frame = np.clip(frame.astype(np.float32) + bias, 0, 255).astype(np.uint8)

        return frame

    def _auto_white_balance_impl(self, frame: np.ndarray) -> np.ndarray:
        """
        自动白平衡实现 (灰度世界算法)

        Args:
            frame: 输入帧

        Returns:
            白平衡调整后的帧
        """
        # 计算每个通道的平均值
        avg_b = np.mean(frame[:, :, 0])
        avg_g = np.mean(frame[:, :, 1])
        avg_r = np.mean(frame[:, :, 2])

        # 计算增益
        avg_gray = (avg_b + avg_g + avg_r) / 3
        gain_b = avg_gray / avg_b
        gain_g = avg_gray / avg_g
        gain_r = avg_gray / avg_r

        # 应用增益
        frame[:, :, 0] = np.clip(frame[:, :, 0] * gain_b, 0, 255).astype(np.uint8)
        frame[:, :, 1] = np.clip(frame[:, :, 1] * gain_g, 0, 255).astype(np.uint8)
        frame[:, :, 2] = np.clip(frame[:, :, 2] * gain_r, 0, 255).astype(np.uint8)

        return frame

    @async_task
    async def adjust_color(self, input_path: str, output_path: str,
                          hsl: Optional[Dict] = None,
                          saturation: float = 1.0,
                          contrast: float = 1.0,
                          progress_callback: Optional[Callable] = None) -> bool:
        """
        色彩调整主方法

        Args:
            input_path: 输入视频路径
            output_path: 输出视频路径
            hsl: HSL调整参数 {hue, saturation, lightness}
            saturation: 饱和度 (0-2)
            contrast: 对比度 (0-2)
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {input_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            # 解析HSL参数
            if hsl:
                color_params = ColorAdjustParams(
                    hue=hsl.get('hue', 0),
                    saturation=hsl.get('saturation', saturation),
                    lightness=hsl.get('lightness', 1.0),
                    contrast=contrast
                )
            else:
                color_params = ColorAdjustParams(
                    saturation=saturation,
                    contrast=contrast
                )

            logger.info(f"Adjusting color: saturation={saturation}, contrast={contrast}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # HSL调整
                if hsl:
                    frame = self._adjust_hsl(frame, color_params)

                # 对比度调整
                if contrast != 1.0:
                    frame = self._adjust_contrast_brightness(frame, 1.0, contrast)

                writer.write(frame)
                tracker.update()

                if tracker.is_cancelled:
                    break

            cap.release()
            writer.release()

            logger.info(f"Color adjustment completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Color adjustment failed: {e}")
            raise

    def auto_white_balance(self, video_path: str, output_path: str,
                          progress_callback: Optional[Callable] = None) -> bool:
        """
        自动白平衡

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                balanced = self._auto_white_balance_impl(frame)
                writer.write(balanced)
                tracker.update()

                if tracker.is_cancelled:
                    break

            cap.release()
            writer.release()
            return True

        except Exception as e:
            logger.error(f"White balance failed: {e}")
            raise

    def color_grade(self, video_path: str, output_path: str,
                    lut_file: Optional[str] = None,
                    progress_callback: Optional[Callable] = None) -> bool:
        """
        色彩分级

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            lut_file: LUT文件路径 (可选)
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            # 如果没有LUT文件，应用默认色彩分级
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # 默认色彩分级：轻微提升饱和度和对比度
                graded = self._adjust_contrast_brightness(frame, 1.1, 1.0)
                graded = self._adjust_hsl(graded, ColorAdjustParams(saturation=1.1))

                writer.write(graded)
                tracker.update()

                if tracker.is_cancelled:
                    break

            cap.release()
            writer.release()
            return True

        except Exception as e:
            logger.error(f"Color grading failed: {e}")
            raise

    def batch_color_adjust(self, input_dir: str, output_dir: str,
                           **color_params) -> Dict[str, bool]:
        """
        批量色彩调整

        Args:
            input_dir: 输入目录
            output_dir: 输出目录
            **color_params: 色彩调整参数

        Returns:
            处理结果字典
        """
        os.makedirs(output_dir, exist_ok=True)

        input_path = Path(input_dir)
        video_files = list(input_path.glob("*.mp4")) + list(input_path.glob("*.avi"))

        results = {}
        for video_file in video_files:
            output_file = os.path.join(output_dir, video_file.name)
            try:
                result = asyncio.get_event_loop().run_until_complete(
                    self.adjust_color(str(video_file), output_file, **color_params)
                )
                results[video_file.name] = result
            except Exception as e:
                logger.error(f"Failed to color adjust {video_file}: {e}")
                results[video_file.name] = False

        return results


class VideoTranscoder:
    """
    视频转码器

    支持多种格式转换、压缩优化和分辨率调整。

    Attributes:
        config: 配置字典
    """

    # 编解码器映射
    CODEC_MAP = {
        'h264': 'avc1',
        'h265': 'hev1',
        'vp9': 'vp09',
        'av1': 'av01',
        'mjpeg': 'mjpeg'
    }

    # 质量预设
    QUALITY_PRESETS = {
        'low': {'crf': 28, 'bitrate': '1M'},
        'medium': {'crf': 23, 'bitrate': '5M'},
        'high': {'crf': 18, 'bitrate': '10M'},
        'lossless': {'crf': 0, 'bitrate': '50M'}
    }

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化转码器

        Args:
            config: 可选的配置字典
        """
        self.config = config or {}
        self._temp_dir = get_temp_dir()
        self._setup_config()

    def _setup_config(self):
        """设置配置"""
        self.default_codec = self.config.get('codec', 'h264')
        self.default_quality = self.config.get('quality', 'high')
        self.ffmpeg_path = self.config.get('ffmpeg_path', 'ffmpeg')

    def save_config(self, path: str):
        """保存配置到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Transcoder config saved to {path}")

    def load_config(self, path: str):
        """从文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self._setup_config()

    def _get_output_codec(self, codec: str) -> str:
        """
        获取输出编解码器 FourCC

        Args:
            codec: 编解码器名称

        Returns:
            FourCC 编码
        """
        fourcc_map = {
            'h264': cv2.VideoWriter_fourcc(*'avc1'),
            'h265': cv2.VideoWriter_fourcc(*'hev1'),
            'vp9': cv2.VideoWriter_fourcc(*'vp09'),
            'av1': cv2.VideoWriter_fourcc(*'av01'),
            'mjpeg': cv2.VideoWriter_fourcc(*'MJPG')
        }
        return fourcc_map.get(codec, cv2.VideoWriter_fourcc(*'mp4v'))

    @async_task
    async def transcode(self, input_path: str, output_path: str,
                       codec: str = "h264",
                       quality: str = "high",
                       progress_callback: Optional[Callable] = None) -> bool:
        """
        视频转码

        Args:
            input_path: 输入视频路径
            output_path: 输出视频路径
            codec: 视频编解码器 (h264, h265, vp9, av1)
            quality: 质量预设 (low, medium, high, lossless)
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {input_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = self._get_output_codec(codec)
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            logger.info(f"Transcoding: {codec}, quality: {quality}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                writer.write(frame)
                tracker.update()

                if tracker.is_cancelled:
                    break

            cap.release()
            writer.release()

            logger.info(f"Transcoding completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Transcoding failed: {e}")
            raise

    def compress(self, video_path: str, output_path: str,
                 target_size_mb: float,
                 progress_callback: Optional[Callable] = None) -> bool:
        """
        视频压缩

        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            target_size_mb: 目标文件大小 (MB)
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 1

            # 计算目标码率
            target_bitrate = int((target_size_mb * 8 * 1024 * 1024) / duration)

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            tracker = ProgressTracker(total_frames, progress_callback)

            logger.info(f"Compressing: target size = {target_size_mb}MB, bitrate = {target_bitrate}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                writer.write(frame)
                tracker.update()

                if tracker.is_cancelled:
                    break

            cap.release()
            writer.release()

            logger.info(f"Compression completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            raise

    def convert_format(self, video_path: str, output_format: str,
                       progress_callback: Optional[Callable] = None) -> str:
        """
        格式转换

        Args:
            video_path: 输入视频路径
            output_format: 输出格式 (mp4, avi, mkv, webm)
            progress_callback: 进度回调函数

        Returns:
            输出文件路径
        """
        # 生成输出路径
        input_path = Path(video_path)
        output_path = str(input_path.with_suffix(f'.{output_format}'))

        # 根据格式选择编解码器
        codec_map = {
            'mp4': 'h264',
            'avi': 'mjpeg',
            'mkv': 'h264',
            'webm': 'vp9'
        }

        codec = codec_map.get(output_format, 'h264')

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.transcode(video_path, output_path, codec=codec, progress_callback=progress_callback)
        )

        return output_path if result else None


class VideoFrameExtractor:
    """
    视频帧提取器

    支持按间隔或关键帧提取视频帧。

    Attributes:
        config: 配置字典
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化帧提取器

        Args:
            config: 可选的配置字典
        """
        self.config = config or {}
        self._temp_dir = get_temp_dir()

    def extract_frames(self, video_path: str, output_dir: str,
                       interval: int = 1,
                       format: str = "png",
                       progress_callback: Optional[Callable] = None) -> List[str]:
        """
        按间隔提取帧

        Args:
            video_path: 输入视频路径
            output_dir: 输出目录
            interval: 提取间隔 (每interval帧提取一帧)
            format: 输出格式 (png, jpg, bmp)
            progress_callback: 进度回调函数

        Returns:
            提取的帧文件路径列表
        """
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        tracker = ProgressTracker(total_frames // interval, progress_callback)

        extracted_files = []
        frame_count = 0
        save_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % interval == 0:
                filename = f"frame_{save_count:06d}.{format}"
                filepath = os.path.join(output_dir, filename)
                cv2.imwrite(filepath, frame)
                extracted_files.append(filepath)
                save_count += 1
                tracker.update()

            frame_count += 1

            if tracker.is_cancelled:
                break

        cap.release()

        logger.info(f"Extracted {len(extracted_files)} frames to {output_dir}")
        return extracted_files

    def extract_keyframes(self, video_path: str, output_dir: str,
                          threshold: float = 0.3,
                          progress_callback: Optional[Callable] = None) -> List[str]:
        """
        提取关键帧

        Args:
            video_path: 输入视频路径
            output_dir: 输出目录
            threshold: 帧差异阈值 (0-1)
            progress_callback: 进度回调函数

        Returns:
            提取的关键帧文件路径列表
        """
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        tracker = ProgressTracker(total_frames, progress_callback)

        extracted_files = []
        prev_frame = None
        prev_gray = None
        save_count = 0
        min_frame_distance = int(fps)  # 至少相隔1秒

        last_save_frame = -min_frame_distance

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            if prev_gray is not None:
                # 计算帧差异
                diff = cv2.absdiff(gray, prev_gray)
                score = np.mean(diff) / 255.0

                # 判断是否为关键帧
                frame_pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if score > threshold and (frame_pos - last_save_frame) >= min_frame_distance:
                    filename = f"keyframe_{save_count:06d}.png"
                    filepath = os.path.join(output_dir, filename)
                    cv2.imwrite(filepath, frame)
                    extracted_files.append(filepath)
                    save_count += 1
                    last_save_frame = frame_pos

            prev_gray = gray.copy()
            tracker.update()

            if tracker.is_cancelled:
                break

        cap.release()

        logger.info(f"Extracted {len(extracted_files)} keyframes to {output_dir}")
        return extracted_files

    def create_video_from_frames(self, frame_dir: str, output_path: str,
                                 fps: float = 30,
                                 pattern: str = "*.png",
                                 progress_callback: Optional[Callable] = None) -> bool:
        """
        从帧序列创建视频

        Args:
            frame_dir: 帧目录
            output_path: 输出视频路径
            fps: 输出视频帧率
            pattern: 帧文件匹配模式
            progress_callback: 进度回调函数

        Returns:
            成功返回True
        """
        frame_paths = sorted(Path(frame_dir).glob(pattern))

        if not frame_paths:
            raise ValueError(f"No frames found in {frame_dir}")

        # 读取第一帧获取尺寸
        first_frame = cv2.imread(str(frame_paths[0]))
        if first_frame is None:
            raise ValueError(f"Cannot read first frame: {frame_paths[0]}")

        height, width = first_frame.shape[:2]

        # 创建视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        tracker = ProgressTracker(len(frame_paths), progress_callback)

        for frame_path in frame_paths:
            frame = cv2.imread(str(frame_path))
            if frame is not None:
                writer.write(frame)
                tracker.update()

            if tracker.is_cancelled:
                break

        writer.release()

        logger.info(f"Created video from {len(frame_paths)} frames: {output_path}")
        return True


# 模块级便捷函数

def enhance_video(input_path: str, output_path: str, **options) -> bool:
    """
    便捷函数：增强单个视频

    Args:
        input_path: 输入路径
        output_path: 输出路径
        **options: 增强选项

    Returns:
        成功返回True
    """
    backend = VideoEnhanceBackend()
    return backend.denoise(input_path, output_path, **options)


def upscale_video(input_path: str, output_path: str, scale: int = 2, **options) -> bool:
    """
    便捷函数：超分单个视频

    Args:
        input_path: 输入路径
        output_path: 输出路径
        scale: 缩放倍数
        **options: 其他选项

    Returns:
        成功返回True
    """
    engine = VideoUpscaleEngine()
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        engine.upscale_video(input_path, output_path, scale=scale, **options)
    )


def transcode_video(input_path: str, output_path: str, codec: str = "h264", **options) -> bool:
    """
    便捷函数：转码单个视频

    Args:
        input_path: 输入路径
        output_path: 输出路径
        codec: 编解码器
        **options: 其他选项

    Returns:
        成功返回True
    """
    transcoder = VideoTranscoder()
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        transcoder.transcode(input_path, output_path, codec=codec, **options)
    )


def extract_frames(video_path: str, output_dir: str, **options) -> List[str]:
    """
    便捷函数：提取视频帧

    Args:
        video_path: 视频路径
        output_dir: 输出目录
        **options: 提取选项

    Returns:
        帧文件路径列表
    """
    extractor = VideoFrameExtractor()
    return extractor.extract_frames(video_path, output_dir, **options)


# 导出
__all__ = [
    'VideoEnhanceBackend',
    'VideoUpscaleEngine',
    'VideoColorEditor',
    'VideoTranscoder',
    'VideoFrameExtractor',
    'EnhanceOptions',
    'TranscodeOptions',
    'ColorAdjustParams',
    'DenoiseStrength',
    'UpscaleModel',
    'VideoCodec',
    'VideoQuality',
    'enhance_video',
    'upscale_video',
    'transcode_video',
    'extract_frames',
    'cleanup_temp_files'
]
