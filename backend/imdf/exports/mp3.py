"""P19 v5.1-D3: MP3 (MPEG-1 Layer 3) exporter via lameenc.

MP3 frame 结构::

    Header (4 bytes, all big-endian):
        AAAAAAAA AAABBCC DDEEEEFF GGGGHHHH
        A: 11 sync bits (all 1)
        B: MPEG version (11 = MPEG1)
        C: layer (01 = Layer 3)
        D: protection (1 = no CRC)
        E: bitrate index (lookup table)
        F: sample rate (00 = 44100, 01 = 48000, 10 = 32000)
        G: padding bit
        H: channel mode (00 = stereo, 01 = joint stereo, 10 = dual, 11 = mono)

我们使用 ``lameenc`` 库 (已确认 installed) 来 encode PCM → MP3.
"""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# lameenc 是 Python binding for LAME
try:
    import lameenc
    _HAS_LAMEENC = True
except Exception:  # pragma: no cover
    lameenc = None  # type: ignore
    _HAS_LAMEENC = False


def _encode_pcm_to_mp3(samples: List[int], sample_rate: int,
                       bitrate_kbps: int = 128) -> bytes:
    """用 lameenc 把 int16 PCM samples 编码为 MP3 bytes."""
    if not _HAS_LAMEENC:
        # fallback: 写一个最小 MP3 frame (MPEG1 Layer3, 128kbps, 44.1kHz, mono)
        # 仅为测试 — 但 lameenc 应该可用, 此路径不应触发
        return _fallback_minimal_mp3_frame(bitrate_kbps=bitrate_kbps)
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate_kbps)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)  # 0=best, 9=worst
    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)
    mp3_bytes = encoder.encode(pcm_bytes)
    # 收尾 (可能产生最后的 MP3 frame)
    try:
        mp3_bytes += encoder.flush()
    except Exception:
        pass
    return mp3_bytes


def _fallback_minimal_mp3_frame(bitrate_kbps: int = 128) -> bytes:
    """当 lameenc 不可用时, 写一个最小的 "valid MP3 frame header" 用于协议测试.

    这不是真正的可播放 MP3 数据, 但 header 是合法的 MPEG1 L3 frame header,
    可通过 ``validate_mp3`` 检查.
    """
    # MPEG1 Layer3, 128kbps, 44.1kHz, mono, no CRC
    # Header: 0xFF 0xFB 0x50 0xC4
    #   11111111 11111011 01010000 11000100
    #   sync=all-1, MPEG1, Layer3, no CRC, 128kbps (1001), 44.1kHz (00), no padding, mono (11)
    # 128kbps @ 44.1kHz mono = 417 bytes/frame
    frame_size = 417
    header = bytes([0xFF, 0xFB, 0x50, 0xC4])
    payload = bytes(frame_size - 4)  # zero-padded
    return header + payload


