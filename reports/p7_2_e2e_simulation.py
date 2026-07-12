"""P7-2 End-to-End simulation: 1 full payment → partial refund → invoice → red-letter + SLA breach

Tests the complete commercial-grade flow on top of P6-Fix-C fixes.
"""
import json
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"D:/Hermes/生产平台/nanobot-factory/backend")

import os
os.environ["BILLING_IDEMPOTENCY_BACKEND"] = "fake"
os.environ["BILLING_DEDUP_BACKEND"] = "fake"

results = {"steps": [], "summary": {}}


def log(step: str, ok: bool, detail: str = ""):
    icon = "✅" if ok else "❌"
    line = f"{icon} {step}"
    if detail:
        line += f" — {detail}"
    print(line)
    results["steps"].append({"step": step, "ok": bool(ok), "detail": detail})


print("=" * 70)
print("P7-2 SIMULATION: 完整支付 + 部分退款 + 发票红冲 + SLA breach")
print("=" * 70)

# ===== Step 1: 创建订单 =====
print("\n[1] Create order (P6-Fix-C-3 atomic 事务基础)")
from billing.orders import OrderService, InMemoryOrderStore, OrderStatus
order_store = InMemoryOrderStore()
order_svc = OrderService(order_store)
order = order_svc.create_order(
    user_id="u_test_p7_2",
    plan_id="pro",
    amount_cents=10000,  # $100.00
    currency="USD",
    payment_method="stripe",
)
log("create_order", order.status == OrderStatus.PENDING, f"order_id={order.order_id} amount=$100")

# ===== Step 2: 支付 (mock provider) =====
print("\n[2] Pay via mock provider + webhook (F-6.1 live mode 路径已联通)")
from billing.payments import factory
prov = factory.get_provider("stripe")
pay_result = prov.create_payment(order)
from billing.payments.base import PaymentStatus
log("provider create_payment", pay_result.status in (PaymentStatus.SUCCESS, PaymentStatus.PENDING), f"payment_id={pay_result.payment_id} status={pay_result.status}")

# Idempotency (F-6.3 配套 F-6.9)
from billing.payments import idempotency, webhook_dedup
idem_store = idempotency.get_store()
key = f"idem:create_payment:{order.order_id}"
idem_store.release(key)  # clean slate
hit, reserved = idem_store.lookup_or_reserve(key, request_hash="hash1")
idem_store.commit(key, "hash1", {"payment_id": pay_result.payment_id})
hit2, reserved2 = idem_store.lookup_or_reserve(key, request_hash="hash1")
log("idempotency 24h TTL", hit2 is not None, f"replay hit={hit2 is not None} reserved={reserved2}")

# Webhook dedup (F-6.3 Redis SETNX 24h)
dedup_store = webhook_dedup.get_store()
evt_id = f"evt_test_{order.order_id}"
dedup_store.release(evt_id, "stripe")  # clean slate
d1 = dedup_store.register(evt_id, "stripe")
d2 = dedup_store.register(evt_id, "stripe")
log("webhook dedup 24h TTL", d2.is_duplicate, f"2nd register is_duplicate={d2.is_duplicate}")

# Mark paid
order_svc.mark_paid(order.order_id, external_ref=pay_result.payment_id)
order_refreshed = order_svc.get(order.order_id)
log("order mark_paid", order_refreshed.status == OrderStatus.FULFILLED, f"status={order_refreshed.status.value} (paid→fulfilled)")

# ===== Step 3-5: 部分退款累计 =====
print("\n[3-5] Cumulative partial refunds (F-6.2 累计追踪)")
order_svc.refund(order.order_id, reason="customer_partial_30", amount_cents=3000)
o1 = order_svc.get(order.order_id)
log("partial refund 1 ($30)", o1.refunded_amount_cents == 3000 and o1.status == OrderStatus.FULFILLED, f"refunded={o1.refunded_amount_cents} status={o1.status.value}")

order_svc.refund(order.order_id, reason="customer_partial_40", amount_cents=4000)
o2 = order_svc.get(order.order_id)
log("partial refund 2 ($40 cum)", o2.refunded_amount_cents == 7000, f"refunded={o2.refunded_amount_cents}")

order_svc.refund(order.order_id, reason="customer_final_30", amount_cents=3000)
o3 = order_svc.get(order.order_id)
log("final refund → REFUNDED", o3.status == OrderStatus.REFUNDED and o3.refunded_amount_cents == 10000, f"refunded={o3.refunded_amount_cents} status={o3.status.value}")

refunds_hist = o3.metadata.get("refunds", [])
log("refund history tracked", len(refunds_hist) == 3, f"history count={len(refunds_hist)}")

# 退款金额超限拦截
print("\n[6] Cumulative refund > order.amount guard (F-6.2 边界)")
from billing.payments.base import RefundValidationError, to_refund_cents
try:
    to_refund_cents(50.00, order_amount_cents=10000, already_refunded_cents=10000)
    log("over-refund guard", False, "should have raised")
