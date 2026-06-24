"""
NanoBot Factory - 视频数据生产管线
Video Data Production Pipeline

功能:
- 视频帧提取 (ffmpeg + OpenCV)
- 视频感知去重 (使用 data_quality_engine 的 PerceptualHasher)
- 视频质量过滤 (使用 data_quality_engine 的 QualityScore/BatchQualityReport 数据结构)
- 视频分段 (scene detection)
- 关键帧提取
- 批量处理
"""

import os, sys, io, json, logging, subprocess, tempfile, shutil, math, struct
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Iterator, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from collections import defaultdict
from PIL import Image

import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# 从 data_quality_engine 导入 (避免循环引用)
# ============================================================================

def _import_quality_engine():
    """延迟导入 DataQualityEngine 的数据结构"""
    from data_quality_engine import PerceptualHasher, QualityScore, BatchQualityReport
    return PerceptualHasher, QualityScore, BatchQualityReport


# ============================================================================
# 视频分段策略
# ============================================================================

class SceneDetectionStrategy(str, Enum):
    """场景检测策略"""
    HISTOGRAM = "histogram"         # 直方图差异
    CONTENT = "content"             # 内容感知 (使用pHash)
    FFMPEG = "ffmpeg"               # 使用ffmpeg的scene detect
    FIXED_INTERVAL = "fixed"        # 固定间隔分段


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class VideoInfo:
    """视频基本信息"""
    path: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    total_frames: int = 0
    duration_sec: float = 0.0
    codec: str = ""
    file_size: int = 0
    has_audio: bool = False
    bitrate: int = 0


@dataclass
class VideoFrame:
    """视频帧"""
    frame_index: int
    timestamp_sec: float
    image: Optional[np.ndarray] = None  # BGR numpy array (OpenCV格式)
    pil_image: Optional[Image.Image] = None
    phash: str = ""
    quality_score: float = 0.0


@dataclass
class VideoSegment:
    """视频分段"""
    segment_id: str
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    duration_sec: float = 0.0
    key_frames: List[VideoFrame] = field(default_factory=list)
    scene_score: float = 0.0
    avg_quality: float = 0.0
    phash_signature: str = ""


@dataclass
class VideoPipelineResult:
    """视频管线处理结果"""
    video_path: str
    video_info: Optional[VideoInfo] = None
    segments: List[VideoSegment] = field(default_factory=list)
    key_frames: List[VideoFrame] = field(default_factory=list)
    duplicates_removed: int = 0
    quality_filtered: int = 0
    total_frames_processed: int = 0
    status: str = "pending"  # pending / processing / completed / failed
    error: str = ""
    duration_sec: float = 0.0
    output_dir: str = ""


# ============================================================================
# 核心管线
# ============================================================================

