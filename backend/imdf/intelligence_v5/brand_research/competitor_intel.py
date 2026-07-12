"""智影 V5 — 4 大广告研究技能 (Gooseworks 模式)"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .ad_sources import AdSource, CompetitorAd

logger = logging.getLogger(__name__)


# ===== 1. Trending Hook Spotter =====
class HookCategory(str, Enum):
    """钩子类型 — Gooseworks 模式"""
    FEAR_LOSS = "fear_loss"            # 恐惧损失型
    RESULT_PROMISE = "result_promise"  # 结果承诺型
    QUESTION = "question"              # 问题引导型
    SOCIAL_PROOF = "social_proof"      # 社会证明型
    URGENCY = "urgency"                # 紧迫感
    AUTHORITY = "authority"            # 权威背书
    CURIOSITY = "curiosity"            # 好奇心
    FREE = "free"                      # 免费
    NOVELTY = "novelty"                # 新奇
    STORY = "story"                    # 故事


@dataclass
class TrendingHook:
    """趋势钩子"""

    text: str
    category: HookCategory = HookCategory.RESULT_PROMISE
    hook_id: str = field(default_factory=lambda: f"th-{uuid.uuid4().hex[:8]}")
    source: str = ""  # "x" | "reddit"
    source_url: str = ""
    engagement: int = 0
    sentiment: float = 0.0  # -1 to 1
    language: str = "en"
    timestamp: float = 0.0
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hook_id": self.hook_id,
            "text": self.text,
            "category": self.category.value,
            "source": self.source,
            "source_url": self.source_url,
            "engagement": self.engagement,
            "sentiment": self.sentiment,
            "language": self.language,
            "keywords": self.keywords,
            "timestamp": self.timestamp,
        }


class TrendingHookSpotter:
    """趋势钩子发现 — 监控 X/Reddit 上的实时讨论,把热门讨论自动映射为广告钩子"""

    HOOK_PATTERNS: Dict[HookCategory, List[str]] = {
        HookCategory.FEAR_LOSS: ["怕错过", "失去", "错过", "最后", "截止", "亏", "后悔", "担心", "焦虑", "错过再等一年"],
        HookCategory.RESULT_PROMISE: ["30天", "21天", "7天", "立刻见效", "快速", "3步", "变美", "瘦身", "致富", "搞定"],
        HookCategory.QUESTION: ["你知道吗", "为什么", "怎么", "如何", "是什么", "为什么这么", "怎么做到的", "你试过吗"],
        HookCategory.SOCIAL_PROOF: ["万人", "百万", "10万+", "热销", "推荐", "首选", "第一", "Top 1", "明星", "专家"],
        HookCategory.URGENCY: ["限时", "今天", "马上", "立刻", "截止", "倒计时", "仅剩", "最后", "急", "即将"],
        HookCategory.AUTHORITY: ["哈佛", "斯坦福", "MIT", "专家", "教授", "医生", "博士", "央视", "获奖", "认证"],
        HookCategory.CURIOSITY: ["揭秘", "真相", "为什么", "内幕", "秘密", "居然", "竟", "原来", "惊人发现", "万万没想到"],
        HookCategory.FREE: ["免费", "0元", "不花钱", "白送", "送", "免单", "试用", "体验", "限时免费", "免费领"],
        HookCategory.NOVELTY: ["新品", "首发", "全新", "首发", "上市", "黑科技", "新", "首创", "首发", "首款"],
        HookCategory.STORY: ["我曾经", "我朋友", "我同事", "我家人", "故事", "经历", "那年", "曾经", "回忆", "从前"],
    }

    def __init__(self):
        self.hooks: List[TrendingHook] = []

    def spot_from_posts(
        self,
        posts: List[Dict[str, Any]],
        min_engagement: int = 100,
    ) -> List[TrendingHook]:
        """从帖子列表中识别钩子"""
        results: List[TrendingHook] = []
        for post in posts:
            text = post.get("text", "") or post.get("body", "")
            if not text or len(text) < 10:
                continue
            engagement = post.get("engagement", 0) or post.get("impressions", 0) or 0
            if engagement < min_engagement:
                continue
            # 匹配钩子
            for category, patterns in self.HOOK_PATTERNS.items():
                for pat in patterns:
                    if pat.lower() in text.lower() or pat in text:
                        hook = TrendingHook(
                            text=text[:300],
                            category=category,
                            source=post.get("source", "unknown"),
                            source_url=post.get("url", ""),
                            engagement=engagement,
                            language=post.get("language", "en"),
                            timestamp=time.time(),
                            keywords=self._extract_keywords(text),
                            metadata={"matched_pattern": pat},
                        )
                        results.append(hook)
                        break  # 一条 post 只匹配一个钩子
        # 按 engagement 排序
        results.sort(key=lambda h: h.engagement, reverse=True)
        self.hooks.extend(results)
        return results

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单: 找长度 2-6 的中文/英文词
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,5}", text)
        en_words = re.findall(r"\b[A-Za-z]{3,15}\b", text)
        return cn_words[:5] + en_words[:5]

    def get_stats(self) -> Dict[str, Any]:
        by_cat: Dict[str, int] = {}
        for h in self.hooks:
            by_cat[h.category.value] = by_cat.get(h.category.value, 0) + 1
        return {
            "total_hooks": len(self.hooks),
            "by_category": by_cat,
            "top_engagement": max((h.engagement for h in self.hooks), default=0),
        }


# ===== 2. Competitor Ad Intelligence =====
@dataclass
class AdCluster:
    """广告聚类"""

    cluster_id: str = field(default_factory=lambda: f"cl-{uuid.uuid4().hex[:8]}")
    name: str = ""
    hook_category: HookCategory = HookCategory.RESULT_PROMISE
    ads: List[CompetitorAd] = field(default_factory=list)
    total_engagement: int = 0
    format_distribution: Dict[str, int] = field(default_factory=dict)
    cta_distribution: Dict[str, int] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "category": self.hook_category.value,
            "ad_count": len(self.ads),
            "total_engagement": self.total_engagement,
            "format_distribution": self.format_distribution,
            "cta_distribution": self.cta_distribution,
            "summary": self.summary,
        }


class CompetitorAdIntelligence:
    """竞品广告情报 — 从 Meta Ad Library + Google Ads Transparency 抓取所有活跃广告, 自动聚类钩子类型"""

    def __init__(self):
        from .ad_sources import MetaAdLibrary, GoogleAdsTransparency
        self.meta = MetaAdLibrary()
        self.google = GoogleAdsTransparency()
        self.spotter = TrendingHookSpotter()

    async def analyze_competitor(
        self,
        advertiser: str,
        platforms: Optional[List[str]] = None,
        max_per_platform: int = 30,
    ) -> Dict[str, Any]:
        """分析竞品"""
        platforms = platforms or ["meta", "google"]
        all_ads: List[CompetitorAd] = []
        # 拉取多平台
        tasks = []
        if "meta" in platforms:
            tasks.append(self.meta.fetch_ads(advertiser, max_per_platform))
        if "google" in platforms:
            tasks.append(self.google.fetch_ads(advertiser, max_per_platform))
        results = await asyncio.gather(*tasks)
        for ads in results:
            all_ads.extend(ads)
        # 聚类
        clusters = self._cluster_ads(all_ads)
        # 格式/CTA 分布
        format_dist = Counter(a.format for a in all_ads)
        cta_dist = Counter(a.cta for a in all_ads)
        # 主力钩子
        top_hooks = sorted(
            clusters,
            key=lambda c: c.total_engagement,
            reverse=True,
        )[:5]
        # 空白钩子
        existing_categories = {c.hook_category for c in clusters}
        all_categories = set(HookCategory)
        gaps = all_categories - existing_categories
        # Counter-Play 建议
        counter_play = self._generate_counter_play(clusters, gaps)
        return {
            "advertiser": advertiser,
            "total_ads": len(all_ads),
            "platforms": platforms,
            "clusters": [c.to_dict() for c in clusters],
            "format_distribution": dict(format_dist),
            "cta_distribution": dict(cta_dist),
            "top_hooks": [c.to_dict() for c in top_hooks],
            "gaps": [g.value for g in gaps],
            "counter_play": counter_play,
        }

    def _cluster_ads(self, ads: List[CompetitorAd]) -> List[AdCluster]:
        """按钩子类型聚类"""
        # 把 ads 转 dict 给 spotter 处理
        posts = [
            {
                "text": f"{a.headline} {a.body}",
                "engagement": a.impressions,
                "source": a.platform,
                "url": a.landing_url,
                "language": a.language,
            }
            for a in ads
        ]
        hooks = self.spotter.spot_from_posts(posts, min_engagement=0)
        # 按 category 分组
        groups: Dict[HookCategory, List[TrendingHook]] = {}
        for h in hooks:
            groups.setdefault(h.category, []).append(h)
        # 构造 AdCluster
        clusters: List[AdCluster] = []
        for cat, cat_hooks in groups.items():
            ad_ids = set()
            ads_in_cluster: List[CompetitorAd] = []
            for h in cat_hooks:
                # 通过 matched_pattern 反查 (简化: 给所有 ads 都加, 因为是按文本匹配的)
                pass
            # 简化: 取 ad 的 hook_category 通过文本匹配判断
            for ad in ads:
                combined = (ad.headline + " " + ad.body).lower()
                for pat in self.spotter.HOOK_PATTERNS.get(cat, []):
                    if pat.lower() in combined:
                        ads_in_cluster.append(ad)
                        break
            if not ads_in_cluster:
                continue
            cluster = AdCluster(
                name=f"{cat.value} ({len(ads_in_cluster)} ads)",
                hook_category=cat,
                ads=ads_in_cluster,
                total_engagement=sum(a.impressions for a in ads_in_cluster),
                format_distribution=dict(Counter(a.format for a in ads_in_cluster)),
                cta_distribution=dict(Counter(a.cta for a in ads_in_cluster)),
                summary=f"竞品在 {cat.value} 类型投放 {len(ads_in_cluster)} 条, 总曝光 {sum(a.impressions for a in ads_in_cluster):,}",
            )
            clusters.append(cluster)
        return clusters

    def _generate_counter_play(self, clusters: List[AdCluster], gaps: set) -> List[str]:
        """生成反制打法"""
        suggestions: List[str] = []
        if clusters:
            top = max(clusters, key=lambda c: c.total_engagement)
            suggestions.append(
                f"主力钩子: {top.hook_category.value} ({top.total_engagement:,} 曝光), "
                f"建议: 1) 不要同质化竞争 2) 找差异化角度 3) 测试更长尾钩子"
            )
        if gaps:
            for g in list(gaps)[:3]:
                suggestions.append(f"空白钩子: {g.value}, 建议: 抢先占据这个钩子类型")
        # 格式建议
        all_formats = Counter()
        for c in clusters:
            all_formats.update(c.format_distribution)
        top_format = all_formats.most_common(1)[0][0] if all_formats else None
        if top_format:
            suggestions.append(f"竞品主力格式: {top_format}, 建议: 测试 { 'video' if top_format == 'image' else 'image' } 差异化")
        return suggestions

    def get_stats(self) -> Dict[str, Any]:
        return {
            "spotter": self.spotter.get_stats(),
        }


# ===== 3. Ad Angle Miner =====
@dataclass
class ConversionAngle:
    """转化角度"""

    text: str
    angle_id: str = field(default_factory=lambda: f"ca-{uuid.uuid4().hex[:8]}")
    source: MiningSource = None
    frequency: int = 0
    sentiment: float = 0.0
    language: str = "en"
    related_ad_format: str = ""  # 适用广告格式
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.source is None:
            from .ad_sources import RedditMonitor
            self.source = MiningSource(RedditMonitor(), "reddit")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "angle_id": self.angle_id,
            "text": self.text,
            "source": self.source.source_name if self.source else "",
            "frequency": self.frequency,
            "sentiment": self.sentiment,
            "language": self.language,
            "related_ad_format": self.related_ad_format,
            "keywords": self.keywords,
        }


class MiningSource:
    """挖掘源"""

    def __init__(self, source: Any, name: str):
        self.source = source
        self.source_name = name


class AdAngleMiner:
    """广告角度挖掘 — 从产品评论/Reddit/竞品评论区提取真正驱动下单的语言"""

    ANGLE_PATTERNS = {
        "性价比": ["便宜", "实惠", "划算", "性价比", "值", "贵", "便宜", "cost-effective", "affordable", "worth", "value"],
        "质量": ["质量好", "耐用", "持久", "做工", "质感", "quality", "durable", "well-made"],
        "效果": ["见效", "有效", "管用", "效果", "真的", "effective", "works", "results"],
        "服务": ["客服", "服务", "态度", "退换", "回复", "service", "support", "responsive"],
        "外观": ["好看", "漂亮", "颜值", "设计", "look", "design", "beautiful", "stylish"],
        "功能": ["功能", "齐全", "齐全", "强大", "feature", "powerful", "versatile"],
        "口碑": ["推荐", "朋友", "同事", "家人", "都说", "推荐", "recommended", "popular"],
    }

    def __init__(self):
        self.angles: List[ConversionAngle] = []

    def mine_from_texts(
        self,
        texts: List[Dict[str, Any]],  # [{text, source, language, ...}]
        min_freq: int = 1,
    ) -> List[ConversionAngle]:
        """从文本集合挖掘角度"""
        # 按角度分类
        angle_counter: Counter = Counter()
        angle_texts: Dict[str, List[str]] = {}
        for item in texts:
            text = item.get("text", "")
            if not text:
                continue
            for angle_name, patterns in self.ANGLE_PATTERNS.items():
                for pat in patterns:
                    if pat.lower() in text.lower() or pat in text:
                        angle_counter[angle_name] += 1
                        angle_texts.setdefault(angle_name, []).append(text[:200])
                        break
        # 构造
        results: List[ConversionAngle] = []
        for angle_name, freq in angle_counter.most_common():
            if freq < min_freq:
                continue
            sample_texts = angle_texts.get(angle_name, [])
            best_text = sample_texts[0] if sample_texts else angle_name
            # 推断格式
            related_format = "video" if angle_name in ("效果", "口碑") else "image"
            results.append(
                ConversionAngle(
                    text=best_text,
                    source=MiningSource(None, item.get("source", "review")),
                    frequency=freq,
                    language=item.get("language", "en") if texts else "en",
                    related_ad_format=related_format,
                    keywords=[pat for pat in self.ANGLE_PATTERNS[angle_name] if pat in best_text][:5],
                    metadata={"all_samples": sample_texts[:5]},
                )
            )
        self.angles.extend(results)
        return results

    def get_stats(self) -> Dict[str, Any]:
        by_freq: Dict[str, int] = {}
        for a in self.angles:
            by_freq[a.related_ad_format] = by_freq.get(a.related_ad_format, 0) + a.frequency
        return {
            "total_angles": len(self.angles),
            "by_format": by_freq,
        }


# ===== 4. Brand Researcher =====
@dataclass
class BrandProfile:
    """品牌画像"""

    brand_name: str
    industry: str = ""
    positioning: str = ""  # 品牌定位
    icp: str = ""          # 理想客户画像
    pain_points: List[str] = field(default_factory=list)
    benefits: List[str] = field(default_factory=list)
    visual_style: str = ""  # 视觉风格
    tone_of_voice: str = ""  # 语气
    competitors: List[str] = field(default_factory=list)
    hooks_used: List[str] = field(default_factory=list)
    color_palette: List[str] = field(default_factory=list)
    logo_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrandContext:
    """品牌上下文包 — Gooseworks 关键设计"""

    brand: BrandProfile
    context_id: str = field(default_factory=lambda: f"bc-{uuid.uuid4().hex[:8]}")
    related_ads: List[CompetitorAd] = field(default_factory=list)
    related_angles: List[ConversionAngle] = field(default_factory=list)
    related_hooks: List[TrendingHook] = field(default_factory=list)
    summary: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_id": self.context_id,
            "brand": {
                "name": self.brand.brand_name,
                "industry": self.brand.industry,
                "positioning": self.brand.positioning,
                "icp": self.brand.icp,
                "pain_points": self.brand.pain_points,
                "benefits": self.brand.benefits,
                "visual_style": self.brand.visual_style,
                "tone_of_voice": self.brand.tone_of_voice,
                "competitors": self.brand.competitors,
                "hooks_used": self.brand.hooks_used,
            },
            "related_ads_count": len(self.related_ads),
            "related_angles_count": len(self.related_angles),
            "related_hooks_count": len(self.related_hooks),
            "summary": self.summary,
            "created_at": self.created_at,
        }


class BrandResearcher:
    """品牌研究 — 把品牌定位/ICP/痛点语言/视觉风格打包成可复用文件"""

    def __init__(self):
        self.contexts: Dict[str, BrandContext] = {}
        self.competitor_intel = CompetitorAdIntelligence()
        self.angle_miner = AdAngleMiner()
        self.hook_spotter = TrendingHookSpotter()

    def create_profile(
        self,
        brand_name: str,
        industry: str = "",
        positioning: str = "",
        icp: str = "",
        pain_points: Optional[List[str]] = None,
        benefits: Optional[List[str]] = None,
        visual_style: str = "",
        tone_of_voice: str = "",
        competitors: Optional[List[str]] = None,
        color_palette: Optional[List[str]] = None,
    ) -> BrandProfile:
        return BrandProfile(
            brand_name=brand_name,
            industry=industry,
            positioning=positioning,
            icp=icp,
            pain_points=pain_points or [],
            benefits=benefits or [],
            visual_style=visual_style,
            tone_of_voice=tone_of_voice,
            competitors=competitors or [],
            color_palette=color_palette or [],
        )

    async def build_context(
        self,
        profile: BrandProfile,
        fetch_competitor_ads: bool = True,
        mine_angles: bool = True,
        spot_hooks: bool = True,
    ) -> BrandContext:
        """构建品牌上下文包 — 整合 4 技能"""
        ctx = BrandContext(brand=profile, created_at=time.time(), updated_at=time.time())
        # 1. 竞品广告
        if fetch_competitor_ads and profile.competitors:
            tasks = [self.competitor_intel.analyze_competitor(c) for c in profile.competitors[:3]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    for cl in r.get("clusters", []):
                        for ad in cl.get("ads", []):
                            ctx.related_ads.append(ad)
        # 2. 角度挖掘
        if mine_angles:
            sample_texts = [
                {"text": f"{profile.brand_name} {pp}", "source": "review", "language": "zh-CN"}
                for pp in profile.pain_points
            ] + [
                {"text": f"{profile.brand_name} {b}", "source": "review", "language": "zh-CN"}
                for b in profile.benefits
            ]
            angles = self.angle_miner.mine_from_texts(sample_texts, min_freq=1)
            ctx.related_angles = angles
        # 3. 趋势钩子
        if spot_hooks:
            posts = [
                {"text": f"{profile.brand_name} {pp}", "engagement": 100, "source": "review", "language": "zh-CN"}
                for pp in profile.pain_points
            ]
            hooks = self.hook_spotter.spot_from_posts(posts, min_engagement=0)
            ctx.related_hooks = hooks
        # 4. summary
        ctx.summary = (
            f"{profile.brand_name} ({profile.industry}) 品牌上下文包: "
            f"竞品广告 {len(ctx.related_ads)} 条, 角度 {len(ctx.related_angles)} 个, 钩子 {len(ctx.related_hooks)} 个"
        )
        ctx.updated_at = time.time()
        self.contexts[ctx.context_id] = ctx
        return ctx

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_contexts": len(self.contexts),
            "competitor_intel": self.competitor_intel.get_stats(),
            "angle_miner": self.angle_miner.get_stats(),
        }
