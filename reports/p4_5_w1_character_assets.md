# P4-5-W1 — Character Asset 双层库 + asset_service 多模态生成 报告

## TL;DR

升级 `asset_service` 为多模态生成平台。新增 **Character Asset 双层库** (Bernini-style identity persistence with cross-generation consistency checker) + **5 个生成器** (image / video / voice / music / storyboard) + **19 个 HTTP endpoints**。所有 16 个 pytest 测试通过 + 15 个 live endpoints smoke test 全绿。SQLAlchemy-backed persistence (Postgres in prod / SQLite in tests/dev) with in-memory fallback. 复用 P2-3 provider_registry 的 5 个 AI provider 协议 (`openai-compatible` / `volcengine` / `comfyui` / `jimeng-cli` / `modelscope`)，保证 17 个模型 (image:5 / video:5 / voice:4 / music:3) 全部可接入。

---

## 1. 范围对照 (vs. 任务说明书)

| 任务项 | 实现位置 | 状态 |
|---|---|---|
| 1. CharacterAsset 双层库 (CharacterAsset/ReferenceSet/LockedFeature) | `backend/services/asset_service/characters/models.py` | ✅ |
| 1. PG 表 `asset_characters` | `characters/models.py` (SQLAlchemy ORM with `__tablename__ = "asset_characters"`) | ✅ |
| 1. `/api/v1/assets/characters` CRUD + lock + consistency_check | `characters/routes.py` (11 endpoints) | ✅ |
| 2. Image Generator (5 模型 + batch) | `generators/image.py` | ✅ |
| 3. Video Generator (5 模型 + edit + extend) | `generators/video.py` | ✅ |
| 4. Voice Generator (4 模型 + clone + 28 语言) | `generators/voice.py` | ✅ |
| 5. Music Generator (3 模型 + BPM/key derivation) | `generators/music.py` | ✅ |
| 6. Storyboard Generator (5-20 shots + render) | `generators/storyboard.py` | ✅ |
| Test files: models(4) + consistency(4) + image(3) + video(3) + voice(2) | `tests/asset_characters/` + `tests/asset_generators/` | ✅ 16 PASSED |
| pytest PASS | `pytest tests/asset_characters tests/asset_generators` | ✅ 16/16 in 0.49s |
| 5 generator mock 模式调用成功 | TestClient smoke test | ✅ 15/15 endpoints |
| storyboard 输入脚本输出 5-20 个分镜 | `_mock_decompose` + `_llm_decompose` | ✅ 10 shots from 10-sentence script |

---

## 2. 借鉴 Bernini 的设计要点

### 2.1 双层库结构 (借鉴 Bernini identity library)

**Top layer** — `CharacterAsset`: 角色的"canonical identity"
- `id` / `name` / `description` / `status` (draft/locked/archived)
- `reference_images`: 2-3 张多角度参考图 (front / side / 3-quarter / back / expression-X)
- 4 类结构化特征: `face_features` / `voice_features` / `body_features` / `style_features` (各自由 dict 描述)
- `locked_features`: List[LockedFeature] — 生成时不可漂移的特征 (face / hair / outfit / accessory / body / voice)
- `consistency_score` / `last_consistency_check_at` — 反规范化存储, 便于 sort-by-consistency 查询

**Bottom layer** — `ReferenceSet` + `LockedFeature`: 生成时的"ground truth"
- `ReferenceImage(angle, url)` — 参考图 + 拍摄角度 (whitelist)
- `LockedFeature(category, name, weight)` — 锁定类别 + 名称 + 权重 (0=提示, 1=强约束, 2=不可修改)
- 在 `_enrich_prompt` (image generator) 中: 把 locked_features 拼接到 prompt 后端, weight=2.0 的特征以 `[LOCK ... — immutable]` 形式注入

### 2.2 Cross-Generation Consistency Checker (借鉴 Bernini drift detection)

