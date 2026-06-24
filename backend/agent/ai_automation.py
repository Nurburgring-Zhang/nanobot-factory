"""
NanoBot Factory 全AI自动化驱动系统
文件: agent/ai_automation.py
功能：全球信息采集、Agent Reach、World Monitor、热点追踪
作者：Matrix Agent
版本：v1.0.0
"""

import os
import json
import asyncio
import logging
import hashlib
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import threading
import queue
import time
from urllib.parse import urljoin, urlparse
import html
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import feedparser
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AIAutomation")


# ==================== 枚举类型定义 ====================

class Region(Enum):
    """地理区域"""
    CHINA = "china"
    ASIA = "asia"
    EUROPE = "europe"
    AMERICAS = "americas"
    GLOBAL = "global"


class DataSourceType(Enum):
    """数据源类型"""
    NEWS = "news"
    SOCIAL_MEDIA = "social_media"
    FORUM = "forum"
    BLOG = "blog"
    ACADEMIC = "academic"
    GOVERNMENT = "government"
    ECOMMERCE = "ecommerce"
    VIDEO = "video"
    SEARCH_ENGINE = "search_engine"
    RSS = "rss"
    API = "api"


class ContentType(Enum):
    """内容类型"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    MIXED = "mixed"


class TopicCategory(Enum):
    """话题分类"""
    TECHNOLOGY = "technology"
    POLITICS = "politics"
    ECONOMY = "economy"
    ENTERTAINMENT = "entertainment"
    SPORTS = "sports"
    SCIENCE = "science"
    HEALTH = "health"
    EDUCATION = "education"
    TRAVEL = "travel"
    FOOD = "food"
    FASHION = "fashion"
    GAMING = "gaming"
    BUSINESS = "business"
    FINANCE = "finance"
    OTHER = "other"


class SentimentType(Enum):
    """情感类型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class PriorityLevel(Enum):
    """优先级"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


# ==================== 数据类定义 ====================

@dataclass
class DataSource:
    """数据源"""
    source_id: str
    name: str
    url: str
    source_type: DataSourceType
    region: Region
    language: str
    reliability_score: float = 0.5
    update_frequency: int = 60
    is_active: bool = True
    last_scraped: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectedItem:
    """采集项目"""
    item_id: str
    source_id: str
    url: str
    title: str
    content: str
    content_type: ContentType
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=datetime.now)
    region: Region = Region.GLOBAL
    language: str = "zh"
    topic_categories: List[TopicCategory] = field(default_factory=list)
    sentiment: SentimentType = SentimentType.NEUTRAL
    tags: List[str] = field(default_factory=list)
    quality_score: float = 0.5
    is_processed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotTopic:
    """热点话题"""
    topic_id: str
    keywords: List[str]
    title: str
    description: str
    topic_category: TopicCategory
    heat_score: float
    trend_direction: str
    first_appeared: datetime
    last_updated: datetime
    total_mentions: int
    region: Region = Region.GLOBAL
    sources: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapingTask:
    """采集任务"""
    task_id: str
    source: DataSource
    priority: PriorityLevel
    max_items: int = 100
    time_range: Optional[Tuple[datetime, datetime]] = None
    keywords: List[str] = field(default_factory=list)
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    items_collected: int = 0
    error_message: Optional[str] = None


# ==================== 网页抓取引擎 ====================

class WebScraper:
    """网页抓取引擎"""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def fetch(self, url: str) -> Optional[str]:
        """抓取网页内容"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.warning(f"抓取失败 {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def parse_html(self, html_content: str) -> BeautifulSoup:
        """解析HTML"""
        return BeautifulSoup(html_content, 'html.parser')

    def extract_text(self, soup: BeautifulSoup) -> str:
        """提取文本"""
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(separator='\n', strip=True)

    def extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """提取链接"""
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http'):
                links.append(href)
            else:
                links.append(urljoin(base_url, href))
        return links


# ==================== RSS聚合器 ====================

class RSSAggregator:
    """RSS订阅聚合器"""

    def __init__(self):
        self.feeds: Dict[str, str] = {}

    def add_feed(self, name: str, url: str):
        """添加RSS源"""
        self.feeds[name] = url

    def fetch_all(self) -> List[Dict[str, Any]]:
        """获取所有订阅源"""
        results = []
        for name, url in self.feeds.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    results.append({
                        'source': name,
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'published': entry.get('published', ''),
                        'summary': entry.get('summary', ''),
                        'author': entry.get('author', '')
                    })
            except Exception as e:
                logger.error(f"RSS解析失败 {name}: {e}")
        return results


# ==================== 情感分析器 ====================

class SentimentAnalyzer:
    """简单情感分析器"""

    POSITIVE_WORDS = {'好', '优秀', '棒', '赞', '喜欢', '满意', '支持', '成功', '突破', '创新', 'great', 'good', 'excellent', 'amazing'}
    NEGATIVE_WORDS = {'差', '坏', '烂', '糟糕', '失望', '问题', '失败', '错误', '危险', 'bad', 'poor', 'terrible', 'awful', 'fail'}

    def analyze(self, text: str) -> Tuple[SentimentType, float]:
        """分析情感"""
        text_lower = text.lower()
        pos_count = sum(1 for word in self.POSITIVE_WORDS if word in text_lower)
        neg_count = sum(1 for word in self.NEGATIVE_WORDS if word in text_lower)

        total = pos_count + neg_count
        if total == 0:
            return SentimentType.NEUTRAL, 0.5

        score = pos_count / total
        if score > 0.6:
            return SentimentType.POSITIVE, score
        elif score < 0.4:
            return SentimentType.NEGATIVE, 1 - score
        return SentimentType.MIXED, 0.5


# ==================== 话题追踪器 ====================

class TopicTracker:
    """热点话题追踪器"""

    def __init__(self, window_minutes: int = 60):
        self.window_minutes = window_minutes
        self.mention_timeline: Dict[str, List[datetime]] = defaultdict(list)
        self.topics: Dict[str, HotTopic] = {}

    def record_mention(self, topic_id: str, timestamp: datetime):
        """记录话题提及"""
        self.mention_timeline[topic_id].append(timestamp)

    def calculate_heat(self, topic_id: str) -> float:
        """计算热度"""
        if topic_id not in self.mention_timeline:
            return 0.0

        cutoff = datetime.now() - timedelta(minutes=self.window_minutes)
        recent = [t for t in self.mention_timeline[topic_id] if t > cutoff]
        return len(recent) * 10.0

    def get_trend(self, topic_id: str) -> str:
        """获取趋势"""
        if topic_id not in self.mention_timeline:
            return "stable"

        now = datetime.now()
        recent = self.mention_timeline[topic_id]

        last_hour = [t for t in recent if t > now - timedelta(hours=1)]
        last_2hours = [t for t in recent if t > now - timedelta(hours=2)]

        if len(last_hour) > len(last_2hours) / 2:
            return "up"
        elif len(last_hour) < len(last_2hours) / 4:
            return "down"
        return "stable"


# ==================== 数据采集器基类 ====================

class BaseCollector(ABC):
    """数据采集器基类"""

    @abstractmethod
    async def collect(self, task: ScrapingTask) -> List[CollectedItem]:
        """执行采集"""
        pass


# ==================== 新闻采集器 ====================

class NewsCollector(BaseCollector):
    """新闻网站采集器"""

    def __init__(self):
        self.scraper = WebScraper()
        self.sentiment = SentimentAnalyzer()

    async def collect(self, task: ScrapingTask) -> List[CollectedItem]:
        """采集新闻"""
        items = []
        html = self.scraper.fetch(task.source.url)
        if not html:
            return items

        soup = self.scraper.parse_html(html)
        articles = soup.find_all('article') or soup.find_all('div', class_=re.compile('article|news|post'))

        for idx, article in enumerate(articles[:task.max_items]):
            try:
                title_elem = article.find(['h1', 'h2', 'h3']) or article.find('a')
                title = title_elem.get_text(strip=True) if title_elem else ""

                link_elem = article.find('a', href=True)
                url = link_elem['href'] if link_elem else task.source.url
                if not url.startswith('http'):
                    url = urljoin(task.source.url, url)

                content = self.scraper.extract_text(article)

                sentiment, score = self.sentiment.analyze(content)

                item = CollectedItem(
                    item_id=hashlib.md5(f"{url}{idx}".encode()).hexdigest(),
                    source_id=task.source.source_id,
                    url=url,
                    title=title,
                    content=content[:5000],
                    content_type=ContentType.TEXT,
                    region=task.source.region,
                    language=task.source.language,
                    sentiment=sentiment,
                    quality_score=score,
                    metadata={'source_name': task.source.name}
                )
                items.append(item)
            except Exception as e:
                logger.error(f"解析文章失败: {e}")

        return items


# ==================== AgentReach 全球信息采集系统 ====================

class AgentReachSystem:
    """AgentReach 全球信息采集系统"""

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.data_sources: Dict[str, DataSource] = {}
        self.collectors: Dict[DataSourceType, BaseCollector] = {
            DataSourceType.NEWS: NewsCollector(),
        }
        self.topic_tracker = TopicTracker()
        self.rss_aggregator = RSSAggregator()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        self._init_default_sources()

    def _init_default_sources(self):
        """初始化默认数据源"""
        default_sources = [
            DataSource("src_news_sina", "新浪新闻", "https://news.sina.com.cn/", DataSourceType.NEWS, Region.CHINA, "zh"),
            DataSource("src_news_tencent", "腾讯新闻", "https://news.qq.com/", DataSourceType.NEWS, Region.CHINA, "zh"),
            DataSource("src_news_bbc", "BBC News", "https://www.bbc.com/news", DataSourceType.NEWS, Region.EUROPE, "en"),
            DataSource("src_news_cnn", "CNN", "https://www.cnn.com/", DataSourceType.NEWS, Region.AMERICAS, "en"),
        ]
        for source in default_sources:
            self.data_sources[source.source_id] = source

    def add_data_source(self, source: DataSource):
        """添加数据源"""
        self.data_sources[source.source_id] = source

    async def reach(self, regions: List[Region] = None, keywords: List[str] = None) -> List[CollectedItem]:
        """从多区域采集信息"""
        all_items = []

        if regions is None:
            regions = [Region.GLOBAL]

        for source in self.data_sources.values():
            if not source.is_active:
                continue
            if regions and source.region not in regions:
                continue

            task = ScrapingTask(
                task_id=f"task_{source.source_id}_{int(time.time())}",
                source=source,
                priority=PriorityLevel.NORMAL,
                keywords=keywords or []
            )

            collector = self.collectors.get(source.source_type)
            if collector:
                items = await collector.collect(task)
                all_items.extend(items)

                for item in items:
                    self.topic_tracker.record_mention(item.topic_id, item.scraped_at)

        return all_items


# ==================== World Monitor 热点监控系统 ====================

class WorldMonitor:
    """World Monitor 热点话题监控系统"""

    def __init__(self, track_window: int = 60):
        self.tracker = TopicTracker(window_minutes=track_window)
        self.keywords: Dict[str, List[str]] = {
            TopicCategory.TECHNOLOGY: ['AI', 'ChatGPT', '科技', '技术'],
            TopicCategory.POLITICS: ['政治', '政府', '选举'],
            TopicCategory.ECONOMY: ['经济', '股市', '金融'],
            TopicCategory.ENTERTAINMENT: ['娱乐', '明星', '电影'],
        }

    def track_topic(self, topic_id: str, items: List[CollectedItem]):
        """追踪话题"""
        for item in items:
            if any(kw.lower() in item.content.lower() for kw in self.keywords.get(item.topic_categories[0] if item.topic_categories else TopicCategory.OTHER, [])):
                self.tracker.record_mention(topic_id, item.scraped_at)

    def get_hot_topics(self, limit: int = 10) -> List[HotTopic]:
        """获取热点话题"""
        topics = []
        for topic_id in list(self.tracker.mention_timeline.keys())[:limit]:
            heat = self.tracker.calculate_heat(topic_id)
            if heat > 0:
                topic = HotTopic(
                    topic_id=topic_id,
                    keywords=[topic_id],
                    title=topic_id,
                    description="",
                    topic_category=TopicCategory.OTHER,
                    heat_score=heat,
                    trend_direction=self.tracker.get_trend(topic_id),
                    first_appeared=datetime.now(),
                    last_updated=datetime.now(),
                    total_mentions=len(self.tracker.mention_timeline[topic_id])
                )
                topics.append(topic)
        return sorted(topics, key=lambda t: t.heat_score, reverse=True)


# ==================== Data Processor 数据处理器 ====================

class DataProcessor:
    """数据处理器"""

    def __init__(self):
        self.sentiment = SentimentAnalyzer()

    def process(self, items: List[CollectedItem]) -> List[CollectedItem]:
        """处理采集的数据"""
        for item in items:
            if not item.is_processed:
                item.sentiment, item.quality_score = self.sentiment.analyze(item.content)
                item.is_processed = True
        return items

    def filter_by_quality(self, items: List[CollectedItem], threshold: float = 0.5) -> List[CollectedItem]:
        """按质量过滤"""
        return [item for item in items if item.quality_score >= threshold]

    def group_by_topic(self, items: List[CollectedItem]) -> Dict[TopicCategory, List[CollectedItem]]:
        """按话题分组"""
        grouped = defaultdict(list)
        for item in items:
            for category in item.topic_categories:
                grouped[category].append(item)
        return dict(grouped)


# ==================== Information Fusion 信息融合 ====================

class InformationFusion:
    """多源信息融合"""

    def __init__(self):
        self.fusion_cache: Dict[str, Dict[str, Any]] = {}

    def fuse(self, items: List[CollectedItem]) -> Dict[str, Any]:
        """融合信息"""
        if not items:
            return {}

        topics = defaultdict(list)
        sentiments = defaultdict(int)
        regions = defaultdict(int)

        for item in items:
            for cat in item.topic_categories:
                topics[cat].append(item)
            sentiments[item.sentiment] += 1
            regions[item.region] += 1

        return {
            'total_items': len(items),
            'topics': {k.value: len(v) for k, v in topics.items()},
            'sentiments': {k.value: v for k, v in sentiments.items()},
            'regions': {k.value: v for k, v in regions.items()},
            'avg_quality': sum(i.quality_score for i in items) / len(items),
            'sources': list(set(i.source_id for i in items))
        }


# ==================== AI Automation Engine 主引擎 ====================

class AIAutomationEngine:
    """AI自动化驱动主引擎"""

    def __init__(self):
        self.agent_reach = AgentReachSystem()
        self.world_monitor = WorldMonitor()
        self.processor = DataProcessor()
        self.fusion = InformationFusion()
        self.collected_data: List[CollectedItem] = []

    async def run(self, regions: List[Region] = None, keywords: List[str] = None) -> Dict[str, Any]:
        """运行自动化采集"""
        logger.info("启动AI自动化采集...")

        items = await self.agent_reach.reach(regions=regions, keywords=keywords)

        processed_items = self.processor.process(items)

        self.world_monitor.track_topic("global", processed_items)

        hot_topics = self.world_monitor.get_hot_topics()

        fusion_result = self.fusion.fuse(processed_items)

        self.collected_data.extend(processed_items)

        return {
            'items_collected': len(processed_items),
            'hot_topics': hot_topics,
            'fusion': fusion_result,
            'timestamp': datetime.now().isoformat()
        }

    def get_data(self, topic: TopicCategory = None, region: Region = None) -> List[CollectedItem]:
        """获取采集的数据"""
        result = self.collected_data
        if topic:
            result = [i for i in result if topic in i.topic_categories]
        if region:
            result = [i for i in result if i.region == region]
        return result


# ==================== 导出模块 ====================

__all__ = [
    'Region', 'DataSourceType', 'ContentType', 'TopicCategory', 'SentimentType', 'PriorityLevel',
    'DataSource', 'CollectedItem', 'HotTopic', 'ScrapingTask',
    'WebScraper', 'RSSAggregator', 'SentimentAnalyzer', 'TopicTracker',
    'BaseCollector', 'NewsCollector',
    'AgentReachSystem', 'WorldMonitor', 'DataProcessor', 'InformationFusion', 'AIAutomationEngine'
]
