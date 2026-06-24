"""Cleaning template: Image standard clean (12-operator chain).

串联 12 个图像清洗算子:
  1.  format_check   - 解码 + 格式校验 (PNG/JPG/WEBP)
  2.  size_check     - 最小分辨率 / 长宽比
  3.  blur_detect    - Laplacian variance
  4.  nsfw_filter    - NSFW classifier
  5.  watermark_detect - 水印/Logo 检测
  6.  text_ocr_detect - OCR 检测 (可选丢弃含敏感文本)
  7.  dedup_phash    - pHash 全局去重
  8.  face_quality   - 面部质量 (可选)
  9.  color_stats    - 颜色直方图统计
  10. aesthetic_low  - 极低美学阈值丢弃
  11. exif_clean     - 去除 EXIF/GPS
  12. reencode       - 重编码到目标格式 + 质量
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-cln-001",
    "name": "Image Standard Clean (图像标准清洗 12 算子)",
    "category": "cleaning",
    "description": (
        "12 个图像清洗算子串联: 格式/分辨率/模糊/NSFW/水印/OCR/"
        "去重/人脸/颜色/美学/EXIF/重编码, 输出 manifest + 统计。"
    ),
    "tags": ["image", "cleaning", "nsfw", "dedup"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "min_resolution": {"type": "int", "default": 512},
        "max_aspect_ratio": {"type": "float", "default": 4.0},
        "blur_threshold": {"type": "float", "default": 50.0},
        "enable_nsfw": {"type": "bool", "default": True},
        "enable_watermark_detect": {"type": "bool", "default": True},
        "phash_threshold": {"type": "int", "default": 6},
        "target_format": {"type": "string", "default": "jpeg"},
        "jpeg_quality": {"type": "int", "default": 92},
        "oss_bucket": {"type": "string", "default": "cleaned-images"},
    },
    "outputs": ["clean_manifest.jsonl",
                "dropped_manifest.jsonl",
                "stats.json"],
    "steps": [
        {"id": "fmt", "name": "Format Check",
         "operator": "image.format_check",
         "config": {"allow": ["png", "jpeg", "webp", "bmp"]}},
        {"id": "sz", "name": "Size Check",
         "operator": "image.size_check",
         "config": {"min_side": "$inputs.min_resolution",
                    "max_aspect_ratio": "$inputs.max_aspect_ratio"}},
        {"id": "blur", "name": "Blur Detect",
         "operator": "image.blur_detect",
         "config": {"method": "laplacian_var",
                    "threshold": "$inputs.blur_threshold"}},
        {"id": "nsfw", "name": "NSFW Filter",
         "operator": "image.nsfw_classify",
         "config": {"enabled": "$inputs.enable_nsfw",
                    "threshold": 0.85}},
        {"id": "wm", "name": "Watermark Detect",
         "operator": "image.watermark_detect",
         "config": {"enabled": "$inputs.enable_watermark_detect",
                    "threshold": 0.7}},
        {"id": "ocr", "name": "OCR Sensitive Text",
         "operator": "image.ocr_detect",
         "config": {"enabled": False,
                    "denylist": []}},
        {"id": "ph", "name": "pHash Dedup",
         "operator": "image.phash_dedup",
         "config": {"hash_bits": 64,
                    "hamming_threshold": "$inputs.phash_threshold"}},
        {"id": "fq", "name": "Face Quality",
         "operator": "image.face_quality",
         "config": {"enabled": False, "min_score": 0.4}},
        {"id": "col", "name": "Color Stats",
         "operator": "image.color_stats",
         "config": {"histogram_bins": 32}},
        {"id": "aes", "name": "Aesthetic Low Drop",
         "operator": "image.aesthetic_score",
         "config": {"min_score": 0.2, "model": "laion-aes-v2"}},
        {"id": "exif", "name": "EXIF Clean",
         "operator": "image.strip_exif",
         "config": {"strip_gps": True, "strip_all": True}},
        {"id": "enc", "name": "Reencode",
         "operator": "image.reencode",
         "config": {"format": "$inputs.target_format",
                    "quality": "$inputs.jpeg_quality"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "cleaning/image_standard/",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total", "drop_by_reason",
                "duration_seconds", "throughput_img_per_sec"],
}


__all__ = ["TEMPLATE"]