# P9-1 — Embedding 模型深度审计 (5 模态 × 1024-d)

**核心文件**: `backend/imdf/multimodal/embedding.py` (653 lines, canonical) + `embedders.py` (146 lines, legacy)
**核心常量**: `UNIFIED_DIM = 1024` (跨模态联合空间, L2 归一化)
**实测**: smoke_p9_1.py → 5/5 模态产出 1024 维向量 ✅

---

## 1. 双 Embedder 并存架构

| 文件 | 维度 | 状态 | 用途 | Lazy Real Model |
|------|------|------|------|------------------|
| `multimodal/embedding.py` | **1024** | canonical (新) | 5 模态统一空间 | BAAI/bge-m3 (text), openai/clip-vit-base-patch32 (image) |
| `multimodal/embedders.py` | **512** | legacy (旧) | CLIP-style 图文对齐 | open_clip ViT-B-32 |

⚠️ **P1 建议**: 长期统一到 `embedding.py` (1024-d, 5 模态, 真实模型), `embedders.py` 标记 deprecated。

---

## 2. 5 模态 Encoder 详解

### 2.1 `_TextEncoder` (token-hash + char-trigram)

```python
# multimodal/embedding.py:85-104
class _TextEncoder:
    """Token-hash + char-trigram TF → 1024-d L2-normalised vector."""

    def encode(self, text: str) -> np.ndarray:
        vec = np.zeros(UNIFIED_DIM, dtype=np.float32)
        if not text:
            return vec
        tokens = _tokenize(text)  # 英文 word + 中文 bigram
        for t in tokens:
            vec[_hash_token(t)] += 1.0
        # char-trigrams as second view
        for i in range(len(text) - 2):
            tri = text[i:i + 3].lower()
            if tri.strip():
                vec[_hash_token("##" + tri, UNIFIED_DIM)] += 0.5
        n = np.linalg.norm(vec) or 1.0
        return vec / n

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)  # 中英文混合

def _tokenize(text: str) -> List[str]:
    """英文 word token + 中文 char-bigram token"""
    out = []
    for m in _TOKEN_RE.findall(text.lower()):
        out.append(m)
        if any("\u4e00" <= ch <= "\u9fff" for ch in m):
            out.extend(m[i:i+2] for i in range(len(m)-1))  # 中文 bigram
    return out

def _hash_token(tok: str, dim: int = UNIFIED_DIM) -> int:
    """md5(token) % dim → bucket index"""
    h = hashlib.md5(tok.encode("utf-8")).digest()
    return struct.unpack(">I", h[:4])[0] % dim
```

**特点**:
- ✅ 中英文双语支持 (正则 + bigram)
- ✅ char-trigram 补强子词召回
- ✅ L2 归一化 → cosine = dot product
- ⚠️ 缺乏 IDF 权重 → 停用词 ("的" "是") 与关键词权重相同

### 2.2 `_ImageEncoder` (pHash + Color + Sobel + Tile)

```python
# multimodal/embedding.py:107-155
class _ImageEncoder:
    """PIL + numpy based image embedding projected to 1024-dim.

    Combines: DCT-pHash(64) + dominant colour histogram(64) +
    Sobel-edge histogram(128) + 8x8 tile-grid DC means(64) →
    replicated to 1024.
    """

    def encode(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.asarray(img.resize((64, 64), Image.BILINEAR), dtype=np.float32) / 255.0

        # 1) DCT-pHash (64 dim) — 感知哈希
        gray = arr.mean(axis=2)
        dct = _dct2d(gray)  # scipy.fftpack.dct
        dct_low = dct[:8, :8].flatten()
        med = np.median(dct_low)
        phash = (dct_low > med).astype(np.float32)

        # 2) Color Histogram (64 dim) — hue/sat 8x8
        h, _ = np.histogramdd(arr.reshape(-1, 3)[:, :2], bins=(8, 8), range=((0, 1), (0, 1)))
        chist = h.flatten().astype(np.float32) / (h.sum() or 1.0)

        # 3) Sobel Edge Histogram (128 dim)
        gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
        gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
        mag = np.sqrt(gx * gx + gy * gy)
        ang = (np.arctan2(gy, gx) + np.pi) % (2 * np.pi)
        ehist, _ = np.histogram(ang, bins=128, range=(0, 2*np.pi), weights=mag)
        ehist = ehist / (ehist.sum() or 1.0)

        # 4) Tile Grid (64 dim) — 8x8 区域均值
        tile = arr.mean(axis=(1, 2)).reshape(8, 8).flatten()

        # concat = 64 + 64 + 128 + 64 = 320 → np.tile 复制到 1024
        feat = np.concatenate([phash, chist, ehist, tile]).astype(np.float32)
        feat = np.tile(feat, UNIFIED_DIM // len(feat) + 1)[:UNIFIED_DIM]
        n = np.linalg.norm(feat) or 1.0
        return feat / n
```

