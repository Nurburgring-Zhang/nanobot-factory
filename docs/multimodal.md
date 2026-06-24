# Multimodal Interface (P4-7-W1)

> 12 service 统一多模态接口 (文档/PDF/Office/Email/图像/视频/语音)
> Inspired by **Google Flow Agent** + **Gemini Omni** — every service accepts 6 input
> modalities and returns 3 output kinds through one canonical contract.

## TL;DR

| Service (12) | Endpoint |
|---|---|
| `user_service` | `POST /api/v1/multimodal/process` |
| `asset_service` | `POST /api/v1/multimodal/process` |
| `search_service` | `POST /api/v1/multimodal/process` + RAG |
| `annotation_service` | `POST /api/v1/multimodal/process` |
| `collection_service` | `POST /api/v1/multimodal/process` |
| `cleaning_service` | `POST /api/v1/multimodal/process` |
| `dataset_service` | `POST /api/v1/multimodal/process` |
| `evaluation_service` | `POST /api/v1/multimodal/process` |
| `notification_service` | `POST /api/v1/multimodal/process` |
| `scoring_service` | `POST /api/v1/multimodal/process` |
| `workflow_service` | `POST /api/v1/multimodal/process` |
| `agent_service` | `POST /api/v1/multimodal/process` |

All 12 services expose the **same** 4 endpoints, sharing one adapter,
one parser, and one 1024-dim embedder.

## Architecture

```
                  +-------------------------+
   raw input ───▶ |   MultiModalParser      | → MultimodalDocument
                  +-------------------------+
                              │
                              ▼
                  +-------------------------+
                  |   MultiModalEmbedder    | → 1024-dim vector
                  +-------------------------+
                              │
                              ▼
                  +-------------------------+
                  |  MultimodalAdapter      | (shared by 12 services)
                  +-------------------------+
                              │
                              ▼
   response  ◀──  text | structured_json | multimodal_response
```

### Components

| File | Purpose |
|---|---|
| `backend/imdf/multimodal/parser.py` | `MultiModalParser` — parses 6 input modalities into `MultimodalDocument` (text + segments + images + tables + metadata). |
| `backend/imdf/multimodal/embedding.py` | `MultiModalEmbedder` — encodes 5 modalities into a unified 1024-dim vector space (CLIP-style alignment). Persists to `multimodal_embeddings` (PG/vector) when available. |
| `backend/common/multimodal_adapter.py` | `MultimodalAdapter` — shared by all 12 services. Routes by modality, dispatches to per-modality handlers, and composes the output envelope. |
| `backend/services/search_service/multimodal_rag.py` | `MultimodalRAG` — cross-modal retrieval + LLM answer synthesis. |
| `backend/services/search_service/multimodal_routes.py` | FastAPI routes mounted on search_service: parse/embed/process/search-multimodal/rag. |
| `tests/multimodal/test_parser.py` (12 tests) | Parser unit tests. |
| `tests/multimodal/test_embedding.py` (8 tests) | Embedder unit tests. |
| `tests/multimodal/test_rag.py` (7 tests) | RAG unit tests. |
| `tests/multimodal/test_12service_adapter.py` (8 tests) | 12 service adapter smoke. |

## Input modalities (6)

| Modality | MIME / extension | Parser | Embedder |
|---|---|---|---|
| `text` | `text/plain`, `.txt` | paragraph split + char-trigram | token-hash + char-trigram (1024-dim) |
| `image` | JPEG/PNG/WEBP/GIF/BMP | PIL verify + dimensions + pytesseract OCR | DCT-pHash + color + edge + tile-grid |
| `video` | MP4/AVI/MOV/MKV/WEBM | OpenCV probe + keyframe extraction | mean of per-frame image embeddings |
| `audio` | MP3/WAV/FLAC/M4A/OGG | WAV decode + Whisper ASR | energy + ZCR spectral fingerprint |
| `document` | PDF/DOCX/XLSX/PPTX/MD/HTML | pdfplumber / python-docx / openpyxl / python-pptx / BeautifulSoup | mean of segment + table embeddings |
| `email` | EML/MSG/MBOX | email parser + attachment extraction | mean of text + image attachments |
| `multimodal_mix` | any | composite | per-modality then mean |

## Output kinds (3)

| Output kind | Use case |
|---|---|
| `text` | chat / answer / summary |
| `structured_json` | classification / tagging / analysis result |
| `multimodal_response` | full document (text + images + tables + metadata) |

## Quick start

```bash
# 1) Parse any of 6 input modalities
curl -X POST http://localhost:8011/api/v1/multimodal/parse \
  -H 'Content-Type: application/json' \
  -d '{"base64":"<...png...>", "filename":"x.png"}'

# 2) Embed a single item
curl -X POST http://localhost:8011/api/v1/multimodal/embed \
  -H 'Content-Type: application/json' \
  -d '{"modality":"text","text":"blue sky","entity_type":"asset","entity_id":"a1"}'

# 3) Unified process (6 input / 3 output)
curl -X POST http://localhost:8011/api/v1/multimodal/process \
  -H 'Content-Type: application/json' \
  -d '{"modality":"text","text":"hello","output_kind":"text"}'

# 4) Cross-modal RAG
curl -X POST http://localhost:8011/api/v1/search/multimodal/rag \
  -H 'Content-Type: application/json' \
  -d '{"text":"展示蓝色天空的视频","top_k":3}'
```

## Routing table

The adapter routes each modality to the canonical handler:

| Modality | Default service |
|---|---|
| `image` (人脸照片) | `user_service` |
| `image_classify` | `asset_service` |
| `video` | `asset_service` |
| `audio` | `annotation_service` |
| `document` | `search_service` |
| `email` | `notification_service` |
| `text` | `search_service` |
| `multimodal_mix` | `search_service` |

(See `common.multimodal_adapter.MODALITY_ROUTING` for the live table.)

## Storage

* **In-process** (default): `MultimodalStore` in `common.multimodal_adapter`.
* **PG/vector** (when `PG_DSN` is set): table `multimodal_embeddings` with
  `entity_type`, `entity_id`, `modality`, `vector vector(1024)`, `metadata JSONB`,
  and `created_at timestamptz`. The embedder transparently upserts each record.

## Testing

```bash
pytest tests/multimodal/ -v
# 35 passed, 5 warnings in 12.43s
```

| Test file | Tests | Coverage |
|---|---|---|
| `test_parser.py` | 12 | detect_modality, PDF/DOCX/XLSX/MD/HTML/TXT/PNG/WAV/AVI/EML + batch |
| `test_embedding.py` | 8 | 1024-dim, 5 modalities, similar-cluster, batch, top-k search |
| `test_rag.py` | 7 | reranker, modal bonus, RAG w/ citations, real payload, template + callback LLM, empty |
| `test_12service_adapter.py` | 8 | 6 modality inputs × 3 output kinds + routing + router endpoints |

## Notes on real models

The embedder tries to use real BGE-M3 (text) and CLIP ViT-B/32 (image) when
`sentence-transformers` + `transformers` are available, but **falls back
deterministically** to a hand-engineered hash+pHash+edge embedder when they
are not (the typical CI / Windows / offline situation).  The fallback still
produces 1024-dim L2-normalised vectors, so retrieval and RAG work
hermetically.
