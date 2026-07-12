"""Wechat MP (微信公众号) channel — china_social (P20-H)

Search source: weixin.sogou.com (Sogou mirror — only public crawler entry
that doesn't require login for index queries).

URL pattern:
    https://weixin.sogou.com/weixin?type=2&query={query}&page={n}

HTML structure (Sogou mirror):
    <li class="news-list__item">
      <div class="txt-box">
        <a href="/link?url=...&k=...&..." target="_blank">{title}</a>
        <p class="txt-info">{description}</p>
        <div class="s-p">
          <a class="account">{author}</a>
          <span class="time">{date}</span>
        </div>
      </div>
    </li>

Real WeChat (mp.weixin.qq.com) requires __biz + signature in URL — only
search-engine indexed pages are scrape-able. Sogou mirror is the
de-facto public search gateway.

Robots.txt note: weixin.sogou.com Disallows /weixin for many bots.
Default BaseCrawlerChannel respects this. If you need to bypass (e.g.
in test env), pass `respect_robots=False`.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional
from urllib.parse import quote_plus, unquote

from bs4 import BeautifulSoup

from ._base import BaseCrawlerChannel, CrawlResult

logger = logging.getLogger(__name__)


class WechatMPChannel(BaseCrawlerChannel):
    """微信公众号搜索 — Sogou mirror 入口.

    Usage:
        async with httpx.AsyncClient() as client:
            cw = WechatMPChannel(client=client)
            results = await cw.search("AI 大模型", max_results=20)

        # or test:
        cw = WechatMPChannel(transport=mock_transport)
        results = await cw.search("AI 大模型")

    Returns:
        List[CrawlResult] (空 list 表示无结果 / 失败 / robots.txt 拒绝)
    """

    channel: ClassVar[str] = "wechatmp"
    api_endpoint: ClassVar[str] = "https://weixin.sogou.com/weixin"
    rate_per_sec: ClassVar[float] = 1.0

    def build_search_url(self, query: str, page: int = 1) -> str:
        """Sogou 微信搜索 URL — type=2 (文章)."""
        return (
            f"{self.api_endpoint}?type=2&query={quote_plus(query)}"
            f"&page={max(1, page)}"
        )

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawlResult]:
        max_results = max(1, min(int(max_results), 100))
        url = self.build_search_url(query, page=1)
        html = await self._fetch(url)
        if not html:
            return []
        try:
            results = self.parse(html)
        except Exception as e:
            logger.warning("%s parse error: %s", self.channel, e)
            return []
        return results[:max_results]

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """解析 Sogou 微信搜索 HTML → List[CrawlResult].

        模式 1 (Sogou):
            li.news-list__item > div.txt-box > a[href*="/link?"]
        模式 2 (Sogou alternate):
            div.news-list__item > a[href*=mp.weixin.qq.com]
        模式 3 (raw text fallback):
            href 包含 "mp.weixin.qq.com"
        """
        if not html or not html.strip():
            return []
        soup: Optional[BeautifulSoup] = None
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []

        results: List[CrawlResult] = []

        # 模式 1 + 2: news-list__item 列表
        for idx, li in enumerate(soup.select("li.news-list__item, "
                                            "div.news-list__item")):
            # 标题 + URL
            link = (li.select_one("div.txt-box h3 a")
                    or li.select_one("h3 a")
                    or li.select_one("a[href*='/link?']")
                    or li.select_one("a[href*='mp.weixin.qq.com']"))
            if not link:
                continue
            title = (link.get_text(strip=True)
                     or link.get("title", "")
                     or "")
            href = link.get("href", "")
            # Sogou /link?url= 解码
            if "/link?" in href:
                m = re.search(r"[?&]url=([^&]+)", href)
                if m:
                    href = unquote(m.group(1))
            if not href or "javascript:" in href.lower():
                continue

            # 描述
            desc_el = (li.select_one("p.txt-info")
                       or li.select_one("div.txt-info")
                       or li.select_one("p"))
            description = desc_el.get_text(strip=True) if desc_el else ""

            # 作者 (公众号)
            author_el = (li.select_one("a.account")
                         or li.select_one("span.account")
                         or li.select_one(".s-p a"))
            author = author_el.get_text(strip=True) if author_el else ""

            # 时间
            time_el = (li.select_one("span.time")
                       or li.select_one(".s-p .time")
                       or li.select_one("span"))
            date_str = time_el.get_text(strip=True) if time_el else ""

            # 缩略图 (Sogou)
            img_el = (li.select_one("div.img-box img")
                      or li.select_one("img"))
            thumb = img_el.get("src", "") if img_el else ""

            try:
                results.append(CrawlResult(
                    id=f"wechatmp_{idx:04d}_{abs(hash(href)) % 100000}",
                    url=href,
                    title=title,
                    description=description,
                    source="wechatmp",
                    author=author,
                    keywords=[],
                    created_at=datetime.now(timezone.utc),
                    thumbnail_url=thumb,
                    extra={
                        "publish_date": date_str,
                        "snippet": description[:200] if description else "",
                        "channel_kind": "wechatmp_article",
                    },
                ))
            except Exception as e:
                logger.debug("wechatmp result %d skipped: %s", idx, e)
                continue

        return results


__all__ = ["WechatMPChannel"]