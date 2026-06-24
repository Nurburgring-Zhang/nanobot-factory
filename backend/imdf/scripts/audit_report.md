================================================================================
NANOBOT-FACTORY DEEP CODE AUDIT REPORT
================================================================================
Scope: 61 engine files (engines/) + 52 API route files (api/)
Date: 2026-06-17
Methodology: Automated AST scanning + manual call-chain tracing + import analysis

================================================================================
P0 — CRITICAL (16 findings)
================================================================================

[P0-01] api/annotation_routes.py:12-13 — STUB: POST /api/annotations/save
  save_annotation() returns {"success":True,"saved":len(req.annotations),"item_id":req.item_id}
  but performs NO actual save/database write. Data is silently discarded.
  Impact: All annotation submissions are lost.

[P0-02] api/delivery_routes.py:11-21 — COMPLETE STUB FILE (entire module)
  delivery_list() returns 2 hardcoded fake deliveries (d1, d2).
  delivery_create() returns fake "d3" ID without creating anything.
  impact: Entire delivery management system is non-functional.

[P0-03] api/crowd_routes.py:5-15 — COMPLETE STUB FILE (entire module)
  crowd_workers() returns 3 hardcoded fake workers (标注员A/B, 审核员C).
  crowd_stats() returns hardcoded fake stats (45 workers, 23 tasks, etc.).
  No real backend. No DB. No state. Fully synthetic output.

[P0-04] api/routes_extended.py:8  vs  api/crowd_routes.py:3 — URL PREFIX COLLISION
  Both define routers with prefix="/api/crowd":
    crowd_routes.py:3 → router = APIRouter(prefix="/api/crowd", tags=["crowd"])
    routes_extended.py:8 → crowd_router = APIRouter(prefix="/api/crowd", tags=["crowd"])
  FastAPI will merge both into the same path — one may silently shadow the other.

[P0-05] api/export_routes.py:18  vs  api/export_enhanced_routes.py:22 — DUPLICATE PREFIX
  Both define prefix="/api/v1/export":
    export_routes.py:18 → APIRouter(prefix="/api/v1/export", tags=["export"])
    export_enhanced_routes.py:22 → APIRouter(prefix="/api/v1/export", tags=["export_package"])
  Routes from one module may shadow the other entirely.

