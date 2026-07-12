# P20-G Storage Crawler Channels — Report

**Date**: 2026-07-09
**Task**: Storage crawler (5 channels)
**Status**: ✅ All 5 channels built + 112 tests pass

## File List

### Channel modules (`backend/imdf/crawler/channels/storage/`)

| File | Size | Channel | Endpoint pattern |
|------|------|---------|------------------|
| `__init__.py` | ~9 KB | base + registry | — |
| `s3.py` | ~7 KB | s3 | `https://<bucket>.s3.<region>.amazonaws.com/?list-type=2&prefix=<q>` |
| `gcs.py` | ~7 KB | gcs | `https://storage.googleapis.com/storage/v1/b/<bucket>/o?prefix=<q>` |
| `azure.py` | ~7 KB | azure | `https://<account>.blob.core.windows.net/<container>?restype=container&comp=list&prefix=<q>` |
| `alioss.py` | ~7 KB | alioss | `https://<bucket>.oss.aliyuncs.com/?prefix=<q>` |
| `tencentcos.py` | ~7 KB | tencentcos | `https://<bucket>.cos.<region>.myqcloud.com/?prefix=<q>` |

### Test modules (`backend/imdf/crawler/channels/storage/__tests__/`)

| File | Tests | Pass |
|------|-------|------|
| `s3_test.py` | 22 | 22 |
| `gcs_test.py` | 21 | 21 |
| `azure_test.py` | 21 | 21 |
| `tencentcos_test.py` | 23 | 23 |
| `alioss_test.py` | 21 | 21 |
| **Total** | **108 + 4 parser-only** | **112 / 112** |

### Support files

- `backend/imdf/crawler/channels/storage/pytest.ini` — local override: `python_files = *_test.py` (matches task spec naming)
- `backend/imdf/crawler/channels/storage/__tests__/__init__.py` — pytest package marker

## Test Results

```
============================= 112 passed in 0.91s =============================
```

**Test command**:
```bash
"D:\ComfyUI\.ext\python.exe" -m pytest "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\storage\__tests__" -v
```

**Existing test suites unaffected**:
- `tests/test_datasets_5.py` — 49 tests passed
- `tests/test_baidu_images.py` — 14 tests passed
- **63 pre-existing tests still pass** alongside the new 112

## Coverage per channel

Each channel has the following test classes (≥ 4 tests/channel as required, all have 20+):

### `Test{Channel}Parser` (static XML/JSON parsing)
- test_xml_parses_n_objects
- test_etag_quoted_stripped (S3, Aliyun, COS strip `"…"` quotes)
- test_storage_class_preserved
- test_url_constructed
- test_empty_xml / test_malformed_xml / test_error_root (edge cases)

### `Test{Channel}Channel` (async search via httpx.MockTransport)
- test_search_returns_storage_objects
- test_search_fields_populated
- test_search_max_results
- test_url_format
- test_status_error_returns_empty (500)
- test_404_returns_empty (or 403 for Aliyun)
- test_malformed_xml_returns_empty
- test_user_agent_sent
- test_query_in_url (or prefix param)
- test_static_parse (delegates to parse())

### `Test{Channel}Registry`
- test_in_registry (verifies CHANNEL_REGISTRY entry + get_channel() works)

### `TestS3Channel.test_rate_limit_enforced`
- Verifies 1 req/sec default via sleep timing

## Sample Queries

| Channel | Query | Expected result |
|---------|-------|-----------------|
| s3 | `"cats/"` | `https://my-bucket.s3.us-east-1.amazonaws.com/?list-type=2&prefix=cats%2F&max-keys=20` |
| gcs | `"land/"` | `https://storage.googleapis.com/storage/v1/b/gcp-public-data-samples/o?maxResults=20&prefix=land%2F` |
| azure | `"docs/"` | `https://myaccount.blob.core.windows.net/public?restype=container&comp=list&prefix=docs%2F&maxresults=20` |
| alioss | `"data/"` | `https://aliyun-public.oss.aliyuncs.com/?max-keys=20&prefix=data%2F` |
| tencentcos | `"videos/"` | `https://public-read-1300000000.cos.ap-shanghai.myqcloud.com/?max-keys=20&prefix=videos%2F` |

