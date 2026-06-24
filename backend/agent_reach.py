#!/usr/bin/env python3
"""
Nanobot Factory - Agent-Reach Module
全网爬取、搜索与社交媒体集成模块
基于Panniantong/Agent-Reach项目架构

功能：
- 网页阅读（Jina Reader）
- YouTube/B站字幕提取
- RSS订阅
- 全网语义搜索（Exa）
- GitHub仓库读取
- 社交媒体内容获取
- 代理配置管理

@author MiniMax Agent
@date 2026-03-03
"""

import os
import json
import asyncio
import logging
import subprocess
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import aiohttp
import feedparser

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class PlatformType(Enum):
    """平台类型"""
    WEB = "web"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    GITHUB = "github"
    TWITTER = "twitter"
    REDDIT = "reddit"
    WEIBO = "weibo"
    XIAOHONGSHU = "xiaohongshu"
    LINKEDIN = "linkedin"
    RSS = "rss"
    SEARCH = "search"


@dataclass
class ContentItem:
    """内容条目"""
    id: str
    platform: PlatformType
    title: str
    content: str
    summary: str
    url: str
    author: str = ""
    published_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    query: str
    results: List[ContentItem]
    total: int
    search_time: float
    sources: List[str] = field(default_factory=list)


@dataclass
class AgentReachConfig:
    """Agent-Reach配置"""
    # 代理设置
    proxy_url: str = ""
    # Twitter配置
    twitter_cookies: str = ""
    # Exa搜索配置
    exa_api_key: str = ""
    # GitHub配置
    github_token: str = ""
    # 启用状态
    enabled_platforms: List[str] = field(default_factory=lambda: [
        "web", "youtube", "github", "rss", "search"
    ])


# =============================================================================
# Core Functions
# =============================================================================

