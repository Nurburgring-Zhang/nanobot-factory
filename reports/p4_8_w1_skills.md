# P4-8-W1 Deliverable — extended_skills (10 Skill + SkillOrchestrator + Obsidian + Marketplace)

**Task**: P4-8-W1: extended_skills (10 个 Skill + SkillOrchestrator, 借鉴 10 开源 Skill)
**Date**: 2026-06-24
**Worker**: coder
**Status**: ✅ DONE (34 new tests, 0 regressions)

---

## 1. Summary

Borrowing from 10 open-source Claude-skill projects (guizangPPTX, guizang-social-card,
Awesome-GPT-Image-Prompts, humanizer-zh, deep-research-mcp, anything-to-notebooklm,
WeWrite, youtube-clipper, oh-story-claudecode, marketingskills) plus the
7200★ claude-obsidian-view pattern, this task shipped a complete second-generation
skill framework under `backend/skills/` with **10 built-in skills**, a
`SkillOrchestrator` (routing + chain + retry/fallback), a ClaudeObsidianView
module (wiki + LLM auto-KB), a SkillMarketplace (install / rate / community),
and full FastAPI surface mounted on `agent_service`. The framework integrates
with P4-3 agent_service via a new `SKILL_ORCHESTRATOR` AgentType, an MCP tool
bridge, MemoryPalace retain hooks, and a multimodal adapter; **34 new tests
all pass, 0 regressions across 32 prior P4-3 agent tests**.

---

## 2. Changed files

### Created — framework (8 files)
| Path | Purpose | LoC |
|------|---------|-----|
| `backend/skills/__init__.py` | Package docstring + version | 60 |
| `backend/skills/base.py` | `Skill` ABC + `SkillCategory` enum + `@skill` decorator + schema introspection | 220 |
| `backend/skills/context.py` | `SkillContext` + `Blackboard` + `TraceEntry` (shared state across chain) | 145 |
| `backend/skills/result.py` | `SkillResult` dataclass + `pick()` mode helpers + JSON serialisation | 100 |
| `backend/skills/registry.py` | `SkillRegistry` (thread-safe) + `SKILL_REGISTRY` singleton + lazy instantiate | 165 |
| `backend/skills/orchestrator.py` | `SkillOrchestrator` + `ChainStep` + `ChainResult` (route / chain / retry / fallback) | 220 |
| `backend/skills/api.py` | FastAPI router (skills + orchestrator + marketplace + obsidian) | 280 |
| `backend/skills/marketplace.py` | `SkillMarketplace` + `SkillEntry` + `SkillRating` + JSON persistence | 220 |

### Created — 10 built-in skills (10 files)
| Path | Skill | Category | LoC |
|------|-------|----------|-----|
| `backend/skills/builtin/__init__.py` | Re-exports for side-effect registration | 35 |
| `backend/skills/builtin/guizang_ppt.py` | Idea → PPT deck | content | 115 |
| `backend/skills/builtin/guizang_social_card.py` | Text → social cards (5 platforms) | content | 75 |
| `backend/skills/builtin/awesome_gpt_image.py` | AI image prompt library + rewriter | image | 95 |
| `backend/skills/builtin/humanizer_zh.py` | AI-voice → human-voice (zh) | content | 90 |
| `backend/skills/builtin/deep_research.py` | Cited deep research (pluggable search_fn) | research | 100 |
| `backend/skills/builtin/anything_to_notebooklm.py` | Source → NotebookLM briefing (TL;DR + FAQ + quotes) | research | 105 |
| `backend/skills/builtin/wewrite.py` | Public-account writing one-stop (titles + outline + body + CTA) | content | 90 |
| `backend/skills/builtin/youtube_clipper.py` | Long-video → short clips + hook + reason | video | 75 |
| `backend/skills/builtin/oh_story_claudecode.py` | Web-novel topic mining + heat score ranking | content | 80 |
| `backend/skills/builtin/marketingskills.py` | Marketing toolkit (5 tools: SEO / landing / email / ads / lead magnet) | marketing | 130 |

### Created — ClaudeObsidianView (3 files)
| Path | Purpose | LoC |
|------|---------|-----|
| `backend/skills/obsidian/__init__.py` | Re-exports + singleton `get_knowledge_graph` / `get_llm_kb` | 60 |
| `backend/skills/obsidian/wiki.py` | `WikiLinkParser` + `KnowledgeGraph` (nodes / edges / backlinks / tag cloud) + vault persistence | 240 |
| `backend/skills/obsidian/llm_kb.py` | `LLMKnowledgeBase` + `KBIngestItem` + `KBIngestReport` (auto-summarise + dedupe) | 145 |

