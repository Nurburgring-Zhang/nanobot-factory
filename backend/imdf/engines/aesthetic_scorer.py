"""
F1.11 审美评分引擎 — Aesthetic Scoring Engine
============================================
- CLIP-IQA风格评分: 清晰度/构图/色彩/亮度/噪点
- MUSIQ风格多维度打分: technical/aesthetic/content
- 批量评分支持
"""

from __future__ import annotations
import os
import math
import statistics
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image, ImageStat, ImageFilter, ImageEnhance
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


@dataclass
class ClipIQAScores:
    """CLIP-IQA风格评分维度"""
    sharpness: float = 0.0      # 清晰度 (0-100)
    composition: float = 0.0    # 构图平衡 (0-100)
    color_harmony: float = 0.0  # 色彩和谐 (0-100)
    brightness: float = 0.0     # 亮度适中 (0-100)
    noise_level: float = 0.0    # 噪点水平 (越低越好, 转换为分数)

    @property
    def overall(self) -> float:
        """综合分: 加权平均"""
        weights = {"sharpness": 0.25, "composition": 0.20, "color_harmony": 0.25,
                    "brightness": 0.15, "noise_level": 0.15}
        return round(
            self.sharpness * weights["sharpness"] +
            self.composition * weights["composition"] +
            self.color_harmony * weights["color_harmony"] +
            self.brightness * weights["brightness"] +
            self.noise_level * weights["noise_level"], 2
        )

    def to_dict(self) -> dict:
        return {
            "sharpness": self.sharpness,
            "composition": self.composition,
            "color_harmony": self.color_harmony,
            "brightness": self.brightness,
            "noise_level": self.noise_level,
            "overall": self.overall,
        }


@dataclass
class MUSIQScores:
    """MUSIQ风格多维度打分"""
    technical: float = 0.0    # 技术质量: no blur/noise/artifact
    aesthetic: float = 0.0    # 美学质量: composition/color/light
    content: float = 0.0      # 内容质量: subject/semantics

    @property
    def overall(self) -> float:
        return round((self.technical * 0.35 + self.aesthetic * 0.40 + self.content * 0.25), 2)

    def to_dict(self) -> dict:
        return {
            "technical": self.technical,
            "aesthetic": self.aesthetic,
            "content": self.content,
            "overall": self.overall,
        }


@dataclass
class AestheticResult:
    """完整审美评分结果"""
    file_path: str = ""
    file_name: str = ""
    image_size: tuple = (0, 0)
    clip_iqa: Optional[ClipIQAScores] = None
    musiq: Optional[MUSIQScores] = None
    grade: str = "C"  # S/A/B/C/D
    issues: List[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        """综合美学得分 (0-100)"""
        scores = []
        if self.clip_iqa:
            scores.append(self.clip_iqa.overall)
        if self.musiq:
            scores.append(self.musiq.overall)
        return round(statistics.mean(scores), 2) if scores else 0.0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "image_size": {"width": self.image_size[0], "height": self.image_size[1]},
            "clip_iqa": self.clip_iqa.to_dict() if self.clip_iqa else None,
            "musiq": self.musiq.to_dict() if self.musiq else None,
            "overall_score": self.overall_score,
            "grade": self.grade,
            "issues": self.issues,
        }


def _compute_grade(score: float) -> str:
    """分数转等级"""
    if score >= 90:
        return "S"
    elif score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"


