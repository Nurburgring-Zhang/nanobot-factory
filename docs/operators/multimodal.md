# `imdf.multimodal` — 多模态算子包

> **Status: DECLARATIVE** — This package is a **declarative reference** of the
> multimodal capabilities the platform supports. It exposes pure dataclasses,
> enums, parsers, embedders, and a `routes.py` FastAPI surface — but **does not
> perform runtime training, data ingest, or production scoring**.
>
> Source: `backend/imdf/multimodal/` (15 Python files)
> Service-level integration: see `docs/multimodal.md`

## Scope

`imdf.multimodal` is the canonical Python package that 12 downstream services
share for cross-modal understanding, generation, and tool-using agents. It
defines:

1. The **modality taxonomy** (7 modalities, 3 output kinds).
2. The **dataclass contract** (`MediaRef`, `UnderstandingRequest`,
   `GenerationRequest`, `AgentRequest`, etc.) every service uses.
3. The **parsers** (`parsers`, `parser`) for image / video / audio / document /
   email / mix.
4. The **embedders** (`embedders`, `embedding`) — including the 1024-dim
   unified CLIP-style space.
5. The **RAG** layer (`rag`) for cross-modal retrieval.
6. The **cross-modal tasks** (`understanding`) — 8 tasks including captioning,
   VQA, retrieval, OCR.
7. The **generation** surface (`generation`) — text→image, text→video,
   text→audio (Bernini-style).
8. The **agent** (`multimodal_agent`) — tool-using multimodal agent.
9. The **FastAPI router** (`routes`) — `/api/v1/multimodal/*` +
   `/api/v1/agent/multimodal`.
10. The **service-integration** smoke tests (`service_integration`).

The package is **fully self-contained**: only Pydantic v2 + FastAPI + stdlib
are required at runtime. Heavy model deps (CLIP, BLIP-2, Whisper, …) are
imported lazily and fall back to deterministic mock implementations when not
installed, so unit tests run hermetically without GPU.

## Module map

| File | Purpose | Status |
|---|---|---|
| `__init__.py` | Public API + lazy re-exports | ✅ |
| `types.py` | Enums (`ModalKind`, `UnderstandingTask`, …) + Pydantic request/response | ✅ |
| `parsers.py` | Per-modality low-level parsers (P4-7-W1) | ✅ |
| `parser.py` | `MultiModalParser` — full document/email/video/audio (P4-7-W1 12-service) | ✅ |
| `embedders.py` | CLIP / AudioCLIP — separate modality-specific encoders | ✅ |
| `embedding.py` | `MultiModalEmbedder` — 1024-dim unified cross-modal space | ✅ |
| `rag.py` | `MultimodalRAG` — retrieval + LLM answer synthesis | ✅ |
| `understanding.py` | `CrossModalUnderstanding` — 8 tasks (caption / VQA / retrieval / …) | ✅ |
| `generation.py` | `CrossModalGeneration` — text→image/video/audio | ✅ |
| `multimodal_agent.py` | `MultimodalAgent` — tool-using multimodal agent | ✅ |
| `service_integration.py` | 12 service smoke helpers | ✅ |
| `routes.py` | FastAPI router — `/api/v1/multimodal/*` | ✅ |

## Modality taxonomy

7 input modalities, all share one parser path and one 1024-dim embedding:

| `ModalKind` value | MIME / extension | Parser | Embedder |
|---|---|---|---|
| `text` | `text/plain`, `.txt` | paragraph split + char-trigram | token-hash + char-trigram |
| `image` | JPEG/PNG/WEBP/GIF/BMP | PIL verify + OCR (pytesseract) | DCT-pHash + color + edge + tile-grid |
| `video` | MP4/AVI/MOV/MKV/WEBM | OpenCV probe + keyframe extraction | mean of per-frame image embeddings |
| `audio` | MP3/WAV/FLAC/M4A/OGG | WAV decode + Whisper ASR | energy + ZCR spectral fingerprint |
| `document` | PDF/DOCX/XLSX/PPTX/MD/HTML | pdfplumber / python-docx / openpyxl / python-pptx / BeautifulSoup | mean of segment + table embeddings |
| `email` | EML/MSG/MBOX | email parser + attachment extraction | mean of text + image attachments |
| `multimodal_mix` | any | composite | per-modality then mean |

3 output kinds:

| `OutputKind` value | Use case |
|---|---|
| `text` | chat / answer / summary |
| `structured_json` | classification / tagging / analysis |
| `multimodal_response` | full document (text + images + tables + metadata) |

## Core dataclass contract

Every downstream service uses these — no service invents its own request shape.

