# P3-3-W2 Report — workflow / notification / search 3 services (ports 8009-8011)

**Project**: `D:\Hermes\生产平台\nanobot-factory` (imdf sub-project)
**Date**: 2026-06-22
**Author**: coder (P3-3-W2)
**Status**: DONE — TestClient 21/21 PASS, live uvicorn boot + httpx + WS all PASS

---

## 1. Objective

Complete the 12-service split by extracting the last 3 bounded contexts:

| Service | Port | Surface | Pre-existing engine reused |
|---------|------|---------|----------------------------|
| **workflow-service** | 8009 | DAG definitions, runs, monitoring, 53 templates | `imdf/engines/scheduler_engine.py` (mounted as legacy) |
| **notification-service** | 8010 | Inbox + email + webhook fan-out + WebSocket | `imdf/engines/event_engine.py`, `imdf/engines/webhook_engine.py` |
| **search-service** | 8011 | Text / semantic / vector retrieval, pgvector-capable | `imdf/engines/vector_retrieval.py`, `imdf/engines/semantic_search.py`, P3-1-W1 pgvector |

After W1 (agent-service:8008) and this W2, **all 12** microservice
directories exist under `backend/services/`.

---

## 2. Files

### 2.1 Created (10 files, ~52 KB)

```
backend/services/workflow_service/__init__.py
backend/services/workflow_service/main.py         FastAPI app, port 8009, lifespan + cors
backend/services/workflow_service/routes.py       13 endpoints (workflows CRUD + run + cancel + templates + stats)
backend/services/workflow_service/dag.py          DAGRuntime singleton + topo waves + per-node retry + logs
backend/services/workflow_service/templates.py    53 templates (image/video/audio/annotation/cleaning/scoring/dataset/export/ops)
backend/services/notification_service/__init__.py
backend/services/notification_service/main.py     FastAPI app, port 8010, cors + legacy webhook mount
backend/services/notification_service/routes.py   REST (publish/list/email) + WebSocket /ws /ws/notifications
backend/services/search_service/__init__.py
backend/services/search_service/main.py           FastAPI app, port 8011, cors + legacy search mount
backend/services/search_service/routes.py         SearchEngine (BM25 + TF-IDF cosine + pgvector) + 10 endpoints
```

### 2.2 Updated (2 files)

```
docker-compose.yml          +88 lines (3 service blocks: workflow/notification/search)
backend/gateway/routes.yaml +27 lines (5 routing entries: agent × 2 + workflow + notification + search)
```

### 2.3 Verification scripts (intermediate, kept under plan outputs)

```
C:\Users\Administrator\.mavis\plans\plan_480a3ce1\outputs\p3_3_w2_more_services\smoke_test.py
C:\Users\Administrator\.mavis\plans\plan_480a3ce1\outputs\p3_3_w2_more_services\spawn_and_test.py
C:\Users\Administrator\.mavis\plans\plan_480a3ce1\outputs\p3_3_w2_more_services\live_probes.py
C:\Users\Administrator\.mavis\plans\plan_480a3ce1\outputs\p3_3_w2_more_services\ws_probe.py
```

---

## 3. Verification

### 3.1 TestClient smoke (21/21 PASS)

Run with:

```powershell
$env:PYTHONPATH='D:\Hermes\生产平台\nanobot-factory\backend'
D:\ComfyUI\.ext\python.exe `
   C:\Users\Administrator\.mavis\plans\plan_480a3ce1\outputs\p3_3_w2_more_services\smoke_test.py
```

Result:

```
workflow-service:     7/7 PASS
notification-service: 7/7 PASS
search-service:       7/7 PASS
GRAND TOTAL: 21/21 PASS
```

Per-endpoint:

- **workflow-service** (7): `/healthz`, list templates, get one template,
  clone template -> workflow, list workflows, sync run, stats summary.
- **notification-service** (7): `/healthz`, list channels, post inbox,
  list, post email, subscribe, email log.
- **search-service** (7): `/healthz`, text search, semantic search,
  vector search, add document, list documents, stats.

### 3.2 Live uvicorn boot (3 services on 8009/8010/8011)

`spawn_and_test.py` boots the 3 services with `subprocess.Popen` +
`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, polls `socket.create_connection`
for each port, then probes with httpx:

```
[wf] listening on 8009
[nt] listening on 8010
[sr] listening on 8011

HTTP probe results:
  wf: status=200 body={'status': 'ok', 'service': 'workflow-service',
       'version': '0.1.0', 'templates': 53, 'workflows': 2, 'runs': 0}
  nt: status=200 body={'status': 'ok', 'service': 'notification-service',
       'version': '0.1.0', 'inbox_size': 0, 'subscribers': 0, 'email_log_size': 0}
  sr: status=200 body={'status': 'ok', 'service': 'search-service',
       'version': '0.1.0', 'corpus_size': 10, 'vector_dim': 256, 'pgvector_enabled': False}
```

### 3.3 Live HTTP probes (`live_probes.py`)

```
GET  8009 /api/v1/workflows/templates      -> 200 total=53
POST 8009 /api/v1/workflows                -> 201 id=wf-d412b87685f3
POST 8009 /api/v1/workflows/{id}/run       -> 200 status=succeeded
POST 8010 /api/v1/notifications            -> 201 id=notif-e9807dae6c39
GET  8010 /api/v1/notifications            -> 200 total=1
GET  8011 /api/v1/search/text?q=diffusion  -> 200 total=1 first=Image Generation Overview
GET  8011 /api/v1/search/semantic          -> 200 total=3
All live HTTP probes PASS
```