### Created — integration glue (2 files)
| Path | Purpose | LoC |
|------|---------|-----|
| `backend/skills/mcp_bridge.py` | `SkillMCPTool` + `discover_skill_tools()` + `invoke_skill_tool()` for agent_service MCP | 95 |
| `backend/skills/memory_hooks.py` | `retain_to_memory()` — push SkillResult into MemoryPalace L3 (Room) | 50 |
| `backend/skills/multimodal.py` | `register_skill_multimodal()` — image/audio/video/file handlers | 80 |

### Created — tests (5 files)
| Path | Tests |
|------|-------|
| `tests/skills/__init__.py` | sys.path bootstrap |
| `tests/skills/test_framework.py` | 5 — decorator + registry + context + result + orchestrator |
| `tests/skills/test_builtin.py` | 11 — one per skill + registry-has-all-10 |
| `tests/skills/test_obsidian.py` | 6 — WikiLinkParser + KnowledgeGraph + LLMKB (dedupe + session) |
| `tests/skills/test_marketplace.py` | 5 — sync_from_registry + install/rate + community publish + persist roundtrip |
| `tests/skills/test_api.py` | 7 — full HTTP surface via TestClient |

### Modified (3 files)
| Path | Change |
|------|--------|
| `backend/services/agent_service/agents.py` | Added `AgentType.SKILL_ORCHESTRATOR = "skill_orchestrator"` + matching `AGENT_REGISTRY` entry (capabilities: skill_run, skill_chain, skill_auto_route, skill_marketplace, obsidian_wiki, llm_kb). |
| `backend/services/agent_service/main.py` | Mounted `skills.api.router` in lifespan; eager-loaded `skills.builtin` so all 10 skills register at startup; called `get_marketplace()` to publish builtins. Wrapped in try/except so missing dependencies don't break the app. |
| `outputs/p4_8_w1_skills/deliverable.md` | Engine deliverable marker |

---

## 3. Test results

### New tests (34 total, all green)
```
tests/skills/test_api.py         .......        7 passed
tests/skills/test_builtin.py     ............   11 passed (10 skills + 1 registry-has-all)
tests/skills/test_framework.py   .....           5 passed
tests/skills/test_marketplace.py .....           5 passed
tests/skills/test_obsidian.py    ......          6 passed
                                  ============
                                  34 passed in 0.65s
```

### Regression — P4-3 agent tests (32 still green)
```
$ pytest tests/skills/ tests/agent/ -q
======================== 66 passed, 1 warning in 2.58s ========================
```

### Live smoke (`_smoke_p4_8_w1_live.py`, removed after run)
```
GET /api/v1/skills                       -> 200 count=10
GET /api/v1/skills/guizang_ppt           -> 200 name=guizang_ppt
POST /api/v1/skills/guizang_ppt/run      -> 200 success=True slides=4
POST /api/v1/skills/orchestrator/run     -> 200 success=True steps=2
GET /api/v1/agents/skill_orchestrator    -> 200 (AgentType registered)
SMOKE PASSED
```

### 3-skill chain smoke (manual `_smoke_p4_8_w1.py`, removed)
```
chain.success = True
  guizang_ppt   ok=True ms=0.0
  humanizer_zh  ok=True ms=1.0
  wewrite       ok=True ms=0.0
errors: []
final_data preview: {'topic': 'AI factory', 'length': 1200, 'tone': '深度 + 口语',
  'titles': ['关于「AI factory」的 3 个反常识', ...]}
```

---

## 4. Architecture & integration map

```
backend/skills/
├── base.py             ──┐
├── context.py           │   Core framework
├── result.py            │   (Skill ABC + decorator + registry)
├── registry.py          │
├── orchestrator.py     ──┘
├── api.py              ← FastAPI router (mounted on agent_service)
├── marketplace.py      ← In-memory + JSON-file marketplace
├── mcp_bridge.py       ← Exposes skills as MCP tools (P4-3-W2)
├── memory_hooks.py     ← Push results to MemoryPalace L3 (P4-3-W2)
├── multimodal.py       ← Skill accepts image/audio/video/file (P4-7)
├── builtin/            ← 10 skills (auto-register via @skill)
└── obsidian/
    ├── wiki.py         ← WikiLinkParser + KnowledgeGraph
    └── llm_kb.py       ← LLM auto-KB ingest

Integration points
──────────────────
* P4-3 agent_service:  AgentType.SKILL_ORCHESTRATOR → AGENT_REGISTRY entry
                       (capabilities: skill_run, skill_chain, skill_auto_route,
                        skill_marketplace, obsidian_wiki, llm_kb)
* P4-3 main.py:        skills.api.router mounted; skills.builtin eager-loaded;
                       get_marketplace() publishes 10 builtins
* P4-3 MCP:            skills.mcp_bridge.discover_skill_tools() registers
                       one MCP tool per skill
* P4-3 MemoryPalace:   skills.memory_hooks.retain_to_memory() pushes results
* P4-7 multimodal:     skills.multimodal.register_skill_multimodal() handlers
```