class AestheticScorer:
    """审美评分引擎 — 基于图像特征的启发式评分"""

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        if not HAS_PILLOW:
            print("[AestheticScorer] WARNING: Pillow not installed. Scoring will use fallback.")

    # ── CLIP-IQA风格评分 ────────────────────────────────────────────────

    def score_sharpness(self, img: Image.Image) -> float:
        """评估清晰度: 基于拉普拉斯方差"""
        gray = img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(edges)
        variance = stat.var[0] if stat.var else 0
        # 映射到0-100 (典型值: 方差50-500)
        score = min(100, max(0, math.log2(variance + 1) * 12))
        return round(score, 2)

    def score_composition(self, img: Image.Image) -> float:
        """评估构图: 基于三分法/对称性"""
        w, h = img.size
        gray = img.convert("L")
        pixels = list(gray.getdata())

        # 计算水平和垂直方向的质量分布
        def _region_mean(x1, y1, x2, y2):
            region = img.crop((x1, y1, x2, y2))
            stat = ImageStat.Stat(region)
            return sum(stat.mean) / len(stat.mean) if stat.mean else 0

        # 九宫格分析
        third_w, third_h = w // 3, h // 3
        regions = []
        for row in range(3):
            for col in range(3):
                x1, y1 = col * third_w, row * third_h
                x2, y2 = min(x1 + third_w, w), min(y1 + third_h, h)
                if x2 > x1 and y2 > y1:
                    regions.append(_region_mean(x1, y1, x2, y2))

        if len(regions) < 2:
            return 50.0

        # 区域差异度 — 适中为好 (太均匀=平淡, 太差异=杂乱)
        mean_vals = regions
        avg = statistics.mean(mean_vals)
        std = statistics.stdev(mean_vals) if len(mean_vals) > 1 else 0

        # 理想std约为主体的30-50%
        ideal_std = 40
        comp_score = 100 - min(100, abs(std - ideal_std) * 1.5)
        return round(max(0, comp_score), 2)

    def score_color_harmony(self, img: Image.Image) -> float:
        """评估色彩和谐度"""
        img_rgb = img.convert("RGB")
        stat = ImageStat.Stat(img_rgb)

        # 各通道均值和标准差
        means = stat.mean
        stds = stat.stddev if stat.stddev else [0, 0, 0]

        # 色彩饱和度
        r, g, b = means[0], means[1], means[2]
        # 饱和度 = max-min
        saturation = max(r, g, b) - min(r, g, b)

        # 色彩丰富度 (std之和)
        richness = sum(stds)

        # 理想饱和度30-80, 丰富度40-120
        sat_score = 100 - min(100, abs(saturation - 55) * 1.5)
        rich_score = min(100, richness * 1.2)

        return round((sat_score * 0.4 + rich_score * 0.6), 2)

    def score_brightness(self, img: Image.Image) -> float:
        """评估亮度: 理想亮度在40-65%区间"""
        gray = img.convert("L")
        stat = ImageStat.Stat(gray)
        mean_brightness = stat.mean[0] if stat.mean else 128

        # 理想亮度约128 (50%灰)
        ideal = 128
        deviation = abs(mean_brightness - ideal)
        score = 100 - min(100, deviation * 0.8)
        return round(score, 2)

    def score_noise(self, img: Image.Image) -> float:
        """评估噪点水平: 分数越高噪点越少"""
        gray = img.convert("L")
        # 用模糊差分评估噪点
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=3))
        pixels_orig = list(gray.getdata())
        pixels_blur = list(blurred.getdata())

        diffs = [abs(pixels_orig[i] - pixels_blur[i]) for i in range(len(pixels_orig))]
        avg_diff = statistics.mean(diffs) if diffs else 0

        # 差异越小越好 (0差异=完美, 但实际图像总有些纹理)
        score = 100 - min(100, avg_diff * 6)
        return round(score, 2)

    def score_clip_iqa(self, img: Image.Image) -> ClipIQAScores:
        """完整CLIP-IQA风格评分"""
        return ClipIQAScores(
            sharpness=self.score_sharpness(img),
            composition=self.score_composition(img),
            color_harmony=self.score_color_harmony(img),
            brightness=self.score_brightness(img),
            noise_level=self.score_noise(img),
        )

    # ── MUSIQ风格多维度打分 ─────────────────────────────────────────────

    def score_musiq(self, img: Image.Image) -> MUSIQScores:
        """MUSIQ风格评分: 基于CLIP-IQA结果进行维度聚合"""
        clip = self.score_clip_iqa(img)

        # Technical: 清晰度+噪点
        technical = round((clip.sharpness * 0.6 + clip.noise_level * 0.4), 2)

        # Aesthetic: 构图+色彩+亮度
        aesthetic = round((clip.composition * 0.35 + clip.color_harmony * 0.40 +
                           clip.brightness * 0.25), 2)

        # Content: 基于图像复杂度推测 (分辨率+细节)
        w, h = img.size
        resolution_score = min(100, math.log2(w * h) * 4)
        content = round(resolution_score * 0.7 + clip.composition * 0.3, 2)

        return MUSIQScores(technical=technical, aesthetic=aesthetic, content=content)

    # ── Public API ──────────────────────────────────────────────────────

    def score_image(self, image_path: str) -> AestheticResult:
        """对单张图片进行完整审美评分"""
        path = Path(image_path)
        if not path.exists():
            return AestheticResult(
                file_path=str(path),
                file_name=path.name,
                issues=[f"File not found: {image_path}"],
            )

        if not HAS_PILLOW:
            return AestheticResult(
                file_path=str(path),
                file_name=path.name,
                issues=["Pillow not installed; cannot perform scoring"],
                clip_iqa=ClipIQAScores(),
                musiq=MUSIQScores(),
            )

        try:
            img = Image.open(path)
            w, h = img.size

            clip = self.score_clip_iqa(img)
            musiq = self.score_musiq(img)

            overall = round((clip.overall + musiq.overall) / 2, 2)
            grade = _compute_grade(overall)

            issues = []
            if clip.sharpness < 30:
                issues.append("Low sharpness: image may be blurry")
            if clip.brightness < 20:
                issues.append("Very dark image")
            if clip.brightness > 90:
                issues.append("Overexposed image")
            if clip.noise_level < 30:
                issues.append("High noise level detected")

            return AestheticResult(
                file_path=str(path.absolute()),
                file_name=path.name,
                image_size=(w, h),
                clip_iqa=clip,
                musiq=musiq,
                grade=grade,
                issues=issues,
            )
        except Exception as e:
            return AestheticResult(
                file_path=str(path),
                file_name=path.name,
                issues=[f"Error processing image: {str(e)}"],
            )

    def score_batch(self, image_paths: List[str]) -> List[AestheticResult]:
        """批量评分"""
        return [self.score_image(p) for p in image_paths]

    def score_directory(self, directory: str, extensions: tuple = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')) -> List[AestheticResult]:
        """对目录下所有图片进行评分"""
        dir_path = Path(directory)
        if not dir_path.exists():
            return []

        image_files = []
        for ext in extensions:
            image_files.extend(dir_path.glob(f"*{ext}"))
            image_files.extend(dir_path.glob(f"*{ext.upper()}"))

        paths = [str(f) for f in sorted(set(image_files))]
        return self.score_batch(paths)

    def batch_summary(self, results: List[AestheticResult]) -> dict:
        """批量评分汇总统计"""
        if not results:
            return {"total": 0, "average_score": 0, "grade_distribution": {}}

        scores = [r.overall_score for r in results if r.overall_score > 0]
        grades = [r.grade for r in results if r.grade]

        grade_dist = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        for g in grades:
            if g in grade_dist:
                grade_dist[g] += 1

        return {
            "total": len(results),
            "scored": len(scores),
            "average_score": round(statistics.mean(scores), 2) if scores else 0.0,
            "min_score": round(min(scores), 2) if scores else 0.0,
            "max_score": round(max(scores), 2) if scores else 0.0,
            "std_dev": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
            "grade_distribution": grade_dist,
        }


# ── Singleton ──────────────────────────────────────────────────────────

_aesthetic_scorer: Optional[AestheticScorer] = None


def get_aesthetic_scorer() -> AestheticScorer:
    global _aesthetic_scorer
    if _aesthetic_scorer is None:
        _aesthetic_scorer = AestheticScorer()
    return _aesthetic_scorer
