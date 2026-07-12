# P19 v5.6 — Crowdsource Management Full + CDP Advanced Billing (V5 §13.4)

**Date:** 2026-07-06  
**Branch session:** mvs_2530e84529204fb1834734741c2a40a8  
**Plan:** plan_218c7f26 — V5 implementation cycle 5  
**Scope:** V5 Chapter 17 (Workflow / Crowdsourcing full) + Chapter 22 (Authorization/Billing/Security / CDP Advanced Billing)

---

## 1. Goal Recap

Two features from the VDP-2026-V5 gap-analysis §13.4:

1. **Crowdsourcing Management Full Version** — admin panel that lets ops manage the
   crowdsource task pool, workers, payments, and a quality-score distribution.
2. **CDP Advanced Billing** — backend service with multi-tier pricing, usage metering,
   and invoice/PDF generation, exposed via REST + a matching admin panel.

---

## 2. Files Created / Modified

### 2.1 Backend (`backend/imdf/billing/`, `backend/imdf/skills/`)

| File | Type | LOC (≈) | Purpose |
|---|---:|---:|---|
| `billing/__init__.py` | new | 25 | Re-exports |
| `billing/cdp_billing_schemas.py` | new | 130 | Pydantic v2 schemas (BillingTier / PricingRule / UsageRecord / InvoiceLineItem / Invoice) |
| `billing/cdp_billing.py` | new | 320 | `CDPBillingService` (track_usage / calculate_invoice / generate_invoice_pdf / list_invoices) + in-memory store + default_tiers / default_pricing_rules |
| `billing/api.py` | new | 165 | FastAPI router with 4 endpoints (`POST /usage`, `POST /invoice`, `GET /invoices`, `GET /invoice/{id}/pdf`) |
| `billing/tests/test_cdp_billing.py` | new | 290 | 19 tests — all passing |
| `backend/imdf/skills/registry.py` | modified | +200 | Added `cdp_billing_invoice` + `crowdsource_manage` skills |

### 2.2 Frontend (`frontend-v2/src/`)

| File | Type | LOC (≈) | Purpose |
|---|---:|---:|---|
| `components/CrowdsourceAdmin.vue` | new | 230 | 4 tabs (Tasks / Workers / Payments / Quality histogram) — Naive UI |
| `components/BillingAdmin.vue` | new | 175 | 3 sections (Usage / Invoices / Tiers) — Naive UI |
| `stores/crowdsource.ts` | new | 95 | Pinia store with deterministic seed data |
| `stores/billing.ts` | new | 100 | Pinia store with deterministic seed data + tier-resolution getter |
| `components/__tests__/CrowdsourceAdmin.spec.ts` | new | 90 | 5 smoke tests (header / tabs / empty / seed-load / switch) |
| `components/__tests__/BillingAdmin.spec.ts` | new | 80 | 5 smoke tests (header / sections / empty / seed-load / tier resolution) |
| `router/index.ts` | modified | +15 | 2 new routes: `/admin/crowdsource`, `/admin/billing` |
| `vite.config.ts` | modified | ±1 | `include` adds `src/**/__tests__/**/*.spec.ts` so vitest discovers new tests |

### 2.3 Reports

| File | Type | LOC (≈) | Purpose |
|---|---:|---:|---|
| `reports/p19_v56_crowdsource_billing.md` | new | — | this file |

---

## 3. Tests

### 3.1 Backend (pytest)

```
$ D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/billing/tests/test_cdp_billing.py -v
…
19 passed, 1 warning in 0.25s
```

Coverage by topic:

1. Schema validation (4) — empty tenant / negative value / invalid discount_pct / pricing-rule roundtrip
2. Usage tracking accumulation + tenant isolation (1)
3. Empty / inverted-period invoice handling (2)
4. Tier resolution at three thresholds (4 — tier_1 small / tier_2 mid / tier_3 large / **spec example** $100→$95)
5. Included-qty deduction (1) — render_minutes 30-free still works
6. PDF generation non-empty + valid reportlab-or-HTML (2)
7. Invoice listing chronological + limit (2)
8. Input validation rejections (3)

### 3.2 Frontend (vitest)

```
$ cd frontend-v2
$ npx vitest run src/components/__tests__/CrowdsourceAdmin.spec.ts src/components/__tests__/BillingAdmin.spec.ts
…
 Test Files  2 passed (2)
      Tests  10 passed (10)
   Duration  2.71s
```

