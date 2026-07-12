"""Tests for WAV exporter."""
import os
import tempfile
import unittest
from pathlib import Path

from exports.wav import export, validate_wav, _synthesize_samples, _build_wav_bytes


class _MockFile:
    def __init__(self, path: str):
        self.path = path
        self.modality_id = "audio"
        self.size = 0
        self.hash = "deadbeef"


class _MockDataset:
    def __init__(self, files):
        self.files = files
        self.version = "v_test"


class TestWAVExport(unittest.TestCase):
    def test_wav_basic_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "audio.wav")
            written = export(ds, out, sample_rate=16000, duration_seconds=1.0)
            raw = Path(written).read_bytes()
            result = validate_wav(raw)
            self.assertTrue(result["ok"], msg=result)
            self.assertEqual(result["format"], "PCM")
            self.assertEqual(result["channels"], 1)
            self.assertEqual(result["bits_per_sample"], 16)
            self.assertEqual(result["sample_rate"], 16000)
            self.assertGreater(result["n_samples"], 0)

    def test_wav_10s_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "10s.wav")
            export(ds, out, sample_rate=8000, duration_seconds=10.0)
            raw = Path(out).read_bytes()
            result = validate_wav(raw)
            self.assertTrue(result["ok"])
            self.assertAlmostEqual(result["duration_seconds"], 10.0, delta=0.01)

    def test_wav_synthesize(self):
        samples = _synthesize_samples(1.0, 16000)
        self.assertEqual(len(samples), 16000)
        # 检查波形在 [-32767, 32767]
        self.assertGreaterEqual(min(samples), -32768)
        self.assertLessEqual(max(samples), 32767)

    def test_wav_build_bytes(self):
        samples = _synthesize_samples(0.5, 8000)
        wav = _build_wav_bytes(samples, sample_rate=8000, num_channels=1, bits_per_sample=16)
        result = validate_wav(wav)
        self.assertTrue(result["ok"])

    def test_wav_metadata_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "x.wav")
            export(ds, out)
            meta = os.path.join(tmp, "x.meta.json")
            self.assertTrue(os.path.exists(meta))
            import json
            meta_doc = json.loads(Path(meta).read_text(encoding="utf-8"))
            self.assertEqual(meta_doc["format"], "wav")
            self.assertEqual(meta_doc["sample_rate"], 16000)


if __name__ == "__main__":
    unittest.main()