# P4-3-W2 Report: MemoryPalace + Hindsight + MCP Server

## What was built

Three new modules under `backend/services/agent_service/`:

1. **`memory_palace/`** — a 6-layer hierarchical long-term memory
   (L0 Identity → L1 Essential Story → L2 Wing → L3 Room → L4 Drawer
   → L5 Tunnel), backed by 5 SQLite tables. CRUD + search + stats
   endpoints under `/api/v1/memory/palace/*`.

2. **`hindsight.py`** — a 4-layer Memory Stack (L0/L1/L2/L3) with the
   Hermes "verbatim" discipline (raw text is never mutated, L1 is
   generated from L3 by an LLM and stored as a separate record), an
   automatic L1 compressor, a pluggable backend selector
   (sqlite_exact / pgvector / chromadb / qdrant), and 4-layer search
   with cosine re-rank when an embedder is supplied.

3. **`mcp/`** — a Model Context Protocol server with JSON-RPC
   dispatch over stdio (for Claude Code / Cursor) and HTTP/SSE (for
   browser clients). Exposes 5 tools, 3 resources, 2 prompts.

## Validation

```
$ D:\ComfyUI\.ext\python.exe -m pytest tests/agent/ -v
…
16/16 W2 tests pass (test_memory_palace 8 + test_hindsight 5 + test_mcp 3).
14/16 W1 tests pass (2 unrelated W1 template-filter + 404-detail bugs).
Total: 30/32 PASS, 0 regressions in P3-3.
```

Smoke test of the running app (TestClient, no uvicorn) confirms:

  * `GET /api/v1/memory/palace/levels` → 6 levels
  * `GET /api/v1/memory/palace/tables` → 5 tables
  * `GET /api/v1/agent/mcp/status` → 5 tools, 3 resources, 2 prompts
  * `POST /api/v1/agent/mcp` → JSON-RPC round-trip works for every
    method (initialize, tools/list, tools/call, resources/read,
    prompts/get, method_not_found).

## What's in the commit

```
backend/services/agent_service/
├── mcp/
│   ├── __init__.py
│   ├── server.py          (JSON-RPC dispatcher + stdio loop)
│   ├── tools.py           (5 default tools)
│   ├── resources.py       (3 default resources)
│   └── prompts.py         (2 default prompts)
├── memory_palace/
│   ├── __init__.py
│   ├── levels.py          (MemoryLevel enum + 5 record dataclasses)
│   └── manager.py         (SQLite facade + 5-table DDL)
├── hindsight.py           (4-layer Memory Stack + pluggable backends)
├── routes_memory.py       (/api/v1/memory/palace/* + /api/v1/memory/hindsight/*)
├── routes_mcp.py          (/api/v1/agent/mcp/* + POST JSON-RPC + SSE)
└── main.py                (mount the new routers + init memory subsystems in lifespan)

tests/agent/
├── __init__.py
├── test_memory_palace.py  (8 tests)
├── test_hindsight.py      (5 tests)
└── test_mcp.py            (3 tests)
```

## Open items (out of scope for this commit)

* Integration into W1 files (multi_turn / instructions / tools /
  variables) — see deliverable §4.3 for the recipe.
* Alembic migration for the 5 tables (deferred per plan task).
* `pgvector` runtime path — config knob exists, fallback is
  `sqlite_exact`.
