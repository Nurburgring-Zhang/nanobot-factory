"""前程无忧 / 51job (www.51job.com) jobs 渠道适配器 (P20-B2)

搜索 URL (公开):
    https://search.51job.com/list/000000,000000,0000,00,9,99,{query},2,{page}.html

公开搜索 — 无需 API key.
HTML 结构 (简化):
    <div class="el">  <-- 职位卡片
        <p class="t1">
            <a class="el" href="...">职位名</a>
        </p>
        <span class="t2">公司</span>
        <span class="t3">15-25万/年</span>
        <span class="t4">地点</span>
        <span class="t5">经验/学历</span>
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


_JOB51_CARD_SELECTORS = (
    "div.el",
    "div.jjoblist",
    "div[class*='jjob']",
    "div[onmouseover*='changeBg']",
    "div.jjobs",
)


class Job51Channel(BaseCrawlerChannel):
    """前程无忧 (51job) jobs 搜索 — 公开 HTML."""

    channel: ClassVar[str] = "job51"
    api_endpoint: ClassVar[str] = (
        "https://search.51job.com/list/000000,000000,0000,00,9,99,{query},2,{page}.html"
    )

    async def _fetch(self, query: str, max_results: int) -> str:
        await self._rate_limiter.acquire()
        client = await self._ensure_client()
        url = self._build_url(query=query, page=1)
        if not self._robots_ok(url, client):
            return ""
        try:
            headers = self._headers()
            headers["Referer"] = "https://www.51job.com/"
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
        """静态解析 51job 职位列表 HTML → List[JobPosting]."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.debug("51job BS4 init failed: %s", e)
            return []
        out: List[JobPosting] = []
        cards: List[Tag] = []
        for sel in _JOB51_CARD_SELECTORS:
            try:
                found = soup.select(sel)
            except Exception:
                continue
            if found:
                cards = found
                break
        for idx, card in enumerate(cards):
            try:
                posting = Job51Channel._parse_card(card, idx)
                if posting and posting.title:
                    out.append(posting)
            except Exception as e:
                logger.debug("51job card %d skip: %s", idx, e)
                continue
        return out

    @staticmethod
    def _parse_card(card: Tag, idx: int) -> Optional[JobPosting]:
        # 51job 用 .t1 ~ .t5 表示字段
        # 标题 (.t1 > a)
        t1 = card.select_one("p.t1, .t1")
        title = ""
        url = ""
        if t1:
            a = t1.find("a")
            if a:
                title = a.get_text(strip=True)
                if a.has_attr("href"):
                    url = a["href"]
        if not title:
            # 兜底
            title_el = card.select_one("a[href*='jobs.51job.com']")
            if title_el:
                title = title_el.get_text(strip=True)
                if title_el.has_attr("href"):
                    url = title_el["href"]
        if not title:
            return None
        if not url:
            url = f"https://jobs.51job.com/all/co{idx}.html"
        # 公司 .t2
        t2 = card.select_one(".t2, span.t2, a.t2")
        company = t2.get_text(strip=True) if t2 else ""
        # 薪资 .t3
        t3 = card.select_one(".t3, span.t3")
        salary = t3.get_text(strip=True) if t3 else ""
        # 地点 .t4
        t4 = card.select_one(".t4, span.t4")
        location = t4.get_text(strip=True) if t4 else ""
        # 经验/学历 .t5
        t5 = card.select_one(".t5, span.t5")
        experience = t5.get_text(strip=True) if t5 else ""
        # 公司性质/规模 .t6 (optional)
        t6 = card.select_one(".t6, span.t6")
        company_type = t6.get_text(strip=True) if t6 else ""
        # 福利标签 (.t7 span 或 .tags span)
        tag_els = card.select(".t7 span, .tags span, [class*='tag']")
        tags: List[str] = []
        for t in tag_els:
            txt = t.get_text(strip=True)
            if txt and len(txt) <= 30:
                tags.append(txt)
        # id: 从 URL 提取 co 后面的数字
        m = re.search(r"co(\d+)\.html", url) or re.search(r"/(\d+)\.html", url)
        posting_id = m.group(1) if m else f"job51_{idx}"
        return JobPosting(
            id=posting_id,
            title=title,
            company=company,
            salary=salary,
            location=location,
            url=url,
            source="job51",
            posted_at="",
            description="",
            tags=tags,
            extra={
                "experience": experience,
                "company_type": company_type,
                "channel": "job51",
            },
        )

    def _build_url(self, query: str, page: int = 1) -> str:
        from urllib.parse import quote_plus
        return self.api_endpoint.format(query=quote_plus(query), page=page)


__all__ = ["Job51Channel"]
