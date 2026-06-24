"""
NanoBot Factory - 视频Caption+帧描述管线
Video Caption & Frame Description Pipeline

功能:
- 帧提取+逐帧描述 (复用 data_video_pipeline.py 的视频帧提取)
- 全局叙事描述 (Video-LLaVA风格)
- 逐场景描述
- 保存为Open-Sora标准格式
"""

import os, json, logging, subprocess, tempfile, shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import OrderedDict
from PIL import Image
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
class CaptionedFrame:
    """带描述的帧"""
    frame_index: int
    timestamp_sec: float
    image_path: str = ""
    caption: str = ""
    caption_short: str = ""
    scene_id: str = ""
    quality_score: float = 0.0


@dataclass
class VideoCaptionResult:
    """视频Caption结果"""
    video_path: str
    video_name: str = ""
    duration_sec: float = 0.0
    fps: float = 0.0
    total_frames: int = 0
    narrative_caption: str = ""    # 全局叙事描述
    segment_captions: List[Dict] = field(default_factory=list)  # 逐场景描述
    frame_captions: List[CaptionedFrame] = field(default_factory=list)  # 逐帧描述
    num_frames: int = 0
    output_dir: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Video Caption Generator
# ============================================================================

class VideoCaptionGenerator:
    """
    视频Caption生成器

    基于图像属性分析生成视频描述。不需要VLM模型，全部本地算法。

    Video-LLaVA风格:
    - 全局叙事: 对整个视频的情节/内容概括描述
    - 逐段描述: 每个场景的详细描述
    - 支持Open-Sora标准格式保存
    """

    def __init__(self, work_dir: str = "./data/video_caption"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _import_video_pipeline(self):
        """延迟导入VideoPipeline"""
        from data_video_pipeline import VideoPipeline, VideoInfo, SceneDetectionStrategy
        return VideoPipeline, VideoInfo, SceneDetectionStrategy

    def _import_dense_caption(self):
        """延迟导入DenseCaptionGenerator"""
        from data_dense_caption import DenseCaptionGenerator
        return DenseCaptionGenerator

    def _analyze_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        分析单帧的属性
        Returns:
            dict with scene_type, brightness, dominant_color, motion_level
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 亮度
        brightness = float(np.mean(gray)) / 255.0

        # 对比度
        contrast = float(np.std(gray)) / 127.5

        # 清晰度
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness = min(lap_var / 500.0, 1.0)

        # 主色调
        avg_color = np.mean(frame.reshape(-1, 3), axis=0)
        colors = {
            "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
            "yellow": (255, 255, 0), "orange": (255, 165, 0), "purple": (128, 0, 128),
            "gray": (128, 128, 128), "white": (255, 255, 255), "black": (0, 0, 0),
        }
        dominant_color = "unknown"
        min_dist = float("inf")
        for name, rgb in colors.items():
            dist = np.sqrt((avg_color[0] - rgb[2])**2 +
                           (avg_color[1] - rgb[1])**2 +
                           (avg_color[2] - rgb[0])**2)
            if dist < min_dist:
                min_dist = dist
                dominant_color = name

        # 场景类型
        face_count = 0
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if os.path.exists(cascade_path):
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            face_count = len(faces)

        if face_count > 0:
            scene_type = "portrait"
        elif brightness < 0.25:
            scene_type = "night"
        elif brightness > 0.6 and contrast > 0.5:
            scene_type = "outdoor"
        else:
            scene_type = "indoor"

        return {
            "brightness": brightness,
            "contrast": contrast,
            "sharpness": sharpness,
            "dominant_color": dominant_color,
            "scene_type": scene_type,
            "face_count": face_count,
        }

    # ========================================================================
    # 帧提取+逐帧描述
    # ========================================================================

    def extract_captioned_frames(
        self,
        video_path: str,
        interval: int = 30,
        max_frames: int = 0,
        output_dir: str = ""
    ) -> List[CaptionedFrame]:
        """
        帧提取 + 逐帧描述

        提取视频指定间隔的帧，并为每帧生成描述。

        Args:
            video_path: 视频路径
            interval: 帧间隔 (每N帧取1帧)
            max_frames: 最大帧数 (0=不限制)
            output_dir: 输出目录 (空=不保存)

        Returns:
            CaptionedFrame列表
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available")
            return []

        if not os.path.exists(video_path):
            logger.error(f"Video not found: {video_path}")
            return []

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Cannot open video: {video_path}")
            return []

        fps = max(cap.get(cv2.CAP_PROP_FPS), 0.01)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # 准备DenseCaptionGenerator
        DenseCaptionGenerator = self._import_dense_caption()
        caption_gen = DenseCaptionGenerator()

        captioned_frames = []
        frame_idx = 0
        saved_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % interval == 0:
                    if max_frames > 0 and saved_count >= max_frames:
                        break

                    timestamp = frame_idx / fps
                    analysis = self._analyze_frame(frame)

                    # 生成描述
                    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    full_caption = caption_gen.generate_full_caption(pil_img)
                    short_caption = caption_gen.generate_short_caption(pil_img)

                    cf = CaptionedFrame(
                        frame_index=frame_idx,
                        timestamp_sec=timestamp,
                        caption=full_caption,
                        caption_short=short_caption,
                        quality_score=analysis.get("sharpness", 0.5),
                    )

                    # 保存帧图像
                    if output_dir:
                        frame_path = os.path.join(
                            output_dir, f"frame_{frame_idx:06d}.jpg"
                        )
                        cv2.imwrite(frame_path, frame)
                        cf.image_path = frame_path

                    captioned_frames.append(cf)
                    saved_count += 1

                frame_idx += 1

        finally:
            cap.release()

        logger.info(f"Extracted {len(captioned_frames)} captioned frames from {video_path}")
        return captioned_frames

    # ========================================================================
    # 全局叙事描述 (Video-LLaVA风格)
    # ========================================================================

    def generate_narrative_caption(self, video_path: str) -> str:
        """
        全局叙事描述 (Video-LLaVA风格)

        对整个视频的内容进行叙事性概括描述。
        基于视频的关键帧序列分析，生成连贯的叙事文本。

        Video-LLaVA风格: "The video shows... First, ... Then, ... Finally, ..."
        """
        if not CV2_AVAILABLE:
            return "Video analysis requires OpenCV (cv2)."

        if not os.path.exists(video_path):
            return f"Video file not found: {video_path}"

        # 提取关键帧 (30帧间隔, 最多取30帧)
        frames = self.extract_captioned_frames(video_path, interval=30, max_frames=30)
        if not frames:
            return "Unable to extract frames from this video."

        # 分析关键帧的变化模式
        scene_types = []
        brightnesses = []
        face_counts = []

        cap = cv2.VideoCapture(video_path)
        fps = max(cap.get(cv2.CAP_PROP_FPS), 0.01)
        duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
        cap.release()

        # 分析前中后段
        mid_point = len(frames) // 2
        first_half = frames[:mid_point] if mid_point > 0 else frames
        second_half = frames[mid_point:] if mid_point > 0 else frames

        # 读取代表性帧进行分析
        representative_frames = []
        cap = cv2.VideoCapture(video_path)
        for cf in [frames[0], frames[len(frames)//2], frames[-1]]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, cf.frame_index)
            ret, frame = cap.read()
            if ret:
                representative_frames.append(self._analyze_frame(frame))
        cap.release()

        # 构建叙事
        parts = []

        # 开头
        if len(frames) <= 2:
            parts.append(f"This is a short video clip lasting about {duration:.1f} seconds.")
        else:
            parts.append(f"This video spans approximately {duration:.1f} seconds.")

        # 分析第一个代表帧
        if representative_frames:
            r0 = representative_frames[0]
            scene_desc = r0.get("scene_type", "unknown")
            color = r0.get("dominant_color", "neutral")
            parts.append(f"It begins with a {scene_desc} scene dominated by {color} tones.")

        # 中间变化
        if len(frames) > 5:
            # 检测场景变化
            changes = 0
            prev_type = representative_frames[0].get("scene_type", "") if representative_frames else ""
            for rf in representative_frames[1:]:
                curr_type = rf.get("scene_type", "")
                if curr_type != prev_type:
                    changes += 1
                prev_type = curr_type

            if changes > 0:
                parts.append(f"The content transitions between different scenes {changes} time{'s' if changes != 1 else ''}.")
            else:
                parts.append(f"The visual style remains relatively consistent throughout.")

        # 人脸信息
        total_faces = sum(rf.get("face_count", 0) for rf in representative_frames)
        if total_faces > 0:
            parts.append(f"People appear in the video, adding a human element to the scene.")
        else:
            parts.append(f"The video primarily captures environmental or object-focused content.")

        # 结尾
        if representative_frames and len(representative_frames) >= 3:
            r_last = representative_frames[-1]
            last_brightness = r_last.get("brightness", 0.5)
            if last_brightness < 0.3:
                parts.append("The video concludes in a darker setting.")
            elif last_brightness > 0.7:
                parts.append("The video ends in a well-lit scene.")
            else:
                parts.append("The lighting remains moderate towards the end.")

        parts.append("Overall, this is a coherent video sequence with natural visual flow.")

        return " ".join(parts)

    # ========================================================================
    # 逐场景描述
    # ========================================================================

    def generate_segment_captions(self, video_path: str) -> List[Dict]:
        """
        逐场景描述

        基于场景检测的结果，对每个场景生成描述。

        Returns:
            [{"segment_id": str, "start_time": float, "end_time": float,
              "duration": float, "caption": str, "keyframe_caption": str}, ...]
        """
        if not CV2_AVAILABLE:
            return []

        VideoPipeline, VideoInfo, SceneDetectionStrategy = self._import_video_pipeline()
        DenseCaptionGenerator = self._import_dense_caption()

        pipeline = VideoPipeline()
        caption_gen = DenseCaptionGenerator()

        # 场景检测
        segments = pipeline.detect_scenes(
            video_path,
            strategy=SceneDetectionStrategy.HISTOGRAM,
            threshold=0.3,
            min_segment_frames=10,
        )

        if not segments:
            # 如果没有检测到场景，把整个视频作为一个场景
            info = pipeline.probe_video(video_path)
            duration = info.duration_sec if info else 0
            segments = [type("Segment", (), {
                "segment_id": "seg_0000",
                "start_time": 0,
                "end_time": duration,
                "duration_sec": duration,
            })()]

        segment_captions = []

        for seg in segments:
            # 提取该段中间帧
            mid_time = (seg.start_time + seg.end_time) / 2
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_MSEC, mid_time * 1000)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                continue

            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            analysis = self._analyze_frame(frame)

            # 生成场景描述
            scene_type = analysis.get("scene_type", "unknown")
            color = analysis.get("dominant_color", "neutral")
            brightness = analysis.get("brightness", 0.5)

            duration_str = f"{seg.duration_sec:.1f}s" if hasattr(seg, "duration_sec") else "unknown"

            # 场景级描述
            face_count = analysis.get("face_count", 0)
            if face_count > 0:
                subject_desc = " featuring people"
            else:
                subject_desc = ""

            caption = (
                f"A {scene_type} scene lasting {duration_str}{subject_desc}. "
                f"The color palette features {color} tones "
                f"with {'bright' if brightness > 0.6 else 'moderate' if brightness > 0.3 else 'dim'} lighting."
            )

            # 关键帧描述
            keyframe_caption = caption_gen.generate_full_caption(pil_img)

            segment_captions.append({
                "segment_id": getattr(seg, "segment_id", "unknown"),
                "start_time": round(seg.start_time, 2),
                "end_time": round(seg.end_time, 2),
                "duration": round(getattr(seg, "duration_sec", 0), 2),
                "caption": caption,
                "keyframe_caption": keyframe_caption,
                "scene_type": scene_type,
                "dominant_color": color,
            })

        logger.info(f"Generated {len(segment_captions)} segment captions for {video_path}")
        return segment_captions

    # ========================================================================
    # 保存为Open-Sora标准格式
    # ========================================================================

    def save_open_sora_format(
        self,
        video_path: str,
        output_dir: str = "",
        generate_captions: bool = True,
    ) -> str:
        """
        保存为Open-Sora标准格式

        Open-Sora格式:
        output_dir/
            videos/
                video_name/
                    frame_000000.jpg
                    frame_000001.jpg
                    ...
            captions.jsonl
                {"path": "videos/video_name", "caption": "narrative caption",
                 "frames": ["frame_000000.jpg", ...], "fps": 24}

        Args:
            video_path: 视频路径
            output_dir: 输出目录
            generate_captions: 是否生成描述

        Returns:
            输出目录路径
        """
        if not output_dir:
            output_dir = str(self.work_dir / "open_sora_format")

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        video_out_dir = os.path.join(output_dir, "videos", video_name)
        os.makedirs(video_out_dir, exist_ok=True)

        # 提取帧 (1fps 或 keyframes)
        frames_dir = os.path.join(video_out_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        # 使用VideoPipeline提取帧
        VideoPipeline, _, _ = self._import_video_pipeline()
        pipeline = VideoPipeline()

        # 提取视频信息
        info = pipeline.probe_video(video_path)
        fps = info.fps if info else 24.0
        duration = info.duration_sec if info else 0.0

        # 提取帧 (uniform 1fps)
        cap = cv2.VideoCapture(video_path)
        vid_fps = max(cap.get(cv2.CAP_PROP_FPS), 0.01)
        frame_list = []

        frame_idx = 0
        saved = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 1fps采样
            if frame_idx % max(1, int(round(vid_fps))) == 0:
                frame_name = f"frame_{saved:06d}.jpg"
                frame_path = os.path.join(frames_dir, frame_name)
                cv2.imwrite(frame_path, frame)
                frame_list.append(frame_name)
                saved += 1

            frame_idx += 1
        cap.release()

        # 生成描述
        narrative = ""
        segment_captions_list = []

        if generate_captions:
            narrative = self.generate_narrative_caption(video_path)
            segment_captions_list = self.generate_segment_captions(video_path)

        # 写入captions.jsonl
        jsonl_path = os.path.join(output_dir, "captions.jsonl")
        entry = {
            "path": f"videos/{video_name}",
            "caption": narrative,
            "frames": frame_list,
            "fps": int(round(fps)) if fps > 0 else 24,
            "duration": round(duration, 2),
            "total_frames": len(frame_list),
            "segments": segment_captions_list,
        }

        with open(jsonl_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 写入帧级描述
        if generate_captions:
            frames_jsonl = os.path.join(output_dir, "frame_captions.jsonl")
            DenseCaptionGenerator = self._import_dense_caption()
            cap_gen = DenseCaptionGenerator()

            with open(frames_jsonl, "a") as f:
                for i, frame_name in enumerate(frame_list):
                    frame_path = os.path.join(frames_dir, frame_name)
                    if os.path.exists(frame_path):
                        try:
                            pil_img = Image.open(frame_path).convert("RGB")
                            short_cap = cap_gen.generate_short_caption(pil_img)
                            full_cap = cap_gen.generate_full_caption(pil_img)
                            frame_entry = {
                                "path": f"videos/{video_name}/frames/{frame_name}",
                                "short_caption": short_cap,
                                "full_caption": full_cap,
                                "frame_index": i,
                            }
                            f.write(json.dumps(frame_entry, ensure_ascii=False) + "\n")
                        except Exception:
                            pass

        logger.info(f"Open-Sora format saved to {output_dir}")
        return output_dir

    # ========================================================================
    # 完整管线
    # ========================================================================

    def run_pipeline(
        self,
        video_path: str,
        output_dir: str = "",
        extract_interval: int = 30,
        save_open_sora: bool = True,
    ) -> VideoCaptionResult:
        """
        完整视频Caption管线

        Args:
            video_path: 视频路径
            output_dir: 输出目录
            extract_interval: 帧提取间隔
            save_open_sora: 是否保存为Open-Sora格式

        Returns:
            VideoCaptionResult
        """
        if not os.path.exists(video_path):
            return VideoCaptionResult(video_path=video_path)

        if not output_dir:
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            output_dir = str(self.work_dir / video_name)

        os.makedirs(output_dir, exist_ok=True)

        result = VideoCaptionResult(
            video_path=video_path,
            video_name=os.path.basename(video_path),
        )

        # 视频信息
        VideoPipeline, VideoInfo, _ = self._import_video_pipeline()
        pipeline = VideoPipeline()
        info = pipeline.probe_video(video_path)
        if info:
            result.duration_sec = info.duration_sec
            result.fps = info.fps
            result.total_frames = info.total_frames

        # 1. 提取帧+逐帧描述
        frames_dir = os.path.join(output_dir, "captioned_frames")
        captioned_frames = self.extract_captioned_frames(
            video_path, interval=extract_interval, output_dir=frames_dir
        )
        result.frame_captions = captioned_frames
        result.num_frames = len(captioned_frames)

        # 2. 生成全局叙事描述
        narrative = self.generate_narrative_caption(video_path)
        result.narrative_caption = narrative

        # 3. 生成逐场景描述
        segment_captions = self.generate_segment_captions(video_path)
        result.segment_captions = segment_captions

        # 4. 保存为Open-Sora格式
        if save_open_sora:
            open_sora_dir = os.path.join(output_dir, "open_sora")
            self.save_open_sora_format(video_path, output_dir=open_sora_dir)
            result.output_dir = open_sora_dir

        # 保存结果JSON
        result_path = os.path.join(output_dir, "video_caption_result.json")
        with open(result_path, "w") as f:
            # 手工序列化
            d = asdict(result)
            # 处理CaptionedFrame对象
            d["frame_captions"] = [
                {
                    "frame_index": cf.frame_index,
                    "timestamp_sec": cf.timestamp_sec,
                    "image_path": cf.image_path,
                    "caption": cf.caption[:200] if cf.caption else "",
                    "caption_short": cf.caption_short,
                    "scene_id": cf.scene_id,
                    "quality_score": cf.quality_score,
                }
                for cf in captioned_frames
            ]
            json.dump(d, f, indent=2, ensure_ascii=False)

        logger.info(f"Video caption pipeline completed: {result_path}")
        return result


# ============================================================================
# Convenience
# ============================================================================

def get_video_caption_generator(work_dir: str = "./data/video_caption") -> VideoCaptionGenerator:
    """获取视频Caption生成器"""
    return VideoCaptionGenerator(work_dir=work_dir)