## Architecture

### `BaseCrawlerChannel` (in `storage/__init__.py`)

Provides shared transport + rate-limit + robots.txt logic:

```python
class BaseCrawlerChannel:
    channel: str = "storage_base"
    api_endpoint: str = ""
    USER_AGENTS: List[str]  # 3-rotate pool

    def __init__(self, transport=None, timeout=30.0, client=None,
                 rate_limit_per_sec=1.0, respect_robots=True, user_agent=None)

    async def search(self, query: str, max_results: int = 20) -> List[StorageObject]
    @staticmethod def parse(html: str) -> List[StorageObject]  # subclasses override

    # Template methods
    def _build_url(self, query, max_results) -> str
    def _parse_payload(self, text, query, max_results) -> List[Dict]
    def _build_object(self, raw, query, idx) -> Optional[StorageObject]
```

### `StorageObject` (Pydantic v2 model)

```python
class StorageObject(BaseModel):
    id: str           # "{channel}:{bucket}:{key}"
    bucket: str
    key: str
    url: str          # canonical HTTPS URL
    size: Optional[int]
    last_modified: Optional[str]  # ISO 8601
    etag: Optional[str]
    content_type: Optional[str]
    channel: str
    description: str
    storage_class: Optional[str]
    created_at: datetime  # auto-filled
    extra: Dict[str, Any]
```

### `CHANNEL_REGISTRY` (5 entries)

```python
CHANNEL_REGISTRY = {
    "s3": S3Channel,
    "gcs": GcsChannel,
    "azure": AzureChannel,
    "alioss": AliossChannel,
    "tencentcos": TencentCosChannel,
}

def get_channel(name: str, **kwargs) -> BaseCrawlerChannel
```

## Cross-cutting features

| Feature | Status | Notes |
|---------|--------|-------|
| httpx async client | ✅ | `httpx.AsyncClient` + `httpx.MockTransport` for tests |
| BeautifulSoup | ✅ | Fallback for malformed XML |
| Pydantic v2 models | ✅ | `StorageObject` with validators |
| User-Agent rotation | ✅ | 3-UA pool; default `Chrome/120.0.0.0` |
| Rate limiting (1 req/sec) | ✅ | `asyncio.Lock` + `time.monotonic()` per instance |
| robots.txt respect | ✅ | In-memory cache; best-effort; default permissive on failure |
| Network failure graceful | ✅ | All channels return `[]` + log on 4xx/5xx/exception |
| No API keys | ✅ | All endpoints are public list APIs |
| ETag quote stripping | ✅ | S3, Aliyun, COS strip `"…"` at parse time |
| XML namespace handling | ✅ | S3 strips `xmlns="…doc/2006-03-01/"` for cleaner parsing |

## Notes for verifier

1. **Run pytest** with `D:\ComfyUI\.ext\python.exe` per task spec:
   ```bash
   & "D:\ComfyUI\.ext\python.exe" -m pytest "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\storage\__tests__" -v
   ```
   Expected: `112 passed in <2s`.

2. **Pytest config override** — `storage/pytest.ini` sets `python_files = *_test.py` because the parent `pytest.ini` (in `imdf/`) uses `test_*.py`. The override is local to this package.

3. **No new dependencies** — uses only `httpx`, `bs4`, `pydantic` (all pre-installed).

4. **No files outside `storage/` were touched** — the package is self-contained.

5. **Public-bucket semantics** — the crawler requires the *target bucket* to be public-read. It does NOT enumerate random buckets; users pass `bucket=` (S3/Aliyun/COS) or `account= + container=` (Azure) explicitly. Default buckets are well-known public ones (e.g. `aws-public-datasets`).

6. **GCS quirk** — uses the modern `storage/v1/b/<bucket>/o` JSON endpoint (not the legacy XML listing). Falls back to BS4 HTML-directory-listing parse if JSON decode fails.

7. **Memory entry** — not added; the patterns (httpx + Pydantic v2 + MockTransport) are project-agnostic and already documented in `python-footguns.md` / `fastapi-validation-patterns.md` from prior plans.
