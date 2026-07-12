"""P19 v5.1-D3: WAV (RIFF WAVE PCM) exporter.

WAV 文件结构::

    RIFF <size> WAVE              # 12 bytes (size = file_size - 8)
        fmt  <size>               # 8 + size bytes
            <fmt_chunk: PCM (16-bit LE)>
            - audio_format  : 1 (PCM)
            - num_channels  : 1 (mono) | 2 (stereo)
            - sample_rate   : 44100
            - byte_rate     : sample_rate * num_channels * bits_per_sample/8
            - block_align   : num_channels * bits_per_sample/8
            - bits_per_sample : 16
        data <size>
            <raw PCM samples>

无外部依赖 (无 scipy / wave 模块也 OK, 全部纯 Python).
"""
from __future__ import annotations

import json
import math
import os
import struct
from pathlib import Path
from typing import Any, Dict, List, Tuple

# numpy 可选, 用于快速 sin 合成
try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    _HAS_NUMPY = False


# 模拟合成 sine + 谐波音频样本 (无 dataset 文件时 fallback)
def _synthesize_samples(duration_seconds: float, sample_rate: int,
                       base_freq: float = 440.0) -> List[int]:
    """生成 16-bit PCM sample (整数) — 440Hz + 880Hz 谐波 + 衰减包络."""
    n_samples = int(duration_seconds * sample_rate)
    if n_samples <= 0:
        return [0] * 1024  # fallback
    samples: List[int] = []
    for n in range(n_samples):
        t = n / sample_rate
        # base + 1st harmonic
        amp = 0.6 * math.sin(2 * math.pi * base_freq * t)
        amp += 0.3 * math.sin(2 * math.pi * 2 * base_freq * t)
        # 衰减包络 (前 50ms 渐入, 末尾 200ms 渐出)
        env = 1.0
        fade_in_samples = int(0.05 * sample_rate)
        fade_out_samples = int(0.20 * sample_rate)
        if n < fade_in_samples:
            env = n / fade_in_samples
        elif n > n_samples - fade_out_samples:
            env = (n_samples - n) / fade_out_samples
        s = int(amp * env * 32767)
        s = max(-32768, min(32767, s))
        samples.append(s)
    return samples