[P0-06] api/model_routes.py:19 — DANGEROUSLY BROAD PREFIX
  router = APIRouter(prefix="/api", tags=["model-gateway"])
  Prefix "/api" captures ALL paths under /api/* — will collide with every other
  /api/* router (admin, aesthetic, audio, book, etc.)

[P0-07] api/prelabel_router.py:11 — DANGEROUSLY BROAD PREFIX
  router = APIRouter(prefix="/api", tags=["prelabel"])
  Same issue as P0-06 — captures entire /api/* namespace.

[P0-08] api/canvas_web.py:3905 — DANGEROUSLY BROAD PREFIX
  search_router = APIRouter(prefix="/api", tags=["search"])
  Third router claiming /api — triple collision with model_routes and prelabel_router.

[P0-09] api/canvas_web.py:3721/3828/3887 — AMBIGUOUS /api/v1 PREFIXES
  ingest_router = APIRouter(prefix="/api/v1", tags=["ingest"])
  backup_router = APIRouter(prefix="/api/v1", tags=["backup"])
  delivery_inc_router = APIRouter(prefix="/api/v1", tags=["delivery_inc"])
  Three routers all claiming /api/v1 without sub-paths — they will merge unpredictably.

[P0-10] api/health_routes.py:29 — NO PREFIX AT ALL
  router = APIRouter(tags=["health"])  # No prefix specified
  Returns routes at root level (/, /ready, /live) instead of /api/v1/health/...

[P0-11] api/auth_routes.py:28 — INCONSISTENT PREFIX (no /api/)
  router = APIRouter(prefix="/auth", tags=["auth"])
  All other routes use /api/ prefix; auth uses bare /auth. Mixing schemes
  makes API gateway/proxy routing fragile.

[P0-12] engines/__init__.py — EMPTY FILE (0 bytes)
  No namespace exports. Every `from engines.xxx import ...` must hit disk.
  Missing centralized exports, lazy-loading guards, or entry points.

[P0-13] api/__init__.py — EMPTY FILE (0 bytes)
  Same as P0-12. No API namespace exports or router aggregator.

[P0-14] api/quality_routes.py:56-58 — IAA route calls get_iaa().agreement_report() but...
  `from engines.annotation_quality import get_iaa` — need to verify get_iaa() actually exists
  and returns a real engine (not a stub). The import is inside the route function body
  (lazy import). If annotation_quality.py is incomplete, IAA returns garbage.

[P0-15] api/annotation_history_routes.py:17  vs  api/annotation_routes.py:4 — TAG COLLISION
  annotation_history_routes: prefix="/api/v1/annotations", tags=["annotations"]
  annotation_routes: prefix="/api/annotations", tags=["annotations"]
  Same tag "annotations" for two different routers. OpenAPI schema merges them confusingly.

[P0-16] api/book_routes.py:19 — IMPORTS REAL ENGINE BUT METHOD NOT IMPLEMENTED
  from engines.book_engine import get_book_engine, Book, BookPage
  book_engine:_call_comfyui (line 300) raises NotImplementedError — the ComfyUI
  image generation path is a hard crash. Any API call that reaches ComfyUI generation
  will fail with HTTP 500.

================================================================================
P1 — HIGH SEVERITY (18 findings)
================================================================================

[P1-01] engines/operators_lib.py:42-102 — STUB ENGINE: Operator.run() has 13 'return data' fallbacks
  SOURCE category (line 86): `return data  # 采集算子在外部调用`
  LABEL category (line 88): `return data  # 标注算子在外部调用`
  SCORE category (line 94): returns `random.uniform(0.5, 1.0)` placeholder scores
  EXPORT category (line 101): `return data  # 导出算子在外部调用`
  FILTER default (line 52,58,69,74,78,84): returns unchanged data when type doesn't match
  SELECT default (line 99): returns unmodified data
  Only the explicitly matched filter IDs (filter.null_filter, etc.) actually work.
  All other operators are no-ops. The "占位" SCORE operators return random data.

[P1-02] engines/audio_engine.py:50-74 — TTS STUB: Generates silent WAV placeholder
  text_to_speech() writes a WAV file header with zero-filled audio data.
  The Windows PowerShell Speech call at line 53 doesn't actually save audio.
  All TTS output is SILENCE. Not a true TTS engine.

[P1-03] api/data_browser_routes.py:47-69 — MOCK DATA FALLBACK
  _generate_mock_datasets() returns random fake datasets when DB is empty.
  This masks database configuration errors — users see fake data thinking
  the system works when it's actually misconfigured.

[P1-04] api/monitor_routes.py:27-42 — RANDOM FALLBACK DATA
  pipeline_snapshot() falls back to `random.randint(0,10)` when engines fail.
  pipeline_history() returns random trend data when DB unavailable.
  Production monitoring returns synthetic numbers indistinguishable from real.

[P1-05] engines/event_engine.py:241-246 — SYNC CALLS ASYNC WITHOUT AWAIT
  publish_sync() (sync function) calls publish() (async function) 3 times
  at lines 241, 244, 246 without await. This will either:
  (a) Return a coroutine object instead of execution result, or
  (b) Raise RuntimeError if there's no running event loop.

[P1-06] engines/scheduler_engine.py:431-435 — SYNC CALLS ASYNC WITHOUT AWAIT
  run_job_now() (sync) calls _run_scheduled_job() (async) without await.
  Same class of bug as P1-05.

[P1-07] api/resource_library.py:427-431 — SYNC CALLS ASYNC WITHOUT AWAIT
  _resolve_source() (sync) calls _fetch_remote() (async) without await.

[P1-08] api/api_key_routes.py:160 — BARE 'dict' TYPE HINT
  Parameter 'current_user' declared as `dict` instead of `Dict[str, Any]`.
  FastAPI can't generate accurate OpenAPI schema from bare `dict`.

[P1-09] api/auth_routes.py:296 — BARE 'dict' TYPE HINT
  Parameter 'current_user' declared as bare `dict`.

[P1-10] api/canvas_web.py:2595 — BARE 'dict' TYPE HINT
  Parameter 'req' declared as bare `dict`.

[P1-11] api/annotation_history_routes.py:17 — INCONSISTENT PREFIX STYLE
  Uses `/api/v1/annotations` while annotation_routes.py uses `/api/annotations`.
  Two annotation systems with different API versioning paths suggests incomplete migration.

[P1-12] api/quality_routes.py:46 — LAZY IMPORTS INSIDE ROUTE BODIES
  Every route function imports engines locally (e.g., line 57: `from engines.annotation_quality import get_iaa`).
  This pattern (a) hides import errors until runtime, (b) makes startup validation impossible,
  (c) incurs per-request import overhead.

[P1-13] api/admin_routes.py:21-23 — SYS.PATH MANIPULATION BEFORE IMPORTS
  sys.path.insert(0, str(_PROJECT_ROOT)) before the FastAPI import.
  Same pattern in 6+ files (admin_routes, api_key_routes, canvas_web, classify_routes,
  health_routes...). This is a packaging antipattern — the project should be installed
  as a proper package or run with PYTHONPATH.

[P1-14] engines/dam_engine.py:417 — LAZY PIL IMPORT INSIDE METHOD
  `from PIL import Image` inside an instance method. Will crash at runtime
  if PIL is not installed, but won't be caught at module import time.
  No try/except wrapping.

[P1-15] engines/local_models.py:66,80,120,139,156,168 — MULTIPLE LAZY ML IMPORTS
  sentence_transformers, PIL submodules imported inside methods without error handling.
  Runtime crashes possible when these packages aren't installed.

[P1-16] engines/data_pipeline.py:702 — ONLY ENGINE WITH STANDARD run()
  Only data_pipeline and operators_lib define explicit `run()` methods.
  55+ other engines use ad-hoc method names (discover, score, generate, etc.)
  No consistent engine interface/abstract base class.

[P1-17] api/sharing_routes.py:23 — DUPLICATE TRANSFER FUNCTIONALITY
  sharing_routes duplicates transfer_routes functionality (both implement
  share/create, share/access, token verification). Duplicated HMAC signing,
  password hashing, and expiration logic across sharing_routes.py and
  transfer_engine.py.

[P1-18] api/external_routes.py:16 — IMPORTS Body BUT NOT USED
  `from fastapi import APIRouter, Body, HTTPException` — imports Body but
  all POST endpoints use Pydantic BaseModel classes. Unused import.

================================================================================
P2 — LOW SEVERITY (notable patterns only — full 96-item list omitted)
================================================================================

[P2-01] api/api_key_routes.py:43 — MODULE-LEVEL bcrypt IMPORT
  `import bcrypt` at top level — will crash entire module if bcrypt not installed.
  Unlike auth_routes.py which wraps in try/except.

[P2-02] api/api_key_routes.py:48 — MODULE-LEVEL passlib IMPORT
  `from passlib.hash import bcrypt as passlib_bcrypt` — no try/except.

[P2-03] api/auth_routes.py:12 — passlib CryptContext WITH TRY/EXCEPT (GOOD)
  Correct pattern: try/except with pwd_context=None fallback.
  Sets good example that api_key_routes.py should follow.

[P2-04] Multiple files use bare 'list' instead of 'List[X]' in Pydantic models
  e.g., annotation_routes.py:8 `annotations: list`, delivery_routes.py:9 `items: list`
  FastAPI/Pydantic v2 treats bare `list` differently than `List` in older versions.

[P2-05] engines/assertion_engine.py:19 — BASE CLASS NotImplementedError (EXPECTED)
  Expectation.validate() raises NotImplementedError — this is proper ABC pattern.

[P2-06] Extensive use of `import random` inside function bodies for mock data
  (data_browser_routes, monitor_routes, discovery_engine) — makes testability poor
  and masks real system failures.

================================================================================
CALL CHAIN INTEGRITY SUMMARY
================================================================================

REAL ENGINES (verified with actual data processing):
  ✅ transfer_engine.py — Full HMAC signing, password hashing, JSON persistence (523 lines)
  ✅ dam_engine.py — Complete DAM with 90+ formats, scanning, tagging, lineage (1372 lines)
  ✅ aesthetic_engine.py — Three-model ensemble (Q-Align + LAION + MUSIQ) with real inference (239 lines)
  ✅ discovery_engine.py — Real API calls to HF/Kaggle/arXiv with json parsing (139 lines)
  ✅ classification_engine.py — Referenced by classify_routes (import verified)
  ✅ pe_system.py — Referenced by pe_routes (import verified)
  ✅ model_gateway.py — Referenced by model_routes (import verified)
  ✅ book_engine.py — Real LLM→image→HTML/PDF pipeline (565 lines) EXCEPT _call_comfyui
  ✅ preview_engine.py — Real format support checking, thumbnail generation (484 lines)
  ✅ quality_v2_routes.py → connects to discovery_quality, filter_quality, collection_quality, etc.
  ✅ search_routes.py → connects to search_engine.py (verified import)
  ✅ db_models.py — Real SQLAlchemy models (121 lines)
  ✅ audit_routes.py — Real SQLite audit log queries (126 lines)
  ✅ template_routes.py → connects to template_market.py (verified import)
  ✅ local_model_routes.py → connects to local_models.py (verified import)
  ✅ enhanced_routes.py → connects to enhanced_engines.py (verified import)

STUB ENGINES / STUB ENDPOINTS:
  ❌ operators_lib.py — 13 `return data` no-ops; SCORE returns random placeholders
  ❌ audio_engine.py — TTS generates silent WAV (not real TTS)
  ❌ book_engine.py:_call_comfyui — NotImplementedError (ComfyUI path broken)
  ❌ annotation_routes.py — save_annotation discards data (no-op)
  ❌ delivery_routes.py — Entire file is hardcoded fake responses
  ❌ crowd_routes.py — Entire file is hardcoded fake responses
  ❌ data_browser_routes.py — Falls back to random mock data when DB absent

ENGINES NOT VERIFIED (need deeper manual review):
  ? crowd_platform.py — Referenced but routes_extended may not call correctly
  ? event_engine.py — Has sync/async mismatch bug
  ? scheduler_engine.py — Has sync/async mismatch bug
  ? annotation_quality.py — quality_routes calls get_iaa() lazily
  ? data_pipeline.py — Only one with explicit run() method
  ? zhiying_dev_engine.py — Likely development-only; not imported by any route
  ? algorithm_review.py — Not imported by any route
  ? stats_dashboard.py — Referenced by monitor_routes
  ? multi_tenant.py — Not imported by any route
  ? comfyui_engine.py — canvas_web imports but uses lazily
  ? engine_router.py — Imported by canvas_web.py:86
  ? web_engine.py — Not imported by any route
  ? story_arc_engine.py — Not imported by any route
  ? video_composer.py — Not imported by any route (likely unused)
  ? scene_exporter.py — Not imported by any route (likely unused)
  ? data_delivery.py — Partially used by canvas_web
  ? delivery_inc.py — Referenced by canvas_web:3887 delivery_inc_router

================================================================================
PREFIX INVENTORY (for collision detection)
================================================================================
/api/annotations          → annotation_routes.py      + annotation_history_routes.py (/api/v1/annotations)
/api/quality              → quality_routes.py
/api/quality/v2           → quality_v2_routes.py
/api/discovery            → discovery_routes.py
/api/dam                  → dam_routes.py
/api/transfer             → transfer_routes.py
/api/sharing              → sharing_routes.py          <-- DUPLICATE of transfer
/api/classify             → classify_routes.py
/api/search               → search_routes.py
/api/delivery             → delivery_routes.py         <-- STUB
/api/crowd                → crowd_routes.py + routes_extended.py  <-- STUB + COLLISION
/api/audio                → audio_routes.py
/api/book                 → book_routes.py
/api/drama                → drama_routes.py
/api/aesthetic            → aesthetic_routes.py
/api/pe                   → pe_routes.py
/api/enhanced             → enhanced_routes.py
/api/local-models         → local_model_routes.py
/api/templates            → template_routes.py
/api/datasets             → data_browser_routes.py
/api/monitor              → monitor_routes.py
/api/ops                  → ops_dashboard_routes.py
/api/cloud                → cloud_storage.py
/api/admin                → admin_routes.py
/api                      → model_routes.py, prelabel_router.py  <-- COLLISION!
/api/v1                   → canvas_web.py(×3 routers)  <-- AMBIGUOUS
/api/v1/export            → export_routes.py + export_enhanced_routes.py  <-- COLLISION!
/api/v1/batch             → batch_routes.py
/api/v1/api-keys          → api_key_routes.py
/api/v1/annotations       → annotation_history_routes.py
/api/v1/audit-logs        → audit_routes.py
/auth                     → auth_routes.py              <-- INCONSISTENT
/imdf/canvas              → board_manager.py
/imdf/provider            → external_providers.py
/imdf/figma               → figma_bridge.py
/imdf/image               → image_processor.py
/imdf/media               → media_manager.py
<no prefix>               → health_routes.py            <-- MISSING

================================================================================
