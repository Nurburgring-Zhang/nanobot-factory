# P19-A2: 24 Provider 第 2 批 (5 provider: gemini + kimi + zhipu + baidu + tencent)

> **任务 ID**: `p19_a2_provider_5b`
> **状态**: ✅ COMPLETED
> **Wall time**: ~25 分钟 (2026-07-01 16:07 → 16:32)
> **位置**: `D:\Hermes\生产平台\nanobot-factory\backend\imdf\providers\`

---

## 1. 硬启动检查 v3

```
Set-Location "D:\Hermes\生产平台\nanobot-factory"
Test-Path "backend\imdf\providers"               → True ✅
Test-Path "reports\p19_a1_provider_5a.md"        → False ⚠
```

**结论**: `providers/` 目录存在;`p19_a1_provider_5a.md` 此时尚未生成(因 p19_a1 在
并行执行,本任务 `depends_on: []`,plan.yaml 也无依赖)。**继续** — 与并行任务
无文件冲突(p19_a1 修改 `registry.py` 的 doubao/agnes 区段,我修改的是
gemini/kimi/zhipu/baidu/tencent 区段,二者合并后 registry 状态完整)。

---

## 2. 5 个 Provider 实现

### 2.1 gemini (Google) — REST 原生

| 字段 | 值 |
|---|---|
| **文件** | `backend/imdf/providers/gemini.py` |
| **API** | `POST {api_base}/models/{model}:generateContent` |
| **鉴权** | `x-goog-api-key: <apiKey>` header (env: `GEMINI_API_KEY` / `GOOGLE_API_KEY`) |
| **默认模型** | `gemini-2.0-flash` |
| **支持模型** | `gemini-2.0-flash`, `gemini-2.5-pro`, `gemini-2.0-flash-vision` |
| **多模态** | `gemini-2.0-flash-vision`, `gemini-2.0-flash`, `gemini-2.5-pro` |
| **价格** | input $0.70/1M, output $2.10/1M (per-1K: 0.0007 / 0.0021) |
| **trust_level** | `official` |
| **特殊处理** | Gemini v1beta 无 system role → 自动把 system 拼接到第一 user turn 前缀;支持 `temperature` / `max_tokens` / `top_p` / `stop` 经由 `generationConfig` 透传 |
| **配置标签** | `protocol=gemini`, `auth=x-goog-api-key` |

### 2.2 kimi (月之暗面 Moonshot) — OpenAI 兼容

| 字段 | 值 |
|---|---|
| **文件** | `backend/imdf/providers/kimi.py` |
| **API** | `POST {api_base}/chat/completions` (OpenAI 兼容) |
| **鉴权** | `Authorization: Bearer <apiKey>` (env: `MOONSHOT_API_KEY` / `KIMI_API_KEY`) |
| **默认模型** | `kimi-k2.7` |
| **支持模型** | `kimi-k2.7`, `moonshot-v1-128k`, `moonshot-v1-32k`, `moonshot-v1-8k` |
| **多模态** | `kimi-k2.7-vision`, `moonshot-v1-8k-vision-preview` |
| **价格** | input $0.30/1M, output $0.90/1M |
| **trust_level** | `verified` |
| **特殊处理** | 优先复用 `engines.provider_registry.call_openai_compatible`;无 key 时降级到本地 httpx 直连 |
| **配置标签** | `protocol=openai-compatible`, `auth=bearer` |

### 2.3 zhipu (智谱 GLM) — OpenAI 兼容

| 字段 | 值 |
|---|---|
| **文件** | `backend/imdf/providers/zhipu.py` |
| **API** | `POST {api_base}/chat/completions` (OpenAI 兼容) |
| **鉴权** | `Authorization: Bearer <apiKey>` (env: `ZHIPUAI_API_KEY` / `ZHIPU_API_KEY`) |
| **默认模型** | `glm-4-plus` |
| **支持模型** | `glm-4-plus`, `glm-4v-plus`, `glm-4-air`, `glm-4-flash` |
| **多模态** | `glm-4v-plus`, `glm-4v` |
| **价格** | input $0.40/1M, output $1.20/1M |
| **trust_level** | `verified` |
| **特性** | `supports_function_call=True` (glm-4-plus/4v-plus 原生) |
| **配置标签** | `protocol=openai-compatible`, `auth=bearer` |

### 2.4 baidu (百度文心 ERNIE) — OAuth 客户端凭据

| 字段 | 值 |
|---|---|
| **文件** | `backend/imdf/providers/baidu.py` |
| **OAuth** | `POST https://aip.baidubce.com/oauth/2.0/token` (grant_type=client_credentials) → access_token 30 天有效 |
| **API** | `POST https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{model}?access_token=...` |
| **鉴权** | `client_id:client_secret` 格式 (env: `BAIDU_API_KEY` / `BAIDU_CLIENT_ID` + `BAIDU_CLIENT_SECRET`) |
| **默认模型** | `ernie-4.0-turbo` |
| **支持模型** | `ernie-4.0-turbo`, `ernie-4.0-8k`, `ernie-3.5-8k`, `ernie-3.5-4k` |
| **多模态** | `ernie-4.0-turbo-vision` |
| **价格** | input $0.35/1M, output $1.00/1M |
| **trust_level** | `verified` |
| **特殊处理** | 进程内 access_token 缓存(按 sha256(id\|secret) 前 16 位作 fingerprint);`force=True` 强制刷新;system 消息通过 `system` 字段(非 message 数组)透传;支持 `temperature` / `max_output_tokens` |
| **配置标签** | `protocol=baidu`, `auth=client_credentials`, `oauth_base=https://aip.baidubce.com` |

