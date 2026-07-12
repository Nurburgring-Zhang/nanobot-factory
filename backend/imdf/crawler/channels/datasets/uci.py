"""UCI Machine Learning Repository crawler (P20-B1 batch 2)

UCI ML has no public REST API. Two relevant pages:
    https://archive.ics.uci.edu/dataset/{id}/{slug}    — single dataset
    https://archive.ics.uci.edu/datasets?search=<q>    — search page (HTML)

Approach: scrape the search results page with httpx + stdlib html.parser.
No external HTML lib required (keeps the dep footprint small).

Search result row (HTML):
    <a class="link-style" href="/dataset/53/iris">Iris</a>
    <div class="dataset-description">…</div>
    <div class="dataset-meta">…</div>
    <span class="dataset-tags">…</span>

If the search returns no rows (UCI modern layout sometimes returns JS-only),
we fall back to the static index pages:
    https://archive.ics.uci.edu/datasets (paginated HTML list)
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from . import BaseDatasetCrawler
from .dataset import Dataset

logger = logging.getLogger(__name__)


# ---- HTML parsers (stdlib only, no BeautifulSoup dependency) ----

class _UCISearchParser(HTMLParser):
    """Extract dataset links from UCI search / index page.

    Looks for <a href="/dataset/<id>/<slug>">NAME</a> blocks and tries to
    capture the surrounding <p> description when available.
    """

    LINK_RE = re.compile(r"/dataset/(\d+)/?([\w\-]+)?")

    def __init__(self) -> None:
        super().__init__()
        self.records: List[Dict[str, Any]] = []
        self._current_link: Optional[Dict[str, Any]] = None
        self._capture_text = False
        self._capture_into = None  # "title" | "description"
        self._buf: List[str] = []
        self._in_p = False
        self._p_depth = 0
        # Also accumulate any tags we see in adjacent <span> / <a class=…>
        self._capture_tags = False
        self._tag_buf: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_d = {k: v for k, v in attrs if v is not None}
        href = attr_d.get("href", "")
        m = self.LINK_RE.search(href)
        if m and tag == "a":
            self._current_link = {
                "id": m.group(1),
                "slug": m.group(2) or "",
                "url": f"https://archive.ics.uci.edu{href}",
            }
            self._capture_text = True
            self._capture_into = "title"
            self._buf = []
        elif tag in ("p", "div") and self._current_link is not None and not self._capture_text:
            # heuristic — capture description as next text chunk
            css_class = (attr_d.get("class") or "").lower()
            if any(k in css_class for k in ("description", "text", "body")):
                self._capture_text = True
                self._capture_into = "description"
                self._buf = []
        elif tag in ("span", "a") and self._current_link is not None:
            css_class = (attr_d.get("class") or "").lower()
            if "tag" in css_class:
                self._capture_tags = True
                self._tag_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture_text and tag == "a":
            text = "".join(self._buf).strip()
            if self._current_link is not None:
                if self._capture_into == "title":
                    self._current_link["title"] = html_lib.unescape(text)
            self._capture_text = False
            self._capture_into = None
            self._buf = []
        elif self._capture_text and tag in ("p", "div"):
            text = "".join(self._buf).strip()
            if self._current_link is not None and self._capture_into == "description":
                self._current_link["description"] = html_lib.unescape(text)
            self._capture_text = False
            self._capture_into = None
            self._buf = []
        elif self._capture_tags and tag in ("span", "a"):
            text = "".join(self._tag_buf).strip()
            if text:
                self._current_link.setdefault("tags", []).append(
                    html_lib.unescape(text)
                )
            self._capture_tags = False
            self._tag_buf = []
        elif tag in ("div", "section", "article") and self._current_link is not None:
            # emit record when container closes
            if self._current_link.get("title"):
                self.records.append(self._current_link)
            self._current_link = None

    def handle_data(self, data: str) -> None:
        if self._capture_text:
            self._buf.append(data)
        if self._capture_tags:
            self._tag_buf.append(data)


def parse_uci_search_html(html_text: str) -> List[Dict[str, Any]]:
    """Public helper — for direct test usage."""
    parser = _UCISearchParser()
    parser.feed(html_text)
    # Dedupe by id (sometimes link + close-button both produce links)
    seen = set()
    out: List[Dict[str, Any]] = []
    for rec in parser.records:
        rid = rec.get("id")
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rec)
    return out


# ---- Crawler ----

class UCIMLCrawler(BaseDatasetCrawler):
    """Search UCI ML Repository by scraping the search/index HTML pages.

    No API key needed. No external HTML lib needed (stdlib html.parser).
    """

    channel = "uci_ml"
    api_endpoint = "https://archive.ics.uci.edu/datasets"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.timeout < 30:
            self.timeout = 30.0

    async def _fetch_raw(self, query: str, max_results: int) -> List[Any]:
        url = f"{self.api_endpoint}?search={urllib.parse.quote(query)}"
        client = self._build_client()
        try:
            resp = await client.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "Mozilla/5.0 (compatible; imdf-crawler/1.0)",
                },
            )
            if resp.status_code != 200:
                logger.warning("UCI ML status %d", resp.status_code)
                return []
            html_text = resp.text
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)
        return parse_uci_search_html(html_text)

    def parse_records(self, records: List[Any], query: str = "") -> List[Dataset]:
        out: List[Dataset] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            try:
                ds_id = str(r.get("id") or f"uci_{idx}")
                slug = r.get("slug") or ""
                url = r.get("url") or f"https://archive.ics.uci.edu/dataset/{ds_id}"
                title = (r.get("title") or slug.replace("-", " ") or ds_id).strip()
                tags = r.get("tags") or []
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                tags_list: List[str] = []
                for t in tags:
                    if isinstance(t, str):
                        tags_list.append(t.strip())
                    elif isinstance(t, dict):
                        nm = t.get("name") or t.get("value") or t.get("label")
                        if nm:
                            tags_list.append(str(nm))
                ds = Dataset(
                    id=ds_id,
                    title=title or ds_id,
                    url=url,
                    size=None,
                    format=[],  # UCI doesn't expose formats in search HTML
                    tags=tags_list,
                    channel=self.channel,
                    description=str(r.get("description") or ""),
                    license=None,
                    downloads=None,
                    author=None,
                    last_updated=None,
                    extra={
                        "slug": slug,
                        "search_query": query,
                    },
                )
                if not ds.title:
                    ds = ds.model_copy(update={"title": ds.id})
                if not ds.url:
                    ds = ds.model_copy(update={
                        "url": f"https://archive.ics.uci.edu/dataset/{ds.id}",
                    })
                out.append(ds)
            except Exception as e:
                logger.debug("UCI record %d skipped: %s", idx, e)
                continue
        return out


__all__ = ["UCIMLCrawler", "parse_uci_search_html"]