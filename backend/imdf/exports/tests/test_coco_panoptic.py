"""Tests for COCO Panoptic exporter."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from exports.coco_panoptic import export, validate_coco_panoptic


class _MockFile:
    def __init__(self, name: str, modality_id: str = ""):
        self.path = os.path.join("/fake", name)
        self.modality_id = modality_id
        self.size = 0
        self.hash = "deadbeef"


class _MockDataset:
    def __init__(self, files):
        self.files = files
        self.version = "v_test"


class TestCOCOPanopticExport(unittest.TestCase):
    def test_basic_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = [_MockFile(f"img_{i:06d}.jpg") for i in range(5)]
            ds = _MockDataset(files)
            out = os.path.join(tmp, "panoptic.json")
            written = export(ds, out)
            doc = json.loads(Path(written).read_text(encoding="utf-8"))
            result = validate_coco_panoptic(doc)
            self.assertTrue(result["ok"], msg=result)
            self.assertEqual(result["n_images"], 5)
            self.assertEqual(result["n_annotations"], 5)
            self.assertGreater(result["total_segments"], 0)
            self.assertGreater(result["n_thing_classes"], 0)
            self.assertGreater(result["n_stuff_classes"], 0)

    def test_png_masks_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = [_MockFile(f"img_{i:06d}.jpg") for i in range(3)]
            ds = _MockDataset(files)
            out = os.path.join(tmp, "pan.json")
            export(ds, out)
            masks_dir = os.path.join(tmp, "pan_masks")
            self.assertTrue(os.path.isdir(masks_dir))
            masks = list(Path(masks_dir).glob("*.png"))
            self.assertEqual(len(masks), 3)
            # 每个 PNG 应当 >= 67 bytes (最小有效 PNG)
            for m in masks:
                self.assertGreater(m.stat().st_size, 50)

    def test_panoptic_100_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = [_MockFile(f"img_{i:06d}.jpg") for i in range(100)]
            ds = _MockDataset(files)
            out = os.path.join(tmp, "pan100.json")
            written = export(ds, out, image_width=32, image_height=32)
            doc = json.loads(Path(written).read_text(encoding="utf-8"))
            result = validate_coco_panoptic(doc)
            self.assertEqual(result["n_images"], 100)


if __name__ == "__main__":
    unittest.main()