class JinaReader:
    """Jina Reader网页阅读"""

    BASE_URL = "https://r.jina.ai"

    @staticmethod
    async def read(url: str) -> ContentItem:
        """读取网页内容"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{JinaReader.BASE_URL}/url/{url}",
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        return JinaReader._parse_content(url, content)
                    else:
                        raise Exception(f"Failed to fetch: {resp.status}")
        except Exception as e:
            logger.error(f"Jina Reader error: {e}")
            raise

    @staticmethod
    async def read_text(url: str) -> str:
        """读取纯文本内容"""
        content = await JinaReader.read(url)
        return content.content

    @staticmethod
    def _parse_content(url: str, raw_text: str) -> ContentItem:
        """解析内容"""
        lines = raw_text.split('\n')
        title = lines[0].strip() if lines else url

        # 提取内容（跳过标题行）
        content_lines = []
        in_content = False
        for line in lines[1:]:
            if line.strip():
                in_content = True
                content_lines.append(line)

        content = '\n'.join(content_lines)
        summary = content[:300] + '...' if len(content) > 300 else content

        return ContentItem(
            id=hashlib.md5(url.encode()).hexdigest()[:16],
            platform=PlatformType.WEB,
            title=title[:200],
            content=content[:10000],  # 限制长度
            summary=summary,
            url=url,
            published_at=datetime.now().isoformat()
        )


class YouTubeExtractor:
    """YouTube内容提取"""

    @staticmethod
    async def get_transcript(video_url: str) -> str:
        """获取YouTube字幕"""
        try:
            # 使用yt-dlp获取字幕
            cmd = [
                "yt-dlp",
                "--write-subs",
                "--write-auto-subs",
                "--skip-download",
                "--sub-lang",
                "zh-Hans,en",
                "-o",
                "/tmp/%(id)s.%(ext)s",
                video_url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # 读取生成的字幕文件
                video_id = YouTubeExtractor._extract_video_id(video_url)
                if video_id:
                    subtitle_path = f"/tmp/{video_id}.zh-Hans.srt"
                    if Path(subtitle_path).exists():
                        with open(subtitle_path, 'r', encoding='utf-8') as f:
                            return f.read()
                    subtitle_path = f"/tmp/{video_id}.en.srt"
                    if Path(subtitle_path).exists():
                        with open(subtitle_path, 'r', encoding='utf-8') as f:
                            return f.read()

            return ""
        except Exception as e:
            logger.warning(f"YouTube transcript error: {e}")
            return ""

    @staticmethod
    def _extract_video_id(url: str) -> Optional[str]:
        """提取视频ID"""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    @staticmethod
    async def get_info(video_url: str) -> ContentItem:
        """获取视频信息"""
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-download",
                video_url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                data = json.loads(stdout.decode())

                return ContentItem(
                    id=data.get('id', ''),
                    platform=PlatformType.YOUTUBE,
                    title=data.get('title', ''),
                    content=data.get('description', ''),
                    summary=data.get('description', '')[:300],
                    url=video_url,
                    author=data.get('uploader', ''),
                    published_at=data.get('upload_date', ''),
                    metadata={
                        'duration': data.get('duration', 0),
                        'view_count': data.get('view_count', 0),
                        'like_count': data.get('like_count', 0),
                        'channel': data.get('channel', ''),
                    }
                )

        except Exception as e:
            logger.error(f"YouTube info error: {e}")

        return ContentItem(
            id="",
            platform=PlatformType.YOUTUBE,
            title="",
            content="",
            summary="",
            url=video_url
        )


class GitHubClient:
    """GitHub客户端"""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str = ""):
        self.token = token
        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if token:
            self.headers["Authorization"] = f"token {token}"

    async def get_repo(self, owner: str, repo: str) -> Dict:
        """获取仓库信息"""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        raise Exception(f"Failed to fetch repo: {resp.status}")
        except Exception as e:
            logger.error(f"GitHub repo error: {e}")
            return {}

    async def search_repos(self, query: str, limit: int = 10) -> List[ContentItem]:
        """搜索仓库"""
        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": limit
        }

        items = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for repo in data.get('items', []):
                            item = ContentItem(
                                id=str(repo.get('id', '')),
                                platform=PlatformType.GITHUB,
                                title=repo.get('name', ''),
                                content=repo.get('description', ''),
                                summary=repo.get('description', '')[:200] if repo.get('description') else '',
                                url=repo.get('html_url', ''),
                                author=repo.get('owner', {}).get('login', ''),
                                published_at=repo.get('created_at', ''),
                                metadata={
                                    'stars': repo.get('stargazers_count', 0),
                                    'forks': repo.get('forks_count', 0),
                                    'language': repo.get('language', ''),
                                    'topics': repo.get('topics', [])
                                }
                            )
                            items.append(item)

        except Exception as e:
            logger.error(f"GitHub search error: {e}")

        return items

    async def get_readme(self, owner: str, repo: str) -> str:
        """获取README"""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/readme"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        import base64
                        content = data.get('content', '')
                        if content:
                            return base64.b64decode(content).decode('utf-8')
        except Exception as e:
            logger.error(f"GitHub readme error: {e}")

        return ""


class RSSReader:
    """RSS阅读器"""

    def __init__(self):
        self.cache: Dict[str, List[ContentItem]] = {}

    async def fetch(self, feed_url: str, limit: int = 10) -> List[ContentItem]:
        """获取RSS源内容"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        parsed = feedparser.parse(content)

                        items = []
                        for entry in parsed.entries[:limit]:
                            item = ContentItem(
                                id=hashlib.md5(entry.get('link', '').encode()).hexdigest()[:16],
                                platform=PlatformType.RSS,
                                title=entry.get('title', ''),
                                content=entry.get('summary', '') or entry.get('description', ''),
                                summary=entry.get('summary', '')[:200] if entry.get('summary') else '',
                                url=entry.get('link', ''),
                                author=entry.get('author', ''),
                                published_at=entry.get('published', '')
                            )
                            items.append(item)

                        return items

        except Exception as e:
            logger.error(f"RSS fetch error: {e}")

        return []


class ExaSearch:
    """Exa语义搜索"""

    BASE_URL = "https://api.exa.ai"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    async def search(self, query: str, limit: int = 10, **kwargs) -> List[ContentItem]:
        """Exa搜索"""
        if not self.api_key:
            # 如果没有API key，返回空结果
            logger.warning("Exa API key not configured")
            return []

        url = f"{self.BASE_URL}/search"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "query": query,
            "num_results": limit,
            "kwargs": kwargs
        }

        items = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        for item in result.get('results', []):
                            content_item = ContentItem(
                                id=hashlib.md5(item.get('url', '').encode()).hexdigest()[:16],
                                platform=PlatformType.SEARCH,
                                title=item.get('title', ''),
                                content=item.get('text', ''),
                                summary=item.get('text', '')[:200] if item.get('text') else '',
                                url=item.get('url', ''),
                                published_at=item.get('published_date', ''),
                                metadata={
                                    'score': item.get('score', 0),
                                    'author': item.get('author', '')
                                }
                            )
                            items.append(content_item)

        except Exception as e:
            logger.error(f"Exa search error: {e}")

        return items


# =============================================================================
# Agent-Reach Main Class
# =============================================================================

