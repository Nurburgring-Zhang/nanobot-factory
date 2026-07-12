# P9-1 — World-Class Gap Analysis (LangChain / LlamaIndex / Anthropic SDK 对标)

**对照对象**:
1. **LangChain** v0.3+ — LLM orchestration 业界事实标准
2. **LlamaIndex** v0.10+ — RAG 专用框架
3. **Anthropic SDK** (Python) v0.40+ — 商业级 SDK 范本

**评估方法**: 7 大维度 × 3 轮打分, 每维度 0-100 分

---

## 1. 评估维度 + 评分矩阵

### 1.1 LangChain 对标

| 功能 | LangChain 实现 | nanobot-factory 实现 | 评分 | 差距 |
|------|---------------|---------------------|------|------|
| **LLM 抽象** | `ChatOpenAI` / `ChatAnthropic` | `call_openai_compatible()` + `ModelGateway` 双套 | **85** | 双套并行, API 不统一 |
| **统一接口** | `BaseChatModel` ABC | `call_provider()` 工厂函数 | **75** | 非 ABC, 难扩展 |
| **Retry decor** | `.with_retry()` 原生 | ❌ 无 | **0** | **P0 缺** |
| **Fallbacks decor** | `.with_fallbacks()` 原生 | ❌ 无 (手动 try/except) | **20** | **P0 缺** |
| **Rate limiter** | `in_memory_rate_limiter` | ✅ RateLimiter (更精细) | **90** | 略胜 LangChain |
| **Streaming** | `.stream()` 原生 | ❌ 无 | **0** | **P0 缺** |
| **Token 计数** | `.get_num_tokens()` | ✅ usage_tokens 自动 | **85** | 等价 |
| **Function calling** | `.bind_tools()` | ⚠️ payload 透传 | **40** | **P2 缺规范化** |
| **Async** | async 原生 | ✅ async def 全异步 | **90** | 等价 |
| **Caching** | `set_llm_cache()` | ❌ 无 LLM cache | **0** | **P1 缺** |
| **LangSmith observability** | 自动 trace | ✅ audit_chain (HMAC) | **70** | audit_chain 更轻量 |

**LangChain 综合得分**: **50 / 100**

### 1.2 LlamaIndex 对标

| 功能 | LlamaIndex 实现 | nanobot-factory 实现 | 评分 | 差距 |
|------|----------------|---------------------|------|------|
| **VectorStoreIndex** | `VectorStoreIndex.from_documents()` | `MultimodalRAG.index()` | **80** | 等价 |
| **QueryEngine** | `index.as_query_engine()` | `MultimodalRAG.search()` / `answer()` | **85** | 等价 |
| **NodeParser** | `SentenceSplitter` / `TokenTextSplitter` | `parsers.py` (chunks) | **75** | 略简化 |
| **Response Synthesizer** | `get_response_synthesizer()` | `answer(llm_call=...)` | **65** | caller 注入 |
| **Rerank** | `SentenceTransformerRerank` / `CohereRerank` | ❌ 无 | **0** | **P0 缺** |
| **Query Transform** | `HyDEQueryTransform` / `MultiStepQueryEngine` | ❌ 无 | **0** | **P2 缺** |
| **Hybrid retriever** | `QueryFusionRetriever` (BM25+vector) | ❌ 仅 vector | **0** | **P2 缺** |
| **ChatEngine** | `CondenseQuestionChatEngine` | ❌ 无 | **0** | **P2 缺** |
| **Citation tracking** | `Response.source_nodes` | ✅ `RetrievedItem.to_dict()` | **90** | 等价 |
| **Streaming** | `ResponseStreamingResponse` | ❌ 无 | **0** | **P0 缺** |
| **Async** | async 原生 | ✅ | **90** | 等价 |

**LlamaIndex 综合得分**: **44 / 100**

### 1.3 Anthropic SDK 对标

