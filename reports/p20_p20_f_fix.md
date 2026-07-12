# P20-F RSS Fix — 3 channels (rsshub + newsapi + reddit)

**Status**: DONE  
**Test count**: 18 passed (rsshub 6, newsapi 5, reddit 7)  
**Time**: 2026-07-09 ~10:44-10:57 (~13min, well under 20min budget)

## What was built

Three async RSS/news crawler channels, all extending `BaseCrawlerChannel`
from `backend/imdf/crawler/channels/rss/__init__.py` (the 7935B base+registry
shipped from the previous cancelled worker). All channels:

- Use `httpx.AsyncClient` via the shared `_fetch()` helper with 1 RPS throttle
- Gracefully return `[]` on network errors (no exceptions to caller)
- Implement both async `search(query, max_results)` and static `parse(raw)`
- Output unified `CrawledItemModel` (Pydantic v2, 10 fields)

### Channels

| Channel | Source | Endpoint | Notes |
|---------|--------|----------|-------|
| `RsshubChannel` | rsshub.app | `/search/{q}` JSON -> first feed Atom XML | 公开 RSS 聚合 |
| `NewsApiChannel` | newsapi.org | `/v2/everything` (key) or `/search` (metadata) | no-key fallback mode |
| `RedditChannel` | old.reddit.com | `/search.json` | 强校验 UA |

## File list

### Modified
- `backend/imdf/crawler/channels/rss/__init__.py` — fixed broken imports (`..base`/`..config` -> `...`); removed unused `CrawledItem` dataclass import; `_register_all()` now updates `globals()` so channel classes are importable from the package; registry now only registers the 3 built channels (feedly + digg skipped per task spec).

### Created (3 channels)
- `backend/imdf/crawler/channels/rss/rsshub.py` (6089B)
- `backend/imdf/crawler/channels/rss/newsapi.py` (6114B)
- `backend/imdf/crawler/channels/rss/reddit.py` (5039B)

### Created (3 test files + infra)
- `backend/imdf/crawler/channels/rss/__tests__/rsshub_test.py` — 6 tests
- `backend/imdf/crawler/channels/rss/__tests__/newsapi_test.py` — 5 tests
- `backend/imdf/crawler/channels/rss/__tests__/reddit_test.py` — 7 tests
- `backend/imdf/crawler/channels/rss/__tests__/conftest.py` — sys.path shim
- `backend/imdf/crawler/channels/rss/__tests__/pytest.ini` — asyncio_mode=auto

## Test results

```
============================= test session starts =============================
collected 18 items

newsapi_test.py::test_search_with_api_key_returns_articles PASSED        [  5%]
newsapi_test.py::test_search_without_api_key_falls_back_to_public PASSED [ 11%]
newsapi_test.py::test_search_handles_network_errors PASSED               [ 16%]
newsapi_test.py::test_parse_articles_json PASSED                         [ 22%]
newsapi_test.py::test_parse_handles_invalid_json PASSED                  [ 27%]
reddit_test.py::test_search_returns_results PASSED                       [ 33%]
reddit_test.py::test_search_self_post_builds_permalink_url PASSED        [ 38%]
reddit_test.py::test_search_empty_query_returns_empty PASSED             [ 44%]
reddit_test.py::test_search_handles_network_errors PASSED                [ 50%]
reddit_test.py::test_parse_search_payload PASSED                         [ 55%]
reddit_test.py::test_parse_handles_invalid_json PASSED                   [ 61%]
reddit_test.py::test_rate_limit_waits_before_request PASSED              [ 66%]
rsshub_test.py::test_search_returns_results PASSED                       [ 72%]
rsshub_test.py::test_search_empty_query_returns_empty PASSED             [ 77%]
rsshub_test.py::test_search_handles_network_errors PASSED                [ 83%]
rsshub_test.py::test_parse_atom_feed_extracts_entries PASSED             [ 88%]
rsshub_test.py::test_search_handles_invalid_json PASSED                  [ 94%]
rsshub_test.py::test_rate_limit_waits_before_request PASSED              [100%]

============================= 18 passed in 1.20s =============================
```

Run command:
```
python -m pytest backend/imdf/crawler/channels/rss/__tests__/ -v
```

## Implementation notes

- **BaseCrawlerChannel** (already shipped): provides `_fetch(url, headers)` with 1 RPS throttle + UA pool + graceful empty-on-error, plus `_build_item()` helper.
- **RsshubChannel**: 2-step search — first `/search/{q}` JSON returns list of routes, then fetch first route's Atom XML and parse `<entry>` elements via BeautifulSoup.
- **NewsApiChannel**: graceful degradation — when `NEWSAPI_KEY` env var is set, calls real `/v2/everything`; otherwise returns 1 metadata-only result linking to the public search page (`extra.mode = "public-fallback"`).
- **RedditChannel**: hits `old.reddit.com/search.json` and parses `data.children[*].data`. Self-posts (no `url_overridden_by_dest`) get URL synthesized from `permalink`.

## Pre-existing __init__.py issues fixed

The 7935B `__init__.py` from the previous cancelled worker had 3 broken imports:

1. `from ..base import CrawledItem` — `..` from rss resolves to `imdf.crawler.channels`, but `base.py` is at `imdf.crawler.base` -> needed `...base`. Also `CrawledItem` (dataclass) is unused since channels use `CrawledItemModel`.
2. `from ..config import USER_AGENT_POOL, CrawlerConfig, RobotsPolicy` — same problem -> needed `...config`.
3. `from ..config import RateLimitConfig` (inside `_rate_limit_cfg`) — same fix needed `...config`.

Additionally, `_register_all()` previously used `from .X import Y` inside a function — those imports are local to the function, NOT module-level, so `from imdf.crawler.channels.rss import RsshubChannel` failed. Fixed by adding `globals()["X"] = X` after the registration loop.

## Scope compliance

- Did NOT touch any file outside `backend/imdf/crawler/channels/rss/`.
- No new dependencies (httpx 0.27.2, pydantic 2.9.2, beautifulsoup4 already installed).
- Feedly + Digg channels skipped per task instructions.
- 13 min wall-clock vs 20 min budget — no shortcuts, all 18 tests pass cleanly.