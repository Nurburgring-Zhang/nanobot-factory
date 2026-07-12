"""V5 第32章 — Agent Reach 26 渠道 channel 实现.

P19-B3 首批 (14): web / twitter / youtube / bilibili / reddit / xiaohongshu /
                   github / rss / exa_search / linkedin / instagram / wechat /
                   douyin / zhihu
P22-P2a 新增 12 P2: feedly / digg / pinterest / vimeo / delicious /
                    stumbleupon / tumblr / pocket / instapaper / medium /
                    substack / hackernews
"""
from imdf.intelligence.agent_reach.channels.web import JinaReader
from imdf.intelligence.agent_reach.channels.twitter import TwitterAPI
from imdf.intelligence.agent_reach.channels.youtube import YouTubeDL
from imdf.intelligence.agent_reach.channels.bilibili import BilibiliDL
from imdf.intelligence.agent_reach.channels.reddit import RedditAPI
from imdf.intelligence.agent_reach.channels.xiaohongshu import RedFox
from imdf.intelligence.agent_reach.channels.github import GitHubAPI
from imdf.intelligence.agent_reach.channels.rss import FeedParser
from imdf.intelligence.agent_reach.channels.exa_search import ExaSearch
from imdf.intelligence.agent_reach.channels.linkedin import LinkedInMCP
from imdf.intelligence.agent_reach.channels.instagram import Instaloader
from imdf.intelligence.agent_reach.channels.wechat import WeChatMCP
from imdf.intelligence.agent_reach.channels.douyin import DouyinAPI
from imdf.intelligence.agent_reach.channels.zhihu import ZhihuAPI
# P22-P2a: 12 new P2 channels
from imdf.intelligence.agent_reach.channels.feedly import FeedlyAPI
from imdf.intelligence.agent_reach.channels.digg import DiggAPI
from imdf.intelligence.agent_reach.channels.pinterest import PinterestAPI
from imdf.intelligence.agent_reach.channels.vimeo import VimeoAPI
from imdf.intelligence.agent_reach.channels.delicious import DeliciousAPI
from imdf.intelligence.agent_reach.channels.stumbleupon import StumbleuponAPI
from imdf.intelligence.agent_reach.channels.tumblr import TumblrAPI
from imdf.intelligence.agent_reach.channels.pocket import PocketAPI
from imdf.intelligence.agent_reach.channels.instapaper import InstapaperAPI
from imdf.intelligence.agent_reach.channels.medium import MediumAPI
from imdf.intelligence.agent_reach.channels.substack import SubstackAPI
from imdf.intelligence.agent_reach.channels.hackernews import HackernewsAPI

__all__ = [
    # P19-B3 首批 14
    "JinaReader",
    "TwitterAPI",
    "YouTubeDL",
    "BilibiliDL",
    "RedditAPI",
    "RedFox",
    "GitHubAPI",
    "FeedParser",
    "ExaSearch",
    "LinkedInMCP",
    "Instaloader",
    "WeChatMCP",
    "DouyinAPI",
    "ZhihuAPI",
    # P22-P2a 新增 12 P2
    "FeedlyAPI",
    "DiggAPI",
    "PinterestAPI",
    "VimeoAPI",
    "DeliciousAPI",
    "StumbleuponAPI",
    "TumblrAPI",
    "PocketAPI",
    "InstapaperAPI",
    "MediumAPI",
    "SubstackAPI",
    "HackernewsAPI",
]