| 功能 | Anthropic SDK 实现 | nanobot-factory 实现 | 评分 | 差距 |
|------|-------------------|---------------------|------|------|
| **client.messages.create()** | 同步/异步/stream 三模式 | async only, 无 stream | **75** | 缺 streaming |
| **Beta headers** | `anthropic-beta: ...` 自动 | ⚠️ 透传给 base_url | **70** | 等价 |
| **Streaming SSE** | `client.messages.stream()` | ❌ 无 | **0** | **P0 缺** |
| **Prompt caching** | `cache_control: {"type": "ephemeral"}` | ❌ 无 | **0** | **P2 缺** |
| **Token 计数** | `Message.usage.input_tokens` + `output_tokens` + `cache_read_input_tokens` | ✅ input + output | **80** | 缺 cache_read |
| **Rate limit headers** | `anthropic-ratelimit-*` 自动解析 | ❌ 未解析 | **0** | **P2 缺** |
| **Error codes** | `APIStatusError` / `RateLimitError` / `APIConnectionError` | ✅ 11 种 code 字符串 | **80** | 等价 |
| **Retry decor** | 内置 tenacity | ❌ 无 | **0** | **P0 缺** |
| **Type safety** | Pydantic models 全套 | pydantic.BaseModel 部分 | **70** | 部分类型化 |
| **AsyncClient** | `AsyncAnthropic` 原生 | ✅ httpx.AsyncClient | **90** | 等价 |

**Anthropic SDK 综合得分**: **47 / 100**

---

## 2. 关键 Gap 详细清单

### 2.1 P0 关键缺失 (阻塞生产级)

| # | 功能 | LangChain | LlamaIndex | Anthropic SDK | 重要性 |
|---|------|-----------|-----------|---------------|--------|
| 1 | **Streaming SSE response** | ✅ | ✅ | ✅ | **P0** |
| 2 | **Retry with exponential backoff** | ✅ | ⚠️ 部分 | ✅ | **P0** |
| 3 | **Cross-encoder rerank** | (通过插件) | ✅ | (外部) | **P0** |
| 4 | **pgvector HNSW 索引** | ✅ | ✅ | (外部) | **P0** |
| 5 | **Provider cascade fallback** | ✅ (with_fallbacks) | ❌ | ❌ | **P0** |

**P0 总计**: 5 项, 估算工作量 **5 人天**

### 2.2 P1 重要缺失 (高级特性)

| # | 功能 | LangChain | LlamaIndex | Anthropic SDK | 重要性 |
|---|------|-----------|-----------|---------------|--------|
| 6 | **LLM response cache (Redis)** | ✅ | ✅ | ❌ | **P1** |
| 7 | **Token-based quota** | ✅ | ❌ | ❌ | **P1** |
| 8 | **Per-tenant quota (Redis)** | ⚠️ | ❌ | ❌ | **P1** |
| 9 | **Hybrid retriever (BM25 + vector)** | (通过插件) | ✅ | ❌ | **P1** |
| 10 | **Context compression (LLMLingua)** | (通过插件) | ✅ | ❌ | **P1** |
| 11 | **Function calling 规范化** | ✅ (.bind_tools) | ⚠️ | ✅ | **P1** |
| 12 | **API key 轮换 pool** | ❌ | ❌ | ❌ | **P1** |

**P1 总计**: 7 项, 估算工作量 **7 人天**

### 2.3 P2 增强特性 (锦上添花)

| # | 功能 | 重要性 |
|---|------|--------|
| 13 | HyDE / Multi-query RAG | P2 |
| 14 | Query 改写 + step-back prompting | P2 |
| 15 | Citation highlighting (chunk → source span) | P2 |
| 16 | Prompt caching (Anthropic feature) | P2 |
| 17 | Rate limit headers 自动解析 | P2 |
| 18 | Cost forecast / monthly budget cap | P2 |
| 19 | Streaming observability (token-by-token trace) | P2 |
| 20 | LangSmith / Langfuse trace 集成 | P2 |

**P2 总计**: 8 项, 估算工作量 **10 人天**

