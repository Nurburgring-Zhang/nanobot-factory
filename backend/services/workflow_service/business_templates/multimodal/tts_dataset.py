"""P3-6.5-W2: Hybrid Multimodal — TTS Training Dataset.

TTS training dataset pipeline: collect audio transcripts -> speaker
embedding -> quality filter -> phoneme alignment -> metadata export.

Category: multimodal
Improvements over existing tts_dataset (legacy):
  * Multi-speaker support (per-speaker metadata)
  * Phoneme-level alignment (forced alignment via Montreal Forced Aligner)
  * Quality dimensions: SNR, VAD ratio, MOS estimate
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-mm-h05",
    "category": "multimodal",
    "name": "TTS Training Dataset Pipeline (Hybrid)",
    "tags": ["tts", "audio", "multi-speaker", "phoneme-alignment"],
    "description": (
        "TTS training dataset: collect audio transcripts (multi-speaker) "
        "-> speaker embedding (Resemblyzer) -> quality filter (SNR/VAD/MOS) "
        "-> Montreal forced alignment (phoneme + word timestamps) -> "
        "LJSpeech-style metadata export."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "audio_sources": {"type": "array<object>", "required": True,
                                "description": "[{path, speaker_id, "
                                                "transcript, language}]"},
            "speaker_encoder": {"type": "string",
                                   "default": "resemblyzer"},
            "aligner": {"type": "string",
                          "default": "mfa",
                          "enum": ["mfa", "whisperx", "wav2vec2"]},
            "min_snr_db": {"type": "float", "default": 20.0,
                            "min": 0.0, "max": 60.0},
            "min_vad_ratio": {"type": "float", "default": 0.6,
                               "min": 0.0, "max": 1.0},
            "min_mos_estimate": {"type": "float", "default": 3.5,
                                  "min": 1.0, "max": 5.0},
            "oss_bucket": {"type": "string", "default": "tts-data"},
        },
        outputs=["metadata.csv", "speaker_embeddings.npy",
                 "alignments/*.TextGrid", "stats.json"],
        steps=[
            {"id": "col", "name": "Audio Collect",
             "operator": "collection.audio_source",
             "config": {"sources": "$inputs.audio_sources"}},
            {"id": "spk", "name": "Speaker Embedding",
             "operator": "audio.speaker_embed",
             "config": {"model": "$inputs.speaker_encoder"}},
            {"id": "qf", "name": "Quality Filter (SNR/VAD/MOS)",
             "operator": "cleaning.audio_quality",
             "config": {"min_snr_db": "$inputs.min_snr_db",
                        "min_vad_ratio": "$inputs.min_vad_ratio",
                        "min_mos": "$inputs.min_mos_estimate"}},
            {"id": "al", "name": "Forced Alignment",
             "operator": "audio.forced_align",
             "config": {"aligner": "$inputs.aligner"}},
            {"id": "ph", "name": "Phoneme Extraction",
             "operator": "audio.phoneme_extract"},
            {"id": "md", "name": "Metadata Export",
             "operator": "export.write_tts_metadata",
             "config": {"format": "ljspeech_with_speaker"}},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["clips", "speakers", "after_quality",
                 "phoneme_aligned", "duration_seconds"],
    ),
    "nodes": [_n("col", "audio_collect", "collection"),
              _n("spk", "speaker_embed", "audio", "col"),
              _n("qf", "audio_quality", "cleaning", "spk"),
              _n("al", "forced_align", "audio", "qf"),
              _n("ph", "phoneme_extract", "audio", "al"),
              _n("md", "write_metadata", "export", "ph"),
              _n("up", "oss_upload", "export", "md")],
}