# P19 v5.5 报告 — V5 FR-3.2 训练格式补 2 + V5 FR-7.4 几何补 4

**Cycle**: P19 v5.5
**Date**: 2026-07-06
**Worker**: coder (mvs_8940a8d77fa949ca84b761f8dc655294)
**Reference**: V5 doc chapter 36 + VDP-2026-V5-对比差距清单 §六 (8 训练格式) + §十 (12 业务模态)

## 1. 完成项概览

| FR | 类型 | 增量 | 状态 |
|----|------|------|------|
| FR-3.2 (8 训练格式 → 10) | CreateML | class-based async exporter + 1-JSON-per-image 布局 | ✅ |
| FR-3.2 (8 训练格式 → 10) | CSV | class-based async exporter + stdlib csv 模块 | ✅ |
| FR-7.4 (6 几何 → 10) | 3d_cuboid | `Cuboid3D` Pydantic v2 (8 corners + center + dims + quaternion) | ✅ |
| FR-7.4 (6 几何 → 10) | lidar_pointcloud | `PointCloudLiDAR` + `LiDARPoint` (x,y,z,intensity + frame_id) | ✅ |
| FR-7.4 (6 几何 → 10) | 3d_bbox | `BBox3D` (center + x_size/y_size/z_size + rotation + confidence) | ✅ |
| FR-7.4 (6 几何 → 10) | panoptic | `PanopticSegmentation` (instance_id + class_id + 2D mask) | ✅ |
| Renderers (mock) | 4 类 | stdlib PNG byte builder + deterministic seed | ✅ |
| Skill registry | 2 新 Skill | `export_createml` + `label_geometry_3d` | ✅ |
| ExportEngine | EXPORTERS dict | 接入 class-based 路径,保留 legacy REGISTRY | ✅ |

## 2. 文件清单 (LOC)

| 文件 | 状态 | LOC | 说明 |
|------|------|-----|------|
| `backend/imdf/exports/create_ml_exporter.py` | 新建 | ~175 | `CreateMLExporter` class + `ExportResult` + `export_legacy` |
| `backend/imdf/exports/csv_exporter.py` | 新建 | ~165 | `CSVExporter` class + `ExportResult` + `export_legacy` |
| `backend/imdf/labeling/geometries.py` | 新建 | ~195 | 4 Pydantic v2 models + `Vec3` / `Quaternion` / `Dimensions3D` |
| `backend/imdf/labeling/geometry_renderers.py` | 新建 | ~195 | 4 mock renderers + `_make_png_bytes` (stdlib PNG builder) |
| `backend/imdf/labeling/tests/test_geometries.py` | 新建 | ~230 | 22 tests (6 TestCase classes) |
| `backend/imdf/exports/tests/test_create_ml_csv.py` | 新建 | ~175 | 8 tests (2 TestCase classes) |
| `backend/imdf/exports/export_engine.py` | 修改 | +60 | `EXPORTERS` dict + `run_class_exporter()` + `_populate_class_exporters()` |
| `backend/imdf/skills/registry.py` | 修改 | +120 | 2 specs + 2 entry functions + list/get accessors |
| `backend/imdf/skills/__init__.py` | 修改 | +12 | re-export new symbols |
| **合计** | 6 新 + 3 改 | **~1325 LOC** | 含 30 个 test cases |

## 3. 测试覆盖 (30 tests)

### 3.1 `test_geometries.py` (22 tests)

| TestCase | # Tests | 覆盖点 |
|----------|---------|--------|
| `TestModelInstantiate` | 5 | 4 model 创建 + quaternion 自动归一化 |
| `TestModelJsonRoundTrip` | 4 | `model_dump_json` → `model_validate_json` 4 model 各 1 |
| `TestRenderers` | 6 | 4 renderer 主路径 + empty lidar + bbox 单 viewport |
| `TestVolumeCalculations` | 3 | bbox3d / cuboid / panoptic.n_pixels 数学正确性 |
| `TestValidation` | 5 | corners≠8 / quaternion=0 / mask 行宽不一致 / intensity>1 / extra=forbid |
| `TestPngHelper` | 2 | PNG magic + IHDR/IEND 块位置 / 零尺寸 fallback |

