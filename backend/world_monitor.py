#!/usr/bin/env python3
"""
Nanobot Factory - World Monitor Module
全网信息检索、热点监控、舆情分析模块
基于WorldMonitor项目架构，支持多源数据聚合、实时监控、智能分析

功能：
- 全网信息检索（RSS、API、网页爬取）
- 热点话题检测与趋势分析
- 舆情分析与情感判断
- 多源数据聚合
- 智能情报合成

@author MiniMax Agent
@date 2026-03-03
"""

import os
import json
import asyncio
import logging
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import aiohttp
import feedparser
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class ThreatLevel(Enum):
    """威胁等级分类"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SentimentType(Enum):
    """情感类型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


@dataclass
class NewsArticle:
    """新闻文章"""
    id: str
    title: str
    content: str
    summary: str
    url: str
    source: str
    source_type: str  # rss, twitter, weibo, github, etc.
    published_at: str
    sentiment: SentimentType = SentimentType.NEUTRAL
    sentiment_score: float = 0.0
    entities: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    threat_level: ThreatLevel = ThreatLevel.INFO
    relevance_score: float = 0.0
    language: str = "zh"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotTopic:
    """热点话题"""
    id: str
    topic: str
    description: str
    热度: int
    trend: str  # rising, falling, stable
    sentiment: SentimentType
    first_seen: str
    last_updated: str
    related_articles: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    region: str = "global"
    category: str = "general"


@dataclass
class MonitorConfig:
    """监控配置"""
    keywords: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)  # rss urls, api endpoints
    regions: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=lambda: ["zh", "en"])
    update_interval: int = 300  # seconds
    sentiment_analysis: bool = True
    threat_detection: bool = True


@dataclass
class WorldBrief:
    """AI合成世界简报"""
    id: str
    title: str
    summary: str
    key_events: List[str] = field(default_factory=list)
    hot_topics: List[str] = field(default_factory=list)
    sentiment_overall: SentimentType = SentimentType.NEUTRAL
    regions: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    sources_count: int = 0


# =============================================================================
# Data Sources
# =============================================================================

class DataSourceType(Enum):
    """数据源类型"""
    RSS = "rss"
    TWITTER = "twitter"
    WEIBO = "weibo"
    GITHUB = "github"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    REDDIT = "reddit"
    API = "api"
    WEB = "web"


class BaseDataSource:
    """数据源基类"""

    def __init__(self, source_type: DataSourceType, name: str):
        self.source_type = source_type
        self.name = name
        self.enabled = True

    async def fetch(self, query: Optional[str] = None, **kwargs) -> List[NewsArticle]:
        """获取数据"""
        raise NotImplementedError

    async def search(self, query: str, **kwargs) -> List[NewsArticle]:
        """搜索数据"""
        raise NotImplementedError


