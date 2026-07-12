#!/usr/bin/env python3
"""
P19 V5.1 附录 D — 50 个内置 Skill (25 基础 + 25 扩展)

按 11 个分类组织:
- 采集类 (10)   : crawl_web/crawl_deep/crawl_redfox/source_trace/seed_extract/...
- 处理类 (5)    : dedupe/auto_label/score_quality/translate/format_normalize
- Agent 类 (8)  : agent_chat/agent_memory/bot_create/channel_create/matter_create/
                  vida_screen/meta_intent/meta_review
- Octo 类 (4)   : bot_create/channel_create/matter_create/collab_run (与 Agent 重叠,
                   这里 Octo 指"内部 Octo 引擎协议",ID 不同避免冲突)
- Vida 类 (2)   : vida_screen/vida_action
- Meta_Kim (3)  : meta_intent/meta_review/meta_lesson
- 短剧类 (5)    : drama_script/drama_character/drama_scene/drama_shot/drama_assemble
- Comfy 类 (3)  : comfy_run/comfy_workflow/comfy_model
- RedFox 类 (3) : redfox_search/redfox_hot/redfox_publish
- Reach 类 (4)  : reach_web/reach_twitter/reach_github/reach_arxiv
- Agency 类 (3) : agency_expert/agency_department/agency_capability

合计 = 10+5+8+4+2+3+5+3+3+4+3 = 50

注意: Octo 与 Agent 在 bot/channel/matter 上有意重复 ID,
所以用不同前缀 (octo_* vs agent_*) 避免与 Skill.id 唯一约束冲突。

@author MiniMax Agent
@date 2026-07-02
@task P19 v5.1-B
"""

from typing import Any, Dict, List, Type

from backend.skills import SkillSpec


# ----------------------------------------------------------------------------
# Helper factory
# ----------------------------------------------------------------------------

def _make(
    skill_id: str,
    name: str,
    category: str,
    trigger: List[str],
    inputs: Dict[str, str],
    outputs: Dict[str, str],
    desc: str = "",
    deps: List[str] = None,
    version: str = "1.0.0",
) -> SkillSpec:
    """工厂函数: 生成 SkillSpec,减少模板代码"""
    return SkillSpec(
        id=skill_id,
        name=name,
        category=category,
        trigger_phrases=list(trigger),
        inputs=dict(inputs),
        outputs=dict(outputs),
        description=desc or f"{name} ({category})",
        enabled=True,
        version=version,
        dependencies=list(deps or []),
    )


# ----------------------------------------------------------------------------
# 类别 1: 采集类 (10)
# ----------------------------------------------------------------------------

