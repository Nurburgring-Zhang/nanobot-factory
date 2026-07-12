"""Tests for glTF (JSON) exporter."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from exports.gltf import export, validate_gltf


class _MockFile:
    def __init__(self, path: str, modality_id: str = "three_d_pointcloud"):
        self.path = path
        self.modality_id = modality_id
        self.size = 0
        self.hash = "deadbeef"


class _MockDataset:
    def __init__(self, files):
        self.files = files
        self.version = "v_test"


def _make_obj(path: str, n_verts: int = 100) -> str:
    lines = ["# gltf test"]
    for i in range(n_verts):
        x = (i % 10) * 0.1
        y = ((i // 10) % 10) * 0.1
        z = (i // 100) * 0.1
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    if n_verts >= 3:
        lines.append("f 1 2 3")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


class TestGLTFExport(unittest.TestCase):
    def test_gltf_basic_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = _make_obj(os.path.join(tmp, "cube.obj"), n_verts=100)
            ds = _MockDataset([_MockFile(obj)])
            out = os.path.join(tmp, "out.gltf")
            written = export(ds, out)
            self.assertTrue(os.path.exists(written))
            raw = Path(written).read_text(encoding="utf-8")
            doc = json.loads(raw)
            result = validate_gltf(raw)
            self.assertTrue(result["ok"], msg=f"validate failed: {result}")
            self.assertEqual(result["asset_version"], "2.0")
            self.assertGreater(result["n_accessors"], 0)
            self.assertEqual(result["buffer_uri_kind"], "base64")

    def test_gltf_external_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = _make_obj(os.path.join(tmp, "cube.obj"), n_verts=100)
            ds = _MockDataset([_MockFile(obj)])
            out = os.path.join(tmp, "out.gltf")
            export(ds, out, embed_base64=False)
            raw = Path(out).read_text(encoding="utf-8")
            doc = json.loads(raw)
            uri = doc["buffers"][0]["uri"]
            self.assertFalse(uri.startswith("data:"))
            bin_path = os.path.join(tmp, "out.bin")
            self.assertTrue(os.path.exists(bin_path))
            result = validate_gltf(raw)
            self.assertEqual(result["buffer_uri_kind"], "external")

    def test_gltf_empty_dataset_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "fb.gltf")
            export(ds, out)
            raw = Path(out).read_text(encoding="utf-8")
            doc = json.loads(raw)
            self.assertIn("meshes", doc)
            self.assertGreater(len(doc["meshes"]), 0)


if __name__ == "__main__":
    unittest.main()