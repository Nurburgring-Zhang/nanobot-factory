# Multimodal Operator — 声明式多模态检索算子

> **类型**: Declarative operator (声明式算子, 非 runtime)
> **状态**: 已实现 (P4-7-W1)
> **所属模块**: `backend/imdf/multimodal/`
> **版本**: v1.0

## 概述

Multimodal Operator 是智影平台的多模态检索与理解算子。它**不直接执行 LLM 推理**, 而是为上层业务提供**跨模态 embedding / 解析 / RAG / 路由**四类声明式能力。

**核心架构**:

```
┌─────────────────────────────────────────────────────────────┐
│                  Multimodal Operator (声明式)               │
├─────────────────────────────────────────────────────────────┤
│  parsers/        — 多模态文档解析 (PDF / 视频 / 音频)        │
│  embedders/      — 跨模态 embedding (text/image/audio/video) │
│  rag.py          — VectorStore + RAG 检索入口               │
│  routers/        — 模态路由 (按内容类型分发到不同模型)      │
│  multimodal_agent.py — 高级 Agent 接口                     │
├─────────────────────────────────────────────────────────────┤
│         LLM Gateway / Model Gateway (runtime)               │
└─────────────────────────────────────────────────────────────┘
```

**重要边界**: 本模块声明式 — 调用方传入 media ref / text, 本模块返回 parsed / embedded / retrieved 结果, 不调用运行时模型。模型调用走 `engines/model_gateway.py`。

## 子模块

### 1. `parsers/` — 多模态解析

```python
from backend.imdf.multimodal.parsers import parse_media, ParsedMedia

parsed = parse_media(MediaRef(uri="file:///data/report.pdf", kind="document"))
# → ParsedMedia(text="...", chunks=[...], metadata={...})
```

支持模态:

- `text` — 纯文本
- `document` — PDF / Word / Markdown
- `image` — PNG / JPG / WebP
- `audio` — MP3 / WAV
- `video` — MP4 / MOV

### 2. `embedders/` — 跨模态 Embedding

```python
from backend.imdf.multimodal.embedders import MultimodalEmbedder, Embedding

embedder = MultimodalEmbedder()
vec: Embedding = embedder.embed_text("用户查询")
# → Embedding(vector=[...], dim=1024, model="bge-large")
```

接口:

- `embed_text(text: str)` → text embedding
- `embed_image(image_ref: MediaRef)` → image embedding
- `embed_audio(audio_ref: MediaRef)` → audio embedding
- `embed_video(video_ref: MediaRef)` → video embedding
- `cosine(a, b)` → 相似度

### 3. `rag.py` — Multimodal RAG

```python
from backend.imdf.multimodal.rag import MultimodalRAG

rag = MultimodalRAG()
rag.index([parsed1, parsed2, ...])  # 入库

hits = rag.search(query="AI 趋势", top_k=5)
# → List[RetrievedItem] with .score / .chunk / .media

answer = rag.answer(query="...", top_k=5)
# → {"text": "...", "citations": [...]}
```

`MultimodalRAG.answer()` 依赖 LLM 拼接 — 无 LLM 时退化为 top-K 拼接。

### 4. `routers/` — 模态路由

```python
from backend.imdf.multimodal.routers import route_request

route = route_request(media_ref)
# → {"model": "imagebind", "endpoint": "...", "params": {...}}
```

### 5. `multimodal_agent.py` — Agent 接口

```python
from backend.imdf.multimodal.multimodal_agent import MultimodalAgent

agent = MultimodalAgent()
result = await agent.process(query="...", media_refs=[...])
```

高级接口 — 串联 parse + embed + retrieve + answer。

## 数据类型

```python
from backend.imdf.multimodal.types import MediaRef, ModalKind

ref = MediaRef(
    uri="file:///path/to/image.jpg",
    kind=ModalKind.IMAGE,
    metadata={"size": 4096, "format": "jpg"},
)
```

`ModalKind` 枚举: `TEXT / IMAGE / AUDIO / VIDEO / DOCUMENT`

## 声明式 vs Runtime

| 模块 | 角色 |
|------|------|
| `multimodal/*` (本文档) | 声明式 — 描述接口与数据流 |
| `engines/model_gateway.py` | Runtime — 实际调用 embedding/LLM API |
| `agents/builtin/*` | 调用方 — 用 multimodal 接口编排 agent |

**测试建议**: 用 mock 的 `ModelGateway` 注入 embedding 模型, 跑声明式流程。

## 测试

参见 `tests/unit/test_multimodal_rag.py`。

## 已知约束

1. 内存 VectorStore — 生产环境需替换为 Milvus/Qdrant
2. `parse_media` 对损坏文件抛 `ParseError`, 调用方需 try/except
3. `MultimodalRAG.answer` 在无 LLM 时降级 — 不保证语义质量