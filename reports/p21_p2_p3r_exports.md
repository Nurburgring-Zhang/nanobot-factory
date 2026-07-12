# P21 P2 P3 (revised) — 18 Export Formats Lazy DatasetManager Init

**Project**: nanobot-factory VDP-2026 v1.5.0
**Sprint**: P21 Phase 2 P3 (revised) P1 fix
**R2 finding closed**: R2 data #4 — 18 export formats require DatasetManager
**Auditor**: data-pipeline-expert (coder branch session)
**Date**: 2026-07-11
**Python**: `D:\ComfyUI\.ext\python.exe` 3.11.6
**Project root**: `D:\Hermes\生产平台\nanobot-factory`

---

## TL;DR

Fixed the R2 data #4 finding: 6 of the 18 export formats (jsonl, coco,
webdataset, parquet, llava, internvl) whose exporter spec is bound to
`engines.dataset_manager:DatasetManager.export_X` now work end-to-end via
`eng.export(fmt, dataset, output)` (no manager passed) by lazy-initializing
a default `DatasetManager` in `ExportEngine.export()`.

- **Modified**: `backend/imdf/exports/export_engine.py` — 2 hunks in
  `ExportEngine.export()` (lazy-init for manager-bound formats + version-id
  normalization for the explicit-manager path)
- **Created**: `tests/p2_p3_revised/test_export_formats.py` — 32 tests
  (18 format end-to-end + 6 manager-bound specific + 5 roundtrip + 3
  edge-case regression)
- **All 32 new tests pass in 0.80s**
- **All 16 pre-existing tests in `backend/imdf/exports/tests/test_export_18_formats.py` still pass** (backward-compat verified)

---

## What was changed

### 1. `backend/imdf/exports/export_engine.py`

Two small hunks inside `ExportEngine.export()`:

**Hunk A — explicit-manager version normalization (lines 149-158)**
The previous code did `export_with_manager(fmt, manager, dataset, output)`
which passed a `DatasetVersion` (or any non-string dataset) where the
`version: str` argument was expected. This raised
`TypeError: unhashable type: 'DatasetVersion'` whenever the caller passed
both an explicit manager and a dataset-like object (the most common usage).
Now the engine normalizes: if `dataset` is a string it is passed through;
otherwise `dataset.version` is extracted and used as the version id.

**Hunk B — lazy `DatasetManager` init (lines 177-204)**
When `manager=None` and the spec is manager-bound
(`engines.dataset_manager:...`), the engine now:
1. Imports `DatasetManager` (lazy, only on this path)
2. Creates a default `manager = DatasetManager(data_dir=os.path.dirname(output) or ".")`
3. Auto-registers the dataset as a version if it has `.version` (str) and `.files`
4. Delegates to `export_with_manager(fmt, lazy_manager, version_str, output, **kwargs)`

This means the 18-format export registry now works end-to-end without
callers having to wire a manager manually. Behavior is unchanged when
`manager=` is passed explicitly (the explicit-manager branch runs first
and never falls through to the lazy path).

### Why not a separate `base.py`?

The task spec mentioned `backend/imdf/exports/base.py`, but that file
does not exist in this codebase. The base export logic lives in
`export_engine.py` (single 299-line module that holds the
`ExportEngine` class). I added the lazy init directly in
`ExportEngine.export()` (the natural "base" method for the 18-format
registry) rather than creating a new file.

---

## Test coverage

`tests/p2_p3_revised/test_export_formats.py` (32 tests, 0.80s):

| # | Phase | Test class | What it covers |
|---|-------|-----------|----------------|
| 1 | 1 | `test_export_format_produces_nonempty_file[fmt]` (18 parametrized) | Every one of the 18 formats in REGISTRY must produce a non-empty file when called as `eng.export(fmt, dataset, output)` with no manager |
| 2 | 2 | `test_manager_bound_format_lazy_init[fmt]` (6 parametrized) | The 6 manager-bound formats (jsonl/coco/webdataset/parquet/llava/internvl) must work via the lazy DatasetManager path |
| 3 | 3 | `test_jsonl_roundtrip_count_matches` | jsonl: 3 lines for 3 rows, each with `path`/`size`/`type` |
| 4 | 3 | `test_coco_roundtrip_count_matches` | coco: 3 image records for 3 rows |
| 5 | 3 | `test_csv_roundtrip_count_matches` | csv: 4 rows (header + 3 data) |
| 6 | 3 | `test_parquet_roundtrip_count_matches` | parquet: 3 rows (or jsonl fallback) |
| 7 | 3 | `test_llava_internvl_records_match` | llava + internvl: 3 records each with `image` + `conversations` |
| 8 | 4 | `test_explicit_manager_still_wins` | The `manager=` parameter is still honored (non-regression) |
| 9 | 5 | `test_minimal_dataset_with_only_version_and_files` | Bare-bones `SimpleNamespace(version, files)` works for all 6 manager-bound formats |
| 10 | 6 | `test_missing_version_attribute_raises_clear_error` | Datasets without `.version` get a clear `ValueError` (not confusing AttributeError) |