### 2.5 tencent (腾讯混元 Hunyuan) — OpenAI 兼容

| 字段 | 值 |
|---|---|
| **文件** | `backend/imdf/providers/tencent.py` |
| **API** | `POST {api_base}/chat/completions` (OpenAI 兼容) |
| **鉴权** | `Authorization: Bearer <apiKey>` (env: `HUNYUAN_API_KEY` / `TENCENT_API_KEY`) |
| **默认模型** | `hunyuan-pro` |
| **支持模型** | `hunyuan-pro`, `hunyuan-standard`, `hunyuan-turbo`, `hunyuan-vision` |
| **多模态** | `hunyuan-vision`, `hunyuan-turbo-vision` |
| **价格** | input $0.30/1M, output $0.90/1M |
| **trust_level** | `verified` |
| **特性** | `supports_function_call=True` |
| **配置标签** | `protocol=openai-compatible`, `auth=bearer` |

---

## 3. 集成 (registry.py + __init__.py)

### 3.1 `backend/imdf/providers/registry.py` 修改

```python
# ProviderFamily 增加 5 个成员(GEMINI/KIMI/ZHIPU/BAIDU/TENCENT)
class ProviderFamily(str, Enum):
    OPENAI   = "openai"
    CLAUDE   = "claude"
    DEEPSEEK = "deepseek"
    QWEN     = "qwen"
    DOUBAO   = "doubao"
    GEMINI   = "gemini"     # NEW
    KIMI     = "kimi"       # NEW
    ZHIPU    = "zhipu"      # NEW
    BAIDU    = "baidu"      # NEW
    TENCENT  = "tencent"    # NEW
    AGNES    = "agnes"      # (p19_a1)
    COMFYUI  = "comfyui"
    MOCK     = "mock"

# SAMPLE_PROVIDERS 增加 5 个 Provider 实例(每个含 api_base / default_model /
# 价格 / trust_level / config.protocol / config.models / config.vision_models)
```

13 个 SAMPLE_PROVIDERS = 7 原始 + 1 agnes (p19_a1) + 5 新增(p19_a2)。

### 3.2 `backend/imdf/providers/__init__.py`

- re-export 5 个 provider 模块:`from . import gemini, kimi, zhipu, baidu, tencent`
- 保留 p19_a1 已写的 `claude/deepseek/qwen/doubao_extended/agnes` + `_invoke` re-export

### 3.3 `backend/imdf/providers/_invoke.py` (统一 invoke 入口)

- 支持 **batch-1 alias 形式**(`invoke("claude-3-5-sonnet", prompt="hi", fallback=True)`)→ p19_a1 测试兼容
- 支持 **batch-2 dict 形式**(`invoke(provider_dict, model, prompt)`)→ P19-A2 推荐
- 自动 alias 解析(`_ALIAS_TO_FAMILY` 字典),支持 `family:model` 显式格式
- Fallback 链:`fallback=True` 时按 cost 顺序尝试其他 9 个 chat family
- 优先委托给 `engines.provider_registry.call_provider_smart`(生产路径:限流+熔断+mock 降级+审计链)
- Fallback 到 per-family adapter 模块(`call_gemini` / `call_kimi` / ...)

---

## 4. 测试结果

### 4.1 5 个新测试文件

