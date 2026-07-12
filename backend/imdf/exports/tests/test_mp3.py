"""Tests for MP3 exporter."""
import os
import tempfile
import unittest
from pathlib import Path

from exports.mp3 import export, validate_mp3, _HAS_LAMEENC


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


class TestMP3Export(unittest.TestCase):
    def test_mp3_basic_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "audio.mp3")
            written = export(ds, out, sample_rate=44100, bitrate_kbps=128)
            raw = Path(written).read_bytes()
            result = validate_mp3(raw)
            self.assertTrue(result["ok"], msg=result)
            self.assertEqual(result["mpeg_version"], "MPEG1")
            self.assertEqual(result["layer"], 3)
            self.assertEqual(result["bitrate_kbps"], 128)
            self.assertEqual(result["channel_mode"], "mono")

    def test_mp3_10s_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "10s.mp3")
            export(ds, out, sample_rate=44100, duration_seconds=10.0)
            raw = Path(out).read_bytes()
            result = validate_mp3(raw)
            self.assertTrue(result["ok"])
            # lameenc produces multiple MP3 frames for 10s of audio
            self.assertGreater(result["file_size"], 1000)

    def test_mp3_metadata_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "x.mp3")
            export(ds, out)
            meta = os.path.join(tmp, "x.meta.json")
            self.assertTrue(os.path.exists(meta))
            import json
            meta_doc = json.loads(Path(meta).read_text(encoding="utf-8"))
            self.assertEqual(meta_doc["format"], "mp3")
            self.assertIn("encoder", meta_doc)
            if _HAS_LAMEENC:
                self.assertEqual(meta_doc["encoder"], "lameenc")

    def test_validate_corrupt_bytes(self):
        bad = b"NOTMP3" * 100
        result = validate_mp3(bad)
        self.assertFalse(result["ok"])

    def test_mp3_mpeg2_acceptable(self):
        """MP3 MPEG2 Layer 3 64kbps @ 22050Hz mono — we should accept that."""
        # Header: AAABBCCD EEEEFFGG GGGGHHHH (big-endian)
        # A = 111 (sync)
        # B = 10 (MPEG2)
        # C = 01 (Layer 3)
        # D = 1 (no CRC)
        # → b2 = 111_10_01_1 = 0b11110011 = 0xF3
        # E = 1000 (bitrate_idx=8, 64kbps MPEG2 L3)
        # F = 00 (sample_rate_idx=0, 22050 Hz MPEG2)
        # G = 0 (no padding)
        # → b3 = 1000_00_0 = 0b10000000 = 0x80
        # H = 11 (mono)
        # → b4 = 0b11000000 = 0xC0
        hdr = bytes([0xFF, 0xF3, 0x80, 0xC0])
        # frame size for MPEG2 L3 = 72 * 64000 / 22050 + 0 = 209 bytes
        frame_size = 72 * 64 * 1000 // 22050
        payload = bytes(frame_size - 4)
        raw = hdr + payload
        result = validate_mp3(raw)
        self.assertTrue(result["ok"], msg=result)
        self.assertEqual(result["mpeg_version"], "MPEG2")
        self.assertEqual(result["bitrate_kbps"], 64)
        self.assertEqual(result["sample_rate"], 22050)
        self.assertEqual(result["channel_mode"], "mono")


if __name__ == "__main__":
    unittest.main()