CRAWL_SKILLS: List[SkillSpec] = [
    _make(
        "skill_crawl_web",
        "网页抓取 / Web Crawler",
        "crawl",
        ["抓取网页", "crawl", "fetch", "获取网页", "网页抓取"],
        {"url": "string", "depth": "int", "selector": "string?"},
        {"content": "string", "links": "list", "metadata": "dict"},
        desc="从 URL 抓取网页内容与链接,支持深度与 CSS 选择器过滤",
    ),
    _make(
        "skill_crawl_deep",
        "深度递归抓取 / Deep Crawler",
        "crawl",
        ["深度抓取", "递归抓取", "deep crawl", "全站抓取"],
        {"url": "string", "max_depth": "int", "max_pages": "int"},
        {"pages": "list", "graph": "dict"},
        desc="对整站进行 BFS/DFS 递归抓取,生成 URL 关系图",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_crawl_redfox",
        "RedFox 焦点抓取 / RedFox Focus",
        "crawl",
        ["redfox", "焦点抓取", "redfox 抓取"],
        {"topic": "string", "max_results": "int"},
        {"results": "list", "traces": "list"},
        desc="通过 RedFox 引擎对指定主题进行高信噪比抓取",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_source_trace",
        "信源溯源 / Source Trace",
        "crawl",
        ["信源溯源", "source trace", "溯源"],
        {"content": "string", "url": "string?"},
        {"source_chain": "list", "confidence": "float"},
        desc="追溯一段内容的原始信源链路,生成可信度评分",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_seed_extract",
        "种子提取 / Seed Extract",
        "crawl",
        ["seed", "种子", "提取种子", "extract seed"],
        {"text": "string", "min_weight": "float?"},
        {"seeds": "list", "scores": "list"},
        desc="从非结构化文本中提取可继续抓取的种子实体",
    ),
    _make(
        "skill_feed_subscribe",
        "RSS/Atom 订阅 / Feed Subscribe",
        "crawl",
        ["rss", "订阅", "feed", "atom"],
        {"feed_url": "string", "interval_sec": "int?"},
        {"items": "list", "last_fetch": "datetime"},
        desc="订阅 RSS/Atom feed,周期性拉取并触发下游 pipeline",
    ),
    _make(
        "skill_sitemap_parse",
        "Sitemap 解析 / Sitemap Parse",
        "crawl",
        ["sitemap", "站点地图"],
        {"sitemap_url": "string"},
        {"urls": "list", "last_modified": "datetime?"},
        desc="解析 XML sitemap,提取全站 URL 列表",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_browser_screenshot",
        "浏览器截图 / Browser Screenshot",
        "crawl",
        ["screenshot", "截图", "浏览器截图"],
        {"url": "string", "viewport": "string?", "full_page": "bool?"},
        {"png_bytes": "bytes", "url_final": "string"},
        desc="通过 Playwright 渲染并保存网页截图(png bytes)",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_proxy_fetch",
        "代理抓取 / Proxy Fetch",
        "crawl",
        ["代理", "proxy", "proxy 抓取"],
        {"url": "string", "proxy_pool": "string?"},
        {"content": "string", "proxy_used": "string"},
        desc="通过代理池抓取 URL,降低单 IP 被反爬风险",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_cookie_manage",
        "Cookie 管理 / Cookie Manager",
        "crawl",
        ["cookie", "登录态"],
        {"site": "string", "cookie_dict": "dict?"},
        {"cookies": "dict", "expires_at": "datetime"},
        desc="管理多站点登录态 Cookie,提供抓取时注入",
    ),
]


# ----------------------------------------------------------------------------
# 类别 2: 处理类 (5)
# ----------------------------------------------------------------------------

PROCESS_SKILLS: List[SkillSpec] = [
    _make(
        "skill_dedupe",
        "去重 / Dedupe",
        "process",
        ["去重", "dedupe", "remove duplicate"],
        {"items": "list", "key": "string?"},
        {"unique_items": "list", "duplicates": "list"},
        desc="按 key 字段对列表去重,保留首次出现",
    ),
    _make(
        "skill_auto_label",
        "自动打标 / Auto Label",
        "process",
        ["打标", "auto label", "分类"],
        {"items": "list", "labels": "list"},
        {"labeled": "list", "label_map": "dict"},
        desc="调用 LLM 或规则对 items 打标签,返回 label_map",
    ),
    _make(
        "skill_score_quality",
        "质量打分 / Quality Score",
        "process",
        ["打分", "quality score", "评分"],
        {"items": "list", "rubric": "string?"},
        {"scores": "list", "overall": "float"},
        desc="对数据按 rubric 进行多维度打分,返回 0-1 质量分",
    ),
    _make(
        "skill_translate",
        "中英翻译 / Translate",
        "process",
        ["翻译", "translate", "中英"],
        {"text": "string", "src_lang": "string?", "tgt_lang": "string?"},
        {"translated": "string", "src_lang": "string", "tgt_lang": "string"},
        desc="调用 LLM 完成多语种互译,默认 zh <-> en",
    ),
    _make(
        "skill_format_normalize",
        "格式归一化 / Format Normalize",
        "process",
        ["归一化", "normalize", "格式"],
        {"items": "list", "schema": "dict"},
        {"normalized": "list", "errors": "list"},
        desc="按 schema 把异构 item 归一化为统一字段格式",
    ),
]


