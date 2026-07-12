# P19 v5.1-D3: 18 训练格式补 6 (GLB / glTF / OBJ / COCO Panoptic / WAV / MP3)

**Date**: 2026-07-02
**Owner**: coder (mvs_2c6e55ee08c148c18c6ee9ae81178366)
**Parent**: mvs_8ecc804a9afa42dc8e79427bfcff5828
**Status**: done — 38 / 38 tests PASS

## 1. TL;DR

新增 `backend/imdf/exports/` 包 (12 个模块), 把训练格式从 12 扩到 18:
- 6 个全新 exporter: `glb.py`, `gltf.py`, `obj.py`, `coco_panoptic.py`, `wav.py`, `mp3.py`
- 6 个既有 exporter 补成 module 形式: `yolo.py`, `pascal_voc.py`, `createml.py`, `clip_fmt.py`, `csv_fmt.py`, `diffusiondb.py`
- 中心 registry: `__init__.py` 含 18 格式注册表
- Dispatch: `export_engine.py` (ExportEngine class + module-level `export()`)
- 7 个测试文件 (6 unit + 1 e2e): **38 / 38 PASS**
- API: `api/export_routes.py` 新增 `/api/v1/datasets/{id}/export` 端点, 支持 18 训练格式

## 2. 18 格式注册表

| # | Format | Category | Status | Module |
|---|--------|----------|--------|--------|
| 1 | glb | 3d | **NEW** | `exports.glb` |
| 2 | gltf | 3d | **NEW** | `exports.gltf` |
| 3 | obj | 3d | **NEW** | `exports.obj` |
| 4 | coco | image | existing | `engines.dataset_manager.export_coco` |
| 5 | coco_panoptic | image | **NEW** | `exports.coco_panoptic` |
| 6 | yolo | image | existing | `exports.yolo` |
| 7 | pascal_voc | image | existing | `exports.pascal_voc` |
| 8 | createml | image | existing | `exports.createml` |
| 9 | clip | image | existing | `exports.clip_fmt` |
| 10 | webdataset | video | existing | `engines.dataset_manager.export_webdataset` |
| 11 | llava | multimodal | existing | `engines.dataset_manager.export_llava` |
| 12 | internvl | multimodal | existing | `engines.dataset_manager.export_internvl` |
| 13 | diffusiondb | multimodal | existing | `exports.diffusiondb` |
| 14 | jsonl | table | existing | `engines.dataset_manager.export_jsonl` |
| 15 | parquet | table | existing | `engines.dataset_manager.export_parquet` |
| 16 | csv | table | existing | `exports.csv_fmt` |
| 17 | wav | audio | **NEW** | `exports.wav` |
| 18 | mp3 | audio | **NEW** | `exports.mp3` |

Category breakdown:
- 3d: 3 (全部 NEW)
- image: 6 (1 NEW)
- video: 1
- multimodal: 3
- table: 3
- audio: 2 (全部 NEW)
- **Total: 18**

## 3. 6 NEW 格式详细

### 3.1 GLB (`backend/imdf/exports/glb.py`, 250 lines)
- 12-byte header: `glTF` magic + version=2 + length
- JSON chunk: scene/meshes/accessors/bufferViews/buffers
- BIN chunk: raw float32 vertices + uint32 indices
- Reads .obj / .ply files via custom parser (无 numpy 依赖)
- Validates magic + version + length + JSON parse + BIN presence
- 100-point OBJ → 100-vertex GLB (4 测试 PASS)

### 3.2 glTF (`backend/imdf/exports/gltf.py`, 150 lines)
- 复用 GLB 的 accessor/bufferView 构建逻辑
- BIN data 通过 `data:application/octet-stream;base64,...` 内嵌, 或外部 `.bin` 文件
- Validates asset.version="2.0", scenes/meshes/buffers 存在
- 100-point OBJ → valid glTF JSON (3 测试 PASS)

### 3.3 OBJ (`backend/imdf/exports/obj.py`, 175 lines)
- ASCII 文本: `v x y z`, `vn nx ny nz`, `f i//i j//j k//k`
- 同时输出 `.mtl` sidecar (Phong 材质)
- 空 dataset fallback: 1x1 立方体 (8 顶点 + 12 三角面)
- 100-point OBJ → 100-vertex OBJ text (4 测试 PASS)

