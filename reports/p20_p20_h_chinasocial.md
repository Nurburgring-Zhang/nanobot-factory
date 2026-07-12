# P20-H — china_social crawler channels (5 channels)

## Summary

Built 5 china-social crawler channels under
`backend/imdf/crawler/channels/china_social/`. All extend a new
`BaseCrawlerChannel` (with rate-limit + robots.txt + UA rotation),
return Pydantic v2 `CrawlResult` models, and degrade gracefully
(network failure → `[]` + log). **51/51 pytest tests pass in 2.31s**
(no real network, all httpx.MockTransport).

## Channels

| Channel | Class | API target | Public search |
|---|---|---|---|
| `wechatmp` | `WechatMPChannel` | `weixin.sogou.com/weixin?type=2` (Sogou mirror) | yes |
| `weibomp` | `WeiboMPChannel` | `m.weibo.cn/api/container/getIndex` | yes |
| `douyinmp` | `DouyinMPChannel` | `www.douyin.com/aweme/v1/web/search/item` | yes |
| `xigua` | `XiguaChannel` | `www.ixigua.com/api/search` | yes |
| `bilibilimp` | `BilibiliMPChannel` | `api.bilibili.com/x/web-interface/search/type?search_type=bili_user` | yes |

All 5 channels: no API key required, JSON-first with HTML fallback,
Pydantic v2 input (`CrawlSearchRequest`) + output (`CrawlResult`).

## Changed files

```
backend/imdf/crawler/channels/china_social/
  __init__.py                  2234 B   registry + re-exports
  _base.py                    14233 B   BaseCrawlerChannel + CrawlResult + CrawlSearchRequest + UA pool + rate-limit + robots.txt cache
  wechatmp.py                  6178 B   WechatMPChannel — Sogou mirror HTML parse
  weibomp.py                  10577 B   WeiboMPChannel — m.weibo.cn JSON parse
  douyinmp.py                  9568 B   DouyinMPChannel — JSON + _ROUTER_DATA fallback
  xigua.py                     9468 B   XiguaChannel — JSON + __INITIAL_STATE__ fallback
  bilibilimp.py               10173 B   BilibiliMPChannel — bilibili API JSON parse
  __tests__/
    conftest.py                7558 B   shared fixtures + _run() + payload samples
    test_wechatmp.py           5433 B   10 tests (parse × 4, search × 6 incl. robots/rate-limit/sync)
    test_weibomp.py            4890 B   10 tests
    test_douyinmp.py           4921 B   10 tests
    test_xigua.py              4598 B   10 tests
    test_bilibilimp.py         4989 B   10 tests
```

Total: 7 source files (62.4 KB) + 6 test files (32.4 KB).
**51 tests, 51 passed, 0 failed, 0 skipped (2.31s wall).**

## Cross-cutting features

- **`BaseCrawlerChannel`** (`_base.py`): single base class shared by all 5 channels
  - httpx async client (NOT requests); injectable `transport=httpx.MockTransport` for tests
  - User-Agent rotation pool (5 UAs: Chrome Win/Mac, Firefox, Safari, WeChat Android)
  - 1 req/sec rate limit per channel via async token bucket (`_RateLimiter`)
  - robots.txt cache per origin (`_RobotsCache`) — respects Disallow; failure → permissive default
  - Network error → `[]` + log warning (never raise)
- **`CrawlResult`** Pydantic v2 model: 10 fields aligned with existing `CrawledItem` schema
- **`CrawlSearchRequest`** Pydantic v2 input validation (query / max_results / page / extra)
- **Per-channel `parse(html)` static method**: JSON-first, HTML fallback (`__INITIAL_STATE__` / `_ROUTER_DATA` / DOM)
- **Per-channel `search(query, max_results=20)` async method**: applies rate-limit + UA + robots
- **Per-channel `search_request(SearchRequest)` async**: Pydantic-typed entry
- **Per-channel `search_sync(query, max_results)`**: blocking wrapper for non-async callers
- Registry: `get_channel_registry()` returns `{name: ChannelClass}` dict