class RSSDataSource(BaseDataSource):
    """RSS数据源"""

    # 默认RSS源（地缘政治、科技、AI）
    DEFAULT_SOURCES = [
        # 科技与AI
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://wired.com/feed/rss",
        "https://venturebeat.com/feed/",
        "https://arxiv.org/rss/",
        # 国内科技
        "https://www.36kr.com/feed/",
        "https://www.ifeng.com/rss/",
        # 地缘政治
        "https://www.reutersagency.com/feed/",
        "https://foreignpolicy.com/feed/",
    ]

    def __init__(self):
        super().__init__(DataSourceType.RSS, "RSS Aggregator")
        self.sources = self.DEFAULT_SOURCES.copy()
        self.cache: Dict[str, List[NewsArticle]] = {}
        self.cache_ttl = 300  # 5 minutes

    async def fetch(self, query: Optional[str] = None, **kwargs) -> List[NewsArticle]:
        """获取RSS源内容"""
        articles = []
        current_time = datetime.now()

        # Check cache
        cache_key = query or "all"
        if cache_key in self.cache:
            cached_articles, cache_time = self.cache[cache_key]
            if (current_time - cache_time).total_seconds() < self.cache_ttl:
                return cached_articles

        for source_url in self.sources:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(source_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            parsed = feedparser.parse(content)

                            for entry in parsed.entries[:10]:  # 限制每源数量
                                article = self._parse_entry(entry, source_url)
                                if query is None or self._matches_query(article, query):
                                    articles.append(article)

            except Exception as e:
                logger.warning(f"Failed to fetch RSS {source_url}: {e}")

        # Update cache
        self.cache[cache_key] = (articles, current_time)
        return articles

    def _parse_entry(self, entry: feedparser.FeedParserDict, source_url: str) -> NewsArticle:
        """解析RSS条目"""
        article_id = hashlib.md5(entry.get('link', '').encode()).hexdigest()[:16]

        # 提取内容
        content = entry.get('summary', '') or entry.get('description', '') or ''
        # 清理HTML标签
        content_clean = re.sub(r'<[^>]+>', '', content)
        content_clean = content_clean.strip()

        # 提取摘要
        summary = content_clean[:200] + '...' if len(content_clean) > 200 else content_clean

        # 提取发布时间
        published = entry.get('published', datetime.now().isoformat())
        if isinstance(published, datetime):
            published = published.isoformat()

        return NewsArticle(
            id=article_id,
            title=entry.get('title', 'Untitled'),
            content=content_clean,
            summary=summary,
            url=entry.get('link', ''),
            source=self._extract_source_name(source_url),
            source_type="rss",
            published_at=published,
            language="en"
        )

    def _extract_source_name(self, url: str) -> str:
        """从URL提取源名称"""
        try:
            domain = url.split('/')[2]
            return domain.replace('www.', '')
        except Exception as e:
            logger.warning(f"从URL提取源名称失败 {url}: {e}")
            return url

    def _matches_query(self, article: NewsArticle, query: str) -> bool:
        """检查文章是否匹配查询"""
        query_lower = query.lower()
        return (query_lower in article.title.lower() or
                query_lower in article.content.lower())

    async def search(self, query: str, **kwargs) -> List[NewsArticle]:
        """搜索RSS内容"""
        return await self.fetch(query=query)


class WebSearchDataSource(BaseDataSource):
    """网页搜索数据源（模拟Jina Reader功能）"""

    def __init__(self):
        super().__init__(DataSourceType.WEB, "Web Search")
        self.jina_reader_url = "https://r.jina.ai"

    async def fetch(self, query: Optional[str] = None, **kwargs) -> List[NewsArticle]:
        """获取网页内容"""
        if not query:
            return []
        return await self.search(query)

    async def search(self, query: str, **kwargs) -> List[NewsArticle]:
        """使用Jina Reader搜索网页"""
        articles = []

        # 使用搜索引擎获取相关URL（模拟）
        search_urls = [
            f"https://www.google.com/search?q={query}&hl=zh-CN",
            f"https://www.bing.com/search?q={query}",
        ]

        for url in search_urls:
            try:
                # 使用Jina Reader读取页面
                reader_url = f"{self.jina_reader_url}/URL/{url}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(reader_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            article = self._parse_web_content(content, url, query)
                            articles.append(article)
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")

        return articles[:5]  # 限制结果数量

    def _parse_web_content(self, content: str, url: str, query: str) -> NewsArticle:
        """解析网页内容"""
        lines = content.split('\n')
        title = lines[0] if lines else query
        body = '\n'.join(lines[1:]) if len(lines) > 1 else content

        article_id = hashlib.md5(url.encode()).hexdigest()[:16]

        return NewsArticle(
            id=article_id,
            title=title[:200],
            content=body[:2000],
            summary=body[:200] if len(body) > 200 else body,
            url=url,
            source=url.split('/')[2] if '://' in url else url,
            source_type="web",
            published_at=datetime.now().isoformat(),
            relevance_score=1.0
        )


class GitHubDataSource(BaseDataSource):
    """GitHub数据源"""

    def __init__(self):
        super().__init__(DataSourceType.GITHUB, "GitHub")

    async def fetch(self, query: Optional[str] = None, **kwargs) -> List[NewsArticle]:
        """获取GitHub trending"""
        if query:
            return await self.search(query)
        return await self._fetch_trending()

    async def _fetch_trending(self) -> List[NewsArticle]:
        """获取GitHub trending"""
        articles = []
        url = "https://api.github.com/search/repositories?q=created:>7days&sort=stars&order=desc"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for repo in data.get('items', [])[:10]:
                            article = NewsArticle(
                                id=hashlib.md5(repo['html_url'].encode()).hexdigest()[:16],
                                title=f"{repo['name']}: {repo['description'] or 'No description'}",
                                content=f"Stars: {repo['stargazers_count']}\nForks: {repo['forks_count']}\nLanguage: {repo['language'] or 'N/A'}",
                                summary=repo.get('description', '')[:200],
                                url=repo['html_url'],
                                source="github.com",
                                source_type="github",
                                published_at=repo['created_at'],
                                topics=[repo['language']] if repo.get('language') else []
                            )
                            articles.append(article)
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub trending: {e}")

        return articles

    async def search(self, query: str, **kwargs) -> List[NewsArticle]:
        """搜索GitHub仓库"""
        articles = []
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for repo in data.get('items', [])[:10]:
                            article = NewsArticle(
                                id=hashlib.md5(repo['html_url'].encode()).hexdigest()[:16],
                                title=repo['name'],
                                content=repo.get('description', ''),
                                summary=repo.get('description', '')[:200],
                                url=repo['html_url'],
                                source="github.com",
                                source_type="github",
                                published_at=repo['created_at'],
                                relevance_score=repo['stargazers_count'] / 1000
                            )
                            articles.append(article)
        except Exception as e:
            logger.warning(f"Failed to search GitHub: {e}")

        return articles


# =============================================================================
# Analysis Engine
# =============================================================================

class SentimentAnalyzer:
    """情感分析器"""

    # 情感关键词
    POSITIVE_WORDS = [
        '好', '棒', '优秀', '完美', '喜欢', '赞', '成功', '增长', '创新', '突破',
        'good', 'great', 'excellent', 'amazing', 'wonderful', 'best', 'success', 'growth'
    ]

    NEGATIVE_WORDS = [
        '坏', '差', '糟糕', '失败', '问题', '风险', '危机', '崩盘', '下跌',
        'bad', 'terrible', 'awful', 'worst', 'fail', 'crisis', 'risk', 'problem', 'crash'
    ]

    def analyze(self, text: str) -> tuple[SentimentType, float]:
        """分析文本情感"""
        text_lower = text.lower()

        positive_count = sum(1 for word in self.POSITIVE_WORDS if word in text_lower)
        negative_count = sum(1 for word in self.NEGATIVE_WORDS if word in text_lower)

        total = positive_count + negative_count
        if total == 0:
            return SentimentType.NEUTRAL, 0.0

        score = (positive_count - negative_count) / total

        if score > 0.3:
            return SentimentType.POSITIVE, score
        elif score < -0.3:
            return SentimentType.NEGATIVE, abs(score)
        else:
            return SentimentType.NEUTRAL, abs(score)

    def analyze_batch(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """批量分析文章情感"""
        for article in articles:
            sentiment, score = self.analyze(article.title + ' ' + article.content)
            article.sentiment = sentiment
            article.sentiment_score = score

        return articles


class ThreatDetector:
    """威胁检测器"""

    # 威胁关键词（按级别）
    THREAT_KEYWORDS = {
        ThreatLevel.CRITICAL: ['战争', '核武器', '恐怖袭击', '核弹', '核战争', 'war', 'nuclear', 'terrorist'],
        ThreatLevel.HIGH: ['冲突', '危机', '制裁', '军事', '战争', 'conflict', 'crisis', 'sanction', 'military'],
        ThreatLevel.MEDIUM: ['抗议', '动荡', '紧张', '不稳定', 'protest', 'unrest', 'tension'],
        ThreatLevel.LOW: ['争议', '问题', 'concern', 'issue', 'dispute'],
    }

    def detect(self, article: NewsArticle) -> ThreatLevel:
        """检测威胁等级"""
        text = (article.title + ' ' + article.content).lower()

        # 从高到低检查
        for level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH, ThreatLevel.MEDIUM, ThreatLevel.LOW]:
            keywords = self.THREAT_KEYWORDS.get(level, [])
            if any(kw in text for kw in keywords):
                return level

        return ThreatLevel.INFO


class EntityExtractor:
    """实体提取器"""

    def extract(self, text: str) -> List[str]:
        """提取实体（简化版）"""
        # 提取@mentions
        mentions = re.findall(r'@(\w+)', text)

        # 提取#话题#
        topics = re.findall(r'#(\w+)#', text)

        # 提取URLs
        urls = re.findall(r'https?://\S+', text)

        # 提取大写字母开头的词
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)

        entities = list(set(mentions + topics + words[:10]))
        return entities[:20]


