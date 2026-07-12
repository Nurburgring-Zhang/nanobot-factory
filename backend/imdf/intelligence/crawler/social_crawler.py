"""智影 V4 — 社交媒体爬虫: Twitter/Reddit/HackerNews/Mastodon/DevTo/Lemmy 公开 API"""
from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class SocialCrawler(BaseCrawler):
    """社交媒体公开 API 爬虫 — 不需要认证或仅需要可选 API key"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    async def _ensure_client(self):
        if self._client is None:
            if httpx is None:
                raise RuntimeError("httpx 未安装: pip install httpx")
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "IMDF-Crawler/4.0 (+social)"},
            )
        return self._client

    async def fetch(self, url: str) -> RawDocument:
        """根据 url 域名自动路由到具体平台处理器"""
        start = time.time()
        # 自动识别平台
        if "reddit.com" in url or "redd.it" in url:
            return await self._fetch_reddit(url, start)
        if "news.ycombinator.com" in url or "hacker-news.firebaseio.com" in url:
            return await self._fetch_hackernews(url, start)
        if "mastodon" in url and "/api/" in url:
            return await self._fetch_mastodon(url, start)
        if "dev.to" in url:
            return await self._fetch_devto(url, start)
        if "twitter.com" in url or "x.com" in url:
            return await self._fetch_twitter(url, start)
        if "lemmy" in url and "/api/" in url:
            return await self._fetch_lemmy(url, start)
        # 通用: 当作 web 处理
        from .web_crawler import WebCrawler
        wc = WebCrawler(self.config)
        return await wc.fetch(url)

    async def _fetch_reddit(self, url: str, start: float) -> RawDocument:
        """Reddit JSON API (公开,不需要 OAuth)"""
        client = await self._ensure_client()
        # 转换 .json 后缀
        if not url.endswith(".json"):
            if "?" in url:
                url = url.replace("?", ".json?", 1)
            else:
                url = url.rstrip("/") + ".json"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        # 提取 posts
        posts: List[Dict[str, Any]] = []
        items = _extract_reddit_listing(data)
        for item in items[: self.config.max_pages]:
            post = item.get("data", {})
            posts.append(
                {
                    "id": post.get("id"),
                    "title": post.get("title"),
                    "selftext": post.get("selftext"),
                    "url": post.get("url"),
                    "score": post.get("score"),
                    "subreddit": post.get("subreddit"),
                    "author": post.get("author"),
                    "created_utc": post.get("created_utc"),
                    "num_comments": post.get("num_comments"),
                }
            )
        text = "\n\n".join(f"[{p['subreddit']}] {p['title']}\n{p['selftext'][:500]}" for p in posts[:10])
        return RawDocument(
            url=url,
            type="json",
            title=f"Reddit: {len(posts)} posts",
            text=text,
            json={"posts": posts, "raw": data},
            source_metadata={"platform": "reddit"},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_hackernews(self, url: str, start: float) -> RawDocument:
        """HackerNews Firebase API (完全公开)"""
        client = await self._ensure_client()
        # 解析 item id
        if "item?id=" in url:
            import re
            m = re.search(r"id=(\d+)", url)
            if m:
                url = f"https://hacker-news.firebaseio.com/v0/item/{m.group(1)}.json"
        elif url.endswith(".json"):
            pass  # 直接用
        else:
            # 当作 top stories
            url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        # 如果是 story id 列表,批量获取
        if isinstance(data, list):
            items: List[Dict[str, Any]] = []
            for sid in data[: min(self.config.max_pages, 100)]:
                ir = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                if ir.status_code == 200:
                    items.append(ir.json() or {})
            text = "\n\n".join(
                f"[{i.get('score', 0)}↑] {i.get('title', '')}\n{i.get('text', '')[:300] or i.get('url', '')}"
                for i in items[:10]
            )
            return RawDocument(
                url=url,
                type="json",
                title=f"HN: {len(items)} stories",
                text=text,
                json={"items": items},
                source_metadata={"platform": "hackernews"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        # 单个 item
        text = (data.get("text") or "") + "\n\n" + (data.get("url") or "")
        return RawDocument(
            url=url,
            type="json",
            title=data.get("title", ""),
            text=text,
            json=data,
            source_metadata={"platform": "hackernews", "type": data.get("type")},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_mastodon(self, url: str, start: float) -> RawDocument:
        """Mastodon 公开 API"""
        client = await self._ensure_client()
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            text = "\n\n".join(
                f"@{s.get('account', {}).get('username', '?')}: {s.get('content', '')[:300]}" for s in data[:10]
            )
            return RawDocument(
                url=url,
                type="json",
                title=f"Mastodon: {len(data)} toots",
                text=text,
                json={"statuses": data},
                source_metadata={"platform": "mastodon"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        return RawDocument(
            url=url,
            type="json",
            title="Mastodon status",
            text=data.get("content", ""),
            json=data,
            source_metadata={"platform": "mastodon"},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_devto(self, url: str, start: float) -> RawDocument:
        """Dev.to 公开 API"""
        client = await self._ensure_client()
        # 转 API
        if "/api/articles" not in url:
            if "/@" in url:
                username = url.split("/@")[-1].split("/")[0].split("?")[0]
                url = f"https://dev.to/api/articles?username={username}"
            else:
                url = "https://dev.to/api/articles"
        resp = await client.get(url)
        resp.raise_for_status()
        articles = resp.json()
        if not isinstance(articles, list):
            articles = [articles]
        text = "\n\n".join(
            f"[{a.get('readable_publish_date', '')}] {a.get('title', '')}\n{a.get('description', '')[:300]}"
            for a in articles[:10]
        )
        return RawDocument(
            url=url,
            type="json",
            title=f"Dev.to: {len(articles)} articles",
            text=text,
            json={"articles": articles},
            source_metadata={"platform": "devto"},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_twitter(self, url: str, start: float) -> RawDocument:
        """Twitter 公开 Nitter 实例镜像 (合规优先,失败时返回占位)"""
        # Twitter 强反爬,推荐用 nitter.net 镜像或 syndication API
        client = await self._ensure_client()
        # 提取 username
        import re
        m = re.search(r"/(\w+)/status/(\d+)", url)
        if m:
            username, tweet_id = m.group(1), m.group(2)
            syndication_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}"
        else:
            m2 = re.search(r"/(\w+)$", url.rstrip("/"))
            if m2:
                username = m2.group(1)
                syndication_url = f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?user_names={username}"
            else:
                syndication_url = url
        try:
            resp = await client.get(syndication_url)
            resp.raise_for_status()
            data = resp.json()
            return RawDocument(
                url=url,
                type="json",
                title=f"Twitter: {username}",
                text=json.dumps(data, ensure_ascii=False)[:5000],
                json=data,
                source_metadata={"platform": "twitter", "via": "syndication"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.warning(f"Twitter syndication failed: {e}")
            return RawDocument(
                url=url,
                type="json",
                title="Twitter (syndication failed)",
                text="",
                source_metadata={"platform": "twitter", "error": str(e)},
                http_status=429,
                crawl_duration_ms=(time.time() - start) * 1000,
            )

    async def _fetch_lemmy(self, url: str, start: float) -> RawDocument:
        """Lemmy 公开 API (ActivityPub)"""
        client = await self._ensure_client()
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("posts", []) if isinstance(data, dict) else data
        text = "\n\n".join(
            f"[{p.get('community', {}).get('title', '?')}] {p.get('post', {}).get('name', '')}"
            for p in posts[:10]
        )
        return RawDocument(
            url=url,
            type="json",
            title=f"Lemmy: {len(posts)} posts",
            text=text,
            json={"posts": posts, "raw": data},
            source_metadata={"platform": "lemmy"},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


def _extract_reddit_listing(data: Any) -> List[Dict[str, Any]]:
    """从 Reddit listing JSON 提取 children items"""
    items: List[Dict[str, Any]] = []
    if isinstance(data, list):
        for x in data:
            items.extend(_extract_reddit_listing(x))
    elif isinstance(data, dict):
        if data.get("kind") == "t3" and "data" in data:
            items.append(data)
        for v in data.values():
            if isinstance(v, (list, dict)):
                items.extend(_extract_reddit_listing(v))
    return items
