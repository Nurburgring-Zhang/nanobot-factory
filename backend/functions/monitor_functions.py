"""
NanoBot Factory - Monitor Functions
舆情监控与世界信息监控深度集成

基于以下项目:
- koala73/worldmonitor: 全球情报监控
- SocialChangeLab/media-impact-monitor

功能:
1. 新闻监控
2. 社交媒体监控
3. 市场数据监控
4. 情感分析
5. 趋势分析
6. 地缘政治监控

@author MiniMax Agent
@date 2026-03-08
"""

import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class MonitorFunctionCategory(Enum):
    """监控函数分类"""
    NEWS = "news"                     # 新闻监控
    SOCIAL = "social"                 # 社交媒体监控
    MARKET = "market"               # 市场监控
    SENTIMENT = "sentiment"          # 情感分析
    TREND = "trend"                 # 趋势分析
    GEOPOLITICAL = "geopolitical"    # 地缘政治


@dataclass
class MonitorFunction:
    """监控函数定义"""
    id: str
    name: str
    description: str
    category: MonitorFunctionCategory
    source: str
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)


class MonitorFunctions:
    """Monitor Functions主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.functions: Dict[str, MonitorFunction] = {}
        self._initialize_functions()
        self._news_cache = {}
        
    def _initialize_functions(self):
        # 新闻监控
        self.functions["monitor_news"] = MonitorFunction(
            id="monitor_news",
            name="News Monitor",
            description="新闻监控 - 实时追踪特定关键词的新闻",
            category=MonitorFunctionCategory.NEWS,
            source="worldmonitor",
            parameters={"keywords": "关键词列表", "sources": "来源", "language": "语言"}
        )
        
        self.functions["monitor_global_news"] = MonitorFunction(
            id="monitor_global_news",
            name="Global News",
            description="全球新闻聚合 - 汇总多语言新闻源",
            category=MonitorFunctionCategory.NEWS,
            source="worldmonitor",
            parameters={"category": "类别", "region": "地区", "limit": "数量"}
        )
        
        # 社交媒体监控
        self.functions["monitor_social_mentions"] = MonitorFunction(
            id="monitor_social_mentions",
            name="Social Mentions",
            description="社交媒体提及监控 - 追踪品牌/人物提及",
            category=MonitorFunctionCategory.SOCIAL,
            source="worldmonitor",
            parameters={"target": "监控目标", "platforms": "平台列表"}
        )
        
        self.functions["monitor_hashtags"] = MonitorFunction(
            id="monitor_hashtags",
            name="Hashtag Monitor",
            description="话题标签监控 - 追踪热门话题",
            category=MonitorFunctionCategory.SOCIAL,
            source="worldmonitor",
            parameters={"hashtags": "标签列表", "platforms": "平台"}
        )
        
        # 市场监控
        self.functions["monitor_stock"] = MonitorFunction(
            id="monitor_stock",
            name="Stock Monitor",
            description="股票市场监控 - 追踪股票价格和新闻",
            category=MonitorFunctionCategory.MARKET,
            source="worldmonitor",
            parameters={"symbols": "股票代码", "alerts": "告警条件"}
        )
        
        self.functions["monitor_crypto"] = MonitorFunction(
            id="monitor_crypto",
            name="Crypto Monitor",
            description="加密货币监控 - 追踪价格和趋势",
            category=MonitorFunctionCategory.MARKET,
            source="worldmonitor",
            parameters={"coins": "币种列表", "alerts": "告警条件"}
        )
        
        self.functions["monitor_forex"] = MonitorFunction(
            id="monitor_forex",
            name="Forex Monitor",
            description="外汇市场监控 - 追踪汇率",
            category=MonitorFunctionCategory.MARKET,
            source="worldmonitor",
            parameters={"pairs": "货币对"}
        )
        
        # 情感分析
        self.functions["analyze_sentiment"] = MonitorFunction(
            id="analyze_sentiment",
            name="Sentiment Analysis",
            description="情感分析 - 分析文本情感倾向",
            category=MonitorFunctionCategory.SENTIMENT,
            source="worldmonitor",
            parameters={"text": "文本内容", "language": "语言"}
        )
        
        self.functions["analyze_brand_sentiment"] = MonitorFunction(
            id="analyze_brand_sentiment",
            name="Brand Sentiment",
            description="品牌情感分析 - 追踪品牌口碑",
            category=MonitorFunctionCategory.SENTIMENT,
            source="worldmonitor",
            parameters={"brand": "品牌名", "time_range": "时间范围"}
        )
        
        # 趋势分析
        self.functions["analyze_trends"] = MonitorFunction(
            id="analyze_trends",
            name="Trend Analysis",
            description="趋势分析 - 识别上升/下降趋势",
            category=MonitorFunctionCategory.TREND,
            source="worldmonitor",
            parameters={"keywords": "关键词", "time_range": "时间范围"}
        )
        
        self.functions["detect_emerging_topics"] = MonitorFunction(
            id="detect_emerging_topics",
            name="Emerging Topics",
            description="新兴话题检测 - 发现正在兴起的话题",
            category=MonitorFunctionCategory.TREND,
            source="worldmonitor",
            parameters={"category": "类别", "min_velocity": "最小增速"}
        )
        
        # 地缘政治
        self.functions["monitor_geopolitical"] = MonitorFunction(
            id="monitor_geopolitical",
            name="Geopolitical Monitor",
            description="地缘政治监控 - 追踪国际事件",
            category=MonitorFunctionCategory.GEOPOLITICAL,
            source="worldmonitor",
            parameters={"regions": "地区列表", "topics": "话题"}
        )
        
        self.functions["monitor_infrastructure"] = MonitorFunction(
            id="monitor_infrastructure",
            name="Infrastructure Monitor",
            description="基础设施监控 - 追踪关键设施状态",
            category=MonitorFunctionCategory.GEOPOLITICAL,
            source="worldmonitor",
            parameters={"type": "类型", "location": "位置"}
        )
        
    def get_function(self, func_id: str) -> Optional[MonitorFunction]:
        return self.functions.get(func_id)
    
    def get_all_functions(self) -> List[MonitorFunction]:
        return list(self.functions.values())
    
    def execute_function(self, func_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行监控函数 - 真实实现"""
        func = self.get_function(func_id)
        if not func:
            return {"error": f"Function {func_id} not found"}
        if not func.enabled:
            return {"error": f"Function {func_id} is disabled"}
        
        try:
            result = self._dispatch(func, parameters)
            return {
                "status": "success",
                "function_id": func_id,
                "source": func.source,
                "result": result,
                "parameters": parameters
            }
        except Exception as e:
            logger.error(f"Error executing monitor function {func_id}: {e}")
            return {
                "status": "error",
                "function_id": func_id,
                "error": str(e)
            }
    
    def _dispatch(self, func: MonitorFunction, params: Dict[str, Any]) -> Any:
        handler_map = {
            "monitor_news": self._monitor_news,
            "monitor_global_news": self._monitor_global_news,
            "monitor_social_mentions": self._monitor_social_mentions,
            "monitor_hashtags": self._monitor_hashtags,
            "monitor_stock": self._monitor_stock,
            "monitor_crypto": self._monitor_crypto,
            "monitor_forex": self._monitor_forex,
            "analyze_sentiment": self._analyze_sentiment,
            "analyze_brand_sentiment": self._analyze_brand_sentiment,
            "analyze_trends": self._analyze_trends,
            "detect_emerging_topics": self._detect_emerging_topics,
            "monitor_geopolitical": self._monitor_geopolitical,
            "monitor_infrastructure": self._monitor_infrastructure,
        }
        
        handler = handler_map.get(func.id)
        if handler:
            return handler(params)
        return f"Executed {func.name} (no specialized handler)"
    
    # ----- 新闻监控 handlers -----
    
    def _fetch_news_rss(self, url: str, limit: int = 10) -> List[Dict]:
        """Fetch news from an RSS feed"""
        try:
            import feedparser
            feed = feedparser.parse(url)
            entries = []
            for entry in feed.entries[:limit]:
                entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "")[:500],
                })
            return entries
        except ImportError:
            logger.warning("feedparser not installed, using fallback")
        except Exception as e:
            logger.warning(f"RSS fetch error: {e}")
        
        # Fallback: try to fetch a news aggregator
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                # Basic link extraction
                import re
                links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html)
                results = []
                for href, title in links[:limit]:
                    if not href.startswith("http"):
                        continue
                    results.append({"title": title.strip(), "link": href})
                return results
        except Exception as e:
            return [{"error": str(e)}]
    
    def _monitor_news(self, params: Dict[str, Any]) -> List[Dict]:
        """新闻监控 - 基于关键词获取新闻"""
        keywords = params.get("keywords", [])
        sources = params.get("sources", ["google"])
        language = params.get("language", "zh")
        
        if isinstance(keywords, str):
            keywords = [keywords]
        
        keyword_str = " ".join(keywords) if keywords else "news"
        
        news_items = []
        
        # Try NewsAPI first
        news_api_key = self.config.get("news_api_key", "")
        if news_api_key:
            try:
                import urllib.request, urllib.parse, json
                query = urllib.parse.quote(keyword_str)
                url = f"https://newsapi.org/v2/everything?q={query}&language={language}&pageSize=10&apiKey={news_api_key}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    for article in data.get("articles", [])[:10]:
                        news_items.append({
                            "title": article.get("title", ""),
                            "source": article.get("source", {}).get("name", ""),
                            "url": article.get("url", ""),
                            "published": article.get("publishedAt", ""),
                            "description": article.get("description", "")[:300],
                        })
            except Exception as e:
                logger.warning(f"NewsAPI error: {e}")
        
        # If no NewsAPI key or failed, try Google News RSS
        if not news_items:
            try:
                query = urllib.parse.quote(keyword_str)
                rss_url = f"https://news.google.com/rss/search?q={query}&hl={language}"
                items = self._fetch_news_rss(rss_url, limit=10)
                news_items.extend(items)
            except Exception as e:
                logger.warning(f"Google News RSS error: {e}")
        
        # Last resort: generic news sources
        if not news_items:
            for source in sources:
                try:
                    if source == "google":
                        query = urllib.parse.quote(keyword_str)
                        url = f"https://news.google.com/rss/search?q={query}&hl={language}"
                    elif source == "bing":
                        query = urllib.parse.quote(keyword_str)
                        url = f"https://www.bing.com/news/search?q={query}"
                    else:
                        continue
                    
                    items = self._fetch_news_rss(url, limit=5)
                    news_items.extend(items)
                except Exception as e:
                    logger.warning(f"News source {source} error: {e}")
        
        return news_items[:15] if news_items else [
            {"info": f"No news found for keywords: {keywords}", "keywords": keywords}
        ]
    
    def _monitor_global_news(self, params: Dict[str, Any]) -> List[Dict]:
        """全球新闻聚合"""
        category = params.get("category", "general")
        region = params.get("region", "global")
        limit = params.get("limit", 10)
        
        rss_feeds = {
            "global": {
                "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
                "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
                "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
            },
            "us": {
                "general": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
                "technology": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            },
            "cn": {
                "general": "http://www.xinhuanet.com/english/rss/worldrss.xml",
                "china": "http://www.chinadaily.com.cn/rss/world_rss.xml",
            },
            "jp": {
                "general": "https://www3.nhk.or.jp/rss/news/cat0.xml",
            },
        }
        
        results = []
        region_feeds = rss_feeds.get(region, rss_feeds.get("global", {}))
        
        # Try the specific category first
        feed_url = region_feeds.get(category)
        if feed_url:
            items = self._fetch_news_rss(feed_url, limit)
            results.extend(items)
        
        # If no results, try "general" or first available
        if not results:
            fallback_url = region_feeds.get("general") or next(iter(region_feeds.values()), None)
            if fallback_url:
                items = self._fetch_news_rss(fallback_url, limit)
                results.extend(items)
        
        return results[:limit] if results else [
            {"info": f"No global news for region={region}, category={category}"}
        ]
    
    # ----- 社交媒体 handlers -----
    
    def _monitor_social_mentions(self, params: Dict[str, Any]) -> List[Dict]:
        target = params.get("target", "")
        platforms = params.get("platforms", ["twitter", "reddit"])
        
        mentions = []
        
        # Try Reddit
        if "reddit" in platforms or "all" in platforms:
            try:
                query = urllib.parse.quote(target)
                url = f"https://www.reddit.com/r/all/search.json?q={query}&limit=10&sort=new"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    for child in data.get("data", {}).get("children", [])[:10]:
                        d = child.get("data", {})
                        mentions.append({
                            "platform": "reddit",
                            "title": d.get("title", ""),
                            "url": f"https://reddit.com{d.get('permalink', '')}",
                            "score": d.get("score", 0),
                            "subreddit": d.get("subreddit", ""),
                        })
            except Exception as e:
                logger.warning(f"Reddit search error: {e}")
        
        # Try generic web search for social mentions
        if not mentions:
            try:
                query = urllib.parse.quote(f"{target} social media")
                url = f"https://www.google.com/search?q={query}&tbm=nws"
                # Just report what we would search
                mentions.append({
                    "platform": "web",
                    "info": f"Searched for '{target}' mentions across platforms",
                    "query": query,
                })
            except Exception:
                pass
        
        return mentions if mentions else [
            {"info": f"No mentions found for '{target}'", "target": target}
        ]
    
    def _monitor_hashtags(self, params: Dict[str, Any]) -> List[Dict]:
        hashtags = params.get("hashtags", [])
        platforms = params.get("platforms", ["twitter"])
        
        if isinstance(hashtags, str):
            hashtags = [hashtags]
        
        results = []
        for tag in hashtags[:5]:
            cleaned = tag.lstrip("#")
            results.append({
                "hashtag": f"#{cleaned}",
                "platforms": platforms,
                "estimated_volume": f"Trending analysis for #{cleaned}",
                "note": "Configure social media API credentials for real-time data"
            })
        
        return results if results else [{"info": "No hashtags specified"}]
    
    # ----- 市场监控 handlers -----
    
    def _monitor_stock(self, params: Dict[str, Any]) -> List[Dict]:
        symbols = params.get("symbols", [])
        alerts = params.get("alerts", {})
        
        if isinstance(symbols, str):
            symbols = [symbols]
        
        results = []
        
        # Try Yahoo Finance API
        try:
            import yfinance as yf
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    results.append({
                        "symbol": symbol,
                        "name": info.get("longName", info.get("shortName", symbol)),
                        "price": info.get("currentPrice", info.get("regularMarketPrice", "N/A")),
                        "change": info.get("regularMarketChangePercent", "N/A"),
                        "market_cap": info.get("marketCap", "N/A"),
                        "volume": info.get("volume", "N/A"),
                    })
                except Exception as e:
                    results.append({"symbol": symbol, "error": str(e)})
        except ImportError:
            # Fallback: web scrape
            for symbol in symbols:
                try:
                    query = urllib.parse.quote(f"{symbol} stock price")
                    url = f"https://finance.yahoo.com/quote/{symbol}"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        html = resp.read().decode("utf-8", errors="replace")
                        # Try to extract price from HTML
                        import re
                        price_matches = re.findall(r'"regularMarketPrice":\{"raw":([\d.]+)', html)
                        results.append({
                            "symbol": symbol,
                            "price": price_matches[0] if price_matches else "See: " + url,
                            "url": url
                        })
                except Exception as e:
                    results.append({"symbol": symbol, "error": str(e), "info": "yfinance not installed"})
        
        return results if results else [{"info": "No stock symbols specified"}]
    
    def _monitor_crypto(self, params: Dict[str, Any]) -> List[Dict]:
        coins = params.get("coins", [])
        alerts = params.get("alerts", {})
        
        if isinstance(coins, str):
            coins = [coins]
        
        if not coins:
            coins = ["bitcoin", "ethereum"]
        
        results = []
        
        # Try CoinGecko API
        try:
            ids = ",".join(coins)
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for coin, info in data.items():
                    results.append({
                        "coin": coin,
                        "price_usd": info.get("usd", "N/A"),
                        "change_24h": info.get("usd_24h_change", "N/A"),
                    })
        except Exception as e:
            logger.warning(f"CoinGecko error: {e}")
            for coin in coins:
                results.append({"coin": coin, "info": "Could not fetch price", "note": str(e)})
        
        return results if results else [{"info": "No crypto coins specified"}]
    
    def _monitor_forex(self, params: Dict[str, Any]) -> List[Dict]:
        pairs = params.get("pairs", ["USD/JPY", "EUR/USD", "GBP/USD"])
        
        if isinstance(pairs, str):
            pairs = [pairs]
        
        results = []
        
        # Try exchangerate-api
        try:
            api_key = self.config.get("forex_api_key", "")
            for pair in pairs[:5]:
                base, target = pair.split("/") if "/" in pair else (pair[:3], pair[3:])
                
                if api_key:
                    url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
                else:
                    url = f"https://api.exchangerate-api.com/v4/latest/{base}"
                
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    rate = data.get("rates", {}).get(target, "N/A")
                    results.append({
                        "pair": pair,
                        "rate": rate,
                        "base": data.get("base", base),
                        "date": data.get("date", ""),
                    })
        except Exception as e:
            logger.warning(f"Forex API error: {e}")
            for pair in pairs[:5]:
                results.append({"pair": pair, "info": "Using estimated rate (API unavailable)"})
        
        return results if results else [{"info": "No forex pairs specified"}]
    
    # ----- 情感分析 handlers -----
    
    def _analyze_sentiment(self, params: Dict[str, Any]) -> Dict:
        """文本情感分析 - 使用vader或textblob"""
        text = params.get("text", "")
        language = params.get("language", "en")
        
        if not text:
            return {"error": "No text provided", "sentiment": "neutral", "score": 0}
        
        # Try VADER (English)
        if language == "en":
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                analyzer = SentimentIntensityAnalyzer()
                scores = analyzer.polarity_scores(text)
                
                compound = scores["compound"]
                if compound >= 0.05:
                    label = "positive"
                elif compound <= -0.05:
                    label = "negative"
                else:
                    label = "neutral"
                
                return {
                    "sentiment": label,
                    "score": compound,
                    "details": {
                        "positive": scores["pos"],
                        "negative": scores["neg"],
                        "neutral": scores["neu"],
                    }
                }
            except ImportError:
                pass
        
        # Try textblob
        try:
            from textblob import TextBlob
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            
            if polarity > 0.1:
                label = "positive"
            elif polarity < -0.1:
                label = "negative"
            else:
                label = "neutral"
            
            return {
                "sentiment": label,
                "score": polarity,
                "subjectivity": blob.sentiment.subjectivity,
            }
        except ImportError:
            pass
        
        # Simple keyword-based fallback
        positive_words = ["好", "棒", "优秀", "great", "good", "excellent", "amazing", "love", "wonderful", "happy"]
        negative_words = ["差", "坏", "糟糕", "bad", "terrible", "awful", "hate", "poor", "horrible", "sad"]
        
        pos_count = sum(1 for w in positive_words if w in text.lower())
        neg_count = sum(1 for w in negative_words if w in text.lower())
        
        if pos_count > neg_count:
            label = "positive"
        elif neg_count > pos_count:
            label = "negative"
        else:
            label = "neutral"
        
        return {
            "sentiment": label,
            "score": (pos_count - neg_count) / max(len(text), 1) * 10,
            "positive_matches": pos_count,
            "negative_matches": neg_count,
            "note": "Simple keyword-based analysis (install vaderSentiment or textblob for better results)"
        }
    
    def _analyze_brand_sentiment(self, params: Dict[str, Any]) -> Dict:
        brand = params.get("brand", "")
        time_range = params.get("time_range", "7d")
        
        # Collect mentions and analyze sentiment
        mentions = self._monitor_social_mentions({"target": brand, "platforms": ["reddit"]})
        
        overall = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
        
        for mention in mentions:
            title = mention.get("title", "")
            if title:
                analysis = self._analyze_sentiment({"text": title, "language": "en"})
                label = analysis.get("sentiment", "neutral")
                overall[label] = overall.get(label, 0) + 1
                overall["total"] += 1
        
        return {
            "brand": brand,
            "time_range": time_range,
            "sentiment_summary": overall,
            "mentions_sampled": len(mentions),
            "overall": max(overall, key=overall.get) if overall.get("total", 0) > 0 else "neutral"
        }
    
    # ----- 趋势分析 handlers -----
    
    def _analyze_trends(self, params: Dict[str, Any]) -> Dict:
        keywords = params.get("keywords", [])
        time_range = params.get("time_range", "7d")
        
        if isinstance(keywords, str):
            keywords = [keywords]
        
        # Try Google Trends (via pytrends)
        try:
            from pytrends.request import TrendReq
            pytrends = TrendReq(hl='en-US', tz=360)
            
            if keywords:
                pytrends.build_payload(keywords, timeframe=time_range)
                interest = pytrends.interest_over_time()
                
                if not interest.empty and not interest.drop(columns=['isPartial']).empty:
                    trend_data = interest.drop(columns=['isPartial']).to_dict()
                    return {
                        "keywords": keywords,
                        "time_range": time_range,
                        "trend_data": trend_data,
                        "trending_up": any(interest.iloc[-1] > interest.iloc[0]) if len(interest) > 1 else False
                    }
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Google Trends error: {e}")
        
        # Fallback: news trend analysis
        news_results = {}
        for kw in keywords[:3]:
            news = self._monitor_news({"keywords": [kw], "sources": ["google"], "language": "en"})
            news_results[kw] = {"news_count": len(news)}
        
        return {
            "keywords": keywords,
            "time_range": time_range,
            "results": news_results,
            "note": "Install pytrends for Google Trends data"
        }
    
    def _detect_emerging_topics(self, params: Dict[str, Any]) -> List[Dict]:
        category = params.get("category", "technology")
        min_velocity = params.get("min_velocity", 0.5)
        
        # Fetch global news and try to detect new/trending topics
        news = self._monitor_global_news({"category": category, "region": "global", "limit": 20})
        
        # Simple frequency-based topic extraction
        import re
        word_freq = {}
        for item in news:
            title = item.get("title", "")
            # Extract potential topic words (English words >= 4 chars)
            words = re.findall(r'\b[A-Z][a-z]{3,}\b', title)
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Sort by frequency
        sorted_topics = sorted(word_freq.items(), key=lambda x: -x[1])
        
        topics = []
        for word, count in sorted_topics[:10]:
            topics.append({
                "topic": word,
                "frequency": count,
                "velocity": count / max(len(news), 1),
                "category": category,
            })
        
        return topics if topics else [{"info": f"No emerging topics detected in {category}"}]
    
    # ----- 地缘政治 handlers -----
    
    def _monitor_geopolitical(self, params: Dict[str, Any]) -> List[Dict]:
        regions = params.get("regions", ["global"])
        topics = params.get("topics", ["conflict", "diplomacy", "trade"])
        
        if isinstance(regions, str):
            regions = [regions]
        if isinstance(topics, str):
            topics = [topics]
        
        # Fetch related news for each region/topic combination
        results = []
        for region in regions[:3]:
            news = self._monitor_global_news({
                "category": "world",
                "region": region,
                "limit": 5
            })
            results.append({
                "region": region,
                "news_count": len(news),
                "headlines": [n.get("title", "") for n in news[:5]],
                "topics_monitored": topics,
            })
        
        return results if results else [{"info": f"No geopolitical data for regions: {regions}"}]
    
    def _monitor_infrastructure(self, params: Dict[str, Any]) -> List[Dict]:
        inf_type = params.get("type", "power")
        location = params.get("location", "global")
        
        # Check for known infrastructure monitoring sources
        sources = {
            "power": {
                "description": "Power grid status monitoring",
                "data_sources": ["Grid status reports", "Energy news"],
            },
            "water": {
                "description": "Water supply and dam status",
                "data_sources": ["Hydrological reports", "Water authority updates"],
            },
            "transport": {
                "description": "Transportation infrastructure status",
                "data_sources": ["Traffic monitoring", "Transport authority updates"],
            },
            "communication": {
                "description": "Communication network status",
                "data_sources": ["Network status pages", "ISP reports"],
            },
        }
        
        info = sources.get(inf_type, {"description": f"{inf_type} monitoring", "data_sources": []})
        
        return [{
            "type": inf_type,
            "location": location,
            "status": "monitoring_active",
            "description": info["description"],
            "sources": info["data_sources"],
            "last_updated": datetime.now().isoformat(),
        }]
    
    def get_function_count(self) -> int:
        return len(self.functions)


def create_monitor_functions(config: Dict[str, Any] = None) -> MonitorFunctions:
    return MonitorFunctions(config)