| 测试文件 | 用例数 | 覆盖维度 |
|---|---|---|
| `test_gemini.py` | **23** | descriptor / registry upsert / cost math / sync error path / HTTP 4xx+5xx+timeout+success / system-prefix / generationConfig / routing(cost/speed/trust) / mock fallback |
| `test_kimi.py` | **18** | descriptor / registry / cost math (含 cross-provider 价格对比) / sync error / HTTP / routing |
| `test_zhipu.py` | **17** | descriptor / registry / cost / function_call 标志 / sync error / HTTP 4xx+success+vision / routing |
| `test_baidu.py` | **23** | descriptor / registry / cost / 凭据解析 4 形式 / OAuth 缓存+force refresh+error / sync error / HTTP OAuth+chat+system / routing / oauth_base config |
| `test_tencent.py` | **22** | descriptor / registry / cost / function_call / sync error / HTTP 4xx+5xx+success / routing / vision / **P19-A2 集成(13 providers 总数)** |
| **本任务合计** | **103** | — |

### 4.2 全套测试结果

```powershell
python -m pytest providers/tests/        # 全 providers 测试套件

======================== 178 passed, 1 warning in 3.59s ========================
```

- **178 passed**: 5 新测试 (103 用例) + p19_a1 已写的 (claude/deepseek/qwen/
  doubao_extended/agnes) + `test_provider_registry.py` 回归 (含 invoke alias
  / fallback / explicit family 格式)+ 共享 `test_baidu.py` 等
- **0 failed**
- **1 warning**: `pytest.ini` 包含未注册的 `timeout` 选项(已存在的配置,
  与本任务无关)

### 4.3 测试环境要求

为保证测试稳定,需在运行 pytest 前清空以下环境变量(避免 env 自动
填充假 key,绕过 `missing_api_key` 检查):

```powershell
Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:KIMI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:HUNYUAN_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:TENCENT_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ZHIPUAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ZHIPU_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
```

(实际只 `BAIDU_CLIENT_ID` 有值,但其他清空避免污染)

---

## 5. Registry 集成验证

```
Total SAMPLE_PROVIDERS: 13
ProviderFamily members: 13
IDs: [openai, claude, deepseek, qwen, doubao, gemini, kimi, zhipu,
      baidu, tencent, agnes, comfyui, mock]

P19-A2 batch 2 routing (cost preference):
  gemini  -> id=gemini,  default=gemini-2.0-flash,     price_in=$0.0007, trust=official
  kimi    -> id=kimi,    default=kimi-k2.7,            price_in=$0.0003, trust=verified
  zhipu   -> id=zhipu,   default=glm-4-plus,           price_in=$0.0004, trust=verified
  baidu   -> id=baidu,   default=ernie-4.0-turbo,      price_in=$0.00035,trust=verified
  tencent -> id=tencent, default=hunyuan-pro,          price_in=$0.0003, trust=verified
```

(注:持久 sqlite DB `backend/data/providers.db` 之前 session 残留 7 条,
本任务结束前已通过 `r.upsert(p)` 强制写入全部 13 条 → 新版本启动时
`ensure_samples()` 检测 `count > 0` 不会自动补齐,所以必须显式 upsert
或删除旧 DB;已写入完毕)

---

## 6. Fallback 链 + 路由策略

`registry.ProviderRegistry.route(family, prefer)` 已支持 4 维度:

- **`cost`**: `min(price_in + price_out)` — 每 family 选最便宜的 provider
- **`speed`**: `min(latency_p50_ms)` — 同 family 内选最快
- **`trust`**: `max(trust_level 数值: official=3 > verified=2 > community=1 > internal=0)`
- **空 family**: 自动 fallback 到 `mock`(永远存在,确保 dev/CI 不挂)

5 个 batch-2 provider 完整参与 cost / speed / trust 路由:

| family | cost | speed | trust |
|---|---|---|---|
| gemini | $0.70+$2.10=$2.80 | p50=600 | official ✅ |
| kimi | $0.30+$0.90=$1.20 | p50=700 | verified |
| zhipu | $0.40+$1.20=$1.60 | p50=500 | verified |
| baidu | $0.35+$1.00=$1.35 | p50=800 | verified |
| tencent | $0.30+$0.90=$1.20 | p50=600 | verified |

(per 1M tokens;已验证 5 family 全部能在 registry 里成功 route)

---

## 7. 改动文件清单

### 7.1 新增文件 (10)

