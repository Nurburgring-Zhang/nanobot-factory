"""P17-A1 invoice template tests.

Coverage:
- 5 templates (standard / detailed / summary / electronic / custom)
- Each generates a valid PDF (starts with %PDF-)
- PDF size sanity check (non-empty)
- InvoiceContext creation from order dict
- list_templates metadata
- Custom renderer integration
- Sample PDFs written to disk for inspection
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing import invoice_templates as inv


# ── 1. Template metadata ───────────────────────────────────────────────────

class TestTemplateMetadata:
    def test_001_supported_templates(self):
        assert inv.INVOICE_TEMPLATES == ("standard", "detailed", "summary",
                                          "electronic", "custom")
        assert len(inv.INVOICE_TEMPLATES) == 5

    def test_002_list_templates(self):
        templates = inv.list_templates()
        assert len(templates) == 5
        ids = [t["id"] for t in templates]
        assert ids == ["standard", "detailed", "summary", "electronic", "custom"]
        for t in templates:
            assert t["name"]
            assert t["description"]


# ── 2. InvoiceContext ────────────────────────────────────────────────────

class TestInvoiceContext:
    def test_010_minimal_context(self):
        ctx = inv.InvoiceContext(
            order_id="ord_001",
            user_id="u_001",
            customer_name="Alice",
            customer_email="alice@example.com",
            plan_name="Pro",
            amount_cents=9900,
            currency="USD",
        )
        assert ctx.issued_at != ""  # auto-populated
        assert ctx.country == "CN"  # default

    def test_011_full_context(self):
        ctx = inv.InvoiceContext(
            order_id="ord_002",
            user_id="u_002",
            customer_name="Bob",
            customer_email="bob@example.com",
            plan_name="Business",
            amount_cents=29900,
            currency="CNY",
            country="CN",
            tax_rate=0.13,
            tax_amount=3887,
            total_amount=33787,
            payment_method="alipay",
            external_ref="202606010001",
        )
        assert ctx.total_amount == 33787
        assert ctx.external_ref == "202606010001"


# ── 3. PDF generation for each template ───────────────────────────────────

SAMPLE_CTX = inv.InvoiceContext(
    order_id="ord_test_001",
    user_id="u_test_001",
    customer_name="张三",
    customer_email="zhangsan@example.com",
    plan_name="Pro Plan 月度订阅",
    amount_cents=9900,
    currency="CNY",
    country="CN",
    tax_rate=0.13,
    tax_amount=1287,
    total_amount=11187,
    payment_method="alipay",
    external_ref="2026070100001",
    line_items=[
        {"description": "Pro Plan 月度订阅", "qty": 1, "unit_price_cents": 9900,
         "amount_cents": 9900, "category": "standard"},
    ],
)


def _is_valid_pdf(data: bytes) -> bool:
    """Sanity check: must start with %PDF- and end with %%EOF."""
    return data[:5] == b"%PDF-" and b"%%EOF" in data[-200:]


class TestRenderStandard:
    def test_020_standard_template(self):
        pdf = inv.render_invoice(SAMPLE_CTX, "standard")
        assert _is_valid_pdf(pdf)
        assert len(pdf) > 1000  # non-trivial size

    def test_021_standard_jpy(self):
        ctx = inv.InvoiceContext(
            order_id="ord_jpy", user_id="u_001",
            customer_name="Yuki", customer_email="yuki@example.com",
            plan_name="Pro", amount_cents=1500, currency="JPY",
        )
        pdf = inv.render_invoice(ctx, "standard")
        assert _is_valid_pdf(pdf)


class TestRenderDetailed:
    def test_030_detailed_template(self):
        pdf = inv.render_invoice(SAMPLE_CTX, "detailed")
        assert _is_valid_pdf(pdf)
        assert len(pdf) > 1000

    def test_031_detailed_no_tax(self):
        ctx = inv.InvoiceContext(
            order_id="ord_no_tax", user_id="u_001",
            customer_name="Alice", customer_email="a@a.com",
            plan_name="Free", amount_cents=0, currency="USD",
            tax_rate=0.0, tax_amount=0,
        )
        pdf = inv.render_invoice(ctx, "detailed")
        assert _is_valid_pdf(pdf)


class TestRenderSummary:
    def test_040_summary_template(self):
        pdf = inv.render_invoice(SAMPLE_CTX, "summary")
        assert _is_valid_pdf(pdf)
        assert len(pdf) > 800

    def test_041_summary_with_tax(self):
        ctx = inv.InvoiceContext(
            order_id="ord_sum", user_id="u_001",
            customer_name="Alice", customer_email="a@a.com",
            plan_name="Pro", amount_cents=9900, currency="USD",
            tax_rate=0.07, tax_amount=693, total_amount=10593,
        )
        pdf = inv.render_invoice(ctx, "summary")
        assert _is_valid_pdf(pdf)


class TestRenderElectronic:
    def test_050_electronic_template(self):
        pdf = inv.render_invoice(SAMPLE_CTX, "electronic")
        assert _is_valid_pdf(pdf)
        assert len(pdf) > 800


class TestRenderCustom:
    def test_060_custom_template(self):
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, Spacer
        def my_renderer(ctx, doc):
            styles = inv._styles()
            doc.title = f"Custom Invoice {ctx.order_id}"
            # Caller is responsible for building the doc's story
            # Note: render_invoice already creates doc and builds story;
            # custom_renderer needs to APPEND to existing story — but
            # for simplicity, we provide a simple custom flow here.
        # The custom template requires a custom_renderer; we use a
        # simple inline one.
        def renderer(ctx, doc):
            styles = inv._styles()
            p = Paragraph(f"<b>Custom Invoice</b>: {ctx.order_id}", styles["title"])
            # Append to the doc... but doc has no public 'story' here.
            # Use a different approach: bypass render_invoice for custom and
            # call SimpleDocTemplate directly.
            from reportlab.platypus import SimpleDocTemplate
            import io
            buf = io.BytesIO()
            d = SimpleDocTemplate(buf, pagesize=inv.A4)
            d.build([p])
            return buf.getvalue()
        # Actually, we test that custom_renderer is required first
        with pytest.raises(ValueError):
            inv.render_invoice(SAMPLE_CTX, "custom")
        # And that providing one works
        pdf = inv.render_invoice(SAMPLE_CTX, "custom", custom_renderer=renderer)
        assert _is_valid_pdf(pdf)


# ── 4. File output helper ─────────────────────────────────────────────────

class TestRenderFile:
    def test_070_render_to_file(self, tmp_path):
        out = tmp_path / "invoice.pdf"
        result = inv.render_invoice_file(SAMPLE_CTX, "standard", str(out))
        assert result == str(out)
        assert out.exists()
        data = out.read_bytes()
        assert _is_valid_pdf(data)


# ── 5. All 5 templates — sample generation ────────────────────────────────

class TestAllTemplatesGenerate:
    """Spec: 5 模板各 1 个 sample PDF 生成."""

    @pytest.fixture(scope="class")
    def output_dir(self, tmp_path_factory):
        d = tmp_path_factory.mktemp("invoices")
        return d

    def test_080_generate_all_five(self, output_dir):
        results = []
        for tmpl in inv.INVOICE_TEMPLATES:
            if tmpl == "custom":
                def renderer(ctx, doc):
                    from reportlab.platypus import Paragraph
                    styles = inv._styles()
                    p = Paragraph(f"Custom invoice {ctx.order_id}", styles["title"])
                    doc.build([p])  # builds own story
                pdf = inv.render_invoice(SAMPLE_CTX, "custom",
                                          custom_renderer=renderer)
            else:
                pdf = inv.render_invoice(SAMPLE_CTX, tmpl)
            out = output_dir / f"sample_{tmpl}.pdf"
            out.write_bytes(pdf)
            results.append((tmpl, out, len(pdf)))
        # Verify all 5
        assert len(results) == 5
        for tmpl, out, size in results:
            assert out.exists()
            assert size > 500
            data = out.read_bytes()
            assert _is_valid_pdf(data)


# ── 6. Validation errors ──────────────────────────────────────────────────

class TestValidation:
    def test_090_invalid_template(self):
        with pytest.raises(ValueError):
            inv.render_invoice(SAMPLE_CTX, "nonexistent")

    def test_091_custom_without_renderer(self):
        with pytest.raises(ValueError):
            inv.render_invoice(SAMPLE_CTX, "custom")


# ── 7. make_context_from_order helper ─────────────────────────────────────

class TestMakeContext:
    def test_100_basic(self):
        order = {
            "order_id": "ord_001",
            "user_id": "u_001",
            "amount_cents": 9900,
            "currency": "USD",
            "payment_method": "stripe",
            "external_ref": "ch_abc123",
        }
        ctx = inv.make_context_from_order(
            order, plan_name="Pro",
            customer_name="Alice", customer_email="a@a.com",
            country="US", tax_rate=0.07, tax_amount=693,
        )
        assert ctx.order_id == "ord_001"
        assert ctx.amount_cents == 9900
        assert ctx.tax_rate == 0.07
        assert ctx.total_amount == 9900 + 693