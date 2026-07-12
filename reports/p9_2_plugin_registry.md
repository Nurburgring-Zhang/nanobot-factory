# P9-2.2 — PluginRegistry 三次审查 (CORRECTED — bridge confirmed)

**File**: `backend/imdf/agents/registry.py` (190 LOC, 7636 bytes)
**Companion**: `loader.py` (226 LOC, 8805 bytes)
**Bridge**: `services/agent_service/agents.py::AGENT_CLASS_REGISTRY` — 23 entries

---

## 1. Implementation (same as attempt 1)

### 1.1 Singleton + RLock
```python
_instance: Optional["PluginRegistry"] = None
_singleton_lock = threading.Lock()

def __init__(self):
    self._agents: Dict[str, Type[BaseAgent]] = {}
    self._lock = threading.RLock()
    self._validator = None
```
- ✅ Double-checked locking for singleton
- ✅ RLock (re-entrant) for dict ops
- ✅ Validator hook for namespace conflicts

### 1.2 Core API (line 72-187)
- `register(name, cls, *, overwrite=True)` — strict type check + validator
- `unregister(name)` — exception-free no-op on unknown
- `get(name)` — KeyError on unknown
- `try_get(name)` — None on unknown
- `list() / items() / __contains__ / __len__` — snapshot accessors
- `bulk_register(mapping)` — atomic with rollback

### 1.3 Loader (loader.py)
- Dynamic plugin loading via `importlib.util.spec_from_file_location`
- Synthetic module name (`imdf_agent_plugin_{stem}_{hash}`)
- Walk module namespace for BaseAgent subclasses
- Auto rollback on import failure

---

## 2. CORRECTION: Bridge to services (NEW finding)

The original attempt 1 said "35/35 tests pass" — CONFIRMED, plus there's now a bridge to the services layer:

### 2.1 Bridge implementation
`backend/services/agent_service/agents.py` adds:
- `AGENT_CLASS_REGISTRY: Dict[AgentType, Type[BaseAgent]]` — 23 entries
- `get_agent_class(slug: str) -> Type[BaseAgent]`
- Backward-compatible: legacy code importing from `services.agent_service.agents` works

### 2.2 Test coverage
- 12 tests in `backend/services/agent_service/tests/test_plugin_registry.py`:
  - Legacy metadata contract (4)
  - get_agent_class (3)
  - AGENT_CLASS_REGISTRY (2)
  - Real execute() round-trip (2)
  - Plugin CRUD (1)

### 2.3 The 23 vs 25 issue
- `imdf/agents/builtin/_all.py`: 23 classes
- `services/agent_service/agents.py::AgentType`: 25 enum members
- Gap: 2 missing concrete classes (GENERATION_CHARACTER, SKILL_ORCHESTRATOR)

---

## 3. Three-pass audit (refined)

### 3.1 Thread safety (Pass 1) — P7-1 finding VERIFIED FIXED
- ✅ RLock all dict ops (6 places)
- ✅ Singleton double-checked locking correct
- ✅ `__contains__`, `__len__` also locked
- ⚠ `_validator` set is in lock, but callable invocation not protected — assumption: caller provides thread-safe validator

### 3.2 Lifecycle (Pass 2)
- ✅ register → get → unregister → reset
- ⚠ No `is_registered()` method (use `__contains__`)
- ⚠ No weakref — strong ref keeps class alive until unregister
- ⚠ No version tracking (would help with hot-reload)

### 3.3 Conflict detection (Pass 3)
- ✅ `set_validator()` hook
- ✅ `overwrite=True` default (idempotent)
- ❌ No namespace support
- ❌ No version field

---

## 4. P0/P1 Fix list

| # | Issue | Severity | Effort |
|---|---|---|---|
| I1 | Add version field | P1 | 30min |
| I2 | Add namespace prefix support | P2 | 1d |
| I3 | Add `weakref` option | P2 | 2h |
| I4 | Add `is_registered()` public method | P3 | 5min |
| I5 | Sync 23 imdf built-ins with 25 services AgentTypes | P1 | 4h |
| I6 | Add plugin signature verification in loader | P0 (security) | 20min |

---

## 5. Score

| Dimension | Score |
|---|---|
| Thread safety | 9/10 |
| Lifecycle | 8/10 |
| Conflict detection | 6/10 |
| Bridge integration | 9/10 |
| **Total** | **8.0/10** |

---

## 6. Honest note from attempt 1

Attempt 1 was largely correct on PluginRegistry — the bridge detail was the only addition. The main correction is **23 vs 25 AgentType mismatch** discovered in this revision.