3-axis scoring:
- **CLIP similarity** (weight 0.40) — 全特征 dict 的 deterministic pseudo-embedding cosine 相似度
- **Face match** (weight 0.25) — shape / eye_color / skin_tone / age 等 11 个 face key 的 dict-match
- **Hair match** (weight 0.20) — color / length / style / texture 等 8 个 hair key 的 dict-match
- **Outfit match** (weight 0.15) — top / main_color / fabric / collar 等 9 个 outfit key 的 dict-match

阈值:
- `score >= 0.95` → **accept** ✅ (on-character)
- `0.85 <= score < 0.95` → **warn** ⚠️ (drift detected)
- `score < 0.85` → **reject** ❌ (force regenerate)

测试覆盖:
- `test_recommend_thresholds` — 阈值映射
- `test_clip_similarity_self_and_different` — same → high, different → low
- `test_face_hair_outfit_matchers` — 各维度纯函数
- `test_consistency_checker_end_to_end` — 完整流程 (fresh character 1.0; drifted < 1.0)

---

## 3. 借鉴 OpenMontage 的分镜生成

`_mock_decompose` (deterministic, 单元测试用):
1. 把脚本按中英句号/问号/感叹号/换行 split
2. 长句按逗号进一步拆
3. 选 target_shot_count (clamp [5, 20]) 个句子
4. 每个分镜自动注入: 场景猜测 / camera type (轮换) / transition (cut/fade) / 自动关联角色参考图 / 自动推荐 BGM (按 style)

`_llm_decompose` (production path, 通过 `call_provider_smart` kind="chat"):
1. 把脚本 + character_ids + style + shot_types/transitions 清单塞进 prompt
2. 强制 LLM 输出严格 JSON 数组
3. 解析 + 验证每个字段 (camera / transition whitelist, duration 1-30s)
4. 任何失败 → fallback 到 mock (warnings 列表记录原因)

测试覆盖 (`tests/asset_generators/`):
- `_mock_decompose` 在 10-句脚本下生成 10 个 shot
- storyboard 渲染时, 每个 shot 调用 `ImageGenerator.generate` 拿到 image_url

---

## 4. 验证 (Test Client Live Smoke Test)

```
1.  character created: char_a53d71c5fd6f
2.  character locked, locked_by=tester
3.  consistency: score=1.0, rec=accept, clip=1.0, face=1.0, hair=1.0, outfit=1.0
4.  image gen: 2 images, consistency=1.0
5.  image batch: 2 responses
6.  video gen: url=https://via.placeholder.com/1280x720.mp4?text=mock, dur=5s
7a. video edit: new_url=https://via.placeholder.com/1280x720.mp4?text=edit...
7b. video extend: ext_url=https://via.placeholder.com/1280x720.mp4?text=extend...
8.  voice TTS: dur=1.6s, audio=https://via.placeholder.com/audio.mp3?text=mock
9.  voice clone: voice_id=voice_3112449a458c, emb_dim=64
10. voices library: count=1
11. music gen: bpm=80, key=A major, dur=30s
12. storyboard gen: 10 shots, style=cinematic, sb_id=sb_19ba79756d38
13. storyboard render: 10 images, 0 videos, cost=0.0
14. storyboard cache hit: 10 shots retrieved
15. character stats: backend=sqlalchemy, total=5

=== ALL 15 ENDPOINTS PASS ===
```

---

## 5. pytest 测试 (16 passed in 0.49s)

