"""Douyin MP (抖音号) channel — china_social (P20-H)

Search source: www.douyin.com/user — public user search.

URL pattern:
    https://www.douyin.com/search/{query}/?type=user
or
    https://www.douyin.com/aweme/v1/web/search/item/?keyword={query}

Douyin is a heavy-SPA + dynamic-loaded content site.
Real data is loaded via XHR to:
    https://www.douyin.com/aweme/v1/web/search/item/?keyword=...
or via embedded _ROUTER_DATA in HTML.

HTML structure (when accessible):
    window._ROUTER_DATA = {...user_list: [{user_info: {...}}]...}

JSON shape (Douyin search API):
    {
      "status_code": 0,
      "user_list": [
        {
          "user_info": {
            "uid": "...",
            "nickname": "...",
            "signature": "...",
            "follower_count": 12345,
            "aweme_count": 100,
            "avatar_thumb": {"url_list": ["..."]},
            "share_info": {"share_url": "..."}
          }
        }
      ]
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


class DouyinMPChannel(BaseCrawlerChannel):
    """抖音用户搜索 — Douyin web 入口.

    Usage:
        async with httpx.AsyncClient() as client:
            cw = DouyinMPChannel(client=client)
            results = await cw.search("美食探店", max_results=20)
    """

    channel: ClassVar[str] = "douyinmp"
    api_endpoint: ClassVar[str] = "https://www.douyin.com/aweme/v1/web/search/item/"
    rate_per_sec: ClassVar[float] = 1.0

    def build_search_url(self, query: str, page: int = 1) -> str:
        return (
            f"{self.api_endpoint}?keyword={quote_plus(query)}"
            f"&search_user=%7B%22from_group_id%22%3A%22%22%7D"
            f"&offset={max(0, (page - 1) * 20)}&count=20"
        )

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawlResult]:
        max_results = max(1, min(int(max_results), 100))
        url = self.build_search_url(query, page=1)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.douyin.com/",
        }
        body = await self._fetch(url, headers=headers)
        if not body:
            return []
        # JSON 优先
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
        """解析 Douyin 搜索 JSON — 关注 user_list."""
        if not isinstance(data, dict):
            return []
        if data.get("status_code") not in (0, None):
            logger.debug("%s status_code=%s",
                         self.channel, data.get("status_code"))
        user_list = data.get("user_list") or []
        results: List[CrawlResult] = []
        for idx, entry in enumerate(user_list):
            if not isinstance(entry, dict):
                continue
            ui = entry.get("user_info") or {}
            if not ui:
                continue
            uid = ui.get("uid") or ui.get("sec_uid") or f"dy_{idx}"
            nickname = ui.get("nickname", "")
            signature = ui.get("signature", "")
            follower = ui.get("follower_count", 0)
            aweme_count = ui.get("aweme_count", 0)
            # 头像 URL (优先缩略图)
            avatar = ""
            thumb_obj = ui.get("avatar_thumb") or ui.get("avatar_medium")
            if isinstance(thumb_obj, dict):
                urls = thumb_obj.get("url_list") or []
                if urls:
                    avatar = urls[0]
            elif isinstance(thumb_obj, str):
                avatar = thumb_obj
            # 分享 URL
            share_info = ui.get("share_info") or {}
            url = (share_info.get("share_url")
                   or f"https://www.douyin.com/user/{ui.get('sec_uid', uid)}")
            try:
                results.append(CrawlResult(
                    id=f"douyinmp_{uid}",
                    url=url,
                    title=nickname,
                    description=signature,
                    source="douyinmp",
                    author=nickname,
                    keywords=[],
                    created_at=datetime.now(timezone.utc),
                    thumbnail_url=avatar,
                    extra={
                        "uid": uid,
                        "sec_uid": ui.get("sec_uid", ""),
                        "follower_count": follower,
                        "aweme_count": aweme_count,
                        "verified": ui.get("enterprise_verify_reason", ""),
                        "channel_kind": "douyinmp_user",
                    },
                ))
            except Exception as e:
                logger.debug("douyinmp user %d skipped: %s", idx, e)
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
                ch = DouyinMPChannel()
                results = ch._parse_json(data)
                if results:
                    return results
            except (json.JSONDecodeError, ValueError):
                pass
        # 模式 2: _ROUTER_DATA 嵌入 HTML
        import re as _re
        m = _re.search(r"_ROUTER_DATA\s*=\s*(\{.+?\})\s*[;<]",
                       html, _re.DOTALL)
        # 模式 3: __INITIAL_STATE__ 嵌入 HTML
        if not m:
            m = _re.search(r"__INITIAL_STATE__\s*=\s*(\{.+?\});?\s*</script>",
                           html, _re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                results = _extract_users_from_routdata(data)
                if results:
                    return results
            except (json.JSONDecodeError, ValueError):
                pass
        # 模式 4: DOM fallback
        soup: Optional[BeautifulSoup] = None
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        return _parse_douyinmp_dom(soup)


def _extract_users_from_routdata(data: Any) -> List[CrawlResult]:
    """递归查找 user_list 字段并解析."""
    found: List[Any] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if "user_list" in o and isinstance(o["user_list"], list):
                found.extend(o["user_list"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(data)
    results: List[CrawlResult] = []
    for idx, entry in enumerate(found):
        if not isinstance(entry, dict):
            continue
        ui = entry.get("user_info") or entry
        uid = ui.get("uid") or f"dy_{idx}"
        nickname = ui.get("nickname", "")
        signature = ui.get("signature", "")
        try:
            results.append(CrawlResult(
                id=f"douyinmp_{uid}",
                url=f"https://www.douyin.com/user/{ui.get('sec_uid', uid)}",
                title=nickname,
                description=signature,
                source="douyinmp",
                author=nickname,
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url="",
                extra={
                    "uid": uid,
                    "channel_kind": "douyinmp_user_routed",
                },
            ))
        except Exception:
            continue
    return results


def _parse_douyinmp_dom(soup: BeautifulSoup) -> List[CrawlResult]:
    """DOM 回退解析."""
    out: List[CrawlResult] = []
    for idx, card in enumerate(soup.select(
            "[data-e2e='search-user-card'], .user-card, "
            "[class*='UserCard'], [class*='userInfo']")):
        link = (card.select_one("a[href*='/user/']")
                or card.select_one("a"))
        if not link:
            continue
        url = link.get("href", "")
        if not url or url.startswith("javascript"):
            continue
        title = link.get_text(strip=True) or card.get("data-nickname", "")
        try:
            out.append(CrawlResult(
                id=f"douyinmp_dom_{idx:04d}",
                url=url,
                title=title,
                description=card.get_text(strip=True)[:500],
                source="douyinmp",
                author=title,
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url="",
                extra={"channel_kind": "douyinmp_user_dom"},
            ))
        except Exception:
            continue
    return out


__all__ = ["DouyinMPChannel"]