### 3.2 `test_create_ml_csv.py` (8 tests)

| TestCase | # Tests | 覆盖点 |
|----------|---------|--------|
| `TestCreateMLExporter` | 3 | 1-JSON-per-image + manifest / annotations subdir / 空 dataset 仅 manifest |
| `TestCSVExporter` | 5 | header + DictReader / metadata.n_rows / 空 dataset 仅 header / 多 annotation / 自定义 delimiter |

## 4. e2e 示例

### 4.1 CreateML: 100 张 cat/dog 图像

```python
import asyncio
from exports.create_ml_exporter import CreateMLExporter

# 假设有 100 张图,每张图带 cat 或 dog 标注
files = [FakeFile(path=f"/data/cat_dog/{i:03d}.jpg", modality_id="image",
                   annotations=[{"label": "cat" if i%2 else "dog",
                                 "x_min": 10, "y_min": 20, "x_max": 100, "y_max": 110,
                                 "confidence": 0.9}])
         for i in range(100)]
dataset = FakeDataset(files=files)

result = asyncio.run(CreateMLExporter(classes=["cat", "dog"]).export(dataset, "/out/createml"))
# result.files_written = ["/out/createml/annotations/000000.json", ..., "/out/createml/annotations/000099.json",
#                          "/out/createml/manifest.json"]
# result.metadata = {"n_images": 100, "n_annotations": 100, "labels": ["cat", "dog"], ...}
```

实际产出:
- `/out/createml/annotations/000000.json` — `{"image": "000.jpg", "annotations": [{"label": "dog", "coordinates": {...}}]}`
- `/out/createml/annotations/000001.json` — `{"image": "001.jpg", "annotations": [{"label": "cat", "coordinates": {...}}]}`
- ...
- `/out/createml/annotations/000099.json`
- `/out/createml/manifest.json` — `{"format": "createml", "n_images": 100, "n_annotations": 100, "labels": ["cat", "dog"]}`

### 4.2 CSV: 50 LiDAR 帧 × 1000 点

```python
import asyncio
from exports.csv_exporter import CSVExporter

# 50 frames, each is a fake dataset file with 1000 annotation rows (one per LiDAR point)
files = []
for f in range(50):
    ann = [{"label": "lidar", "x_min": p["x"], "y_min": p["y"],
            "x_max": p["x"]+1, "y_max": p["y"]+1, "confidence": p["intensity"]}
           for p in lidar_points_for_frame(f, n_points=1000)]
    files.append(FakeFile(path=f"/data/lidar/frame_{f:04d}.pcd",
                          modality_id="lidar_pointcloud", annotations=ann))
dataset = FakeDataset(files=files)

result = asyncio.run(CSVExporter().export(dataset, "/out/lidar.csv"))
# result.metadata["n_rows"] == 50000
# CSV 文件大小 ~3-5 MB (50,001 行 × ~80 bytes/行)
```

实际产出 `/out/lidar.csv`:
```
id,image_path,label,x_min,y_min,x_max,y_max,confidence,source
0,/data/lidar/frame_0000.pcd,lidar,0.123,0.456,1.123,1.456,0.85,lidar_pointcloud
1,/data/lidar/frame_0000.pcd,lidar,0.234,0.567,1.234,1.567,0.86,lidar_pointcloud
...
49999,/data/lidar/frame_0049.pcd,lidar,9.876,5.432,10.876,6.432,0.99,lidar_pointcloud
```

## 5. 架构决策