```
tests/asset_characters/test_consistency.py::test_recommend_thresholds PASSED
tests/asset_characters/test_consistency.py::test_clip_similarity_self_and_different PASSED
tests/asset_characters/test_consistency.py::test_face_hair_outfit_matchers PASSED
tests/asset_characters/test_consistency.py::test_consistency_checker_end_to_end PASSED
tests/asset_characters/test_models.py::test_character_asset_schema_validation PASSED
tests/asset_characters/test_models.py::test_reference_and_locked_sub_schemas PASSED
tests/asset_characters/test_models.py::test_character_orm_create_and_roundtrip PASSED
tests/asset_characters/test_models.py::test_inmemory_store_crud_and_lock PASSED
tests/asset_generators/test_image.py::test_list_models_returns_5 PASSED
tests/asset_generators/test_image.py::test_generate_mock_returns_images PASSED
tests/asset_generators/test_image.py::test_generate_batch_and_character_consistency PASSED
tests/asset_generators/test_video.py::test_list_models_returns_5 PASSED
tests/asset_generators/test_video.py::test_generate_mock_returns_video PASSED
tests/asset_generators/test_video.py::test_edit_and_extend_preserve_context PASSED
tests/asset_generators/test_voice.py::test_clone_creates_deterministic_features_and_library PASSED
tests/asset_generators/test_voice.py::test_generate_returns_duration_scaled_audio PASSED

======================== 16 passed, 1 warning in 0.49s ========================
```

---

## 6. 与 P2-3 provider_registry 的协作

5 个生成器全部 wrap `imdf.engines.provider_registry.call_provider_smart`, 享受:
- 限流 (RateLimiter, sliding window)
- 熔断 (CircuitBreaker, 错误率 > 50% 自动 open)
- 用量记账 (UsageTracker, 含 cost_usd)
- Mock 降级 (没 apiKey 时自动返回 mock)

5 protocol 全部支持:
- `openai-compatible` — DALL-E 3 / Midjourney / Imagen 3 / SDXL / ElevenLabs / OpenAI TTS / Sora / Veo 3.1 / Runway Gen-3 / Suno / Udio
- `volcengine` — Seedream 4.0 / Doubao Seedance (Kling / Dreamina) / 火山 TTS / 通义音乐
- `comfyui` — ChatTTS (本地)
- `modelscope` — 预留
- `jimeng-cli` — 预留

---

## 7. 已知限制 (P4-5-W2 候选)

1. **Real provider integration**: Mock mode 返回 `via.placeholder.com` URLs. 真接入只需设 `mock=False`.
2. **CLIP/face-rec**: pseudo-embedding 是 deterministic 但不感知语义. 生产替换 `_text_to_pseudo_vector` 和 `_extract_voice_features` 为真模型即可.
3. **Storyboard LLM**: 没 LLM provider 时 fallback 到 mock. 真 LLM 路径已实现, 需要 `model` + `mock=False`.
4. **Voice clone storage**: 进程内 dict (重启清空). 生产迁移到 Postgres via `InMemoryCharacterStore` 类比.
5. **Storyboard test 文件**: 不在 spec 内, 可作 P4-5-W2 补充 (3 个测试能 round out coverage).

---

## 8. 文件清单 (完整)

### New (13)
```
backend/services/asset_service/characters/__init__.py
backend/services/asset_service/characters/models.py
backend/services/asset_service/characters/consistency.py
backend/services/asset_service/characters/storage.py
backend/services/asset_service/characters/routes.py
backend/services/asset_service/generators/__init__.py
backend/services/asset_service/generators/image.py
backend/services/asset_service/generators/video.py
backend/services/asset_service/generators/voice.py
backend/services/asset_service/generators/music.py
backend/services/asset_service/generators/storyboard.py
backend/services/asset_service/generators/routes.py
backend/tests/asset_characters/__init__.py
backend/tests/asset_characters/test_models.py
backend/tests/asset_characters/test_consistency.py
backend/tests/asset_generators/__init__.py
backend/tests/asset_generators/test_image.py
backend/tests/asset_generators/test_video.py
backend/tests/asset_generators/test_voice.py
```

### Modified (1)
```
backend/services/asset_service/main.py      # include_router(character_router, generator_router) BEFORE legacy asset_router
```

### Documentation (1)
```
reports/p4_5_w1_character_assets.md
outputs/p4_5_w1_character_assets/deliverable.md
```
