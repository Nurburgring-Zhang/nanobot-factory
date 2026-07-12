"""智影 V5 — Brand Research 子包: 4 个广告研究技能 (Gooseworks)

迁移自 Shiv Sakhuja 的 Meta Ad Researcher 技能包:
1. trending-ad-hook-spotter: 趋势钩子发现 (X/Reddit)
2. competitor-ad-intelligence: 竞品广告情报 (Meta Ad Library + Google Ads Transparency)
3. ad-angle-miner: 转化角度挖掘 (评论分析)
4. brand-research: 品牌研究上下文包
"""
from .ad_sources import AdSource, MetaAdLibrary, GoogleAdsTransparency, XMonitor, RedditMonitor
from .competitor_intel import (
    TrendingHookSpotter,
    HookCategory,
    TrendingHook,
    AdCluster,
    CompetitorAdIntelligence,
    CompetitorAd,
    ConversionAngle,
    MiningSource,
    AdAngleMiner,
    BrandProfile,
    BrandContext,
    BrandResearcher,
)

__all__ = [
    "AdSource",
    "MetaAdLibrary",
    "GoogleAdsTransparency",
    "XMonitor",
    "RedditMonitor",
    "TrendingHookSpotter",
    "HookCategory",
    "TrendingHook",
    "CompetitorAdIntelligence",
    "CompetitorAd",
    "AdCluster",
    "AdAngleMiner",
    "ConversionAngle",
    "MiningSource",
    "BrandResearcher",
    "BrandProfile",
    "BrandContext",
]
