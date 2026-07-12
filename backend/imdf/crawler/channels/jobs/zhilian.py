"""智联招聘 (www.zhaopin.com) jobs 渠道适配器 (P20-B2)

搜索 URL (公开):
    https://www.zhaopin.com/sou?kw={query}&p={page}

公开搜索 — 无需 API key.
HTML 结构 (简化):
    <div class="joblist-box__item">  <-- 职位卡片
        <a class="jobinfo__name">职位名</a>
        <div class="company__name">公司</div>
        <p class="jobinfo__salary">15-25K</p>
        <div class="jobinfo__other">地点|经验|学历</div>
    </div>

Pydantic v2 输出: List[JobPosting]
"""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar, List, Optional

from bs4 import BeautifulSoup, Tag

from ._base import BaseCrawlerChannel, JobPosting

logger = logging.getLogger(__name__)


_ZHILIAN_CARD_SELECTORS = (
    "div.joblist-box__item",
    "div.position-item",
    "div.contentpile__item",
    "li[class*='joblist']",
    "div[class*='joblist']",
)


class ZhilianChannel(BaseCrawlerChannel):
    """智联招聘 jobs 搜索 — 公开 HTML."""

    channel: ClassVar[str] = "zhilian"
    api_endpoint: ClassVar[str] = "https://www.zhaopin.com/sou?kw={query}&p={page}"

    async def _fetch(self, query: str, max_results: int) -> str:
        await self._rate_limiter.acquire()
        client = await self._ensure_client()
        url = self._build_url(query=query, page=1)
        if not self._robots_ok(url, client):
            return ""
        try:
            headers = self._headers()
            headers["Referer"] = "https://www.zhaopin.com/"
            resp = await client.get(url, headers=headers)
        except Exception as e:
            logger.warning("%s network error: %s", self.channel, e)
            return ""
        if resp.status_code != 200:
            logger.warning("%s status %d", self.channel, resp.status_code)
            return ""
        return resp.text

    @staticmethod
    def parse(html: str) -> List[JobPosting]:
        """静态解析智联职位列表 HTML → List[JobPosting]."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.debug("Zhilian BS4 init failed: %s", e)
            return []
        out: List[JobPosting] = []
        cards: List[Tag] = []
        for sel in _ZHILIAN_CARD_SELECTORS:
            try:
                found = soup.select(sel)
            except Exception:
                continue
            if found:
                cards = found
                break
        for idx, card in enumerate(cards):
            try:
                posting = ZhilianChannel._parse_card(card, idx)
                if posting and posting.title:
                    out.append(posting)
            except Exception as e:
                logger.debug("Zhilian card %d skip: %s", idx, e)
                continue
        return out

    @staticmethod
    def _parse_card(card: Tag, idx: int) -> Optional[JobPosting]:
        # 标题
        title_el = (
            card.select_one(".jobinfo__name")
            or card.select_one(".position-title")
            or card.select_one("a.jobinfo__name")
            or card.select_one("[class*='jobinfo__name']")
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None
        # URL
        url = ""
        anchor = (
            card.select_one("a.jobinfo__name")
            or card.select_one("a[href*='/jobs/']")
            or card.select_one("a[href*='zhaopin.com']")
        )
        if anchor and anchor.has_attr("href"):
            url = anchor["href"]
        if not url:
            url = f"https://www.zhaopin.com/jobs/placeholder_{idx}.html"
        elif url.startswith("/"):
            url = "https://www.zhaopin.com" + url
        # 公司
        company_el = (
            card.select_one(".company__name")
            or card.select_one(".company-name")
            or card.select_one("[class*='company__name']")
        )
        company = company_el.get_text(strip=True) if company_el else ""
        # 薪资
        salary_el = (
            card.select_one(".jobinfo__salary")
            or card.select_one(".salary")
            or card.select_one("[class*='salary']")
        )
        salary = salary_el.get_text(strip=True) if salary_el else ""
        # 地点 / 经验 / 学历 — 用 | 拆主结构, 内部用 · 拆城市/区
        info_el = (
            card.select_one(".jobinfo__other")
            or card.select_one(".job-info")
            or card.select_one("[class*='jobinfo__other']")
        )
        location = ""
        experience = ""
        education = ""
        if info_el:
            raw_text = info_el.get_text()
            # 用 | 拆主要三段 (地点|经验|学历)
            parts = [p.strip() for p in raw_text.split("|") if p.strip()]
            if parts:
                # 地点可能含 ·, e.g. "北京·海淀区" — 保留原样
                location = parts[0]
            if len(parts) >= 2:
                experience = parts[1]
            if len(parts) >= 3:
                education = parts[2]
        # 福利标签
        tag_els = card.select(".welfare__item, .tag-list span, [class*='welfare']")
        tags: List[str] = []
        for t in tag_els:
            txt = t.get_text(strip=True)
            if txt and len(txt) <= 30:
                tags.append(txt)
        # id
        m = re.search(r"/jobs?/([A-Za-z0-9]+)", url)
        posting_id = m.group(1) if m else f"zhilian_{idx}"
        return JobPosting(
            id=posting_id,
            title=title,
            company=company,
            salary=salary,
            location=location,
            url=url,
            source="zhilian",
            posted_at="",
            description="",
            tags=tags,
            extra={
                "experience": experience,
                "education": education,
                "channel": "zhilian",
            },
        )

    def _build_url(self, query: str, page: int = 1) -> str:
        from urllib.parse import quote_plus
        return self.api_endpoint.format(query=quote_plus(query), page=page)


__all__ = ["ZhilianChannel"]
