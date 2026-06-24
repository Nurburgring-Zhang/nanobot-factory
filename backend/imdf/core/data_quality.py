"""
Data Quality Engine — 多模态数据质量评估
=========================================
统一图像/视频/文本质量评分标准。
整合NanoBot Factory的 data_quality_engine.py 和 data_quality_advanced.py。
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from PIL import Image
import io
import os
import json
import logging
import hashlib
import struct

logger = logging.getLogger(__name__)


class DataType(str, Enum):
    TEXT_TO_IMAGE = "t2i"
    IMAGE_EDIT = "image_edit"
    VIDEO = "video"
    SHORT_DRAMA = "short_drama"
    PICTURE_BOOK = "picture_book"


class QualityLevel(str, Enum):
    EXCELLENT = "A+"
    GOOD = "A"
    ACCEPTABLE = "B"
    POOR = "C"
    REJECT = "D"


@dataclass
class QualityReport:
    score: float = 0.0
    level: QualityLevel = QualityLevel.REJECT
    dimensions: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class DataQualityEngine:
    """数据质量引擎 — 统一质量评估"""

    @staticmethod
    def aesthetic_score(image_path: str) -> float:
        """图像美学评分(0-10)"""
        try:
            img = Image.open(image_path)
            w, h = img.size
            # 基于分辨率+尺寸比+文件大小的快速评分
            resolution_score = min(10.0, (w * h) / (1024 * 1024) * 2)
            aspect_ratio = max(w, h) / max(min(w, h), 1)
            if 1.0 < aspect_ratio < 2.0:
                ratio_score = 8.0
            elif 2.0 < aspect_ratio < 3.0:
                ratio_score = 6.0
            else:
                ratio_score = 4.0
            # 文件大小(大文件一般质量更高)
            size_mb = os.path.getsize(image_path) / (1024 * 1024)
            size_score = min(5.0, size_mb * 2)
            score = (resolution_score * 0.3 + ratio_score * 0.3 + size_score * 0.4)
            return round(min(10.0, score), 1)
        except Exception as e:
            return 0.0

    @staticmethod
    def check_resolution(image_path: str, min_w: int = 512, min_h: int = 512) -> Dict:
        """检查分辨率是否达标"""
        try:
            img = Image.open(image_path)
            w, h = img.size
            return {
                "width": w, "height": h,
                "passed": w >= min_w and h >= min_h,
                "megapixels": round(w * h / 1_000_000, 2),
            }
        except Exception as e:
            return {"width": 0, "height": 0, "passed": False, "error": str(e)}

    @staticmethod
    def dedup_hash(image_path: str, hash_size: int = 8) -> str:
        """感知哈希去重"""
        try:
            img = Image.open(image_path).convert("L").resize((hash_size + 1, hash_size))
            diff = []
            for row in range(hash_size):
                for col in range(hash_size):
                    left = img.getpixel((col, row))
                    right = img.getpixel((col + 1, row))
                    diff.append("1" if left > right else "0")
            hex_val = hex(int("".join(diff), 2))[2:]
            return hex_val.zfill(16)
        except:
            return ""

    @staticmethod
    def nsfw_check(image_path: str) -> Dict[str, float]:
        """NSFW检测(基于图像统计)"""
        try:
            img = Image.open(image_path).convert("RGB")
            pixels = list(img.getdata())
            # 肤色像素比例(粗略估计)
            skin_count = sum(1 for r, g, b in pixels if r > 60 and g < 200 and b < 200)
            skin_ratio = skin_count / len(pixels)
            return {
                "skin_ratio": round(skin_ratio, 3),
                "nsfw_probability": round(min(1.0, skin_ratio * 3), 2),
                "safe": skin_ratio < 0.2,
            }
        except:
            return {"nsfw_probability": 0.0, "safe": True}

    def evaluate_image(self, image_path: str, min_resolution: int = 512) -> QualityReport:
        """完整图片质量评估"""
        issues = []
        suggestions = []
        dimensions = {}
        score = 0.0

        # 分辨率检查
        res = self.check_resolution(image_path, min_resolution, min_resolution)
        dimensions["resolution"] = res["megapixels"]
        if not res["passed"]:
            issues.append(f"分辨率不足: {res['width']}x{res['height']}")
            suggestions.append(f"建议分辨率≥{min_resolution}x{min_resolution}")
        else:
            score += 3.0

        # 美学评分
        aesthetic = self.aesthetic_score(image_path)
        dimensions["aesthetic"] = aesthetic
        if aesthetic >= 7.0:
            score += 4.0
        elif aesthetic >= 5.0:
            score += 2.0
        else:
            issues.append(f"美学评分低: {aesthetic}")
            suggestions.append("建议提高画质/构图")

        # NSFW检查
        nsfw = self.nsfw_check(image_path)
        dimensions["nsfw"] = nsfw["nsfw_probability"]
        if not nsfw["safe"]:
            issues.append("可能包含不安全内容")
        else:
            score += 3.0

        # 总评分
        total = min(10.0, score)
        if total >= 8.0:
            level = QualityLevel.EXCELLENT
        elif total >= 6.0:
            level = QualityLevel.GOOD
        elif total >= 4.0:
            level = QualityLevel.ACCEPTABLE
        else:
            level = QualityLevel.POOR

        return QualityReport(
            score=total, level=level,
            dimensions=dimensions, issues=issues,
            suggestions=suggestions,
        )

    def evaluate_video(self, video_path: str) -> QualityReport:
        """视频质量评估(基于ffmpeg)"""
        issues = []
        score = 5.0  # 基础分
        try:
            import subprocess
            r = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", video_path
            ], capture_output=True, text=True, timeout=30)
            data = json.loads(r.stdout)
            streams = data.get("streams", [])
            video_streams = [s for s in streams if s["codec_type"] == "video"]
            if video_streams:
                vs = video_streams[0]
                w, h = int(vs.get("width", 0)), int(vs.get("height", 0))
                fps = eval(vs.get("avg_frame_rate", "0/1"))
                duration = float(data.get("format", {}).get("duration", 0))
                if w >= 720:
                    score += 2.0
                else:
                    issues.append(f"分辨率低: {w}x{h}")
                if fps >= 24:
                    score += 1.0
                else:
                    issues.append(f"帧率低: {fps}fps")
                if duration >= 2.0:
                    score += 1.0
                else:
                    issues.append(f"时长太短: {duration}s")
            else:
                issues.append("无视频流")
        except Exception as e:
            issues.append(f"无法分析: {e}")

        total = min(10.0, score)
        return QualityReport(
            score=total,
            level=QualityLevel.GOOD if total >= 6.0 else QualityLevel.ACCEPTABLE,
            dimensions={"score": total},
            issues=issues,
        )


class DataFormatConverter:
    """数据格式转换工具"""

    @staticmethod
    def to_coco(images: List[Dict], annotations: List[Dict], output_path: str):
        """转换为COCO JSON格式"""
        coco = {
            "images": [{"id": i, "file_name": img["path"],
                        "width": img.get("w", 0), "height": img.get("h", 0)}
                       for i, img in enumerate(images)],
            "annotations": [{"id": i, "image_id": ann["image_id"],
                            "category_id": ann.get("cat_id", 0),
                            "bbox": ann.get("bbox", [0, 0, 0, 0]),
                            "caption": ann.get("caption", "")}
                           for i, ann in enumerate(annotations)],
            "categories": [{"id": 0, "name": "object"}],
        }
        with open(output_path, "w") as f:
            json.dump(coco, f, ensure_ascii=False)

    @staticmethod
    def to_webdataset(images: List[str], captions: List[str],
                       output_dir: str, shard_size: int = 1000):
        """转换为WebDataset格式(多tar包)"""
        import tarfile
        os.makedirs(output_dir, exist_ok=True)
        for shard_idx in range(0, len(images), shard_size):
            shard_path = os.path.join(output_dir, f"shard-{shard_idx:06d}.tar")
            batch_images = images[shard_idx:shard_idx + shard_size]
            batch_caps = captions[shard_idx:shard_idx + shard_size]
            with tarfile.open(shard_path, "w") as tar:
                for i, (img_path, cap) in enumerate(zip(batch_images, batch_caps)):
                    sample_id = f"{shard_idx + i:08d}"
                    if os.path.exists(img_path):
                        tar.add(img_path, arcname=f"{sample_id}.jpg")
                        # 添加caption
                        cap_bytes = cap.encode("utf-8")
                        cap_io = io.BytesIO(cap_bytes)
                        # tar不支持直接加bytes,写临时文件
                        cap_path = f"/tmp/{sample_id}.txt"
                        with open(cap_path, "w") as f:
                            f.write(cap)
                        tar.add(cap_path, arcname=f"{sample_id}.txt")
                        os.remove(cap_path)

    @staticmethod
    def to_parquet(records: List[Dict], output_path: str):
        """转换为Parquet格式"""
        try:
            import pandas as pd
            df = pd.DataFrame(records)
            df.to_parquet(output_path)
            return True
        except ImportError:
            # fallback to JSON
            with open(output_path.replace(".parquet", ".json"), "w") as f:
                json.dump(records, f, ensure_ascii=False)
            return False
