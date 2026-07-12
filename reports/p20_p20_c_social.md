# P20-C Social Crawlers

## Summary
Implemented six public social-search crawler channels under `backend/imdf/crawler/channels/social/`: Weibo, Douyin, Bilibili, Xiaohongshu, Zhihu, and Baidu Tieba. Each channel exposes async `search(query, max_results)` plus static `parse(html)` returning Pydantic crawler items, uses `httpx.AsyncClient`, `BeautifulSoup`, rotating browser User-Agent headers, 1 req/sec per-instance rate limiting, robots.txt checks, and graceful empty-list handling on network failures.

## Changed files

### Channel implementation
- `backend/imdf/crawler/channels/social/_base.py`
- `backend/imdf/crawler/channels/social/__init__.py`
- `backend/imdf/crawler/channels/social/weibo.py`
- `backend/imdf/crawler/channels/social/douyin.py`
- `backend/imdf/crawler/channels/social/bilibili.py`
- `backend/imdf/crawler/channels/social/xiaohongshu.py`
- `backend/imdf/crawler/channels/social/zhihu.py`
- `backend/imdf/crawler/channels/social/tieba.py`

### Tests
- `backend/imdf/crawler/channels/social/__tests__/pytest.ini`
- `backend/imdf/crawler/channels/social/__tests__/conftest.py`
- `backend/imdf/crawler/channels/social/__tests__/weibo_test.py`
- `backend/imdf/crawler/channels/social/__tests__/douyin_test.py`
- `backend/imdf/crawler/channels/social/__tests__/bilibili_test.py`
- `backend/imdf/crawler/channels/social/__tests__/xiaohongshu_test.py`
- `backend/imdf/crawler/channels/social/__tests__/zhihu_test.py`
- `backend/imdf/crawler/channels/social/__tests__/tieba_test.py`

## Registry
`backend/imdf/crawler/channels/social/__init__.py` exports:

- `WeiboChannel`
- `DouyinChannel`
- `BilibiliChannel`
- `XiaohongshuChannel`
- `ZhihuChannel`
- `TiebaChannel`
- `SOCIAL_CHANNEL_REGISTRY`

## Test count and verification

- Test files: 6 channel test files
- Test cases: 24 total (4 per channel)
  - search returns results
  - parse extracts fields
  - network error handling returns `[]`
  - rate limiting waits before request

Verification command run:

```powershell
& "D:\ComfyUI\.ext\python.exe" -m pytest backend/imdf/crawler/channels/social/__tests__/ -v
```

Result: `24 passed in 0.21s`.

## Sample queries

- Weibo: `AI 绘画`, `多模态数据`
- Douyin: `AI 视频`, `机器人舞蹈`
- Bilibili: `AI 视频教程`, `数据标注`
- Xiaohongshu: `AI 绘本`, `机器人摄影`
- Zhihu: `AI 数据治理`, `大模型训练数据`
- Tieba: `AI 模型`, `数据采集`

## Notes

- The current repository snapshot has `CrawledItemModel`, `SearchRequest`, and `SearchResponse` in `backend/imdf/crawler/channels/_schemas.py`, but no `BaseCrawlerChannel`/`CrawlResult` symbols. To stay within the hard rule of not touching files outside `crawler/social/`, `social/_base.py` provides a local compatibility shim and aliases `CrawlResult` to `CrawledItemModel`.
- `*_test.py` naming was required by the task, while root pytest config only collects `test_*.py`; therefore `social/__tests__/pytest.ini` sets local discovery to `*_test.py` for the required command.
- Crawlers collect search-result metadata only and include copyright/robots notes in item `extra`; downstream download/reuse still needs source-specific licensing checks.
