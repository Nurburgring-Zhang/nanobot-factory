"""V5 P2 channel — Reach: web / twitter / github / arxiv (multi-source).

This module consolidates the four reach_* skills into a single channel
class with a real HTTP backend per source. Each source has a public
no-auth API (or HTML page) and a deterministic mock fallback:

  - reach_web:       any URL via the HTTP helper
  - reach_twitter:   nitter.net mirror (HTML parse, no API key)
  - reach_github:    api.github.com/repos/{owner}/{name} (no key for public repos)
  - reach_arxiv:     export.arxiv.org/api/query (no key, real Atom XML)

Select source via the ``source`` kwarg in ``fetch(query, source=...)``.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from typing import Any, List, Optional

from imdf.intelligence.agent_reach.channels._http import http_get_json, http_get_text
from imdf.intelligence.agent_reach.schemas import FetchResult


def _mock_items(source: str, query: str) -> List[dict]:
    h = hashlib.md5(f"{source}|{query}".encode("utf-8")).hexdigest()[:6]
    return [
        {
            "title": f"[Mock {source}] Result #{i}: {query}",
            "url": f"https://example.com/{source}/{h}{i:02d}",
            "snippet": f"Mock snippet for {source} query={query} #{i}",
        }
        for i in range(3)
    ]


class ReachWebAPI:
    """Generic URL fetch + title/links/size extraction."""

    channel = "reach_web"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        url = query if query.startswith("http") else ""
        items: List[dict] = []
        source = "mock"
        if url:
            try:
                text = await http_get_text(url, timeout=15.0)
                title_m = re.search(r"<title[^>]*>([^<]*)</title>", text, re.I)
                items.append({
                    "title": title_m.group(1) if title_m else url,
                    "url": url,
                    "snippet": text[:500],
                    "size": len(text),
                })
                source = "http"
            except Exception:
                pass
        if not items:
            items = _mock_items("web", query)
            source = "mock-fallback"
        return FetchResult(
            success=True, channel=self.channel, query=query,
            content="\n".join(it.get("title", "") for it in items),
            url=url or items[0]["url"],
            content_type="text/html",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )


class ReachTwitterAPI:
    channel = "reach_twitter"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        handle = query.lstrip("@")
        items: List[dict] = []
        source = "mock"
        if handle:
            try:
                html = await http_get_text(f"https://nitter.net/{handle}", timeout=10.0)
                # Each tweet is in a <div class="timeline-item"> ... </div>
                pattern = re.compile(r'<div class="tweet-content[^"]*"[^>]*>(.*?)</div>', re.S)
                titles = pattern.findall(html)
                for i, t in enumerate(titles[:10]):
                    text = re.sub(r"<[^>]+>", "", t).strip()
                    items.append({
                        "title": text[:200],
                        "url": f"https://twitter.com/{handle}/status/mock{i}",
                        "snippet": text,
                    })
                if items:
                    source = "nitter"
            except Exception:
                pass
        if not items:
            items = _mock_items("twitter", query)
            source = "mock-fallback"
        return FetchResult(
            success=True, channel=self.channel, query=query,
            content="\n".join(it.get("title", "") for it in items),
            url=f"https://twitter.com/{handle}" if handle else items[0]["url"],
            content_type="text/html",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )


class ReachGithubAPI:
    channel = "reach_github"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        repo = query.strip()
        items: List[dict] = []
        source = "mock"
        if "/" in repo:
            try:
                data = await http_get_json(f"https://api.github.com/repos/{repo}")
                items.append({
                    "title": data.get("full_name", repo),
                    "url": data.get("html_url", f"https://github.com/{repo}"),
                    "snippet": data.get("description", ""),
                    "stars": data.get("stargazers_count", 0),
                    "forks": data.get("forks_count", 0),
                    "language": data.get("language", ""),
                    "updated_at": data.get("updated_at", ""),
                })
                source = "github-api"
            except Exception:
                pass
        if not items:
            items = _mock_items("github", query)
            source = "mock-fallback"
        return FetchResult(
            success=True, channel=self.channel, query=query,
            content="\n".join(it.get("title", "") for it in items),
            url=items[0]["url"],
            content_type="application/json",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )


class ReachArxivAPI:
    channel = "reach_arxiv"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        items: List[dict] = []
        source = "mock"
        if query:
            try:
                url = f"http://export.arxiv.org/api/query?search_query={query}&max_results=10"
                text = await http_get_text(url, timeout=15.0)
                entries = re.findall(r"<entry>(.*?)</entry>", text, re.S)
                for e in entries[:10]:
                    title_m = re.search(r"<title>(.*?)</title>", e, re.S)
                    id_m = re.search(r"<id>(.*?)</id>", e)
                    author_m = re.findall(r"<author>\s*<name>(.*?)</name>", e)
                    pub_m = re.search(r"<published>(.*?)</published>", e)
                    items.append({
                        "title": re.sub(r"\s+", " ", title_m.group(1) if title_m else "").strip(),
                        "url": id_m.group(1) if id_m else "",
                        "authors": author_m,
                        "published": pub_m.group(1) if pub_m else "",
                    })
                if items:
                    source = "arxiv-api"
            except Exception:
                pass
        if not items:
            items = _mock_items("arxiv", query)
            source = "mock-fallback"
        return FetchResult(
            success=True, channel=self.channel, query=query,
            content="\n".join(it.get("title", "") for it in items),
            url=f"http://export.arxiv.org/api/query?search_query={query}",
            content_type="application/atom+xml",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )
