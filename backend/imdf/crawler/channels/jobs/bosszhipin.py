"""BOSS直聘 (www.zhipin.com) jobs 渠道适配器 (P20-B2)

搜索 URL (公开, mobile m 站反爬轻):
    https://www.zhipin.com/web/geek/job?query={query}&page={page}

公开搜索 — 无需登录, 但 BOSS 反爬严格 (cookie + 滑块).
best-effort: 失败返回 [].

HTML 结构 (简化):
    <li class="job-card-wrapper">  <-- 职位卡片
        <div class="job-title">职位名</div>
        <div class="company-name">公司</div>
        <span class="salary">15-25K·15薪</span>
        <div class="job-area">地点</div>
        <div class="job-tag">...</div>
    </li>

Pydantic v2 输出: List[JobPosting]
"""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar, List, Optional

from bs4 import BeautifulSoup, Tag

from ._base import BaseCrawlerChannel, JobPosting

logger = logging.getLogger(__name__)


_BOSS_CARD_SELECTORS = (
    "li.job-card-wrapper",
    "div.job-card-wrapper",
    "li[data-jobid]",
    "div.job-primary",
    "div[class*='job-card']",
)


class BossZhipinChannel(BaseCrawlerChannel):
    """BOSS直聘 jobs 搜索 — 公开 HTML, 反爬较严."""

    channel: ClassVar[str] = "bosszhipin"
    api_endpoint: ClassVar[str] = (
        "https://www.zhipin.com/web/geek/job?query={query}&page={page}"
    )

    async def _fetch(self, query: str, max_results: int) -> str:
        """重写 — BOSS 走 web 端 cookie 预热."""
        await self._rate_limiter.acquire()
        client = await self._ensure_client()
        url = self._build_url(query=query, page=1)
        if not self._robots_ok(url, client):
            return ""
        try:
            # BOSS 公开 web 需要 Referer 头才能拿到完整内容
            headers = self._headers()
            headers["Referer"] = "https://www.zhipin.com/web/geek/job"
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
        """静态解析 BOSS 职位列表 HTML → List[JobPosting]."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.debug("BOSS BS4 init failed: %s", e)
            return []
        out: List[JobPosting] = []
        cards: List[Tag] = []
        for sel in _BOSS_CARD_SELECTORS:
            try:
                found = soup.select(sel)
            except Exception:
                continue
            if found:
                cards = found
                break
        for idx, card in enumerate(cards):
            try:
                posting = BossZhipinChannel._parse_card(card, idx)
                if posting and posting.title:
                    out.append(posting)
            except Exception as e:
                logger.debug("BOSS card %d skip: %s", idx, e)
                continue
        return out

    @staticmethod
    def _parse_card(card: Tag, idx: int) -> Optional[JobPosting]:
        # 标题 + URL
        title_el = (
            card.select_one(".job-title")
            or card.select_one(".job-name")
            or card.select_one("a.job-title")
            or card.select_one("[class*='job-title']")
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None
        url = ""
        anchor = card.select_one("a[href*='/job_detail/']") or (
            title_el if title_el and title_el.name == "a" else None
        )
        if anchor and anchor.has_attr("href"):
            url = anchor["href"]
        if not url:
            url = f"https://www.zhipin.com/job_detail/placeholder_{idx}.html"
        elif url.startswith("/"):
            url = "https://www.zhipin.com" + url
        # 公司
        company_el = (
            card.select_one(".company-name")
            or card.select_one(".name")
            or card.select_one("[class*='company-name']")
        )
        company = company_el.get_text(strip=True) if company_el else ""
        # 薪资
        salary_el = (
            card.select_one(".salary")
            or card.select_one("[class*='salary']")
            or card.select_one(".red")
        )
        salary = salary_el.get_text(strip=True) if salary_el else ""
        # 地点
        location_el = (
            card.select_one(".job-area")
            or card.select_one(".area")
            or card.select_one("[class*='job-area']")
        )
        location = location_el.get_text(strip=True) if location_el else ""
        # 标签 (经验/学历/技能)
        tag_els = card.select(
            ".job-tag span, .tag-list span, [class*='job-tag'] span, "
            ".job-info span"
        )
        tags: List[str] = []
        for t in tag_els:
            txt = t.get_text(strip=True)
            if txt and len(txt) <= 20:
                tags.append(txt)
        # jobId
        jobid = card.get("data-jobid", "") or card.get("data-id", "")
        if not jobid:
            m = re.search(r"/job_detail/([^/?]+)", url)
            jobid = m.group(1) if m else f"boss_{idx}"
        return JobPosting(
            id=str(jobid),
            title=title,
            company=company,
            salary=salary,
            location=location,
            url=url,
            source="bosszhipin",
            posted_at="",
            description="",
            tags=tags,
            extra={
                "channel": "bosszhipin",
            },
        )

    def _build_url(self, query: str, page: int = 1) -> str:
        from urllib.parse import quote_plus
        return self.api_endpoint.format(query=quote_plus(query), page=page)


__all__ = ["BossZhipinChannel"]