## Test coverage (10 tests × 5 channels = 50 + 1 integration smoke)

Each channel has these 10 test cases:

1. `parse(html)` extracts N results
2. `parse(html)` extracts correct field values (id/url/title/author/source)
3. `parse(html)` populates extra fields (channel-specific metadata)
4. `parse(html)` handles invalid/empty input → returns `[]`
5. `parse(html)` handles `__INITIAL_STATE__` / `_ROUTER_DATA` HTML fallback
6. `search(query)` returns results with correct source
7. `search(query, max_results=N)` caps results
8. `search(query)` on empty/404 response → `[]`
9. `search(query)` on 5xx → `[]`
10. `search_request(SearchRequest)` Pydantic-typed entry works

Plus wechatmp adds:
- Rate-limit enforces ≥ 1.5s for 3 sequential calls
- robots.txt Disallow blocks /weixin → returns `[]`
- `search_sync()` sync wrapper works

## Sample queries

```python
from china_social import WechatMPChannel, WeiboMPChannel, \
    DouyinMPChannel, XiguaChannel, BilibiliMPChannel

# 1. Wechat 公众号
import asyncio, httpx
async def main():
    transport = httpx.MockTransport(...)  # or None for real
    async with httpx.AsyncClient(transport=transport) as c:
        cw = WechatMPChannel(client=c, respect_robots=False)
        results = await cw.search("AI 大模型", max_results=10)
        for r in results:
            print(r.title, "|", r.url, "|", r.author)

asyncio.run(main())
```

Sample queries each channel handles:
- `wechatmp`: "AI 大模型", "Python 教程", "机器之心"
- `weibomp`: "AI 观察家", "Python 教程推荐"
- `douyinmp`: "美食探店", "Python 编程教学"
- `xigua`: "美食教程", "Python 数据可视化"
- `bilibilimp`: "Python 教程 UP 主", "AI 科技前沿"

## Verification

```
D:\ComfyUI\.ext\python.exe -m pytest \
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\china_social\__tests__" \
  -v --rootdir="D:\Hermes\生产平台\nanobot-factory\backend\imdf"
```

Result: **51 passed in 2.31s** (all green; 1 unrelated pytest config warning for unknown `timeout` option in `pytest.ini`).

## Notes for verifier

1. **`BaseCrawlerChannel` does NOT exist in `_schemas.py`** despite the task description
   referencing it. We define it inside `china_social/_base.py` to keep the package
   self-contained and not modify existing files outside the scope.
2. **`respect_robots=True` by default**. Tests pass `respect_robots=False` to bypass
   in test environments. wechatmp test specifically verifies robots.txt enforcement.
3. **Rate-limit (1 req/sec) is real and enforced.** The wechatmp rate-limit test
   verifies 3 sequential calls take ≥ 1.5s. For tests, set `rate_per_sec=0` if you
   want to skip this.
4. **JSON-first parse with HTML fallback.** Each channel's static `parse()` method
   tries JSON first (handles API responses), then `__INITIAL_STATE__` / `_ROUTER_DATA`
   (handles SSR), then DOM (handles SSR HTML).
5. **Network calls fail gracefully.** All channels return `[]` on network error,
   5xx, robots disallow, or empty response — they never raise.
6. **No new dependencies added.** Uses existing `httpx` 0.27.2, `bs4` 4.14.3,
   `pydantic` 2.9.2.

## What's NOT included (out-of-scope by task spec)

- Real-network integration tests (all tests use MockTransport — real Wechat/Weibo/Douyin/Xigua/Bilibili are anti-scraping and would 403/empty in CI)
- Login state / cookie handling (would be required for real production crawling)
- Proxy rotation / captcha solving (out of task scope)
- Persistence layer (channels return `List[CrawlResult]`; downstream pipeline is responsible for storage)