**特点**:
- ✅ 无深度学习依赖, 纯 numpy + PIL
- ✅ pHash 感知相似 (缩放/压缩不变)
- ✅ Sobel 边缘 + Color + Tile 多特征融合
- ⚠️ 320-dim tile 到 1024 是重复, 不是真正的 1024 维特征

### 2.3 `_AudioEncoder` (Energy + ZCR + 1024-bin)

```python
# multimodal/embedding.py:177-220
class _AudioEncoder:
    """Energy-binned spectral fingerprint (1024-dim)."""

    def encode(self, audio_bytes: bytes) -> np.ndarray:
        vec = np.zeros(UNIFIED_DIM, dtype=np.float32)
        # try to decode WAV
        with wave.open(io.BytesIO(audio_bytes), "rb") as w:
            sr = w.getframerate()
            nframes = w.getnframes()
            raw = w.readframes(nframes)
            sampw = w.getsampwidth()

        if sampw != 2 or sr <= 0:
            return _ImageEncoder()._fingerprint_from_bytes(audio_bytes)

        # 64ms frames
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        frame_size = max(1, int(sr * 0.064))
        n_frames = max(1, len(samples) // frame_size)
        frames = samples[:n_frames * frame_size].reshape(n_frames, frame_size)

        # energy + ZCR per frame
        energy = np.sqrt((frames ** 2).mean(axis=1))
        zcr = np.abs(np.diff(np.sign(frames), axis=1)).mean(axis=1)
        feat = energy * 0.7 + zcr * 0.3

        # quantise into 1024 bins (sort + spread)
        order = np.argsort(feat)[::-1]
        for rank, idx in enumerate(order):
            bin_idx = (idx * 17 + rank * 31) % UNIFIED_DIM
            vec[bin_idx] += float(feat[idx])
        return vec / (np.linalg.norm(vec) or 1.0)
```

**特点**:
- ✅ WAV 16-bit 解码
- ❌ 不支持 MP3/FLAC/Opus (直接 fallback 到 _fingerprint_from_bytes)
- ⚠️ 仅能量 + ZCR, 无 MFCC / mel-spectrogram (识别精度有限)
- ⚠️ 排序 bin 映射 (`(idx*17 + rank*31) % 1024`) 不稳定 — 排序改变结果就变

### 2.4 `_DocumentEncoder` (text + tables + images 平均)

```python
# multimodal/embedding.py:223-255
class _DocumentEncoder:
    def encode(self, doc: MultimodalDocument) -> np.ndarray:
        vecs = []
        for seg in doc.segments:
            if seg.text:
                vecs.append(self._txt.encode(seg.text))
        if doc.text:
            vecs.append(self._txt.encode(doc.text))
        for tbl in doc.tables:
            flat = "\n".join("\t".join(r) for r in tbl.rows[:50])
            if flat.strip():
                vecs.append(self._txt.encode(flat))
        for img in doc.images:
            if img.base64:
                try:
                    vecs.append(self._img.encode(base64.b64decode(img.base64)))
                except Exception:
                    pass
        if not vecs:
            return np.zeros(UNIFIED_DIM, dtype=np.float32)
        out = np.mean(np.stack(vecs, axis=0), axis=0)
        return out / (np.linalg.norm(out) or 1.0)
```

**特点**:
- ✅ 多视图融合 (text segments + full text + tables + images)
- ⚠️ 简单平均, 无加权 (table 应权重大, image 权重小)

### 2.5 `_VideoEncoder` (per-frame image 平均)

```python
# multimodal/embedding.py:258-276
class _VideoEncoder:
    def encode(self, doc: MultimodalDocument) -> np.ndarray:
        vecs = []
        for img in doc.images:
            if img.base64:
                try:
                    vecs.append(self._img.encode(base64.b64decode(img.base64)))
                except Exception:
                    pass
        if not vecs:
            return np.zeros(UNIFIED_DIM, dtype=np.float32)
        out = np.mean(np.stack(vecs, axis=0), axis=0)
        return out / (np.linalg.norm(out) or 1.0)
```