---

## 5. Borrowed-from matrix

| Skill | Borrowed from | Open-source reference |
|-------|---------------|-----------------------|
| `guizang_ppt` | guizangPPTX | idea → structured PPT outline |
| `guizang_social_card` | guizang-social-card | text → multi-platform social cards |
| `awesome_gpt_image` | Awesome-GPT-Image-Prompts | image prompt library + rewriter |
| `humanizer_zh` | humanizer-zh | AI voice → human voice (zh) |
| `deep_research` | deep-research-mcp | cited deep research |
| `anything_to_notebooklm` | anything-to-notebooklm | source → multi-format briefing |
| `wewrite` | WeWrite | public-account one-stop writing |
| `youtube_clipper` | youtube-clipper | long-video → short clips |
| `oh_story_claudecode` | oh-story-claudecode | web-novel topic mining |
| `marketingskills` | marketingskills | 5-tool marketing toolkit |
| `obsidian.wiki` | claude-obsidian-view (7200★) | wiki links + knowledge graph |
| `obsidian.llm_kb` | claude-obsidian-view + Karpathy LLM Wiki | LLM-driven KB ingest |

---

## 6. Endpoints exposed on agent_service

```
GET  /api/v1/skills                              — list / search
GET  /api/v1/skills/{name}                       — detail
POST /api/v1/skills/{name}/run                   — execute
POST /api/v1/skills/orchestrator/run             — run chain
POST /api/v1/skills/orchestrator/auto            — auto-route + run
GET  /api/v1/skills/marketplace/list             — marketplace
POST /api/v1/skills/{name}/install               — install
POST /api/v1/skills/{name}/rate                  — rate
POST /api/v1/skills/install_community            — publish community skill
GET  /api/v1/obsidian/wiki                       — list pages
POST /api/v1/obsidian/wiki                       — upsert page
GET  /api/v1/obsidian/wiki/{slug}                — page detail
DEL  /api/v1/obsidian/wiki/{slug}                — delete page
GET  /api/v1/obsidian/wiki/{slug}/backlinks      — backlinks
GET  /api/v1/obsidian/wiki/graph                 — knowledge graph (nodes + edges)
GET  /api/v1/obsidian/wiki/tags                  — tag cloud
POST /api/v1/obsidian/llm_kb/ingest              — bulk LLM-KB ingest
POST /api/v1/obsidian/llm_kb/ingest_session      — session ingest
```

---

## 7. Notes for the verifier

1. **Route ordering matters**: `/api/v1/skills/orchestrator/run` and
   `/api/v1/obsidian/wiki/graph|tags` are declared BEFORE the
   `/api/v1/skills/{name}/...` and `/api/v1/obsidian/wiki/{slug}` patterns.
   FastAPI matches routes in declaration order — putting the static routes
   first prevents the `{name}` / `{slug}` parameter from swallowing
   `orchestrator` and `graph|tags`.

2. **Mock mode by default**: when no real LLM is wired in, every skill
   returns a deterministic placeholder (e.g. `[mock:guizang_ppt] echo head=...`).
   Tests rely on the deterministic fallback, so they pass without a
   network connection or LLM credentials. Production deployments inject
   an LLM via `Skill.set_llm(...)`.

3. **Pydantic v2 / FastAPI 0.115**: the API uses `pydantic.BaseModel`
   with `Field(default_factory=...)`. No `orm_mode` / `from_orm` usage.

4. **Singleton discipline**: `SKILL_REGISTRY`, `get_marketplace()`,
   `get_knowledge_graph()` are all lazy-singleton with thread-safe
   initialisation. Test fixtures use the `reset_*_for_test()` helpers
   to start clean.

5. **MemoryPalace hook is opt-in**: the `retain_to_memory()` helper is
   exposed but the orchestrator does not auto-call it (avoids accidental
   spam on every chain step). Callers wire it in explicitly when they
   want durable Skill results.

6. **No regressions**: 32 prior P4-3-W1/W2 agent tests still pass; the
   only agent_service change is the additive `SKILL_ORCHESTRATOR` entry
   plus the new router mount. No existing endpoints modified.