class VideoPipeline:
    """
    视频数据生产管线

    处理流程:
    1. 获取视频信息 (probe)
    2. 帧提取 (ffmpeg/opencv)
    3. 场景检测 -> 分段
    4. 关键帧提取
    5. 感知去重 (PerceptualHasher)
    6. 质量过滤 (QualityScore)
    7. 输出结果
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg",
                 ffprobe_path: str = "ffprobe",
                 work_dir: str = "./data/video_pipeline",
                 use_opencv: bool = True):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.use_opencv = CV2_AVAILABLE and use_opencv

    # ========================================================================
    # 视频信息获取
    # ========================================================================

    def probe_video(self, video_path: str) -> Optional[VideoInfo]:
        """使用ffprobe获取视频信息"""
        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.warning(f"ffprobe failed: {result.stderr}")
                return self._probe_fallback(video_path)

            data = json.loads(result.stdout)
            info = VideoInfo(path=video_path)

            # 获取文件大小
            if "format" in data:
                fmt = data["format"]
                info.file_size = int(float(fmt.get("size", 0)))
                info.duration_sec = float(fmt.get("duration", 0))
                info.bitrate = int(float(fmt.get("bit_rate", 0)))

            # 获取视频流信息
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    info.width = int(stream.get("width", 0))
                    info.height = int(stream.get("height", 0))
                    info.codec = stream.get("codec_name", "")
                    # FPS
                    avg_frame_rate = stream.get("avg_frame_rate", "0/1")
                    if "/" in avg_frame_rate:
                        num, den = avg_frame_rate.split("/")
                        try:
                            info.fps = float(num) / max(float(den), 1.0)
                        except (ValueError, ZeroDivisionError):
                            info.fps = 0.0
                    # 总帧数
                    info.total_frames = int(float(stream.get("nb_frames", 0)))
                    break

            # 音频
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    info.has_audio = True
                    break

            # 如果ffprobe没给帧数，估算
            if info.total_frames == 0 and info.fps > 0 and info.duration_sec > 0:
                info.total_frames = int(info.fps * info.duration_sec)

            return info

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"ffprobe error: {e}")
            return self._probe_fallback(video_path)

    def _probe_fallback(self, video_path: str) -> Optional[VideoInfo]:
        """使用OpenCV作为ffprobe的fallback"""
        if not CV2_AVAILABLE:
            return None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None

            info = VideoInfo(path=video_path)
            info.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            info.fps = cap.get(cv2.CAP_PROP_FPS)
            info.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if info.fps > 0:
                info.duration_sec = info.total_frames / info.fps
            info.file_size = os.path.getsize(video_path)
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            if fourcc:
                info.codec = struct.pack('<I', fourcc).decode('utf-8', errors='replace').strip()
            cap.release()
            return info
        except Exception as e:
            logger.error(f"OpenCV fallback probe failed: {e}")
            return None

    # ========================================================================
    # 帧提取
    # ========================================================================

    def extract_frames_ffmpeg(self, video_path: str, output_dir: str,
                               fps: float = 0, max_frames: int = 0,
                               start_time: float = 0, duration: float = 0,
                               quality: int = 85) -> List[str]:
        """
        使用ffmpeg提取视频帧

        Args:
            video_path: 视频路径
            output_dir: 输出目录
            fps: 提取帧率 (0=使用视频原始帧率)
            max_frames: 最大帧数 (0=全部)
            start_time: 开始时间(秒)
            duration: 持续时间(秒)

        Returns:
            提取的图像文件路径列表
        """
        os.makedirs(output_dir, exist_ok=True)
        output_pattern = os.path.join(output_dir, "frame_%06d.jpg")

        cmd = [self.ffmpeg_path, "-i", video_path]

        if start_time > 0:
            cmd.extend(["-ss", str(start_time)])
        if duration > 0:
            cmd.extend(["-t", str(duration)])
        if fps > 0:
            cmd.extend(["-vf", f"fps={fps}"])
        else:
            cmd.extend(["-vf", "fps=30"])

        cmd.extend([
            "-vframes", str(max_frames) if max_frames > 0 else "999999",
            "-q:v", str(min(max(1, 31 - quality // 3), 31)),
            "-y", output_pattern,
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=600)
            if result.returncode != 0:
                logger.warning(f"ffmpeg frame extraction failed: {result.stderr}")
                return []

            # 收集输出文件
            frames = sorted([
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if f.startswith("frame_") and f.endswith(".jpg")
            ])
            logger.info(f"Extracted {len(frames)} frames from {video_path}")
            return frames

        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timed out for {video_path}")
            return []

    def extract_frames_opencv(self, video_path: str,
                               max_frames: int = 0,
                               step: int = 1) -> Iterator[VideoFrame]:
        """
        使用OpenCV逐帧提取（内存中）

        Yields:
            VideoFrame 对象 (不含phash/quality_score)
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available")
            return

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Cannot open video: {video_path}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        frame_idx = 0
        count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % step == 0:
                    max_frames_reached = max_frames > 0 and count >= max_frames
                    if max_frames_reached:
                        break

                    timestamp = frame_idx / max(fps, 0.01) if fps > 0 else 0
                    vf = VideoFrame(
                        frame_index=frame_idx,
                        timestamp_sec=timestamp,
                        image=frame,
                    )
                    yield vf
                    count += 1

                frame_idx += 1
        finally:
            cap.release()

    # ========================================================================
    # 场景检测
    # ========================================================================

    def detect_scenes(self, video_path: str,
                       strategy: SceneDetectionStrategy = SceneDetectionStrategy.HISTOGRAM,
                       threshold: float = 0.3,
                       min_segment_frames: int = 5,
                       max_frames: int = 0,
                       sample_step: int = 1) -> List[VideoSegment]:
        """
        场景检测 - 将视频分段

        Args:
            video_path: 视频路径
            strategy: 检测策略
            threshold: 检测阈值 (越低越敏感)
            min_segment_frames: 最小分段帧数
            max_frames: 最大处理帧数
            sample_step: 采样步长

        Returns:
            分段列表
        """
        if strategy == SceneDetectionStrategy.FFMPEG:
            return self._detect_scenes_ffmpeg(video_path, threshold, min_segment_frames)
        elif strategy == SceneDetectionStrategy.FIXED_INTERVAL:
            return self._detect_scenes_fixed(video_path, min_segment_frames)
        else:
            return self._detect_scenes_content(video_path, threshold,
                                                min_segment_frames, max_frames, sample_step)

    def _detect_scenes_content(self, video_path: str, threshold: float,
                                min_frames: int, max_frames: int, step: int) -> List[VideoSegment]:
        """
        基于内容的场景检测（直方图差异 + 感知哈希）
        """
        segments = []
        current_frames: List[VideoFrame] = []
        scene_boundaries = [0]
        prev_hist = None
        frame_idx = 0

        for vf in self.extract_frames_opencv(video_path, max_frames, step):
            if vf.image is None:
                continue

            # 计算直方图
            try:
                gray = cv2.cvtColor(vf.image, cv2.COLOR_BGR2GRAY)
                hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()
            except Exception:
                hist = None

            if prev_hist is not None and hist is not None:
                # 直方图差异
                diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CHISQR)
                # 归一化差异
                normalized_diff = min(diff / 100.0, 1.0)

                if normalized_diff > threshold:
                    # 场景边界
                    scene_boundaries.append(frame_idx)

            prev_hist = hist
            current_frames.append(vf)
            frame_idx += 1

        # 最后一个边界
        if current_frames:
            scene_boundaries.append(len(current_frames))

        # 构建分段
        for i in range(len(scene_boundaries) - 1):
            start = scene_boundaries[i]
            end = scene_boundaries[i + 1]

            if end - start < min_frames:
                continue

            segment_frames = current_frames[start:end]
            seg = VideoSegment(
                segment_id=f"seg_{i:04d}",
                start_frame=segment_frames[0].frame_index,
                end_frame=segment_frames[-1].frame_index,
                start_time=segment_frames[0].timestamp_sec,
                end_time=segment_frames[-1].timestamp_sec,
                duration_sec=segment_frames[-1].timestamp_sec - segment_frames[0].timestamp_sec,
                key_frames=[segment_frames[len(segment_frames) // 2]],  # 中间帧作为关键帧
            )

            # 计算场景差异分数
            if len(segment_frames) > 1:
                try:
                    first_gray = cv2.cvtColor(segment_frames[0].image, cv2.COLOR_BGR2GRAY) if segment_frames[0].image is not None else None
                    last_gray = cv2.cvtColor(segment_frames[-1].image, cv2.COLOR_BGR2GRAY) if segment_frames[-1].image is not None else None
                    if first_gray is not None and last_gray is not None:
                        hist1 = cv2.calcHist([first_gray], [0], None, [64], [0, 256])
                        hist2 = cv2.calcHist([last_gray], [0], None, [64], [0, 256])
                        hist1 = cv2.normalize(hist1, hist1).flatten()
                        hist2 = cv2.normalize(hist2, hist2).flatten()
                        seg.scene_score = min(cv2.compareHist(hist1, hist2, cv2.HISTCMP_CHISQR) / 100.0, 1.0)
                except Exception:
                    pass

            segments.append(seg)

        logger.info(f"Scene detection (histogram): {len(segments)} segments from {len(current_frames)} frames")
        return segments

    def _detect_scenes_ffmpeg(self, video_path: str, threshold: float,
                               min_frames: int) -> List[VideoSegment]:
        """使用ffmpeg的场景检测"""
        segments = []
        try:
            cmd = [
                self.ffmpeg_path, "-i", video_path,
                "-vf", f"select='gt(scene,{threshold})',showinfo",
                "-vsync", "vfr",
                "-f", "null", "-",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=300)
            # 解析showinfo输出
            scene_times = set()
            for line in result.stderr.split("\n"):
                if "pts_time:" in line:
                    try:
                        for part in line.split():
                            if part.startswith("pts_time:"):
                                t = float(part.split(":")[1])
                                scene_times.add(t)
                    except (ValueError, IndexError):
                        pass

            if scene_times:
                times = sorted(scene_times)
                for i, t in enumerate(times):
                    start = times[i - 1] if i > 0 else 0
                    seg = VideoSegment(
                        segment_id=f"seg_{i:04d}",
                        start_frame=int(start * 30),  # 估算
                        end_frame=int(t * 30),
                        start_time=start,
                        end_time=t,
                        duration_sec=t - start,
                    )
                    segments.append(seg)

            logger.info(f"ffmpeg scene detection: {len(segments)} segments")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"ffmpeg scene detection failed: {e}")

        return segments

    def _detect_scenes_fixed(self, video_path: str,
                              interval_frames: int = 30) -> List[VideoSegment]:
        """固定间隔分段"""
        segments = []
        info = self.probe_video(video_path)
        if not info or info.total_frames == 0:
            return segments

        for start in range(0, info.total_frames, interval_frames):
            end = min(start + interval_frames, info.total_frames)
            fps = max(info.fps, 0.01)
            seg = VideoSegment(
                segment_id=f"seg_{len(segments):04d}",
                start_frame=start,
                end_frame=end,
                start_time=start / fps,
                end_time=end / fps,
                duration_sec=(end - start) / fps,
            )
            segments.append(seg)

        return segments

    # ========================================================================
    # 关键帧提取
    # ========================================================================

    def extract_keyframes(self, video_path: str,
                           strategy: str = "segment_center",
                           max_keyframes: int = 5,
                           segments: Optional[List[VideoSegment]] = None,
                           use_phash_selection: bool = True) -> List[VideoFrame]:
        """
        提取关键帧

        Args:
            video_path: 视频路径
            strategy: 策略
                - "segment_center": 取每个分段的中间帧
                - "uniform": 均匀采样
                - "quality_best": 质量最高的帧
            max_keyframes: 最大关键帧数
            segments: 分段列表 (配合 segment_center 策略)
            use_phash_selection: 是否用pHash去重选择关键帧

        Returns:
            关键帧列表
        """
        PerceptualHasher, _, _ = _import_quality_engine()

        if strategy == "segment_center" and segments:
            keyframes = []
            for seg in segments:
                if seg.key_frames:
                    keyframes.append(seg.key_frames[0])

            # 用pHash去重
            if use_phash_selection and keyframes:
                unique_frames = []
                seen_hashes = set()
                for kf in keyframes:
                    if kf.image is not None:
                        try:
                            pil_img = Image.fromarray(cv2.cvtColor(kf.image, cv2.COLOR_BGR2RGB))
                            h = PerceptualHasher.phash(pil_img)
                            if h not in seen_hashes:
                                seen_hashes.add(h)
                                kf.phash = h
                                unique_frames.append(kf)
                        except Exception:
                            unique_frames.append(kf)
                    else:
                        unique_frames.append(kf)
                return unique_frames[:max_keyframes]

            return keyframes[:max_keyframes]

        elif strategy == "uniform":
            info = self.probe_video(video_path)
            if not info or info.total_frames == 0:
                return []

            total = info.total_frames
            if max_keyframes > 0:
                step = max(1, total // max_keyframes)
            else:
                step = max(1, total // 10)

            keyframes = []
            count = 0
            for vf in self.extract_frames_opencv(video_path, max_keyframes, step):
                keyframes.append(vf)
                count += 1
                if max_keyframes > 0 and count >= max_keyframes:
                    break

            return keyframes

        return []

    # ========================================================================
    # 感知去重
    # ========================================================================

    def deduplicate_frames(self, frames: List[VideoFrame],
                            threshold: int = 5) -> List[VideoFrame]:
        """
        使用感知哈希对帧进行去重

        Args:
            frames: 帧列表
            threshold: 汉明距离阈值 (越小越严格)

        Returns:
            去重后的帧列表
        """
        PerceptualHasher, _, _ = _import_quality_engine()
        unique_frames = []
        seen_hashes = []

        for f in frames:
            try:
                if f.image is not None:
                    pil_img = Image.fromarray(cv2.cvtColor(f.image, cv2.COLOR_BGR2RGB))
                    h = PerceptualHasher.phash(pil_img)
                    f.phash = h
                else:
                    continue
            except Exception:
                continue

            # 检查是否与已有哈希重复
            is_duplicate = False
            for existing_h in seen_hashes:
                try:
                    dist = PerceptualHasher.hamming_distance(h, existing_h)
                    if dist <= threshold:
                        is_duplicate = True
                        break
                except Exception:
                    pass

            if not is_duplicate:
                seen_hashes.append(h)
                unique_frames.append(f)

        logger.info(f"Frame dedup: {len(frames)} -> {len(unique_frames)} ({len(frames) - len(unique_frames)} removed)")
        return unique_frames

    # ========================================================================
    # 质量过滤
    # ========================================================================

    def filter_by_quality(self, frames: List[VideoFrame],
                           min_quality: float = 0.3) -> List[VideoFrame]:
        """
        根据质量过滤帧

        使用 QualityScore 数据结构计算质量，但使用轻量图像属性评估
        （不依赖AI模型）

        Args:
            frames: 帧列表
            min_quality: 最低质量分数

        Returns:
            过滤后的帧列表
        """
        _, QualityScore, _ = _import_quality_engine()
        filtered = []

        for f in frames:
            if f.image is None:
                continue

            # 使用轻量图像属性评估
            score = self._lightweight_quality(f.image)
            f.quality_score = score.overall_score

            if score.overall_score >= min_quality:
                filtered.append(f)

        logger.info(f"Quality filter: {len(frames)} -> {len(filtered)} (threshold={min_quality})")
        return filtered

    def _lightweight_quality(self, frame: np.ndarray) -> 'QualityScore':
        """
        轻量质量评估 (不使用AI模型)
        """
        _, QualityScore, _ = _import_quality_engine()
        score = QualityScore()

        try:
            h, w = frame.shape[:2]
            score.width = w
            score.height = h
            score.aspect_ratio = round(w / max(h, 1), 4)

            # 灰度
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame

            # 清晰度 (Laplacian方差)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            score.sharpness = min(laplacian_var / 500.0, 1.0)

            # 亮度
            score.brightness = min(float(np.mean(gray)) / 255.0, 1.0)

            # 对比度
            score.contrast = min(float(np.std(gray)) / 127.5, 1.0)

            # 色彩丰富度
            if len(frame.shape) == 3:
                r, g, b = frame[:, :, 0].astype(float), frame[:, :, 1].astype(float), frame[:, :, 2].astype(float)
                rg = np.abs(r - g).mean()
                yb = np.abs(0.5 * (r + g) - b).mean()
                score.colorfulness = min(np.sqrt(rg**2 + yb**2) / 80.0, 1.0)
            else:
                score.colorfulness = 0.0

            # 噪点估计
            try:
                small = cv2.resize(gray, (32, 32))
                smoothed = cv2.GaussianBlur(small, (3, 3), 0)
                score.noise_level = min(float(np.std(small - smoothed)) / 20.0, 1.0)
            except Exception:
                pass

            # 综合评分 (轻量加权)
            components = {
                "sharpness": score.sharpness,
                "brightness": 1.0 - abs(0.5 - score.brightness) * 2,
                "contrast": score.contrast,
                "colorfulness": score.colorfulness,
                "noise": 1.0 - score.noise_level,
            }
            weights = {"sharpness": 0.30, "brightness": 0.15, "contrast": 0.15,
                       "colorfulness": 0.20, "noise": 0.20}
            weighted = sum(components[k] * weights[k] for k in weights)
            total_w = sum(weights.values())
            score.overall_score = round(weighted / max(total_w, 0.01), 4)

        except Exception as e:
            logger.warning(f"Lightweight quality assessment failed: {e}")

        return score

    # ========================================================================
    # 分段质量过滤器
    # ========================================================================

    def filter_segments_by_quality(self, segments: List[VideoSegment],
                                    min_quality: float = 0.3) -> List[VideoSegment]:
        """
        按质量过滤分段
        """
        filtered = []
        for seg in segments:
            if seg.key_frames:
                avg_q = sum(kf.quality_score for kf in seg.key_frames) / len(seg.key_frames)
                seg.avg_quality = avg_q
                if avg_q >= min_quality:
                    filtered.append(seg)
            else:
                filtered.append(seg)

        return filtered

    # ========================================================================
    # 完整管线
    # ========================================================================

    def run_pipeline(self, video_path: str,
                     output_dir: str = "",
                     extract_frames: bool = True,
                     detect_scenes: bool = True,
                     scene_threshold: float = 0.3,
                     deduplicate: bool = True,
                     quality_filter: bool = True,
                     min_quality: float = 0.3,
                     max_keyframes: int = 5,
                     max_frames: int = 0) -> VideoPipelineResult:
        """
        运行完整视频处理管线

        Args:
            video_path: 视频路径
            output_dir: 输出目录
            extract_frames: 是否提取帧
            detect_scenes: 是否检测场景
            scene_threshold: 场景检测阈值
            deduplicate: 是否去重
            quality_filter: 是否质量过滤
            min_quality: 最低质量
            max_keyframes: 最大关键帧数
            max_frames: 最大处理帧数

        Returns:
            VideoPipelineResult
        """
        result = VideoPipelineResult(video_path=video_path)

        if not os.path.exists(video_path):
            result.status = "failed"
            result.error = f"Video file not found: {video_path}"
            return result

        result.status = "processing"

        # 1. 获取视频信息
        video_info = self.probe_video(video_path)
        result.video_info = video_info
        if video_info:
            result.duration_sec = video_info.duration_sec

        logger.info(f"Processing video: {video_path} ({video_info})")

        # 2. 输出目录
        if not output_dir:
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            output_dir = str(self.work_dir / video_name)
        result.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 3. 帧提取
        all_frames: List[VideoFrame] = []
        if extract_frames:
            frame_dir = os.path.join(output_dir, "frames")
            os.makedirs(frame_dir, exist_ok=True)

            # 用OpenCV提取内存帧
            try:
                for vf in self.extract_frames_opencv(video_path, max_frames, step=1):
                    all_frames.append(vf)
                    # 保存到磁盘
                    if vf.image is not None:
                        frame_path = os.path.join(frame_dir, f"frame_{vf.frame_index:06d}.jpg")
                        cv2.imwrite(frame_path, vf.image)
            except Exception as e:
                logger.warning(f"OpenCV frame extraction failed, trying ffmpeg: {e}")
                # fallback: 用ffmpeg
                ff_frames = self.extract_frames_ffmpeg(video_path, frame_dir)
                for i, fp in enumerate(ff_frames):
                    img = cv2.imread(fp)
                    all_frames.append(VideoFrame(frame_index=i, timestamp_sec=i / 30.0, image=img))

        result.total_frames_processed = len(all_frames)
        logger.info(f"Extracted {len(all_frames)} frames")

        # 4. 场景检测 -> 分段
        if detect_scenes and all_frames:
            segments = self.detect_scenes(
                video_path,
                strategy=SceneDetectionStrategy.HISTOGRAM,
                threshold=scene_threshold,
                max_frames=max_frames,
            )
            result.segments = segments

            # 更新分段的关键帧
            for seg in segments:
                mid_idx = len(all_frames) // 2 if len(all_frames) > 1 else 0
                if mid_idx < len(all_frames):
                    seg.key_frames = [all_frames[mid_idx]]
        elif all_frames:
            # 不分段，所有帧作为一个整体
            seg = VideoSegment(
                segment_id=f"seg_0000",
                start_frame=0,
                end_frame=len(all_frames) - 1,
                start_time=0,
                end_time=len(all_frames) / max(video_info.fps if video_info else 30, 0.01),
            )
            seg.key_frames = all_frames[:max_keyframes] if max_keyframes > 0 else all_frames
            result.segments = [seg]

        # 5. 感知去重
        if deduplicate and all_frames:
            before_dedup = len(all_frames)
            all_frames = self.deduplicate_frames(all_frames)
            result.duplicates_removed = before_dedup - len(all_frames)

        # 6. 质量过滤
        if quality_filter and all_frames:
            before_filter = len(all_frames)
            all_frames = self.filter_by_quality(all_frames, min_quality)
            result.quality_filtered = before_filter - len(all_frames)

        # 7. 提取关键帧
        result.key_frames = self.extract_keyframes(
            video_path,
            strategy="segment_center",
            max_keyframes=max_keyframes,
            segments=result.segments,
            use_phash_selection=True,
        )

        # 8. 保存关键帧
        kf_dir = os.path.join(output_dir, "keyframes")
        os.makedirs(kf_dir, exist_ok=True)
        for i, kf in enumerate(result.key_frames):
            if kf.image is not None:
                kf_path = os.path.join(kf_dir, f"keyframe_{i:04d}.jpg")
                cv2.imwrite(kf_path, kf.image)

        result.status = "completed"
        logger.info(f"Pipeline completed for {video_path}")
        return result

    # ========================================================================
    # 批量处理
    # ========================================================================

    def batch_process(self, video_paths: List[str],
                       output_base_dir: str = "",
                       parallel: bool = False,
                       max_workers: int = 2,
                       **pipeline_kwargs) -> List[VideoPipelineResult]:
        """
        批量处理多个视频

        Args:
            video_paths: 视频路径列表
            output_base_dir: 输出基目录
            parallel: 是否并行处理
            max_workers: 并行数
            pipeline_kwargs: 传递给run_pipeline的参数

        Returns:
            处理结果列表
        """
        results = []

        if parallel:
            try:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    for vp in video_paths:
                        out_dir = ""
                        if output_base_dir:
                            vname = os.path.splitext(os.path.basename(vp))[0]
                            out_dir = os.path.join(output_base_dir, vname)
                        future = executor.submit(self.run_pipeline, vp,
                                                  output_dir=out_dir, **pipeline_kwargs)
                        futures[future] = vp

                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            vp = futures[future]
                            err_result = VideoPipelineResult(
                                video_path=vp,
                                status="failed",
                                error=str(e),
                            )
                            results.append(err_result)
            except ImportError:
                logger.warning("concurrent.futures not available, falling back to sequential")
                parallel = False

        if not parallel:
            for vp in video_paths:
                out_dir = ""
                if output_base_dir:
                    vname = os.path.splitext(os.path.basename(vp))[0]
                    out_dir = os.path.join(output_base_dir, vname)
                try:
                    result = self.run_pipeline(vp, output_dir=out_dir, **pipeline_kwargs)
                    results.append(result)
                except Exception as e:
                    err_result = VideoPipelineResult(
                        video_path=vp,
                        status="failed",
                        error=str(e),
                    )
                    results.append(err_result)

        return results


    # ========================================================================
    # Open-Sora / Panda-70M JSONL 导出
    # ========================================================================

    def export_open_sora_jsonl(self, video_path: str, caption: str = "",
                                output_path: str = "") -> Dict:
        """
        导出Open-Sora标准JSONL格式

        Open-Sora格式:
        {
          "path": "/data/videos/001.mp4",
          "caption": "...",
          "num_frames": 64,
          "fps": 24,
          "width": 1920,
          "height": 1080,
          "aspect_ratio": 1.778,
          "resolution": 1080,
          "duration": 2.67,
          "text_len": 35,
          "aesthetic_score": 6.2,
          "flow_score": 0.85,
          "dover_score": 0.78,
          "motion_score": 0.92,
          "nsfw_score": 0.001
        }

        Args:
            video_path: 视频路径
            caption: 文本描述
            output_path: JSONL输出路径 (可选, 如果提供则写入文件)

        Returns:
            评分结果字典
        """
        try:
            from data_video_quality import VideoQualityAssessor
            assessor = VideoQualityAssessor()
            result = assessor.to_opensora_jsonl(video_path, caption)
        except ImportError:
            # fallback: 只输出基本信息
            info = self.probe_video(video_path)
            result = {
                "path": video_path,
                "caption": caption,
                "num_frames": info.total_frames if info else 0,
                "fps": info.fps if info else 0,
                "width": info.width if info else 0,
                "height": info.height if info else 0,
                "aspect_ratio": round(info.width / max(info.height, 1), 4) if info else 0,
                "resolution": min(info.width, info.height) if info else 0,
                "duration": info.duration_sec if info else 0,
                "text_len": len(caption) if caption else 0,
                "aesthetic_score": 0.0,
                "flow_score": 0.0,
                "dover_score": 0.0,
                "motion_score": 0.0,
                "nsfw_score": 0.0,
            }

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "a") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            logger.info(f"Open-Sora JSONL appended to {output_path}")

        return result

    def export_panda_70m_jsonl(self, video_path: str, caption: str = "",
                                output_path: str = "") -> Dict:
        """
        导出Panda-70M标准JSONL格式

        Panda-70M格式:
        {
          "video": "/path/to/video.mp4",
          "caption": "...",
          "duration": 10.0,
          "resolution": [1920, 1080],
          "fps": 30,
          "num_frames": 300,
          "aesthetic": 0.65,
          "motion": 0.8,
          "dover": 0.75,
          "nsfw": 0.001
        }

        Args:
            video_path: 视频路径
            caption: 文本描述
            output_path: JSONL输出路径 (可选)

        Returns:
            评分结果字典
        """
        try:
            from data_video_quality import VideoQualityAssessor
            assessor = VideoQualityAssessor()
            result = assessor.to_panda70m_jsonl(video_path, caption)
        except ImportError:
            info = self.probe_video(video_path)
            result = {
                "video": video_path,
                "caption": caption,
                "duration": info.duration_sec if info else 0,
                "resolution": [info.width if info else 0, info.height if info else 0],
                "fps": info.fps if info else 0,
                "num_frames": info.total_frames if info else 0,
                "aesthetic": 0.0,
                "motion": 0.0,
                "dover": 0.0,
                "nsfw": 0.0,
            }

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "a") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            logger.info(f"Panda-70M JSONL appended to {output_path}")

        return result

    # ========================================================================
    # 批量JSONL导出
    # ========================================================================

    def batch_export_open_sora_jsonl(self, video_paths: List[str],
                                      captions: Optional[List[str]] = None,
                                      output_path: str = "",
                                      parallel: bool = False) -> List[Dict]:
        """批量导出Open-Sora JSONL"""
        if captions is None:
            captions = [""] * len(video_paths)
        results = []
        for vp, cap in zip(video_paths, captions):
            r = self.export_open_sora_jsonl(vp, cap, output_path)
            results.append(r)
        return results

    def batch_export_panda_70m_jsonl(self, video_paths: List[str],
                                      captions: Optional[List[str]] = None,
                                      output_path: str = "",
                                      parallel: bool = False) -> List[Dict]:
        """批量导出Panda-70M JSONL"""
        if captions is None:
            captions = [""] * len(video_paths)
        results = []
        for vp, cap in zip(video_paths, captions):
            r = self.export_panda_70m_jsonl(vp, cap, output_path)
            results.append(r)
        return results


# ============================================================================
# 简便入口
# ============================================================================

def get_video_pipeline(**kwargs) -> VideoPipeline:
    return VideoPipeline(**kwargs)
