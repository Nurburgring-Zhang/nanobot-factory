"""Bilibili MP (B站UP主) channel — china_social (P20-H)

Search source: api.bilibili.com (公开搜索 API — 无需登录).

URL pattern:
    https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword={query}

JSON shape (real API):
    {
      "code": 0,
      "data": {
        "result": [
          {
            "mid": 123456,
            "uname": "UP主名字",
            "usign": "签名",
            "level": 6,
            "fans": 12345,
            "videos": 100,
            "upic": "https://...",
            "room_id": 0,
            "official_verify": {
              "type": -1,
              "desc": ""
            }
          }
        ],
        "numResults": 100,
        "pages": 5
      },
      "message": "0",
      "ttl": 1
    }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, ClassVar, List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ._base import BaseCrawlerChannel, CrawlResult

logger = logging.getLogger(__name__)


class BilibiliMPChannel(BaseCrawlerChannel):
    """B 站 UP 主搜索 — bilibili API 入口.

    Usage:
        async with httpx.AsyncClient() as client:
            cw = BilibiliMPChannel(client=client)
            results = await cw.search("Python 教程", max_results=20)
    """

    channel: ClassVar[str] = "bilibilimp"
    api_endpoint: ClassVar[str] = (
        "https://api.bilibili.com/x/web-interface/search/type"
    )
    rate_per_sec: ClassVar[float] = 1.0

    def build_search_url(self, query: str, page: int = 1) -> str:
        # search_type=bili_user → UP 主
        return (
            f"{self.api_endpoint}?search_type=bili_user"
            f"&keyword={quote_plus(query)}&page={max(1, page)}&pagesize=20"
        )

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawlResult]:
        max_results = max(1, min(int(max_results), 100))
        url = self.build_search_url(query, page=1)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://search.bilibili.com/",
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
        """解析 bilibili 搜索响应 JSON."""
        if not isinstance(data, dict):
            return []
        if data.get("code") != 0:
            logger.debug("%s code=%s msg=%s",
                         self.channel, data.get("code"), data.get("message"))
            # 仍然尝试 — code=-101 通常是未登录但搜索仍可拿到 result
        inner = data.get("data") or {}
        result = inner.get("result") if isinstance(inner, dict) else None
        if not isinstance(result, list):
            return []
        results: List[CrawlResult] = []
        for idx, it in enumerate(result):
            if not isinstance(it, dict):
                continue
            mid = it.get("mid") or f"bili_{idx}"
            uname = it.get("uname") or ""
            usign = it.get("usign") or ""
            level = it.get("level") or 0
            fans = it.get("fans") or 0
            videos = it.get("videos") or 0
            upic = it.get("upic") or ""
            room_id = it.get("room_id") or 0
            ov = it.get("official_verify") or {}
            ov_type = ov.get("type", -1) if isinstance(ov, dict) else -1
            ov_desc = ov.get("desc", "") if isinstance(ov, dict) else ""
            url = f"https://space.bilibili.com/{mid}"
            try:
                results.append(CrawlResult(
                    id=f"bilibilimp_{mid}",
                    url=url,
                    title=uname,
                    description=usign,
                    source="bilibilimp",
                    author=uname,
                    keywords=[],
                    created_at=datetime.now(timezone.utc),
                    thumbnail_url=upic,
                    extra={
                        "mid": mid,
                        "level": level,
                        "fans": fans,
                        "videos": videos,
                        "room_id": room_id,
                        "official_verify_type": ov_type,
                        "official_verify_desc": ov_desc,
                        "channel_kind": "bilibilimp_user",
                    },
                ))
            except Exception as e:
                logger.debug("bilibilimp user %d skipped: %s", idx, e)
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
                ch = BilibiliMPChannel()
                results = ch._parse_json(data)
                if results:
                    return results
            except (json.JSONDecodeError, ValueError):
                pass
        # 模式 2: __INITIAL_STATE__ 嵌入 HTML
        import re
        m = re.search(r"__INITIAL_STATE__\s*=\s*(\{.+?\});?\s*</script>",
                      html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                results = _extract_bili_users(data)
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
        return _parse_bili_dom(soup)


def _extract_bili_users(data: Any) -> List[CrawlResult]:
    """递归查找 result 列表 — 仅取最浅层匹配一次."""
    found: List[Any] = []
    seen_ids: set = set()

    def try_emit(items: List[Any]) -> bool:
        """尝试发射 list — 若包含像 user 字典就 emit."""
        emitted = 0
        for it in items:
            if isinstance(it, dict) and (
                "uname" in it or "name" in it or "mid" in it
            ):
                _id = id(it)
                if _id not in seen_ids:
                    seen_ids.add(_id)
                    found.append(it)
                    emitted += 1
        return emitted > 0

    def walk(o: Any, depth: int = 0) -> bool:
        """返回 True 表示已找到结果, 不再下钻."""
        if isinstance(o, dict):
            # 模式: data.result = [users]
            d = o.get("data")
            if isinstance(d, dict) and isinstance(d.get("result"), list):
                if try_emit(d["result"]):
                    return True
            for key in ("result", "userList", "users", "items"):
                v = o.get(key)
                if isinstance(v, list) and try_emit(v):
                    return True
            for v in o.values():
                if walk(v, depth + 1):
                    return True
        elif isinstance(o, list):
            for it in o:
                if walk(it, depth + 1):
                    return True
        return False

    walk(data)
    results: List[CrawlResult] = []
    for idx, it in enumerate(found):
        if not isinstance(it, dict):
            continue
        mid = it.get("mid") or f"bili_{idx}"
        uname = it.get("uname") or it.get("name") or ""
        if not uname:
            continue
        try:
            results.append(CrawlResult(
                id=f"bilibilimp_ssr_{mid}",
                url=f"https://space.bilibili.com/{mid}",
                title=uname,
                description=it.get("usign") or it.get("sign") or "",
                source="bilibilimp",
                author=uname,
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url=it.get("upic") or it.get("face", ""),
                extra={
                    "mid": mid,
                    "fans": it.get("fans", 0),
                    "channel_kind": "bilibilimp_user_ssr",
                },
            ))
        except Exception:
            continue
    return results


def _parse_bili_dom(soup: BeautifulSoup) -> List[CrawlResult]:
    """DOM 回退解析 — 找 .user-card / .up-card 类容器."""
    out: List[CrawlResult] = []
    for idx, card in enumerate(soup.select(
            ".user-card, .up-card, .bili-user-card, "
            "[class*='UserCard']")):
        link = (card.select_one("a[href*='space.bilibili.com']")
                or card.select_one("a"))
        if not link:
            continue
        url = link.get("href", "")
        if not url or url.startswith("javascript"):
            continue
        title = (link.get_text(strip=True)
                 or card.get("data-uname", ""))
        try:
            out.append(CrawlResult(
                id=f"bilibilimp_dom_{idx:04d}",
                url=url,
                title=title,
                description=card.get_text(strip=True)[:500],
                source="bilibilimp",
                author=title,
                keywords=[],
                created_at=datetime.now(timezone.utc),
                thumbnail_url="",
                extra={"channel_kind": "bilibilimp_user_dom"},
            ))
        except Exception:
            continue
    return out


__all__ = ["BilibiliMPChannel"]