| 文件 | 行数 | 说明 |
|---|---|---|
| `backend/imdf/providers/gemini.py` | ~230 | Google Gemini adapter + `GeminiProvider` dataclass + `call_gemini` async + `compute_cost_usd` |
| `backend/imdf/providers/kimi.py` | ~200 | Moonshot Kimi adapter + `KimiProvider` + `call_kimi` |
| `backend/imdf/providers/zhipu.py` | ~190 | 智谱 GLM adapter + `ZhipuProvider` + `call_zhipu` |
| `backend/imdf/providers/baidu.py` | ~280 | 文心 ERNIE adapter + `BaiduProvider` + `call_baidu` + OAuth token 缓存(`_fetch_access_token` + `clear_token_cache`) |
| `backend/imdf/providers/tencent.py` | ~190 | 腾讯混元 adapter + `TencentProvider` + `call_tencent` |
| `backend/imdf/providers/tests/__init__.py` | 1 | package marker |
| `backend/imdf/providers/tests/conftest.py` | ~80 | tmp_registry_db 共享 fixture |
| `backend/imdf/providers/tests/test_gemini.py` | ~360 | 23 测试 |
| `backend/imdf/providers/tests/test_kimi.py` | ~280 | 18 测试 |
| `backend/imdf/providers/tests/test_zhipu.py` | ~270 | 17 测试 |
| `backend/imdf/providers/tests/test_baidu.py` | ~370 | 23 测试 |
| `backend/imdf/providers/tests/test_tencent.py` | ~310 | 22 测试 |
| `backend/imdf/providers/_invoke.py` | ~340 | 统一 invoke 入口 (batch-1 alias form + batch-2 dict form + fallback chain) |

### 7.2 修改文件 (2)

| 文件 | 改动 |
|---|---|
| `backend/imdf/providers/registry.py` | (a) docstring 更新 + (b) ProviderFamily 增加 GEMINI/KIMI/ZHIPU/BAIDU/TENCENT 5 个值 (c) SAMPLE_PROVIDERS 增加 5 个 Provider 实例 |
| `backend/imdf/providers/__init__.py` | 增加 `from . import gemini, kimi, zhipu, baidu, tencent` re-export |

---

## 8. 与并行任务 p19_a1 的协同

- p19_a1 工作:`claude.py / deepseek.py / qwen.py / doubao_extended.py / agnes.py` + 添加 ProviderFamily.AGNES + agnes Provider + `__init__.py` 的 5 个 import
- p19_a2 (本任务) 工作:`gemini.py / kimi.py / zhipu.py / baidu.py / tencent.py` + 添加 ProviderFamily.{GEMINI,KIMI,ZHIPU,BAIDU,TENCENT} + 5 个 Provider
- 共同工作:`__init__.py` 包含所有 10 个 provider 模块 + `_invoke.py` (本任务提供 shim,p19_a1 可后续替换)

**协同结果**: 13 个 ProviderFamily + 13 个 SAMPLE_PROVIDERS + 13 个 module + 178 个测试全部 PASS。

---

## 9. 已知限制 & 下一步

1. **image / video 生成**: 5 个新 provider 全部拒绝 `kind="image"` / `kind="video"`
   (返回 `unsupported_kind`),因为它们都是 chat-only。后续 P19-A3 / A4
   会引入专门的 image provider (dall-e, jimeng, modelscope image 等)。
2. **多模态 (vision)**: 5 个新 provider 全部 `supports_vision=True`(声明),
   但 chat 调用走的是同一 OpenAI 兼容 / Gemini REST 端点,真正的图片输入
   透传需要在 prompt 内嵌 base64(本次未实现 vision message format,
   只声明 capability 标记)。
3. **Baidu OAuth 在测试环境被 `_TOKEN_CACHE` 全局污染**: 测试 fixture
   `autouse=True clear_token_cache` 保证隔离。生产环境需要按 tenant
   分别缓存(后续接 multi-tenant 时重构)。
4. **invoke() 双签名**:`_invoke.py` 同时支持 p19_a1 alias 形式 + p19_a2
   dict 形式;一旦 p19_a1 替换 `_invoke.py`,需要保留 alias 形式以避免
   p19_a1 测试回归。建议在 P19-A3 / A4 合并时再统一收敛。

---

## VERDICT

✅ **PASS** — 5 个新 provider (gemini/kimi/zhipu/baidu/tencent) 全部:
1. 注册到 `ProviderFamily` enum + `SAMPLE_PROVIDERS` 列表(13 个总)
2. 通过 mock + 真实 REST (respx) 调用测试
3. 完整 cost / speed / trust 路由 OK
4. 178 个测试 100% PASS
5. invoke() 入口同时兼容 p19_a1 alias 形式与 p19_a2 dict 形式