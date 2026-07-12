# P19-A1: 24 Provider 第 1 批 — 交付报告

**日期**: 2026-07-01
**任务 ID**: P19-A1
**负责 worker**: coder (session mvs_9cd0fdd75dfb4b099d24afc930fbf6c1)
**耗时**: ~25 min

---

## Summary

新建 5 个 AI provider 模块 (claude / deepseek / qwen / doubao_extended / agnes) + 1 个统一 invoke() 入口 + 6 个测试文件 (64 用例)。所有 64 个新测试 PASS, 25 个回归测试 PASS, 合计 **89/89 green**。

Doubao 通过扩展注册 `doubao-seed-1-6` (默认) + `doubao-1-5-vision-pro`; Agnes 作为新免费全模态 provider 加入 `ProviderFamily` 和 `SAMPLE_PROVIDERS`, 价格设为 0 (免费全模态)。

---

## Changed files

### Provider 模块 (新建 — 5)

| File | Class | API | Default Model | 价格 (1M tokens in/out) |
|------|-------|-----|---------------|-------------------------|
| `backend/imdf/providers/claude.py` | `ClaudeProvider` | `https://api.anthropic.com/v1/messages` (x-api-key) | `claude-3-5-sonnet-20241022` | $3 / $15 |
| `backend/imdf/providers/deepseek.py` | `DeepSeekProvider` | `https://api.deepseek.com/v1/chat/completions` (OpenAI 兼容) | `deepseek-chat` | $0.14 / $0.28 |
| `backend/imdf/providers/qwen.py` | `QwenProvider` | `https://dashscope.aliyuncs.com/compatible-mode/v1` (OpenAI 兼容) | `qwen-plus` | $0.40 / $1.20 |
| `backend/imdf/providers/doubao_extended.py` | `DoubaoProvider` (alias `DoubaoExtendedProvider`) | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-1-6-250615` (新) | $0.80 / $2.00 |
| `backend/imdf/providers/agnes.py` | `AgnesProvider` | `https://platform.agnes-ai.com/api/v1` | `agnes-2.0-flash` | **免费** ($0) |

**每个 Provider 类实现的统一 API**:
- `chat(messages, model, temperature, max_tokens) → dict` — 调真 API, 无 key → placeholder (success=False + 明确 error)
- `get_models() → List[dict]` — 模型清单
- `health_check(model) → dict` — 轻量 ping
- `generate_image(prompt, **kwargs)` — 各家不一样 (claude/deepseek: 不支持; qwen: wanx; doubao: seedream; agnes: image-2.1-flash)
- `generate_video(prompt, **kwargs)` — 同上 (claude/deepseek/qwen: 不支持; doubao: seedance; agnes: video-2.0)
- `generate_drama(theme, **kwargs)` — Agnes 独有
- `cost_estimate_usd(prompt_tokens, completion_tokens) → float` — 价格估算
- `has_credentials() → bool`
- Env var 自动加载 (每 provider 列在上面 + 多 env var 兼容 QWEN_API_KEY/DASHSCOPE_API_KEY,DOUBAO_API_KEY/ARK_API_KEY)

### 集成层 (新建 / 修改)

- **新建** `backend/imdf/providers/p19a1_entry.py` — **隔离 invoke 入口** (命名带 P19-A1 前缀,避免并发 worker 覆盖):
  - `invoke(model, messages|prompt, *, temperature, max_tokens, fallback=True)` — 统一路由 + fallback chain
  - `list_all_providers() → {family: instance}` — 5 个 provider 实例
  - `get_provider_by_family(family)` — 按 family 取实例
  - 12+ 个模型别名映射 (claude-3-5-sonnet / deepseek-coder / qwen-vl-plus / doubao-seed-1-6 / agnes-drama-1.0 等)
  - family 前缀推断 ("claude:custom-model" / "deepseek:..." 格式)

- **修改** `backend/imdf/providers/__init__.py`:
  - export 5 个 Provider class (`ClaudeProvider`, `DeepSeekProvider`, `QwenProvider`, `DoubaoProvider`, `DoubaoExtendedProvider`, `AgnesProvider`)
  - export 3 个入口 (`invoke`, `list_all_providers`, `get_provider_by_family`)
  - 合并 P19-A1 + P19-A2 batch 2 re-exports (gemini/kimi/zhipu/baidu/tencent 子包)

- **修改** `backend/imdf/providers/registry.py`:
  - `ProviderFamily.AGNES = "agnes"` — 新增 family
  - SAMPLE_PROVIDERS 加 agnes 条目 (price=0, modalities={text, image, video, drama}, free=True)
  - doubao 条目升级: `default_model` 改为 `doubao-seed-1-6-250615`, config.models 含 seed-1-6 + 1-5-vision-pro + pro-32k + lite-32k + image_model (seedream) + video_model (seedance)

### Tests (新建 — 6 文件, 64 用例)

| File | 用例数 | 覆盖 |
|------|--------|------|
| `tests/test_claude.py` | 9 | 无 key placeholder / 有 key mock / system message 抽离 / HTTP 错误 / cost |
| `tests/test_deepseek.py` | 8 | 同上 + coder 模型 + health_check |
| `tests/test_qwen.py` | 9 | 同上 + vl-plus + wanx image 端点 + 多 env var |
| `tests/test_doubao_extended.py` | 10 | 同上 + 1-5-vision-pro + seedream image + seedance video + 多 env var |
| `tests/test_agnes.py` | 14 | 无 key placeholder + 4 modality (chat/image/video/drama) + placeholder 路径 + invoke fallback |
| `tests/test_provider_registry.py` | 14 | SAMPLE_PROVIDERS 注册 / ProviderFamily.AGNES / list_all_providers / invoke alias / fallback / 5 价格表 |

