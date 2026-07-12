"""V5 第31章 — RedFox Skill 集合.

4 个 Skill 函数(模块级函数,可被 imdf/skills/registry.py 注册):
  * publish_to_all(content, only=None)
        — fan out to all 11 platforms (or subset)
        — 返回 Dict[PlatformId, PublishResult],失败隔离
  * schedule_publish(content, schedule_time, target_platforms=None)
        — 把 content + schedule_time 加入队列; 实际触发由 worker 拉取
        — 默认立即执行 (schedule_time <= now),否则 enqueue
  * fetch_cross_platform_metrics(post_id, platforms=None, title="")
        — 聚合多平台指标 → CrossPlatformMetrics (with total aggregation)
  * generate_platform_variants(base_content, platforms=None, llm=None)
        — 用 LLM 把同一内容改写成各平台风格 (规则 fallback when no LLM)

调用方示例:
    from backend.imdf.creative.redfox.skills import publish_to_all
    results = await publish_to_all(content)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

from ..registry import PLATFORMS, RedFoxClient, get_platform
from ..schemas import (
    ContentItem,
    CrossPlatformMetrics,
    PlatformId,
    PlatformVariant,
    PublishResult,
    ScheduledPublish,
)

logger = logging.getLogger(__name__)


# ── 进程内调度队列 (简化实现 — 生产环境用 APScheduler / Redis) ────────────
_SCHEDULE_QUEUE: List[ScheduledPublish] = []


def _enqueue(item: ScheduledPublish) -> None:
    _SCHEDULE_QUEUE.append(item)


def _pop_due(now: int) -> List[ScheduledPublish]:
    """弹出所有 schedule_time <= now 的调度项."""
    due: List[ScheduledPublish] = []
    remaining: List[ScheduledPublish] = []
    for it in _SCHEDULE_QUEUE:
        if it.schedule_time <= now:
            due.append(it)
        else:
            remaining.append(it)
    _SCHEDULE_QUEUE[:] = remaining
    return due


def list_scheduled(include_done: bool = False) -> List[ScheduledPublish]:
    """查看调度队列 — 用于调试/UI."""
    if include_done:
        return list(_SCHEDULE_QUEUE)
    return [it for it in _SCHEDULE_QUEUE if it.status == "pending"]


# ── Skill 1: publish_to_all ────────────────────────────────────────────────
async def publish_to_all(
    content: ContentItem,
    only: Optional[List[PlatformId]] = None,
) -> Dict[PlatformId, PublishResult]:
    """Fan out content to all 11 platforms (or subset).

    默认对 11 平台全部发布 — placeholder 平台返回 NOT_IMPLEMENTED。
    """
    client = RedFoxClient(platforms=PLATFORMS)
    return await client.publish_to_all(content, only=only)


# ── Skill 2: schedule_publish ──────────────────────────────────────────────
async def schedule_publish(
    content: ContentItem,
    schedule_time: int,
    target_platforms: Optional[List[PlatformId]] = None,
) -> ScheduledPublish:
    """把发布任务加入调度队列 — 立即执行或按 schedule_time.

    Args:
      content: 待发布内容
      schedule_time: unix timestamp,0/过去时间 = 立即执行
      target_platforms: None=全部 11 平台

    Returns:
      ScheduledPublish(status="done"|"pending", result populated if executed)
    """
    targets = target_platforms or list(PLATFORMS.keys())
    item = ScheduledPublish(
        content=content,
        target_platforms=targets,
        schedule_time=int(schedule_time),
        status="pending",
    )
    now = int(time.time())
    if item.schedule_time <= now:
        # 立即执行
        client = RedFoxClient(platforms=PLATFORMS)
        results = await client.publish_to_all(content, only=targets)
        item.status = "done"
        item.result = {pid: r for pid, r in results.items()}
    else:
        _enqueue(item)
    return item


async def run_due_scheduled(now: Optional[int] = None) -> List[ScheduledPublish]:
    """worker 钩子 — 拉取并执行所有 due 任务. 测试/Worker 入口使用."""
    ts = now if now is not None else int(time.time())
    due = _pop_due(ts)
    executed: List[ScheduledPublish] = []
    for item in due:
        client = RedFoxClient(platforms=PLATFORMS)
        results = await client.publish_to_all(item.content, only=item.target_platforms)
        item.status = "done"
        item.result = {pid: r for pid, r in results.items()}
        executed.append(item)
    return executed


# ── Skill 3: fetch_cross_platform_metrics ─────────────────────────────────
async def fetch_cross_platform_metrics(
    post_id: str,
    platforms: Optional[List[PlatformId]] = None,
    title: str = "",
) -> CrossPlatformMetrics:
    """聚合多平台指标 — 含 total 自动求和."""
    client = RedFoxClient(platforms=PLATFORMS)
    return await client.fetch_cross_platform_metrics(
        post_id, platforms=platforms, title=title,
    )


# ── Skill 4: generate_platform_variants ───────────────────────────────────
# ── 平台改写规则 (LLM fallback 用) ─────────────────────────────────────────
_PLATFORM_RULES: Dict[PlatformId, Dict[str, Any]] = {
    PlatformId.WECHAT_MP: {
        "max_title": 64, "max_body": 20000,
        "tone": "正式深度", "tag_prefix": "#",
        "tag_count": 0, "emoji": "low",
    },
    PlatformId.WEIBO: {
        "max_title": 0, "max_body": 2000,
        "tone": "轻松短句", "tag_prefix": "#",
        "tag_count": 5, "emoji": "high",
    },
    PlatformId.DOUYIN: {
        "max_title": 0, "max_body": 2200,
        "tone": "口语钩子", "tag_prefix": "#",
        "tag_count": 5, "emoji": "mid",
    },
    PlatformId.XIAOHONGSHU: {
        "max_title": 20, "max_body": 1000,
        "tone": "种草安利", "tag_prefix": "#",
        "tag_count": 10, "emoji": "high",
    },
    PlatformId.BILIBILI: {
        "max_title": 80, "max_body": 2000,
        "tone": "梗向互动", "tag_prefix": "#",
        "tag_count": 10, "emoji": "mid",
    },
    # placeholder 平台也支持 LLM 改写规则
    PlatformId.KUAISHOU: {
        "max_title": 0, "max_body": 500,
        "tone": "老铁互动", "tag_prefix": "#",
        "tag_count": 3, "emoji": "high",
    },
    PlatformId.ZHIHU: {
        "max_title": 50, "max_body": 5000,
        "tone": "理性分析", "tag_prefix": "#",
        "tag_count": 5, "emoji": "low",
    },
    PlatformId.TOUTIAO: {
        "max_title": 30, "max_body": 1000,
        "tone": "资讯标题党", "tag_prefix": "#",
        "tag_count": 5, "emoji": "low",
    },
    PlatformId.BAIJIAHAO: {
        "max_title": 30, "max_body": 3000,
        "tone": "百度SEO", "tag_prefix": "#",
        "tag_count": 5, "emoji": "low",
    },
    PlatformId.QIEHAO: {
        "max_title": 0, "max_body": 150,
        "tone": "生活分享", "tag_prefix": "",
        "tag_count": 0, "emoji": "mid",
    },
    PlatformId.SHIPINHAO: {
        "max_title": 14, "max_body": 1000,
        "tone": "短视频文案", "tag_prefix": "#",
        "tag_count": 3, "emoji": "mid",
    },
}


def _truncate(s: str, n: int) -> str:
    if n <= 0 or len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def _adapt_with_rules(
    base: ContentItem, pid: PlatformId,
) -> PlatformVariant:
    """规则式 fallback — 不调 LLM,生成 deterministic 平台变体."""
    rule = _PLATFORM_RULES.get(pid, {})
    tone = str(rule.get("tone", "通用"))
    title = _truncate(base.title, int(rule.get("max_title", 50)))
    body = _truncate(base.body, int(rule.get("max_body", 2000)))
    tag_n = int(rule.get("tag_count", 3))
    tag_prefix = str(rule.get("tag_prefix", "#"))
    tags = base.tags[:tag_n]
    if tag_prefix and tags and not tags[0].startswith(tag_prefix):
        tags = [f"{tag_prefix}{t}" if not t.startswith(tag_prefix) else t for t in tags]
    return PlatformVariant(
        platform=pid,
        title=title,
        body=body,
        tags=tags,
        notes=f"rule-based fallback, tone={tone}",
    )


async def _call_llm_for_variant(
    llm: Callable[..., str],
    base: ContentItem,
    pid: PlatformId,
    rule: Dict[str, Any],
) -> Optional[PlatformVariant]:
    """调用 LLM 改写 — 失败时回退到规则式."""
    try:
        prompt = (
            f"把以下自媒体内容改写到平台 {pid.value} 风格:\n"
            f"标题字数 ≤ {rule.get('max_title', 50)}\n"
            f"正文字数 ≤ {rule.get('max_body', 2000)}\n"
            f"语气: {rule.get('tone', '通用')}\n"
            f"标签数: {rule.get('tag_count', 3)} (前缀 {rule.get('tag_prefix', '#')})\n\n"
            f"原标题: {base.title}\n原正文: {base.body}\n"
            f"原标签: {','.join(base.tags)}\n\n"
            f"输出 JSON: {{\"title\": \"...\", \"body\": \"...\", \"tags\": [\"...\"]}}"
        )
        raw = llm(prompt)
        import json
        # 容忍 ```json ... ``` 包裹
        raw_clean = raw.strip().strip("`").lstrip("json").strip()
        data = json.loads(raw_clean)
        return PlatformVariant(
            platform=pid,
            title=str(data.get("title", ""))[: int(rule.get("max_title", 50)) or 500],
            body=str(data.get("body", ""))[: int(rule.get("max_body", 2000)) or 20000],
            tags=[str(t) for t in data.get("tags", [])][: int(rule.get("tag_count", 3)) or 10],
            notes=f"LLM-adapted, tone={rule.get('tone')}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM adapt for %s failed: %s — falling back", pid.value, exc)
        return _adapt_with_rules(base, pid)


async def generate_platform_variants(
    base_content: ContentItem,
    platforms: Optional[List[PlatformId]] = None,
    llm: Optional[Callable[..., str]] = None,
) -> Dict[PlatformId, PlatformVariant]:
    """为每个目标平台生成改写变体 — LLM 优先,规则 fallback."""
    targets = platforms if platforms is not None else list(PLATFORMS.keys())
    sem = asyncio.Semaphore(5)

    async def _one(pid: PlatformId) -> tuple[PlatformId, PlatformVariant]:
        rule = _PLATFORM_RULES.get(pid, {})
        async with sem:
            if llm is None:
                return pid, _adapt_with_rules(base_content, pid)
            return pid, await _call_llm_for_variant(llm, base_content, pid, rule)

    results = await asyncio.gather(*(_one(pid) for pid in targets))
    return dict(results)


# ── Skill 注册 (供 imdf/skills/registry.py 调用) ─────────────────────────
SKILL_REGISTRATION: List[Dict[str, Any]] = [
    {
        "skill_id": "redfox_publish",
        "name": "RedFox 多平台发布",
        "description": "把一条内容并发发布到 11 个自媒体平台(微信公众号/微博/抖音/快手/小红书/B站/知乎/头条号/百家号/企鹅号/视频号)",
        "trigger_phrases": ["全平台发布", "redfox_publish", "跨平台发布", "多平台分发"],
        "function": "publish_to_all",
        "category": "marketing",
    },
    {
        "skill_id": "redfox_schedule",
        "name": "RedFox 调度发布",
        "description": "把内容加入调度队列 — 指定 schedule_time 后由 worker 拉取并 fan-out 发布",
        "trigger_phrases": ["定时发布", "redfox_schedule", "预约发布", "排队发布"],
        "function": "schedule_publish",
        "category": "marketing",
    },
    {
        "skill_id": "redfox_metrics",
        "name": "RedFox 跨平台指标",
        "description": "聚合 11 个平台同一 post_id 的浏览/点赞/评论/转发/收藏/粉丝增量",
        "trigger_phrases": ["跨平台指标", "redfox_metrics", "指标聚合", "全平台数据"],
        "function": "fetch_cross_platform_metrics",
        "category": "data",
    },
    {
        "skill_id": "redfox_adapt",
        "name": "RedFox 平台改写",
        "description": "用 LLM 把同一内容改写成各平台风格变体 (微博短句/小红书种草/B站梗向等)",
        "trigger_phrases": ["平台改写", "redfox_adapt", "内容改写", "多版本内容"],
        "function": "generate_platform_variants",
        "category": "content",
    },
]


__all__ = [
    "publish_to_all",
    "schedule_publish",
    "run_due_scheduled",
    "list_scheduled",
    "fetch_cross_platform_metrics",
    "generate_platform_variants",
    "SKILL_REGISTRATION",
]