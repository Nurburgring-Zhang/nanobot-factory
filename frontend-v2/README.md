# nanobot-factory frontend-v2

Vue 3 + TypeScript + Pinia + Naive UI scaffold for the **nanobot-factory 智影 (ZhiYing)** data generation platform.

This directory is a **monorepo SPA** that complements (does not replace) the legacy `frontend/` directory (R6.5 vanilla) and the `backend/imdf/` monolith. The 12 application modules here correspond to the 12 planned microservices.

## Stack

- **Vue 3.3** + `<script setup>` composition API
- **TypeScript 5.0** with strict mode and `@/*` path alias
- **Pinia 2.1** for state management (auth, api)
- **Vue Router 4** with 12 lazy-loaded module routes
- **Naive UI 2.34** component library
- **Axios 1.6** with JWT interceptor
- **ECharts 5.4** + **vue-echarts 7** for dashboards
- **Vue Flow 1.0** for workflow editor (matches the platform's `nodes/` engine runtime)
- **Vite 5** dev server + build tool

## Quick start

```bash
# 1. install deps (uses npm registry; --registry=https://registry.npmmirror.com if behind GFW)
cd frontend-v2
npm install

# 2. dev (Vite serves on http://127.0.0.1:5173, proxies /api/* to gateway:8000)
npm run dev

# 3. type-check + production build
npm run build

# 4. preview built bundle
npm run preview
```

The dev server proxies `/api/*` to `VITE_API_PROXY_TARGET` (default `http://localhost:8000`, the API Gateway). Set `VITE_API_BASE` for production builds.

## Directory layout

```
frontend-v2/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── .env.development
├── .env.production
├── public/                       # static assets served at root
├── src/
│   ├── main.ts                   # bootstrap: Pinia + Router + Naive UI
│   ├── App.vue                   # root component (N-ConfigProvider + N-MessageProvider)
│   ├── router/
│   │   └── index.ts              # 12 module routes
│   ├── stores/
│   │   ├── auth.ts               # JWT login / refresh / logout
│   │   └── api.ts                # Axios instance + JWT interceptor
│   ├── layouts/
│   │   └── DefaultLayout.vue     # sidebar + header + content area
│   ├── views/
│   │   ├── Login.vue             # JWT login page
│   │   ├── Dashboard.vue         # /api/stats/overview dashboard
│   │   ├── Dataset.vue           # data asset management
│   │   ├── Annotation.vue        # annotation studio (stub)
│   │   ├── Review.vue            # review/QA (stub)
│   │   ├── Scoring.vue           # scoring/eval (stub)
│   │   ├── Workflows.vue         # Vue Flow workflow editor
│   │   ├── Engines.vue           # engine inventory (stub)
│   │   ├── Tasks.vue             # Celery task queue (stub)
│   │   ├── Users.vue             # user management (stub)
│   │   ├── Billing.vue           # usage/billing (stub)
│   │   ├── Monitoring.vue        # monitoring (stub)
│   │   └── Settings.vue          # system settings (stub)
│   ├── components/               # reusable UI bits (kept minimal in W1)
│   └── types/                    # shared TS types
└── README.md
```

## The 12 modules (microservice-aligned)

Each module corresponds to one of the planned microservices. W1 only ships Dashboard + Login in full; the other 10 are intentionally lightweight stubs (`<h2>` placeholder + "TODO: implement view") so the route map compiles and the layout/permissions can be validated end-to-end.

| # | Path | Module | Backend service |
|---|------|--------|-----------------|
| 1 | `/`            | Dashboard   | stats / overview |
| 2 | `/dataset`     | Dataset     | dataset_service  |
| 3 | `/annotation`  | Annotation  | annotation_service |
| 4 | `/review`      | Review      | review_service |
| 5 | `/scoring`     | Scoring     | scoring_service |
| 6 | `/workflows`   | Workflows   | workflow_service |
| 7 | `/engines`     | Engines     | engine_registry |
| 8 | `/tasks`       | Tasks       | celery_orchestrator |
| 9 | `/users`       | Users       | user_service |
| 10 | `/billing`    | Billing     | billing_service |
| 11 | `/monitoring` | Monitoring  | observability |
| 12 | `/settings`   | Settings    | config_service |

## Auth flow

- `POST /api/auth/login` → returns `{ access_token, refresh_token, user }` (set by R9.5 auth)
- `access_token` is kept in Pinia `auth.token` and persisted to `localStorage` under `imdf.auth`
- The Axios interceptor attaches `Authorization: Bearer <token>` to every `/api/*` request
- On `401`, the interceptor attempts one `/api/auth/refresh` then redirects to `/login`
- `csrf_token` (when present) is read from a double-submit cookie and added to mutating requests

## Verification

This scaffold passed:

- `npm install` (no errors, lockfile generated)
- `vue-tsc --noEmit` (0 errors, strict mode)
- `vite build` (sourcemap-disabled production bundle)
- `npm run dev` listening on `127.0.0.1:5173` returning valid Vue HTML

See `reports/p3_7_w1_vue3_scaffold.md` for the full audit log.