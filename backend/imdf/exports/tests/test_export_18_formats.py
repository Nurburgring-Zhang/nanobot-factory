"""End-to-end test: verify all 18 formats can be exported against a REAL DatasetVersion.

P19-E2: 改用 ``DatasetManager.create_version_from_paths()`` 真实构造
``DatasetVersion`` (而不是 mock). 这让以下 regression 被捕获:

1. ``DatasetManager._load_index`` 必须把 ``files`` list of dict coerce 成
   list of ``DatasetFile`` instances. 修复前, 从 index.json load 后
   ``ver.files[i]`` 是 dict, exporter 调 ``f.path`` / ``f.modality_id``
   会 raise AttributeError 或静默返回空字符串.

2. ``create_version_from_paths`` 必须保留所有 ``DatasetFile`` 属性
   (``path`` / ``hash`` / ``size`` / ``data_type`` / ``modality_id``).

3. manager-bound exporters (coco / webdataset / jsonl / parquet / llava /
   internvl) 必须能拿到正确的 ``ver.files`` 元数据.
"""
import json
import os
import shutil
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import List, Optional

from exports import REGISTRY, SUPPORTED_FORMATS
from exports.export_engine import ExportEngine, get_engine, export
from engines.dataset_manager import (
    DatasetFile,
    DatasetManager,
    DatasetVersion,
)


def _make_tiny_obj(path: str, n_vertices: int = 4) -> None:
    """写一个最小合法 Wavefront OBJ 文件 (n_vertices 顶点 + 2 triangle)."""
    lines = ["# test fixture"]
    for i in range(n_vertices):
        x = float(i)
        y = 0.0
        z = 0.0
        lines.append(f"v {x:.4f} {y:.4f} {z:.4f}")
    if n_vertices >= 3:
        lines.append("f 1 2 3")
    if n_vertices >= 4:
        lines.append("f 1 3 4")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestExport18Formats(unittest.TestCase):
    """P19 v5.1-D3 + P19-E2: verify all 18 formats export against a REAL
    ``DatasetVersion`` produced by ``DatasetManager``.
    """

    # 6 manager-bound (历史既有) → 必须 manager 调用
    MANAGER_FORMATS = {
        "coco", "webdataset", "jsonl", "parquet", "llava", "internvl",
    }
    # 6 NEW format exporters
    NEW_FORMATS = {"glb", "gltf", "obj", "coco_panoptic", "wav", "mp3"}
    # 6 function exporters (不需 manager)
    FUNCTION_FORMATS = {
        "yolo", "pascal_voc", "createml", "clip", "diffusiondb", "csv",
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="p19_d3_")
        # P19-E2: 真实 DatasetManager — temp data_dir 隔离
        self.data_dir = os.path.join(self.tmp, "datasets")
        self.engine = ExportEngine(data_dir=os.path.join(self.tmp, "exports"))
        self.manager = DatasetManager(data_dir=self.data_dir)

        # 创建 3 个真实 OBJ 文件 (for GLB/glTF/OBJ exporters 读 vertex data)
        self.obj_paths: List[str] = []
        for i in range(3):
            p = os.path.join(self.tmp, f"cube_{i}.obj")
            _make_tiny_obj(p, n_vertices=4)
            self.obj_paths.append(p)

        # 用真实 create_version_from_paths 构造 DatasetVersion
        self.version_str: str = self._build_real_version(
            paths=self.obj_paths,
            name="v_e2e",
        )

    def _build_real_version(self, paths: List[str], name: str = "v_e2e") -> str:
        """通过 ``DatasetManager.create_version_from_paths`` 构造真实版本.
        返回 version string."""
        ver = self.manager.create_version_from_paths(
            name=name, paths=paths, data_type="image")
        return ver.version

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ─── 基础 sanity ────────────────────────────────────────────────────

    def test_registry_has_18_formats(self):
        self.assertEqual(len(SUPPORTED_FORMATS), 18,
                         msg=f"expected 18 formats, got {len(SUPPORTED_FORMATS)}: {SUPPORTED_FORMATS}")
        expected = {
            # 3D (3 NEW)
            "glb", "gltf", "obj",
            # Image (5 existing + 1 NEW coco_panoptic = 6)
            "coco", "coco_panoptic", "yolo", "pascal_voc", "createml", "clip",
            # Video (1)
            "webdataset",
            # Multimodal (3)
            "llava", "internvl", "diffusiondb",
            # Table (3)
            "jsonl", "parquet", "csv",
            # Audio (2 NEW)
            "wav", "mp3",
        }
        self.assertEqual(set(SUPPORTED_FORMATS), expected)

    # ─── P19-E2 重点: load path 真实 DatasetVersion ─────────────────────

    def test_loaded_version_has_datasetfile_instances(self):
        """关键 regression 测试 — _load_index 必须 coerce files dict → DatasetFile.

        流程:
        1. save index (create_version 已经触发 _save_index)
        2. 创建新的 DatasetManager (强制走 _load_index)
        3. assert 所有 files 都是 DatasetFile 实例
        """
        # 1) 上面 setUp 已经触发 save; 验证 index.json 存在
        index_path = os.path.join(self.data_dir, "index.json")
        self.assertTrue(os.path.exists(index_path),
                        msg=f"index.json not saved at {index_path}")
        # 2) 重新加载
        mgr2 = DatasetManager(data_dir=self.data_dir)
        ver = mgr2.get_version(self.version_str)
        self.assertIsNotNone(ver, msg=f"version {self.version_str} not loaded back")
        self.assertIsInstance(ver, DatasetVersion)
        # 3) 关键 assertion — files list 里每个元素必须是 DatasetFile
        self.assertGreater(len(ver.files), 0,
                           msg="loaded version has empty files")
        for i, f in enumerate(ver.files):
            with self.subTest(file_idx=i):
                self.assertIsInstance(f, DatasetFile,
                                      msg=f"files[{i}] = {type(f).__name__}, "
                                          f"not DatasetFile — _load_index coerce "
                                          f"broken!")
                # 4) 所有 DatasetFile 字段必须可访问 (i.e. 不 raise AttributeError)
                _ = f.path
                _ = f.hash
                _ = f.size
                _ = f.data_type
                _ = f.modality_id

    def test_create_version_from_paths_preserves_fields(self):
        """create_version_from_paths 必须保留所有 DatasetFile 字段."""
        ver = self.manager.get_version(self.version_str)
        self.assertIsNotNone(ver)
        for i, f in enumerate(ver.files):
            with self.subTest(file_idx=i):
                self.assertEqual(f.path, self.obj_paths[i])
                # modality_id auto-detected from .obj extension → "three_d_pointcloud"
                self.assertEqual(f.modality_id, "three_d_pointcloud")
                # size > 0 (real file on disk)
                self.assertGreater(f.size, 0)
                # hash non-empty (real file on disk)
                self.assertNotEqual(f.hash, "")

    # ─── 18 格式 export 测试 (real DatasetVersion) ──────────────────────

    def test_each_format_runs_export(self):
        """P19-E2: 用真实 DatasetVersion 测试 18 格式."""
        # 重新拿 version (从当前 manager)
        ver = self.manager.get_version(self.version_str)
        self.assertIsNotNone(ver)
        # export() 接受 dataset (DatasetVersion-like object)
        for fmt in SUPPORTED_FORMATS:
            with self.subTest(fmt=fmt):
                try:
                    if fmt in self.MANAGER_FORMATS:
                        # Manager-bound: 用真实 DatasetManager
                        out = self.engine.export_with_manager(
                            fmt, self.manager, self.version_str,
                            output=os.path.join(self.tmp, f"{self.version_str}_{fmt}"))
                    else:
                        # Function-bound (新格式 + function exporters)
                        out = export(fmt, ver,
                                     output=os.path.join(self.tmp, f"{self.version_str}_{fmt}.out"))
                    self.assertTrue(out and os.path.exists(out),
                                    msg=f"{fmt}: output file not found at {out}")
                except Exception as exc:
                    self.fail(f"{fmt}: export raised {type(exc).__name__}: {exc}")

    def test_new_6_formats(self):
        """The 6 new formats added in P19 v5.1-D3."""
        ver = self.manager.get_version(self.version_str)
        for fmt in self.NEW_FORMATS:
            with self.subTest(fmt=fmt):
                out = export(fmt, ver,
                             output=os.path.join(self.tmp, f"{fmt}.out"))
                self.assertTrue(os.path.exists(out))
                size = os.path.getsize(out)
                self.assertGreater(size, 0, msg=f"{fmt}: empty output")

    def test_glb_is_valid_binary(self):
        ver = self.manager.get_version(self.version_str)
        out = export("glb", ver, output=os.path.join(self.tmp, "test.glb"))
        raw = Path(out).read_bytes()
        magic, ver_, length = struct.unpack("<III", raw[:12])
        self.assertEqual(magic, 0x46546C67)  # 'glTF'
        self.assertEqual(ver_, 2)
        self.assertEqual(length, len(raw))

    def test_gltf_is_valid_json(self):
        ver = self.manager.get_version(self.version_str)
        out = export("gltf", ver, output=os.path.join(self.tmp, "test.gltf"))
        doc = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(doc["asset"]["version"], "2.0")

    def test_obj_has_vertices_and_faces(self):
        ver = self.manager.get_version(self.version_str)
        out = export("obj", ver, output=os.path.join(self.tmp, "test.obj"))
        text = Path(out).read_text(encoding="utf-8")
        n_v = sum(1 for ln in text.splitlines() if ln.startswith("v "))
        self.assertGreater(n_v, 0)

    def test_coco_panoptic_structure(self):
        ver = self.manager.get_version(self.version_str)
        out = export("coco_panoptic", ver, output=os.path.join(self.tmp, "test_pan.json"))
        doc = json.loads(Path(out).read_text(encoding="utf-8"))
        for k in ("images", "annotations", "categories"):
            self.assertIn(k, doc)
        self.assertGreater(len(doc["images"]), 0)

    def test_wav_valid_header(self):
        ver = self.manager.get_version(self.version_str)
        out = export("wav", ver, output=os.path.join(self.tmp, "test.wav"))
        raw = Path(out).read_bytes()
        self.assertEqual(raw[:4], b"RIFF")
        self.assertEqual(raw[8:12], b"WAVE")

    def test_mp3_valid_frame_header(self):
        ver = self.manager.get_version(self.version_str)
        out = export("mp3", ver, output=os.path.join(self.tmp, "test.mp3"))
        raw = Path(out).read_bytes()
        # 找 MP3 sync word (0xFF 0xFB 或 0xFF 0xFA)
        found_sync = False
        for i in range(len(raw) - 1):
            if raw[i] == 0xFF and (raw[i + 1] & 0xE0) == 0xE0:
                found_sync = True
                break
        self.assertTrue(found_sync, msg="no MP3 sync word in output")

    def test_csv_has_rows(self):
        ver = self.manager.get_version(self.version_str)
        out = export("csv", ver, output=os.path.join(self.tmp, "test.csv"))
        import csv as _csv
        with open(out, "r", encoding="utf-8-sig") as fh:
            rows = list(_csv.DictReader(fh))
        self.assertGreater(len(rows), 0)
        self.assertIn("path", rows[0])

    def test_jsonl_with_real_manager(self):
        # jsonl 用真实 manager + real DatasetVersion
        out = self.engine.export_with_manager(
            "jsonl", self.manager, self.version_str,
            output=os.path.join(self.tmp, "test.jsonl"))
        self.assertTrue(os.path.exists(out))

    def test_coco_with_real_manager(self):
        out = self.engine.export_with_manager(
            "coco", self.manager, self.version_str,
            output=os.path.join(self.tmp, "test_coco.json"))
        self.assertTrue(os.path.exists(out))
        doc = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertIn("images", doc)
        # P19-E2 regression: 当 _load_index 修复了, exported images 应该有真实 path
        self.assertGreater(len(doc["images"]), 0,
                           msg="coco.images should not be empty with real DatasetVersion")

    def test_yolo_zip(self):
        ver = self.manager.get_version(self.version_str)
        out = export("yolo", ver, output=os.path.join(self.tmp, "test_yolo.zip"))
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        self.assertTrue(any(n.endswith("classes.names") for n in names))

    def test_format_categories(self):
        from exports import list_formats
        self.assertEqual(len(list_formats("3d")), 3)  # glb, gltf, obj
        self.assertEqual(len(list_formats("image")), 6)  # coco, coco_panoptic, yolo, pascal_voc, createml, clip
        self.assertEqual(len(list_formats("audio")), 2)  # wav, mp3
        self.assertEqual(len(list_formats("table")), 3)  # jsonl, parquet, csv
        self.assertEqual(len(list_formats("video")), 1)  # webdataset
        self.assertEqual(len(list_formats("multimodal")), 3)  # llava, internvl, diffusiondb


if __name__ == "__main__":
    unittest.main()