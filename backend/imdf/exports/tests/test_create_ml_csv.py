"""P19 v5.5: CreateML + CSV exporter tests (class-based, async API).

≥6 tests covering:
  - CreateMLExporter: 1 JSON per image + manifest, async API, empty dataset
  - CSVExporter: header + rows, async API, empty dataset, annotation rows
  - Both exporters wired through ExportResult metadata
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import dataclass
from typing import List, Optional

# Allow standalone test execution without imdf.__init__.
_REPO_BACKEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_BACKEND not in sys.path:
    sys.path.insert(0, _REPO_BACKEND)

from exports.create_ml_exporter import CreateMLExporter, ExportResult as CMR  # noqa: E402
from exports.csv_exporter import CSVExporter, ExportResult as CSVR  # noqa: E402


@dataclass
class _FakeFile:
    """Dataset file stand-in — supports `.path`, `.modality_id`, `.annotations`."""

    path: str
    modality_id: str = "image"
    annotations: Optional[List[dict]] = None


@dataclass
class _FakeDataset:
    files: List[_FakeFile]


def _make_dataset(n: int = 3) -> _FakeDataset:
    files = []
    for i in range(n):
        files.append(_FakeFile(
            path=f"/tmp/imgs/cat_{i:03d}.jpg",
            modality_id="image",
            annotations=[
                {
                    "label": "cat" if i % 2 == 0 else "dog",
                    "x_min": 10 + i * 5,
                    "y_min": 20 + i * 5,
                    "x_max": 100 + i * 5,
                    "y_max": 110 + i * 5,
                    "confidence": 0.9 + i * 0.01,
                },
            ],
        ))
    return _FakeDataset(files=files)


def _make_empty_dataset() -> _FakeDataset:
    return _FakeDataset(files=[])


# ──────────────────────────────────────────────────────────────────────────────
# 1. CreateMLExporter
# ──────────────────────────────────────────────────────────────────────────────
class TestCreateMLExporter(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="p19v55_createml_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_one_json_per_image_with_annotations(self):
        ds = _make_dataset(n=3)
        exporter = CreateMLExporter(classes=["cat", "dog", "bird"])
        result = asyncio.run(exporter.export(ds, self.tmp))

        self.assertIsInstance(result, CMR)
        self.assertEqual(result.format, "createml")

        # 3 image JSONs + 1 manifest = 4 files written
        json_files = [p for p in result.files_written if p.endswith(".json")
                      and not p.endswith("manifest.json")]
        self.assertEqual(len(json_files), 3,
                         msg=f"expected 3 image JSONs, got {len(json_files)}: {json_files}")

        # Verify each JSON has correct structure
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertIn("image", doc)
            self.assertIn("annotations", doc)
            self.assertIsInstance(doc["annotations"], list)
            self.assertGreater(len(doc["annotations"]), 0)
            for ann in doc["annotations"]:
                self.assertIn("label", ann)
                self.assertIn("coordinates", ann)
                coords = ann["coordinates"]
                for k in ("x", "y", "width", "height"):
                    self.assertIn(k, coords, msg=f"missing coord key {k}")

        # Manifest present and valid
        manifest_path = os.path.join(self.tmp, "manifest.json")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(manifest["format"], "createml")
        self.assertEqual(manifest["n_images"], 3)

    def test_create_annotations_subdir_layout(self):
        ds = _make_dataset(n=2)
        exporter = CreateMLExporter()
        asyncio.run(exporter.export(ds, self.tmp))
        ann_dir = os.path.join(self.tmp, "annotations")
        self.assertTrue(os.path.isdir(ann_dir))
        files = sorted(os.listdir(ann_dir))
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.endswith(".json") for f in files))

    def test_create_ml_empty_dataset(self):
        ds = _make_empty_dataset()
        exporter = CreateMLExporter()
        result = asyncio.run(exporter.export(ds, self.tmp))
        self.assertEqual(result.metadata["n_images"], 0)
        # 0 image JSONs + 1 manifest
        json_files = [p for p in result.files_written if p.endswith(".json")
                      and not p.endswith("manifest.json")]
        self.assertEqual(len(json_files), 0)
        # Manifest still written
        self.assertTrue(any(p.endswith("manifest.json") for p in result.files_written))


# ──────────────────────────────────────────────────────────────────────────────
# 2. CSVExporter
# ──────────────────────────────────────────────────────────────────────────────
class TestCSVExporter(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="p19v55_csv_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _out_path(self, name: str = "out.csv") -> str:
        return os.path.join(self.tmp, name)

    def test_csv_header_and_rows(self):
        ds = _make_dataset(n=3)
        out = self._out_path()
        exporter = CSVExporter()
        result = asyncio.run(exporter.export(ds, out))

        self.assertIsInstance(result, CSVR)
        self.assertEqual(result.format, "csv")
        self.assertEqual(result.output_path, out)
        self.assertTrue(os.path.exists(out))

        # Verify CSV structure
        with open(out, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            self.assertEqual(
                reader.fieldnames,
                ["id", "image_path", "label", "x_min", "y_min",
                 "x_max", "y_max", "confidence", "source"],
            )
            rows = list(reader)
        self.assertEqual(len(rows), 3,
                         msg=f"expected 3 rows, got {len(rows)}")
        for i, row in enumerate(rows):
            self.assertEqual(int(row["id"]), i)
            self.assertIn("/tmp/imgs/", row["image_path"])
            self.assertIn(row["label"], ("cat", "dog"))
            # Confidence = 0.9 + i*0.01 → 0.90, 0.91, 0.92 (always >= 0.9)
            self.assertGreaterEqual(float(row["confidence"]), 0.9)
            self.assertLessEqual(float(row["confidence"]), 1.0)

    def test_csv_metadata_n_rows(self):
        ds = _make_dataset(n=5)
        out = self._out_path()
        result = asyncio.run(CSVExporter().export(ds, out))
        self.assertEqual(result.metadata["n_rows"], 5)
        self.assertEqual(result.metadata["n_columns"], 9)
        self.assertGreater(result.bytes_total, 0)

    def test_csv_empty_dataset_writes_header_only(self):
        ds = _make_empty_dataset()
        out = self._out_path()
        result = asyncio.run(CSVExporter().export(ds, out))
        self.assertEqual(result.metadata["n_rows"], 0)
        # File still exists with just header
        self.assertTrue(os.path.exists(out))
        with open(out, "r", encoding="utf-8", newline="") as fh:
            content = fh.read()
        first_line = content.splitlines()[0]
        self.assertIn("id", first_line)
        self.assertIn("image_path", first_line)
        # No data rows beyond header
        self.assertEqual(len(content.splitlines()), 1)

    def test_csv_handles_multi_annotation_per_file(self):
        ds = _FakeDataset(files=[
            _FakeFile(
                path="/tmp/multi.jpg",
                modality_id="image",
                annotations=[
                    {"label": "cat", "x_min": 0, "y_min": 0,
                     "x_max": 50, "y_max": 50, "confidence": 0.9},
                    {"label": "dog", "x_min": 60, "y_min": 60,
                     "x_max": 100, "y_max": 100, "confidence": 0.8},
                ],
            ),
        ])
        out = self._out_path()
        result = asyncio.run(CSVExporter().export(ds, out))
        self.assertEqual(result.metadata["n_rows"], 2)

    def test_csv_custom_delimiter(self):
        ds = _make_dataset(n=1)
        out = self._out_path()
        exporter = CSVExporter(delimiter="|")
        asyncio.run(exporter.export(ds, out))
        with open(out, "r", encoding="utf-8") as fh:
            content = fh.read()
        # Header should use pipe delimiter
        self.assertIn("|", content.splitlines()[0])


if __name__ == "__main__":
    unittest.main()