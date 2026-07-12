"""Xigua (西瓜视频) channel — china_social (P20-H)

Search source: www.ixigua.com — 头条系长视频平台.

URL pattern:
    https://www.ixigua.com/search/{query}/
or
    https://www.ixigua.com/api/search?keyword={query}

HTML structure:
    Xigua HTML is partly server-rendered, with SSR-snapshot in
    window.__INITIAL_STATE__ JSON.

JSON shape:
    {
      "data": {
        "searchResult": {
          "data": [
            {
              "title": "...",
              "abstract": "...",
              "video_id": "...",
              "video_url": "...",
              "user": {"name": "...", "user_id": "..."},
              "play_count": 0,
              "duration": 0,
              "publish_time": "..."
            }
          ]
        }
      }
    }
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, ClassVar, List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ._base import BaseCrawlerChannel, CrawlResult

logger = logging.getLogger(__name__)


class XiguaChannel(BaseCrawlerChannel):
    """西瓜视频搜索 — ixigua.com 入口.

    Usage:
        async with httpx.AsyncClient() as client:
            cw = XiguaChannel(client=client)
            results = await cw.search("美食教程", max_results=20)
    """

    channel: ClassVar[str] = "xigua"
    api_endpoint: ClassVar[str] = "https://www.ixigua.com/api/search"
    rate_per_sec: ClassVar[float] = 1.0

    def build_search_url(self, query: str, page: int = 1) -> str:
        return (
            f"{self.api_endpoint}?keyword={quote_plus(query)}"
            f"&offset={(max(1, page) - 1) * 20}&count=20"
        )

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawlResult]:
        max_results = max(1, min(int(max_results), 100))
        url = self.build_search_url(query, page=1)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.ixigua.com/",
        }
        body = await self._fetch(url, headers=headers)
        if not body:
            return []
        results: List[CrawlResult] = []
        try:
            data = json.loads(body)
            results = self._parse_json(data)
        except (json.JSONDecodeError, ValueError):
            logger.debug("%s JSON parse failed, falling back to HTML",
                         self.channel)
            try:
                results = self.parse(body)
            except Exception as e:
                logger.warning("%s HTML parse error: %s", self.channel, e)
                return []
        return results[:max_results]

    def _parse_json(self, data: Any) -> List[CrawlResult]:
        """解析 Xigua 搜索响应 JSON."""
        if not isinstance(data, dict):
            return []
        # 多入口兼容
        items: List[Any] = []
        for key in ("data", "items", "results", "videos", "searchResult"):
            v = data.get(key)
            if isinstance(v, list):
                items = v
                break
            elif isinstance(v, dict):
                for sub in ("data", "items", "results", "videos"):
                    inner = v.get(sub)
                    if isinstance(inner, list):
                        items = inner
                        break
                if items:
                    break
        results: List[CrawlResult] = []
        for idx, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            title = it.get("title") or ""
            abstract = it.get("abstract") or it.get("description") or ""
            video_id = (it.get("video_id") or it.get("id")
                        or f"xg_{idx}")
            video_url = (it.get("video_url") or it.get("url")
                         or f"https://www.ixigua.com/{video_id}")
            user_obj = it.get("user") or {}
            if isinstance(user_obj, dict):
                author = user_obj.get("name", "")
            else:
                author = str(user_obj) if user_obj else ""
            play_count = it.get("play_count", 0)
            duration = it.get("duration", 0)
            publish_time = it.get("publish_time", "")
            thumb = (it.get("poster_url") or it.get("cover_url")
                     or it.get("thumbnail") or "")
            try:
                results.append(CrawlResult(
                    id=f"xigua_{video_id}",
                    url=video_url,
                    title=title,
                    description=abstract,
                    source="xigua",
                    author=author,
                    keywords=[],
                    created_at=datetime.now(timezone.utc),
                    thumbnail_url=thumb,
                    extra={
                        "video_id": video_id,
                        "play_count": play_count,
                        "duration": duration,
                        "publish_time": publish_time,
                        "channel_kind": "xigua_video",
                    },
                ))
            except Exception as e:
                logger.debug("xigua video %d skipped: %s", idx, e)
                continue
        return results

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """统一解析入口 — JSON 优先, HTML fallback."""
        if not html or not html.strip():
            return []
        stripped = html.lstrip()
        # 模式 1: 纯 JSON API 响应
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(html)
                ch = XiguaChannel()
                results = ch._parse_json(data)
                if results:
                    return results
            except (json.JSONDecodeError, ValueError):
                pass
        # 模式 2: __INITIAL_STATE__ 嵌入 HTML
        m = re.search(r"__INITIAL_STATE__\s*=\s*(\{.+?\});?\s*</script>",
                      html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                results = _extract_xigua_videos(data)
                if results:
                    return results
            except (json.JSONDecodeError, ValueError):
                pass
        # 模式 3: DOM fallback
        soup: Optional[BeautifulSoup] = None
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        return _parse_xigua_dom(soup)


def _extract_xigua_videos(data: Any) -> List[CrawlResult]:
    """递归查找 data.searchResult.data 结构."""
    found: List[Any] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            # 模式 1: data.searchResult.data = [videos]
            d = o.get("data")
            if isinstance(d, dict):
                sr = d.get("searchResult")
                if isinstance(sr, dict) and isinstance(sr.get("data"), list):
                    found.extend(sr["data"])
            # 模式 2: data.items = [videos]
            for key in ("items", "videos", "results"):
                v = o.get(key)
                if isinstance(v, list):
                    found.extend(v)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(data)
    results: List[CrawlResult] = []
    for idx, it in enumerate(found):
        if not isinstance(it, dict):
            continue
        title = it.get("title", "")
        if not title:
            continue
        try:
            results.append(CrawlResult(
                id=str(it.get("video_id") or it.get("id") or f"xg_{idx:04d}"),
                url=it.get("video_url") or f"https://www.ixigua.com/{idx}",
                title=title,
                description=it.get("abstract") or "",
                source="xigua",
                author=str(it.get("user", "") or ""),
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url=it.get("poster_url") or "",
                extra={"channel_kind": "xigua_video_ssr"},
            ))
        except Exception:
            continue
    return results


def _parse_xigua_dom(soup: BeautifulSoup) -> List[CrawlResult]:
    """DOM 回退解析."""
    out: List[CrawlResult] = []
    for idx, card in enumerate(soup.select(
            ".video-card, [class*='VideoCard'], [class*='videoItem']")):
        link = (card.select_one("a[href*='/video/']")
                or card.select_one("a[href*='ixigua.com']")
                or card.select_one("a"))
        if not link:
            continue
        url = link.get("href", "")
        if not url or url.startswith("javascript"):
            continue
        title = link.get_text(strip=True) or card.get("data-title", "")
        try:
            out.append(CrawlResult(
                id=f"xigua_dom_{idx:04d}",
                url=url,
                title=title,
                description=card.get_text(strip=True)[:500],
                source="xigua",
                author="",
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url="",
                extra={"channel_kind": "xigua_video_dom"},
            ))
        except Exception:
            continue
    return out


__all__ = ["XiguaChannel"]