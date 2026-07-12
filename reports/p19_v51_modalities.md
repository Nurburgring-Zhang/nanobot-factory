# P19 v5.1-C: 12 业务模态补 4 — 3D / LiDAR / DICOM / Panoptic

**Date**: 2026-07-02
**Owner**: coder (mvs_82c73398ab164daf833e0573e63cf9ab)
**Parent**: mvs_8ecc804a9afa42dc8e79427bfcff5828
**Status**: ✅ done — 78 / 78 tests PASS

## 1. TL;DR

在 `multimodal/` 包内新增 4 个业务模态 (`three_d_pointcloud`, `lidar`, `medical_dicom`,
`panoptic_segmentation`), 全部通过统一 **1024-dim L2-normalised embedding** 接入 RAG,
并扩展 `engines/dataset_manager.py` 支持 4 模态的 dataset 创建、过滤和导出。
新增 5 个测试文件 (含集成测试), 78 个测试全部通过。

## 2. 4 业务模态详细规格

| ID | 中文 / English | 文件扩展名 | canonical_kind | schema 关键字段 |
|----|---------------|-----------|---------------|----------------|
| `three_d_pointcloud` | 三维点云 / 网格 | `.glb`, `.gltf`, `.obj`, `.ply` | document | format, n_vertices, n_faces, has_normals, has_uvs, has_materials, has_textures |
| `lidar` | 激光雷达点云 | `.las`, `.laz`, `.e57` | document | format, version, n_points, point_format, min/max_xyz, has_gps_time, has_rgb, has_classification |
| `medical_dicom` | 医学影像 (DICOM) | `.dcm`, `.dicom` | document | format, modality, rows, columns, bits_allocated, bits_stored, n_frames, patient_id, study_uid, series_uid |
| `panoptic_segmentation` | 全景分割 (COCO Panoptic) | `.panoptic.json`, `.json` | document | format, n_images, n_annotations, n_categories, n_thing_classes, n_stuff_classes, total_segments, categories_sample |

每个模态实现统一的 5 件套:
1. `processor` — bytes/path → `ModalityAsset` (sha256 + 结构元数据 + 文本预览)
2. `validator` — `ModalityAsset` → `{ok, errors, warnings}`
3. `preview` — 短文本摘要 (UI 用)
4. `embedder` — `ModalityAsset` → 1024-dim L2-normalised `list[float]`
5. `schema` — 字典描述结构字段 (供 OpenAPI / docs 自动生成)

## 3. Embedding 策略 (1024-dim 统一空间)

4 模态共用统一 embedding pipeline (`multimodal.embedding`):

* **结构指纹** — 将 schema 关键字段 (vertices / points / rows / n_images 等) 做
  log1p + quantile-bin histogram → 320-dim feature vector (`_statistical_fingerprint`)
* **字节指纹** — sha256 分块 + uint32 hash → 1024-dim (`_hash_fingerprint`)
* **混合** — `0.4 * struct + 0.6 * bytes` (3D), `0.5 * struct + 0.5 * bytes` (LiDAR/DICOM),
  `0.4 * struct + 0.3 * cat_hash + 0.3 * bytes` (Panoptic), 然后 L2-normalise

这保证:
- 同模态的不同文件 → 不同 1024-d 向量
- 跨模态的相同字节不会碰撞 (cat_hash + struct 偏移让 4 模态的"指纹基"自然分离)
- 全部走 `MultimodalRAG` → `VectorStore` → cosine retrieval pipeline

## 4. 集成点

### 4.1 `multimodal/rag.py`
新增:
- `VectorStore.add_business_asset(asset)` — 接收 `ModalityAsset`, 走 modality-specific embedder, fallback 到 unified shim
- `VectorStore.add_business_file(path)` — 一键 ingest
- `MultimodalRAG.index_business_files(paths)` — 批量 ingest

### 4.2 `multimodal/embedding.py`
- `_ref_to_embedding_request` 识别 `meta.modality_id == "three_d_pointcloud|lidar|medical_dicom|panoptic_segmentation"`,
  把它们路由到 `MODALITY_DOCUMENT` 通道, 携带 modality_id 进入 metadata。

### 4.3 `engines/dataset_manager.py`
- `DatasetFile` 新增 `modality_id` 字段 (向后兼容, 老 json 文件无此字段也能加载)
- `SUPPORTED_BUSINESS_MODALITIES = ["three_d_pointcloud", "lidar", "medical_dicom", "panoptic_segmentation"]`
- `_detect_modality_id(path)` — extension-based fallback (业务 registry 不可用时)
- `DatasetManager.add_file()` — 自动 sha256 + size + modality 检测
- `DatasetManager.create_version_from_paths(name, paths)` — 一键创建 version
- `DatasetManager.list_business_modalities()` / `filter_by_modality()` / `modality_summary()`
- 所有 `export_*()` (coco, webdataset, jsonl, parquet) 现在带 `modality_id` 字段
- `create_version` 的 metadata 新增 `modality_breakdown` dict