except RefundValidationError as e:
    log("over-refund guard", True, f"correctly raised: {e}")

# ===== Step 7: 发票生成 =====
print("\n[7] Invoice generation (中国国标 + SM3 防篡改)")
from invoices import generate_invoice, _STORE
inv = generate_invoice(
    invoice_type="vat_special",
    order_id=order.order_id,
    buyer_name="Acme Corp",
    buyer_tax_id="TAX-12345",
    seller_name="ZhiYing Inc.",
    seller_tax_id="TAX-67890",
    items=[{"name": "Pro Plan Monthly", "qty": 1, "unit_price": 100.00, "amount": 100.00}],
    amount=100.00,
    tax_rate=0.06,
)
log("generate invoice", inv.invoice_no.startswith("INV-"), f"invoice_no={inv.invoice_no} amount={inv.amount} tax_dict={inv.tax}")

# ===== Step 8: 发票红冲 =====
print("\n[8] Invoice red-letter (F-6.5 负数发票 + 原票 voided)")
from invoices.redletter import redletter, is_redlettered
red_res = redletter(inv.invoice_no, reason="customer_request", refund_amount=100.00, operator="test_op_p7_2")
log("redletter original → voided", red_res.original.status == "voided", f"status={red_res.original.status} red_no={red_res.record.red_letter_invoice_no}")
log("redletter reverse → negative amount", red_res.red_letter.amount < 0, f"reverse.amount={red_res.red_letter.amount:.2f}")
log("is_redlettered recorded", is_redlettered(inv.invoice_no), f"is_redlettered={is_redlettered(inv.invoice_no)}")

try:
    redletter(inv.invoice_no, reason="double_test", refund_amount=100.00)
    log("double-redletter guard", False, "should have raised")
except ValueError as e:
    log("double-redletter guard", True, f"correctly raised: {e}")

# ===== Step 9: SLA breach =====
print("\n[9] SLA breach detection (F-6.6 Celery beat 30min)")
from tickets.sla_monitor import check_sla_breach, dispatch_alerts

# Build real Ticket objects (sla_monitor iterates .status / .priority / .sla_deadline)
# Use naive ISO format (no 'Z') to match datetime.utcnow() used in sla_monitor
fake_breached = {
    "t_breach_001": type("T", (), {
        "ticket_id": "t_breach_001",
        "priority": "P0",
        "status": "open",
        "created_at": datetime.utcnow().isoformat(),
        "sla_deadline": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
        "assignee": "oncall1",
        "subject": "DB down",
        "type": "incident",
    })(),
}
fake_at_risk = {
    "t_atrisk_001": type("T", (), {
        "ticket_id": "t_atrisk_001",
        "priority": "P0",
        "status": "open",
        "created_at": datetime.utcnow().isoformat(),
        "sla_deadline": (datetime.utcnow() + timedelta(minutes=20)).isoformat(),
        "assignee": "oncall2",
        "subject": "API latency spike",
        "type": "incident",
    })(),
}

report_breach = check_sla_breach(tickets=fake_breached)
log("SLA breach detected (P0 past)", len(report_breach.breached) >= 1, f"breached={len(report_breach.breached)} at_risk={len(report_breach.at_risk)}")

report_at_risk = check_sla_breach(tickets=fake_at_risk)
log("SLA at-risk detected (P0 20min ahead)", len(report_at_risk.at_risk) >= 1, f"at_risk={len(report_at_risk.at_risk)}")

counters = dispatch_alerts(report_breach)
total_breach_alerts = sum(v for k, v in counters.items() if k.endswith("_breach_alerts"))
log("SLA dispatch_alerts side-effect", total_breach_alerts >= 1, f"counters={counters} total={total_breach_alerts}")

# ===== Step 10: Cross-service =====
print("\n[10] Cross-service: Order paid → Refund → Invoice red-letter → SLA breach (P1-12)")
log("cross-service 4-layer integration",
    o3.status == OrderStatus.REFUNDED and is_redlettered(inv.invoice_no) and len(report_breach.breached) >= 1,
    "billing(refunded) + invoices(voided) + tickets(breach) all green")

# ===== Final =====
print("\n" + "=" * 70)
ok_count = sum(1 for s in results["steps"] if s["ok"])
total_count = len(results["steps"])
print(f"P7-2 SIMULATION RESULT: {ok_count}/{total_count} steps PASS")
print("=" * 70)
results["summary"] = {"total": total_count, "passed": ok_count, "failed": total_count - ok_count}

with open(r"D:/Hermes/生产平台/nanobot-factory/reports/p7_2_simulation.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nResults saved to: reports/p7_2_simulation.json")

sys.exit(0 if ok_count == total_count else 1)