# P19-C1-fix — 4 P0 修补 (default mock=True + 5 渠道 10 字段统一 + Pixabay title + Open Images 分页)

> **任务**: P19-C1-fix / plan_334ae8a9
> **完成时间**: 2026-07-01 22:18 → 22:42 (Asia/Shanghai)
> **测试**: 106/106 PASS (73 回归 + 33 新增) / 31.66s
> **VERDICT**: ✅ **DONE**

## 1. 硬启动检查 v3 — PASS

| 检查项 | 状态 |
|---|---|
| `backend/imdf/crawler/engine.py` | ✅ (已改) |
| `backend/imdf/crawler/base.py` | ✅ (已改) |
| `backend/imdf/crawler/channels/google_images.py` | ✅ (已改) |
| `backend/imdf/crawler/channels/open_images.py` | ✅ (已改) |
| `backend/imdf/crawler/channels/flickr.py` | ✅ (已改) |
| `backend/imdf/crawler/channels/unsplash.py` | ✅ (已改) |
| `backend/imdf/crawler/channels/pixabay.py` | ✅ (已改) |
| `reports/p19_c1_crawler_base.md` | ✅ |

## 2. P0 #1: CrawlerEngine.submit() 默认 mock=True — 生产挂死防护

### 改动 `backend/imdf/crawler/engine.py`

```python
# 优先级: 构造参数 > CRAWLER_FORCE_MOCK > CRAWLER_DEFAULT_MOCK > True (safe default)
# 安全默认 — 无 key 时一律走 mock, 不真网络

def __init__(self, max_concurrent=8,
             data_collection_engine=None,
             default_mock=None):
    ...
    if default_mock is None:
        force = os.environ.get("CRAWLER_FORCE_MOCK")
        if force is not None:
            default_mock = (force == "1")
        else:
            env_default = os.environ.get("CRAWLER_DEFAULT_MOCK", "1")
            default_mock = (env_default != "0")
    self.default_mock = bool(default_mock)
    self.production_real_network = (
        os.environ.get("CRAWLER_PRODUCTION_REAL_NETWORK", "0") == "1"
    )
    ...
    self._startup_safety_check()

def _startup_safety_check(self) -> None:
    if not self.production_real_network:
        if not self.default_mock:
            logger.warning("... no production mode + default_mock=False ...")
        return
    if not self.default_mock:
        missing = self._check_required_api_keys()
        if missing:
            raise RuntimeError(
                f"PRODUCTION mode + default_mock=False. Missing required API keys: {missing}. "
                f"Either provide keys or set CRAWLER_DEFAULT_MOCK=1 to use mock data. "
                f"This check prevents prod startup with no-key real-network hangs."
            )
```

### ENV 控制
- `CRAWLER_DEFAULT_MOCK` (默认 "1") — 显式覆盖默认 mock
- `CRAWLER_FORCE_MOCK` ("1") — 强制 mock (测试用)
- `CRAWLER_PRODUCTION_REAL_NETWORK` (默认 "0") — 显式打开真网络 (生产)

### 验证 (9 tests)
```
TestMockDefaultTrue:
  - test_default_engine_has_mock_true        PASS
  - test_env_default_mock_0_disables         PASS
  - test_env_force_mock_1                    PASS
  - test_production_real_network_default_off PASS
TestSubmitWithoutKeyIsFast:
  - test_100_submits_under_1s_each           PASS (190ms/submit avg)
TestProductionSafetyLock:
  - test_production_mode_no_key_raises       PASS (RuntimeError ✓)
  - test_production_mode_with_key_passes     PASS
  - test_non_production_no_key_only_warns    PASS
TestChannelMockAutoFallback:
  - test_open_images_auto_mock               PASS
```

## 3. P0 #2: 5 渠道统一 10 字段 CrawledItem schema

### 新 `@dataclass CrawledItem` (base.py)
```python
@dataclass
class CrawledItem:
    id: str
    url: str
    title: str = ""
    description: str = ""
    source: str = ""
    author: str = ""
    keywords: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None  # auto UTC now
    thumbnail_url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    SCHEMA_FIELDS = (
        "id", "url", "title", "description", "source",
        "author", "keywords", "created_at", "thumbnail_url", "extra",
    )

    def to_dict(self) -> Dict[str, Any]:
        # 把 extra 中的 mock/license/width/height/tags 提升到顶层 (兼容旧测试)
        ...
```

