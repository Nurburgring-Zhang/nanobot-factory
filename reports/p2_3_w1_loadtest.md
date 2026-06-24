# P2-3-W1: 1000 Concurrent Load Baseline — Status Report

**Branch session:** mvs_f9f8b692b0b84848b5a1034119a642e6
**Workspace:** D:\Hermes\生产平台\nanobot-factory
**Date:** 2026-06-22 11:18 (Asia/Shanghai)
**Engine status:** **KILLED @ 30min** — partial completion, **retry required**

---

## TL;DR

- ✅ `tests/load/locustfile.py` written (15.8K, 5 personas, 16 endpoints, syntax-validated)
- ✅ `tests/load/start_server.ps1` + `stop_server.ps1` written
- ✅ `requirements-test.txt` updated with `locust==2.20.0` (installed)
- ✅ IMDF uvicorn proven bootable (loads all 73 route modules, `event_engine` initialises)
- ❌ 1000-concurrent / 5-min load run did NOT execute
- ❌ HTML report not generated
- ❌ p50/p95/p99 measurements missing

---

## 1. Goal recap (from task brief)

> 建立 1000 并发负载基线,确认 P2-1 后的架构能扛住真负载。

Required deliverables:
- `tests/load/locustfile.py` (5 user personas, 10+ scenarios)  ✅
- `tests/load/report.html` (Locust HTML report)  ❌
- `reports/p2_3_w1_loadtest.md` (this file)  ⚠ placeholder
- `requirements-test.txt` (locust==2.20.0)  ✅
- 8-worker uvicorn on port 8000  ✅ (boots; not held open long enough)
- p99 < 2000ms + error rate < 5% verification  ❌

---

## 2. What was built

### 2.1 `tests/load/locustfile.py` (15,816 bytes)

Five personas via `FastHttpUser` (gevent-based, low overhead per user):

| Class | Weight | % of 1000 | Endpoints exercised |
|---|---|---|---|
| `AnonymousUser` | 4 | ~40% | `/healthz`, `/readyz`, `/api/v1/health`, `/api/v1/health/ready` |
| `AuthenticatedUser` (viewer) | 2 | ~10% | `/auth/login`, `/auth/me`, `/api/users/me`, `/api/projects`, `/api/notifications` |
| `AnnotatorUser` | 3 | ~15% | `/api/assets`, `/api/tasks/recent`, `/api/projects`, `/api/notifications` |
| `ReviewerUser` | 2 | ~10% | `/api/canvas/templates`, `/api/canvas/{id}`, `/api/assets`, `/api/projects` |
| `AdminUser` | 2 | ~10% | `/api/stats/overview`, `/api/queue/health`, `/api/admin/stats`, `/api/admin/users`, `/api/projects`, `POST /api/projects` |

That's **16 distinct endpoints** (brief required 10+) across **5 personas** (brief required 5).

Key design decisions:

- **`FastHttpUser` over `HttpUser`** — gevent-backed, ~10x lower per-user memory, required to
  fit 1000 concurrent users in one process.
- **DB-seeded test users** (not API-registered) — bypasses `/auth/register` rate limit
  (10/min/IP) and lets us pre-create 400 users (100/role × 4 roles) before the swarm starts.
  `_seed_users()` runs in `events.test_start` listener and is idempotent (catches
  `sqlite3.IntegrityError`).
- **Failure policy override** — `_is_failure()` only counts 5xx and connection errors.
  4xx responses (401 missing token, 404 missing canvas, 422 validation) are expected
  business outcomes, NOT load-test failures. Default Locust policy would mark every
  authed-endpoint-without-token as a failure.
- **`wait_time = between(0.1, 0.8)`** — tighter than default (1-5s) to actually generate
  the target RPS at 1000 users. Default wait would cap us at ~200-500 RPS.

### 2.2 `tests/load/start_server.ps1` (2,543 bytes)

```powershell
$Env:PYTHONPATH = 'D:\Hermes\生产平台\nanobot-factory\backend'
$Env:IMDF_WEB_PORT = '8000'
$Env:UVICORN_WORKERS = '8'
$Env:RATE_LIMIT_ENABLED = 'false'    # disable slowapi during load test
$Env:JWT_SECRET = '...'              # from .env
```

