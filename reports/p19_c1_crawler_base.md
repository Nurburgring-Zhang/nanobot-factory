# P19-C1 — 83 渠道爬虫框架 (BaseCrawler + WebCrawler + APICrawler + RSSCrawler + 5 渠道)

> **完成时间**: 2026-07-01 21:43 → 21:58 (Asia/Shanghai)  
> **测试**: 73 passed / 5 test files / 0 failed / 10.51s  
> **任务**: P19-C1 / plan_086a371a

## 硬启动检查 v3 — PASS

| 检查项 | 状态 |
|---|---|
| `backend/imdf/engines/data_collection_engine.py` | ✅ |
| `backend/imdf/engines/crawler_engine.py` | ✅ (P19-B4 已建) |
| `reports/VDP-2026-V5-对比差距清单.md` | ✅ |
| `reports/p19_b2_provider_4c.md` | ✅ |

## 1. 目录结构 ✅

```
backend/imdf/crawler/
├── __init__.py                 公开 API + 导出
├── base.py                     BaseCrawler 抽象基类 (398 行)
├── config.py                   CrawlerConfig + AuthConfig + ProxyConfig + RateLimitConfig (253 行)
├── web_crawler.py              WebCrawler Playwright + urllib fallback (333 行)
├── api_crawler.py              APICrawler + GraphQLCrawler (437 行)
├── rss_crawler.py              RSSCrawler + 增量去重 (231 行)
├── engine.py                   CrawlerEngine 调度器 (356 行)
├── channels/
│   ├── __init__.py             ChannelCrawler 抽象基类 (76 行)
│   ├── google_images.py        Custom Search API + mock (147 行)
│   ├── open_images.py          Open Images v7 CSV + mock (114 行)
│   ├── flickr.py               REST API + farm/server/secret URL + mock (151 行)
│   ├── unsplash.py             REST API + Client-ID + mock (142 行)
│   └── pixabay.py              REST API + mock (137 行)
└── tests/                      5 文件 / 73 tests / 全 PASS
    ├── test_base.py            20 tests
    ├── test_web_crawler.py     11 tests
    ├── test_api_crawler.py     11 tests
    ├── test_rss_crawler.py     9 tests
    └── test_channels_5.py      22 tests (含修复)
```

## 2. BaseCrawler ✅

- 抽象类 + `crawl()` 8 步标准流程 (V5 §19.3.4)
- 合规: robots.txt (1h TTL 缓存) + 自定义 blocklist
- UA 池: 12 条主流 UA,随机轮询
- metrics: fetched / success / errors / blocked / bytes / by_status (Lock 保护)
- audit chain 集成 (P10-A): best-effort lazy import
- 限速: token bucket 简化版 (默认 1.0 RPS)

## 3. WebCrawler ✅

- Playwright 同步驱动 (优先) + urllib fallback
- 智能等待 / 滚动 / 点击翻页 / 多页合并 (PAGE_BREAK)
- 提取模式: html / text / title / images / links / metadata
- BeautifulSoup 解析 + 自定义 selectors
- 异步批量入口 `crawl_batch_async()` — ThreadPoolExecutor

## 4. APICrawler ✅

- HTTP 方法: GET/POST/PUT/PATCH/DELETE
- 鉴权 4 种: Bearer / API Key / Basic / OAuth2 (自动刷新 token)
- 自动分页 4 模式: cursor / offset / page / link_header
- 重试: 429 + 5xx 指数 backoff (默认 3 次)
- httpx (preferred) + urllib fallback
- GraphQLCrawler 子类 — `crawl_query()` 入口

## 5. RSSCrawler ✅

- feedparser: RSS 0.9x / 2.0 / Atom 1.0 / RDF
- 增量去重: GUID (id → link → hash(title) → hash(entry))
- 持久化: rss_seen.json,10000 条/feed 上限
- ISO 8601 时间标准化

## 6. 5 渠道首批 ✅

| 渠道 | 鉴权 | API | key env | mock fallback |
|---|---|---|---|---|
| `google_images` | API Key + cx | Custom Search JSON | `GOOGLE_API_KEY` + `GOOGLE_CX` | 无 key 自动 mock |
| `open_images` | 公开 | CSV (storage.googleapis.com) | (无) | 显式 mock=True |
| `flickr` | API Key (query) | REST (api.flickr.com) | `FLICKR_API_KEY` | 无 key 自动 mock |
| `unsplash` | Client-ID | REST (api.unsplash.com) | `UNSPLASH_ACCESS_KEY` | 无 key 自动 mock |
| `pixabay` | API Key (query) | REST (pixabay.com/api) | `PIXABAY_API_KEY` | 无 key 自动 mock |