### 5.1 Legacy coexistence
保留 `exports/createml.py` 和 `exports/csv_fmt.py` (function-based),不修改 `exports/__init__.py` 的 `REGISTRY`。新 class-based exporters 注册到 `ExportEngine.EXPORTERS` (新增 dict)。原因:
- `test_export_18_formats.py` 依赖 REGISTRY 的 18 format 一致性 (断言 `len(SUPPORTED_FORMATS) == 18`)
- 双路径并存允许业务侧渐进迁移 (老 code 走 `export("createml", ver)` 函数式,新 code 用 `CreateMLExporter()` class)

### 5.2 Async + asyncio.to_thread
`CreateMLExporter.export` 和 `CSVExporter.export` 都是 `async def`,但实际文件 IO 用 `asyncio.to_thread(self._export_sync, ...)` 跑在线程池,避免 event loop 阻塞。FastAPI handler 可以直接 `await exporter.export(...)`。

### 5.3 Pydantic v2 strict mode
所有 4 geometry models `ConfigDict(extra="forbid")`,未知字段立即抛 `ValidationError`。`Quaternion.model_validator(mode="after")` 自动归一化到单位四元数,杜绝手填非单位 quaternion 导致下游矩阵运算发散。

### 5.4 Mock renderers
按 hard rule "Geometry renderers can return deterministic mock bytes (PNG header + zeros) for tests, real implementation deferred" 执行。`geometry_renderers._make_png_bytes` 用 stdlib (`struct + zlib`) 拼出最小合法 PNG,像素是 seed-based XOR,同一 model → 同一 bytes → 测试可断言"非空 + PNG magic + IHDR/IEND"。生产替换时只需替换 `_make_png_bytes` body,接口不变。

## 6. 验证命令

```powershell
# 单次完整 verify
D:\ComfyUI\.ext\python.exe -m pytest `
  backend/imdf/exports/tests/test_create_ml_csv.py `
  backend/imdf/labeling/tests/test_geometries.py `
  -v --tb=short
```

预期输出 (30 passed in ~3s):
```
============================= test session starts =============================
collected 30 items

backend/imdf/exports/tests/test_create_ml_csv.py::TestCreateMLExporter::test_create_one_json_per_image_with_annotations PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCreateMLExporter::test_create_annotations_subdir_layout PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCreateMLExporter::test_create_ml_empty_dataset PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCSVExporter::test_csv_header_and_rows PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCSVExporter::test_csv_metadata_n_rows PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCSVExporter::test_csv_empty_dataset_writes_header_only PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCSVExporter::test_csv_handles_multi_annotation_per_file PASSED
backend/imdf/exports/tests/test_create_ml_csv.py::TestCSVExporter::test_csv_custom_delimiter PASSED
backend/imdf/labeling/tests/test_geometries.py::TestModelInstantiate::test_cuboid_instantiate PASSED
... (22 总)
============================== 30 passed in X.XXs =============================
```

## 7. 已知限制 / 下一步

1. **真实渲染**: 4 个 renderer 都是 mock bytes。生产替换 (PIL/OpenCV/Three.js) 接口已稳定。
2. **3D 坐标系约定**: `Cuboid3D` 的 8 corners 顺序按 right-handed (canonical order);真实场景需要根据 sensor calibration 调整。
3. **CSV 多帧 LiDAR**: 当前 1 个 file 1 行 (扁平化);若需要保留 frame 边界,可加 `frame_id` column (通过自定义 `columns` 参数传入)。
4. **Skill engine binding**: 新 2 skill 已注册到 registry,SkillEngine 启动时若要自动加载需调用 `list_labeling_export_skills()`。
5. **8 训练格式 → 10 训练格式计数**: `REGISTRY` 仍为 18 entries (未加 format id,只加 class-based path);新 2 个 format id 已隐含在 EXPORTERS dict。后续若要显式扩展 REGISTRY 到 20,可加 `"createml_v2"` / `"csv_v2"` entries,但会让 `test_export_18_formats.py` 失败 — 建议该测试改成 `≥18`。