"""
NanoBot Factory — 行业标准视频质量管线
Industry-Standard Video Quality Pipeline

对齐 Open-Sora / Panda-70M 标准。

评分维度:
- DOVER score (无参考视频质量): 基于帧差/模糊/噪声
- Motion score (运动评分): 光流估计 + 帧差法
- Flow score (光流一致性): 光流幅值分布
- Aesthetic score (美学): 逐帧aesthetic平均
- NSFW score: 逐帧NSFW检测取最大值
- CLIP score (视频-文本匹配): 关键帧CLIP Score平均

Open-Sora JSONL 标准输出格式:
{
  "path": "/data/videos/001.mp4",
  "caption": "A runner sprinting on a track",
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
"""

import os, sys, io, json, logging, math, struct, tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
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
# 工具函数
# ============================================================================

def _ensure_rgb(frame: np.ndarray) -> np.ndarray:
    """确保帧为RGB格式 (OpenCV BGR -> RGB)"""
    if frame is None:
        return None
    if len(frame.shape) >= 3 and frame.shape[2] >= 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)


def _frame_iterator_opencv(video_path: str, max_frames: int = 0,
                           step: int = 1, yield_gray: bool = False):
    """OpenCV帧迭代器。yields (frame_index, timestamp, bgr_frame, gray_frame)"""
    if not CV2_AVAILABLE:
        logger.error("OpenCV not available for frame iteration")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    frame_idx = 0
    count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step == 0:
                if max_frames > 0 and count >= max_frames:
                    break
                timestamp = frame_idx / fps
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if yield_gray else None
                yield (frame_idx, timestamp, frame, gray)
                count += 1
            frame_idx += 1
    finally:
        cap.release()


def _load_sentence_transformer():
    """加载 sentence-transformers (带缓存 + 离线模式)"""
    try:
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_OFFLINE'] = '1'
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(
            'paraphrase-multilingual-MiniLM-L12-v2',
            local_files_only=True,
            device='cpu'
        )
        return model
    except Exception as e:
        logger.warning(f"sentence-transformers not available: {e}")
        return None


# ============================================================================
# VideoQualityAssessor
# ============================================================================

