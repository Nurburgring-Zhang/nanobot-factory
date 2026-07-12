# P20-D Academic Crawlers (5 channels) — Report

**Task**: Build 5 academic crawler channels for the nanobot-factory platform.
**Date**: 2026-07-09
**Plan**: plan_ff72ae4c / p20_p20_d_academic
**Status**: ✅ Done — 30/30 tests passing.

---

## Summary

Implemented 5 academic-paper crawler channels under
`backend/imdf/crawler/channels/academic/`:

1. **ArxivChannel** — arxiv.org Atom API (`export.arxiv.org/api`)
2. **PubMedChannel** — NCBI E-utilities (`eutils.ncbi.nlm.nih.gov`)
3. **IEEEChannel** — IEEE Xplore search (`ieeexplore.ieee.org`)
4. **SemanticScholarChannel** — Semantic Scholar Graph API (`api.semanticscholar.org`)
5. **GoogleScholarChannel** — Google Scholar HTML scrape (`scholar.google.com`)

All channels share the same architecture as the project's existing
`datasets/*.py` crawlers: `BaseAcademicCrawler` (httpx async + rate limit
+ MockTransport support), a unified `Paper` Pydantic v2 model, and a
common async `search(query, max_results) -> List[Paper]` entrypoint.

---

## File list (12 new files)

### Channels (`backend/imdf/crawler/channels/academic/`)

| File                   | Bytes  | Lines | Purpose |
| ---------------------- | ------ | ----- | ------- |
| `__init__.py`          | 8.7 KB |  231  | BaseAcademicCrawler + Paper re-exports + public API |
| `paper.py`             | 5.0 KB |  130  | Pydantic v2 Paper model (id/title/url/authors/abstract/year/...) |
| `arxiv.py`             | 7.9 KB |  205  | ArxivChannel — Atom XML feed parser |
| `pubmed.py`            | 9.7 KB |  220  | PubMedChannel — 2-step esearch + esummary |
| `ieee.py`              | 10.4 KB |  275  | IEEEChannel — JSON-LD + DOM walk on search page |
| `semanticscholar.py`   | 5.9 KB |  160  | SemanticScholarChannel — graph v1 paper/search |
| `googlescholar.py`     | 9.8 KB |  255  | GoogleScholarChannel — BeautifulSoup on `gs_r` nodes |

### Tests (`backend/imdf/crawler/channels/academic/__tests__/`)

| File                       | Tests | Coverage |
| -------------------------- | ----- | -------- |
| `__init__.py`              |   —   | package marker |
| `test_arxiv.py`            |   6   | search returns / parse extracts / error handling / http 500 / rate limit / arxiv_id extras |
| `test_pubmed.py`           |   6   | search returns / parse extracts / error handling / empty esearch / rate limit / authors helper |
| `test_ieee.py`             |   6   | search returns / parse extracts / error handling / http 500 / rate limit / empty html |
| `test_semanticscholar.py`  |   6   | search returns / parse extracts / error handling / http 500 / rate limit / max_results truncation |
| `test_googlescholar.py`    |   6   | search returns / parse extracts / error handling / http 500 / rate limit / empty html |
| **Total**                  | **30**| **all PASS** |

Test execution: 1.80 s with `python -m pytest
backend/imdf/crawler/channels/academic/__tests__/ -v
--override-ini="asyncio_mode=auto"`.

---

## Public API

```python
from imdf.crawler.channels.academic import (
    BaseAcademicCrawler,
    Paper,
    ArxivChannel,
    PubMedChannel,
    IEEEChannel,
    SemanticScholarChannel,
    GoogleScholarChannel,
)

# Async
cw = ArxivChannel()  # rate_limit_seconds=1.0 by default
papers: list[Paper] = await cw.search("transformer architectures",
                                      max_results=20)

# Sync
papers = cw.search_sync("transformer architectures")

# Static parser — can be used without an httpx client
records = ArxivChannel.parse(atom_xml)  # -> list[dict]
```

Each channel also exposes a `parse(html_or_json) -> list[dict]` static
method that converts the raw upstream payload into a list of dict
records (caller can then `parse_records(records, query=...)`).

---

## Sample queries (live upstream URLs)