Wraps `uvicorn imdf.api.canvas_web:app --host 127.0.0.1 --port 8000 --workers 8`.

**However** — the script uses `Start-Process` with a `Wait-Process` poll loop, which is
the wrong pattern for engine-killed agents (see §3.2). **Retry must use `cmd /c start /B` instead.**

### 2.3 `tests/load/stop_server.ps1` (631 bytes)

Kills any process bound to port 8000 (LISTEN state).

### 2.4 `requirements-test.txt`

```diff
  playwright==1.40.0
  pytest-playwright==0.4.4
+ locust==2.20.0
```

---

## 3. Why the load test did NOT run

### 3.1 First blocker: `ModuleNotFoundError: No module named 'imdf'`

IMDF's FastAPI app is at `backend/imdf/api/canvas_web.py`. To import it as
`imdf.api.canvas_web:app`, the `imdf/` directory must be on `sys.path`. The project
root (`nanobot-factory/`) does NOT contain `imdf/` — only `backend/imdf/`.

**Error trace** (`tests/load/server.log.err`, first attempt):
```
Traceback (most recent call last):
  File "D:\ComfyUI\.ext\Lib\site-packages\uvicorn\importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
ModuleNotFoundError: No module named 'imdf'
```

**Fix:** set `PYTHONPATH=D:\Hermes\生产平台\nanobot-factory\backend` (BOTH env var
AND `-WorkingDirectory backend/`). This was caught and fixed mid-session — server boot
logs (`server.log`) confirm 73 route modules loaded successfully afterwards.

### 3.2 Second blocker: Start-Process timeout killed uvicorn workers

Pattern used in `start_server.ps1`:
```powershell
Start-Process ... -PassThru | ForEach-Object { ... Wait-Process ... }
```

When the parent PowerShell session hits the Bash tool's timeout (30-180s), the entire
process tree is terminated — **including the detached uvicorn workers**. After two
attempts, the server process appeared in `Get-NetTCPConnection -LocalPort 8000` as
LISTEN, but disappeared seconds later (timeout from the parent shell).

**Fix (for retry):** use `cmd /c start /B` to launch uvicorn truly detached:

```powershell
$env:PYTHONPATH = 'D:\Hermes\生产平台\nanobot-factory\backend'
$env:IMDF_WEB_PORT = '8000'
$env:UVICORN_WORKERS = '8'
$env:RATE_LIMIT_ENABLED = 'false'
$env:JWT_SECRET = 'KFWonsp6d8L4zUg-UyMwFw9sIGF7yOQmBeiXWT47OCo'
cmd /c start /B "uvicorn" /D "D:\Hermes\生产平台\nanobot-factory\backend" ^
    D:\ComfyUI\.ext\python.exe -u -m uvicorn imdf.api.canvas_web:app ^
    --host 127.0.0.1 --port 8000 --workers 8 --log-level warning --no-access-log ^
    > tests\load\server.log 2> tests\load\server.log.err
```

`start /B` creates a process with no new console and no job-object association,
so it survives the calling shell's death.

### 3.3 Third blocker (rule violation): did not write deliverable draft at 14-min mark

Recurring pattern this week — see MEMORY.md for the full list (P2-1-W2, P2-2-W1,
P2-2-W2, P2-3-W2). The rule going forward: **write a draft deliverable.md at minute 12-14**,
even if it says "STATUS: BLOCKED", so the engine has something to mark complete and
the retry has clean handoff context.

---

## 4. Server boot evidence (from this session)

`tests/load/server.log` (last 5 lines of the boot that succeeded):

```
2026-06-22 11:07:20 - engines.event_engine - INFO - Event handlers initialized:
    FILE_UPLOADED→auto_tag, ANNOTATION_COMPLETED→quality_score, DATA_IMPORTED→auto_classify
2026-06-22 11:07:20 - imdf.api.canvas_web - INFO - {"status": "started", "event": "event_engine"}
2026-06-22 11:07:20 - imdf.api.canvas_web - INFO - {"event": "IMDF服务启动"}
```

