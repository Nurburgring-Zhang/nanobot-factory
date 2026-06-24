"""
NanoBot Factory — 视频去重模块
Video Deduplication Module

对齐 Panda-70M / Open-Sora 标准。

去重策略:
1. Spatial pHash: 每3秒提取关键帧的pHash, Hamming距离<15视为重复
2. Temporal matching: 帧差序列的相关性
3. Near-duplicate: 综合spatial+temporal的联合判断
"""

import os, sys, io, json, logging, math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from collections import defaultdict

import numpy as np
from PIL import Image

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# pHash 工具 (纯Python, 无需imagehash库)
# ============================================================================

def _pil_to_gray(img: Image.Image, size: Tuple[int, int] = (32, 32)) -> np.ndarray:
    """PIL Image -> 灰度numpy array"""
    if img.mode != 'L':
        img = img.convert('L')
    img = img.resize(size, Image.LANCZOS)
    return np.array(img, dtype=np.float32)


def compute_phash(image: Union[str, Image.Image, np.ndarray],
                  hash_size: int = 8, highfreq_factor: int = 4) -> str:
    """
    计算感知哈希 (pHash)

    使用DCT的低频系数生成64-bit哈希, 与imagehash.phash兼容。

    Args:
        image: 图像 (路径 / PIL / numpy)
        hash_size: 最终哈希大小 (输出位数 = hash_size^2)
        highfreq_factor: 图像缩放的因子 (缩放尺寸 = hash_size * highfreq_factor)

    Returns:
        64字符的十六进制哈希字符串
    """
    # 加载图像
    if isinstance(image, str):
        img = Image.open(image)
    elif isinstance(image, np.ndarray):
        img = Image.fromarray(image)
    else:
        img = image

    img_size = hash_size * highfreq_factor
    gray = _pil_to_gray(img, (img_size, img_size))

    # DCT
    dct = cv2.dct(gray)
    # 取左上角低频区域
    dct_low = dct[:hash_size, :hash_size]

    # 去掉DC分量 (第一个系数)
    med = np.median(dct_low)
    # 生成二进制哈希
    bits = (dct_low > med).flatten()
    # 转为十六进制字符串
    hex_hash = ''.join(['1' if b else '0' for b in bits])
    # 转为十六进制 (每4位一组)
    hex_str = ''
    for i in range(0, len(hex_hash), 4):
        nibble = hex_hash[i:i+4]
        hex_str += format(int(nibble, 2), 'x')
    return hex_str


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    计算两个十六进制pHash之间的汉明距离

    Args:
        hash1: 第一个哈希 (十六进制字符串)
        hash2: 第二个哈希 (十六进制字符串)

    Returns:
        汉明距离 (不同的位数)
    """
    if len(hash1) != len(hash2):
        return 64  # 最大距离

    # 将十六进制转为二进制后比较
    bits1 = bin(int(hash1, 16))[2:].zfill(len(hash1) * 4)
    bits2 = bin(int(hash2, 16))[2:].zfill(len(hash2) * 4)

    dist = sum(1 for a, b in zip(bits1, bits2) if a != b)
    return dist


# ============================================================================
# 帧提取工具
# ============================================================================

def _extract_keyframe_timestamps(video_path: str,
                                  interval_sec: float = 3.0) -> List[Tuple[float, np.ndarray]]:
    """
    按时间间隔提取关键帧

    Returns:
        [(timestamp, bgr_frame), ...]
    """
    if not CV2_AVAILABLE:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 300

    duration = total_frames / fps
    interval_frames = max(1, int(fps * interval_sec))

    frames = []
    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % interval_frames == 0:
                ts = frame_idx / fps
                frames.append((ts, frame))
            frame_idx += 1

            # 最多采100帧
            if len(frames) >= 100:
                break
    finally:
        cap.release()

    return frames


def _frame_diff_sequence(video_path: str, num_samples: int = 50) -> np.ndarray:
    """
    提取帧差序列 (用于temporal匹配)

    Returns:
        一维数组: 连续帧的绝对差均值
    """
    if not CV2_AVAILABLE:
        return np.array([])

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return np.array([])

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 300

    step = max(1, total_frames // num_samples)

    diffs = []
    prev_gray = None
    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray).astype(np.float32)
                    diffs.append(float(np.mean(diff)))
                prev_gray = gray
            frame_idx += 1
    finally:
        cap.release()

    if not diffs:
        return np.array([])

    # 归一化
    arr = np.array(diffs, dtype=np.float32)
    if np.max(arr) > 0:
        arr = arr / np.max(arr)
    return arr


# ============================================================================
# VideoDeduplicator
# ============================================================================

class VideoDeduplicator:
    """
    视频去重 — 对齐Panda-70M/Open-Sora标准

    策略:
    1. Spatial pHash: 每3秒提取关键帧的pHash, Hamming距离<15
    2. Temporal matching: 帧差序列的相关性 (Pearson相关系数 > 0.85)
    3. Near-duplicate: 综合spatial pHash + temporal matching联合判断

    用法:
        dedup = VideoDeduplicator()
        # Spatial去重
        duplicates = dedup.spatial_dedup(video_paths, threshold=15)
        # Temporal去重
        duplicates = dedup.temporal_dedup(video_paths, threshold=0.85)
        # 全量去重
        duplicates = dedup.full_dedup(video_paths)
    """

    # 默认阈值
    SPATIAL_THRESHOLD = 15      # pHash 汉明距离
    TEMPORAL_THRESHOLD = 0.85   # 帧差序列 Pearson 相关系数

    def __init__(self):
        self._phash_cache: Dict[str, List[str]] = {}  # video_path -> [hash1, hash2, ...]
        self._temporal_cache: Dict[str, np.ndarray] = {}  # video_path -> frame_diff_array

    # ========================================================================
    # Spatial pHash 去重
    # ========================================================================

    def _get_phash_sequence(self, video_path: str,
                            interval_sec: float = 3.0) -> List[str]:
        """获取视频的pHash序列 (缓存)"""
        if video_path in self._phash_cache:
            return self._phash_cache[video_path]

        frames = _extract_keyframe_timestamps(video_path, interval_sec)
        hashes = []
        for ts, bgr in frames:
            try:
                pil_img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                h = compute_phash(pil_img)
                hashes.append(h)
            except Exception as e:
                logger.warning(f"pHashing frame at {ts}s: {e}")
                continue

        self._phash_cache[video_path] = hashes
        return hashes

    def spatial_dedup(self, video_paths: List[str],
                      threshold: int = 15) -> List[Tuple[str, str, float]]:
        """
        Spatial pHash去重

        比较每对视频的pHash序列, 如果任意帧对的汉明距离 < threshold, 标记为重复。

        Args:
            video_paths: 视频路径列表
            threshold: pHash汉明距离阈值 (默认15)

        Returns:
            [(video1, video2, similarity_score), ...] 重复对列表
            similarity_score = 1 - normalized_hamming_distance (0-1)
        """
        duplicates = []
        n = len(video_paths)

        for i in range(n):
            hashes_i = self._get_phash_sequence(video_paths[i])
            if not hashes_i:
                continue

            for j in range(i + 1, n):
                hashes_j = self._get_phash_sequence(video_paths[j])
                if not hashes_j:
                    continue

                # 计算最小汉明距离
                min_dist = 64
                for h1 in hashes_i:
                    for h2 in hashes_j:
                        dist = hamming_distance(h1, h2)
                        min_dist = min(min_dist, dist)
                        if min_dist <= threshold:
                            break
                    if min_dist <= threshold:
                        break

                if min_dist <= threshold:
                    # 相似度 = 1 - dist/64
                    similarity = 1.0 - min_dist / 64.0
                    duplicates.append((video_paths[i], video_paths[j],
                                       round(similarity, 4)))

        logger.info(f"Spatial dedup: {n} videos -> {len(duplicates)} duplicate pairs "
                     f"(threshold={threshold})")
        return duplicates

    # ========================================================================
    # Temporal 帧差序列去重
    # ========================================================================

    def _get_temporal_sequence(self, video_path: str,
                                num_samples: int = 50) -> np.ndarray:
        """获取视频帧差序列 (缓存)"""
        if video_path in self._temporal_cache:
            return self._temporal_cache[video_path]

        seq = _frame_diff_sequence(video_path, num_samples)
        self._temporal_cache[video_path] = seq
        return seq

    def temporal_dedup(self, video_paths: List[str],
                       threshold: float = 0.85) -> List[Tuple[str, str, float]]:
        """
        Temporal帧差序列去重

        比较帧差序列的Pearson相关系数。
        高相关性(>threshold) = 相似的运动模式 = 可能的重复视频。

        Args:
            video_paths: 视频路径列表
            threshold: Pearson相关系数阈值 (默认0.85)

        Returns:
            [(video1, video2, correlation), ...] 重复对列表
        """
        duplicates = []
        n = len(video_paths)

        for i in range(n):
            seq_i = self._get_temporal_sequence(video_paths[i])
            if len(seq_i) < 5:
                continue

            for j in range(i + 1, n):
                seq_j = self._get_temporal_sequence(video_paths[j])
                if len(seq_j) < 5:
                    continue

                # 对齐到相同长度 (取短)
                min_len = min(len(seq_i), len(seq_j))
                a = seq_i[:min_len]
                b = seq_j[:min_len]

                # Pearson相关系数
                if np.std(a) > 0 and np.std(b) > 0:
                    corr = float(np.corrcoef(a, b)[0, 1])
                    if not np.isnan(corr) and corr >= threshold:
                        duplicates.append((video_paths[i], video_paths[j],
                                           round(corr, 4)))

        logger.info(f"Temporal dedup: {n} videos -> {len(duplicates)} duplicate pairs "
                     f"(threshold={threshold})")
        return duplicates

    # ========================================================================
    # 综合 Near-Duplicate 去重
    # ========================================================================

    def full_dedup(self, video_paths: List[str],
                   spatial_threshold: int = 15,
                   temporal_threshold: float = 0.85,
                   spatial_weight: float = 0.5,
                   temporal_weight: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        综合去重 — Spatial + Temporal联合判断

        如果Spatial pHash相似 或 Temporal序列相似, 标记为near-duplicate。
        综合相似度 = spatial_weight * spatial_sim + temporal_weight * temporal_sim

        Args:
            video_paths: 视频路径列表
            spatial_threshold: pHash汉明距离阈值
            temporal_threshold: 帧差序列相关系数阈值
            spatial_weight: spatial相似度权重
            temporal_weight: temporal相似度权重

        Returns:
            [(video1, video2, combined_similarity), ...] 重复对列表
        """
        duplicates = []
        n = len(video_paths)

        for i in range(n):
            hashes_i = self._get_phash_sequence(video_paths[i])
            seq_i = self._get_temporal_sequence(video_paths[i])
            if not hashes_i or len(seq_i) < 5:
                continue

            for j in range(i + 1, n):
                hashes_j = self._get_phash_sequence(video_paths[j])
                seq_j = self._get_temporal_sequence(video_paths[j])
                if not hashes_j or len(seq_j) < 5:
                    continue

                # Spatial相似度
                min_dist = 64
                for h1 in hashes_i:
                    for h2 in hashes_j:
                        dist = hamming_distance(h1, h2)
                        min_dist = min(min_dist, dist)
                spatial_sim = 1.0 - min_dist / 64.0

                # Temporal相似度
                min_len = min(len(seq_i), len(seq_j))
                a = seq_i[:min_len]
                b = seq_j[:min_len]
                temporal_sim = 0.0
                if np.std(a) > 0 and np.std(b) > 0:
                    corr = float(np.corrcoef(a, b)[0, 1])
                    if not np.isnan(corr):
                        temporal_sim = max(0.0, corr)

                # 综合判断
                is_dup = (
                    min_dist <= spatial_threshold or
                    temporal_sim >= temporal_threshold
                )

                if is_dup:
                    combined = (spatial_sim * spatial_weight +
                                temporal_sim * temporal_weight)
                    duplicates.append((video_paths[i], video_paths[j],
                                       round(combined, 4)))

        logger.info(f"Full dedup: {n} videos -> {len(duplicates)} duplicate pairs")
        return duplicates

    # ========================================================================
    # 分组去重 — 找到重复组并推荐保留哪个
    # ========================================================================

    def dedup_groups(self, video_paths: List[str],
                     spatial_threshold: int = 15,
                     temporal_threshold: float = 0.85) -> List[List[str]]:
        """
        去重分组 — 将重复视频分到同一组

        Returns:
            [[keep_path, dup1, dup2, ...], ...]
            每组第一个是保留建议 (基于文件名/质量等简单规则)
        """
        pairs = self.full_dedup(video_paths, spatial_threshold, temporal_threshold)

        # Union-Find 构建分组
        parent = {p: p for p in video_paths}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        for v1, v2, _ in pairs:
            union(v1, v2)

        # 收集分组
        groups = defaultdict(list)
        for p in video_paths:
            groups[find(p)].append(p)

        # 每组第一个作为保留建议
        result = []
        for root, members in groups.items():
            if len(members) > 1:
                # 把最短的文件名作为保留 (简单策略)
                members_sorted = sorted(members, key=lambda x: (len(os.path.basename(x)), x))
                result.append(members_sorted)

        return result

    def clear_cache(self):
        """清除缓存"""
        self._phash_cache.clear()
        self._temporal_cache.clear()


# ============================================================================
# Convenience functions
# ============================================================================

_deduplicator_instance: Optional[VideoDeduplicator] = None


def get_video_deduplicator() -> VideoDeduplicator:
    """获取VideoDeduplicator单例"""
    global _deduplicator_instance
    if _deduplicator_instance is None:
        _deduplicator_instance = VideoDeduplicator()
    return _deduplicator_instance