# =============================================================================
# World Monitor Core
# =============================================================================

class WorldMonitor:
    """世界监控器 - 核心类"""

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.data_sources: Dict[DataSourceType, BaseDataSource] = {}
        self.sentiment_analyzer = SentimentAnalyzer()
        self.threat_detector = ThreatDetector()
        self.entity_extractor = EntityExtractor()
        self.articles_cache: List[NewsArticle] = []
        self.hot_topics: Dict[str, HotTopic] = {}
        self._initialize_sources()

    def _initialize_sources(self):
        """初始化数据源"""
        self.data_sources[DataSourceType.RSS] = RSSDataSource()
        self.data_sources[DataSourceType.WEB] = WebSearchDataSource()
        self.data_sources[DataSourceType.GITHUB] = GitHubDataSource()

    async def fetch_all(self, query: Optional[str] = None) -> List[NewsArticle]:
        """从所有数据源获取内容"""
        all_articles = []

        # 并行获取所有源
        tasks = [source.fetch(query) for source in self.data_sources.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)

        # 去重
        seen_ids = set()
        unique_articles = []
        for article in all_articles:
            if article.id not in seen_ids:
                seen_ids.add(article.id)
                unique_articles.append(article)

        # 分析
        for article in unique_articles:
            # 情感分析
            sentiment, score = self.sentiment_analyzer.analyze(
                article.title + ' ' + article.content
            )
            article.sentiment = sentiment
            article.sentiment_score = score

            # 威胁检测
            article.threat_level = self.threat_detector.detect(article)

            # 实体提取
            article.entities = self.entity_extractor.extract(
                article.title + ' ' + article.content
            )

        # 更新缓存
        self.articles_cache = unique_articles

        return unique_articles

    async def search(self, query: str) -> List[NewsArticle]:
        """搜索内容"""
        all_articles = []

        tasks = [source.search(query) for source in self.data_sources.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)

        return all_articles

    def detect_hot_topics(self, articles: List[NewsArticle], threshold: int = 5) -> List[HotTopic]:
        """检测热点话题"""
        topic_counts = defaultdict(lambda: {"count": 0, "articles": [], "keywords": set()})

        for article in articles:
            # 提取关键词
            title_words = article.title.split()
            content_words = article.content.split()[:50]

            for word in list(set(title_words + content_words)):
                if len(word) > 2:
                    topic_counts[word]["count"] += 1
                    topic_counts[word]["articles"].append(article.id)
                    topic_counts[word]["keywords"].add(word)

        # 排序并生成热点话题
        sorted_topics = sorted(
            topic_counts.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )

        hot_topics = []
        current_time = datetime.now()

        for topic, data in sorted_topics[:20]:
            if data["count"] >= threshold:
                # 计算趋势
                trend = "stable"
                if topic in self.hot_topics:
                    old_count = self.hot_topics[topic].热度
                    if data["count"] > old_count * 1.5:
                        trend = "rising"
                    elif data["count"] < old_count * 0.7:
                        trend = "falling"

                # 情感分析
                topic_articles = [a for a in articles if a.id in data["articles"]]
                sentiments = [a.sentiment for a in topic_articles]
                dominant_sentiment = max(set(sentiments), key=sentiments.count) if sentiments else SentimentType.NEUTRAL

                # Get existing topic for trend calculation, or use current time as default
                existing_topic = self.hot_topics.get(topic)
                first_seen = existing_topic.first_seen if existing_topic else current_time.isoformat()

                hot_topic = HotTopic(
                    id=hashlib.md5(topic.encode()).hexdigest()[:16],
                    topic=topic,
                    description=f"关于{topic}的{data['count']}篇相关报道",
                    热度=data["count"],
                    trend=trend,
                    sentiment=dominant_sentiment,
                    first_seen=first_seen,
                    last_updated=current_time.isoformat(),
                    related_articles=data["articles"][:10],
                    keywords=list(data["keywords"])[:10]
                )

                hot_topics.append(hot_topic)
                self.hot_topics[topic] = hot_topic

        return hot_topics

    async def generate_world_brief(self, topic: Optional[str] = None) -> WorldBrief:
        """生成世界简报"""
        # 获取最新文章
        articles = await self.fetch_all(topic)

        # 检测热点
        hot_topics = self.detect_hot_topics(articles)

        # 计算整体情感
        sentiments = [a.sentiment for a in articles]
        overall_sentiment = max(set(sentiments), key=sentiments.count) if sentiments else SentimentType.NEUTRAL

        # 提取关键事件
        key_events = []
        for article in sorted(articles, key=lambda x: x.relevance_score, reverse=True)[:5]:
            key_events.append(f"- {article.title}")

        # 生成简报
        brief = WorldBrief(
            id=hashlib.md5(str(datetime.now()).encode()).hexdigest()[:16],
            title=f"世界简报 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            summary=f"共收集 {len(articles)} 篇报道，检测到 {len(hot_topics)} 个热点话题",
            key_events=key_events,
            hot_topics=[t.topic for t in hot_topics[:10]],
            sentiment_overall=overall_sentiment,
            regions={},
            generated_at=datetime.now().isoformat(),
            sources_count=len(articles)
        )

        return brief

    def get_trending(self, category: Optional[str] = None, limit: int = 10) -> List[HotTopic]:
        """获取趋势话题"""
        topics = sorted(
            self.hot_topics.values(),
            key=lambda x: x.热度,
            reverse=True
        )

        if category:
            topics = [t for t in topics if t.category == category]

        return topics[:limit]

    def get_articles_by_sentiment(self, sentiment: SentimentType) -> List[NewsArticle]:
        """按情感筛选文章"""
        return [a for a in self.articles_cache if a.sentiment == sentiment]

    def get_articles_by_threat(self, level: ThreatLevel) -> List[NewsArticle]:
        """按威胁等级筛选文章"""
        return [a for a in self.articles_cache if a.threat_level == level]