```python
from imdf.multimodal import (
    MediaRef, ModalKind, UnderstandingTask, GenerationTarget, AgentToolName,
    UnderstandingRequest, UnderstandingResponse,
    GenerationRequest, GenerationResponse,
    AgentRequest, AgentResponse,
    MultiModalParser, MultiModalEmbedder,
    MODALITY_TEXT, OUTPUT_JSON, ALL_MODALITIES, ALL_OUTPUT_KINDS,
    UNIFIED_DIM,  # 1024
)
```

`UNIFIED_DIM = 1024` is the contract every embedder MUST honor — services that
swap their own embedder in must project into this dimension or be rejected.

## Cross-modal understanding tasks (`CrossModalUnderstanding`)

8 tasks enumerated in `UnderstandingTask`:

1. `caption` — image / video / audio → descriptive text
2. `vqa` — visual question answering
3. `retrieval` — cross-modal retrieval (text → image / video / audio)
4. `ocr` — image → text
5. `asr` — audio → text
6. `summarization` — document → summary
7. `classification` — image / audio / document → category
8. `grounding` — text → image region bbox

Each task returns a `UnderstandingResponse` with `task`, `outputs`, `confidence`,
and `evidence` (which modality segments informed the answer).

## Generation surface (`CrossModalGeneration`)

`GenerationTarget` enumerates:

- `text_to_image` — Bernini-style text → image
- `text_to_video` — text → video (mock fallback when no Replicate/Bernini key)
- `text_to_audio` — text → music / TTS
- `image_to_image` — image editing (Bernini-style)
- `video_to_video` — video style transfer
- `audio_to_audio` — voice conversion

`GenerationRequest` carries `prompt`, `media_refs` (optional conditioning
inputs), `target`, `params` (model name, size, seed). `GenerationResponse`
returns `asset_ids` (registered in `asset_service`).

## Agent surface (`MultimodalAgent`)

`AgentToolName` enumerates the multimodal agent's tools:

- `multimodal_understand` (delegate to `CrossModalUnderstanding`)
- `multimodal_generate` (delegate to `CrossModalGeneration`)
- `multimodal_retrieve` (delegate to `MultimodalRAG`)
- `multimodal_embed` (delegate to `MultiModalEmbedder`)
- `asset_search`, `asset_register` (delegate to `asset_service`)

`AgentRequest` is `{ goal, context, tool_budget, model }`. `AgentResponse`
carries `steps[]` (each tool invocation with inputs/outputs) + `final_answer`.

## Routes (`routes.py`)

FastAPI router mounted on `imdf`'s main app:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/multimodal/parse` | parse input → `MultimodalDocument` |
| `POST` | `/api/v1/multimodal/embed` | embed → 1024-dim vector |
| `POST` | `/api/v1/multimodal/process` | end-to-end (parse + embed + understand) |
| `POST` | `/api/v1/multimodal/search` | cross-modal retrieval |
| `POST` | `/api/v1/multimodal/rag` | RAG answer synthesis |
| `POST` | `/api/v1/multimodal/generate` | text→image/video/audio |
| `POST` | `/api/v1/agent/multimodal` | multimodal agent run |

All routes are **declarative**: they expose the package's capabilities over
HTTP. They do NOT perform background training, batch scoring, or data ingest.

## Boundaries — what this package does NOT do

- **No training.** No fine-tuning, no LoRA, no dataset iteration. Training lives
  in `services/training_service/`.
- **No production data ingest.** Ingest lives in `services/asset_service/`,
  `services/dataset_service/`, `services/collection_service/`.
- **No real model inference without explicit provider keys.** Heavy models are
  lazy-imported; if `OPENAI_API_KEY` / `REPLICATE_API_TOKEN` are not set, the
  package uses deterministic mocks (good for tests, NOT for production).
- **No persistence.** Embeddings computed here are returned in the response;
  long-term storage is the caller's responsibility (typically `asset_service`
  or `search_service`).

## When to use

- Building a service that needs to accept image / video / audio / document
  inputs and produce structured outputs.
- Adding a new cross-modal task: extend `UnderstandingTask`, implement the
  handler in `understanding.py`, document it here.
- Wiring a new provider (Replicate, Bernini, OpenAI, local): implement the
  adapter, register it in `generation.py`, expose a `params["provider"]` knob.

## When NOT to use

- For high-throughput batch training — wrong layer.
- For pipeline orchestrations (Celery, Airflow) — wrong layer; this package is
  a synchronous library surface.
- For direct DB access — call `services/*` instead.

## Cross-references

- `docs/multimodal.md` — 12-service integration overview (consumer view).
- `docs/operators/filter.md` — sibling operator doc (declarative eval engine).
- `backend/tests/multimodal/test_parser.py` (12 tests) + `test_embedding.py`
  (8 tests) + `test_rag.py` (7 tests) — canonical usage examples.