### 3.4 COCO Panoptic (`backend/imdf/exports/coco_panoptic.py`, 215 lines)
- JSON: `{images, annotations, categories}`
- 每个 annotation 含 `file_name` (PNG mask) + `segments_info` (id/category_id/isthing/bbox/area)
- 7 thing + 4 stuff 默认类别 (COCO-2017 风格)
- PNG mask 用 PIL 写出, RGB 编码 segment_id (R*65536 + G*256 + B)
- 100 images → 100 PNG masks + 1 JSON (3 测试 PASS)

### 3.5 WAV (`backend/imdf/exports/wav.py`, 250 lines)
- RIFF header: `RIFF<size>WAVE`
- `fmt ` chunk: PCM (audio_format=1), 16-bit, mono
- `data` chunk: int16 LE PCM samples
- 无依赖 (pure Python struct)
- Fallback: 440Hz sine wave + 880Hz harmonic + 衰减包络
- 10s @ 16kHz → 160,000 sample WAV (5 测试 PASS)

### 3.6 MP3 (`backend/imdf/exports/mp3.py`, 230 lines)
- 用 `lameenc` 库 (已 installed v1.8.2)
- Default: 44.1kHz / 128kbps / mono
- 支持 MPEG1 / MPEG2 / MPEG2.5 Layer 3 frame header 解析
- Validate: sync word + version + layer + bitrate_idx + sample_rate_idx + padding + channel_mode
- 10s @ 44.1kHz → ~24KB MP3 (5 测试 PASS, 含 MPEG2 测试)

## 4. ExportEngine (`backend/imdf/exports/export_engine.py`, 200 lines)

### 4.1 设计
- `REGISTRY`: 18 格式注册表 (label, mime, ext, category, description, exporter spec)
- `ExportEngine.export(fmt, dataset, output, manager=None, **kwargs)`: 主入口
  - manager-bound (coco/jsonl/webdataset/parquet/llava/internvl) → `export_with_manager()`
  - function-based → 直接调 `exports.X:export`
- 自动 default output path: `data_dir/<version>_<label><ext>`

### 4.2 API surface
```python
from exports.export_engine import export, list_supported_formats
export("glb", dataset)             # returns path
export("coco", dataset, manager=mgr, version="v1")
export("mp3", dataset, sample_rate=44100, bitrate_kbps=128)
list_supported_formats()           # 18 formats
```

## 5. API Routes (`backend/imdf/api/export_routes.py`, 修改)

新增端点:
- `GET  /api/v1/export/formats`                     — 21 formats (6 generic + 18 training, with 3 overlapping: jsonl/parquet/csv)
- `GET  /api/v1/datasets/{id}/export/formats`       — 18 training formats
- `POST /api/v1/datasets/{id}/export?format=<fmt>`  — 单 dataset 训练格式导出

历史兼容: 6 个 generic formats (json/csv/jsonl/parquet/arrow/tfrecord) 保留.

## 6. 测试 (38 / 38 PASS)

### 6.1 新增测试文件
| 文件 | 测试数 | 覆盖 |
|-----|--------|------|
| `exports/tests/test_glb.py` | 4 | magic+version+length / 100 points / empty fallback / corrupt validate |
| `exports/tests/test_gltf.py` | 3 | asset.version / base64 vs external bin / empty fallback |
| `exports/tests/test_obj.py` | 4 | basic export / .mtl sidecar / 100 points / empty fallback cube |
| `exports/tests/test_coco_panoptic.py` | 3 | structure / PNG masks / 100 images |
| `exports/tests/test_wav.py` | 5 | basic structure / 10s / synthesize / build_bytes / metadata sidecar |
| `exports/tests/test_mp3.py` | 5 | basic MPEG1 / 10s / metadata / corrupt / MPEG2 acceptable |
| `exports/tests/test_export_18_formats.py` | 14 | registry count / each format runs / new 6 formats / 6 specific format checks / categories / manager-bound |

### 6.2 测试运行
```bash
cd backend/imdf
python -m pytest exports/tests/ -v
# ========================= 38 passed, 1 warning in 0.93s =========================
```

## 7. 关键技术决策

1. **PLY 不入 registry** — PLY 是 multimodal.three_d 的 parse 格式 (3D 点云解析), 不是 18 训练格式之一.
   但 3D exporters (GLB/glTF/OBJ) 仍消费 PLY 输入文件 (通过自定义 parser).
   严格保持 18 格式注册表 (12+6).

