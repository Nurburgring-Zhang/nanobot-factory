"""Tests for OBJ exporter."""
import os
import tempfile
import unittest
from pathlib import Path

from exports.obj import export, validate_obj


class _MockFile:
    def __init__(self, path: str):
        self.path = path
        self.modality_id = "three_d_pointcloud"
        self.size = 0
        self.hash = "deadbeef"


class _MockDataset:
    def __init__(self, files):
        self.files = files
        self.version = "v_test"


def _make_obj(path: str, n_verts: int = 100, n_faces: int = 0) -> str:
    lines = ["# obj test"]
    for i in range(n_verts):
        x = (i % 10) * 0.1
        y = ((i // 10) % 10) * 0.1
        z = (i // 100) * 0.1
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    for i in range(n_faces):
        i1 = (i * 3) % n_verts + 1
        i2 = (i * 3 + 1) % n_verts + 1
        i3 = (i * 3 + 2) % n_verts + 1
        lines.append(f"f {i1} {i2} {i3}")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


class TestOBJExport(unittest.TestCase):
    def test_obj_basic_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = _make_obj(os.path.join(tmp, "in.obj"), n_verts=100, n_faces=20)
            ds = _MockDataset([_MockFile(obj)])
            out = os.path.join(tmp, "out.obj")
            written = export(ds, out)
            raw = Path(written).read_text(encoding="utf-8")
            result = validate_obj(raw)
            self.assertTrue(result["ok"], msg=result)
            self.assertGreaterEqual(result["n_vertices"], 100)

    def test_obj_mtl_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "sub", "out.obj")
            written = export(ds, out)
            mtl = os.path.splitext(written)[0] + ".mtl"
            self.assertTrue(os.path.exists(mtl))
            mtl_content = Path(mtl).read_text(encoding="utf-8")
            self.assertIn("newmtl default", mtl_content)

    def test_obj_100_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = _make_obj(os.path.join(tmp, "pts.obj"), n_verts=100)
            ds = _MockDataset([_MockFile(obj)])
            out = os.path.join(tmp, "out100.obj")
            export(ds, out)
            raw = Path(out).read_text(encoding="utf-8")
            result = validate_obj(raw)
            self.assertTrue(result["ok"])
            self.assertEqual(result["n_vertices"], 100)

    def test_obj_empty_fallback_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _MockDataset([])
            out = os.path.join(tmp, "fb.obj")
            export(ds, out)
            raw = Path(out).read_text(encoding="utf-8")
            result = validate_obj(raw)
            self.assertTrue(result["ok"])
            # fallback cube = 8 vertices
            self.assertEqual(result["n_vertices"], 8)


if __name__ == "__main__":
    unittest.main()