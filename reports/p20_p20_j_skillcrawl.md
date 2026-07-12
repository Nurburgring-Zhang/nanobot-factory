# P20-J — Crawl Skills (17)

## Summary

Built 17 async crawl skills for the nanobot-factory platform covering Reddit,
Twitter/X, YouTube, TikTok, Instagram, Pinterest, Tumblr, Flickr (advanced),
Unsplash (keyword), 500px, DeviantArt, Behance, Dribbble, ArtStation, Pixiv,
Danbooru, and Gelbooru.  Each skill exposes the canonical
``async def crawl_<site>(input: SkillInput) -> SkillOutput`` contract, uses
Pydantic models for the request/response payloads, calls ``httpx`` for live
fetches, and falls back to a deterministic offline mock when the network is
unreachable.  **60 / 60 tests pass.**

## Skill list

| # | skill_id | module | tests |
|---|----------|--------|-------|
| 1 | `skill_crawl_reddit` | `crawl_reddit.py` | 5 |
| 2 | `skill_crawl_twitter` | `crawl_twitter.py` | 4 |
| 3 | `skill_crawl_youtube` | `crawl_youtube.py` | 4 |
| 4 | `skill_crawl_tiktok` | `crawl_tiktok.py` | 4 |
| 5 | `skill_crawl_instagram` | `crawl_instagram.py` | 4 |
| 6 | `skill_crawl_pinterest` | `crawl_pinterest.py` | 3 |
| 7 | `skill_crawl_tumblr` | `crawl_tumblr.py` | 3 |
| 8 | `skill_crawl_flickr2` | `crawl_flickr2.py` | 4 |
| 9 | `skill_crawl_unsplash2` | `crawl_unsplash2.py` | 3 |
| 10 | `skill_crawl_500px` | `crawl_500px.py` | 3 |
| 11 | `skill_crawl_deviantart` | `crawl_deviantart.py` | 3 |
| 12 | `skill_crawl_behance` | `crawl_behance.py` | 3 |
| 13 | `skill_crawl_dribbble` | `crawl_dribbble.py` | 3 |
| 14 | `skill_crawl_artstation` | `crawl_artstation.py` | 3 |
| 15 | `skill_crawl_pixiv` | `crawl_pixiv.py` | 3 |
| 16 | `skill_crawl_danbooru` | `crawl_danbooru.py` | 4 |
| 17 | `skill_crawl_gelbooru` | `crawl_gelbooru.py` | 4 |

**Total: 17 skill modules + 17 test files + shared `_base.py` + lazy registry `__init__.py` → 60 tests, all PASS.**

## Sample inputs / outputs

### Reddit
```python
SkillInput(params={"subreddit": "Python", "sort": "hot", "limit": 5})
# → SkillOutput(success=True, result={"subreddit": "Python", "count": 5,
#                                      "posts": [RedditPost(...)]},
#                metadata={"skill_id": "skill_crawl_reddit",
#                          "source": "offline_mock",
#                          "confidence": 0.7, ...})
```

### YouTube (with key)
```python
SkillInput(params={"query": "data engineering", "max_results": 3})
# → SkillOutput(success=True, result={"query": "data engineering", "count": 3,
#                                      "videos": [YouTubeVideo(title=..., duration_seconds=..., url=...)]},
#                metadata={"api_key_present": False, ...})
```

### Danbooru
```python
SkillInput(params={"tags": "blue_hair 1girl", "limit": 3})
# → SkillOutput(success=True, result={"query": "blue_hair 1girl", "count": 3,
#                                      "posts": [DanbooruPost(id=..., tags=[...], file_url=...)]})
```

## Cross-cutting features

* **Offline-first** — every skill registers a `register_offline_fixture` so it
  works without network, returning 5 deterministic mock items. The probe uses
  a TCP socket check against `1.1.1.1:443` with 1 s timeout (cached).
* **httpx-based fetch** — `fetch_or_mock` wraps `httpx.AsyncClient` with 5 s
  timeout and JSON-aware extraction. Falls back to mock on any HTTPError or
  OSError.
* **Standardised metadata** — every SkillOutput has `{skill_id, timestamp,
  source, confidence, query}` plus optional extras. `source` is `live_api` or
  `offline_mock` so consumers can gate downstream behaviour.
* **Pydantic schemas** — each skill defines `{Site}Request` /
  `{Site}Response` models with strict validation (`min_length`, `ge`, `le`,
  regex patterns). Bad params return `SkillOutput(success=False)` rather than
  raising.
* **Lazy registry** — `crawl/__init__.py` exposes a `_build_registry()`
  helper instead of eager-importing all 17 submodules to avoid the
  half-initialised-package error that occurred when pytest collected tests.
* **`from backend.imdf.skills.crawl import *` works** — `__all__` exposes
  the base helpers and registry accessors (`get_crawl_skill`,
  `list_crawl_skill_ids`).

## Verification

```
$ python -m pytest backend/imdf/skills/crawl/__tests__/ -v
============================= 60 passed in 1.47s ==============================
```

Run with: `D:\ComfyUI\.ext\python.exe -m pytest backend/imdf\skills\crawl\__tests__ -v`.

## Notes

* `conftest.py` in the tests dir patches `sys.modules['backend.imdf.skills']`
  so the broken parent `__init__.py` (which transitively imports
  `engines.octo_engine`) doesn't break collection.  No files outside
  `backend/imdf/skills/crawl/` were modified.
* All skills return data on the offline path; no test depends on a live API
  call.
* Files outside scope were not touched; the parent `__init__.py` in
  `backend/imdf/skills/` was left untouched.

## Files changed

| Path | Lines |
|------|-------|
| `backend/imdf/skills/crawl/_base.py` | 230 |
| `backend/imdf/skills/crawl/__init__.py` | 116 |
| `backend/imdf/skills/crawl/crawl_reddit.py` | 168 |
| `backend/imdf/skills/crawl/crawl_twitter.py` | 142 |
| `backend/imdf/skills/crawl/crawl_youtube.py` | 167 |
| `backend/imdf/skills/crawl/crawl_tiktok.py` | 132 |
| `backend/imdf/skills/crawl/crawl_instagram.py` | 134 |
| `backend/imdf/skills/crawl/crawl_pinterest.py` | 124 |
| `backend/imdf/skills/crawl/crawl_tumblr.py` | 125 |
| `backend/imdf/skills/crawl/crawl_flickr2.py` | 167 |
| `backend/imdf/skills/crawl/crawl_unsplash2.py` | 165 |
| `backend/imdf/skills/crawl/crawl_500px.py` | 142 |
| `backend/imdf/skills/crawl/crawl_deviantart.py` | 152 |
| `backend/imdf/skills/crawl/crawl_behance.py` | 138 |
| `backend/imdf/skills/crawl/crawl_dribbble.py` | 138 |
| `backend/imdf/skills/crawl/crawl_artstation.py` | 154 |
| `backend/imdf/skills/crawl/crawl_pixiv.py` | 161 |
| `backend/imdf/skills/crawl/crawl_danbooru.py` | 149 |
| `backend/imdf/skills/crawl/crawl_gelbooru.py` | 145 |
| `backend/imdf/skills/crawl/__tests__/conftest.py` | 50 |
| `backend/imdf/skills/crawl/__tests__/test_crawl_*.py` (×17) | 50–95 ea. |