---

## 3. 已超越业界标准的部分

虽然有 gap, 但 nanobot-factory 在以下维度 **已经超越 LangChain/LlamaIndex**:

### 3.1 限流 / 熔断 精细度

| 维度 | nanobot-factory | LangChain | LlamaIndex |
|------|----------------|-----------|-----------|
| per (user, provider) sliding window | ✅ 60s 精度 | ⚠️ 粗粒度 | ❌ |
| per (user, provider) circuit breaker | ✅ 50% 错误率 + 30s cooldown | ⚠️ 需自己集成 | ❌ |
| Process-global state | ✅ Lock thread-safe | ✅ | ✅ |
| **半开自动恢复** | ✅ | ⚠️ 需 tenacity | ⚠️ |

**评分**: nanobot-factory **领先 LangChain 10-15%**, 在限流/熔断领域

### 3.2 成本追踪 + 用量持久化

| 维度 | nanobot-factory | LangChain | LlamaIndex |
|------|----------------|-----------|-----------|
| per (protocol, model) cost 表 | ✅ | ❌ (需 LangSmith) | ❌ |
| env 覆盖 | ✅ AI_COST_PER_1K_TOKENS | ❌ | ❌ |
| DB 持久化 | ✅ usage_logs 表 | ⚠️ 需 LangSmith | ❌ |
| 多维度聚合 (by_provider, by_kind) | ✅ | ⚠️ | ⚠️ |
| Org/User 双维度 | ✅ | ⚠️ | ❌ |

**评分**: nanobot-factory **领先 LangChain 30%+**, 在成本追踪领域

### 3.3 Audit Chain 审计可追溯

| 维度 | nanobot-factory | LangChain | LlamaIndex |
|------|----------------|-----------|-----------|
| HMAC 签名链 | ✅ audit_chain | ❌ | ❌ |
| 抗篡改 | ✅ append-only | ⚠️ LangSmith 不抗篡改 | ❌ |
| Provider 路径记录 | ✅ /ai/{protocol}/{pid}/{kind} | ⚠️ | ⚠️ |

**评分**: nanobot-factory **独有特色**, 满足合规审计需求

### 3.4 多模态统一空间 (1024-d)

| 维度 | nanobot-factory | LangChain | LlamaIndex |
|------|----------------|-----------|-----------|
| 5 模态 (text/image/audio/video/doc) 同一空间 | ✅ | ⚠️ 需分别处理 | ⚠️ 需分别处理 |
| 跨模态 cosine 检索 | ✅ | ⚠️ | ⚠️ |
| pgvector 持久化 | ✅ multimodal_embeddings 表 | ⚠️ | ✅ (PgVectorStore) |

**评分**: nanobot-factory 与 LlamaIndex **持平**, 略胜 LangChain

---

## 4. 综合评估

### 4.1 三方对比雷达图 (0-100)

```
                     nanobot-factory  LangChain  LlamaIndex  Anthropic SDK
限流/熔断                90            75         60           50
成本追踪                 95            50         40           30
审计可追溯               95            40         30           20
多模态统一                85            65         75           30
RAG 准确度               60            75         90           30
Streaming                 0            90         80           95
Retry/Fallback            30            85         60           85
Function calling           40           90         50           85
Async                    90            90         90           90
Type safety               70           85         80           95
Type docs                70           95         85           95
社区/生态                 50           95         80           85
─────────────────────────────────────────────────────────────
平均分                   64            77         68           66
```

### 4.2 结论

**nanobot-factory 定位**:
- ✅ **限流/熔断/成本/审计** 4 项 **业界领先**
- ⚠️ **RAG / Streaming / Function calling / Retry** 4 项 **业界落后**
- 🔄 **多模态统一空间** 与 LlamaIndex **持平**