# =============================================================================
# API Interface
# =============================================================================

class WorldMonitorAPI:
    """World Monitor API接口"""

    def __init__(self):
        self.monitor = WorldMonitor()
        self.is_running = False
        self.update_task = None

    async def start_monitoring(self, interval: int = 300):
        """启动监控"""
        self.is_running = True
        self.monitor.config.update_interval = interval

        while self.is_running:
            try:
                await self.monitor.fetch_all()
                logger.info(f"监控更新: 获取 {len(self.monitor.articles_cache)} 篇文章")
            except Exception as e:
                logger.error(f"监控更新失败: {e}")

            await asyncio.sleep(interval)

    def stop_monitoring(self):
        """停止监控"""
        self.is_running = False

    async def get_news(self, query: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """获取新闻列表"""
        articles = await self.monitor.fetch_all(query)
        articles = sorted(articles, key=lambda x: x.relevance_score, reverse=True)[:limit]

        return [self._article_to_dict(a) for a in articles]

    async def get_hot_topics(self, limit: int = 10) -> List[Dict]:
        """获取热点话题"""
        topics = self.monitor.get_trending(limit=limit)
        return [self._topic_to_dict(t) for t in topics]

    async def get_world_brief(self) -> Dict:
        """获取世界简报"""
        brief = await self.monitor.generate_world_brief()
        return self._brief_to_dict(brief)

    async def search(self, query: str, limit: int = 20) -> List[Dict]:
        """搜索内容"""
        articles = await self.monitor.search(query)
        return [self._article_to_dict(a) for a in articles[:limit]]

    def _article_to_dict(self, article: NewsArticle) -> Dict:
        """转换文章为字典"""
        return {
            "id": article.id,
            "title": article.title,
            "content": article.content[:500],
            "summary": article.summary,
            "url": article.url,
            "source": article.source,
            "source_type": article.source_type,
            "published_at": article.published_at,
            "sentiment": article.sentiment.value,
            "sentiment_score": article.sentiment_score,
            "threat_level": article.threat_level.value,
            "entities": article.entities[:10],
            "topics": article.topics[:10]
        }

    def _topic_to_dict(self, topic: HotTopic) -> Dict:
        """转换话题为字典"""
        return {
            "id": topic.id,
            "topic": topic.topic,
            "description": topic.description,
            "热度": topic.热度,
            "trend": topic.trend,
            "sentiment": topic.sentiment.value,
            "first_seen": topic.first_seen,
            "last_updated": topic.last_updated,
            "keywords": topic.keywords[:10]
        }

    def _brief_to_dict(self, brief: WorldBrief) -> Dict:
        """转换简报为字典"""
        return {
            "id": brief.id,
            "title": brief.title,
            "summary": brief.summary,
            "key_events": brief.key_events,
            "hot_topics": brief.hot_topics,
            "sentiment_overall": brief.sentiment_overall.value,
            "generated_at": brief.generated_at,
            "sources_count": brief.sources_count
        }


# =============================================================================
# Global Instance
# =============================================================================

_world_monitor_api: Optional[WorldMonitorAPI] = None


def get_world_monitor() -> WorldMonitorAPI:
    """获取World Monitor API实例"""
    global _world_monitor_api
    if _world_monitor_api is None:
        _world_monitor_api = WorldMonitorAPI()
    return _world_monitor_api