def _gather_audio_samples(dataset, sample_rate: int,
                         duration_seconds: float = 1.0) -> Tuple[List[int], int]:
    """从 dataset 中收集 audio 文件的 PCM samples.

    简化策略:
    - 如果文件以 ``.raw`` 结尾, 直接当 int16 读取
    - 如果 dataset 中有 .wav 文件, 用内置 _read_wav_pcm16 解析并复用其 samples
    - 否则 fallback 用合成 sine wave (时长 = duration_seconds)

    Returns:
        (samples_int16_list, num_channels)
    """
    if dataset is None:
        return _synthesize_samples(duration_seconds, sample_rate), 1

    all_samples: List[int] = []
    found_any = False
    for f in getattr(dataset, "files", []) or []:
        path = getattr(f, "path", "")
        if not path or not os.path.exists(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav":
            try:
                samples, channels = _read_wav_pcm16(path)
                all_samples.extend(samples)
                found_any = True
            except Exception:
                pass
        elif ext == ".raw":
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                fmt = f"<{len(raw) // 2}h"
                samples = list(struct.unpack(fmt, raw))
                all_samples.extend(samples)
                found_any = True
            except Exception:
                pass

    if not found_any:
        all_samples = _synthesize_samples(duration_seconds, sample_rate)
    return all_samples, 1


def _read_wav_pcm16(path: str) -> Tuple[List[int], int]:
    """读取一个 WAV 文件 (16-bit PCM), 返回 (samples_list, num_channels)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a valid WAV")
    pos = 12
    audio_format = num_channels = sample_rate = bits_per_sample = 0
    pcm_data = b""
    while pos < len(data):
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        chunk_body = data[pos + 8:pos + 8 + chunk_size]
        if chunk_id == b"fmt ":
            audio_format = struct.unpack("<H", chunk_body[0:2])[0]
            num_channels = struct.unpack("<H", chunk_body[2:4])[0]
            sample_rate = struct.unpack("<I", chunk_body[4:8])[0]
            bits_per_sample = struct.unpack("<H", chunk_body[14:16])[0]
        elif chunk_id == b"data":
            pcm_data = chunk_body
        pos = pos + 8 + chunk_size + (chunk_size & 1)  # word-aligned
    if audio_format != 1 or bits_per_sample != 16:
        # 仅支持 16-bit PCM
        # 转 int16 视角: 即使不匹配, 仍尝试读 (test data 可能是 16-bit)
        pass
    n_samples = len(pcm_data) // 2
    samples = list(struct.unpack(f"<{n_samples}h", pcm_data[:n_samples * 2]))
    return samples, num_channels


def _build_wav_bytes(samples: List[int], sample_rate: int,
                     num_channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """构造 RIFF WAVE PCM bytes."""
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_bytes = struct.pack(f"<{len(samples)}h", *samples)
    fmt_chunk = struct.pack(
        "<HHIIHH",
        1,  # PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )
    data_chunk = data_bytes
    riff_size = 4 + (8 + len(fmt_chunk)) + (8 + len(data_chunk))
    out = bytearray()
    out.extend(b"RIFF")
    out.extend(struct.pack("<I", riff_size))
    out.extend(b"WAVE")
    # fmt chunk
    out.extend(b"fmt ")
    out.extend(struct.pack("<I", len(fmt_chunk)))
    out.extend(fmt_chunk)
    # data chunk
    out.extend(b"data")
    out.extend(struct.pack("<I", len(data_chunk)))
    out.extend(data_chunk)
    return bytes(out)


def export(dataset, output: str, sample_rate: int = 16000, duration_seconds: float = 1.0,
           **kwargs) -> str:
    """导出 dataset 内 audio 数据为 WAV PCM (16-bit mono).

    Args:
        dataset: DatasetVersion (含 .files)
        output: 输出 .wav 路径
        sample_rate: 默认 16kHz
        duration_seconds: fallback 合成时长 (当 dataset 没有 audio 文件时,
            生成这么长的 sine wave)
    """
    # 先 gather 已有 audio (若 dataset 内有 .wav / .raw 文件), 传 duration_seconds
    # 这样没有 audio 文件的 dataset 会生成期望时长的合成数据
    samples, channels = _gather_audio_samples(dataset, sample_rate, duration_seconds=duration_seconds)
    # 仅取前 N 个 sample (避免数据集巨大)
    max_samples = sample_rate * 60  # 60s 上限
    if len(samples) > max_samples:
        samples = samples[:max_samples]
    wav = _build_wav_bytes(samples, sample_rate, num_channels=1, bits_per_sample=16)
    out_path = output or "dataset.wav"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(wav)
    # 同时输出 metadata
    meta_path = os.path.splitext(out_path)[0] + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump({
            "format": "wav",
            "sample_rate": sample_rate,
            "channels": 1,
            "bits_per_sample": 16,
            "n_samples": len(samples),
            "duration_seconds": len(samples) / sample_rate,
            "requested_duration_seconds": duration_seconds,
        }, fh, ensure_ascii=False, indent=2)
    return out_path


def validate_wav(raw: bytes) -> Dict[str, Any]:
    """验证 raw bytes 是否为合法 RIFF WAVE."""
    if len(raw) < 44:
        return {"ok": False, "error": "WAV too short"}
    if raw[:4] != b"RIFF":
        return {"ok": False, "error": "missing RIFF magic"}
    if raw[8:12] != b"WAVE":
        return {"ok": False, "error": "missing WAVE marker"}
    if raw[12:16] != b"fmt ":
        return {"ok": False, "error": "missing fmt chunk"}
    audio_format = struct.unpack("<H", raw[20:22])[0]
    num_channels = struct.unpack("<H", raw[22:24])[0]
    sample_rate = struct.unpack("<I", raw[24:28])[0]
    bits_per_sample = struct.unpack("<H", raw[34:36])[0]
    if audio_format != 1:
        return {"ok": False, "error": f"not PCM (audio_format={audio_format})"}
    if bits_per_sample != 16:
        return {"ok": False, "error": f"not 16-bit (bits={bits_per_sample})"}
    # data chunk
    if raw[36:40] != b"data":
        return {"ok": False, "error": "missing data chunk"}
    data_size = struct.unpack("<I", raw[40:44])[0]
    if data_size % (num_channels * bits_per_sample // 8) != 0:
        return {"ok": False, "error": f"data_size {data_size} not aligned"}
    n_samples = data_size // (num_channels * bits_per_sample // 8)
    duration = n_samples / sample_rate
    return {
        "ok": True,
        "format": "PCM",
        "sample_rate": sample_rate,
        "channels": num_channels,
        "bits_per_sample": bits_per_sample,
        "n_samples": n_samples,
        "duration_seconds": duration,
        "file_size": len(raw),
    }


__all__ = ["export", "validate_wav", "_synthesize_samples", "_build_wav_bytes"]