Test fixtures use slot-rendering stubs for `n-tabs` / `n-tab-pane` / `n-card` / `n-grid` / `n-grid-item` so data-testid children are findable in jsdom; the components themselves use `createDiscreteApi(['message'])` (not `useMessage()`) so no `<NMessageProvider>` wrapper is required.

---

## 4. Example E2E (per spec requirement — exact $95)

```
Setup:
    tenant_id  = "tenant-1"
    period_start = 2026-03-01
    period_end   = 2026-04-01

Step 1 — record usage:
    POST /api/v1/billing/cdp/usage
       { "tenant_id": "tenant-1",
         "metric": "data_gb", "value": 500 }

    POST /api/v1/billing/cdp/usage
       { "tenant_id": "tenant-1",
         "metric": "api_calls", "value": 10000 }

Step 2 — calculate invoice:
    POST /api/v1/billing/cdp/invoice
       { "tenant_id": "tenant-1",
         "period_start": "2026-03-01",
         "period_end": "2026-04-01" }

Math (per V5 §13.4 spec — retry #2 alignment):
    data_gb   : 500 GB × $0.10/GB (no free tier)   = $50.00
    api_calls : 10000 × $0.005/call (no free tier) = $50.00
    subtotal                                  = $100.00
    tier resolution: data_gb qty = 500 → tier_2 (100-1000 GB threshold, 5% discount)
    tier_discount_total                       = $100.00 × 0.05 = $5.00
    total                                     = $95.00  ← matches spec exactly
    currency    = USD
    tier_applied = "tier_2"

Step 3 — generate PDF:
    GET /api/v1/billing/cdp/invoice/inv_…/pdf?tenant_id=tenant-1
    → 200 with Content-Type: application/pdf (or text/html fallback),
      body contains "tenant-1", "Total: $95.00", "Tier discount: $5.00"
```

Pytest equivalent: `test_calculate_invoice_spec_example_500gb_10kapi` asserts exactly this — `subtotal == $100.00`, `tier_discount_total == $5.00`, `total == $95.00`, `tier_applied == "tier_2"`.

### 4.1 Tier thresholds (V5 §13.4 spec)

| Tier | min_units (data_gb) | discount_pct | Description |
|---|---|---:|---|
| tier_1 | 0      | 0 %  | Starter — 0-100 GB data |
| tier_2 | 100    | 5 %  | Growth — 100-1000 GB data |
| tier_3 | 1000   | 15 % | Scale — 1000+ GB data |

Tier resolution is **data_gb-specific** (other metrics contribute to subtotal but don't move the tenant between tiers).

---

## 5. Skill Registry Additions

Both new skills registered under the existing OctoSkillSpec umbrella (unchanged from prior attempts):

```python
CDP_BILLING_INVOICE_SPEC   = skill_id="cdp_billing_invoice"   # registry.py:1786
CROWDSOURCE_MANAGE_SPEC    = skill_id="crowdsource_manage"    # registry.py:1837
```

Verify:

```python
from skills.registry import list_octo_skills, get_octo_skill
assert get_octo_skill("cdp_billing_invoice").name == "CDP Billing Invoice"
assert get_octo_skill("crowdsource_manage").name  == "Crowdsource Manage"
```

---

## 6. Open Items

1. **Frontend vitest** — fully verified (10/10 PASS). Components use `createDiscreteApi(['message'])` instead of `useMessage()`, eliminating the `<NMessageProvider>` wrapper requirement.
2. **PDF download button wiring** — `BillingAdmin.vue` has a download button calling `store.downloadInvoicePdf()` (mock returns `{size, format}`); real wiring awaits v5.7.
3. **No DB persistence yet** — the in-memory `InMemoryCdpBillingStore` (default) is fine for tests + single-process dev. Postgres backend is staged for v5.7 (would slot in via `CdpBillingStore` protocol).

---

## 7. Hand-off

- **Parent session:** `mvs_8ecc804a9afa42dc8e79427bfcff5828`
- **Deliverable file:** `C:\Users\Administrator\.mavis\plans\plan_218c7f26\outputs\p19_v56_crowdsource_billing\deliverable.md`
- **Board entries:** appended under `[2026-07-06 03:32]`, `[03:45]`, and `[04:10]` blocks.