### 4.4 `multimodal/__init__.py`
import + install 4 模态 → 自动注册到 global registry, 暴露:
`THREE_D_MODALITY_ID`, `LIDAR_MODALITY_ID`, `MEDICAL_MODALITY_ID`, `PANOPTIC_MODALITY_ID`,
`list_modalities()`, `detect_business_modality()`, `embed_asset()`, `process_file()`.

## 5. 测试 (78 PASS)

### 5.1 新增测试文件
| 文件 | 测试数 | 覆盖 |
|-----|-------|------|
| `multimodal/tests/test_three_d.py` | 14 | 4 格式 parse / processor / validator / preview / 1024-d embedder / determinism |
| `multimodal/tests/test_lidar.py` | 12 | LAS 1.4 header / LAZ delegation / E57 / processor / validator / embedder |
| `multimodal/tests/test_medical.py` | 13 | DICOM CS/LO/US/UI elements / magic / processor / validator / embedder |
| `multimodal/tests/test_panoptic.py` | 13 | COCO format / thing+stuff classes / embedder dispatch / determinism |
| `multimodal/tests/test_business_modalities_rag.py` | 9 | registry 完整性 / detect / process dispatch / RAG 集成 / 不同模态 cosine ≈ 0 |

### 5.2 既有测试 (不破坏)
`test_rag.py` 全部 12 测试继续 PASS — 旧的 5 模态 (image/video/audio/document/text) 接口零回归。

### 5.3 测试运行命令
```bash
cd backend/imdf
python -m pytest multimodal/tests/ -v
# ================== 78 passed, 1 warning in 0.25s ==================
```

## 6. 修复的真实 bug (写代码时发现)

1. **LAS bbox destructure bug** — LAS 1.4 spec 顺序是 MaxX/MinX/MaxY/MinY/MaxZ/MinZ,
   原代码按 MaxX/MaxY/MaxZ/MinX/MinY/MinZ 解包 → 修。
2. **DICOM long-VR cursor 偏移** — long VR (OB/OW/OF/SQ/UT/UN) 是 12+length, 不是 8+length,
   原 `4+4+length` 少算 4 字节 → 修。
3. **GLB has_normals 双计数** — fix 后扫 mesh primitives 时 n_vertices / n_faces 双计数,
   加 `if n_vertices == 0` 守卫 → 修。

## 7. 文件清单

### 新增 (9 files)
- `backend/imdf/multimodal/business_modalities.py` — Modality dataclass + registry (核心抽象)
- `backend/imdf/multimodal/three_d.py` — 3D PointCloud 模态 (~290 行)
- `backend/imdf/multimodal/lidar.py` — LiDAR 模态 (~280 行)
- `backend/imdf/multimodal/medical.py` — DICOM 模态 (~280 行)
- `backend/imdf/multimodal/panoptic.py` — Panoptic 模态 (~180 行)
- `backend/imdf/multimodal/tests/test_three_d.py`
- `backend/imdf/multimodal/tests/test_lidar.py`
- `backend/imdf/multimodal/tests/test_medical.py`
- `backend/imdf/multimodal/tests/test_panoptic.py`
- `backend/imdf/multimodal/tests/test_business_modalities_rag.py`

### 修改 (4 files)
- `backend/imdf/multimodal/__init__.py` — import + install 4 模态, 暴露顶层 API
- `backend/imdf/multimodal/rag.py` — `add_business_asset/file` + `index_business_files`
- `backend/imdf/multimodal/embedding.py` — `_ref_to_embedding_request` 路由 4 业务 modality_id
- `backend/imdf/engines/dataset_manager.py` — `modality_id` 字段 + auto-detect + export 扩展

## 8. 下一步 (P19 v5.1-D+)

1. P3 研究材料整合 → 把 14 链接的研究 insight 落到 4 模态的 schema 细化
2. 真实大文件 round-trip (10GB LiDAR / 50GB DICOM) — 现在最小 fixture 只 ~50 bytes
3. 业务模态 → Asset table 落库 (PG / sqlite)
4. UI 层 (DatasetManager.vue) 接入 modality_breakdown 显示

## 9. 验证命令

```bash
# 1. import + 4 模态 instantiate
cd backend && python -c "import imdf.multimodal as m; print([(x.id, x.name) for x in m.list_modalities()])"

# 2. RAG 集成
cd backend/imdf && python -m pytest multimodal/tests/ -v

# 3. dataset_manager 端到端
cd backend/imdf && python -c "from engines.dataset_manager import DatasetManager; print(DatasetManager().list_business_modalities())"
```

全部 PASS。