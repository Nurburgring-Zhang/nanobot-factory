"""P4-8-W1: VDP-2026 extended_skills package.

The ``skills`` package is the second-generation skill framework built on top
of P4-3-W1's agent_service.  While P3-3-W1 introduced 15 agent *types* and
P4-3-W1 added tools/instructions/sessions, this module layers:

  * ``Skill`` ABC + ``@skill`` decorator (base.py)
  * ``SkillContext`` (context.py)         — per-call state + blackboard + memory
  * ``SkillResult`` (result.py)           — data + logs + artifacts
  * ``SkillRegistry`` (registry.py)       — name+version catalog
  * ``SkillOrchestrator`` (orchestrator.py)— task routing, chaining, retry/fallback
  * 10 built-in skills (``builtin/``)     — borrows 10 open-source patterns
  * ``ClaudeObsidianView`` (obsidian/)    — wiki + LLM auto KB
  * ``SkillMarketplace`` (marketplace.py) — install + rate + community
  * FastAPI router (``api.py``)           — mounted on agent_service

Borrowed from
-------------
  * Awesome-GPT-Image-Prompts   (image prompt library + categories)
  * awesome-claude-skills       (skill registry / decorator pattern)
  * guizangPPTX                 (idea → PPT outline + slide deck)
  * guizang-social-card         (text → social card)
  * humanizer-zh                (AI-voice → human voice)
  * deep-research-mcp           (cited web research)
  * anything-to-notebooklm      (source → multi-format summary)
  * WeWrite                     (one-stop public-account writing)
  * youtube-clipper             (long-video → short clips)
  * oh-story-claudecode         (web-novel topic mining)
  * marketingskills             (marketing toolkit)
  * claude-obsidian-view        (7200★, wiki-link + LLM auto KB)
  * Karpathy LLM Wiki           (3-pane layout inspiration)

Design notes
------------
* Skills are stateful objects (the orchestrator instantiates them once and
  caches); only the ``SkillContext`` is per-call.  This matches the way
  ``BaseExtendedSkill`` works in the older ``extended_skills_pkg`` and keeps
  a single LLM client / cache hot across calls.
* Mock mode (no LLM configured) returns deterministic placeholder output
  marked with ``SkillResult.metadata.mock = True`` so tests can assert.
  Production deployments inject an LLM via ``set_llm``.
* Errors fall back through ``SkillOrchestrator.run_with_fallback`` —
  retry → next skill in list → skip, so a flaky PPT generator does not
  cascade into the rest of the chain.

Endpoints
---------
* ``/api/v1/skills``                — list / search skills
* ``/api/v1/skills/{name}``         — skill detail
* ``/api/v1/skills/{name}/run``     — execute a skill
* ``/api/v1/skills/{name}/install`` — install community skill
* ``/api/v1/skills/{name}/rate``    — submit rating
* ``/api/v1/skills/orchestrator/run``— run a skill chain
* ``/api/v1/obsidian/wiki``         — wiki CRUD
* ``/api/v1/obsidian/wiki/{slug}``  — wiki detail
* ``/api/v1/obsidian/wiki/{slug}/backlinks`` — backlinks
* ``/api/v1/obsidian/wiki/graph``   — knowledge graph
* ``/api/v1/obsidian/llm_kb/ingest``— LLM auto KB ingest
"""
from __future__ import annotations

from backend.skills.legacy import (
    BaseSkill,
    BatchProductionSkill,
    DataAnalysisSkill,
    MediaProductionSkill,
    PromptGenerationSkill,
    PromptOptimizationSkill,
    SkillInput,
    SkillManager,
    SkillOutput,
    get_skill_manager,
)

# V5.1 (P19 v5.1-B) — 显式从本文件直接定义 SkillSpec,绕过 skills.py 的 shadow
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillSpec:
    """
    V5.1 附录 D — Skill 规格描述 (与 backend/skills.py 同源)

    与 ``SkillInput/SkillOutput`` 不同,这里只描述元数据/接口契约,
    不涉及具体执行逻辑。便于 registry / executor / builtin 工厂统一管理。
    """
    id: str
    name: str
    category: str
    trigger_phrases: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True
    version: str = "1.0.0"
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "trigger_phrases": list(self.trigger_phrases),
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "description": self.description,
            "enabled": self.enabled,
            "version": self.version,
            "dependencies": list(self.dependencies),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillSpec":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            category=data.get("category", "general"),
            trigger_phrases=list(data.get("trigger_phrases", [])),
            inputs=dict(data.get("inputs", {})),
            outputs=dict(data.get("outputs", {})),
            description=data.get("description", ""),
            enabled=bool(data.get("enabled", True)),
            version=data.get("version", "1.0.0"),
            dependencies=list(data.get("dependencies", [])),
        )


# Alias: 任务要求 class 名 `Skill`,但已有 SkillManager, 默认导出 SkillSpec
Skill = SkillSpec


__all__ = [
    # legacy (P19 前)
    "BaseSkill",
    "BatchProductionSkill",
    "DataAnalysisSkill",
    "MediaProductionSkill",
    "PromptGenerationSkill",
    "PromptOptimizationSkill",
    "SkillInput",
    "SkillManager",
    "SkillOutput",
    "get_skill_manager",
    # V5.1 (P19 v5.1-B)
    "SkillSpec",
    "Skill",
]

__version__ = "1.0.0"