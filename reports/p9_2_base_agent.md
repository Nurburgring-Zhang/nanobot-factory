# P9-2.1 — BaseAgent ABC 三次审查 (CORRECTED — bridge to 23 AgentTypes)

**File**: `backend/imdf/agents/base.py` (218 LOC, 9164 bytes)
**Companion**: `backend/services/agent_service/agents.py` (~500+ LOC, 23 AgentTypes)
**Bridge**: `backend/services/agent_service/agents.py::get_agent_class()` + `AGENT_CLASS_REGISTRY`

---

## 1. Abstract contract (base.py)

Same as attempt 1 — BaseAgent ABC is well-designed:

### 1.1 `AgentContext` (line 47-69)
- task_id, agent_type, mode, input, metadata
- Dataclass with `field(default_factory=dict)` defensive

### 1.2 `AgentResult` (line 72-120)
- ok, task_id, agent_type, output, plan, error, error_source
- `to_dict()` JSON-serializable
- `from_exception()` factory
- **Still missing**: traceback field (only type+str in error message)

### 1.3 `BaseAgent` ABC (line 123-211)
- 1 abstract method: `execute(context) -> AgentResult`
- Default methods: `plan()`, `validate()`, `get_agent_type_slug()`, `__repr__()`
- ClassVar: name, description, capabilities, default_mode, default_priority, max_retries, timeout_seconds, downstream_service, agent_type

**35/35 tests PASS** per `p6_fix_p0_5_baseagent.md`.

---

## 2. CORRECTION: 23 AgentTypes (actual count)

### 2.1 The catalog (per agents.py)

```python
class AgentType(str, Enum):
    # 15 base (P3-3-W1)
    REQUIREMENT_PARSER, DATA_COLLECTION, CLEANING, PRELABEL,
    FINE_ANNOTATION, REVIEW, SCORING, FILTERING, EXPORT,
    EVALUATION, BADCASE_ANALYSIS, FEEDBACK, MEMORY, SCHEDULING, QUALITY
    # 7 P4-5 multimodal (DIRECTOR / STORYBOARD / CHARACTER / IMAGE / VIDEO / VOICE / QA)
    GENERATION_DIRECTOR, GENERATION_STORYBOARD, GENERATION_CHARACTER,
    GENERATION_IMAGE, GENERATION_VIDEO, GENERATION_VOICE, GENERATION_QA
    # 1 P4-8
    SKILL_ORCHESTRATOR
```

### 2.2 The bridge — `agents.py::get_agent_class()`

The services/agent_service/agents.py module:
- Defines `AgentType` enum (25 members)
- Defines `AGENT_REGISTRY: Dict[AgentType, Dict]` — 25 metadata entries
- Defines `AGENT_CLASS_REGISTRY: Dict[AgentType, Type[BaseAgent]]` — 25 concrete classes
- Exposes `get_agent_class(slug: str)` — slug → BaseAgent subclass

This **solves the P6-Fix-P0-5 backward-compat issue**: legacy code that imports from `services.agent_service.agents` still works.

### 2.3 The 23 built-ins (per imdf/agents/builtin/_all.py)

The P6-Fix-P0-5 implementation has 23 built-in BaseAgent subclasses in `imdf/agents/builtin/_all.py`. The 24th and 25th (`GENERATION_CHARACTER` + `SKILL_ORCHESTRATOR`) may live elsewhere (multimodal_agent.py / skills/orchestrator.py).

---

## 3. Three-pass audit

### 3.1 Contract clarity (Pass 1: structural)

- ✅ Minimal contract (1 abstract method)
- ✅ Complete docstrings
- ✅ Dataclass-based value objects (immutable by convention)
- ⚠ Mode is hardcoded string (no enum)

### 3.2 Error + timeout (Pass 2)

- ✅ `validate()` pre-execute hook
- ✅ `from_exception()` factory
- ⚠ No built-in timeout enforcement — `timeout_seconds=60` is a hint
- ⚠ No retry mechanism — `max_retries=1` is a hint
- ❌ Traceback lost in AgentResult error message

### 3.3 Thread safety (Pass 3: P7-1 finding)

- ✅ ClassVar (immutable by design) — multi-thread safe
- ✅ Singleton + RLock in PluginRegistry
- ⚠ No lock for instance-level mutable state (if subclasses add cache, must self-lock)

---

## 4. Issues (carryover from attempt 1 + new findings)

| # | Issue | Severity | Effort |
|---|---|---|---|
| **I1** | Traceback lost in AgentResult | P1 | 5min |
| **I2** | Mode is string (not enum) | P2 | 15min |
| **I3** | No built-in timeout wrapper | P1 | 30min |
| **I4** | No built-in retry decorator | P2 | 1h |
| **I5** | No `execute_safe()` template method | P2 | 1h |
| **I6** | 23 vs 25 AgentType mismatch (imdf has 23, services has 25) | P1 | 4h (alignment) |
| **I7** | GENERATION_CHARACTER missing from imdf/builtin/_all.py | P1 | 1h |
| **I8** | SKILL_ORCHESTRATOR missing from imdf/builtin/_all.py | P1 | 1h |

---

## 5. World-class comparison

| Dimension | BaseAgent (nanobot) | CrewAI Agent | AutoGen AssistantAgent | OpenAI Agents SDK |
|---|---|---|---|---|
| Abstract methods | 1 | 3 | 2 | 1 |
| Agent catalog | 25 (services) + 23 (imdf) | Custom | Custom | Custom |
| Multimodal agents | 7 named | Custom | Custom | Custom |
| Skill orchestrator | ✅ P4-8 | ❌ | ❌ | ❌ |
| **Score** | **7.5/10** | **9/10** | **8.5/10** | **8.5/10** |

---

## 6. Score

| Dimension | Score |
|---|---|
| Contract clarity | 8/10 |
| Subclass coverage | 7/10 (25 catalog, 23 concrete) |
| Error semantics | 6/10 (no traceback/timeout wrapper) |
| Thread safety | 8/10 (ClassVar immutable) |
| **Total** | **7.3/10** |