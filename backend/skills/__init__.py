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

__version__ = "1.0.0"