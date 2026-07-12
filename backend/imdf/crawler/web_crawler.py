"""WebCrawler — Playwright 驱动的网页爬虫 (P19-B3 §3)

特性:
- 智能等待 (wait_for_selector / wait_for_load_state)
- 滚动加载 (auto-scroll)
- 点击翻页 (auto-click next)
- 提取: html / text / images / links / metadata
- 异步并发 (semaphore)

Playwright 缺失时的降级:
- 如果环境无 playwright, 走 "passthrough" 模式: 仅做 requests HTML fetch + BeautifulSoup 解析
- 测试用 fake_playwright 注入
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import BaseCrawler, CrawlResult, CrawlStatus, USER_AGENT_POOL
from .config import CrawlerConfig

logger = logging.getLogger(__name__)


# Playwright optional import — 不强制依赖
try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext  # type: ignore
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    Browser = None  # type: ignore
    BrowserContext = None  # type: ignore


@dataclass
class WebPage:
    """单页解析产物"""
    url: str
    title: str = ""
    html: str = ""
    text: str = ""
    images: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status_code: int = 200
    next_page_url: Optional[str] = None

    def to_item(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text[:500],
            "images": self.images[:20],
            "links": self.links[:20],
            "metadata": self.metadata,
            "status_code": self.status_code,
        }


class WebCrawler(BaseCrawler):
    """Playwright 驱动的网页爬虫

    使用:
        cfg = CrawlerConfig(channel="web", max_concurrent=4)
        cw = WebCrawler(cfg)
        result = cw.crawl({"url": "https://example.com", "selectors": {...}})
        for item in result.items:
            print(item["title"])
    """

    channel = "web"

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 playwright_runner: Optional[Callable] = None):
        super().__init__(config=config)
        # playwright_runner: 注入的 playwright mock — 用于测试
        self._pw_runner = playwright_runner
        self._use_real_playwright = _PLAYWRIGHT_AVAILABLE and (playwright_runner is None)

    # ============== _prepare ==============

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """target 接受:
        - str: 当作 url, 默认 selector = body
        - dict: {url, selectors, wait_selector, scroll, click_next, max_pages}
        """
        if isinstance(target, str):
            target = {"url": target}
        if not isinstance(target, dict):
            return None
        url = target.get("url") or target.get("href")
        if not url:
            return None
        return {
            "url": url,
            "headers": target.get("headers", {}),
            "selectors": target.get("selectors", {}),
            "wait_selector": target.get("wait_selector"),
            "wait_timeout_ms": int(target.get("wait_timeout_ms", 5000)),
            "scroll": bool(target.get("scroll", False)),
            "scroll_rounds": int(target.get("scroll_rounds", 3)),
            "click_next": bool(target.get("click_next", False)),
            "max_pages": int(target.get("max_pages", 1)),
            "extract": target.get("extract", ["html", "text", "images", "links"]),
            "proxy": target.get("proxy"),
        }

    # ============== _do_fetch ==============

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        """实际 fetch — Playwright (优先) or urllib fallback"""
        if self._use_real_playwright:
            return self._do_fetch_playwright(url, headers, prep)
        elif self._pw_runner:
            return self._pw_runner(url, headers, prep)
        else:
            # Passthrough — urllib + 默认 headers
            return self._do_fetch_urllib(url, headers)

    def _do_fetch_urllib(self, url: str, headers: Dict[str, str]) -> Tuple[Any, int, Optional[str]]:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                content = resp.read()
                # 尽量 UTF-8 解码
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    text = content.decode("utf-8", errors="replace")
                # Return as string for easier parsing
                return text.encode("utf-8"), resp.status, None
        except Exception as e:
            return b"", 0, str(e)

    def _do_fetch_playwright(self, url: str, headers: Dict[str, str],
                              prep: Dict[str, Any]) -> Tuple[Any, int, Optional[str]]:
        """Playwright 同步 fetch — 包含 wait / scroll / click_next"""
        pages_data: List[Dict[str, Any]] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.config.get_user_agent(),
                    ignore_https_errors=True,
                )
                page = context.new_page()
                # 应用自定义 headers
                if headers:
                    page.set_extra_http_headers(headers)

                page.goto(url, timeout=int(self.config.timeout_seconds * 1000),
                          wait_until="domcontentloaded")

                # 智能等待
                if prep.get("wait_selector"):
                    try:
                        page.wait_for_selector(prep["wait_selector"],
                                               timeout=prep.get("wait_timeout_ms", 5000))
                    except Exception as e:
                        logger.debug("wait_selector timeout: %s", e)

                # 滚动加载
                if prep.get("scroll"):
                    rounds = prep.get("scroll_rounds", 3)
                    for _ in range(rounds):
                        page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                        page.wait_for_timeout(500)

                pages_data.append(self._extract_page(page, prep))

                # 点击翻页
                page_num = 1
                while prep.get("click_next") and page_num < prep.get("max_pages", 5):
                    next_btn = prep.get("next_selector", "a.next, button.next, [rel=next]")
                    try:
                        page.click(next_btn, timeout=2000)
                        page.wait_for_load_state("networkidle", timeout=5000)
                        pages_data.append(self._extract_page(page, prep))
                        page_num += 1
                    except Exception:
                        break

                browser.close()

            # 合并多页
            combined = "\n<!--PAGE_BREAK-->\n".join(p.get("html", "") for p in pages_data)
            return combined.encode("utf-8"), 200, None
        except Exception as e:
            logger.warning("playwright fetch error: %s", e)
            return b"", 0, str(e)

    def _extract_page(self, page, prep: Dict[str, Any]) -> Dict[str, Any]:
        """从 playwright Page 提取数据"""
        extract = prep.get("extract", ["html", "text", "images", "links"])
        data: Dict[str, Any] = {}
        if "html" in extract:
            data["html"] = page.content()
        if "text" in extract:
            data["text"] = page.evaluate("() => document.body.innerText")
        if "title" in extract:
            data["title"] = page.title()
        if "images" in extract:
            try:
                data["images"] = page.evaluate("""
                    () => Array.from(document.images).map(img => img.src).filter(Boolean)
                """)
            except Exception:
                data["images"] = []
        if "links" in extract:
            try:
                data["links"] = page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(Boolean)
                """)
            except Exception:
                data["links"] = []
        if "metadata" in extract:
            try:
                data["metadata"] = page.evaluate("""
                    () => ({
                        description: document.querySelector('meta[name=description]')?.content || '',
                        keywords: document.querySelector('meta[name=keywords]')?.content || '',
                        og_image: document.querySelector('meta[property="og:image"]')?.content || '',
                        og_title: document.querySelector('meta[property="og:title"]')?.content || '',
                    })
                """)
            except Exception:
                data["metadata"] = {}
        return data

    # ============== _parse ==============

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """解析 raw (HTML string) 为标准 items + metadata"""
        html = ""
        if isinstance(raw, bytes):
            try:
                html = raw.decode("utf-8")
            except UnicodeDecodeError:
                html = raw.decode("utf-8", errors="replace")
        elif isinstance(raw, str):
            html = raw
        if not html:
            return [], {"html_length": 0}

        items: List[Dict[str, Any]] = []
        metadata: Dict[str, Any] = {}

        # 如果多页分割
        if "<!--PAGE_BREAK-->" in html:
            chunks = html.split("<!--PAGE_BREAK-->")
        else:
            chunks = [html]

        for idx, chunk in enumerate(chunks):
            item = self._parse_html(chunk, prep, idx)
            if item:
                items.append(item)

        # 计算全局 metadata
        metadata["html_length"] = len(html)
        metadata["pages"] = len(chunks)
        metadata["items_count"] = len(items)
        return items, metadata

    def _parse_html(self, html: str, prep: Dict[str, Any], idx: int) -> Dict[str, Any]:
        """解析单个 HTML chunk — 使用 BeautifulSoup"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            selectors = prep.get("selectors") or {}

            title = ""
            if soup.title:
                title = soup.title.string or ""
            elif soup.find("meta", attrs={"property": "og:title"}):
                title = soup.find("meta", attrs={"property": "og:title"}).get("content", "")

            text = soup.get_text(separator=" ", strip=True)[:2000]
            images = [img.get("src", "") for img in soup.find_all("img") if img.get("src")]
            links = [a.get("href", "") for a in soup.find_all("a", href=True) if a.get("href")]

            meta = {}
            for m in soup.find_all("meta"):
                name = m.get("name") or m.get("property")
                content = m.get("content")
                if name and content:
                    meta[name] = content[:200]

            # 自定义 selector 提取
            custom: Dict[str, List[str]] = {}
            for key, sel in selectors.items():
                found = []
                try:
                    for el in soup.select(sel):
                        txt = el.get_text(strip=True) or el.get("href") or el.get("src")
                        if txt:
                            found.append(txt[:500])
                except Exception:
                    pass
                custom[key] = found[:50]

            return {
                "url": prep.get("url", ""),
                "title": title,
                "text": text,
                "images": images[:50],
                "links": links[:50],
                "metadata": meta,
                "selectors": custom,
                "page_index": idx,
            }
        except Exception as e:
            logger.debug("HTML parse error: %s", e)
            return {"url": prep.get("url", ""), "title": "", "text": "", "error": str(e)}


# 异步批量入口 — 适合 CrawlerEngine
async def crawl_batch_async(web_crawler: WebCrawler,
                              targets: List[Dict[str, Any]]) -> List[CrawlResult]:
    """异步并发 — 用线程池包装同步 crawl."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=web_crawler.config.max_concurrent)
    try:
        tasks = [loop.run_in_executor(executor, web_crawler.crawl, t) for t in targets]
        return await asyncio.gather(*tasks)
    finally:
        executor.shutdown(wait=False)