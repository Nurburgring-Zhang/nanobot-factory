# P20-B2 — Jobs Crawler (4 channels) — Report

## Summary

Built 4 jobs crawler channels for the nanobot-factory platform under
`backend/imdf/crawler/channels/jobs/`. Each channel is a self-contained
async crawler with: Pydantic v2 `JobPosting` schema, `httpx.AsyncClient` + `BeautifulSoup` parsing,
1 req/sec rate limiting, 4-UA rotation pool, `httpx.MockTransport` testable, and graceful
degradation on network/parse failures. All 59 tests pass in 4.4s.

## Channels delivered

| Channel         | Class                | Domain                    | File             |
|-----------------|----------------------|---------------------------|------------------|
| `lagou`         | `LagouChannel`       | www.lagou.com             | `lagou.py`       |
| `bosszhipin`    | `BossZhipinChannel`  | www.zhipin.com            | `bosszhipin.py`  |
| `zhilian`       | `ZhilianChannel`     | www.zhaopin.com           | `zhilian.py`     |
| `job51`         | `Job51Channel`       | www.51job.com             | `job51.py`       |

## Architecture

### Public API (per task spec)
```python
from imdf.crawler.channels.jobs import LagouChannel, BossZhipinChannel, ZhilianChannel, Job51Channel
from imdf.crawler.channels.jobs import get_channel, list_channels, CHANNEL_REGISTRY

# Async context manager
async with LagouChannel() as ch:
    results = await ch.search("Python 后端", max_results=20)
    # results: List[CrawlResult]  — each has .posting (JobPosting)

# Static parse (offline)
postings = LagouChannel.parse(html_str)
# postings: List[JobPosting]

# Registry
ch = get_channel("lagou", timeout=15.0, rate_limit_rps=0.5)
all_names = list_channels()  # ['bosszhipin', 'job51', 'lagou', 'zhilian']
```

### Core types
- `BaseCrawlerChannel` — abstract base in `_base.py`. Handles httpx client lifecycle,
  UA pool rotation, token-bucket rate limiter, optional robots.txt check, error logging.
- `JobPosting` — Pydantic v2 model: `id, title, company, salary, location, url, source,
  posted_at, description, tags, crawled_at, extra`.
- `CrawlResult` — task-spec return wrapper embedding `JobPosting` + `metadata`.

## Files created

```
backend/imdf/crawler/channels/jobs/
├── __init__.py                  78 lines  — registry + factory + re-exports
├── _base.py                    319 lines  — BaseCrawlerChannel, JobPosting, CrawlResult
├── lagou.py                    189 lines  — LagouChannel
├── bosszhipin.py               160 lines  — BossZhipinChannel
├── zhilian.py                  167 lines  — ZhilianChannel
├── job51.py                    152 lines  — Job51Channel
└── __tests__/
    ├── test_lagou.py           170 lines  — 12 tests
    ├── test_bosszhipin.py      138 lines  — 12 tests
    ├── test_zhilian.py         129 lines  — 12 tests
    ├── test_job51.py           139 lines  — 12 tests
    └── test_registry.py        112 lines  — 11 tests (registry + JobPosting schema)
```

**Total: 11 files, 1765 lines, 59 tests, all passing.**

## Test coverage (per channel)

Each channel has 12 tests, divided into 3 classes:
- `TestXxxParse` (5 tests): `parse()` extracts N postings, field values, empty HTML,
  broken HTML doesn't raise, empty string.
- `TestXxxSearchAsync` (5 tests): `search()` returns results, `max_results` truncation,
  network failure returns `[]`, empty query returns `[]`, Pydantic v2 roundtrip.
- `TestXxxRateLimit` (1 test): `_rate_limiter.acquire()` enforces 0.5s minimum between
  3 consecutive calls (2 rps → ≥0.9s elapsed).

Plus `test_registry.py` (11 tests): registry completeness, factory function, error
handling, inheritance check, schema method presence, Pydantic `JobPosting` roundtrip.

## Test command + result

```bash
$ D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/crawler/channels/jobs/__tests__/ -v
============================= 59 passed, 1 warning in 4.41s ==============================
```

The single warning is a pre-existing `pytest.ini: timeout` config option that pytest
8.3 doesn't recognize (not related to our code).

## Sample queries

