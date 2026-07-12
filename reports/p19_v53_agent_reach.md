# P19 v5.3 — V5 第32章 Agent Reach 互联网能力

## 概览

实现 V5 第32章 "Agent Reach" — Agent 互联网能力统一接入层, 14 个渠道 (web/twitter/youtube/bilibili/reddit/xiaohongshu/github/rss/exa_search/linkedin/instagram/wechat/douyin/zhihu) 背后暴露 3 个核心操作: `fetch` / `search` / `health_check`。TTLCache(max_size=5000, ttl=300s) 跨渠道共享, 默认 search channels = `[exa_search, web, reddit, twitter]`, fan-out via `asyncio.gather(return_exceptions=True)`。

## 文件清单 + LOC

| File | LOC | Description |
|---|---:|---|
| `backend/imdf/intelligence/agent_reach/__init__.py` | 24 | package re-exports |
| `backend/imdf/intelligence/agent_reach/schemas.py` | 99 | Pydantic v2 FetchResult / MultiChannelResult / HealthStatus |
| `backend/imdf/intelligence/agent_reach/integration.py` | 301 | AgentReachIntegration + CHANNELS + DEFAULT_SEARCH_CHANNELS |
| `backend/imdf/intelligence/agent_reach/channels/__init__.py` | 32 | 14 channel re-exports |
| `backend/imdf/intelligence/agent_reach/channels/web.py` | 101 | **JinaReader — real aiohttp** to https://r.jina.ai/{url} |
| `backend/imdf/intelligence/agent_reach/channels/github.py` | 123 | **GitHubAPI — real aiohttp** to https://api.github.com (with mock fallback) |
| `backend/imdf/intelligence/agent_reach/channels/twitter.py` | 71 | TwitterAPI — 3 deterministic mock tweets per query |
| `backend/imdf/intelligence/agent_reach/channels/youtube.py` | 44 | YouTubeDL — mock video metadata |
| `backend/imdf/intelligence/agent_reach/channels/bilibili.py` | 42 | BilibiliDL — mock BV-id video |
| `backend/imdf/intelligence/agent_reach/channels/reddit.py` | 55 | RedditAPI — 2 mock threads |
| `backend/imdf/intelligence/agent_reach/channels/xiaohongshu.py` | 42 | RedFox — mock 小红书 note |
| `backend/imdf/intelligence/agent_reach/channels/rss.py` | 53 | FeedParser — 2 mock entries |
| `backend/imdf/intelligence/agent_reach/channels/exa_search.py` | 59 | ExaSearch — 3 mock semantic results |
| `backend/imdf/intelligence/agent_reach/channels/linkedin.py` | 41 | LinkedInMCP — mock profile |
| `backend/imdf/intelligence/agent_reach/channels/instagram.py` | 41 | Instaloader — mock post |
| `backend/imdf/intelligence/agent_reach/channels/wechat.py` | 41 | WeChatMCP — mock 公众号 article |
| `backend/imdf/intelligence/agent_reach/channels/douyin.py` | 41 | DouyinAPI — mock 抖音 video |
| `backend/imdf/intelligence/agent_reach/channels/zhihu.py` | 41 | ZhihuAPI — mock 知乎 answer |
| `backend/imdf/intelligence/agent_reach/tests/__init__.py` | 1 | tests pkg |
| `backend/imdf/intelligence/agent_reach/tests/test_agent_reach.py` | 415 | **70 pytest tests** |
| `backend/imdf/intelligence/agent_reach/tests/e2e_demo.py` | 47 | E2E example script |
| `backend/imdf/skills/registry.py` *(modified)* | +148 | Added AgentReachSkillSpec + AGENT_REACH_INTERNET_SPEC + 3 export funcs |

**Total**: 22 files, **2,263 LOC** (incl. registry expansion).

## Per-Channel Summary

| Channel | Class | Free | Engine | Real? | Mock Strategy |
|---|---|:-:|---|---|---|
| `web` | JinaReader | ✅ | r.jina.ai | ✅ real aiohttp | n/a (real) |
| `github` | GitHubAPI | ✅ | api.github.com | ✅ real aiohttp | deterministic mock on timeout / non-2xx |
| `twitter` | TwitterAPI | ❌ | — | mock | 3 tweets with stable hash-derived IDs |
| `youtube` | YouTubeDL | ✅ | — | mock | 1 video meta with stable video_id |
| `bilibili` | BilibiliDL | ✅ | — | mock | BV-id-style video |
| `reddit` | RedditAPI | ✅ | — | mock | 2 threads per query |
| `xiaohongshu` | RedFox | ❌ | — | mock | 1 note per query |
| `rss` | FeedParser | ✅ | — | mock | 2 feed entries |
| `exa_search` | ExaSearch | ❌ | — | mock | 3 semantic results with score |
| `linkedin` | LinkedInMCP | ❌ | — | mock | 1 profile stub |
| `instagram` | Instaloader | ✅ | — | mock | 1 post per query |
| `wechat` | WeChatMCP | ❌ | — | mock | 1 公众号 article |
| `douyin` | DouyinAPI | ❌ | — | mock | 1 aweme video |
| `zhihu` | ZhihuAPI | ❌ | — | mock | 1 answer per question |

