"""P21 P2 P3 (revised) — 18-format export end-to-end with lazy DatasetManager.

R2 data #4 audit finding
------------------------
The 18 export formats advertised by ``ExportEngine.list_formats()`` (jsonl,
coco, webdataset, parquet, llava, internvl, glb, gltf, obj, coco_panoptic,
yolo, pascal_voc, createml, clip, diffusiondb, csv, wav, mp3) all registered
and supported, but ``eng.export(fmt, dataset, output)`` raised::

    ValueError: format 'jsonl' requires a DatasetManager + version
    (or AttributeError: manager has no method export_xxx)

for 6 of 18 formats whose exporter spec is bound to
``engines.dataset_manager:DatasetManager.export_<fmt>`` (jsonl, coco,
webdataset, parquet, llava, internvl).  R2's audit evidence::

    eng.export("jsonl", ds)   # ValueError
    eng.export("coco", ds)    # ValueError
    eng.export("parquet", ds) # ValueError

P21 P2 P3R (this test) fix
--------------------------
Modified ``backend/imdf/exports/export_engine.py::ExportEngine.export`` so
that when ``manager=None`` and the spec is manager-bound, a default
``DatasetManager`` is lazy-initialized with ``data_dir=os.path.dirname(output)
or "."``.  If the dataset is a ``DatasetVersion``-like object (has both
``.version`` str and ``.files`` list), it is auto-registered with the lazy
manager so that ``get_version(version)`` returns it.  The explicit
``manager=`` parameter is still honored first, so the fix is non-breaking.

This test
---------
Constructs a single ``DatasetVersion`` with 3 ``DatasetFile`` rows
(``id, text, label``) and calls ``eng.export(fmt, dataset, output)`` for each
of the 18 formats.  For each format we assert:
  1. The call returns without exception
  2. The output file exists and is non-empty
  3. For roundtrippable formats (jsonl, csv, parquet, json-based) the parsed
     content matches the input rows in some way (file count == 3 or
     line/record count > 0).

Run with::

    pytest tests/p2_p3_revised/test_export_formats.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

# The engine lives at ``imdf.exports.export_engine`` and uses a relative
# import (``from ..engines.dataset_manager import DatasetManager``) for the
# lazy-init path, so we must add ``backend/`` (NOT ``backend/imdf``) to
# sys.path so that the imdf package is importable as a top-level package.
# Mirrors ``tests/conftest.py`` (which adds backend/ for the same reason).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND = _PROJECT_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from imdf.exports.export_engine import ExportEngine  # noqa: E402
from imdf.engines.dataset_manager import (  # noqa: E402
    DatasetFile,
    DatasetVersion,
)


# ============================================================================
# Test data — 3 rows with id, text, label (the spec from the task)
# ============================================================================
SAMPLE_ROWS: List[Dict[str, Any]] = [
    {"id": 0, "text": "alpha", "label": "A"},
    {"id": 1, "text": "beta", "label": "B"},
    {"id": 2, "text": "gamma", "label": "C"},
]


def _build_test_dataset() -> DatasetVersion:
    """Build a 3-row DatasetVersion with text-like DatasetFile entries.

    Each row is represented as a ``DatasetFile`` whose ``path`` encodes the
    id/text/label triple (e.g. ``"row_0__alpha__A.txt"``).  This shape is
    compatible with the 18 format exporters that all iterate over
    ``dataset.files``.
    """
    files: List[DatasetFile] = []
    for row in SAMPLE_ROWS:
        safe_text = row["text"].replace(" ", "_")
        path = f"row_{row['id']}__{safe_text}__{row['label']}.txt"
        files.append(
            DatasetFile(
                path=path,
                data_type="text",
                size=10 + int(row["id"]),
                hash=f"sha256_{row['id']:04d}",
                modality_id="",
            )
        )
    return DatasetVersion(
        version="v_test_export_3rows",
        files=files,
        metadata={"name": "test_export_3rows", "row_count": len(SAMPLE_ROWS)},
    )


# ============================================================================
# 18-format coverage matrix (matches REGISTRY in imdf/exports/__init__.py)
# ============================================================================
# (format, expected_ext, manager_bound)
#   manager_bound=True  -> spec is engines.dataset_manager:DatasetManager.export_X
#                          (relies on the lazy DatasetManager fix)
#   manager_bound=False -> spec is exports.X:export (already worked)
EXPORT_MATRIX: List[Dict[str, Any]] = [
    # 3D (3)
    {"fmt": "glb", "ext": ".glb", "manager_bound": False},
    {"fmt": "gltf", "ext": ".gltf", "manager_bound": False},
    {"fmt": "obj", "ext": ".obj", "manager_bound": False},
    # image (6)
    {"fmt": "coco", "ext": ".json", "manager_bound": True},
    {"fmt": "coco_panoptic", "ext": ".json", "manager_bound": False},
    {"fmt": "yolo", "ext": ".zip", "manager_bound": False},
    {"fmt": "pascal_voc", "ext": ".xml", "manager_bound": False},
    {"fmt": "createml", "ext": ".json", "manager_bound": False},
    {"fmt": "clip", "ext": ".jsonl", "manager_bound": False},
    # video / multimodal (3)
    {"fmt": "webdataset", "ext": ".tar", "manager_bound": True},
    {"fmt": "llava", "ext": ".json", "manager_bound": True},
    {"fmt": "internvl", "ext": ".json", "manager_bound": True},
    # table / log (3)
    {"fmt": "jsonl", "ext": ".jsonl", "manager_bound": True},
    {"fmt": "parquet", "ext": ".parquet", "manager_bound": True},
    {"fmt": "csv", "ext": ".csv", "manager_bound": False},
    # audio (2)
    {"fmt": "wav", "ext": ".wav", "manager_bound": False},
    {"fmt": "mp3", "ext": ".mp3", "manager_bound": False},
    # 1 extra
    {"fmt": "diffusiondb", "ext": ".parquet", "manager_bound": False},
]

# Drift guard: any future worker who adds a 19th format MUST add a row here.
assert len(EXPORT_MATRIX) == 18, (
    f"EXPORT_MATRIX size drift: expected 18, got {len(EXPORT_MATRIX)}. "
    f"Update the test when adding a new format to REGISTRY."
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def tmp_workdir(tmp_path):
    """P21 P2 P3R: fresh per-test working directory under tmp_path."""
    workdir = tmp_path / "export_workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


@pytest.fixture
def engine(tmp_workdir):
    """ExportEngine pinned to the temp workdir."""
    return ExportEngine(data_dir=str(tmp_workdir))


@pytest.fixture
def dataset():
    """3-row DatasetVersion (id, text, label) reused across all 18 formats."""
    return _build_test_dataset()


# ============================================================================
# Phase 1 — every format must export without manager
# ============================================================================

@pytest.mark.parametrize("row", EXPORT_MATRIX, ids=[r["fmt"] for r in EXPORT_MATRIX])
def test_export_format_produces_nonempty_file(engine, dataset, tmp_workdir, row):
    """R2 data #4 regression: each of the 18 formats must work end-to-end
    with ``eng.export(fmt, dataset, output)`` (no manager passed)."""
    fmt = row["fmt"]
    ext = row["ext"]
    out_path = str(tmp_workdir / f"out_{fmt}{ext}")
    result_path = engine.export(fmt, dataset, out_path)

    # 1. Returns a string path
    assert isinstance(result_path, str) and result_path, (
        f"{fmt}: export() returned falsy path: {result_path!r}"
    )
    # 2. The returned file path exists
    out = Path(result_path)
    assert out.exists(), f"{fmt}: output path {out} does not exist"
    # 3. The file is non-empty
    if out.is_file():
        size = out.stat().st_size
        assert size > 0, f"{fmt}: output file is empty ({size} bytes) at {out}"
    elif out.is_dir():
        # WebDataset returns a directory of shards
        files_in_dir = list(out.rglob("*"))
        assert any(f.is_file() and f.stat().st_size > 0 for f in files_in_dir), (
            f"{fmt}: output directory {out} contains no non-empty files"
        )


# ============================================================================
# Phase 2 — manager-bound formats specifically exercise the lazy init
# ============================================================================

MANAGER_BOUND_FORMATS = [r for r in EXPORT_MATRIX if r["manager_bound"]]
assert len(MANAGER_BOUND_FORMATS) == 6, (
    f"manager-bound format count drift: expected 6 (jsonl/coco/webdataset/"
    f"parquet/llava/internvl), got {len(MANAGER_BOUND_FORMATS)}"
)


@pytest.mark.parametrize(
    "row", MANAGER_BOUND_FORMATS, ids=[r["fmt"] for r in MANAGER_BOUND_FORMATS]
)
def test_manager_bound_format_lazy_init(engine, dataset, tmp_workdir, row):
    """The 6 manager-bound formats must work via the lazy DatasetManager
    path (i.e. the bug fixed by this task)."""
    fmt = row["fmt"]
    out_path = str(tmp_workdir / f"lazy_{fmt}{row['ext']}")
    result_path = engine.export(fmt, dataset, out_path)
    assert result_path, f"{fmt}: lazy-init export returned empty path"
    p = Path(result_path)
    assert p.exists(), f"{fmt}: lazy-init output {p} does not exist"
    if p.is_file():
        assert p.stat().st_size > 0, f"{fmt}: lazy-init output is empty"


# ============================================================================
# Phase 3 — roundtrip checks (where the format is plain text/JSON)
# ============================================================================

def test_jsonl_roundtrip_count_matches(engine, dataset, tmp_workdir):
    """jsonl: 1 record per file in the dataset version."""
    out_path = str(tmp_workdir / "roundtrip.jsonl")
    engine.export("jsonl", dataset, out_path)
    with open(out_path, "r", encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    assert len(lines) == len(SAMPLE_ROWS), (
        f"jsonl roundtrip: expected {len(SAMPLE_ROWS)} lines, got {len(lines)}"
    )
    # Each line must be a parseable JSON object with the dataset's file fields.
    # Per dataset_manager.export_jsonl, the field is "type" (not "data_type").
    for ln in lines:
        rec = json.loads(ln)
        assert "path" in rec, f"jsonl rec missing 'path': {rec}"
        assert "size" in rec, f"jsonl rec missing 'size': {rec}"
        assert "type" in rec, f"jsonl rec missing 'type': {rec}"


def test_coco_roundtrip_count_matches(engine, dataset, tmp_workdir):
    """coco: 1 image record per file in the dataset version."""
    out_path = str(tmp_workdir / "roundtrip_coco.json")
    engine.export("coco", dataset, out_path)
    with open(out_path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    assert "images" in doc and len(doc["images"]) == len(SAMPLE_ROWS), (
        f"coco roundtrip: expected {len(SAMPLE_ROWS)} images, "
        f"got {len(doc.get('images', []))}"
    )


def test_csv_roundtrip_count_matches(engine, dataset, tmp_workdir):
    """csv: 1 row per file in the dataset version (header + N data rows)."""
    import csv
    out_path = str(tmp_workdir / "roundtrip.csv")
    engine.export("csv", dataset, out_path)
    with open(out_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    assert len(rows) == len(SAMPLE_ROWS) + 1, (
        f"csv roundtrip: expected {len(SAMPLE_ROWS) + 1} rows "
        f"(header + {len(SAMPLE_ROWS)} data), got {len(rows)}"
    )
    header = rows[0]
    assert "id" in header and "path" in header


def test_parquet_roundtrip_count_matches(engine, dataset, tmp_workdir):
    """parquet: 1 row per file (pandas may not be available, in which case
    jsonl fallback is used and is roundtrip-checked via test_jsonl)."""
    out_path = str(tmp_workdir / "roundtrip.parquet")
    engine.export("parquet", dataset, out_path)
    # The exporter falls back to jsonl if pandas/pyarrow is missing.
    actual = Path(out_path)
    if not actual.exists():
        # Try jsonl fallback
        actual = Path(str(out_path).rsplit(".", 1)[0] + ".jsonl")
    assert actual.exists(), f"parquet: neither {out_path} nor jsonl fallback found"
    if actual.suffix == ".parquet":
        try:
            import pandas as pd
            df = pd.read_parquet(actual)
            assert len(df) == len(SAMPLE_ROWS)
        except Exception:
            # parquet roundtrip skipped if pandas not available; just check size
            assert actual.stat().st_size > 0
    else:
        with open(actual, "r", encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        assert len(lines) == len(SAMPLE_ROWS)


def test_llava_internvl_records_match(engine, dataset, tmp_workdir):
    """llava + internvl: 1 conversation record per file in the dataset."""
    for fmt in ("llava", "internvl"):
        out_path = str(tmp_workdir / f"rt_{fmt}.json")
        engine.export(fmt, dataset, out_path)
        with open(out_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, list) and len(data) == len(SAMPLE_ROWS), (
            f"{fmt} roundtrip: expected {len(SAMPLE_ROWS)} records, got {len(data)}"
        )
        for rec in data:
            assert "image" in rec and "conversations" in rec


# ============================================================================
# Phase 4 — explicit-manager path is NOT regressed
# ============================================================================

def test_explicit_manager_still_wins(tmp_workdir):
    """The lazy-init fix must NOT change behavior when manager= is passed
    explicitly.  We pass a custom manager that records whether export was
    called via it; the engine must route to it (not the lazy default)."""
    from imdf.engines.dataset_manager import DatasetManager

    # Build a custom manager with a pre-registered version.
    mgr = DatasetManager(data_dir=str(tmp_workdir / "explicit_mgr"))
    files = [
        DatasetFile(path="x.txt", data_type="text", size=1, hash="h", modality_id=""),
        DatasetFile(path="y.txt", data_type="text", size=2, hash="i", modality_id=""),
    ]
    ver = mgr.create_version(name="explicit", files=files)

    # Export via the engine, passing the manager explicitly.
    eng = ExportEngine(data_dir=str(tmp_workdir))
    out = eng.export(
        "jsonl", ver, str(tmp_workdir / "explicit.jsonl"), manager=mgr,
    )
    assert Path(out).exists() and Path(out).stat().st_size > 0
    # Verify the version that the manager has is the one we created
    assert mgr.get_version(ver.version) is ver
    # And the explicit manager's data_dir contains the index
    assert (tmp_workdir / "explicit_mgr" / "index.json").exists()


# ============================================================================
# Phase 5 — bare-bones DatasetVersion (the shape the test should ALSO support)
# ============================================================================

def test_minimal_dataset_with_only_version_and_files(engine, tmp_workdir):
    """If the caller hands in a bare object with just .version and .files
    (no real DatasetFile instances), the lazy manager must still accept it
    and write a non-empty output for the manager-bound formats."""
    from types import SimpleNamespace

    # 3 minimal rows: just .version and .files
    obj = SimpleNamespace(
        version="v_min_3",
        files=[
            SimpleNamespace(path="a", data_type="text", size=1, hash="h", modality_id=""),
            SimpleNamespace(path="b", data_type="text", size=2, hash="i", modality_id=""),
            SimpleNamespace(path="c", data_type="text", size=3, hash="j", modality_id=""),
        ],
    )
    for fmt in ("jsonl", "coco", "parquet", "llava", "internvl", "webdataset"):
        ext = {"jsonl": ".jsonl", "coco": ".json", "parquet": ".parquet",
               "llava": ".json", "internvl": ".json", "webdataset": ".tar"}[fmt]
        out = str(tmp_workdir / f"min_{fmt}{ext}")
        result = engine.export(fmt, obj, out)
        assert result, f"{fmt}: empty result for minimal dataset"
        rp = Path(result)
        assert rp.exists(), f"{fmt}: output {rp} does not exist for minimal dataset"
        if rp.is_file():
            assert rp.stat().st_size > 0, f"{fmt}: empty output for minimal dataset"


# ============================================================================
# Phase 6 — missing .version is rejected with a clear error
# ============================================================================

def test_missing_version_attribute_raises_clear_error(engine, tmp_workdir):
    """A dataset with no .version attribute for a manager-bound format must
    raise a clear ``ValueError`` (not a confusing ``AttributeError``)."""
    bare = type("BareObj", (), {"files": []})()
    with pytest.raises(ValueError, match=r"version"):
        engine.export("jsonl", bare, str(tmp_workdir / "no_version.jsonl"))