All 4 channels work with the same public query interface:

```python
# 1. Quick async search
async with LagouChannel() as ch:
    for r in await ch.search("Python 后端", max_results=10):
        print(r.posting.title, "|", r.posting.company, "|", r.posting.salary)

# 2. Static parse (offline / tests)
html = "<html>...</html>"
for p in ZhilianChannel.parse(html):
    print(p.title, p.url)

# 3. With rate limit + transport override (testing)
async with BossZhipinChannel(
    transport=httpx.MockTransport(my_handler),
    rate_limit_rps=0.5,
    timeout=10.0,
) as ch:
    return await ch.search("数据工程师", max_results=20)

# 4. Iterate all channels
from imdf.crawler.channels.jobs import list_channels, get_channel
import asyncio

async def search_all(q: str, n: int = 5):
    out = {}
    for name in list_channels():
        async with get_channel(name) as ch:
            out[name] = await ch.search(q, max_results=n)
    return out

results = asyncio.run(search_all("AI 工程师"))
```

## Design decisions

1. **Self-contained `_base.py`**: The task spec referenced a `BaseCrawlerChannel` in
   `_schemas.py` that doesn't exist; the existing base classes are in
   `imdf.crawler.base` (BaseCrawler) and `imdf.crawler.channels.__init__` (ChannelCrawler).
   Per "Don't touch other files outside crawler/jobs/" rule, I created a new
   `BaseCrawlerChannel` in `jobs/_base.py` as a minimal ABC tailored to the jobs use case
   (httpx-based, async-first, Pydantic v2 output).

2. **CrawlResult as Pydantic wrapper**: Task spec said `list[CrawlResult]`. I made
   `CrawlResult` a thin Pydantic v2 wrapper that embeds `JobPosting` and adds `metadata`.
   External code can use either `.title`/`.url` (top-level for compat) or
   `.posting.title` (canonical).

3. **Multiple CSS selectors per channel**: Each channel's HTML structure is unstable
   (sites A/B test constantly). I used **3-5 fallback selectors** per channel and
   also a final anchor-based fallback. This keeps `parse()` robust against cosmetic
   redesigns.

4. **Cookie / referer warmup**: Lagou and BOSS both benefit from a warmup request to
   the homepage (sets `X_Anti-Forge_Cookie` etc.). I added light warmup in `_fetch()`
   where needed but kept it optional and non-blocking.

5. **Graceful failure everywhere**: Every `parse()` is wrapped in try/except that
   logs and continues (returns partial results or `[]`). `_fetch()` errors are caught
   and converted to empty string. `search()` is the public API and never raises.

6. **Pydantic v2 strict**: All schema classes use `ConfigDict(extra="allow")` so
   sites can stash extra fields without breaking validation. `model_dump_json()`
   roundtrip is tested.

## Cross-cutting compliance

- ✅ httpx async client (NOT requests)
- ✅ BeautifulSoup HTML parsing
- ✅ Pydantic models for inputs/outputs
- ✅ Proper User-Agent header with 4-UA rotation pool
- ✅ Rate limiting: 1 req/sec default (configurable per channel)
- ✅ Network failures → empty list + log (no exceptions)
- ✅ No API keys required
- ✅ robots.txt check available (off by default, can enable)
- ✅ All 4 channels follow same pattern (consistent `__init__`, `search`, `parse` API)
- ✅ Tests use `httpx.MockTransport` (no real network)
- ✅ Each test file ≥ 4 tests per channel (12 actually)

## Notes for verifier

- **Run tests from backend dir**:
  `D:\ComfyUI\.ext\python.exe -m pytest backend/imdf\crawler/channels/jobs/__tests__/ -v`
  Result: `59 passed in 4.41s`.
- **Real network not required** — all tests use `httpx.MockTransport`.
- **No new dependencies** — only `httpx`, `bs4`, `pydantic` (already installed).
- **No other files touched** — all changes scoped to `channels/jobs/`.
- **Lagou cookie warmup** is best-effort and may be blocked by anti-bot; tests
  inject mock transport so warmup is bypassed. Real production deployment will
  need session cookie management (out of scope for this task).
- **BOSS直聘** has the strictest anti-bot; expect high failure rate in production
  without proxy rotation. Mock tests verify logic; real-world use will need
  proxy + sliding captcha handling.
