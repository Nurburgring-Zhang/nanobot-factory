"""R10.5-Worker-2 商业化测试套件

覆盖:
- 账单: 用量计费 + 月度发票 + tiered pricing 算得对
- 数据导出: JSON / CSV 格式标准
- 审计: hash chain 完整 + 篡改检出
- 多租户: 隔离 + 配额 hard/soft/audit

目标: ≥ 15 用例全 PASS

设计:
- 业务核心用 InMemory store (无文件副作用)
- 路由用 mini FastAPI app + TestClient
- 每个测试独立构造 backend 实例 (避免模块级 state 污染)
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import os
from pathlib import Path
from typing import Dict, List

import pytest

# ── Path setup ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMDF_ROOT = PROJECT_ROOT
sys.path.insert(0, str(IMDF_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))


# ── 业务核心 import ─────────────────────────────────────────────────
from business.billing import (
    UsageMeter, UsageEvent, InMemoryUsageStore, JsonlUsageStore,
    TieredPricing, PricingTier, InvoiceEngine,
    Invoice, LineItem, utc_now_period, _month_range,
)
from business.data_exporter import (
    JSONExporter, CSVExporter, ExportFormat, export_data, SCHEMA_VERSION,
)
from business.audit_log import (
    AuditLog, AuditEntry, InMemoryAuditStore, JsonlAuditStore,
    GENESIS_HASH,
)
from business.tenant import (
    Tenant, Quota, QuotaDecision,
    TenantRegistry, assert_tenant_isolation,
)
from decimal import Decimal


# ============================================================================
# A. Billing — 用量计费 / 阶梯定价 / 月度发票
# ============================================================================

class TestBilling:
    """账单核心测试."""

    def test_usage_meter_record_and_query(self):
        """A1: 用量计费 — 记录 + 查询."""
        store = InMemoryUsageStore()
        meter = UsageMeter(store)
        m1 = meter.record("acme", "api_calls", 100, unit="call", ts=1700000000.0)
        m2 = meter.record("acme", "api_calls", 50, unit="call", ts=1700001000.0)
        meter.record("acme", "storage_gb_hour", 2, unit="gb_hour", ts=1700000500.0)
        # 不同租户不应混入
        meter.record("globex", "api_calls", 999, unit="call", ts=1700000500.0)

        start, end = _month_range("2023-11")
        events = meter.events_for("acme", "2023-11")
        assert len(events) == 3
        assert sum(int(e.qty) for e in events if e.metric == "api_calls") == 150

    def test_tiered_pricing_free_no_overage(self):
        """A2: Free tier — 完全在 included 内, total_cents = base_fee = 0."""
        store = InMemoryUsageStore()
        meter = UsageMeter(store)
        meter.record("free_user", "api_calls", 500, unit="call")
        events = meter.events_for("free_user", utc_now_period())
        inv = InvoiceEngine(TieredPricing.default()).build(
            "free_user", utc_now_period(), "free", events,
        )
        assert inv.subtotal_cents == 0
        assert inv.total_cents == 0
        assert inv.tier == "free"

    def test_tiered_pricing_pro_overage(self):
        """A3: Pro tier — 超过 included 后按 overage 阶梯计费."""
        store = InMemoryUsageStore()
        meter = UsageMeter(store)
        # Pro: api_calls included=100000, overage=(1000, 5cents)
        # 用 105000 = 5000 超量 = 5 units * 5 cents = 25 cents
        meter.record("pro_user", "api_calls", 105000, unit="call")
        events = meter.events_for("pro_user", utc_now_period())
        inv = InvoiceEngine(TieredPricing.default()).build(
            "pro_user", utc_now_period(), "pro", events,
        )
        # base 2900 + api overage 25 = 2925
        assert inv.subtotal_cents == 2900 + 25
        assert inv.total_cents == 2900 + 25
        # 单 line item
        api_items = [li for li in inv.line_items if li.metric == "api_calls"]
        assert len(api_items) == 1
        assert api_items[0].amount_cents == 25

    def test_tiered_pricing_enterprise_base_fee(self):
        """A4: Enterprise tier — base $299 + 完整 included 不超."""
        store = InMemoryUsageStore()
        meter = UsageMeter(store)
        # Enterprise: api_calls included=1M, storage=5000, render=600
        meter.record("ent_user", "api_calls", 500000, unit="call")
        meter.record("ent_user", "storage_gb_hour", 1000, unit="gb_hour")
        meter.record("ent_user", "render_minutes", 100, unit="minute")
        events = meter.events_for("ent_user", utc_now_period())
        inv = InvoiceEngine(TieredPricing.default()).build(
            "ent_user", utc_now_period(), "enterprise", events,
        )
        assert inv.subtotal_cents == 29900  # 只有 base fee
        assert inv.tier == "enterprise"

    def test_invoice_tax_and_currency(self):
        """A5: 发票 tax + 币种."""
        store = InMemoryUsageStore()
        meter = UsageMeter(store)
        meter.record("acme", "api_calls", 150, unit="call")
        events = meter.events_for("acme", utc_now_period())
        # 10% 税
        eng = InvoiceEngine(TieredPricing.default(), tax_rate=Decimal("0.10"))
        inv = eng.build("acme", utc_now_period(), "free", events, currency="CNY")
        assert inv.currency == "CNY"
        assert inv.subtotal_cents == 0
        assert inv.tax_cents == 0
        assert inv.total_cents == 0
        # Pro tier + tax
        meter.record("acme", "api_calls", 100001, unit="call")
        events = meter.events_for("acme", utc_now_period())
        inv = eng.build("acme", utc_now_period(), "pro", events)
        # base 2900 + overage ceil(1/1000)*5 = 1*5 = 5 → subtotal 2905
        # tax 10% → 291 (round HALF_UP) → total 3196
        assert inv.subtotal_cents == 2900 + 5
        assert inv.tax_cents == 291
        assert inv.total_cents == 2900 + 5 + 291

    def test_invoice_export_csv(self):
        """A6: 发票 CSV 导出可解析."""
        store = InMemoryUsageStore()
        meter = UsageMeter(store)
        meter.record("acme", "api_calls", 100, unit="call")
        events = meter.events_for("acme", utc_now_period())
        inv = InvoiceEngine(TieredPricing.default()).build(
            "acme", utc_now_period(), "free", events,
        )
        csv_text = InvoiceEngine(TieredPricing.default()).export_csv(inv)
        # header
        assert "metric" in csv_text and "amount_cents" in csv_text
        assert "api_calls" in csv_text

    def test_period_validation(self):
        """A7: period 格式错误应 raise."""
        with pytest.raises(ValueError):
            _month_range("2026/05")
        with pytest.raises(ValueError):
            _month_range("invalid")


# ============================================================================
# B. Data Exporter — JSON / CSV 标准
# ============================================================================

class TestDataExporter:
    """数据导出测试."""

    def test_json_envelope_shape(self):
        """B1: JSON 导出包含 schema_version + exported_at + records."""
        records = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
        out = JSONExporter().export(records, meta={"source": "test"})
        data = json.loads(out)
        assert data["schema_version"] == SCHEMA_VERSION
        assert "exported_at" in data and "T" in data["exported_at"]
        assert data["count"] == 2
        assert len(data["records"]) == 2
        assert data["meta"]["source"] == "test"

    def test_csv_utf8_bom_and_header(self):
        """B2: CSV 导出 UTF-8 BOM + header + row."""
        records = [{"id": 1, "name": "张三"}, {"id": 2, "name": "李四"}]
        blob = CSVExporter(include_bom=True).export_to_bytes(records)
        assert blob.startswith(b"\xef\xbb\xbf")
        text = blob.decode("utf-8")
        lines = text.lstrip("\ufeff").splitlines()
        assert lines[0] == "id,name"
        assert "张三" in text and "李四" in text

    def test_csv_column_ordering_preserved(self):
        """B3: CSV 列顺序 = first seen."""
        records = [{"b": 2, "a": 1}, {"a": 3, "b": 4, "c": 5}]
        text = CSVExporter(include_bom=False).export(records)
        lines = text.splitlines()
        assert lines[0] == "b,a,c"
        # 第二行 a 在第 2 列 (没有 c)
        assert lines[1].split(",")[1] == "1"
        # 第三行有 c
        assert lines[2].split(",")[2] == "5"

    def test_csv_quoting_special_chars(self):
        """B4: CSV 含逗号/引号/换行的字段应被正确引用."""
        records = [{"text": 'hello, "world"\nnew'}]
        text = CSVExporter(include_bom=False).export(records)
        # RFC4180: 引号字段, 内部引号用双引号转义
        assert '"hello, ""world""' in text
        # 完整可被 csv 解析
        import csv as _csv
        import io
        rdr = _csv.reader(io.StringIO(text))
        rows = list(rdr)
        assert rows[1][0] == 'hello, "world"\nnew'

    def test_export_data_dispatcher(self):
        """B5: export_data 顶层入口分发 json/csv."""
        records = [{"x": 1}]
        json_bytes = export_data(records, fmt="json")
        csv_bytes = export_data(records, fmt="csv")
        assert json.loads(json_bytes.decode("utf-8"))["count"] == 1
        assert csv_bytes.startswith(b"\xef\xbb\xbf")
        with pytest.raises(ValueError):
            export_data(records, fmt="xml")

    def test_json_normalize_pydantic_and_dataclass(self):
        """B6: JSONExporter 自动 normalize dataclass / dict 嵌套."""
        from dataclasses import dataclass

        @dataclass
        class User:
            id: int
            name: str

        records = [User(1, "alice"), {"k": User(2, "bob")}]
        out = JSONExporter().export(records)
        data = json.loads(out)
        assert data["records"][0]["name"] == "alice"
        assert data["records"][1]["k"]["name"] == "bob"


# ============================================================================
# C. Audit Log — 不可篡改 hash chain
# ============================================================================

class TestAuditLog:
    """审计日志测试."""

    def test_chain_initial(self):
        """C1: 空 log verify ok=True."""
        log = AuditLog(InMemoryAuditStore())
        ok, bad = log.verify_chain()
        assert ok is True
        assert bad == -1

    def test_chain_append_and_verify(self):
        """C2: 多条 append 后链仍完整."""
        log = AuditLog(InMemoryAuditStore())
        log.append("alice", "create_user", "u_1", {"role": "admin"})
        log.append("alice", "login", "u_1")
        log.append("bob", "delete_user", "u_2")
        ok, bad = log.verify_chain()
        assert ok is True
        entries = log.query()
        assert len(entries) == 3
        assert entries[0].seq == 1
        assert entries[2].seq == 3
        # prev_hash 串联
        assert entries[1].prev_hash == entries[0].entry_hash
        assert entries[2].prev_hash == entries[1].entry_hash

    def test_tamper_detection_payload(self):
        """C3: 篡改 payload 后 verify 失败."""
        log = AuditLog(InMemoryAuditStore())
        log.append("alice", "create_user", "u_1")
        log.append("alice", "login", "u_1")
        log.append("bob", "delete_user", "u_2")
        # 模拟磁盘篡改: 直接改 store 里的 payload
        store_entries = log.store.load_all()
        store_entries[1].payload["malicious"] = "true"
        # 重新写回 store (审计日志自身的容错测试)
        log.store._entries = store_entries  # type: ignore[attr-defined]
        ok, bad = log.verify_chain()
        assert ok is False
        assert bad == 2

    def test_tamper_detection_prev_hash(self):
        """C4: 篡改 prev_hash 后 verify 失败."""
        log = AuditLog(InMemoryAuditStore())
        log.append("alice", "create_user", "u_1")
        log.append("bob", "login", "u_2")
        store_entries = log.store.load_all()
        store_entries[1].prev_hash = GENESIS_HASH
        log.store._entries = store_entries  # type: ignore[attr-defined]
        ok, bad = log.verify_chain()
        assert ok is False
        assert bad == 2

    def test_query_filters(self):
        """C5: query 按 actor/action/target 过滤."""
        log = AuditLog(InMemoryAuditStore())
        log.append("alice", "create_user", "u_1")
        log.append("alice", "login", "u_1")
        log.append("bob", "create_user", "u_2")
        assert len(log.query(actor="alice")) == 2
        assert len(log.query(action="login")) == 1
        assert len(log.query(target="u_2")) == 1
        assert len(log.query(actor="alice", action="create_user")) == 1

    def test_persist_and_reload_jsonl(self, tmp_path):
        """C6: JsonlAuditStore 持久化 + 重启后链仍可 verify."""
        path = tmp_path / "audit.jsonl"
        s1 = JsonlAuditStore(str(path))
        log1 = AuditLog(s1)
        log1.append("alice", "create", "u_1")
        log1.append("bob", "create", "u_2")
        log1.append("alice", "delete", "u_3")
        # 新 store 读旧文件
        s2 = JsonlAuditStore(str(path))
        log2 = AuditLog(s2)
        ok, bad = log2.verify_chain()
        assert ok is True
        assert len(log2.query()) == 3
        # 续写
        log2.append("bob", "delete", "u_4")
        ok, bad = log2.verify_chain()
        assert ok is True


# ============================================================================
# D. Tenant — 隔离 + 配额
# ============================================================================

class TestTenant:
    """多租户测试."""

    def test_create_and_get(self):
        """D1: 创建 + 查询."""
        r = TenantRegistry()
        t = r.create("acme", "Acme Inc", tier="pro")
        assert t.tenant_id == "acme"
        assert r.get("acme") is not None
        assert r.get("nonexistent") is None

    def test_create_duplicate_rejected(self):
        """D2: 重复 tenant_id 应拒绝."""
        r = TenantRegistry()
        r.create("acme", "Acme")
        with pytest.raises(ValueError):
            r.create("acme", "Acme2")

    def test_invalid_tenant_id_rejected(self):
        """D3: 非法 tenant_id 字符拒绝."""
        r = TenantRegistry()
        with pytest.raises(ValueError):
            r.create("bad name!", "Bad")

    def test_quota_hard_block(self):
        """D4: 硬配额超额返回 hard_block + allowed=False."""
        r = TenantRegistry()
        t = r.create("acme", "Acme", tier="free")
        r.update_quota("acme", "api_calls", hard=100, soft=80, audit=50, unit="call")
        d = r.check_quota("acme", "api_calls", current=150)
        assert d.allowed is False
        assert d.level == "hard_block"
        assert "hard quota" in d.reason

    def test_quota_soft_warn(self):
        """D5: 软配额超额 allowed=True 但 level=soft_warn."""
        r = TenantRegistry()
        r.create("acme", "Acme", tier="free")
        r.update_quota("acme", "api_calls", hard=100, soft=80, audit=50, unit="call")
        d = r.check_quota("acme", "api_calls", current=85)
        assert d.allowed is True
        assert d.level == "soft_warn"

    def test_quota_audit_warn(self):
        """D6: 审计配额触发 allowed=True, level=audit_warn."""
        r = TenantRegistry()
        r.create("acme", "Acme", tier="free")
        r.update_quota("acme", "api_calls", hard=100, soft=80, audit=50, unit="call")
        d = r.check_quota("acme", "api_calls", current=55)
        assert d.allowed is True
        assert d.level == "audit_warn"

    def test_quota_disabled_tenant(self):
        """D7: 禁用租户任何用量 hard_block."""
        r = TenantRegistry()
        r.create("acme", "Acme")
        r.disable("acme")
        d = r.check_quota("acme", "api_calls", current=1)
        assert d.allowed is False
        assert "disabled" in d.reason

    def test_quota_unknown_metric(self):
        """D8: 无配额 metric 默认允许."""
        r = TenantRegistry()
        r.create("acme", "Acme")
        d = r.check_quota("acme", "unknown_metric", current=999999)
        assert d.allowed is True
        assert d.level == "ok"

    def test_isolation_helper(self):
        """D9: assert_tenant_isolation 一致通过 / 不一致拒绝."""
        assert_tenant_isolation("acme", "acme")  # 不抛
        with pytest.raises(PermissionError):
            assert_tenant_isolation("acme", "globex")

    def test_registry_persistence(self, tmp_path):
        """D10: 持久化 + 重启后状态保留."""
        path = tmp_path / "tenants.json"
        r1 = TenantRegistry(storage_path=str(path))
        r1.create("acme", "Acme", tier="pro")
        r1.update_quota("acme", "api_calls", hard=50)
        # 重启
        r2 = TenantRegistry(storage_path=str(path))
        t = r2.get("acme")
        assert t is not None
        assert t.tier == "pro"
        assert t.quotas["api_calls"].hard == 50


# ============================================================================
# E. Router — 4 routers via TestClient
# ============================================================================

@pytest.fixture
def business_app():
    """构造一个独立的 mini FastAPI app 用于 router 测试."""
    # 注意: r10_5_business_routes 内部使用模块级 _STATE, 跨测试会累积
    # 这里只用 tenant_id 不冲突的方式测 — 每次用 unique ID
    from fastapi import FastAPI
    from api.r10_5_business_routes import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(business_app):
    from fastapi.testclient import TestClient
    return TestClient(business_app, raise_server_exceptions=False)


class TestBusinessRouter:
    """路由层端到端测试."""

    def test_tenant_crud_flow(self, client):
        """E1: tenant CRUD 完整流程."""
        tid = "router_tenant_1"
        # create
        r = client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Router T1", "tier": "pro",
        })
        assert r.status_code == 200
        assert r.json()["tenant_id"] == tid
        # get
        r = client.get(f"/api/v1/business/tenant/{tid}")
        assert r.status_code == 200
        # list
        r = client.get("/api/v1/business/tenant")
        assert r.status_code == 200
        assert any(t["tenant_id"] == tid for t in r.json()["tenants"])
        # delete
        r = client.delete(f"/api/v1/business/tenant/{tid}")
        assert r.status_code == 200
        # get again -> 404
        r = client.get(f"/api/v1/business/tenant/{tid}")
        assert r.status_code == 404

    def test_tenant_create_invalid_422(self, client):
        """E2: 非法 tenant_id 字符 → 422 (Pydantic)."""
        r = client.post("/api/v1/business/tenant", json={
            "tenant_id": "bad name!", "name": "Bad",
        })
        assert r.status_code == 422

    def test_billing_record_then_invoice(self, client):
        """E3: record 用量 + 生成发票."""
        tid = "router_billing_1"
        client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Billing", "tier": "pro",
        })
        # record
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 50000, "unit": "call",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["quota"]["level"] == "ok"  # 没设配额 → ok
        # query
        r = client.get(f"/api/v1/business/billing/usage/{tid}")
        assert r.status_code == 200
        assert r.json()["count"] == 1
        # invoice
        r = client.post("/api/v1/business/billing/invoice", json={
            "tenant_id": tid, "period": utc_now_period(), "tier": "pro",
        })
        assert r.status_code == 200
        inv = r.json()
        assert inv["tier"] == "pro"
        assert inv["subtotal_cents"] == 2900  # 只有 base fee (api_calls 在 included)

    def test_billing_quota_three_levels(self, client):
        """E4: 三档配额 — audit/soft/hard."""
        tid = "router_quota_1"
        client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Q", "tier": "pro",
        })
        client.put(f"/api/v1/business/tenant/{tid}/quotas", json={
            "quotas": {"api_calls": {"hard": 100, "soft": 80, "audit": 50, "unit": "call"}},
        })
        # cum 60 -> audit_warn
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 60,
        })
        assert r.json()["quota"]["level"] == "audit_warn"
        # cum 95 -> soft_warn
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 35,
        })
        assert r.json()["quota"]["level"] == "soft_warn"
        # cum 105 -> hard_block
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 10,
        })
        assert r.json()["quota"]["level"] == "hard_block"
        assert r.json()["quota"]["allowed"] is False

    def test_billing_unknown_tenant_404(self, client):
        """E5: 不存在的 tenant_id 记录用量 → 404."""
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": "ghost_tenant_xyz", "metric": "api_calls", "qty": 1,
        })
        assert r.status_code == 404

    def test_export_json(self, client):
        """E6: JSON 导出接口."""
        r = client.post("/api/v1/business/export/data", json={
            "fmt": "json",
            "records": [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}],
            "meta": {"src": "test"},
        })
        assert r.status_code == 200
        body = r.json()
        assert body["fmt"] == "json"
        assert body["count"] == 2
        # sha256 校验
        import base64
        blob = base64.b64decode(body["b64"])
        assert hashlib.sha256(blob).hexdigest() == body["sha256"]
        envelope = json.loads(blob.decode("utf-8"))
        assert envelope["schema_version"] == SCHEMA_VERSION
        assert len(envelope["records"]) == 2

    def test_export_csv(self, client):
        """E7: CSV 导出接口."""
        r = client.post("/api/v1/business/export/data", json={
            "fmt": "csv",
            "records": [{"id": 1, "name": "alice"}],
            "columns": ["id", "name"],
        })
        assert r.status_code == 200
        body = r.json()
        assert body["fmt"] == "csv"
        assert body["size_bytes"] > 0
        # preview 包含 header
        assert "id,name" in body["preview"]

    def test_export_formats_listing(self, client):
        """E8: 列出支持的导出格式."""
        r = client.get("/api/v1/business/export/formats")
        assert r.status_code == 200
        body = r.json()
        assert "json" in body["formats"]
        assert "csv" in body["formats"]

    def test_audit_append_verify_query(self, client):
        """E9: audit append + verify + query."""
        # append 3 条
        for i in range(3):
            r = client.post("/api/v1/business/audit/append", json={
                "actor": "tester", "action": "test.action",
                "target": f"t_{i}", "payload": {"i": i},
            })
            assert r.status_code == 200
        # verify
        r = client.get("/api/v1/business/audit/verify")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # query (filter actor=tester)
        r = client.get("/api/v1/business/audit/entries",
                       params={"actor": "tester", "limit": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 3
        # 验证 seq 单调递增
        seqs = [e["seq"] for e in body["entries"]]
        assert seqs == sorted(seqs)

    def test_tenant_disable_blocks_usage(self, client):
        """E10: 禁用租户记录用量 → 403."""
        tid = "router_disabled_1"
        client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Disabled", "tier": "free",
        })
        client.post(f"/api/v1/business/tenant/{tid}/disable")
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 1,
        })
        assert r.status_code == 403
        # 重新启用
        client.post(f"/api/v1/business/tenant/{tid}/enable")
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 1,
        })
        assert r.status_code == 200

    def test_billing_invalid_period_422(self, client):
        """E11: 非法 period 格式 → 422."""
        tid = "router_inv_1"
        client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Inv", "tier": "pro",
        })
        r = client.post("/api/v1/business/billing/invoice", json={
            "tenant_id": tid, "period": "2026/05", "tier": "pro",
        })
        assert r.status_code == 422

    def test_quota_check_endpoint(self, client):
        """E12: 显式 quota/check 端点."""
        tid = "router_check_1"
        client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Check", "tier": "free",
        })
        client.put(f"/api/v1/business/tenant/{tid}/quotas", json={
            "quotas": {"api_calls": {"hard": 100, "soft": 80, "audit": 50}},
        })
        r = client.post(f"/api/v1/business/tenant/{tid}/quota/check", json={
            "tenant_id": tid, "metric": "api_calls", "current": 85,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is True
        assert body["level"] == "soft_warn"


# ============================================================================
# F. Integration — 4 routers 协同
# ============================================================================

class TestIntegration:
    """4 routers 协同 — tenant → billing → invoice → audit → export."""

    def test_full_commercial_flow(self, client):
        """F1: 完整商用闭环."""
        import uuid
        tid = f"integ_{uuid.uuid4().hex[:8]}"
        # 1. 创建租户 + 设配额
        r = client.post("/api/v1/business/tenant", json={
            "tenant_id": tid, "name": "Integration", "tier": "pro",
        })
        assert r.status_code == 200
        r = client.put(f"/api/v1/business/tenant/{tid}/quotas", json={
            "quotas": {"api_calls": {"hard": 200000, "soft": 150000, "audit": 100000}},
        })
        assert r.status_code == 200
        # 2. 记录用量
        r = client.post("/api/v1/business/billing/usage", json={
            "tenant_id": tid, "metric": "api_calls", "qty": 120000,
        })
        assert r.status_code == 200
        assert r.json()["quota"]["level"] == "audit_warn"
        # 3. 生成发票
        r = client.post("/api/v1/business/billing/invoice", json={
            "tenant_id": tid, "period": utc_now_period(), "tier": "pro",
        })
        assert r.status_code == 200
        inv = r.json()
        # Pro base 2900 + overage 20000 (ceil 20 * 5 cents) = 3000
        assert inv["subtotal_cents"] == 2900 + 100  # 20k overage = 20 units * 5 cents
        # 4. 导出发票 JSON
        r = client.post("/api/v1/business/export/data", json={
            "fmt": "json",
            "records": [inv],
            "meta": {"invoice_id": inv["invoice_id"]},
        })
        assert r.status_code == 200
        # 5. 验证审计链
        r = client.get("/api/v1/business/audit/verify")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # 6. 审计 entries 包含 tenant.create / quota.set / usage.record / invoice.create
        r = client.get("/api/v1/business/audit/entries",
                       params={"limit": 100})
        actions = [e["action"] for e in r.json()["entries"]]
        assert "tenant.create" in actions
        assert "billing.usage.record" in actions
        assert "billing.invoice.create" in actions

    def test_multi_tenant_isolation_via_api(self, client):
        """F2: 多租户通过 API 隔离."""
        import uuid
        tid_a = f"a_{uuid.uuid4().hex[:6]}"
        tid_b = f"b_{uuid.uuid4().hex[:6]}"
        # 创建
        for tid, name in [(tid_a, "TenantA"), (tid_b, "TenantB")]:
            r = client.post("/api/v1/business/tenant", json={
                "tenant_id": tid, "name": name, "tier": "free",
            })
            assert r.status_code == 200
        # 各自记录
        for tid, qty in [(tid_a, 100), (tid_b, 500)]:
            r = client.post("/api/v1/business/billing/usage", json={
                "tenant_id": tid, "metric": "api_calls", "qty": qty,
            })
            assert r.status_code == 200
        # 查询 — 各自只看到自己的
        r_a = client.get(f"/api/v1/business/billing/usage/{tid_a}")
        r_b = client.get(f"/api/v1/business/billing/usage/{tid_b}")
        assert r_a.json()["count"] == 1
        assert r_b.json()["count"] == 1
        # A 看到 100, B 看到 500
        assert r_a.json()["events"][0]["qty"] == "100"
        assert r_b.json()["events"][0]["qty"] == "500"