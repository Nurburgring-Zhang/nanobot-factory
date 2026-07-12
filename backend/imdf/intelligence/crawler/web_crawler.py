"""智影 V4 — Web 爬虫: Playwright (JS 渲染) + httpx (静态) + BeautifulSoup"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class WebCrawler(BaseCrawler):
    """通用 Web 爬虫 — 支持静态 (httpx+BS4) 和动态 (Playwright)"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._client: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._playwright_ctx: Optional[Any] = None

    async def _ensure_httpx(self):
        if self._client is None:
            if httpx is None:
                raise RuntimeError("httpx 未安装: pip install httpx")
            ua = random.choice(self.config.user_agent_pool)
            proxy = random.choice(self.config.proxy_pool) if self.config.proxy_pool else None
            limits = httpx.Limits(
                max_keepalive_connections=self.config.parallel_workers,
                max_connections=self.config.parallel_workers * 2,
            )
            self._client = httpx.AsyncClient(
                http2=True,
                timeout=30.0,
                headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"},
                proxy=proxy,
                limits=limits,
                follow_redirects=True,
            )
        return self._client

    async def _ensure_browser(self):
        if self._browser is None:
            if async_playwright is None:
                raise RuntimeError("playwright 未安装: pip install playwright + playwright install")
            self._playwright_ctx = await async_playwright().start()
            self._browser = await self._playwright_ctx.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
        return self._browser

    async def fetch(self, url: str) -> RawDocument:
        """抓取单个 URL — 智能选择 httpx 或 Playwright"""
        start = time.time()
        # 动态内容 (config.wait_selectors 或 JS 站点)
        use_browser = bool(self.config.wait_selectors) or self.config.scroll_to_bottom or self.config.click_selectors
        if use_browser:
            return await self._fetch_with_browser(url, start)
        return await self._fetch_with_httpx(url, start)

    async def _fetch_with_httpx(self, url: str, start: float) -> RawDocument:
        client = await self._ensure_httpx()
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
        doc = RawDocument(
            url=url,
            type="html",
            html=html,
            http_status=resp.status_code,
            crawl_duration_ms=(time.time() - start) * 1000,
        )
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "lxml")
            # title
            if soup.title:
                doc.title = (soup.title.string or "").strip()[:500]
            # 提取正文文本 (简单策略: 找最大 text 块)
            doc.text = self._extract_text(soup)
            # 提取图片
            if self.config.extract_images:
                doc.images = self._extract_images(soup, url)
            # 提取链接
            if self.config.extract_links:
                doc.links = self._extract_links(soup, url)
        else:
            # 退化: 简单正则
            import re
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            doc.title = (title_match.group(1).strip() if title_match else "")[:500]
        return doc

    async def _fetch_with_browser(self, url: str, start: float) -> RawDocument:
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=random.choice(self.config.user_agent_pool),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等待选择器
            for sel in self.config.wait_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                except Exception as e:
                    logger.debug(f"wait_selector {sel} timeout: {e}")
            # 滚动到底部
            if self.config.scroll_to_bottom:
                await self._auto_scroll(page)
            # 点击
            for sel in self.config.click_selectors:
                try:
                    await page.click(sel, timeout=3000)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
            html = await page.content()
            title = await page.title()
            # 提取正文 (页面 evaluate)
            text = await page.evaluate("() => document.body.innerText")
            images = await page.evaluate(
                "() => Array.from(document.querySelectorAll('img')).map(i => i.src).filter(Boolean)"
            )
            links = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(Boolean)"
            )
            doc = RawDocument(
                url=url,
                type="html",
                title=title,
                html=html,
                text=text,
                images=images,
                links=links,
                crawl_duration_ms=(time.time() - start) * 1000,
            )
            return doc
        finally:
            await context.close()

    async def _auto_scroll(self, page):
        """自动滚动到底部 (SPA 触发懒加载)"""
        last_height = await page.evaluate("() => document.body.scrollHeight")
        for _ in range(20):  # 最多 20 次
            await page.evaluate("() => window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(0.3)
            new_height = await page.evaluate("() => document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def _extract_text(self, soup: Any) -> str:
        """从 BeautifulSoup 提取主要文本 (启发式: 找最大 <article>/<main>/<div>)"""
        # 优先: article > main > body
        for tag in ["article", "main"]:
            el = soup.find(tag)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) >= self.config.min_content_length:
                    return text[:50000]  # 限制 50K
        # 退化: body
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)[:50000]
        return soup.get_text(separator="\n", strip=True)[:50000]

    def _extract_images(self, soup: Any, base_url: str) -> List[str]:
        """提取所有图片 URL (含 srcset / data-src)"""
        seen: set = set()
        result: List[str] = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if not src and img.get("srcset"):
                # srcset: "url1 1x, url2 2x" → 取第一
                src = img["srcset"].split(",")[0].strip().split()[0]
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(base_url, src)
            elif not src.startswith(("http://", "https://", "data:")):
                src = urljoin(base_url, src)
            if src not in seen and not src.startswith("data:"):
                seen.add(src)
                result.append(src)
        return result[:500]

    def _extract_links(self, soup: Any, base_url: str) -> List[str]:
        """提取所有链接 (绝对 URL)"""
        seen: set = set()
        result: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("javascript:", "mailto:", "#")):
                continue
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = urljoin(base_url, href)
            elif not href.startswith(("http://", "https://")):
                href = urljoin(base_url, href)
            if href not in seen:
                seen.add(href)
                result.append(href)
        return result[:1000]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright_ctx:
            await self._playwright_ctx.stop()
            self._playwright_ctx = None