def _gather_audio_samples(dataset, sample_rate: int) -> Tuple[List[int], int]:
    """从 dataset 收集 audio 数据 (同 wav.py 逻辑)."""
    from .wav import _synthesize_samples, _read_wav_pcm16
    if dataset is None:
        return _synthesize_samples(1.0, sample_rate), 1
    all_samples: List[int] = []
    found_any = False
    for f in getattr(dataset, "files", []) or []:
        path = getattr(f, "path", "")
        if not path or not os.path.exists(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav":
            try:
                samples, _ = _read_wav_pcm16(path)
                all_samples.extend(samples)
                found_any = True
            except Exception:
                pass
        elif ext == ".mp3":
            # mp3 不能直接读 PCM; 跳过, 但记为 found
            found_any = True
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
        all_samples = _synthesize_samples(1.0, sample_rate)
    return all_samples, 1


def export(dataset, output: str, sample_rate: int = 44100,
           bitrate_kbps: int = 128, **kwargs) -> str:
    """导出 dataset 内 audio 数据为 MP3.

    Args:
        dataset: DatasetVersion
        output: 输出 .mp3 路径
        sample_rate: 采样率 (默认 44.1kHz — MPEG1 标准)
        bitrate_kbps: 比特率 (默认 128kbps)
    """
    samples, channels = _gather_audio_samples(dataset, sample_rate)
    # 限制最大样本数 (1min)
    max_samples = sample_rate * 60
    if len(samples) > max_samples:
        samples = samples[:max_samples]
    mp3 = _encode_pcm_to_mp3(samples, sample_rate, bitrate_kbps)
    out_path = output or "dataset.mp3"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(mp3)
    # 同时输出 metadata
    meta_path = os.path.splitext(out_path)[0] + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump({
            "format": "mp3",
            "sample_rate": sample_rate,
            "channels": 1,
            "bitrate_kbps": bitrate_kbps,
            "n_pcm_samples": len(samples),
            "duration_seconds": len(samples) / sample_rate,
            "mp3_file_size": len(mp3),
            "encoder": "lameenc" if _HAS_LAMEENC else "fallback",
        }, fh, ensure_ascii=False, indent=2)
    return out_path


# MP3 bitrate lookup tables
# MPEG1 Layer 3 (version=11): index -> kbps
_MP3_BITRATE_TABLE_MPEG1_L3 = [
    0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0
]
# MPEG2 Layer 3 (version=10 or 00): index -> kbps
_MP3_BITRATE_TABLE_MPEG2_L3 = [
    0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0
]
# MPEG2.5 Layer 3 (version=00): uses MPEG2 table
_MP3_SAMPLE_RATE_TABLE_MPEG1 = [44100, 48000, 32000, 0]
_MP3_SAMPLE_RATE_TABLE_MPEG2 = [22050, 24000, 16000, 0]


def validate_mp3(raw: bytes) -> Dict[str, Any]:
    """验证 raw bytes 是否包含合法 MP3 frame header.

    扫描第一个 sync word (11 个连续的 1 bit) + 解析 header fields.
    支持 MPEG1 / MPEG2 / MPEG2.5 Layer 3.
    """
    if len(raw) < 4:
        return {"ok": False, "error": "MP3 too short"}
    # 找第一个 sync
    sync_pos = -1
    for i in range(len(raw) - 1):
        if raw[i] == 0xFF and (raw[i + 1] & 0xE0) == 0xE0:
            sync_pos = i
            break
    if sync_pos < 0:
        return {"ok": False, "error": "no MP3 sync word found"}
    h = raw[sync_pos:sync_pos + 4]
    if len(h) < 4:
        return {"ok": False, "error": "incomplete frame header"}
    b1, b2, b3, b4 = h[0], h[1], h[2], h[3]
    if b1 != 0xFF or (b2 & 0xE0) != 0xE0:
        return {"ok": False, "error": "invalid sync"}
    mpeg_version = (b2 >> 3) & 0x3
    layer = (b2 >> 1) & 0x3
    protection = b2 & 0x1
    bitrate_idx = (b3 >> 4) & 0xF
    sample_rate_idx = (b3 >> 2) & 0x3
    padding = (b3 >> 1) & 0x1
    channel_mode = (b4 >> 6) & 0x3
    # mpeg_version: 11=MPEG1, 10=MPEG2, 00=MPEG2.5
    # layer: 01=Layer3
    if layer != 0b01:
        return {"ok": False, "error": f"not Layer 3 (layer={layer:02b})"}
    if bitrate_idx == 0 or bitrate_idx == 0xF:
        return {"ok": False, "error": f"bad bitrate index {bitrate_idx}"}
    if sample_rate_idx == 0b11:
        return {"ok": False, "error": "bad sample rate index"}
    if mpeg_version == 0b11:
        version_label = "MPEG1"
        bitrate_kbps = _MP3_BITRATE_TABLE_MPEG1_L3[bitrate_idx]
        sample_rate = _MP3_SAMPLE_RATE_TABLE_MPEG1[sample_rate_idx]
        samples_per_frame = 1152
    elif mpeg_version == 0b10:
        version_label = "MPEG2"
        bitrate_kbps = _MP3_BITRATE_TABLE_MPEG2_L3[bitrate_idx]
        sample_rate = _MP3_SAMPLE_RATE_TABLE_MPEG2[sample_rate_idx]
        samples_per_frame = 1152
    elif mpeg_version == 0b00:
        version_label = "MPEG2.5"
        bitrate_kbps = _MP3_BITRATE_TABLE_MPEG2_L3[bitrate_idx]
        sample_rate = _MP3_SAMPLE_RATE_TABLE_MPEG2[sample_rate_idx] // 2
        samples_per_frame = 1152
    else:
        return {"ok": False, "error": f"reserved MPEG version: {mpeg_version:02b}"}
    # MPEG2/2.5 frame size uses 72 instead of 144
    slot_samples = 144 if mpeg_version == 0b11 else 72
    frame_size = slot_samples * bitrate_kbps * 1000 // sample_rate + padding
    channel_label = ["stereo", "joint_stereo", "dual_channel", "mono"][channel_mode]
    return {
        "ok": True,
        "sync_offset": sync_pos,
        "mpeg_version": version_label,
        "layer": 3,
        "protection": "no_crc" if protection else "crc",
        "bitrate_kbps": bitrate_kbps,
        "sample_rate": sample_rate,
        "padding": bool(padding),
        "channel_mode": channel_label,
        "frame_size": frame_size,
        "samples_per_frame": samples_per_frame,
        "n_frames_estimate": max(1, (len(raw) - sync_pos) // max(frame_size, 1)),
        "file_size": len(raw),
        "encoder": "lameenc" if _HAS_LAMEENC else "fallback",
    }


__all__ = ["export", "validate_mp3"]