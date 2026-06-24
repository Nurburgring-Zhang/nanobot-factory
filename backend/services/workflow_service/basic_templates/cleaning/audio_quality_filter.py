"""Cleaning template: Audio quality filter (音频质量过滤).

Pipeline:
  1.  probe         - ffprobe / soxi 元数据
  2.  vad           - 语音活动检测 (silero-vad)
  3.  snr           - 信噪比估计
  4.  clip_detect   - 削波检测
  5.  denoise       - 可选 denoise (RNNoise/DeepFilter)
  6.  resample      - 重采样到目标 SR
  7.  filter        - 综合阈值丢弃
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-cln-004",
    "name": "Audio Quality Filter (音频质量过滤)",
    "category": "cleaning",
    "description": (
        "VAD + SNR + 削波检测 + 可选降噪 + 重采样, 综合阈值过滤低质量音频。"
    ),
    "tags": ["audio", "cleaning", "vad", "snr"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "target_sample_rate": {"type": "int", "default": 16000},
        "min_duration_sec": {"type": "float", "default": 0.5},
        "max_duration_sec": {"type": "float", "default": 60.0},
        "min_snr_db": {"type": "float", "default": 15.0},
        "min_speech_ratio": {"type": "float", "default": 0.3},
        "enable_denoise": {"type": "bool", "default": False},
        "oss_bucket": {"type": "string", "default": "cleaned-audio"},
    },
    "outputs": ["clean_manifest.jsonl", "stats.json"],
    "steps": [
        {"id": "probe", "name": "Audio Probe",
         "operator": "audio.probe",
         "config": {"fields": ["duration", "sample_rate", "channels",
                                "bit_depth", "codec"]}},
        {"id": "vad", "name": "VAD",
         "operator": "audio.vad",
         "config": {"model": "silero-vad",
                    "threshold": 0.5}},
        {"id": "snr", "name": "SNR Estimate",
         "operator": "audio.snr",
         "config": {"method": "energy-ratio"}},
        {"id": "clip", "name": "Clip Detect",
         "operator": "audio.clip_detect",
         "config": {"threshold": 0.99}},
        {"id": "dn", "name": "Denoise",
         "operator": "audio.denoise",
         "config": {"enabled": "$inputs.enable_denoise",
                    "model": "deepfilter"}},
        {"id": "rs", "name": "Resample",
         "operator": "audio.resample",
         "config": {"target_sr": "$inputs.target_sample_rate",
                    "channels": 1}},
        {"id": "flt", "name": "Filter",
         "operator": "audio.composite_filter",
         "config": {"min_dur": "$inputs.min_duration_sec",
                    "max_dur": "$inputs.max_duration_sec",
                    "min_snr_db": "$inputs.min_snr_db",
                    "min_speech_ratio": "$inputs.min_speech_ratio"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "cleaning/audio_quality/",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total", "drop_by_reason",
                "total_duration_hours", "duration_seconds"],
}


__all__ = ["TEMPLATE"]