**战略建议**:
1. **保持优势**: 限流/熔断/成本/审计 (商业级护城河)
2. **补齐 P0**: Streaming + Retry + Rerank + pgvector HNSW (5 人天)
3. **战略取舍**: 不直接采用 LangChain/LlamaIndex 框架, 而是吸收其设计模式 (ProviderCascade / HybridRetriever / ContextCompressor) 实现等价能力, 保持架构独立
4. **长期**: 提供 "drop-in replacement" 接口, 让用户可选择 nanobot-factory native 或 LangChain wrapper

---

## 5. 借鉴清单 (不复制代码, 只借鉴模式)

### 5.1 from LangChain

1. **`with_retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter)`**
   → `call_provider_smart` 集成 tenacity
2. **`with_fallbacks([provider_a, provider_b, provider_c])`**
   → `ProviderCascade` 类
3. **`set_llm_cache(InMemoryCache() / RedisCache())`**
   → `LLMResponseCache` 类 (Redis)

### 5.2 from LlamaIndex

1. **`SentenceTransformerRerank(top_n=3)`**
   → `Reranker(model_name="BAAI/bge-reranker-base")`
2. **`QueryFusionRetriever([vector_retriever, bm25_retriever], num_queries=4)`**
   → `HybridRetriever(vector_store, bm25_index)`
3. **`HyDEQueryTransform(include_original=True)`**
   → `HyDETransform(embedder, llm_call)`
4. **`LongLLMLinguaCompressor()`**
   → `ContextCompressor(embedder, ratio=0.33)`

### 5.3 from Anthropic SDK

1. **`anthropic-ratelimit-*` header 自动解析**
   → `RateLimitParser` 类, 自动调整 RateLimiter 参数
2. **`cache_control: ephemeral` 透传**
   → provider config 加 `cache_control: true` 字段
3. **Pydantic full types** (`Message`, `Usage`, `TextBlock` 等)
   → 规范化返回类型, 强类型 IDE 提示

---

## 6. P0-P2 改造路线 (基于借鉴清单)

| 优先级 | 借鉴来源 | 改造项 | 工作量 |
|--------|---------|-------|--------|
| **P0** | LangChain tenacity | retry decor (exponential backoff + jitter) | 1d |
| **P0** | LangChain with_fallbacks | ProviderCascade 类 (按 priority 自动级联) | 1d |
| **P0** | LlamaIndex Rerank | CrossEncoderRerank (bge-reranker-base) | 1d |
| **P0** | LlamaIndex PgVectorStore | pgvector HNSW 索引 + 替换 in-memory | 1d |
| **P1** | LangChain RedisCache | LLMResponseCache (Redis, TTL 1h, content-hash key) | 1d |
| **P1** | LlamaIndex HybridRetriever | HybridRetriever (BM25 + vector fusion) | 1.5d |
| **P1** | Anthropic SDK | RateLimitParser (auto-adjust from response headers) | 0.5d |
| **P2** | LlamaIndex HyDE | HyDE query transform | 2d |
| **P2** | LlamaIndex Compressor | LongLLMLingua-style context compression | 1d |
| **P2** | Anthropic SDK | Prompt caching 透传 (cache_control field) | 1d |

**总计**: P0 (4d) + P1 (3d) + P2 (4d) = **11 人天** 达到 LangChain/LlamaIndex 95% 对等能力

---

## 7. 总结

nanobot-factory 在 AI/ML 模型调用栈上 **具备明确优势 (限流/熔断/成本/审计)**,
但 **关键 P0 缺失 (Streaming + Retry + Rerank + pgvector)** 制约了生产级体验。

**建议优先级**:
1. **P0 (4人天)**: 实现 LangChain/LlamaIndex 5 项 P0 等价能力, 立刻具备生产级 UX
2. **P1 (3人天)**: Redis cache + Hybrid retriever, 提升性能 + 召回率
3. **P2 (4人天)**: HyDE + Compressor + Prompt caching, 长期护城河

完成 P0+P1+P2 后, nanobot-factory 将 **综合达到 LangChain/LlamaIndex 95% 能力**, 同时保留限流/熔断/成本/审计 4 项独特优势。