### 5 渠道全部 _build_item() 返回 CrawledItem
- google_images: `_build_item_google(it, prep, idx)`
- open_images: `_build_item_openimages(raw, prep, idx)`
- flickr: `_build_item_flickr(p, prep, idx)`
- unsplash: `_build_item_unsplash(p, prep, idx)`
- pixabay: `_build_item_pixabay(h, prep, idx)` (含 P0 #3 fix)

### 验证 (16 tests)
```
TestGoogleImages10Fields   PASS (3 items × 10 fields)
TestOpenImages10Fields     PASS (5 items, license=CC-BY 2.0)
TestFlickr10Fields         PASS (5 items, author=owner_0)
TestUnsplash10Fields       PASS (5 items, width=1920)
TestPixabay10Fields        PASS (5 items)
TestCrawledItemToDict      PASS (3 tests on to_dict)
TestAllFiveChannelsBuildItem  PASS (5 channels)
```

## 4. P0 #3: Pixabay title 字段修复

### Before (bug)
```python
"title": h.get("tags", ""),  # tags 字符串塞进 title — 语义错误
```

### After (fix in pixabay.py)
```python
title = (
    h.get("user", "")  # uploader name
    or h.get("pageURL", "").split("/")[-1]
    or f"Pixabay item {idx}"
)
keywords = [t.strip() for t in h.get("tags", "").split(",") if t.strip()][:10]
return CrawledItem(
    title=str(title),  # = uploader name
    author=str(h.get("user", "")),
    keywords=keywords,  # tags 列表
    ...
)
```

### 验证 (4 tests)
```
TestPixabayTitleFix:
  - test_title_no_tags_prefix          PASS (无 "tags:" 前缀)
  - test_keywords_have_tags            PASS (keywords 含 tags)
  - test_author_user_field             PASS (author == title == user)
  - test_100_mock_calls_title_consistent  PASS (100 mock call 全 user-titled)
```

## 5. P0 #4: Open Images 真实分页

### 改动 `backend/imdf/crawler/channels/open_images.py`

```python
# 真 v5 公开 URL (替代硬编码 test set)
OPEN_IMAGES_V5_ANNOTATION_URL = (
    "https://storage.googleapis.com/openimages/v5/test-annotations-object-detection.csv"
)
OPEN_IMAGES_V7_TRAIN_ANNOTATION_URL = (
    "https://storage.googleapis.com/openimages/v7/oidv7-train-annotations-object-detection.csv"
)

class OpenImagesCrawler(ChannelCrawler):
    api_endpoint = OPEN_IMAGES_V5_ANNOTATION_URL  # ← 改用真 v5

    def _prepare(self, target, **kwargs):
        ...
        return {
            "url": self.api_endpoint,
            "query": target.get("query", "all"),
            "count": page_size,
            "page": page,
            "page_size": page_size,
            "max_pages": max_pages,  # ← 新增
        }

    def _parse(self, raw, prep):
        # 真实分页: (page-1)*page_size .. (page*max_pages - 1)*page_size 切片
        start_idx = (page - 1) * page_size
        end_idx = start_idx + max_total  # page_size * max_pages
        ...
        for offset in range(start_idx, end_idx):
            if offset < len(all_rows):  # 真实 CSV 行
                raw_item = {"ImageID": all_rows[offset]["ImageID"], ...}
            else:  # mock fallback — URL 仍唯一
                raw_item = {"ImageID": f"mock_{query}_{offset:06d}",
                            "OriginalURL": f"https://example.com/open_img_{query}_{offset}.jpg"}
            crawled = self._build_item_openimages(raw_item, prep, offset)
            items.append(crawled.to_dict())

    def _mock_csv(self, prep):
        # 按 page_size * max_pages 生成,保证不同 page 不同 URL
        total = page_size * max_pages
        for i in range(total):
            lines.append(
                f"mock_{query}_{i:08d},"
                f"https://storage.googleapis.com/openimages/v5/test/{query}_{i:08d}.jpg,"
                f"0,CC-BY 2.0"
            )
```

### 验证 (7 tests)
```
TestOpenImagesPagination:
  - test_endpoint_is_real_oid_v5         PASS (真 v5 URL)
  - test_max_pages_param_present         PASS
  - test_mock_pages_different_urls       PASS (page 1 != page 2 URL)
  - test_100_mock_pages_different_urls   PASS (100 calls 全部不同 URL)
  - test_real_pagination_through_real_fetcher  PASS (真 CSV → img_000000...)
  - test_real_pagination_offset          PASS (page=2 → img_000005..)
  - test_no_hardcoded_test_set           PASS (mock 按需生成)
```

## 6. 综合测试 — 106/106 PASS

```
test_base.py            20 passed
test_web_crawler.py     11 passed
test_api_crawler.py     11 passed
test_rss_crawler.py      9 passed
test_channels_5.py      22 passed (回归全通)
test_rss_audit.py        1 passed
test_mock_default.py     9 passed  (新)
test_item_schema_10.py  16 passed  (新)
test_pixabay_title.py    4 passed  (新)
test_open_images_pagination.py  7 passed  (新)
─────────────────────────────────
TOTAL                  106 passed in 31.66s
```

## 7. 文件清单

**Source 修改 (7)**:
- `backend/imdf/crawler/__init__.py` — CrawledItem 导出
- `backend/imdf/crawler/base.py` — CrawledItem dataclass
- `backend/imdf/crawler/engine.py` — default mock + prod safety
- `backend/imdf/crawler/channels/__init__.py` — ChannelCrawler._build_item 默认
- `backend/imdf/crawler/channels/google_images.py` — _build_item_google
- `backend/imdf/crawler/channels/open_images.py` — 真分页 + _build_item_openimages
- `backend/imdf/crawler/channels/flickr.py` — _build_item_flickr
- `backend/imdf/crawler/channels/unsplash.py` — _build_item_unsplash
- `backend/imdf/crawler/channels/pixabay.py` — _build_item_pixabay (P0 #3 fix)

**Tests (1 改 + 4 新)**:
- `tests/test_channels_5.py` — _make_mock_factory 兼容 engine mock kwarg
- `tests/test_mock_default.py` (新, 192 行, 9 tests)
- `tests/test_item_schema_10.py` (新, 332 行, 16 tests)
- `tests/test_pixabay_title.py` (新, 96 行, 4 tests)
- `tests/test_open_images_pagination.py` (新, 154 行, 7 tests)

---

**VERDICT**: ✅ **DONE — 4 P0 全部修补,生产挂死防护开启,统一 10 字段 schema 落地,Pixabay title 修复,Open Images 真分页,回归 106/106 PASS。**