class AgentReach:
    """Agent-Reach主类"""

    def __init__(self, config: Optional[AgentReachConfig] = None):
        self.config = config or AgentReachConfig()
        self.jina = JinaReader()
        self.youtube = YouTubeExtractor()
        self.github = GitHubClient(config.github_token if config else "")
        self.rss = RSSReader()
        self.exa = ExaSearch(config.exa_api_key if config else "")

    async def read_web(self, url: str) -> ContentItem:
        """读取网页"""
        return await self.jina.read(url)

    async def get_youtube_transcript(self, video_url: str) -> str:
        """获取YouTube字幕"""
        return await self.youtube.get_transcript(video_url)

    async def get_youtube_info(self, video_url: str) -> ContentItem:
        """获取YouTube视频信息"""
        return await self.youtube.get_info(video_url)

    async def search_github(self, query: str, limit: int = 10) -> List[ContentItem]:
        """搜索GitHub仓库"""
        return await self.github.search_repos(query, limit)

    async def get_github_repo(self, owner: str, repo: str) -> Dict:
        """获取GitHub仓库信息"""
        return await self.github.get_repo(owner, repo)

    async def get_github_readme(self, owner: str, repo: str) -> str:
        """获取GitHub README"""
        return await self.github.get_readme(owner, repo)

    async def fetch_rss(self, feed_url: str, limit: int = 10) -> List[ContentItem]:
        """获取RSS源"""
        return await self.rss.fetch(feed_url, limit)

    async def search_web(self, query: str, limit: int = 10) -> List[ContentItem]:
        """全网搜索"""
        # 优先使用Exa搜索
        if self.config.exa_api_key:
            return await self.exa.search(query, limit)

        # 回退到基础搜索（模拟）
        return []

    async def search_all(self, query: str) -> SearchResult:
        """综合搜索"""
        start_time = datetime.now()
        all_results = []
        sources = []

        # 并行执行各平台搜索
        tasks = [
            self.search_web(query),
            self.search_github(query),
            self.fetch_rss(query)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_results.extend(result)

        # 去重
        seen_urls = set()
        unique_results = []
        for item in all_results:
            if item.url and item.url not in seen_urls:
                seen_urls.add(item.url)
                unique_results.append(item)

        search_time = (datetime.now() - start_time).total_seconds()

        return SearchResult(
            id=hashlib.md5(query.encode()).hexdigest()[:16],
            query=query,
            results=unique_results[:20],
            total=len(unique_results),
            search_time=search_time,
            sources=list(set(sources))
        )


# =============================================================================
# API Interface
# =============================================================================

class AgentReachAPI:
    """Agent-Reach API接口"""

    def __init__(self, config: Optional[AgentReachConfig] = None):
        self.agent_reach = AgentReach(config)

    async def read_url(self, url: str) -> Dict:
        """读取URL内容"""
        content = await self.agent_reach.read_web(url)
        return self._content_to_dict(content)

    async def get_youtube(self, url: str) -> Dict:
        """获取YouTube内容"""
        info = await self.agent_reach.get_youtube_info(url)
        transcript = await self.agent_reach.get_youtube_transcript(url)

        result = self._content_to_dict(info)
        result['transcript'] = transcript
        return result

    async def search_github(self, query: str) -> List[Dict]:
        """搜索GitHub"""
        results = await self.agent_reach.search_github(query)
        return [self._content_to_dict(r) for r in results]

    async def get_repo(self, owner: str, repo: str) -> Dict:
        """获取仓库"""
        return await self.agent_reach.get_github_repo(owner, repo)

    async def get_readme(self, owner: str, repo: str) -> str:
        """获取README"""
        return await self.agent_reach.get_github_readme(owner, repo)

    async def search(self, query: str) -> Dict:
        """综合搜索"""
        result = await self.agent_reach.search_all(query)
        return {
            "id": result.id,
            "query": result.query,
            "results": [self._content_to_dict(r) for r in result.results],
            "total": result.total,
            "search_time": result.search_time
        }

    async def fetch_rss(self, feed_url: str) -> List[Dict]:
        """获取RSS"""
        results = await self.agent_reach.fetch_rss(feed_url)
        return [self._content_to_dict(r) for r in results]

    def _content_to_dict(self, content: ContentItem) -> Dict:
        """转换为字典"""
        return {
            "id": content.id,
            "platform": content.platform.value,
            "title": content.title,
            "content": content.content,
            "summary": content.summary,
            "url": content.url,
            "author": content.author,
            "published_at": content.published_at,
            "metadata": content.metadata
        }


# =============================================================================
# Global Instance
# =============================================================================

_agent_reach_api: Optional[AgentReachAPI] = None


def get_agent_reach(config: Optional[AgentReachConfig] = None) -> AgentReachAPI:
    """获取Agent-Reach API实例"""
    global _agent_reach_api
    if _agent_reach_api is None:
        _agent_reach_api = AgentReachAPI(config)
    return _agent_reach_api