| Channel             | Live URL |
| ------------------- | -------- |
| arxiv               | `http://export.arxiv.org/api/query?search_query=all:transformer&start=0&max_results=20` |
| pubmed              | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=covid+vaccine&retmax=20&retmode=json` (+ follow-up `esummary.fcgi`) |
| ieee                | `https://ieeexplore.ieee.org/search/searchresult.jsp?queryText=5G+network+slicing&highlight=true&returnType=SEARCH` |
| semanticscholar     | `https://api.semanticscholar.org/graph/v1/paper/search?query=transformer&limit=20&fields=title,abstract,authors,year,venue,externalIds,url,citationCount,openAccessPdf,publicationDate` |
| googlescholar       | `https://scholar.google.com/scholar?q=knowledge+distillation&hl=en&num=20` |

---

## Implementation notes

- **No new dependencies** — uses only `httpx` (already required) and
  `beautifulsoup4` (already installed for sibling image crawlers). No
  `lxml`/`feedparser`/etc. arxiv uses stdlib `xml.etree.ElementTree`.
- **Rate limiting** — a per-instance asyncio-Lock-based rate limiter
  in `BaseAcademicCrawler._rate_limit()`. Default `rate_limit_seconds`
  is `1.0`, except `GoogleScholarChannel` which uses `3.0` to honour
  Scholar's terms-of-service requirement.
- **Test isolation** — every channel accepts `transport=` (httpx
  `MockTransport`) so tests never hit the network. The existing
  `datasets/*.py` crawlers use the same pattern.
- **Graceful degradation** — network errors / HTTP 5xx / empty results
  all return `[]` and emit a `WARNING` log line. No exceptions escape.
- **Static `parse()`** — splits payload parsing from network I/O so
  tests can call the parser directly with a fixture. Mirrors the
  `parse_records` separation in the existing dataset crawlers.
- **Type safety** — return types are `List[Paper]` (Pydantic v2). All
  input strings are coerced and `None`-safe by the validators in
  `Paper`.

### Channel-specific design

- **Arxiv** — parses `<entry>` nodes with stdlib `xml.etree.ElementTree`.
  Captures `<arxiv:doi>`, `<arxiv:journal_ref>`, `<arxiv:comment>`, and
  the PDF link when present.
- **PubMed** — does the standard 2-step lookup (`esearch.fcgi` then
  `esummary.fcgi`) in one async chain. Author parsing handles both
  `authors[]` and the `authorlist.complete` fallback. Year is
  extracted from `pubdate` (e.g. `"2023 Apr"`).
- **IEEE** — first walks the page for JSON-LD (`<script
  type="application/ld+json">`); falls back to BeautifulSoup DOM
  traversal with selectors `.result-item`, `.description`, `.authors`,
  `.publication`, `.publication-year`. Year is regex-extracted from
  publication-year.
- **Semantic Scholar** — uses the public Graph API with a fixed
  `fields=` param list. Maps `externalIds.DOI` → `doi`,
  `externalIds.ArXiv` → `extra.arxiv_id`.
- **Google Scholar** — parses the classic `div.gs_r` nodes, extracting
  title, authors/venue/year from the `.gs_a` metadata line, the
  abstract from `.gs_rs`, citation count from "Cited by N", and PDF
  URL from any `[PDF]` link.

---

## Verification

```bash
D:/ComfyUI/.ext/python.exe -m pytest \
    backend/imdf/crawler/channels/academic/__tests__/ \
    -v --override-ini="asyncio_mode=auto"
```

Result:

```
============================== 30 passed, 1 warning in 1.80s ==============================
```

(Warning is the unrelated `Unknown config option: timeout` from
`backend/pytest.ini` — nothing to do with these tests.)

---

## Out of scope (deliberately skipped)

- **No auth flows** — none of these channels require an API key for the
  documented public endpoints.
- **No robots.txt cache** — the project-level robots.txt enforcement
  already lives in `crawler/base.py` (`RobotsPolicy` + `BaseCrawler`).
- **No re-architecture of the global crawler** — this task only adds
  the academic channel group.

---

## Deliverables

- 5 channel modules + base + Paper model at:
  `D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\academic\`
- 5 test files at the same dir under `__tests__/`
- Plan workspace deliverable:
  `C:\Users\Administrator\.mavis\plans\plan_ff72ae4c\outputs\p20_p20_d_academic\deliverable.md`
