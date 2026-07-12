"""Lagou (拉勾网) jobs 渠道适配器 (P20-B2)

搜索 URL (公开, 走 jobs 列表):
    https://www.lagou.com/wn/jobs?kd={query}&pn={page}

公开搜索 — 无需 API key, 但需真实 UA.
HTML 结构 (简化, 真实页面可能动态渲染):
    <div class="item__10RTO">  <-- 职位卡片
        <a class="position_link" href="..."> 职位名 </a>
        <div class="company_name__2-x_P">公司</div>
        <span class="money__3Lkgq">15-25K</span>
        <div class="p_top__1SC7r"> ... </div>
    </div>

注: 拉勾有反爬 (cookie + 滑块), 真实环境需要先 GET / 拿 cookie.
    这里采用 best-effort 公开端点, 网络失败时优雅返回 [].

Pydantic v2 输出: List[JobPosting]
"""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar, Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from ._base import BaseCrawlerChannel, CrawlResult, JobPosting

logger = logging.getLogger(__name__)


# 已知职位卡片的多种 class 变体 — 拉勾改版频繁
_LAGOU_CARD_SELECTORS = (
    "div.item__10RTO",
    "div.list_item",
    "li.con_list_item",
    "div.position-item",
    "div[class*='item__']",
)


class LagouChannel(BaseCrawlerChannel):
    """拉勾网 jobs 搜索 — 公开 HTML."""

    channel: ClassVar[str] = "lagou"
    api_endpoint: ClassVar[str] = "https://www.lagou.com/wn/jobs?kd={query}&pn={page}"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._session_cookie_set = False

    async def _fetch(self, query: str, max_results: int) -> str:
        """重写 — 拉勾需要先访问主页拿 cookie."""
        await self._rate_limiter.acquire()
        client = await self._ensure_client()
        url = self._build_url(query=query, page=1)
        if not self._robots_ok(url, client):
            return ""
        try:
            # 拉勾 cookie 预热: GET 主页拿 set-cookie
            if not self._session_cookie_set:
                try:
                    warmup = await client.get(
                        "https://www.lagou.com/",
                        headers=self._headers(),
                    )
                    if warmup.status_code == 200:
                        self._session_cookie_set = True
                except Exception:
                    pass  # 预热失败不阻塞主请求

            resp = await client.get(url, headers=self._headers())
        except Exception as e:
            logger.warning("%s network error: %s", self.channel, e)
            return ""
        if resp.status_code != 200:
            logger.warning("%s status %d", self.channel, resp.status_code)
            return ""
        return resp.text

    @staticmethod
    def parse(html: str) -> List[JobPosting]:
        """静态解析拉勾职位列表 HTML → List[JobPosting]."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.debug("Lagou BS4 init failed: %s", e)
            return []
        out: List[JobPosting] = []
        # 1) 尝试多种卡片选择器
        cards: List[Tag] = []
        for sel in _LAGOU_CARD_SELECTORS:
            try:
                found = soup.select(sel)
            except Exception:
                continue
            if found and len(found) >= 1:
                cards = found
                break
        if not cards:
            # 兜底: 找所有 a.position_link
            anchors = soup.select("a.position_link, a[href*='lagou.com/jobs/']")
            cards = [a.parent.parent if a.parent else a for a in anchors if isinstance(a, Tag)]
            cards = [c for c in cards if isinstance(c, Tag)]

        for idx, card in enumerate(cards):
            try:
                posting = LagouChannel._parse_card(card, idx)
                if posting and posting.title:
                    out.append(posting)
            except Exception as e:
                logger.debug("Lagou card %d skip: %s", idx, e)
                continue
        return out

    @staticmethod
    def _parse_card(card: Tag, idx: int) -> Optional[JobPosting]:
        """单卡片解析 — 字段从多个选择器中尝试."""
        # 标题
        title_el = (
            card.select_one("a.position_link")
            or card.select_one(".p-top__1F7CL a")
            or card.select_one("h3 a")
            or card.select_one("a[class*='position']")
            or card.select_one(".title")
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None
        # URL
        url = ""
        if title_el and title_el.has_attr("href"):
            url = title_el["href"]
        else:
            anchor = card.select_one("a[href*='lagou.com/jobs/']")
            if anchor and anchor.has_attr("href"):
                url = anchor["href"]
        if not url:
            url = f"https://www.lagou.com/jobs/{idx}.html"
        elif url.startswith("/"):
            url = "https://www.lagou.com" + url
        # 公司
        company_el = (
            card.select_one(".company_name__2-x_P")
            or card.select_one(".company-name")
            or card.select_one("[class*='company_name']")
            or card.select_one(".company a")
        )
        company = company_el.get_text(strip=True) if company_el else ""
        # 薪资
        money_el = (
            card.select_one(".money__3Lkgq")
            or card.select_one(".salary")
            or card.select_one("[class*='money']")
            or card.select_one("[class*='salary']")
        )
        salary = money_el.get_text(strip=True) if money_el else ""
        # 地点 / 经验 / 学历 (合并在 .p_top__1SC7r / .li_b_l 之类)
        info = card.select_one(".p_top__1SC7r, .li_b_l, .position-info, [class*='p_top']")
        location = ""
        experience = ""
        education = ""
        if info:
            spans = info.find_all("span")
            texts = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
            if texts:
                location = texts[0] if len(texts) >= 1 else ""
                experience = texts[1] if len(texts) >= 2 else ""
                education = texts[2] if len(texts) >= 3 else ""
        # 福利/标签
        tags_el = card.select(".li_b_r span, .labels span, [class*='tag']")
        tags: List[str] = []
        for t in tags_el:
            txt = t.get_text(strip=True)
            if txt and len(txt) <= 30:
                tags.append(txt)
        # id
        # 从 URL 提取数字 id, 如 jobs/123456.html
        m = re.search(r"/jobs/(\d+)", url)
        posting_id = m.group(1) if m else f"lagou_{idx}"
        # 公司行业 / 公司规模 在 .company_size 等
        industry_el = card.select_one(".industry, [class*='industry']")
        industry = industry_el.get_text(strip=True) if industry_el else ""
        return JobPosting(
            id=posting_id,
            title=title,
            company=company,
            salary=salary,
            location=location,
            url=url,
            source="lagou",
            posted_at="",
            description="",
            tags=tags,
            extra={
                "experience": experience,
                "education": education,
                "industry": industry,
                "channel": "lagou",
            },
        )

    def _build_url(self, query: str, page: int = 1) -> str:
        from urllib.parse import quote_plus
        return self.api_endpoint.format(query=quote_plus(query), page=page)


__all__ = ["LagouChannel"]