**Mocking strategy**: 用 `unittest.mock.patch("httpx.AsyncClient", return_value=mock_client)` 拦截 HTTP 请求, **不发真实网络流量**。 `fake_post(url, **kwargs)` 用 kwargs-only 签名避免与 `mock.post(url, json=body)` 的 args 绑定冲突。

### 已存在 — 回归 (1 文件)

`backend/imdf/tests/test_provider_registry.py` — 25 用例 (openai/claude/deepseek/qwen/doubao/comfyui 协议 + 限流 + 熔断 + 降级 + cost + audit chain) **全部 PASS**。

---

## 测试结果

```
$ pytest imdf/providers/tests/test_claude.py \
         imdf/providers/tests/test_deepseek.py \
         imdf/providers/tests/test_qwen.py \
         imdf/providers/tests/test_doubao_extended.py \
         imdf/providers/tests/test_agnes.py \
         imdf/providers/tests/test_provider_registry.py -v
  collected 64 items
  64 passed, 1 warning in 1.02s

$ pytest imdf/tests/test_provider_registry.py -v  (回归)
  collected 25 items
  25 passed, 1 warning in 0.75s

总计: 89 passed, 0 failed, 0 errors
```

---

## 用法示例

```python
from providers import invoke, list_all_providers, get_provider_by_family

# 1. 取 provider 实例
claude = list_all_providers()["claude"]
agnes = get_provider_by_family("agnes")

# 2. 直调 chat / image / video / drama
resp = await claude.chat([{"role": "user", "content": "hi"}])
img = await agnes.generate_image("a cat")        # placeholder mode (无 key)
video = await doubao.generate_video("sunset")    # 需真实 ARK api key

# 3. 统一 invoke() — 5 family + fallback chain
r1 = await invoke("claude-3-5-sonnet", prompt="hi")          # → claude
r2 = await invoke("deepseek:deepseek-coder", prompt="fib")   # → deepseek coder
r3 = await invoke("qwen-vl-plus", prompt="describe image")  # → qwen
r4 = await invoke("doubao-seed-1-6", prompt="hi")           # → doubao seed-1-6
r5 = await invoke("agnes-drama-1.0", prompt="urban love")   # → agnes (placeholder)

# 4. fallback chain (family:model 格式)
r = await invoke("claude", prompt="hi", fallback=True)
# → claude (无 key → placeholder) → deepseek (有 key → HTTP 402) → qwen → agnes → doubao
# 返回: {fallback_used: True, fallback_reason: ..., fallback_from: "claude"}
```

---

## Notes

### 多 worker 协作冲突 + 解决

观察到并发期间 P19-A2 batch 2 worker 两次覆写了我的中间产物:
1. **第一次**: `__init__.py` 把 `from .claude import ClaudeProvider` 等等 5 行覆盖
2. **第二次**: `_invoke.py` 把我的 `dict` 版 `list_all_providers()` 改成 `list[dict]` 版

解决方案:
- 把 invoke 入口搬到 **`p19a1_entry.py`** (命名包含任务 ID, 不易踩)。
- 5 个 Provider class 放到独立的 `claude.py` / `deepseek.py` / `qwen.py` / `doubao_extended.py` / `agnes.py` — 这些文件名已被注册,不会被覆盖。
- 测试放在 `imdf/providers/tests/test_<name>.py` — 安全。

最终 `p19a1_entry.py` 作为 invoke() 单一 source of truth, **未再被覆盖**。

### Hard-start v3 验证

```
Set-Location "D:\Hermes\生产平台\nanobot-factory"
Test-Path "backend\imdf\engines\provider_registry.py" → True
Test-Path "backend\imdf\engines\model_gateway.py"     → True
Test-Path "backend\services\agent_service"           → True
Test-Path "reports\VDP-2026-V5-对比差距清单.md"        → True
```
4/4 通过, 不需 abort。

### 已交付 checklist

- [x] `backend/imdf/providers/claude.py`
- [x] `backend/imdf/providers/deepseek.py`
- [x] `backend/imdf/providers/qwen.py`
- [x] `backend/imdf/providers/doubao_extended.py`
- [x] `backend/imdf/providers/agnes.py`
- [x] `backend/imdf/providers/registry.py` (升级 doubao, 加 agnes)
- [x] `backend/imdf/providers/__init__.py` (re-export)
- [x] `backend/imdf/providers/p19a1_entry.py` (invoke 入口)
- [x] `backend/imdf/providers/tests/test_claude.py`
- [x] `backend/imdf/providers/tests/test_deepseek.py`
- [x] `backend/imdf/providers/tests/test_qwen.py`
- [x] `backend/imdf/providers/tests/test_doubao_extended.py`
- [x] `backend/imdf/providers/tests/test_agnes.py`
- [x] `backend/imdf/providers/tests/test_provider_registry.py`
- [x] 64 新测试 + 25 回归 = **89/89 PASS**
- [x] `reports/p19_a1_provider_5a.md` (本文)
- [x] `deliverable.md` (engine check)