### 3.4 WebSocket probe (`ws_probe.py`)

```
hello: type=hello subscriber_id=ws-2648acf8
reply: type=pong
WS probe PASS
```

### 3.5 agent-service cross-check (P3-3-W1)

Verified the parallel W1 worker completed successfully:

```
agent-service /healthz: 200
{'status': 'ok', 'service': 'agent-service', 'version': '0.1.0',
 'agent_types': 15, ...}
```

15 agent types registered — matches the P3-3-W1 spec.

---

## 4. Endpoint catalogue

### workflow-service (8009)

| Method | Path | Purpose |
|--------|------|---------|
| GET    | /healthz | liveness |
| GET    | /api/v1/workflows/templates | list 53 templates (filter: category, q) |
| GET    | /api/v1/workflows/templates/{id} | one template |
| POST   | /api/v1/workflows/templates/{id}/clone | clone -> workflow |
| GET    | /api/v1/workflows | list workflows (filter: tag) |
| POST   | /api/v1/workflows | create workflow |
| GET    | /api/v1/workflows/{id} | get one |
| PUT    | /api/v1/workflows/{id} | update (bumps version) |
| DELETE | /api/v1/workflows/{id} | delete |
| POST   | /api/v1/workflows/{id}/run | execute (sync/async) |
| GET    | /api/v1/workflows/runs | list runs |
| GET    | /api/v1/workflows/runs/{run_id} | run status + per-node state |
| POST   | /api/v1/workflows/runs/{run_id}/cancel | cancel a running run |
| GET    | /api/v1/workflows/stats/summary | workflow/run counts |

### notification-service (8010)

| Method | Path | Purpose |
|--------|------|---------|
| GET    | /healthz | liveness |
| GET    | /api/v1/notifications/channels | list 4 channels |
| POST   | /api/v1/notifications | publish (channel: inbox/ws/email/webhook) |
| GET    | /api/v1/notifications | list inbox |
| GET    | /api/v1/notifications/{id} | get one |
| POST   | /api/v1/notifications/broadcast | publish many |
| POST   | /api/v1/notifications/email | send email (SMTP or log) |
| GET    | /api/v1/notifications/email/log | inspect email log |
| POST   | /api/v1/notifications/subscribe | register subscriber (test) |
| DELETE | /api/v1/notifications/subscribe/{sub} | unregister |
| WS     | /ws/notifications | live push + heartbeat + publish-from-client |

### search-service (8011)

| Method | Path | Purpose |
|--------|------|---------|
| GET    | /healthz | liveness (corpus_size, vector_dim, pgvector_enabled) |
| GET    | /api/v1/search/text | BM25 keyword search |
| GET    | /api/v1/search/semantic | hybrid vector + BM25 (alpha param) |
| GET    | /api/v1/search/vector | vector cosine search |
| POST   | /api/v1/search/vector/query | vector search from raw embedding |
| POST   | /api/v1/search/documents | ingest document (pgvector upsert when enabled) |
| GET    | /api/v1/search/documents | list corpus |
| GET    | /api/v1/search/documents/{id} | get one |
| DELETE | /api/v1/search/documents/{id} | delete |
| GET    | /api/v1/search/stats | corpus + modality + tag stats |

---

## 5. 12-service cumulative map (after W1 + W2)

```
Port  Service                Owner
8000  gateway                P3-1-W2
8001  user-service           P3-2-W1
8002  asset-service          P3-2-W1
8003  annotation-service     P3-2-W1
8004  cleaning-service       P3-2-W2
8005  scoring-service        P3-2-W2
8006  dataset-service        P3-2-W2
8007  evaluation-service     P3-2-W2
8008  agent-service          P3-3-W1
8009  workflow-service       P3-3-W2   <-- this task
8010  notification-service   P3-3-W2   <-- this task
8011  search-service         P3-3-W2   <-- this task
```

12/12 service directories under `backend/services/`.
`backend/gateway/routes.yaml` exposes all 12 with `require_auth: true`.
`docker-compose.yml` registers all 12 as deployable services.

---

## 6. Notes for the next worker

1. **Real worker dispatch**: the workflow-service executor currently stubs
   each node with a 50 ms sleep. To actually run cleaning/scoring/etc.,
   wire `DAGRuntime._execute_node` to call `httpx` against the right
   microservice (port 8004/8005/8003/etc.) keyed on `node.node_type`.

2. **pgvector enablement**: set `PG_DSN=postgresql://postgres:postgres@postgres:5432/imdf`
   in the `search-service` container environment (see commented line in
   `docker-compose.yml`). The service will auto-create
   `search_corpus(id, title, content, tags, embedding vector(256))`
   and upsert every new document.

3. **SMTP enablement**: set `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD`
   in the `notification-service` container env to switch email from
   "log fallback" to real delivery. The default `email_log` deque
   (maxlen=500) is still populated either way.

4. **WebSocket auth**: the WS endpoint currently accepts any client. If
   you need JWT-on-connect, add a query-param token and validate in
   `_ws_handler` before `accept()`.