This confirms the IMDF stack (canvas_web + 73 routers + event_engine + 64 engines)
imports and initialises correctly under 8-worker uvicorn. The architecture can boot;
it just needs to be kept alive for the 5-min load run.

---

## 5. Retry plan (≤ 18 min)

1. **0-2 min** — set env vars (PYTHONPATH + JWT_SECRET + RATE_LIMIT_ENABLED=false)
2. **2-3 min** — `cmd /c start /B` to launch uvicorn 8 workers, port 8000, redirected to `tests/load/server.log`
3. **3-5 min** — `for ($i=0;$i -lt 30;$i++) { sleep 1; Test-NetConnection -Port 8000 }` until LISTEN, then `httpx.get('http://127.0.0.1:8000/healthz')` verify 200
4. **5-6 min** — confirm locust can `import` locustfile.py (syntax check)
5. **6-16 min** — run locust:
   ```bash
   locust -f tests/load/locustfile.py --headless -u 1000 -r 100 --run-time 5m \
       --host http://127.0.0.1:8000 \
       --html tests/load/report.html \
       --csv tests/load/results
   ```
6. **16-17 min** — parse `tests/load/results_stats.csv`, check p99 < 2000ms + error rate < 5%
7. **17-18 min** — fill in §6 below with actual numbers; update this file; notify parent

---

## 6. (Placeholder — fill after retry)

### 6.1 Server response (anonymous probes)
| Endpoint | Method | p50 | p95 | p99 | Error % |
|---|---|---|---|---|---|
| `/healthz` | GET | TBD | TBD | TBD | TBD |
| `/readyz` | GET | TBD | TBD | TBD | TBD |
| `/api/v1/health` | GET | TBD | TBD | TBD | TBD |
| `/api/v1/health/ready` | GET | TBD | TBD | TBD | TBD |

### 6.2 Server response (authenticated)
| Endpoint | Method | p50 | p95 | p99 | Error % |
|---|---|---|---|---|---|
| `/auth/login` | POST | TBD | TBD | TBD | TBD |
| `/auth/me` | GET | TBD | TBD | TBD | TBD |
| `/api/users/me` | GET | TBD | TBD | TBD | TBD |
| `/api/projects` | GET | TBD | TBD | TBD | TBD |
| `/api/assets` | GET | TBD | TBD | TBD | TBD |
| `/api/tasks/recent` | GET | TBD | TBD | TBD | TBD |
| `/api/canvas/templates` | GET | TBD | TBD | TBD | TBD |
| `/api/canvas/{id}` | GET | TBD | TBD | TBD | TBD |
| `/api/stats/overview` | GET | TBD | TBD | TBD | TBD |
| `/api/queue/health` | GET | TBD | TBD | TBD | TBD |
| `/api/admin/stats` | GET | TBD | TBD | TBD | TBD |
| `/api/admin/users` | GET | TBD | TBD | TBD | TBD |
| `/api/notifications` | GET | TBD | TBD | TBD | TBD |
| `/api/projects` | POST | TBD | TBD | TBD | TBD |

### 6.3 Aggregates
- Total requests: TBD
- Total failures (5xx + connection): TBD
- Total RPS: TBD
- Median response time: TBD
- 95th percentile: TBD
- 99th percentile: TBD
- Max response time: TBD

### 6.4 Verdict
- **p99 < 2000ms**: TBD
- **Error rate < 5%**: TBD

---

## 7. Files in this deliverable

```
tests/load/
├── locustfile.py            # 15816 bytes, ready to run
├── start_server.ps1         # 2543 bytes, NEEDS REWRITE (use cmd /c start /B)
├── stop_server.ps1          # 631 bytes, OK
├── server.log               # last successful boot trace
└── server.log.err           # error log
requirements-test.txt        # updated with locust==2.20.0
```

---

## 8. Memory entry

Added entry **P2-3-W1 nanobot-factory 1000 concurrent load baseline (KILLED @ 30min)**
to `C:\Users\Administrator\.mavis\agents\coder\memory\MEMORY.md` with:
- The PYTHONPATH + WorkingDirectory double-fix
- The `cmd /c start /B` detachment pattern (replaces Start-Process for long-lived services)
- The 14-min deliverable-draft rule (now codified as cross-project lesson)