**特点**:
- ✅ 简化: video = per-frame image embed 平均
- ❌ 无 temporal modeling (LSTM/transformer/3D-CNN)
- ❌ 无关键帧采样 (全帧平均, 计算成本高)

---

## 3. 真实模型 Registry (Lazy Load)

```python
# multimodal/embedding.py:290-333
_REAL_TEXT_ENC: Optional[Any] = None
_REAL_IMAGE_ENC: Optional[Any] = None
_REAL_PROBED: bool = False

def _try_real_text_encoder() -> Optional[Any]:
    """BAAI/bge-m3 — 多语言 (100+ 语言), 1024-dim, MTEB top-3"""
    import socket
    socket.setdefaulttimeout(0.5)  # 防止 CI 卡死
    try:
        from sentence_transformers import SentenceTransformer
        os.environ.setdefault("HF_HUB_OFFLINE", "0")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")
        model = SentenceTransformer("BAAI/bge-m3", cache_folder=None)
        _REAL_TEXT_ENC = ("bge-m3", model)
        return _REAL_TEXT_ENC
    except Exception:
        _REAL_TEXT_ENC = None
        return None
    finally:
        socket.setdefaulttimeout(None)

def _try_real_image_encoder() -> Optional[Any]:
    """openai/clip-vit-base-patch32 — 图文对齐, 512-dim (需截断/补零到 1024)"""
    try:
        from transformers import CLIPModel, CLIPProcessor
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _REAL_IMAGE_ENC = ("clip-vit-b32", (model, proc))
        return _REAL_IMAGE_ENC
    except Exception:
        _REAL_IMAGE_ENC = None
        return None
```

**特点**:
- ✅ Lazy probe, 失败 fallback 到 hash 版
- ✅ `socket.setdefaulttimeout(0.5)` 防止 CI hang
- ✅ 真实模型 `source_model = "bge-m3" / "clip-vit-b32"` 标识
- ⚠️ `HF_HUB_OFFLINE=0` 强制在线下载, 离线环境会超时 fallback

**离线环境实测** (本任务执行期间):
```
'(MaxRetryError("HTTPSConnectionPool(host='huggingface.co', port=443):
Max retries exceeded... 'Connection to huggingface.co timed out.'))'
thrown while requesting HEAD https://huggingface.co/BAAI/bge-m3/...
```
→ 自动 fallback 到 hash 版, 不影响业务 ✅

---

## 4. 1024-d 验证 (smoke 实测)

```python
# smoke_p9_1.py
from multimodal.embedding import MultiModalEmbedder, EmbeddingRequest
import base64, io
from PIL import Image
import numpy as np
import struct

# Force non-real probe
import multimodal.embedding as _me
_me._REAL_PROBED = True
_me._REAL_TEXT_ENC = None
_me._REAL_IMAGE_ENC = None

e = MultiModalEmbedder()
print(f"MultiModalEmbedder.dim = {e.dim}")  # 1024

# text
r_text = e.encode_one(EmbeddingRequest(entity_id="t1", modality="text", text="一只猫坐在草地上"))
# image (random 64x64 PNG)
...
# audio (1s 440Hz sine WAV)
...
# video (uses image embed for now)
...
# document
doc = MultimodalDocument(doc_id="d1", modality="document", text="test", segments=[...])
r_doc = e.encode_one(EmbeddingRequest(entity_id="d1", modality="document", document=doc))
```

**输出**:
```
=== 5 modality embedders ===
  text  dim=1024 modality=text      source=text-encoder
  image dim=1024 modality=image     source=image-encoder
  audio dim=1024 modality=audio     source=audio-encoder
  video dim=1024 modality=video     source=video-encoder
  doc   dim=1024 modality=document  source=document-encoder:document
=== All dims match UNIFIED_DIM= 1024 ===
  PASS
```

✅ **5/5 模态产出 1024-d L2-normalized 向量**

---

## 5. pgvector HNSW 索引

### 5.1 DDL