**统一 item schema**: url / thumbnail_url / source / id / title / width / height / license / tags / mock

## 7. CrawlerEngine ✅

- 调度器: `submit(channel, target, job_id) -> str`
- 注册表: `register(channel, cls)` + `get_crawler(channel)` 懒加载
- 任务模型: `CrawlJob` (PENDING/RUNNING/COMPLETED/FAILED/CANCELLED)
- 批量: `crawl_batch(items, sync=True/False, max_workers)`
- 进度: `add_progress_hook(hook)` (WebSocket ready)
- 集成: `_log_to_data_collection()` + `_audit()` 链
- 聚合: `aggregate_metrics() -> Dict[channel, snapshot]`
- 8 默认渠道: 5 image + web + api + rss

## 8. 集成 smoke ✅

5 渠道 batch crawl (mock=True),0.5s 全成功:

```
5d8d4c32: status=success items=3 ok=True source=google_images
3fc6abfd: status=success items=3 ok=True source=open_images
7ea9cd5b: status=success items=3 ok=True source=flickr
84a69640: status=success items=3 ok=True source=unsplash
ecf2a608: status=success items=3 ok=True source=pixabay
```

每渠道 metrics: fetched=1 success=1 errors=0。

## 9. 测试结果 — 73/73 PASS

```
test_base.py          20 passed
test_web_crawler.py   11 passed
test_api_crawler.py   11 passed
test_rss_crawler.py    9 passed
test_channels_5.py    22 passed (修复后)
─────────────────────────────────
TOTAL                 73 passed in 10.51s
```

## 修复记录

**问题**: `test_crawl_batch_sequential` 首次跑卡 95s/120s 超时,1 个 FAIL。

**根因**: `CrawlerEngine.submit()` 默认 `cls(config=cfg)`,不带 `mock=True`,导致无 key 渠道 (`open_images`, `requires_key=False`) 走真 URL `storage.googleapis.com/openimages/...`,触发 urllib 30s timeout。

**修复**: 测试用 `_make_mock_factory()` 替换 5 渠道工厂,强制 `mock=True` 注入,避免真网络调用。`_boost_rate()` 把 rps 从 1.0 提到 100,避免限速瓶颈。修复后 22 tests 1.37s 通过。

## 已知约束

- Playwright / httpx / feedparser / BeautifulSoup 均为可选依赖,生产部署需 `pip install playwright httpx feedparser beautifulsoup4`
- RSS state 持久化到 `backend/imdf/data/rss_seen.json`,可改 `CRAWLER_STATE_DIR` 环境
- Audit chain lazy import,测试环境 `config.settings` 缺失不影响主流程

## 后续 P19-C2+ 任务

- **C2**: 增量到 83 渠道 (剩余 78)
- **C3**: 渠道动态发现 + 自动注册 (config-driven)
- **C4**: WebSocket 进度推送 (engine 已留 hook)
- **C5**: 渠道健康监控 + 自动降级
- **C6**: SQLite 持久化 (现仅 in-memory + JSON)

## 文件清单 (19 文件)

**源文件 (13)**:
- `crawler/__init__.py` (56 行)
- `crawler/base.py` (398 行)
- `crawler/config.py` (253 行)
- `crawler/web_crawler.py` (333 行)
- `crawler/api_crawler.py` (437 行)
- `crawler/rss_crawler.py` (231 行)
- `crawler/engine.py` (356 行)
- `crawler/channels/__init__.py` (76 行)
- `crawler/channels/google_images.py` (147 行)
- `crawler/channels/open_images.py` (114 行)
- `crawler/channels/flickr.py` (151 行)
- `crawler/channels/unsplash.py` (142 行)
- `crawler/channels/pixabay.py` (137 行)

**测试文件 (6)**:
- `tests/__init__.py`
- `tests/test_base.py` (248 行, 20 tests)
- `tests/test_web_crawler.py` (165 行, 11 tests)
- `tests/test_api_crawler.py` (290 行, 11 tests)
- `tests/test_rss_crawler.py` (190 行, 9 tests)
- `tests/test_channels_5.py` (340 行, 22 tests — 含修复)

**报告**:
- `reports/p19_c1_crawler_base.md`

---

**VERDICT**: ✅ **DONE — 83 渠道爬虫底层框架完成,73 tests pass,集成 data_collection_engine + audit_chain 可用,5 首批渠道 mock 全通。**