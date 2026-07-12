"""Tests for GLB exporter."""
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

from exports.glb import export, validate_glb, GLB_MAGIC


class _MockFile:
    def __init__(self, path: str, modality_id: str = "three_d_pointcloud", size: int = 0):
        self.path = path
        self.modality_id = modality_id
        self.size = size
        self.hash = "deadbeef"


class _MockDataset:
    def __init__(self, files):
        self.files = files
        self.version = "v_test"


def _make_obj(path: str, n_verts: int = 100, n_faces: int = 0) -> str:
    """Write a minimal OBJ file with n_verts vertices."""
    lines = ["# test obj"]
    for i in range(n_verts):
        x = (i % 10) * 0.1
        y = ((i // 10) % 10) * 0.1
        z = (i // 100) * 0.1
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    if n_faces > 0:
        for i in range(n_faces):
            i1 = (i * 3) % n_verts + 1
            i2 = (i * 3 + 1) % n_verts + 1
            i3 = (i * 3 + 2) % n_verts + 1
            lines.append(f"f {i1} {i2} {i3}")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


class TestGLBExport(unittest.TestCase):
    def test_glb_magic_and_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = _make_obj(os.path.join(tmp, "cube.obj"), n_verts=100, n_faces=0)
            ds = _MockDataset([_MockFile(obj)])
            out = os.path.join(tmp, "out.glb")
            written = export(ds, out)
            self.assertTrue(os.path.exists(written))
            with open(written, "rb") as f:
                raw = f.read()
            result = validate_glb(raw)
            self.assertTrue(result["ok"], msg=f"validate_glb failed: {result}")
            self.assertEqual(result["magic"], "glTF")
            self.assertEqual(result["version"], 2)
            self.assertGreater(result["json_chunk_length"], 0)
            self.assertTrue(result["bin_chunk_present"])

    def test_glb_100_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = _make_obj(os.path.join(tmp, "cloud.obj"), n_verts=100)
            ds = _MockDataset([_MockFile(obj)])
            out = os.path.join(tmp, "out100.glb")
            export(ds, out)
            with open(out, "rb") as f:
                raw = f.read()
            magic, ver, length = struct.unpack("<III", raw[:12])
            self.assertEqual(magic, GLB_MAGIC)
            self.assertEqual(ver, 2)
            self.assertEqual(length, len(raw))

    def test_glb_empty_dataset_fallback_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "fallback.glb")
            export(ds, out)
            with open(out, "rb") as f:
                raw = f.read()
            result = validate_glb(raw)
            self.assertTrue(result["ok"])
            self.assertGreater(result["n_meshes"], 0)

    def test_glb_validates_corrupt_bytes(self):
        bad = b"NOTAGLB" + b"\x00" * 100
        result = validate_glb(bad)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()