```python
# multimodal/embedding.py:567-578
def _maybe_upsert_pg(self, rec: EmbeddingRecord) -> None:
    try:
        import psycopg2
        dsn = (os.environ.get("PG_DSN") or os.environ.get("PGVECTOR_DSN")
               or os.environ.get("DATABASE_URL"))
        if not dsn:
            return  # 静默 skip, 用 in-memory store
        conn = psycopg2.connect(dsn, connect_timeout=2)
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS multimodal_embeddings (
                    id BIGSERIAL PRIMARY KEY,
                    entity_type TEXT, entity_id TEXT,
                    modality TEXT, vector vector(1024),
                    metadata JSONB, created_at TIMESTAMPTZ DEFAULT now()
                )
            """)
            vec_literal = "[" + ",".join(f"{x:.6f}" for x in rec.vector) + "]"
            cur.execute(
                "INSERT INTO multimodal_embeddings "
                "(entity_type, entity_id, modality, vector, metadata) "
                "VALUES (%s,%s,%s,%s::vector,%s::jsonb)",
                (rec.entity_type, rec.entity_id, rec.modality,
                 vec_literal, json.dumps(rec.metadata)),
            )
        conn.commit()
```

### 5.2 HNSW 索引缺失 ⚠️

**问题**: DDL 只 `CREATE TABLE`, **未建 HNSW 索引**, 100k+ 行 cosine 查询性能会崩。

**P1 建议**: 在 `_maybe_upsert_pg` 末尾追加:
```python
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_multimodal_embeddings_hnsw
    ON multimodal_embeddings
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
""")
```

### 5.3 PG 连接管理

- ✅ `connect_timeout=2` 防止 hang
- ✅ `_pg_checked` 标记避免重复探测
- ✅ 失败 fallback 到 in-memory
- ⚠️ 无连接池 (每次 encode 都新建连接)

---

## 6. 缓存策略

| 层 | 实现 | 失效策略 | 命中率 (单进程) |
|----|------|---------|----------------|
| L1 进程内 | `self._store: Dict[str, EmbeddingRecord]` | 无 TTL, 进程退出即丢 | 100% |
| L2 PG pgvector | `multimodal_embeddings` 表 | 无 TTL, 永久 | 多 worker 共享 |
| L3 Redis | ❌ 未实现 | — | — |

⚠️ **P1 缺 Redis**: 跨进程 embedding 缓存可省 BGE-M3 推理开销 (单次 ~200ms), 高 QPS 场景必备。
**建议**: 增加 `RedisEmbeddingCache` 类:
```python
class RedisEmbeddingCache:
    """Cache embedding vectors in Redis with TTL"""
    def __init__(self, redis_client, ttl=3600):
        self.redis = redis_client
        self.ttl = ttl

    def get(self, content_hash: str) -> Optional[List[float]]:
        data = self.redis.get(f"emb:{content_hash}")
        return json.loads(data) if data else None

    def set(self, content_hash: str, vector: List[float]):
        self.redis.setex(f"emb:{content_hash}", self.ttl, json.dumps(vector))
```

---

## 7. 关键问题清单

| 优先级 | 问题 | 影响 | 修复 |
|--------|------|------|------|
| **P0** | `_ImageEncoder` 320-d tile 到 1024 是重复, 不是真正的 1024 维 | 高维稀疏, 余弦相似度区分度低 | 改用 `PCA(320 → 1024)` 或换真模型 |
| **P0** | `_AudioEncoder` 不支持 MP3/FLAC | 大部分音频文件无法处理 | 集成 librosa / pydub |
| **P1** | `pgvector` 表缺 HNSW 索引 | 1M+ 行查询慢 | 加 `CREATE INDEX ... USING hnsw` |
| **P1** | 真实模型加载 0.5s 超时, 离线环境永远 fallback | 生产环境拿到的是 hash 版 | 提前下载到 `.cache/sentence_transformers` |
| **P1** | 无 Redis 跨进程缓存 | 多 worker 重复计算 | 集成 Redis |
| **P2** | `_VideoEncoder` 仅平均, 无 temporal modeling | 长视频检索差 | 加 timeSformer / VideoCLIP |
| **P2** | `_DocumentEncoder` 简单平均 | table/image 应有权重 | 加 attention 加权 |
| **P2** | 双 embedder (512 + 1024) 并存 | API 不一致 | 长期统一到 1024, embedders.py 标 deprecated |

---

## 8. 总结

nanobot-factory 的 embedding 系统 **1024 维 + 5 模态 + L2 归一化** 设计达到 **商业级**,
但当前默认走 **deterministic hash 版** (真实模型 lazy load + 离线 fallback),
生产环境需主动预热 BGE-M3 + CLIP 才能拿到语义级向量。

关键改进路径:
- P0: 真模型预热 + Audio MP3/FLAC 支持
- P1: pgvector HNSW + Redis 缓存
- P2: 长期统一 1024-d, 移除 512-d legacy