class VideoQualityAssessor:
    """
    视频质量评估 — 对齐Open-Sora/Panda-70M标准

    评分维度:
    - DOVER score (无参考视频质量): 基于帧差/模糊/噪声
    - Motion score (运动评分): 光流估计 + 帧差法
    - Flow score (光流一致性): 光流幅值分布
    - Aesthetic score (美学): 逐帧aesthetic平均
    - NSFW score: 逐帧NSFW检测取最大值
    - CLIP score (视频-文本匹配): 关键帧CLIP Score平均
    """

    # Open-Sora / Panda-70M 质量阈值
    DOVER_THRESHOLD = 0.65
    MIN_RESOLUTION = 720       # 720p
    MIN_DURATION = 2.0         # 2秒
    MIN_MOTION = 0.1
    MAX_NSFW = 0.5
    MIN_AESTHETIC = 4.5

    def __init__(self):
        self._st_model = None
        self._st_loaded = False
        self._try_load_st()
        self._nsfw_classifier = None

    def _try_load_st(self):
        self._st_model = _load_sentence_transformer()
        self._st_loaded = self._st_model is not None

    def _get_nsfw_classifier(self):
        """懒加载NSFW分类器"""
        if self._nsfw_classifier is None:
            try:
                from data_nsfw_classifier import NSFWClassifier
                self._nsfw_classifier = NSFWClassifier()
            except ImportError:
                logger.warning("NSFWClassifier not available, using fallback")
                self._nsfw_classifier = None
        return self._nsfw_classifier

    # ========================================================================
    # DOVER Score — 无参考视频质量
    # ========================================================================

    def dover_score(self, video_path: str, num_frames: int = 15) -> float:
        """
        DOVER无参考视频质量 (0-1)

        算法:
        1. 提取num_f帧关键帧 (均匀采样)
        2. 每帧计算:
           - 模糊度(Laplacian方差)
           - 噪声(高斯差)
           - 块效应(边界差异)
           - 亮度
        3. 综合 = 模糊度归一化 * 0.35 + 噪声归一化 * 0.25 + 块效应 * 0.20 + 亮度 * 0.10 + 对比度 * 0.10
        """
        if not CV2_AVAILABLE:
            return 0.5

        frames_bgr = []
        for idx, ts, bgr, _ in _frame_iterator_opencv(video_path, max_frames=num_frames,
                                                        step=max(1, 30)):
            frames_bgr.append(bgr)
            if len(frames_bgr) >= num_frames:
                break

        if not frames_bgr:
            return 0.5

        frame_scores = []
        for frame in frames_bgr:
            if frame is None:
                continue
            try:
                h, w = frame.shape[:2]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # 1. 模糊度 (Blur): Laplacian方差, 越大越清晰
                lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                # 归一化: 典型范围0-1000, 映射到0-1
                blur_score = min(lap_var / 500.0, 1.0)

                # 2. 噪声估计: 高斯滤波前后的差异
                blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                noise_map = cv2.absdiff(gray, blurred).astype(np.float32)
                noise_level = float(np.mean(noise_map))
                # 噪声归一化: 0-20范围映射到0-1, 越低越好 → 做反转
                noise_score = max(0.0, 1.0 - noise_level / 20.0)

                # 3. 块效应: 8x8边界差异 (JPEG压缩伪影)
                blockiness = 0.0
                if h > 16 and w > 16:
                    # 在8x8网格边界上计算差异
                    h_diff = 0.0
                    for y in range(8, h - 8, 8):
                        row_diff = np.abs(gray[y, :].astype(float) -
                                          gray[y - 1, :].astype(float)).mean()
                        h_diff += row_diff
                    h_diff /= max(1, (h - 8) // 8)

                    v_diff = 0.0
                    for x in range(8, w - 8, 8):
                        col_diff = np.abs(gray[:, x].astype(float) -
                                          gray[:, x - 1].astype(float)).mean()
                        v_diff += col_diff
                    v_diff /= max(1, (w - 8) // 8)

                    # 与相邻像素差异的比值
                    adj_h = np.abs(gray[:, 1:] - gray[:, :-1]).mean()
                    adj_v = np.abs(gray[1:, :] - gray[:-1, :]).mean()
                    adj_mean = (adj_h + adj_v) / 2.0 if (adj_h + adj_v) > 0 else 1.0

                    block_score = ((h_diff + v_diff) / 2.0) / adj_mean
                    blockiness = max(0.0, 1.0 - min(block_score / 3.0, 1.0))

                # 4. 亮度适中
                brightness = float(np.mean(gray)) / 255.0
                brightness_score = 1.0 - abs(0.5 - brightness) * 2.0

                # 5. 对比度
                contrast = float(np.std(gray)) / 127.5
                contrast_score = min(contrast, 1.0)

                # 综合DOVER评分 (加权)
                combined = (
                    blur_score * 0.35 +
                    noise_score * 0.25 +
                    blockiness * 0.20 +
                    brightness_score * 0.10 +
                    contrast_score * 0.10
                )
                frame_scores.append(max(0.0, min(1.0, combined)))

            except Exception as e:
                logger.warning(f"DOVER frame scoring error: {e}")
                continue

        if not frame_scores:
            return 0.5

        return round(float(np.mean(frame_scores)), 4)

    # ========================================================================
    # Motion Score — 运动评分
    # ========================================================================

    def motion_score(self, video_path: str, num_samples: int = 30) -> float:
        """
        运动评分 (0-1)

        算法:
        1. 帧差法: 连续帧像素差的绝对值均值
        2. 光流法: OpenCV calcOpticalFlowFarneback
        3. 综合 = 帧差均值 * 0.6 + 光流幅值 * 0.4

        高=运动剧烈, 低=静态
        """
        if not CV2_AVAILABLE:
            return 0.5

        # 采样帧对
        frames_bgr = []
        max_frames_needed = min(num_samples + 1, 200)
        for idx, ts, bgr, _ in _frame_iterator_opencv(video_path,
                                                        max_frames=max_frames_needed,
                                                        step=1):
            frames_bgr.append(bgr)
            if len(frames_bgr) >= max_frames_needed:
                break

        if len(frames_bgr) < 2:
            return 0.0

        frame_diffs = []
        flow_mags = []
        sample_pairs = min(len(frames_bgr) - 1, num_samples)

        for i in range(sample_pairs):
            f1 = frames_bgr[i]
            f2 = frames_bgr[i + 1]

            if f1 is None or f2 is None:
                continue

            try:
                g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
                g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)

                # 1. 帧差法
                diff = cv2.absdiff(g1, g2).astype(np.float32)
                frame_diff = float(np.mean(diff))
                frame_diffs.append(frame_diff)

                # 2. 光流法
                flow = cv2.calcOpticalFlowFarneback(
                    g1, g2, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                mag, _ = cv2.cartToPolar(flow[:, :, 0], flow[:, :, 1])
                flow_mag = float(np.mean(mag))
                flow_mags.append(flow_mag)

            except Exception as e:
                logger.warning(f"Motion score frame {i} error: {e}")
                continue

        if not frame_diffs:
            return 0.0

        # 归一化帧差: 典型0-30范围
        diff_mean = float(np.mean(frame_diffs))
        diff_norm = min(diff_mean / 30.0, 1.0)

        # 归一化光流幅值
        flow_mean = float(np.mean(flow_mags)) if flow_mags else 0.0
        flow_norm = min(flow_mean / 5.0, 1.0)

        # 综合
        motion = diff_norm * 0.6 + flow_norm * 0.4
        return round(max(0.0, min(1.0, motion)), 4)

    # ========================================================================
    # Flow Score — 光流一致性
    # ========================================================================

    def flow_score(self, video_path: str, num_samples: int = 30) -> float:
        """
        光流一致性 (0-1)

        高=运动平滑自然, 低=抖动/跳帧/卡顿

        算法:
        1. 计算连续帧的稠密光流
        2. 计算光流幅值分布的方差 (低方差=一致运动)
        3. 计算光流方向的连贯性
        """
        if not CV2_AVAILABLE:
            return 0.5

        frames_bgr = []
        for idx, ts, bgr, _ in _frame_iterator_opencv(video_path,
                                                        max_frames=num_samples + 1,
                                                        step=1):
            frames_bgr.append(bgr)
            if len(frames_bgr) >= num_samples + 1:
                break

        if len(frames_bgr) < 3:
            return 0.5

        flow_magnitudes = []
        flow_angle_diffs = []

        for i in range(len(frames_bgr) - 1):
            try:
                g1 = cv2.cvtColor(frames_bgr[i], cv2.COLOR_BGR2GRAY)
                g2 = cv2.cvtColor(frames_bgr[i + 1], cv2.COLOR_BGR2GRAY)

                flow = cv2.calcOpticalFlowFarneback(
                    g1, g2, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                mag, ang = cv2.cartToPolar(flow[:, :, 0], flow[:, :, 1])

                flow_magnitudes.append(float(np.mean(mag)))

                if i > 0 and len(flow_magnitudes) >= 2:
                    # 方向变化: 相邻光流的角度差
                    prev_mag = flow_magnitudes[-2]
                    curr_mag = flow_magnitudes[-1]
                    if prev_mag > 0.5 and curr_mag > 0.5:  # 只分析有运动的区域
                        angle_change = abs(float(np.mean(ang)) - 0)  # 简化: 用均值方向
                        flow_angle_diffs.append(min(angle_change / np.pi, 1.0))
                    else:
                        flow_angle_diffs.append(0.0)

            except Exception as e:
                logger.warning(f"Flow score error at frame {i}: {e}")
                continue

        if len(flow_magnitudes) < 2:
            return 0.5

        # 幅值稳定性: 低CV = 好 (运动一致)
        mag_arr = np.array(flow_magnitudes)
        mag_mean = float(np.mean(mag_arr))
        mag_std = float(np.std(mag_arr))
        # 使用变异系数: CV越低运动越一致
        cv_score = 1.0 - min(mag_std / (mag_mean + 0.01), 1.0)

        # 方向连续性
        angle_score = 1.0
        if flow_angle_diffs:
            angle_score = 1.0 - float(np.mean(flow_angle_diffs))

        # 综合
        flow_consistency = cv_score * 0.6 + angle_score * 0.4
        return round(max(0.0, min(1.0, flow_consistency)), 4)

    # ========================================================================
    # Aesthetic Score — 视频美学
    # ========================================================================

    def aesthetic_score(self, video_path: str, num_frames: int = 10) -> float:
        """
        视频美学评分 (0-10, 对齐LAION标准)

        取关键帧的aesthetic score平均值。
        使用data_quality_advanced的评分，或fallback到图像属性分析。
        """
        frames_bgr = []
        for idx, ts, bgr, _ in _frame_iterator_opencv(video_path,
                                                        max_frames=num_frames,
                                                        step=max(1, 15)):
            frames_bgr.append(bgr)
            if len(frames_bgr) >= num_frames:
                break

        if not frames_bgr:
            return 5.0

        # 尝试用 AdvancedQualityScorer
        try:
            from data_quality_advanced import AdvancedQualityScorer
            scorer = AdvancedQualityScorer()
            scores = []
            for frame in frames_bgr:
                if frame is None:
                    continue
                try:
                    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    score = scorer.aesthetic_score(pil_img)
                    scores.append(score)
                except Exception:
                    continue
            if scores:
                return round(float(np.mean(scores)), 4)
        except ImportError:
            pass

        # Fallback: 基于图像属性的简单美学评分
        scores = []
        for frame in frames_bgr:
            if frame is None:
                continue
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                h, w = frame.shape[:2]

                # 清晰度
                lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                sharpness = min(lap_var / 500.0, 1.0)

                # 色彩丰富度
                if len(frame.shape) == 3:
                    r, g, b = frame[:, :, 0].astype(float), frame[:, :, 1].astype(float), frame[:, :, 2].astype(float)
                    rg = np.abs(r - g).mean()
                    yb = np.abs(0.5 * (r + g) - b).mean()
                    colorfulness = min(np.sqrt(rg**2 + yb**2) / 80.0, 1.0)
                else:
                    colorfulness = 0.3

                # 亮度适中
                brightness = float(np.mean(gray)) / 255.0
                brightness_score = 1.0 - abs(0.5 - brightness) * 2.0

                # 对比度
                contrast = min(float(np.std(gray)) / 127.5, 1.0)

                # 综合到0-10
                aesthetic = (sharpness * 3.0 + colorfulness * 3.0 +
                             brightness_score * 2.0 + contrast * 2.0)
                scores.append(aesthetic * 10.0 / 10.0)

            except Exception:
                continue

        if not scores:
            return 5.0
        return round(max(1.0, min(10.0, float(np.mean(scores)))), 4)

    # ========================================================================
    # NSFW Score — 视频NSFW检测
    # ========================================================================

    def nsfw_score(self, video_path: str, num_frames: int = 10) -> float:
        """
        视频NSFW评分 (0-1, 0=安全)

        取关键帧中NSFW分数的最大值。
        """
        frames_bgr = []
        for idx, ts, bgr, _ in _frame_iterator_opencv(video_path,
                                                        max_frames=num_frames,
                                                        step=max(1, 15)):
            frames_bgr.append(bgr)
            if len(frames_bgr) >= num_frames:
                break

        if not frames_bgr:
            return 0.0

        classifier = self._get_nsfw_classifier()
        if classifier is None:
            return 0.0

        nsfw_scores = []
        for frame in frames_bgr:
            if frame is None:
                continue
            try:
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                result = classifier.classify(pil_img)
                nsfw_scores.append(result.get("nsfw_score", 0.0))
            except Exception as e:
                logger.warning(f"NSFW frame scoring error: {e}")
                continue

        if not nsfw_scores:
            return 0.0

        # 取最大值 (最不安全的那一帧)
        return round(float(np.max(nsfw_scores)), 4)

    # ========================================================================
    # CLIP Score — 视频-文本匹配
    # ========================================================================

    def video_clip_score(self, video_path: str, caption: str,
                         num_frames: int = 8) -> float:
        """
        视频-文本匹配度 (0-1)

        对关键帧提取embedding，与caption embedding计算余弦相似度，取平均。

        Args:
            video_path: 视频路径
            caption: 文本描述
            num_frames: 采样的关键帧数

        Returns:
            0-1 的匹配度
        """
        if not caption or not self._st_loaded or self._st_model is None:
            return 0.0

        frames_bgr = []
        for idx, ts, bgr, _ in _frame_iterator_opencv(video_path,
                                                        max_frames=num_frames,
                                                        step=max(1, 15)):
            frames_bgr.append(bgr)
            if len(frames_bgr) >= num_frames:
                break

        if not frames_bgr:
            return 0.0

        try:
            # 编码文本
            text_emb = self._st_model.encode(caption)
            text_norm = np.linalg.norm(text_emb)
            if text_norm == 0:
                return 0.0
            text_emb = text_emb / text_norm

            similarities = []
            for frame in frames_bgr:
                if frame is None:
                    continue
                try:
                    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    # 保存临时文件用于编码
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        tmp_path = tmp.name
                        pil_img.save(tmp_path, quality=90)

                    img_emb = self._st_model.encode(tmp_path)
                    os.unlink(tmp_path)

                    img_norm = np.linalg.norm(img_emb)
                    if img_norm > 0:
                        img_emb = img_emb / img_norm
                        sim = float(np.dot(img_emb, text_emb))
                        # 映射到0-1: (sim + 1) / 2
                        clip_val = max(0.0, min(1.0, (sim + 1.0) / 2.0))
                        similarities.append(clip_val)
                except Exception as e:
                    logger.warning(f"CLIP frame scoring error: {e}")
                    continue

            if not similarities:
                return 0.0
            return round(float(np.mean(similarities)), 4)

        except Exception as e:
            logger.warning(f"video_clip_score failed: {e}")
            return 0.0

    # ========================================================================
    # 完整视频信息提取
    # ========================================================================

    def probe_video(self, video_path: str) -> Dict[str, Any]:
        """提取视频基本信息"""
        info = {
            "path": video_path,
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "num_frames": 0,
            "duration": 0.0,
            "aspect_ratio": 0.0,
            "resolution": 0,
            "codec": "",
            "file_size": 0,
        }

        if not os.path.exists(video_path):
            return info

        info["file_size"] = os.path.getsize(video_path)

        if CV2_AVAILABLE:
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                info["fps"] = cap.get(cv2.CAP_PROP_FPS)
                info["num_frames"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
                if fourcc:
                    info["codec"] = struct.pack('<I', fourcc).decode('utf-8', errors='replace').strip()
                cap.release()

                if info["width"] > 0 and info["height"] > 0:
                    info["aspect_ratio"] = round(info["width"] / info["height"], 4)
                    info["resolution"] = min(info["width"], info["height"])

                if info["fps"] > 0 and info["num_frames"] > 0:
                    info["duration"] = round(info["num_frames"] / info["fps"], 4)
                elif info["fps"] > 0:
                    info["duration"] = round(info["num_frames"] / info["fps"], 4)

        return info

    # ========================================================================
    # 完整视频评估
    # ========================================================================

    def assess(self, video_path: str, caption: str = "") -> Dict[str, Any]:
        """
        完整视频评估 — 返回Open-Sora兼容的JSONL格式

        Args:
            video_path: 视频路径
            caption: 文本描述 (用于CLIP Score)

        Returns:
            包含所有评分维度的字典
        """
        info = self.probe_video(video_path)

        result = {
            "path": video_path,
            "caption": caption,
            "num_frames": info.get("num_frames", 0),
            "fps": info.get("fps", 0),
            "width": info.get("width", 0),
            "height": info.get("height", 0),
            "aspect_ratio": info.get("aspect_ratio", 0),
            "resolution": info.get("resolution", 0),
            "duration": info.get("duration", 0),
            "text_len": len(caption) if caption else 0,
            "file_size": info.get("file_size", 0),
            "codec": info.get("codec", ""),
        }

        # 评分
        result["dover_score"] = self.dover_score(video_path)
        result["motion_score"] = self.motion_score(video_path)
        result["flow_score"] = self.flow_score(video_path)
        result["aesthetic_score"] = self.aesthetic_score(video_path)
        result["nsfw_score"] = self.nsfw_score(video_path)

        if caption:
            result["clip_score"] = self.video_clip_score(video_path, caption)
        else:
            result["clip_score"] = 0.0

        return result

    # ========================================================================
    # 一次过滤 — 对齐Open-Sora标准阈值
    # ========================================================================

    def filter(self, video_path: str, caption: str = "") -> Dict[str, Any]:
        """
        一次过滤 — 对齐Open-Sora标准阈值

        Criteria:
        - DOVER >= 0.65
        - Resolution >= 720p
        - Duration >= 2s
        - Motion >= 0.1
        - NSFW < 0.5

        Returns:
            dict with 'passed' (bool) and 'reason' (str if failed)
        """
        info = self.probe_video(video_path)

        reasons = []

        # 1. 分辨率 >= 720p
        resolution = info.get("resolution", 0)
        if resolution < self.MIN_RESOLUTION:
            reasons.append(f"resolution_below_720p({resolution})")

        # 2. 时长 >= 2秒
        duration = info.get("duration", 0)
        if duration < self.MIN_DURATION:
            reasons.append(f"duration_below_2s({duration:.2f})")

        # 如果基本条件不满足, 直接返回
        if reasons:
            return {
                "passed": False,
                "reason": "; ".join(reasons),
                "video_info": info,
            }

        # 3. DOVER评分
        dover = self.dover_score(video_path)
        if dover < self.DOVER_THRESHOLD:
            reasons.append(f"dover_below_0.65({dover:.4f})")

        # 4. Motion评分
        motion = self.motion_score(video_path)
        if motion < self.MIN_MOTION:
            reasons.append(f"motion_below_0.1({motion:.4f})")

        # 5. NSFW
        nsfw = self.nsfw_score(video_path)
        if nsfw >= self.MAX_NSFW:
            reasons.append(f"nsfw_above_0.5({nsfw:.4f})")

        passed = len(reasons) == 0

        return {
            "passed": passed,
            "reason": "; ".join(reasons) if reasons else "passed",
            "dover_score": round(dover, 4),
            "motion_score": round(motion, 4),
            "nsfw_score": round(nsfw, 4),
            "video_info": info,
        }

    # ========================================================================
    # 导出Open-Sora JSONL
    # ========================================================================

    def to_opensora_jsonl(self, video_path: str, caption: str = "") -> Dict:
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
        """
        assessment = self.assess(video_path, caption)
        return assessment

    def to_panda70m_jsonl(self, video_path: str, caption: str = "") -> Dict:
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
        """
        info = self.probe_video(video_path)

        result = {
            "video": video_path,
            "caption": caption,
            "duration": info.get("duration", 0),
            "resolution": [info.get("width", 0), info.get("height", 0)],
            "fps": info.get("fps", 0),
            "num_frames": info.get("num_frames", 0),
            "aesthetic": self.aesthetic_score(video_path),
            "motion": self.motion_score(video_path),
            "dover": self.dover_score(video_path),
            "nsfw": self.nsfw_score(video_path),
        }

        if caption:
            result["clip_score"] = self.video_clip_score(video_path, caption)
        else:
            result["clip_score"] = 0.0

        return result

    # ========================================================================
    # 批量评估
    # ========================================================================

    def batch_assess(self, video_paths: List[str],
                     captions: Optional[List[str]] = None,
                     parallel: bool = False,
                     max_workers: int = 2) -> List[Dict]:
        """批量视频评估"""
        results = []

        if captions is None:
            captions = [""] * len(video_paths)

        if parallel:
            try:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_idx = {}
                    for i, (vp, cap) in enumerate(zip(video_paths, captions)):
                        future = executor.submit(self.assess, vp, cap)
                        future_to_idx[future] = i

                    for future in as_completed(future_to_idx):
                        i = future_to_idx[future]
                        try:
                            results.append(future.result())
                        except Exception as e:
                            results.append({"path": video_paths[i], "error": str(e)})
            except ImportError:
                parallel = False

        if not parallel:
            for vp, cap in zip(video_paths, captions):
                try:
                    results.append(self.assess(vp, cap))
                except Exception as e:
                    results.append({"path": vp, "error": str(e)})

        return results

    def batch_filter(self, video_paths: List[str],
                     captions: Optional[List[str]] = None) -> List[Dict]:
        """批量过滤"""
        if captions is None:
            captions = [""] * len(video_paths)
        return [self.filter(vp, cap) for vp, cap in zip(video_paths, captions)]


# ============================================================================
# Convenience singleton
# ============================================================================

_assessor_instance: Optional[VideoQualityAssessor] = None


def get_video_quality_assessor() -> VideoQualityAssessor:
    """获取VideoQualityAssessor单例"""
    global _assessor_instance
    if _assessor_instance is None:
        _assessor_instance = VideoQualityAssessor()
    return _assessor_instance
