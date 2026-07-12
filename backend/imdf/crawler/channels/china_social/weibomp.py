"""Weibo MP (微博号文章) channel — china_social (P20-H)

Search source: media.weibo.cn (Weibo media articles — long-form).

URL pattern:
    https://media.weibo.cn/article/articles?query={query}&page={n}
or
    https://media.weibo.cn/article/search?keyword={query}

HTML structure (media.weibo.cn — React-rendered SPA):
    The HTML is mostly empty; real data is in __INITIAL_STATE__ JSON.
    Pattern:
        <script>
          window.__INITIAL_STATE__ = { ... "articleList": [{...}] ... }
        </script>

Real Weibo API is at:
    https://m.weibo.cn/api/container/getIndex?containerid=...&query={q}

JSON shape (m.weibo.cn API):
    {
      "ok": 1,
      "data": {
        "cards": [
          {
            "card_type": 9,  // 9 = article
            "mblog": {
              "id": "...",
              "user": {"screen_name": "...", "profile_image_url": "..."},
              "text": "...",
              "created_at": "Mon Jan 01 12:34:56 +0800 2024",
              "page_info": {
                "page_title": "...",
                "content1": "...",
                "page_url": "..."
              }
            }
          }
        ]
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


class WeiboMPChannel(BaseCrawlerChannel):
    """微博文章搜索 — media.weibo.cn 入口.

    Usage:
        async with httpx.AsyncClient() as client:
            cw = WeiboMPChannel(client=client)
            results = await cw.search("AI 大模型", max_results=20)

    Note: media.weibo.cn 主体是 SPA, 直接抓 HTML 通常无内容.
    实测可走 m.weibo.cn 移动 API (JSON).
    本实现优先尝试 JSON API; 失败回退 HTML 解析.
    """

    channel: ClassVar[str] = "weibomp"
    api_endpoint: ClassVar[str] = "https://m.weibo.cn/api/container/getIndex"
    rate_per_sec: ClassVar[float] = 1.0

    # m.weibo.cn 搜索 containerid (公开搜索类型)
    _SEARCH_CONTAINERID = "100103type=1&q="

    def build_search_url(self, query: str, page: int = 1) -> str:
        """Weibo 移动 API 搜索 URL."""
        return (
            f"{self.api_endpoint}?containerid={self._SEARCH_CONTAINERID}"
            f"{quote_plus(query)}&page_type=searchall&page={max(1, page)}"
        )

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawlResult]:
        max_results = max(1, min(int(max_results), 100))
        url = self.build_search_url(query, page=1)
        # Weibo m.weibo.cn 返回 JSON
        headers = {"Accept": "application/json, text/plain, */*"}
        body = await self._fetch(url, headers=headers)
        if not body:
            return []
        # 优先尝试 JSON
        results: List[CrawlResult] = []
        try:
            data = json.loads(body)
            results = self._parse_json(data, query=query)
        except (json.JSONDecodeError, ValueError):
            logger.debug("%s JSON parse failed, falling back to HTML",
                         self.channel)
            try:
                results = self.parse(body)
            except Exception as e:
                logger.warning("%s HTML parse error: %s", self.channel, e)
                return []
        return results[:max_results]

    def _parse_json(self, data: Any, query: str = "") -> List[CrawlResult]:
        """解析 m.weibo.cn 搜索响应 JSON."""
        if not isinstance(data, dict):
            return []
        if data.get("ok") != 1:
            logger.debug("%s api not ok: %s", self.channel, data.get("msg"))
            return []
        cards = data.get("data", {}).get("cards", [])
        results: List[CrawlResult] = []
        for idx, card in enumerate(cards):
            if not isinstance(card, dict):
                continue
            mblog = card.get("mblog") or {}
            if not mblog:
                # card_type 9 = 文章卡片; 跳过其他类型
                continue
            user = mblog.get("user") or {}
            page_info = mblog.get("page_info") or {}
            mblog_id = mblog.get("id") or f"wb_{idx}"
            text = mblog.get("text", "")
            # strip HTML tags from text
            if text:
                text = re.sub(r"<[^>]+>", "", text).strip()
            title = page_info.get("page_title") or text[:80]
            url = page_info.get("page_url") or f"https://m.weibo.cn/detail/{mblog_id}"
            description = text or page_info.get("content1", "")
            author = user.get("screen_name", "")
            thumb = user.get("profile_image_url", "")
            date_str = mblog.get("created_at", "")
            try:
                results.append(CrawlResult(
                    id=f"weibomp_{mblog_id}",
                    url=url,
                    title=title,
                    description=description[:1000],
                    source="weibomp",
                    author=author,
                    keywords=[query] if query else [],
                    created_at=datetime.now(timezone.utc),
                    thumbnail_url=thumb,
                    extra={
                        "publish_date": date_str,
                        "weibo_id": mblog_id,
                        "channel_kind": "weibomp_article",
                        "verified": user.get("verified", False),
                        "followers_count": user.get("followers_count", 0),
                    },
                ))
            except Exception as e:
                logger.debug("weibomp result %d skipped: %s", idx, e)
                continue
        return results

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """统一解析入口 — JSON 优先, HTML fallback.

        兼容:
            - m.weibo.cn API JSON 响应 (body 是 JSON 字符串)
            - media.weibo.cn SPA HTML (含 __INITIAL_STATE__)
            - 普通 HTML 卡片
        """
        if not html or not html.strip():
            return []
        # 模式 1: 纯 JSON (m.weibo.cn API)
        stripped = html.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(html)
                ch = WeiboMPChannel()
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
                items: List[Any] = []
                if isinstance(data, dict):
                    for key in ("articleList", "cards", "list",
                                "data", "items"):
                        v = data.get(key)
                        if isinstance(v, list):
                            items = v
                            break
                out: List[CrawlResult] = []
                for idx, it in enumerate(items):
                    if not isinstance(it, dict):
                        continue
                    url = (it.get("url") or it.get("scheme")
                           or it.get("page_url") or "")
                    if not url:
                        continue
                    user_obj = it.get("user")
                    if isinstance(user_obj, dict):
                        author = (user_obj.get("screen_name", "")
                                  or user_obj.get("name", ""))
                    else:
                        author = (str(user_obj or "")
                                  or str(it.get("author") or ""))
                    try:
                        out.append(CrawlResult(
                            id=str(it.get("id") or f"weibomp_{idx:04d}"),
                            url=url,
                            title=it.get("title")
                            or it.get("page_title") or "",
                            description=it.get("text")
                            or it.get("content") or "",
                            source="weibomp",
                            author=author,
                            keywords=[],
                            created_at=datetime.now(timezone.utc),
                            thumbnail_url=it.get("thumbnail")
                            or it.get("cover", ""),
                            extra={
                                "channel_kind": "weibomp_article",
                            },
                        ))
                    except Exception as e:
                        logger.debug("weibomp result %d skipped: %s", idx, e)
                        continue
                if out:
                    return out
            except (json.JSONDecodeError, ValueError):
                pass
        # 模式 3: DOM fallback
        soup: Optional[BeautifulSoup] = None
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        return _parse_weibomp_dom(soup)


def _parse_weibomp_dom(soup: BeautifulSoup) -> List[CrawlResult]:
    """DOM 回退解析 — 找 .m-card 或 .article-card 类容器."""
    out: List[CrawlResult] = []
    for idx, card in enumerate(soup.select(
            ".m-card, .article-card, .card, [data-id]")):
        link = (card.select_one("a[href*='weibo.cn']")
                or card.select_one("a[href*='weibo.com']")
                or card.select_one("a"))
        if not link:
            continue
        url = link.get("href", "")
        if not url or url.startswith("javascript"):
            continue
        title = link.get_text(strip=True) or card.get("data-title", "")
        try:
            out.append(CrawlResult(
                id=str(card.get("data-id") or f"weibomp_{idx:04d}"),
                url=url,
                title=title,
                description=card.get_text(strip=True)[:500],
                source="weibomp",
                author="",
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url="",
                extra={"channel_kind": "weibomp_dom"},
            ))
        except Exception:
            continue
    return out


__all__ = ["WeiboMPChannel"]