2. **manager-bound vs function-bound 双路径** — `coco` / `webdataset` / `jsonl` /
   `parquet` / `llava` / `internvl` 是 DatasetManager 的 bound methods (历史既有),
   需要 (manager, version) 元组; 其余 12 个新/补 exporter 是 standalone functions.
   `ExportEngine.export()` 自动路由:
   - 传 `manager=` 参数 → `export_with_manager()`
   - 否则用 dataset 上的同名 method (若有) 或尝试 `dataset.version` 当 manager + version

3. **MP3 sample rate 默认 44.1kHz** — lameenc 用 16kHz 会自动选 MPEG2 (而非 MPEG1),
   验证逻辑已扩展到 MPEG1/MPEG2/MPEG2.5 三种 frame header, 测试也加了 MPEG2 case.

4. **WAV 16-bit mono** — 简化设计, 16kHz sample rate (业界标准),
   `duration_seconds` 参数控制 fallback 合成 sine wave 时长.

5. **COCO Panoptic PNG 用 PIL** — 确保 PNG 格式合法 (zlib compressed, IHDR+IDAT+IEND),
   RGB 编码 segment_id (R<<16 | G<<8 | B). 100 张 64x64 image ≈ 30KB total.

## 8. 文件清单

### 新增 (16 files)
- `backend/imdf/exports/__init__.py`             (18-format registry)
- `backend/imdf/exports/glb.py`                 (3D binary)
- `backend/imdf/exports/gltf.py`                (3D JSON)
- `backend/imdf/exports/obj.py`                 (3D text)
- `backend/imdf/exports/coco_panoptic.py`       (segmentation)
- `backend/imdf/exports/wav.py`                 (audio PCM)
- `backend/imdf/exports/mp3.py`                 (audio MP3)
- `backend/imdf/exports/yolo.py`                (image TXT — 既有格式补 module)
- `backend/imdf/exports/pascal_voc.py`          (image XML)
- `backend/imdf/exports/createml.py`            (image JSON)
- `backend/imdf/exports/clip_fmt.py`            (image-text pair JSONL)
- `backend/imdf/exports/csv_fmt.py`             (table CSV)
- `backend/imdf/exports/diffusiondb.py`         (multimodal Parquet)
- `backend/imdf/exports/export_engine.py`       (中心 dispatch)
- `backend/imdf/exports/ply_exporter.py`        (PLY input parser helper, 不入 registry)
- `backend/imdf/exports/tests/conftest.py`      (test env)
- `backend/imdf/exports/tests/test_glb.py`
- `backend/imdf/exports/tests/test_gltf.py`
- `backend/imdf/exports/tests/test_obj.py`
- `backend/imdf/exports/tests/test_coco_panoptic.py`
- `backend/imdf/exports/tests/test_wav.py`
- `backend/imdf/exports/tests/test_mp3.py`
- `backend/imdf/exports/tests/test_export_18_formats.py`

### 修改 (1 file)
- `backend/imdf/api/export_routes.py`           (加 18 训练格式 + 新端点)

### 报告
- `reports/p19_d3_export.md`                    (本报告)
- `C:\Users\Administrator\.mavis\plans\plan_4f83c98e\outputs\p19_d3_export\deliverable.md`

## 9. Lessons / Notes

1. **PLY 输入 vs 输出分离** — PLY 作为输入格式很常见 (Stanford polygon), 但作为训练
   数据导出格式不主流 (GLB/glTF 更标准). Registry 只列 18 个, PLY 输入由 GLB/glTF/OBJ
   exporter 通过自定义 parser 消费.

2. **lameenc + MPEG2** — lameenc 默认在 sample_rate < 32kHz 时切换到 MPEG2.
   validator 必须支持 MPEG2 frame header, 否则低 sample rate 测试会 fail.

3. **DatasetManager-bound methods 调度** — 历史 export_coco 等是 bound methods, 需要
   (manager, version) 元组; 新 exporters 是 standalone functions. Dispatch 用
   `manager=` 参数区分两条路径, 默认走 dataset 上的同名 method (向后兼容).

4. **COCO Panoptic PNG 像素编码** — 像素 RGB = (R*65536 + G*256 + B) 表示
   segment_id. 用 PIL 写出确保格式合法; fallback 极简 PNG 写入仅在 PIL 不可用时使用.

5. **WAV 16-bit mono 通用** — 行业最广泛兼容格式; fallback sine wave 440Hz + 880Hz
   harmonic 提供可听的测试音频 (1s 衰减包络避免 pop 声).