**Drift guards**:
- `assert len(EXPORT_MATRIX) == 18` — any future worker who adds a 19th format to REGISTRY must add a row here
- `assert len(MANAGER_BOUND_FORMATS) == 6` — drift guard for the manager-bound subset

---

## Coverage matrix vs R2 audit

| R2 audit claim | Before fix | After fix | Verified by |
|----------------|-----------|-----------|-------------|
| `eng.export("jsonl", ds)` fails with `ValueError` (no manager) | FAIL — `AttributeError: manager has no method export_jsonl` | PASS | `test_export_format_produces_nonempty_file[jsonl]` |
| `eng.export("coco", ds)` fails | FAIL | PASS | `test_export_format_produces_nonempty_file[coco]` |
| `eng.export("parquet", ds)` fails | FAIL | PASS | `test_export_format_produces_nonempty_file[parquet]` |
| `eng.export("llava", ds)` fails | FAIL | PASS | `test_export_format_produces_nonempty_file[llava]` |
| `eng.export("internvl", ds)` fails | FAIL | PASS | `test_export_format_produces_nonempty_file[internvl]` |
| `eng.export("webdataset", ds)` fails | FAIL | PASS | `test_export_format_produces_nonempty_file[webdataset]` |
| Audit listed 7 formats; actual count is 6 | Audit drift | N/A | The 7th (diffusiondb) is actually an unbound function and worked before; the 6 listed above are the true manager-bound subset |

**Note on R2 audit's "7 formats"**: The R2 audit listed 7 manager-bound
formats (jsonl/coco/webdataset/parquet/llava/internvl/diffusiondb), but
inspection of the registry shows diffusiondb is `exports.diffusiondb:export`
(unbound function, not manager-bound). It worked before the fix and still
works after. The actual manager-bound count is 6 — fixed via this PR.

---

## Backward compatibility

- **Pre-existing `manager=` parameter**: still works. `test_explicit_manager_still_wins` exercises the explicit-manager path end-to-end (DatasetManager + create_version + export) and passes.
- **Pre-existing `export_with_manager(fmt, manager, version, output)` method**: still works. Unchanged signature.
- **16 pre-existing tests in `backend/imdf/exports/tests/test_export_18_formats.py`**: still pass (verified). They use the same patterns the engine was designed for, including manager-bound formats via explicit manager.

---

## Files

### Modified
- `backend/imdf/exports/export_engine.py` — 2 hunks in `ExportEngine.export()` (lazy DatasetManager init + version-id normalization)

### Created
- `tests/p2_p3_revised/test_export_formats.py` — 32 tests covering the 18 formats
- `reports/p21_p2_p3r_exports.md` — this report

---

## Reproduction commands

```powershell
# Run the new tests
& "D:\ComfyUI\.ext\python.exe" -m pytest "D:\Hermes\生产平台\nanobot-factory\tests\p2_p3_revised\test_export_formats.py" -v

# Verify the R2 audit repro is now fixed
& "D:\ComfyUI\.ext\python.exe" -c "import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend'); from imdf.exports.export_engine import ExportEngine; from imdf.engines.dataset_manager import DatasetVersion, DatasetFile; ds = DatasetVersion(version='v_audit_repro', files=[DatasetFile(path='a.txt', data_type='text', size=1, hash='h', modality_id='')]); eng = ExportEngine(data_dir='tmp_audit'); print(eng.export('jsonl', ds, 'tmp_audit/repro.jsonl'))"
# Before: AttributeError: manager has no method export_jsonl
# After:  tmp_audit/repro.jsonl (240 bytes, 1 JSON line)
```

---

## Hard rules — all observed

- 25 minutes total: yes (started 10:23, finished 10:45)
- `D:\ComfyUI\.ext\python.exe`: yes
- `D:\Hermes\生产平台\nanobot-factory` as project root: yes
- No new dependencies: confirmed (lazy `from ..engines.dataset_manager import DatasetManager` reuses existing module)
- Existing `manager=` parameter not broken: confirmed by `test_explicit_manager_still_wins` and 16/16 pre-existing tests still passing
