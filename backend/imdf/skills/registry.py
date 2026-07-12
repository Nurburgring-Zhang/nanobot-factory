"""V5 第31章 + 第26章 + 第32章 — RedFox 4 + Vida 1 + Agent Reach 1 Skill 注册表
(imdf.skills.registry).

把 imdf.creative.redfox.skills.SKILL_REGISTRATION (4 个 dict) + Vida proactive
assist skill + Agent Reach internet skill 提升为 typed RedFoxSkillSpec /
VidaSkillSpec / AgentReachSkillSpec, 提供 imdf.skills.* 命名空间下的统一查询入口。

注册的 Skill:
  * redfox_publish        — 多平台并发发布 (11 平台 fan-out)
  * redfox_schedule       — 调度发布 (队列 + worker)
  * redfox_metrics        — 跨平台指标聚合
  * redfox_adapt          — LLM 平台风格改写
  * vida_proactive_assist — Vida 屏幕感知主动助手 (V5 第26章)
  * agent_reach_internet  — Agent Reach 互联网能力 (V5 第32章 — 14 渠道)

调用方:
    from backend.imdf.skills import list_redfox_skills, list_vida_skills,
        list_agent_reach_skills, get_redfox_skill, get_vida_skill,
        get_agent_reach_skill
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 从 redfox.skills 导入原始 SKILL_REGISTRATION (4 个 dict)
from imdf.creative.redfox.skills import (
    SKILL_REGISTRATION as _REDFOX_SKILLS_RAW,
    fetch_cross_platform_metrics,
    generate_platform_variants,
    publish_to_all,
    schedule_publish,
)


def _meta_kim_governance(*args, **kwargs):
    """Thin wrapper for ``MetaKimEngine.govern_run``.

    Lazily imported to avoid a hard dependency on the engine module at
    registry-build time.  Returns a coroutine — callers must await it.
    """
    import asyncio
    from imdf.engines.meta_kim_engine import MetaKimEngine

    request = args[0] if args else kwargs.get("request", "")
    context = kwargs.get("context") or (args[1] if len(args) > 1 else None)

    engine = MetaKimEngine()
    return asyncio.run(engine.govern_run(request=request, context=context))

# Vida imports — async skill
from imdf.engines.vida_engine import VidaEngine
from imdf.intelligence.vida import (
    ActionExecutor,
    AgentMemoryStore,
    ContextAnalyzer,
    IntentPredictor,
    ScreenCapture,
)


# ── Vida skill factory ─────────────────────────────────────────────────
async def _vida_proactive_assist(*, user_id: str,
                                 engine: Optional[VidaEngine] = None) -> Dict[str, Any]:
    """vida_proactive_assist 入口 — 包装 VidaEngine.perceive_and_act.

    Args:
        user_id: 目标 user_id
        engine:  可选外部注入的 VidaEngine; 不传则构造一个默认 mock 版

    Returns:
        perceive_and_act 的 Dict 输出 (含 context/intent/action/result)
    """
    if engine is None:
        # 默认 mock engine — 给生产代码用; 测试会注入自己的 engine
        from imdf.orchestration.bus import EventBus

        engine = VidaEngine(
            screen_capture=ScreenCapture(mode="mock"),
            context_analyzer=ContextAnalyzer(),
            intent_predictor=IntentPredictor(heuristic_only=True),
            action_executor=ActionExecutor(),
            memory_store=AgentMemoryStore(root_dir=".vida_memory_default"),
            bus=EventBus(),
        )
    result = await engine.perceive_and_act(user_id)
    return {
        "scenario": getattr(result.get("context"), "scenario", None) and result["context"].scenario.value,
        "app": getattr(result.get("context"), "app", None),
        "intent_type": getattr(result.get("intent"), "intent_type", None) and result["intent"].intent_type.value,
        "confidence": getattr(result.get("intent"), "confidence", None),
        "action_type": getattr(result.get("action"), "action_type", None) and (
            result["action"].action_type.value if result["action"] else None
        ),
        "action_executed": result.get("action") is not None,
    }


# ── function_ref wrapper for registry ─────────────────────────────────
def _run_vida_skill(*, user_id: str) -> Dict[str, Any]:
    """同步包装 — 供 RedFoxSkillSpec.function_ref (callable)."""
    import asyncio
    return asyncio.run(_vida_proactive_assist(user_id=user_id))


# --------------------------------------------------------------------------- #
#  RedFox Skill spec
# --------------------------------------------------------------------------- #
@dataclass
class RedFoxSkillSpec:
    """RedFox 单 Skill 规格 — 继承自 P19 v5.1-B SkillSpec 风格.

    比 raw dict 多两个字段: function_ref (实际 callable) + enabled (skill 开关).
    """

    skill_id: str
    name: str
    category: str
    trigger_phrases: List[str]
    function: str
    function_ref: Callable[..., Any]
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    inputs_schema: Dict[str, Any] = field(default_factory=dict)
    outputs_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    author: str = "redfox"
    source: str = "imdf.creative.redfox"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "trigger_phrases": list(self.trigger_phrases),
            "function": self.function,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "inputs_schema": dict(self.inputs_schema),
            "outputs_schema": dict(self.outputs_schema),
            "dependencies": list(self.dependencies),
            "author": self.author,
            "source": self.source,
        }


# ── function_ref 映射 (raw dict.function → 实际 callable) ──────────────────
_FUNCTION_MAP: Dict[str, Callable[..., Any]] = {
    "publish_to_all": publish_to_all,
    "schedule_publish": schedule_publish,
    "fetch_cross_platform_metrics": fetch_cross_platform_metrics,
    "generate_platform_variants": generate_platform_variants,
    "meta_kim_govern_run": _meta_kim_governance,
}


# ── 每个 skill 的 input/output schema (描述) ────────────────────────────────
_INPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "redfox_publish": {
        "content": {"type": "object", "description": "ContentItem"},
        "only": {
            "type": "array", "items": {"type": "string"},
            "description": "Optional subset of platform_ids",
        },
    },
    "redfox_schedule": {
        "content": {"type": "object"},
        "schedule_time": {"type": "integer", "description": "unix timestamp, 0=now"},
        "target_platforms": {"type": "array", "items": {"type": "string"}},
    },
    "redfox_metrics": {
        "post_id": {"type": "string"},
        "platforms": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
    },
    "redfox_adapt": {
        "base_content": {"type": "object"},
        "platforms": {"type": "array", "items": {"type": "string"}},
        "llm": {"type": "object", "description": "Optional LLM callable"},
    },
}

_OUTPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "redfox_publish": {
        "results": {"type": "object", "description": "Dict[PlatformId, PublishResult]"},
    },
    "redfox_schedule": {
        "item": {"type": "object", "description": "ScheduledPublish (status=done|pending)"},
    },
    "redfox_metrics": {
        "metrics": {"type": "object", "description": "CrossPlatformMetrics with total"},
    },
    "redfox_adapt": {
        "variants": {"type": "object", "description": "Dict[PlatformId, PlatformVariant]"},
    },
}


def _build_specs() -> List[RedFoxSkillSpec]:
    """从 raw SKILL_REGISTRATION + _FUNCTION_MAP + schemas 构建 typed specs."""
    out: List[RedFoxSkillSpec] = []
    for entry in _REDFOX_SKILLS_RAW:
        fn_name = entry["function"]
        if fn_name not in _FUNCTION_MAP:
            # 跳过缺少 function_ref 的 skill (避免运行时 ImportError)
            continue
        out.append(RedFoxSkillSpec(
            skill_id=entry["skill_id"],
            name=entry["name"],
            category=entry.get("category", "general"),
            trigger_phrases=list(entry.get("trigger_phrases", [])),
            function=fn_name,
            function_ref=_FUNCTION_MAP[fn_name],
            description=entry.get("description", ""),
            inputs_schema=_INPUT_SCHEMAS.get(entry["skill_id"], {}),
            outputs_schema=_OUTPUT_SCHEMAS.get(entry["skill_id"], {}),
        ))

    # ── V5 第27章 Meta_Kim 治理循环 Skill (P19 v5.3) ──────────────────────
    # This is the canonical 7-step governance loop (Clarify → Search → Select
    # → Split → Execute → Verify → Learn) wrapper that turns a vague user
    # request into an audited, learning-enabled pipeline.
    out.append(RedFoxSkillSpec(
        skill_id="meta_kim_governance",
        name="Meta_Kim Governance Loop",
        category="governance",
        trigger_phrases=[
            "治理循环", "governance loop", "meta_kim", "7步治理",
            "auto pipeline", "auto govern", "auto audit",
            "AI governance", "self-improving",
        ],
        function="meta_kim_govern_run",
        function_ref=_FUNCTION_MAP["meta_kim_govern_run"],
        description=(
            "V5 Chapter 27 — 7-step Meta_Kim governance loop. "
            "Wraps every Agent run with clarify→search→select→split→"
            "execute→verify→learn so all actions are auditable and the "
            "engine learns from each outcome (success → Skill, failure → "
            "FailureKnowledgeBase)."
        ),
        version="1.0.0",
        enabled=True,
        inputs_schema={
            "request": {"type": "string", "description": "User's free-form request"},
            "context": {"type": "object", "description": "Optional execution context"},
        },
        outputs_schema={
            "run_id": {"type": "string", "description": "governance_run id"},
            "intent": {"type": "object", "description": "Resolved Intent"},
            "tasks": {"type": "array", "description": "Subtask list"},
            "verified": {"type": "object", "description": "VerifiedResult"},
            "lessons": {"type": "array", "description": "Extracted lessons"},
            "report": {"type": "object", "description": "GovernedReport"},
        },
        dependencies=["imdf.engines.meta_kim_engine", "imdf.orchestration.bus"],
        author="meta_kim",
        source="imdf.engines.meta_kim",
    ))
    return out


# ── 导出: REDFOX_SKILLS + 查询函数 ────────────────────────────────────────
REDFOX_SKILLS: List[RedFoxSkillSpec] = _build_specs()
"""4 个 RedFox Skill 的 typed specs — 模块加载时一次性构建."""

_BY_ID: Dict[str, RedFoxSkillSpec] = {s.skill_id: s for s in REDFOX_SKILLS}


def list_redfox_skills() -> List[RedFoxSkillSpec]:
    """返回所有 RedFox skills."""
    return list(REDFOX_SKILLS)


def get_redfox_skill(skill_id: str) -> RedFoxSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _BY_ID:
        raise KeyError(f"redfox skill not found: {skill_id}")
    return _BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  Vida Skill spec (V5 第26章)
# --------------------------------------------------------------------------- #
@dataclass
class VidaSkillSpec:
    """Vida 单 Skill 规格 — 屏幕感知主动助手.

    与 RedFoxSkillSpec 同构 — 方便统一查询接口.
    """

    skill_id: str
    name: str
    category: str
    trigger_phrases: List[str]
    function: str
    function_ref: Callable[..., Any]
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    inputs_schema: Dict[str, Any] = field(default_factory=dict)
    outputs_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    author: str = "vida"
    source: str = "imdf.intelligence.vida"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "trigger_phrases": list(self.trigger_phrases),
            "function": self.function,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "inputs_schema": dict(self.inputs_schema),
            "outputs_schema": dict(self.outputs_schema),
            "dependencies": list(self.dependencies),
            "author": self.author,
            "source": self.source,
        }


# ── vida_proactive_assist spec ────────────────────────────────────────────
VIDA_PROACTIVE_ASSIST_SPEC = VidaSkillSpec(
    skill_id="vida_proactive_assist",
    name="Vida Proactive Assist",
    category="proactive_assistant",
    trigger_phrases=[
        "proactive assist",
        "screen aware",
        "what should i do next",
        "主动助手",
        "下一步",
        "vida",
    ],
    function="vida_proactive_assist",
    function_ref=_run_vida_skill,
    description=(
        "Vida 屏幕感知主动助手 — 持续抓拍屏幕、识别 6 大场景 (code/chat/document/"
        "research/email/terminal)、用 LLM 预测用户意图 (write_code/reply_message/"
        "research/read_document/email/other), 当 confidence > 0.7 时主动执行 "
        "7 种行动 (summarize/reply/organize/search/remind/draft/analyze), 并"
        "生成每日战报."
    ),
    version="5.3.0",
    enabled=True,
    inputs_schema={
        "user_id": {"type": "string", "description": "Target user id for memory + report"},
    },
    outputs_schema={
        "scenario": {"type": "string", "description": "Detected Scenario enum value"},
        "app": {"type": "string", "description": "Active application name"},
        "intent_type": {"type": "string", "description": "Predicted intent_type"},
        "confidence": {"type": "number", "description": "Intent confidence [0,1]"},
        "action_type": {"type": "string", "description": "Executed action_type or null"},
        "action_executed": {"type": "boolean", "description": "Whether action was executed"},
    },
    dependencies=[
        "imdf.intelligence.vida.ScreenCapture",
        "imdf.intelligence.vida.ContextAnalyzer",
        "imdf.intelligence.vida.IntentPredictor",
        "imdf.intelligence.vida.ActionExecutor",
        "imdf.intelligence.vida.AgentMemoryStore",
        "imdf.engines.vida_engine.VidaEngine",
        "imdf.orchestration.bus.EventBus",
    ],
    author="vida",
    source="imdf.intelligence.vida",
)


VIDA_SKILLS: List[VidaSkillSpec] = [VIDA_PROACTIVE_ASSIST_SPEC]
"""Vida skills — 当前只 1 个: vida_proactive_assist."""

_VIDA_BY_ID: Dict[str, VidaSkillSpec] = {s.skill_id: s for s in VIDA_SKILLS}


def list_vida_skills() -> List[VidaSkillSpec]:
    """返回所有 Vida skills."""
    return list(VIDA_SKILLS)


def get_vida_skill(skill_id: str) -> VidaSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _VIDA_BY_ID:
        raise KeyError(f"vida skill not found: {skill_id}")
    return _VIDA_BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  Agent Reach Skill spec (V5 第32章)
# --------------------------------------------------------------------------- #
@dataclass
class AgentReachSkillSpec:
    """Agent Reach 单 Skill 规格 — 14 渠道互联网接入层 (V5 第32章).

    与 RedFoxSkillSpec / VidaSkillSpec 同构 — 方便统一查询接口.
    """

    skill_id: str
    name: str
    category: str
    trigger_phrases: List[str]
    function: str
    function_ref: Callable[..., Any]
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    inputs_schema: Dict[str, Any] = field(default_factory=dict)
    outputs_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    author: str = "agent_reach"
    source: str = "imdf.intelligence.agent_reach"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "trigger_phrases": list(self.trigger_phrases),
            "function": self.function,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "inputs_schema": dict(self.inputs_schema),
            "outputs_schema": dict(self.outputs_schema),
            "dependencies": list(self.dependencies),
            "author": self.author,
            "source": self.source,
        }


def _run_agent_reach_skill(*, query: str, channels: Optional[List[str]] = None) -> Dict[str, Any]:
    """同步包装 — 供 AgentReachSkillSpec.function_ref (callable).

    调用 AgentReachIntegration.search(query, channels) 并把 MultiChannelResult
    序列化成 JSON-safe dict.
    """
    import asyncio
    from imdf.intelligence.agent_reach.integration import AgentReachIntegration

    integ = AgentReachIntegration()
    result = asyncio.run(integ.search(query, channels=channels))
    return {
        "query": result.query,
        "channels": list(result.channels),
        "total": result.total,
        "success_count": result.success_count,
        "error_count": result.error_count,
        "elapsed_ms": result.elapsed_ms,
        "results": {ch: fr.model_dump() for ch, fr in result.results.items()},
    }


# ── agent_reach_internet spec ──────────────────────────────────────────────
AGENT_REACH_INTERNET_SPEC = AgentReachSkillSpec(
    skill_id="agent_reach_internet",
    name="Agent Reach Internet",
    category="internet_access",
    trigger_phrases=[
        "agent reach",
        "internet access",
        "fetch from web",
        "search the web",
        "互联网能力",
        "网络接入",
        "fetch url",
        "read web page",
        "jina reader",
    ],
    function="agent_reach_internet",
    function_ref=_run_agent_reach_skill,
    description=(
        "V5 Chapter 32 — Agent Reach 互联网能力. 14 个渠道统一接入层: "
        "web (JinaReader), twitter, youtube, bilibili, reddit, xiaohongshu, "
        "github (real REST), rss, exa_search, linkedin, instagram, wechat, "
        "douyin, zhihu. 暴露 fetch / search / health_check 三类操作, "
        "支持 TTLCache(max=5000, ttl=300s) + fan-out 并发 + Pydantic v2 schemas."
    ),
    version="5.3.0",
    enabled=True,
    inputs_schema={
        "query": {"type": "string", "description": "Search query / URL / keyword"},
        "channels": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Optional channel subset; defaults to "
                "['exa_search', 'web', 'reddit', 'twitter']"
            ),
        },
    },
    outputs_schema={
        "query": {"type": "string"},
        "channels": {"type": "array", "items": {"type": "string"}},
        "total": {"type": "integer"},
        "success_count": {"type": "integer"},
        "error_count": {"type": "integer"},
        "elapsed_ms": {"type": "number"},
        "results": {
            "type": "object",
            "description": "Dict[channel_name, FetchResult dict]",
        },
    },
    dependencies=[
        "imdf.intelligence.agent_reach.integration.AgentReachIntegration",
        "imdf.intelligence.agent_reach.schemas",
    ],
    author="agent_reach",
    source="imdf.intelligence.agent_reach",
)


AGENT_REACH_SKILLS: List[AgentReachSkillSpec] = [AGENT_REACH_INTERNET_SPEC]
"""Agent Reach skills — 当前只 1 个: agent_reach_internet."""

_AGENT_REACH_BY_ID: Dict[str, AgentReachSkillSpec] = {s.skill_id: s for s in AGENT_REACH_SKILLS}


def list_agent_reach_skills() -> List[AgentReachSkillSpec]:
    """返回所有 Agent Reach skills."""
    return list(AGENT_REACH_SKILLS)


def get_agent_reach_skill(skill_id: str) -> AgentReachSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _AGENT_REACH_BY_ID:
        raise KeyError(f"agent_reach skill not found: {skill_id}")
    return _AGENT_REACH_BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  Security Skill spec (V5 第40章 — P19 v5.4)
# --------------------------------------------------------------------------- #
def _run_security_owasp_protect(*, request: Optional[Dict[str, Any]] = None,
                                 jwt_secret: Optional[str] = None) -> Dict[str, Any]:
    """security_owasp_protect 入口 — 调 OWASPProtection.protect_request.

    Args:
        request:    dict 输入 (user/resource/action/roles/context/inputs/path/url/...)
        jwt_secret: 可选 JWT secret; 不传则 OWASPProtection 默认随机生成

    Returns:
        protect_request 输出 dict (ProtectedRequest.model_dump())
    """
    from imdf.security.owasp_protection import OWASPProtection

    ow = OWASPProtection(jwt_secret=jwt_secret)
    pr = ow.protect_request(request or {})
    return pr.model_dump()


def _run_pii_redact(*, text: str = "",
                    enable_luhn_for_bank: bool = True) -> Dict[str, Any]:
    """pii_redact 入口 — 调 PIIRedactor.redact.

    Args:
        text: 待脱敏文本
        enable_luhn_for_bank: 是否对银行卡做 Luhn 校验 (默认 True)

    Returns:
        redact() 输出 dict (RedactionResult.model_dump())
    """
    from imdf.security.pii_redaction import PIIRedactor

    r = PIIRedactor(enable_luhn_for_bank=enable_luhn_for_bank)
    res = r.redact(text)
    return res.to_dict()


def _run_sso_authenticate(*, action: str = "oauth2_authorize",
                          provider: str = "google",
                          scopes: Optional[List[str]] = None,
                          code: Optional[str] = None,
                          state: Optional[str] = None,
                          dn: Optional[str] = None,
                          password: Optional[str] = None,
                          issuer: Optional[str] = None,
                          request: Optional[Dict[str, Any]] = None,
                          relay_state: Optional[str] = None,
                          ) -> Dict[str, Any]:
    """sso_authenticate 入口 — 统一封装 SSOManager 的 4 类操作.

    action ∈ {"oauth2_authorize", "oauth2_callback", "oidc_discovery",
              "ldap_bind", "saml_initiate", "saml_callback"}
    """
    import asyncio
    from imdf.security.sso import SSOManager

    mgr = SSOManager()
    if action == "oauth2_authorize":
        url = asyncio.run(mgr.oauth2_authorize(provider, scopes=scopes, state=state))
        return {"action": action, "provider": provider, "url": url}
    if action == "oauth2_callback":
        result = asyncio.run(mgr.oauth2_callback(provider, code or "", state=state))
        return {"action": action, **result.model_dump()}
    if action == "oidc_discovery":
        if not issuer:
            raise ValueError("issuer required for oidc_discovery")
        cfg = asyncio.run(mgr.oidc_discovery(issuer))
        return {"action": action, "config": cfg.model_dump()}
    if action == "ldap_bind":
        if not dn or not password:
            raise ValueError("dn + password required for ldap_bind")
        ok = asyncio.run(mgr.ldap_bind(dn, password))
        return {"action": action, "dn": dn, "success": ok}
    if action == "saml_initiate":
        resp = mgr.initiate_saml_login(request=request, relay_state=relay_state)
        if hasattr(resp, "headers"):
            location = resp.headers.get("location", "")
        else:
            location = resp.get("location", "")
        return {"action": action, "redirect_url": location}
    if action == "saml_callback":
        result = asyncio.run(mgr.handle_saml_callback(request or {}))
        return {"action": action, **result.model_dump()}
    raise ValueError(f"unknown sso action: {action}")


def _run_mfa_enforce(*, sub_action: str = "enroll_totp",
                     user_id: str = "demo-user",
                     method: Optional[str] = None,
                     target: Optional[str] = None,
                     code: Optional[str] = None,
                     challenge_id: Optional[str] = None,
                     ) -> Dict[str, Any]:
    """mfa_enforce 入口 — 统一封装 MFAManager 的 enroll/challenge/verify.

    sub_action ∈ {"enroll_totp", "enroll_sms", "enroll_email", "enroll_backup",
                  "challenge", "verify"}
    """
    import asyncio
    from imdf.security.mfa import MFAManager
    from imdf.security.sso_mfa_c2pa_schemas import MFAMethod

    mgr = MFAManager()
    if sub_action == "enroll_totp":
        r = mgr.enroll_totp(user_id)
        return r.model_dump()
    if sub_action == "enroll_sms":
        r = asyncio.run(mgr.enroll_sms(user_id, target or ""))
        return r.model_dump()
    if sub_action == "enroll_email":
        r = asyncio.run(mgr.enroll_email(user_id, target or ""))
        return r.model_dump()
    if sub_action == "enroll_backup":
        r = asyncio.run(mgr.enroll_backup(user_id))
        return r.model_dump()
    if sub_action == "challenge":
        if not method:
            raise ValueError("method required for challenge")
        r = asyncio.run(mgr.challenge(user_id, MFAMethod(method)))
        return r.model_dump()
    if sub_action == "verify":
        if not method or not code:
            raise ValueError("method + code required for verify")
        r = asyncio.run(mgr.verify_mfa(
            user_id, MFAMethod(method), code, challenge_id=challenge_id,
        ))
        return r.model_dump()
    raise ValueError(f"unknown mfa sub_action: {sub_action}")


# --------------------------------------------------------------------------- #
#  V5 FR-8.3 + FR-6.3 - Quality + Labeling Skill specs (P19 v5.5)
# --------------------------------------------------------------------------- #
def _run_aql_inspect(
    *,
    aql_level: str = "1.0",
    lot_size: int = 1000,
    defect_count: int = 0,
    sample_seed: Optional[int] = None,
    lot_assets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """aql_inspect entry - run AQL sampling + inspection in one call.

    Wraps AQLSampling.sample/inspect from imdf.quality.aql_sampling.

    Args:
        aql_level:   one of "0.1"/"0.65"/"1.0"/"1.5"/"2.5"/"4.0"/"6.5"
        lot_size:    configured lot size (drives sample size lookup)
        defect_count: defects observed in the sample (drives accept/reject)
        sample_seed: optional RNG seed for reproducibility
        lot_assets:  optional list of asset dicts to actually sample; if None
                     we synthesize N placeholder Asset records
    """
    import asyncio
    from imdf.labeling.auto_strategy_schemas import AQLLevel, Asset, AssetType
    from imdf.quality.aql_sampling import AQLSampling

    level_enum = AQLLevel(aql_level)
    sampler = AQLSampling(level=level_enum, lot_size=lot_size, seed=sample_seed)

    if lot_assets:
        lot = [Asset.model_validate(a) for a in lot_assets]
    else:
        lot = [
            Asset(
                asset_id=f"synth-{i:05d}",
                asset_type=AssetType.IMAGE,
                caption=f"placeholder {i}",
            )
            for i in range(lot_size)
        ]

    sample = asyncio.run(sampler.sample(lot))
    result = asyncio.run(sampler.inspect(sample, defect_count=defect_count))
    return {
        "aql_level": aql_level,
        "lot_size": lot_size,
        "plan": sampler.plan_summary(),
        "sampled_count": sample.sample_size,
        "sample_lot_id": sample.lot_id,
        "decision": result.decision.value,
        "defects_found": result.defects_found,
        "defect_rate": result.defect_rate,
        "rationale": result.rationale,
        "accept_count_threshold": result.accept_count_threshold,
        "reject_count_threshold": result.reject_count_threshold,
    }


def _run_auto_label_consensus(
    *,
    assets: Optional[List[Dict[str, Any]]] = None,
    consensus_threshold: float = 0.8,
    uncertainty_threshold: float = 0.7,
    asset_count: int = 0,
) -> Dict[str, Any]:
    """auto_label_consensus entry - run 4-strategy auto-labeling on a batch.

    Wraps AutoLabelingOrchestrator.label_batch from
    imdf.labeling.auto_strategy.

    Args:
        assets:               list of asset dicts (asset_id/caption/description/...)
        consensus_threshold:  consensus acceptance threshold (default 0.8)
        uncertainty_threshold: active learning uncertainty threshold (default 0.7)
        asset_count:          when assets is None, synthesize this many records
                              (each gets a long caption to simulate high entropy)
    """
    import asyncio
    from imdf.labeling.auto_strategy import (
        ActiveLearningStrategy,
        AutoLabelingOrchestrator,
        ConsensusStrategy,
    )
    from imdf.labeling.auto_strategy_schemas import Asset, AssetType

    if assets:
        lot = [Asset.model_validate(a) for a in assets]
    else:
        lot = [
            Asset(
                asset_id=f"auto-{i:05d}",
                asset_type=AssetType.IMAGE,
                caption=("x" * 400) if i % 4 == 0 else f"asset caption {i}",
                description=f"generated description {i}",
            )
            for i in range(asset_count or 1)
        ]

    orch = AutoLabelingOrchestrator(
        consensus=ConsensusStrategy(consensus_threshold=consensus_threshold),
        active=ActiveLearningStrategy(uncertainty_threshold=uncertainty_threshold),
    )
    results = asyncio.run(orch.label_batch(lot))

    auto_labeled = [r for r in results if not r.needs_human_review]
    human_review = [r for r in results if r.needs_human_review]

    return {
        "consensus_threshold": consensus_threshold,
        "uncertainty_threshold": uncertainty_threshold,
        "total": len(results),
        "auto_labeled": len(auto_labeled),
        "human_review": len(human_review),
        "auto_label_rate": (len(auto_labeled) / len(results)) if results else 0.0,
        "sample_results": [r.model_dump(mode="json") for r in results[:5]],
    }


AQL_INSPECT_SPEC = AgentReachSkillSpec(
    skill_id="aql_inspect",
    name="AQL Inspect (ISO 2859-1)",
    category="quality",
    trigger_phrases=[
        "aql", "aql inspect", "aql sampling", "iso 2859", "acceptance sampling",
        "质量抽样", "aql 1.0", "aql 0.65", "质量检验", "lot inspection",
        "aql 抽样", "质量等级",
    ],
    function="aql_inspect",
    function_ref=_run_aql_inspect,
    description=(
        "V5 Chapter 8 - AQL (Acceptance Quality Limit) sampling + inspection. "
        "ISO 2859-1 normal inspection, 7 levels (0.1 / 0.65 / 1.0 / 1.5 / 2.5 "
        "/ 4.0 / 6.5). Auto-resolves lot size bucket (10 buckets covering "
        "26-50000) and pulls (sample_size, accept_count, reject_count) from "
        "Table II-A. Random-samples the lot (Fisher-Yates), applies "
        "defects <= Ac -> ACCEPT, defects > Ac -> REJECT. plan_summary() "
        "returns full ISO plan dict for traceability."
    ),
    version="5.5.0",
    enabled=True,
    inputs_schema={
        "aql_level": {
            "type": "string",
            "enum": ["0.1", "0.65", "1.0", "1.5", "2.5", "4.0", "6.5"],
            "description": "AQL level (Acceptable Quality Limit %)",
        },
        "lot_size": {
            "type": "integer",
            "description": "Configured lot size for sample size lookup",
        },
        "defect_count": {
            "type": "integer",
            "description": "Observed defects in the sample (drives decision)",
        },
        "sample_seed": {
            "type": "integer",
            "description": "Optional RNG seed for reproducible sampling",
        },
        "lot_assets": {
            "type": "array",
            "description": (
                "Optional explicit list of asset dicts; if omitted we "
                "synthesize N placeholders."
            ),
        },
    },
    outputs_schema={
        "aql_level": {"type": "string"},
        "lot_size": {"type": "integer"},
        "plan": {
            "type": "object",
            "description": "ISO plan dict: sample_size/Ac/Re/bucket/clamped",
        },
        "sampled_count": {"type": "integer"},
        "sample_lot_id": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["accept", "reject", "hold"],
        },
        "defects_found": {"type": "integer"},
        "defect_rate": {"type": "number"},
        "rationale": {"type": "string"},
        "accept_count_threshold": {"type": "integer"},
        "reject_count_threshold": {"type": "integer"},
    },
    dependencies=[
        "imdf.quality.aql_sampling.AQLSampling",
        "imdf.labeling.auto_strategy_schemas.AQLLevel",
        "imdf.labeling.auto_strategy_schemas.Asset",
    ],
    author="quality",
    source="imdf.quality.aql_sampling",
)


AUTO_LABEL_CONSENSUS_SPEC = AgentReachSkillSpec(
    skill_id="auto_label_consensus",
    name="Auto-Label Consensus (4 Strategies)",
    category="labeling",
    trigger_phrases=[
        "auto label", "consensus labeling", "auto labeling", "active learning",
        "自动打标", "多模态投票", "主动学习", "consensus 0.8",
        "clip zero-shot", "rule based label", "uncertainty review",
        "label consensus", "auto annotate",
    ],
    function="auto_label_consensus",
    function_ref=_run_auto_label_consensus,
    description=(
        "V5 Chapter 6 - 4-strategy auto-labeling (FR-6.3). Strategies: "
        "(1) CLIP zero-shot foundation model, (2) rule-based keyword/regex "
        "matching, (3) active learning with uncertainty routing to human "
        "review, (4) consensus voting of 1+2+3 with default threshold 0.8. "
        "Orchestrator runs base 3 strategies in parallel via asyncio.gather, "
        "then aggregates via Consensus. Returns LabelResult with "
        "strategy_votes + final_label + needs_human_review flag."
    ),
    version="5.5.0",
    enabled=True,
    inputs_schema={
        "assets": {
            "type": "array",
            "description": "Optional list of asset dicts (asset_id/caption/description/...)",
        },
        "consensus_threshold": {
            "type": "number",
            "description": "Consensus acceptance threshold (default 0.8)",
        },
        "uncertainty_threshold": {
            "type": "number",
            "description": "Active learning uncertainty threshold (default 0.7)",
        },
        "asset_count": {
            "type": "integer",
            "description": "When assets is None, synthesize this many records",
        },
    },
    outputs_schema={
        "consensus_threshold": {"type": "number"},
        "uncertainty_threshold": {"type": "number"},
        "total": {"type": "integer"},
        "auto_labeled": {"type": "integer"},
        "human_review": {"type": "integer"},
        "auto_label_rate": {"type": "number"},
        "sample_results": {
            "type": "array",
            "description": "First 5 LabelResult dicts for inspection",
        },
    },
    dependencies=[
        "imdf.labeling.auto_strategy.AutoLabelingOrchestrator",
        "imdf.labeling.auto_strategy.CLIPZeroShotStrategy",
        "imdf.labeling.auto_strategy.RuleBasedStrategy",
        "imdf.labeling.auto_strategy.ActiveLearningStrategy",
        "imdf.labeling.auto_strategy.ConsensusStrategy",
    ],
    author="labeling",
    source="imdf.labeling.auto_strategy",
)


def _run_c2pa_provenance(*, sub_action: str = "sign",
                         asset_b64: Optional[str] = None,
                         claim: Optional[Dict[str, Any]] = None,
                         asset_hash: Optional[str] = None,
                         manifest_dict: Optional[Dict[str, Any]] = None,
                         expected_claim_generator: Optional[str] = None,
                         store_db: Optional[str] = None,
                         ) -> Dict[str, Any]:
    """c2pa_provenance 入口 — 统一封装 C2PA sign/verify/store.

    sub_action ∈ {"sign", "verify", "store_record", "store_get"}
    """
    import asyncio
    import base64 as _b64
    import tempfile as _tf
    import os as _os
    from imdf.security.c2pa import C2PASigner, C2PAStore, C2PAVerifier

    if sub_action == "sign":
        asset = _b64.b64decode(asset_b64 or "")
        signer = C2PASigner(claim_generator=expected_claim_generator or "IMDF-Skill/1.0")
        manifest = asyncio.run(signer.sign_manifest(asset, claim or {}))
        return {"sub_action": sub_action, "manifest": manifest.model_dump(mode="json")}
    if sub_action == "verify":
        asset = _b64.b64decode(asset_b64 or "")
        if not manifest_dict:
            raise ValueError("manifest_dict required for verify")
        from imdf.security.sso_mfa_c2pa_schemas import C2PAManifest
        manifest = C2PAManifest.model_validate(manifest_dict)
        verifier = C2PAVerifier(expected_claim_generator=expected_claim_generator)
        r = asyncio.run(verifier.verify(asset, manifest))
        return {"sub_action": sub_action, "result": r.model_dump()}
    if sub_action == "store_record":
        if not manifest_dict:
            raise ValueError("manifest_dict required for store_record")
        from imdf.security.sso_mfa_c2pa_schemas import C2PAManifest
        manifest = C2PAManifest.model_validate(manifest_dict)
        db = store_db or _os.path.join(_tf.gettempdir(), "imdf_c2pa_skill.sqlite3")
        store = C2PAStore(db_path=db)
        asyncio.run(store.record(manifest))
        return {"sub_action": sub_action, "asset_hash": manifest.asset_hash, "stored": True}
    if sub_action == "store_get":
        if not asset_hash:
            raise ValueError("asset_hash required for store_get")
        db = store_db or _os.path.join(_tf.gettempdir(), "imdf_c2pa_skill.sqlite3")
        store = C2PAStore(db_path=db)
        m = asyncio.run(store.get(asset_hash))
        if m is None:
            return {"sub_action": sub_action, "asset_hash": asset_hash, "manifest": None}
        return {"sub_action": sub_action, "asset_hash": asset_hash, "manifest": m.model_dump(mode="json")}
    raise ValueError(f"unknown c2pa sub_action: {sub_action}")


SECURITY_OWASP_PROTECT_SPEC = AgentReachSkillSpec(
    skill_id="security_owasp_protect",
    name="Security OWASP Protect",
    category="security",
    trigger_phrases=[
        "owasp", "owasp top 10", "security protect", "安全防护",
        "rbac", "abac", "access control", "ssrf", "csrf",
        "injection", "xss", "path traversal",
        "权限校验", "注入防护", "ssrf 防护", "审计事件",
    ],
    function="security_owasp_protect",
    function_ref=_run_security_owasp_protect,
    description=(
        "V5 Chapter 40 — OWASP Top 10 (2021) 完整防护聚合层. 10 个 inner "
        "class: AccessControl (RBAC 6 角色 + ABAC 上下文约束) / Cryptographic "
        "(bcrypt 密码 hash + AES-256-GCM 对称加密) / Injection (SQL/NoSQL/XSS "
        "sanitize + path traversal 拦截) / SecureDesign (RateLimiter + "
        "AuditChain + InputValidator) / SecurityConfig (集中 CONFIG: jwt/ "
        "session/password/rate/cors/upload) / VulnerableComponents "
        "(requirements.txt CVE 检查) / IdentificationAuth (HS256 JWTManager "
        "+ SessionManager 含 5 次失败 lockout) / IntegrityFailures "
        "(HMAC-SHA256 SignatureVerifier + CIArtifactAttestation) / "
        "LoggingMonitoring (SecurityEventLogger → bus topic "
        "\"security.event\") / SSRFProtection (URLValidator 拦截 private/loopback/"
        "link-local + internal hostname). 入口 protect_request(request) → "
        "ProtectedRequest, audit_event(event_type, actor, payload) → SecurityEvent."
    ),
    version="5.4.0",
    enabled=True,
    inputs_schema={
        "request": {
            "type": "object",
            "description": (
                "dict with user/resource/action/roles/context/inputs/path/url/"
                "rate_key/artifact/signature/allowed_roots"
            ),
        },
        "jwt_secret": {
            "type": "string",
            "description": "Optional HS256 JWT signing secret (defaults to random)",
        },
    },
    outputs_schema={
        "user": {"type": "string"},
        "resource": {"type": "string"},
        "action": {"type": "string"},
        "permission": {"type": "object", "description": "PermissionDecision"},
        "sanitized_input": {"type": "object"},
        "safe_path": {"type": "string"},
        "ssrf_checked": {"type": "boolean"},
        "rate_limit_ok": {"type": "boolean"},
        "integrity_ok": {"type": "boolean"},
        "config_snapshot": {"type": "object"},
        "errors": {"type": "array", "items": {"type": "string"}},
    },
    dependencies=[
        "imdf.security.owasp_protection.OWASPProtection",
        "imdf.security.schemas.ProtectedRequest",
        "bcrypt",
        "pyjwt",
        "cryptography.hazmat.primitives.ciphers.aead.AESGCM",
    ],
    author="security",
    source="imdf.security",
)


PII_REDACT_SPEC = AgentReachSkillSpec(
    skill_id="pii_redact",
    name="PII Redact",
    category="security",
    trigger_phrases=[
        "pii", "redact", "desensitize", "脱敏", "去标识化",
        "id card", "phone", "email", "bank card",
        "身份证", "手机号", "邮箱", "银行卡", "姓名地址",
    ],
    function="pii_redact",
    function_ref=_run_pii_redact,
    description=(
        "V5 Chapter 40 — 5 类 PII 脱敏 (无外部 NER 依赖). detectors: "
        "id_card (18 位 GB 11643 正则 + 可选 checksum) / phone (1[3-9]\\d{9}) / "
        "email (标准 RFC email) / bank_card (16-19 位 + Luhn 校验) / "
        "name_address (中文姓名词典 + 地址关键字邻近启发式). redact(text) → "
        "RedactionResult{original_text, redacted_text, detected_pii[], pii_count}. "
        "脱敏策略: 身份证 110101********8811 / 手机 138****8000 / 邮箱 a***@x.com / "
        "银行卡 4111********1111 / 姓名 张* / 地址 北京市[REDACTED]."
    ),
    version="5.4.0",
    enabled=True,
    inputs_schema={
        "text": {"type": "string", "description": "Text to redact"},
        "enable_luhn_for_bank": {
            "type": "boolean",
            "description": "Whether to Luhn-validate bank cards (default true)",
        },
    },
    outputs_schema={
        "original_text": {"type": "string"},
        "redacted_text": {"type": "string"},
        "detected_pii": {
            "type": "array",
            "description": "List of DetectedPII dicts (pii_type/original/redacted/start/end/confidence)",
        },
        "pii_count": {"type": "integer"},
    },
    dependencies=[
        "imdf.security.pii_redaction.PIIRedactor",
        "imdf.security.schemas.RedactionResult",
    ],
    author="security",
    source="imdf.security",
)


# ── V5 第40章 — SSO / MFA / C2PA Skills (P19 v5.4) ───────────────────────
SSO_AUTHENTICATE_SPEC = AgentReachSkillSpec(
    skill_id="sso_authenticate",
    name="SSO Authenticate",
    category="security",
    trigger_phrases=[
        "sso", "saml", "oauth2", "oidc", "ldap",
        "single sign-on", "federation", "idp",
        "单点登录", "身份认证", "联邦认证", "企业 ldap",
        "登录 google", "登录 github", "login with",
    ],
    function="sso_authenticate",
    function_ref=_run_sso_authenticate,
    description=(
        "V5 Chapter 40 — SSO 4 类 provider 统一封装 (SAML / OAuth2 / OIDC / LDAP). "
        "SSOManager 内部 in-memory IdP registry 模拟 google/github/ldap 等; "
        "生产替换时,每个方法体里 _mock_* 调用换成 authlib / python3-saml / ldap3 客户端."
    ),
    version="5.4.0",
    enabled=True,
    inputs_schema={
        "action": {
            "type": "string",
            "enum": [
                "oauth2_authorize", "oauth2_callback",
                "oidc_discovery", "ldap_bind",
                "saml_initiate", "saml_callback",
            ],
            "description": "Which SSO operation to perform",
        },
        "provider": {"type": "string", "description": "OAuth2 provider name (google/github/...)"},
        "scopes": {"type": "array", "items": {"type": "string"}},
        "code": {"type": "string"},
        "state": {"type": "string"},
        "dn": {"type": "string", "description": "LDAP distinguished name"},
        "password": {"type": "string"},
        "issuer": {"type": "string", "description": "OIDC issuer URL"},
        "request": {"type": "object", "description": "For SAML callback"},
        "relay_state": {"type": "string"},
    },
    outputs_schema={
        "action": {"type": "string"},
        "url": {"type": "string"},
        "redirect_url": {"type": "string"},
        "config": {"type": "object"},
        "success": {"type": "boolean"},
        "user_id": {"type": "string"},
        "email": {"type": "string"},
        "access_token": {"type": "string"},
        "refresh_token": {"type": "string"},
        "id_token": {"type": "string"},
    },
    dependencies=[
        "imdf.security.sso.SSOManager",
        "imdf.security.sso_mfa_c2pa_schemas.AuthResult",
        "imdf.security.sso_mfa_c2pa_schemas.OIDCConfig",
    ],
    author="security",
    source="imdf.security.sso",
)


MFA_ENFORCE_SPEC = AgentReachSkillSpec(
    skill_id="mfa_enforce",
    name="MFA Enforce",
    category="security",
    trigger_phrases=[
        "mfa", "2fa", "totp", "two-factor", "多因子",
        "双因素", "二次验证", "动态口令", "google authenticator",
        "authy", "短信验证码", "邮件验证码", "备份码",
    ],
    function="mfa_enforce",
    function_ref=_run_mfa_enforce,
    description=(
        "V5 Chapter 40 — MFA 4 类方法 (TOTP RFC 6238 / SMS OTP / Email OTP / "
        "Backup codes). MFAManager 内部 in-memory state; OTP / TOTP secret 不落盘. "
        "TOTP 自包含实现 (不依赖 pyotp): HMAC-SHA1, 30s timestep, 6 digits, "
        "±window=1 漂移容忍. 生产替换 SMS/Email 用 twilio/SES client."
    ),
    version="5.4.0",
    enabled=True,
    inputs_schema={
        "sub_action": {
            "type": "string",
            "enum": [
                "enroll_totp", "enroll_sms", "enroll_email", "enroll_backup",
                "challenge", "verify",
            ],
        },
        "user_id": {"type": "string"},
        "method": {
            "type": "string",
            "enum": ["totp", "sms", "email", "backup"],
        },
        "target": {"type": "string", "description": "phone or email address"},
        "code": {"type": "string", "description": "User-supplied OTP / TOTP / backup code"},
        "challenge_id": {"type": "string"},
    },
    outputs_schema={
        "success": {"type": "boolean"},
        "method": {"type": "string"},
        "secret": {"type": "string"},
        "provisioning_uri": {"type": "string"},
        "challenge_id": {"type": "string"},
        "delivery_target": {"type": "string"},
        "backup_codes": {"type": "array", "items": {"type": "string"}},
        "remaining_backup_codes": {"type": "integer"},
        "consumed": {"type": "boolean"},
        "error": {"type": "string"},
    },
    dependencies=[
        "imdf.security.mfa.MFAManager",
        "imdf.security.sso_mfa_c2pa_schemas.EnrollmentResult",
        "imdf.security.sso_mfa_c2pa_schemas.ChallengeResult",
        "imdf.security.sso_mfa_c2pa_schemas.VerificationResult",
    ],
    author="security",
    source="imdf.security.mfa",
)


C2PA_PROVENANCE_SPEC = AgentReachSkillSpec(
    skill_id="c2pa_provenance",
    name="C2PA Provenance",
    category="security",
    trigger_phrases=[
        "c2pa", "content provenance", "provenance", "content authenticity",
        "内容溯源", "内容来源", "数字签名", "ed25519",
        "asset signature", "content credential",
    ],
    function="c2pa_provenance",
    function_ref=_run_c2pa_provenance,
    description=(
        "V5 Chapter 40 — C2PA 1.4 (subset) 内容来源 + Ed25519 签名. C2PASigner 用 "
        "Ed25519 (cryptography lib) 对 canonical manifest 签名;C2PAVerifier 校验 "
        "signature / asset_hash / claim_generator / time_window 4 件事;C2PAStore "
        "用 SQLite (fallback JSON) 持久化 manifest. 与 engines/c2pa_engine.py 的 "
        "RSA-PSS 路径互补 — 本模块专注 Ed25519 快速验证场景."
    ),
    version="5.4.0",
    enabled=True,
    inputs_schema={
        "sub_action": {
            "type": "string",
            "enum": ["sign", "verify", "store_record", "store_get"],
        },
        "asset_b64": {"type": "string", "description": "Asset bytes base64-encoded"},
        "claim": {"type": "object", "description": "Free-form claim payload"},
        "manifest_dict": {"type": "object"},
        "asset_hash": {"type": "string"},
        "expected_claim_generator": {"type": "string"},
        "store_db": {"type": "string"},
    },
    outputs_schema={
        "sub_action": {"type": "string"},
        "manifest": {"type": "object"},
        "result": {"type": "object"},
        "asset_hash": {"type": "string"},
        "stored": {"type": "boolean"},
    },
    dependencies=[
        "imdf.security.c2pa.C2PASigner",
        "imdf.security.c2pa.C2PAVerifier",
        "imdf.security.c2pa.C2PAStore",
        "imdf.security.sso_mfa_c2pa_schemas.C2PAManifest",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
    ],
    author="security",
    source="imdf.security.c2pa",
)


SECURITY_SKILLS: List[AgentReachSkillSpec] = [
    SECURITY_OWASP_PROTECT_SPEC,
    PII_REDACT_SPEC,
    SSO_AUTHENTICATE_SPEC,
    MFA_ENFORCE_SPEC,
    C2PA_PROVENANCE_SPEC,
]
"""V5 第40章 Security skills — 5 个: security_owasp_protect + pii_redact + sso_authenticate + mfa_enforce + c2pa_provenance."""

_SECURITY_BY_ID: Dict[str, AgentReachSkillSpec] = {s.skill_id: s for s in SECURITY_SKILLS}


def list_security_skills() -> List[AgentReachSkillSpec]:
    """返回所有 Security skills."""
    return list(SECURITY_SKILLS)


def get_security_skill(skill_id: str) -> AgentReachSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _SECURITY_BY_ID:
        raise KeyError(f"security skill not found: {skill_id}")
    return _SECURITY_BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  V5 FR-3.2 + FR-7.4 — Labeling / Export Skills (P19 v5.5)
# --------------------------------------------------------------------------- #
def _run_export_createml(*, dataset: Any = None, output_path: str = "",
                         classes: Optional[List[str]] = None) -> Dict[str, Any]:
    """export_createml skill entry — wraps CreateMLExporter.

    Args:
        dataset:    DatasetVersion-like (has ``.files`` list). Optional —
                    if None, returns metadata only.
        output_path: Output directory root (defaults to temp dir).
        classes:    Optional override of class names.

    Returns:
        ExportResult.to_dict() payload.
    """
    from imdf.exports.create_ml_exporter import CreateMLExporter
    import asyncio as _asyncio
    import tempfile as _tf

    if not output_path:
        output_path = _tf.mkdtemp(prefix="p19v55_createml_skill_")
    exporter = CreateMLExporter(classes=classes) if classes else CreateMLExporter()
    if dataset is None:
        return {
            "format": exporter.FORMAT_NAME,
            "output_path": output_path,
            "files_written": [],
            "metadata": {"note": "no dataset supplied; metadata only"},
            "bytes_total": 0,
        }
    result = _asyncio.run(exporter.export(dataset, output_path))
    return result.to_dict()


def _run_label_geometry_3d(*, geometry_type: str = "3d_bbox",
                           data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """label_geometry_3d skill entry — wraps 4 Pydantic v2 geometry models.

    Args:
        geometry_type: One of ``3d_cuboid`` / ``lidar_pointcloud`` / ``3d_bbox`` / ``panoptic``.
        data:          Payload to validate (defaults provided for each type if absent).

    Returns:
        Dict with keys ``geometry_type``, ``valid``, ``payload`` (model_dump)
        and ``rendered_bytes_len`` (PNG mock byte count).
    """
    from imdf.labeling.geometries import (
        BBox3D,
        Cuboid3D,
        LiDARPoint,
        PanopticSegmentation,
        PointCloudLiDAR,
        Vec3,
        Dimensions3D,
        Quaternion,
        GEOMETRY_REGISTRY,
    )

    gtype = geometry_type.lower().strip()
    if gtype not in GEOMETRY_REGISTRY:
        return {
            "valid": False,
            "error": f"unknown geometry_type {geometry_type!r}",
            "supported": list(GEOMETRY_REGISTRY.keys()),
        }

    payload = data or {}

    try:
        if gtype == "3d_cuboid":
            center = payload.get("center") or {"x": 0.0, "y": 0.0, "z": 0.0}
            dims = payload.get("dimensions") or {"length": 1.0, "width": 1.0, "height": 1.0}
            corners_in = payload.get("corners") or [
                {"x": float(i) * 0.1, "y": 0.0, "z": 0.0} for i in range(8)
            ]
            model = Cuboid3D(
                label=payload.get("label", "object"),
                center=center,
                dimensions=dims,
                corners=corners_in,
            )
        elif gtype == "lidar_pointcloud":
            pts_in = payload.get("points") or [
                {"x": 0.0, "y": 0.0, "z": 0.0, "intensity": 0.5},
            ]
            model = PointCloudLiDAR(
                frame_id=payload.get("frame_id", "frame_0000"),
                points=pts_in,
                sensor_id=payload.get("sensor_id"),
            )
        elif gtype == "3d_bbox":
            model = BBox3D(
                label=payload.get("label", "object"),
                center=payload.get("center") or {"x": 0.0, "y": 0.0, "z": 0.0},
                x_size=payload.get("x_size", 1.0),
                y_size=payload.get("y_size", 1.0),
                z_size=payload.get("z_size", 1.0),
                confidence=payload.get("confidence", 1.0),
            )
        elif gtype == "panoptic":
            mask_in = payload.get("mask") or [[0, 1], [1, 0]]
            model = PanopticSegmentation(
                image_id=payload.get("image_id", "img_0000"),
                instance_id=payload.get("instance_id", 0),
                class_id=payload.get("class_id", 1),
                class_name=payload.get("class_name", "object"),
                is_thing=payload.get("is_thing", False),
                mask=mask_in,
            )
        else:  # pragma: no cover — GEOMETRY_REGISTRY gate covers all 4
            return {"valid": False, "error": "unreachable"}
    except Exception as exc:
        return {"valid": False, "error": str(exc), "geometry_type": gtype}

    # Render to PNG mock bytes (size only — actual bytes handled by renderer)
    from imdf.labeling.geometry_renderers import (
        BBox3DRenderer,
        Cuboid3DRenderer,
        PanopticRenderer,
        PointCloudLiDARRenderer,
    )
    renderer_map = {
        "3d_cuboid": (Cuboid3DRenderer, lambda m: Cuboid3DRenderer().render(m)),
        "lidar_pointcloud": (PointCloudLiDARRenderer, lambda m: PointCloudLiDARRenderer().render(m)),
        "3d_bbox": (BBox3DRenderer, lambda m: BBox3DRenderer().render(m)),
        "panoptic": (PanopticRenderer, lambda m: PanopticRenderer().render(m)),
    }
    cls, fn = renderer_map[gtype]
    rendered = fn(model)
    return {
        "valid": True,
        "geometry_type": gtype,
        "renderer": cls.__name__,
        "payload": json.loads(model.model_dump_json()),
        "rendered_bytes_len": len(rendered),
    }


EXPORT_CREATEML_SPEC = AgentReachSkillSpec(
    skill_id="export_createml",
    name="CreateML Exporter",
    category="export",
    trigger_phrases=[
        "createml", "create ml", "apple vision", "annotation json",
        "训练格式导出", "createml json",
    ],
    function="export_createml",
    function_ref=_run_export_createml,
    description=(
        "V5 FR-3.2 — Apple CreateML annotation exporter. Writes one JSON per image "
        "under ``<output_path>/annotations/<idx>.json`` (CreateML schema) plus a "
        "manifest.json. Class-based async API (CreateMLExporter); empty datasets "
        "gracefully produce manifest-only output. Compatible with Apple's Vision "
        "framework CreateML UI tool."
    ),
    version="5.5.0",
    enabled=True,
    inputs_schema={
        "dataset": {"type": "object", "description": "DatasetVersion-like (has .files)"},
        "output_path": {"type": "string", "description": "Output directory root"},
        "classes": {"type": "array", "items": {"type": "string"},
                    "description": "Optional class names override"},
    },
    outputs_schema={
        "format": {"type": "string"},
        "output_path": {"type": "string"},
        "files_written": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object"},
        "bytes_total": {"type": "integer"},
    },
    dependencies=[
        "imdf.exports.create_ml_exporter.CreateMLExporter",
    ],
    author="export",
    source="imdf.exports.create_ml_exporter",
)


LABEL_GEOMETRY_3D_SPEC = AgentReachSkillSpec(
    skill_id="label_geometry_3d",
    name="3D Geometry Labeling",
    category="labeling",
    trigger_phrases=[
        "3d cuboid", "lidar", "point cloud", "3d bbox", "panoptic",
        "3D 标注", "点云", "3D 框", "全景分割",
        "geometry 3d", "3d label",
    ],
    function="label_geometry_3d",
    function_ref=_run_label_geometry_3d,
    description=(
        "V5 FR-7.4 — 4 3D geometry Pydantic v2 models (Cuboid3D / PointCloudLiDAR / "
        "BBox3D / PanopticSegmentation) with deterministic mock PNG renderers. "
        "Validate arbitrary payload against the chosen geometry type and emit "
        "JSON-serializable payload + PNG byte count."
    ),
    version="5.5.0",
    enabled=True,
    inputs_schema={
        "geometry_type": {
            "type": "string",
            "enum": ["3d_cuboid", "lidar_pointcloud", "3d_bbox", "panoptic"],
        },
        "data": {"type": "object",
                 "description": "Geometry payload (uses default if absent)"},
    },
    outputs_schema={
        "valid": {"type": "boolean"},
        "geometry_type": {"type": "string"},
        "renderer": {"type": "string"},
        "payload": {"type": "object"},
        "rendered_bytes_len": {"type": "integer"},
        "error": {"type": "string"},
    },
    dependencies=[
        "imdf.labeling.geometries",
        "imdf.labeling.geometry_renderers",
    ],
    author="labeling",
    source="imdf.labeling.geometries",
)


LABELING_EXPORT_SKILLS: List[AgentReachSkillSpec] = [
    EXPORT_CREATEML_SPEC,
    LABEL_GEOMETRY_3D_SPEC,
]
"""V5 FR-3.2 + FR-7.4 — 2 new Skills: export_createml + label_geometry_3d (P19 v5.5)."""

_LABELING_EXPORT_BY_ID: Dict[str, AgentReachSkillSpec] = {
    s.skill_id: s for s in LABELING_EXPORT_SKILLS
}


def list_labeling_export_skills() -> List[AgentReachSkillSpec]:
    """返回所有 V5 FR-3.2 + FR-7.4 Skills."""
    return list(LABELING_EXPORT_SKILLS)


def get_labeling_export_skill(skill_id: str) -> AgentReachSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _LABELING_EXPORT_BY_ID:
        raise KeyError(f"labeling/export skill not found: {skill_id}")
    return _LABELING_EXPORT_BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  Quality + Labeling skills list (V5 第8章 + 第6章 — P19 v5.5)
# --------------------------------------------------------------------------- #
QUALITY_SKILLS: List[AgentReachSkillSpec] = [
    AQL_INSPECT_SPEC,
    AUTO_LABEL_CONSENSUS_SPEC,
]
"""V5 FR-8.3 + FR-6.3 — Quality + Labeling skills. 2 个: aql_inspect + auto_label_consensus."""

_QUALITY_BY_ID: Dict[str, AgentReachSkillSpec] = {s.skill_id: s for s in QUALITY_SKILLS}


def list_quality_skills() -> List[AgentReachSkillSpec]:
    """返回所有 Quality + Labeling skills."""
    return list(QUALITY_SKILLS)


def get_quality_skill(skill_id: str) -> AgentReachSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _QUALITY_BY_ID:
        raise KeyError(f"quality skill not found: {skill_id}")
    return _QUALITY_BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  Octo Skill spec (V5 第25章 — P19 v5.3)
# --------------------------------------------------------------------------- #
@dataclass
class OctoSkillSpec:
    """Octo 单 Skill 规格 — 4 概念协作网络封装.

    与 RedFox/Vida/AgentReach 同构 — 方便统一查询接口.
    """

    skill_id: str
    name: str
    category: str
    trigger_phrases: List[str]
    function: str
    function_ref: Callable[..., Any]
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    inputs_schema: Dict[str, Any] = field(default_factory=dict)
    outputs_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    author: str = "octo"
    source: str = "imdf.engines.octo_engine"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "trigger_phrases": list(self.trigger_phrases),
            "function": self.function,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "inputs_schema": dict(self.inputs_schema),
            "outputs_schema": dict(self.outputs_schema),
            "dependencies": list(self.dependencies),
            "author": self.author,
            "source": self.source,
        }


# ── Octo factory + function_ref ────────────────────────────────────────────
from engines.octo_engine import OctoEngine  # noqa: E402  (lazy to keep module load cheap)


def _octo_collaborate(
    *,
    request: str = "",
    skill_engine: Any = None,
    bus: Any = None,
) -> Dict[str, Any]:
    """octo_collaborate 入口 — 启动一个 OctoEngine 跑一个最小协作循环.

    简化的 V5 ch.25 demo: 创建 1 个 generic bot + 1 个 channel, post 1
    条 request 消息, 然后 list 全部 bots/channels/messages.  真实业务
    调用方应该自己 hold 住一个 OctoEngine 实例, 然后调用 create_bot/
    create_channel/... 走完整业务流.
    """
    eng = OctoEngine(skill_engine=skill_engine, bus=bus)
    bot_id = eng.create_bot("OctoBot", agent_type="generic", capabilities=["octo"])
    ch_id = eng.create_channel(
        "Octo Channel",
        description="auto-created by octo_collaborate skill",
        members=[bot_id, "user_default"],
    )
    msg = eng.post_message(ch_id, "user_default", request or "ping")
    return {
        "engine_status": eng.status(),
        "bot_id": bot_id,
        "channel_id": ch_id,
        "message_id": msg.id if msg else None,
        "bots": [b.to_dict() for b in eng.list_bots()],
        "channels": [c.to_dict() for c in eng.list_channels()],
    }


# ── octo_collaborate spec ────────────────────────────────────────────────
OCTO_COLLABORATE_SPEC = OctoSkillSpec(
    skill_id="octo_collaborate",
    name="Octo Agent Collaboration",
    category="collaboration",
    trigger_phrases=[
        "octo", "octo collaborate", "agent network", "bot channel",
        "协作网络", "Bot 协作", "多 Agent", "octo_collaborate",
    ],
    function="octo_collaborate",
    function_ref=_octo_collaborate,
    description=(
        "V5 Chapter 25 — Octo Agent 协作网络. 把 chat 变成 action, 把 "
        "action 变成 deliverable. 4 概念模型: Bot (Agent 身份) + "
        "Channel (项目团队/工作区) + Thread (具体事件上下文) + Matter "
        "(交付物). 支持 6 种 default prompt (coder/reviewer/writer/"
        "analyst/researcher/generic), 6 个 bus topic (octo.bot/channel/"
        "matter_created, octo.matter_assigned, octo.matter_completed, "
        "octo.message_posted), 通过 skill_engine 绑定技能, 通过 bus "
        "暴露事件."
    ),
    version="5.3.0",
    enabled=True,
    inputs_schema={
        "request": {"type": "string", "description": "User's free-form request"},
        "skill_engine": {"type": "object", "description": "Optional SkillEngineLike"},
        "bus": {"type": "object", "description": "Optional EventBus"},
    },
    outputs_schema={
        "engine_status": {"type": "object", "description": "OctoEngine.status()"},
        "bot_id": {"type": "string", "description": "Created bot id"},
        "channel_id": {"type": "string", "description": "Created channel id"},
        "message_id": {"type": "string", "description": "Posted message id or null"},
        "bots": {"type": "array", "description": "All bots in the engine"},
        "channels": {"type": "array", "description": "All channels in the engine"},
    },
    dependencies=[
        "imdf.engines.octo_engine.OctoEngine",
        "imdf.engines.octo_schemas",
        "imdf.engines.octo_kb",
        "imdf.orchestration.bus.EventBus",
    ],
    author="octo",
    source="imdf.engines.octo_engine",
)


OCTO_SKILLS: List[OctoSkillSpec] = [OCTO_COLLABORATE_SPEC]
"""Octo skills — 当前 1 个: octo_collaborate."""
_OCTO_BY_ID: Dict[str, OctoSkillSpec] = {s.skill_id: s for s in OCTO_SKILLS}


def list_octo_skills() -> List[OctoSkillSpec]:
    """返回所有 Octo skills."""
    return list(OCTO_SKILLS)


def get_octo_skill(skill_id: str) -> OctoSkillSpec:
    """按 skill_id 查找; 不存在抛 KeyError."""
    if skill_id not in _OCTO_BY_ID:
        raise KeyError(f"octo skill not found: {skill_id}")
    return _OCTO_BY_ID[skill_id]


# --------------------------------------------------------------------------- #
#  Crowdsource + CDP Billing Skill specs (V5 §13.4 — Chapter 17 + 22, P19 v5.6)
# --------------------------------------------------------------------------- #
def _run_cdp_billing_invoice(*,
                             tenant_id: str = "demo-tenant",
                             metric: Optional[str] = None,
                             value: float = 0.0,
                             period_start: Optional[str] = None,
                             period_end: Optional[str] = None,
                             generate_pdf: bool = False,
                             list_invoices: bool = False,
                             ) -> Dict[str, Any]:
    """cdp_billing_invoice 入口 — 封装 CDPBillingService.

    Action args:
        tenant_id       — 租户
        metric          — 可选, 指定即跟踪用量
        value           — 可选, 用量值
        period_start    — 可选, ISO date, 计算发票需配合 period_end
        period_end      — 可选, ISO date
        generate_pdf    — 可选, 同时渲染 invoice 到 PDF bytes
        list_invoices   — 可选, 列出该 tenant 所有发票
    """
    import asyncio as _asyncio
    from datetime import date as _date
    from billing.cdp_billing import CDPBillingService

    svc = CDPBillingService()
    out: Dict[str, Any] = {"tenant_id": tenant_id, "actions_run": []}
    if metric:
        async def _track():
            return await svc.track_usage(tenant_id, metric, value)
        rec = _asyncio.run(_track())
        out["actions_run"].append("track_usage")
        out["usage"] = rec.model_dump(mode="json")
    if period_start and period_end:
        ps = _date.fromisoformat(period_start)
        pe = _date.fromisoformat(period_end)
        async def _invoice():
            return await svc.calculate_invoice(tenant_id, ps, pe)
        inv = _asyncio.run(_invoice())
        out["actions_run"].append("calculate_invoice")
        out["invoice"] = inv.model_dump(mode="json")
        if generate_pdf:
            async def _pdf():
                return await svc.generate_invoice_pdf(inv)
            pdf = _asyncio.run(_pdf())
            out["actions_run"].append("generate_invoice_pdf")
            out["pdf_bytes"] = len(pdf)
            out["pdf_is_pdf_format"] = pdf.startswith(b"%PDF-")
    if list_invoices:
        async def _list():
            return await svc.list_invoices(tenant_id)
        invs = _asyncio.run(_list())
        out["actions_run"].append("list_invoices")
        out["invoices"] = [i.model_dump(mode="json") for i in invs]
    return out


def _run_crowdsource_manage(*,
                             action: str = "list_tasks",
                             task_id: Optional[str] = None,
                             worker_id: Optional[str] = None,
                             ) -> Dict[str, Any]:
    """crowdsource_manage 入口 — V5 §13.4 占位封装.

    在 P19 v5.6 阶段暴露一个稳定 mock action 接口供前端 / 其他 skill 调用,
    v5.7 会接 imdf/business/crowdsource.py 的真实数据库实现.
    """
    return {
        "action": action,
        "task_id": task_id,
        "worker_id": worker_id,
        "status": "stub",
        "note": (
            "V5 §13.4 placeholder. P19 v5.7 will wrap "
            "imdf.business.crowdsource.CrowdsourceService."
        ),
    }


CDP_BILLING_INVOICE_SPEC = OctoSkillSpec(
    skill_id="cdp_billing_invoice",
    name="CDP Billing Invoice",
    category="billing",
    trigger_phrases=[
        "cdp", "cdp billing", "customer data platform", "billing invoice",
        "tier discount", "calculate invoice", "track usage",
        "计费", "出账", "tier_1", "tier_2", "tier_3",
        "subtotal", "total invoice", "月账单",
    ],
    function="cdp_billing_invoice",
    function_ref=_run_cdp_billing_invoice,
    description=(
        "V5 Chapter 22 / §13.4 — CDP 高级计费 (CDPBillingService 包装)."
        " 支持 track_usage (按 metric + value 记录租户用量),"
        " calculate_invoice (按 [period_start, period_end) 月度账单生成,"
        " 多档位 [tier_1/2/3] 阶梯折扣自动应用),"
        " generate_invoice_pdf (reportlab, 失败降级 HTML),"
        " list_invoices (按 tenant 查找所有历史发票)."
        " 配合 FastAPI 4 个端点 (POST /usage, POST /invoice, GET /invoices, GET /invoice/{id}/pdf)."
    ),
    version="5.6.0",
    enabled=True,
    inputs_schema={
        "tenant_id": {"type": "string"},
        "metric": {"type": "string", "description": "如 api_calls / storage_gb / render_minutes"},
        "value": {"type": "number"},
        "period_start": {"type": "string", "description": "ISO date YYYY-MM-DD"},
        "period_end": {"type": "string"},
        "generate_pdf": {"type": "boolean"},
        "list_invoices": {"type": "boolean"},
    },
    outputs_schema={
        "tenant_id": {"type": "string"},
        "actions_run": {"type": "array", "items": {"type": "string"}},
        "usage": {"type": "object"},
        "invoice": {"type": "object"},
        "invoices": {"type": "array"},
        "pdf_bytes": {"type": "integer"},
        "pdf_is_pdf_format": {"type": "boolean"},
    },
    dependencies=[
        "billing.cdp_billing.CDPBillingService",
        "billing.cdp_billing_schemas",
        "reportlab",
    ],
    author="cdp",
    source="billing.cdp_billing",
)


CROWDSOURCE_MANAGE_SPEC = OctoSkillSpec(
    skill_id="crowdsource_manage",
    name="Crowdsource Manage",
    category="crowdsource",
    trigger_phrases=[
        "crowdsource", "crowdsourcing", "众包", "标注工人", "task pool",
        "worker pool", "quality score", "worker", "annotator", "task assignment",
        "annotation management", "标注任务", "工人管理", "质检评分",
    ],
    function="crowdsource_manage",
    function_ref=_run_crowdsource_manage,
    description=(
        "V5 Chapter 17 / §13.4 — Crowdsourcing Management Full Version."
        " 4 个管理模块: Tasks (任务池 — id / title / status / workers_count / payment / deadline),"
        " Workers (工人花名册 — id / name / completed_tasks / quality_score / earnings),"
        " Payments (支付 — id / worker / amount / status),"
        " Quality (质量分布 — quality_score 直方图)."
        " P19 v5.6 先暴露稳定 mock action 接口 (.stub),"
        " 后续在 v5.7 接 imdf/business/crowdsource.py 实际数据库."
        " 前端对应 /admin/crowdsource (CrowdsourceAdmin.vue)."
    ),
    version="5.6.0",
    enabled=True,
    inputs_schema={
        "action": {
            "type": "string",
            "enum": ["list_tasks", "list_workers", "list_payments", "quality_dist"],
        },
        "task_id": {"type": "string"},
        "worker_id": {"type": "string"},
    },
    outputs_schema={
        "action": {"type": "string"},
        "task_id": {"type": "string"},
        "worker_id": {"type": "string"},
        "status": {"type": "string"},
        "note": {"type": "string"},
    },
    dependencies=[
        "imdf.business.crowdsource (planned P19 v5.7)",
        "frontend-v2/src/components/CrowdsourceAdmin.vue",
    ],
    author="crowdsource",
    source="imdf.business.crowdsource",
)


# Group CDP + Crowdsource skills under the same OctoSkillSpec umbrella —
# keeps a single `list_octo_skills`-shaped query but stable IDs.
_OCTO_BY_ID.update({
    "cdp_billing_invoice": CDP_BILLING_INVOICE_SPEC,
    "crowdsource_manage": CROWDSOURCE_MANAGE_SPEC,
})
OCTO_SKILLS = list(_OCTO_BY_ID.values())
"""Octo skills list now includes cdp_billing_invoice + crowdsource_manage (P19 v5.6)."""


__all__ = [
    "RedFoxSkillSpec",
    "REDFOX_SKILLS",
    "list_redfox_skills",
    "get_redfox_skill",
    "VidaSkillSpec",
    "VIDA_SKILLS",
    "VIDA_PROACTIVE_ASSIST_SPEC",
    "list_vida_skills",
    "get_vida_skill",
    "AgentReachSkillSpec",
    "AGENT_REACH_SKILLS",
    "AGENT_REACH_INTERNET_SPEC",
    "list_agent_reach_skills",
    "get_agent_reach_skill",
    "OctoSkillSpec",
    "OCTO_SKILLS",
    "OCTO_COLLABORATE_SPEC",
    "CDP_BILLING_INVOICE_SPEC",
    "CROWDSOURCE_MANAGE_SPEC",
    "list_octo_skills",
    "get_octo_skill",
    "SECURITY_OWASP_PROTECT_SPEC",
    "PII_REDACT_SPEC",
    "SSO_AUTHENTICATE_SPEC",
    "MFA_ENFORCE_SPEC",
    "C2PA_PROVENANCE_SPEC",
    "SECURITY_SKILLS",
    "list_security_skills",
    "get_security_skill",
    "AQL_INSPECT_SPEC",
    "AUTO_LABEL_CONSENSUS_SPEC",
    "QUALITY_SKILLS",
    "list_quality_skills",
    "get_quality_skill",
    "_run_vida_skill",
    "_vida_proactive_assist",
    "_run_agent_reach_skill",
    "_octo_collaborate",
    "_run_security_owasp_protect",
    "_run_pii_redact",
    "_run_sso_authenticate",
    "_run_mfa_enforce",
    "_run_c2pa_provenance",
    "_run_aql_inspect",
    "_run_auto_label_consensus",
    "_run_cdp_billing_invoice",
    "_run_crowdsource_manage",
] 