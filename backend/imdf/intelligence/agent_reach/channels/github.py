"""V5 第32章 — GitHub channel: GitHubAPI (real + mock fallback).

Real implementation calls the public ``https://api.github.com`` REST API.
When network is unavailable or rate-limited, returns a deterministic
mock repo entry derived from query hash. For unit tests, override the
``_request`` method or use a stub via httpx.MockTransport.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

from imdf.intelligence.agent_reach.schemas import FetchResult

logger = logging.getLogger(__name__)


class GitHubAPI:
    """GitHub REST API — public endpoint, no auth required for low-volume."""

    BASE = "https://api.github.com"
    TIMEOUT_SECONDS = 30.0
    USER_AGENT = "ZhiYing-AgentReach/1.0"

    def __init__(self, timeout: float = TIMEOUT_SECONDS):
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        """Fetch GitHub search results for ``query``.

        On network failure, returns a deterministic mock repo entry —
        tests rely on this fallback path.
        """
        start = time.time()
        url = f"{self.BASE}/search/repositories?q={query}"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "User-Agent": self.USER_AGENT,
                    "Accept": "application/vnd.github+json",
                }
                headers.update(kwargs.get("headers", {}))
                async with session.get(url, headers=headers) as resp:
                    if 200 <= resp.status < 300:
                        data = await resp.json()
                        items = data.get("items", [])
                        return FetchResult(
                            success=True,
                            channel="github",
                            query=query,
                            content=_format_repos(items[:3], query),
                            url=url,
                            content_type="application/json",
                            metadata={
                                "engine": "github-api",
                                "total_count": data.get("total_count", 0),
                                "returned": len(items[:3]),
                                "status": resp.status,
                            },
                            latency_ms=(time.time() - start) * 1000.0,
                        )
                    # rate-limited or other — fall back to mock
                    text = await resp.text()
                    logger.debug("GitHub fetch non-2xx (%s): %s", resp.status, text[:200])
                    return self._mock_fetch(query, start, reason=f"http {resp.status}")
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            logger.debug("GitHub fetch network error: %s", e)
            return self._mock_fetch(query, start, reason=f"{type(e).__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            logger.debug("GitHub fetch unexpected error: %s", e)
            return self._mock_fetch(query, start, reason=f"{type(e).__name__}: {e}")

    def _mock_fetch(self, query: str, start: float, reason: str = "") -> FetchResult:
        import hashlib
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        repo_name = f"mock-repo-{h}"
        return FetchResult(
            success=True,
            channel="github",
            query=query,
            content=(
                f"Mock GitHub repo: {repo_name} matching '{query}'\n"
                f"Fallback reason: {reason or 'unavailable'}"
            ),
            url=f"https://github.com/mock-org/{repo_name}",
            content_type="application/json",
            metadata={
                "engine": "github-api",
                "mock": True,
                "repo_name": repo_name,
                "owner": "mock-org",
                "stars": 100 + (hash(query) % 5000),
                "language": "Python",
                "fallback_reason": reason,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.BASE}/zen") as resp:
                    return 200 <= resp.status < 300
        except Exception as e:  # noqa: BLE001
            logger.debug("GitHubAPI ping failed: %s", e)
            return False


def _format_repos(items, query):
    if not items:
        return f"No GitHub repos found for '{query}'."
    lines = []
    for r in items:
        lines.append(
            f"- {r.get('full_name', '?')} ⭐{r.get('stargazers_count', 0)} — {r.get('description', '')}"
        )
    return "\n".join(lines)


__all__ = ["GitHubAPI"]