# ----------------------------------------------------------------------------
# 类别 3: Agent 类 (8) — 对应内部 Agent 引擎调用
# ----------------------------------------------------------------------------

AGENT_SKILLS: List[SkillSpec] = [
    _make(
        "skill_agent_chat",
        "Agent 对话 / Agent Chat",
        "agent",
        ["agent 对话", "agent chat", "single agent"],
        {"prompt": "string", "agent_id": "string?"},
        {"reply": "string", "tokens": "int"},
        desc="调用单个 Agent 完成一次对话响应",
    ),
    _make(
        "skill_agent_memory",
        "Agent 记忆 / Agent Memory",
        "agent",
        ["agent 记忆", "memory", "long-term memory"],
        {"agent_id": "string", "action": "string", "data": "dict?"},
        {"result": "dict"},
        desc="读写 Agent 长记忆(append/search/summarize/forget)",
    ),
    _make(
        "skill_agent_plan",
        "Agent 计划 / Agent Plan",
        "agent",
        ["规划", "plan", "agent plan"],
        {"goal": "string", "constraints": "list?"},
        {"steps": "list", "plan_id": "string"},
        desc="把目标拆成可执行步骤,生成结构化执行计划",
        deps=["skill_agent_chat"],
    ),
    _make(
        "skill_agent_tools",
        "Agent 工具调用 / Agent Tool Use",
        "agent",
        ["工具调用", "tool use", "function call"],
        {"prompt": "string", "tools": "list"},
        {"tool_calls": "list", "final": "string"},
        desc="让 Agent 自主选择并调用已注册的工具",
        deps=["skill_agent_chat"],
    ),
    _make(
        "skill_agent_reflect",
        "Agent 自省 / Agent Reflect",
        "agent",
        ["self reflect", "自省"],
        {"trace": "list"},
        {"insights": "list", "next_actions": "list"},
        desc="基于执行 trace 让 Agent 做自省,产出改进 insight",
        deps=["skill_agent_chat"],
    ),
    _make(
        "skill_agent_multi",
        "多 Agent 协同 / Multi-Agent Collab",
        "agent",
        ["multi-agent", "多 agent", "多智能体"],
        {"goal": "string", "agents": "list"},
        {"messages": "list", "result": "dict"},
        desc="编排多个 Agent 围绕同一目标协同讨论",
        deps=["skill_agent_chat"],
    ),
    _make(
        "skill_agent_persona",
        "Persona 注入 / Persona Inject",
        "agent",
        ["persona", "人格", "人设"],
        {"agent_id": "string", "persona": "dict"},
        {"agent_id": "string", "applied": "bool"},
        desc="动态替换/注入 Agent 的人格 prompt",
        deps=["skill_agent_chat"],
    ),
    _make(
        "skill_agent_eval",
        "Agent 评测 / Agent Eval",
        "agent",
        ["评测 agent", "agent eval"],
        {"agent_id": "string", "rubric": "dict"},
        {"score": "float", "details": "list"},
        desc="按 rubric 自动评测 Agent 行为并打分",
        deps=["skill_agent_chat"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 4: Octo 类 (4) — 内部 Octo 引擎协议层
# ----------------------------------------------------------------------------

OCTO_SKILLS: List[SkillSpec] = [
    _make(
        "skill_octo_bot_create",
        "Octo Bot 创建 / Octo Bot Create",
        "octo",
        ["octo bot", "bot 创建"],
        {"spec": "dict", "channel": "string?"},
        {"bot_id": "string", "ok": "bool"},
        desc="通过 Octo 协议创建一个可执行 Bot",
    ),
    _make(
        "skill_octo_channel_create",
        "Octo Channel 创建 / Octo Channel Create",
        "octo",
        ["octo channel", "channel 创建"],
        {"spec": "dict"},
        {"channel_id": "string", "ok": "bool"},
        desc="通过 Octo 协议创建频道并初始化订阅者",
        deps=["skill_octo_bot_create"],
    ),
    _make(
        "skill_octo_matter_create",
        "Octo Matter 创建 / Octo Matter Create",
        "octo",
        ["octo matter", "matter 创建"],
        {"spec": "dict"},
        {"matter_id": "string", "ok": "bool"},
        desc="通过 Octo 协议创建一个 Matter(任务/事件)",
        deps=["skill_octo_channel_create"],
    ),
    _make(
        "skill_octo_collab_run",
        "Octo 协同运行 / Octo Collab Run",
        "octo",
        ["octo collab", "octo 协同"],
        {"matter_ids": "list", "mode": "string?"},
        {"results": "list", "ok": "bool"},
        desc="把多个 Matter 装入同一个 Octo 协同运行时",
        deps=["skill_octo_matter_create"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 5: Vida 类 (2)
# ----------------------------------------------------------------------------

VIDA_SKILLS: List[SkillSpec] = [
    _make(
        "skill_vida_screen",
        "Vida 录屏 / Vida Screen",
        "vida",
        ["vida 录屏", "vida screen"],
        {"duration_sec": "int", "fps": "int?"},
        {"video_path": "string", "duration": "int"},
        desc="Vida 引擎录屏一段操作序列为 mp4",
    ),
    _make(
        "skill_vida_action",
        "Vida 动作回放 / Vida Action",
        "vida",
        ["vida action", "vida 动作"],
        {"video_path": "string", "schema": "dict?"},
        {"actions": "list", "confidence": "float"},
        desc="基于录屏视频推断具体动作序列(用于 self-play 数据生成)",
        deps=["skill_vida_screen"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 6: Meta_Kim 类 (3)
# ----------------------------------------------------------------------------

META_KIM_SKILLS: List[SkillSpec] = [
    _make(
        "skill_meta_intent",
        "意图识别 / Intent Recognition",
        "meta_kim",
        ["意图识别", "intent", "meta intent"],
        {"text": "string"},
        {"intent": "string", "slots": "dict"},
        desc="对用户输入做意图分类与槽位抽取",
    ),
    _make(
        "skill_meta_review",
        "元审查 / Meta Review",
        "meta_kim",
        ["meta review", "元审查"],
        {"items": "list", "policy": "dict?"},
        {"approved": "list", "rejected": "list", "issues": "list"},
        desc="按 policy 对数据批量合规审查,分离 approved / rejected",
    ),
    _make(
        "skill_meta_lesson",
        "经验沉淀 / Lesson Distill",
        "meta_kim",
        ["经验沉淀", "lesson", "meta lesson"],
        {"traces": "list"},
        {"lessons": "list", "save_to": "string"},
        desc="从执行 trace 中蒸馏结构化经验,写入 long-term memory",
        deps=["skill_meta_review"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 7: 短剧类 (5)
# ----------------------------------------------------------------------------

DRAMA_SKILLS: List[SkillSpec] = [
    _make(
        "skill_drama_script",
        "短剧剧本 / Drama Script",
        "drama",
        ["短剧剧本", "drama script", "剧本生成"],
        {"outline": "string", "episodes": "int?"},
        {"script": "dict", "scenes": "list"},
        desc="基于大纲生成分集剧本(含对白、镜头指示)",
    ),
    _make(
        "skill_drama_character",
        "短剧角色 / Drama Character",
        "drama",
        ["角色设计", "character"],
        {"names": "list", "style": "string?"},
        {"characters": "list"},
        desc="为剧本生成角色表(肖像 prompt + 人设)",
        deps=["skill_drama_script"],
    ),
    _make(
        "skill_drama_scene",
        "短剧场景 / Drama Scene",
        "drama",
        ["场景", "scene", "分镜"],
        {"script": "dict", "style": "string?"},
        {"scene_cards": "list"},
        desc="把剧本拆为可视化分镜卡片",
        deps=["skill_drama_script"],
    ),
    _make(
        "skill_drama_shot",
        "短剧镜头 / Drama Shot",
        "drama",
        ["镜头", "shot", "镜头生成"],
        {"scene_card": "dict"},
        {"image_prompts": "list", "videos": "list"},
        desc="对每个镜头生成图片 / 短视频 prompt",
        deps=["skill_drama_scene"],
    ),
    _make(
        "skill_drama_assemble",
        "短剧合成 / Drama Assemble",
        "drama",
        ["合成", "assemble", "短剧合成"],
        {"shots": "list", "music": "string?"},
        {"video_url": "string", "duration_sec": "int"},
        desc="把所有镜头拼接为最终短剧视频",
        deps=["skill_drama_shot"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 8: Comfy 类 (3)
# ----------------------------------------------------------------------------

COMFY_SKILLS: List[SkillSpec] = [
    _make(
        "skill_comfy_run",
        "ComfyUI 运行 / Comfy Run",
        "comfy",
        ["comfyui", "comfy run", "comfy 调用"],
        {"workflow": "dict", "params": "dict?"},
        {"images": "list", "outputs": "list"},
        desc="把工作流 json 提交到 ComfyUI,返回生成结果",
    ),
    _make(
        "skill_comfy_workflow",
        "ComfyUI 工作流管理 / Comfy Workflow",
        "comfy",
        ["comfy workflow", "工作流"],
        {"action": "string", "workflow": "dict?"},
        {"workflows": "list", "id": "string?"},
        desc="CRUD 管理一组 ComfyUI 工作流模板",
        deps=["skill_comfy_run"],
    ),
    _make(
        "skill_comfy_model",
        "ComfyUI 模型管理 / Comfy Model",
        "comfy",
        ["comfy 模型", "comfy model"],
        {"action": "string", "model_name": "string?"},
        {"models": "list", "ok": "bool"},
        desc="管理 ComfyUI 模型(checkpoint / lora / vae)",
    ),
]


# ----------------------------------------------------------------------------
# 类别 9: RedFox 类 (3)
# ----------------------------------------------------------------------------

REDFOX_SKILLS: List[SkillSpec] = [
    _make(
        "skill_redfox_search",
        "RedFox 搜索 / RedFox Search",
        "redfox",
        ["redfox 搜索", "redfox search"],
        {"topic": "string", "limit": "int?"},
        {"results": "list"},
        desc="RedFox 全网搜索,返回结构化结果",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_redfox_hot",
        "RedFox 热点 / RedFox Hot",
        "redfox",
        ["redfox 热点", "hot", "trend"],
        {"region": "string?", "limit": "int?"},
        {"trending": "list"},
        desc="RedFox 提供的热点榜(可指定 region)",
    ),
    _make(
        "skill_redfox_publish",
        "RedFox 发布 / RedFox Publish",
        "redfox",
        ["redfox 发布", "publish"],
        {"content": "string", "targets": "list"},
        {"status": "dict", "urls": "list"},
        desc="RedFox 多平台分发(微博/小红书/Twitter/X 等)",
        deps=["skill_redfox_search"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 10: Reach 类 (4) — 对应 Agent-Reach 集成
# ----------------------------------------------------------------------------

REACH_SKILLS: List[SkillSpec] = [
    _make(
        "skill_reach_web",
        "Web Reach / Web Reach",
        "reach",
        ["web reach", "通用 web 搜索"],
        {"query": "string", "limit": "int?"},
        {"results": "list"},
        desc="通过 Agent-Reach 通用 web 搜索",
        deps=["skill_crawl_web"],
    ),
    _make(
        "skill_reach_twitter",
        "Twitter/X Reach / Twitter Reach",
        "reach",
        ["twitter 搜索", "x 搜索", "reach twitter"],
        {"query": "string", "limit": "int?"},
        {"tweets": "list"},
        desc="通过 Agent-Reach 检索 Twitter / X 内容",
        deps=["skill_reach_web"],
    ),
    _make(
        "skill_reach_github",
        "GitHub Reach / GitHub Reach",
        "reach",
        ["github 搜索", "reach github"],
        {"query": "string", "language": "string?"},
        {"repos": "list"},
        desc="通过 Agent-Reach 检索 GitHub repos / code",
        deps=["skill_reach_web"],
    ),
    _make(
        "skill_reach_arxiv",
        "arxiv Reach / arxiv Reach",
        "reach",
        ["arxiv", "reach arxiv", "论文"],
        {"query": "string", "max_results": "int?"},
        {"papers": "list"},
        desc="通过 Agent-Reach 检索 arxiv 论文(含摘要 + PDF 链接)",
        deps=["skill_reach_web"],
    ),
]


# ----------------------------------------------------------------------------
# 类别 11: Agency 类 (3) — IMDF Agency 三件套
# ----------------------------------------------------------------------------

AGENCY_SKILLS: List[SkillSpec] = [
    _make(
        "skill_agency_expert",
        "Agency 专家库 / Agency Expert",
        "agency",
        ["agency expert", "专家", "专家库"],
        {"action": "string", "expert_id": "string?", "spec": "dict?"},
        {"ok": "bool", "expert": "dict"},
        desc="Agency 专家库 CRUD(创建/查找/更新专家档案)",
    ),
    _make(
        "skill_agency_department",
        "Agency 部门 / Agency Department",
        "agency",
        ["agency department", "部门"],
        {"action": "string", "dept_id": "string?", "spec": "dict?"},
        {"ok": "bool", "dept": "dict"},
        desc="Agency 部门 CRUD,并支持把专家编入部门",
        deps=["skill_agency_expert"],
    ),
    _make(
        "skill_agency_capability",
        "Agency 能力调用 / Agency Capability",
        "agency",
        ["agency capability", "agency 调用"],
        {"expert_id": "string", "task": "dict"},
        {"ok": "bool", "result": "dict"},
        desc="基于专家能力描述,把任务路由到合适的专家执行",
        deps=["skill_agency_expert"],
    ),
]


# ----------------------------------------------------------------------------
# 聚合入口: BUILTIN_SKILLS
# ----------------------------------------------------------------------------

def _all_builtin() -> List[SkillSpec]:
    """按分类顺序聚合 50 个 builtin skill"""
    groups: List[List[SkillSpec]] = [
        CRAWL_SKILLS,
        PROCESS_SKILLS,
        AGENT_SKILLS,
        OCTO_SKILLS,
        VIDA_SKILLS,
        META_KIM_SKILLS,
        DRAMA_SKILLS,
        COMFY_SKILLS,
        REDFOX_SKILLS,
        REACH_SKILLS,
        AGENCY_SKILLS,
    ]
    out: List[SkillSpec] = []
    for g in groups:
        out.extend(g)
    return out


BUILTIN_SKILLS: List[SkillSpec] = _all_builtin()


def categories_builtin() -> Dict[str, int]:
    """返回各类别下 builtin skill 数量,用于自检"""
    cnt: Dict[str, int] = {}
    for s in BUILTIN_SKILLS:
        cnt[s.category] = cnt.get(s.category, 0) + 1
    return cnt


if __name__ == "__main__":
    # CLI 自检: 打印数量与各 category 计数
    cnt = categories_builtin()
    print(f"Total builtin skills: {len(BUILTIN_SKILLS)}")
    for k, v in sorted(cnt.items()):
        print(f"  {k}: {v}")
    assert len(BUILTIN_SKILLS) == 50, f"expected 50, got {len(BUILTIN_SKILLS)}"
    print("OK")