Free count: 7 / 14 (web, github, youtube, bilibili, reddit, rss, instagram).

## Test count

**70 pytest tests** (all passing) — breakdown:

| Class | # tests | Coverage |
|---|---:|---|
| `TestSchemas` | 5 | FetchResult defaults / with-error / to_dict; MultiChannelResult.summary; HealthStatus defaults |
| `TestChannelRegistry` | 5 | CHANNELS count = 14, required keys, uniqueness, full set, DEFAULT_SEARCH_CHANNELS |
| `TestIntegrationFetch` | 16 | All 14 channels parametrized + 2 error paths (unknown channel / handler exception) |
| `TestIntegrationCache` | 4 | Cache miss→hit, failure not cached, per-channel isolation, cache_info |
| `TestIntegrationSearch` | 4 | Default channels, custom channels, unknown channel raises, partial failure |
| `TestHealthCheck` | 3 | All healthy, 1 error, returns Dict[str, HealthStatus] |
| `TestHandlersDirect` | 28 | All 14 handlers × {fetch returns FetchResult, ping returns bool} |
| `TestIntegrationHelpers` | 5 | list_channels / is_free (true/false/unknown) / initial health_status empty |

**Verify command**:
```
cd backend
D:\ComfyUI\.ext\python.exe -m pytest imdf/intelligence/agent_reach/tests/ -v --tb=short
# 70 passed
```

## E2E Example

`search "AI safety" on 4 channels` → MultiChannelResult with 4 FetchResults:

```
=== E2E Example: search 'AI safety' on 4 channels ===
Type: MultiChannelResult
Query: AI safety
Channels: ['exa_search', 'web', 'reddit', 'twitter']
Total: 4
Success: 4
Error: 0
Elapsed ms: 1.00

  - exa_search: success=True content='mock-exa_search-AI safety' engine='exa_search-mock'
  - web:        success=True content='mock-web-AI safety'        engine='web-mock'
  - reddit:     success=True content='mock-reddit-AI safety'     engine='reddit-mock'
  - twitter:    success=True content='mock-twitter-AI safety'    engine='twitter-mock'

Cache info: {'size': 4, 'max_size': 5000, 'ttl': 300}
```

Run: `D:\ComfyUI\.ext\python.exe backend/imdf/intelligence/agent_reach/tests/e2e_demo.py`

## Skill Registration

Modified `backend/imdf/skills/registry.py` to add:

```python
@dataclass
class AgentReachSkillSpec:  # dataclass + to_dict()
AGENT_REACH_INTERNET_SPEC = AgentReachSkillSpec(
    skill_id="agent_reach_internet",
    name="Agent Reach Internet",
    category="internet_access",
    function="agent_reach_internet",
    function_ref=_run_agent_reach_skill,  # sync wrapper using asyncio.run
    version="5.3.0",
    enabled=True,
    inputs_schema={"query": str, "channels": List[str] (optional)},
    outputs_schema={"query", "channels", "total", "success_count", "error_count", "elapsed_ms", "results"},
    dependencies=[AgentReachIntegration, schemas],
)

list_agent_reach_skills() -> List[AgentReachSkillSpec]
get_agent_reach_skill(skill_id) -> AgentReachSkillSpec  # KeyError on miss
```

Usage:
```python
from imdf.skills.registry import get_agent_reach_skill
spec = get_agent_reach_skill("agent_reach_internet")
result = spec.function_ref(query="AI safety")
# → {query, channels, total, success_count, error_count, elapsed_ms, results: {ch: FetchResult dict}}
```

## Design Decisions

1. **TTLCache key**: `(channel, query, tuple(sorted(kwargs.items())))` — JSON-comparable,
   supports both URL-style and keyword-style queries.
2. **Cache invalidation**: cache hits return `cached.model_copy(update={"cached": True})`
   so the original cached object is not mutated, and prior caller-held references
   are safe.
3. **Failure not cached**: only successful FetchResults are stored to avoid pinning
   transient errors for 300s.
4. **Lazy handler import**: `importlib.import_module(cfg["module"])` inside `_get_handler`
   — keeps package import cost low; 14 handlers only loaded when used.
5. **Mock deterministic hashes**: every mock channel derives IDs/scores from
   `hashlib.md5(query)[:n]` so the same query always returns the same payload
   (important for cache and test reproducibility).
6. **Network-resilient**: GitHubAPI mock-fallback on timeout / non-2xx, JinaReader
   wraps `aiohttp` exceptions into FetchResult(success=False, error=...).
7. **No new pip dependencies**: only `cachetools` (already in project), `aiohttp` (already
   in project), `pydantic` (already in project) — confirmed all 3 installed via
   `D:\ComfyUI\.ext\python.exe -c "import cachetools/aiohttp/pydantic"`.

## Integration With Existing Codebase

- Follows the same `SkillSpec` pattern as `RedFoxSkillSpec` / `VidaSkillSpec` —
  no breakage to existing 4 RedFox skills + 1 Vida skill.
- Independent from `backend/agent_reach.py` (a pre-existing module with
  different scope — Panniantong-based architecture). New module lives under
  `imdf.intelligence.agent_reach.*` per V5 doc convention.
- Reuses existing pytest fixtures / `asyncio_mode=auto` from `backend/pytest.ini`.