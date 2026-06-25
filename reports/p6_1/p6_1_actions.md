# P6-1: Action Items (P0/P1/P2 + Effort Estimates)

> Generated 2026-06-24 by Coder audit. Owners TBD unless assigned.

---

## P0 — Blocker (no P0 found)

No P0 blockers. All 13 services pass startup, health, readiness, metrics. Business endpoints respond correctly.

---

## P1 — Important (2 items, ~2-3 days total)

### P1-1: Verify `asset_service/iteration/agents.py:154` NotImplementedError

**Severity**: P1 (verify before next release)
**Effort**: 30 min (read + verify) → 1-2 hr (fix if not abstract)
**File**: `backend/services/asset_service/iteration/agents.py:154`

**Action**:
```bash
# 1. Read context around line 154
Read backend/services/asset_service/iteration/agents.py
# Check if it's:
#   (a) abstract base class @abstractmethod → ACCEPTABLE, ignore
#   (b) genuine stub → MUST implement
```

If abstract → add comment `# Intentionally abstract: subclass MUST implement`. If stub → implement minimal logic + remove NotImplementedError.

### P1-2: Replace in-memory rate limiter with Redis (multi-replica scale)

**Severity**: P1 (deferred until >1 gateway replica)
**Effort**: 2-3 days
**Files**: `backend/gateway/middleware/rate_limit.py` (refactor) + new `backend/gateway/middleware/redis_rate_limit.py`

**Action**:
1. Add `redis.asyncio` client to gateway deps
2. Implement `RedisTokenBucket` with `INCR` + `EXPIRE` (or sliding-window via sorted set)
3. Wire as alternative to in-memory via env var `RATE_LIMIT_BACKEND=redis|memory`
4. Test with 3+ gateway replicas hitting same Redis → verify shared rate state
5. Document in `backend/gateway/README.md`

**Why not in-memory now**: Test passes for single replica. Production deployment will use 2-3 gateway replicas (k8s HPA), and per-IP buckets must be shared.

---

## P2 — Nice-to-have (3 items, ~1 hour total)

### P2-1: Deduplicate `routes.yaml`

**Severity**: P2 (cosmetic / future-bug-prevention)
**Effort**: 10 min
**File**: `backend/gateway/routes.yaml`

**Action**:
```diff
-  - name: dataset-service
-    prefix: /api/v1/datasets
-    upstream: http://127.0.0.1:8765/internal   # line 209 — DUPLICATE
-    require_auth: true
-    description: Dataset CRUD + sample listing
-
-  - name: annotation-misc
-    prefix: /api/v1/annotation
-    upstream: http://127.0.0.1:8765/internal   # line 215
...
-  # ===== P3-3-W1: agent-service (port 8008) =====   # line 262 — DUPLICATE section
-  - name: agent-service
-    prefix: /api/v1/agents
-    upstream: http://127.0.0.1:8008
-    require_auth: true
-    description: "P3-3-W1 agent-service: ..."
-
-  - name: agent-service
-    prefix: /api/v1/agent_tasks
-    upstream: http://127.0.0.1:8008
-    require_auth: true
-    description: "P3-3-W1 agent-service: ..."
```

After fix, expect 39 unique prefixes (was 42 with 3 dupes).

### P2-2: Remove or alias `require_role` dead code

**Severity**: P2 (dead code, easy fix)
**Effort**: 5 min
**File**: `backend/common/auth.py:188-203`

**Action** (option A — remove):
```python
# Delete the entire `require_role` function; callers should use `require_role_dep`
```

**Action** (option B — alias):
```python
def require_role(*allowed_roles: str):
    """DEPRECATED: use require_role_dep instead."""
    return require_role_dep(*allowed_roles)
```

### P2-3: Make JWT secret mandatory in gateway (fail-fast)

**Severity**: P2 (prod hardening)
**Effort**: 5 min
**File**: `backend/gateway/main.py:103-107`

**Action**:
```python
def _jwt_secret() -> str:
    sec = os.environ.get("JWT_SECRET_KEY") or os.environ.get("JWT_SECRET")
    if not sec or sec == "imdf_secret_change_me":
        if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
            return "test-secret-gateway"  # explicit test-only default
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required "
            "(refusing to start with insecure default)"
        )
    return sec
```

### P2-4: Add OpenAPI schema cross-check

**Severity**: P2 (long-term correctness)
**Effort**: 4 hours
**File**: new `tests/test_openapi_compat.py`

**Action**: For each service, fetch `/openapi.json`, validate:
- All declared paths in `routes.yaml` have a matching endpoint
- No endpoint returns undocumented 5xx
- All POST endpoints have request body schema

### P2-5: Document service-level ops runbook

**Severity**: P2 (onboarding)
**Effort**: 4 hours
**File**: new `docs/runbooks/microservices.md`

Cover per-service: how to start, env vars, common errors, scaling notes, observability hooks.

---

## P3 — Defer / Backlog (no items, all nice-to-have)

---

## Effort Roll-up

| Priority | Items | Total Effort | Calendar Time |
|---|---|---|---|
| P0 | 0 | 0 | 0 |
| P1 | 2 | ~3 days | ~1 week |
| P2 | 5 | ~1 day | 1-2 days |
| **TOTAL** | **7** | **~4 days** | **~1.5 weeks** |

---

## Suggested Sprint Plan

### Sprint 1 (this week)
- P1-1: Verify F-003 (30 min)
- P2-1: Dedupe routes.yaml (10 min)
- P2-2: Remove dead `require_role` (5 min)
- P2-3: Fail-fast on JWT default (5 min)

### Sprint 2 (next week, before k8s scale-out)
- P1-2: Redis rate limiter (2-3 days)
- P2-4: OpenAPI cross-check (4 hr)
- P2-5: Ops runbook (4 hr)

### Stretch (this quarter)
- Service mesh (Istio/Linkerd) for mTLS + advanced routing
- Distributed tracing (OTel collector + Jaeger)
- Chaos engineering (chaos-mesh) for gateway failure modes