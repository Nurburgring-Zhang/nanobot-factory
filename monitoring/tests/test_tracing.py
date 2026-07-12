"""Tests for monitoring.tracing — distributed tracing primitives.

Covers:
1. Span model — attribute/event/status/duration methods
2. InMemorySpanExporter — thread-safe span collection
3. TracingManager.setup — service-name labelling, idempotency
4. emit_n_spans — 100-req → 100-spans guarantee (the F2 verifier)
5. trace_function / trace_sync / trace_async — context managers + decorators
6. tracing OTLP emission — best-effort, no network required
7. Auto-instrumentation — graceful degradation when libs missing
8. 100-req Jaeger emission contract: every emitted span carries a name +
   trace_id + start/end times + duration.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid

import pytest

from monitoring import tracing
from monitoring.tracing import (
    InMemorySpanExporter,
    Span,
    TracingManager,
    emit_n_spans,
    emit_to_jaeger,
    get_environment_status,
    get_tracing_manager,
    reset_tracing,
    trace_async,
    trace_function,
    trace_sync,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _clean_tracing():
    """Reset the singleton + exporter between tests."""
    reset_tracing()
    yield
    reset_tracing()


# --------------------------------------------------------------------------- #
# 1. Span model
# --------------------------------------------------------------------------- #
def test_span_set_attribute_and_event():
    span = Span(
        name="x", trace_id="t1", span_id="s1", start_time=time.time()
    )
    span.set_attribute("user_id", "u-1")
    span.add_event("checkpoint", phase="start")
    assert span.attributes["user_id"] == "u-1"
    assert span.events[0]["name"] == "checkpoint"
    assert span.events[0]["phase"] == "start"


def test_span_set_status_with_message():
    span = Span(name="x", trace_id="t1", span_id="s1", start_time=time.time())
    span.set_status("error", message="boom")
    assert span.status == "error"
    assert span.attributes["status_message"] == "boom"


def test_span_duration_ms_calculates_end_minus_start():
    span = Span(name="x", trace_id="t1", span_id="s1", start_time=100.0)
    span.end(end_time=100.5)
    assert span.duration_ms() == pytest.approx(500.0)


def test_span_duration_none_while_unfinished():
    span = Span(name="x", trace_id="t1", span_id="s1", start_time=time.time())
    assert span.duration_ms() is None
    span.end()
    assert span.duration_ms() is not None


def test_span_to_dict_is_serializable():
    span = Span(name="x", trace_id="t1", span_id="s1", start_time=100.0)
    span.set_attribute("n", 1)
    span.end(end_time=200.0)
    d = span.to_dict()
    assert d["name"] == "x"
    assert d["trace_id"] == "t1"
    assert d["attributes"]["n"] == 1
    assert d["duration_ms"] == pytest.approx(100_000.0)


# --------------------------------------------------------------------------- #
# 2. InMemorySpanExporter
# --------------------------------------------------------------------------- #
def test_exporter_collects_spans():
    exporter = InMemorySpanExporter()
    span = Span(name="x", trace_id="t1", span_id="s1", start_time=time.time())
    n = exporter.export([span])
    assert n == 1
    assert exporter.count() == 1
    assert exporter.get_finished_spans()[0].name == "x"


def test_exporter_filters_by_name_and_service():
    exporter = InMemorySpanExporter()
    s1 = Span(name="alpha", trace_id="t1", span_id="s1", service="api", start_time=time.time())
    s2 = Span(name="beta", trace_id="t1", span_id="s2", service="db", start_time=time.time())
    exporter.export([s1, s2])
    assert len(exporter.get_finished_spans(name="alpha")) == 1
    assert len(exporter.get_finished_spans(service="db")) == 1
    assert len(exporter.get_finished_spans(service="api", name="alpha")) == 1


def test_exporter_thread_safe_concurrent_export():
    exporter = InMemorySpanExporter()
    def writer(n: int):
        spans = [
            Span(name=f"s{i}", trace_id="t", span_id=f"id{i}", start_time=time.time())
            for i in range(n)
        ]
        exporter.export(spans)
    threads = [threading.Thread(target=writer, args=(20,)) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert exporter.count() == 200


def test_exporter_clear_removes_spans():
    exporter = InMemorySpanExporter()
    span = Span(name="x", trace_id="t1", span_id="s1", start_time=time.time())
    exporter.export([span])
    assert exporter.count() == 1
    exporter.clear()
    assert exporter.count() == 0


def test_exporter_enforces_max_size():
    exporter = InMemorySpanExporter(max_size=10)
    spans = [
        Span(name=f"s{i}", trace_id="t", span_id=f"id{i}", start_time=time.time())
        for i in range(50)
    ]
    exporter.export(spans)
    # After hitting max_size we drop oldest half; total is bounded.
    assert exporter.count() <= 10


# --------------------------------------------------------------------------- #
# 3. TracingManager setup
# --------------------------------------------------------------------------- #
def test_manager_setup_is_idempotent():
    mgr = get_tracing_manager()
    mgr.setup("svc-a")
    mgr.setup("svc-a")  # same name → no-op
    captured = [s for s in mgr.exporter.all()]
    assert len(captured) == 0
    assert mgr._service_name == "svc-a"


def test_manager_setup_with_different_name_resets():
    mgr = get_tracing_manager()
    mgr.setup("svc-a")
    with trace_function("op1"):
        pass
    # Now re-setup with different name
    mgr.setup("svc-b")
    # New spans should still be captured
    with trace_function("op2"):
        pass
    spans = mgr.exporter.all()
    assert any(s.name == "op2" for s in spans)


def test_manager_starts_and_ends_span():
    mgr = get_tracing_manager()
    mgr.setup("svc-test")
    span = mgr.start_span("op")
    mgr.end_span(span, status="ok")
    captured = mgr.exporter.all()
    assert len(captured) == 1
    assert captured[0].name == "op"
    assert captured[0].service == "svc-test"


def test_manager_nested_spans_share_trace_id():
    mgr = get_tracing_manager()
    mgr.setup("svc-test")
    with trace_function("parent") as parent_span:
        with trace_function("child") as child_span:
            pass
    spans = mgr.exporter.all()
    assert len(spans) == 2
    # Both spans must share trace_id (parent context propagation)
    assert parent_span.trace_id == child_span.trace_id
    # child.parent_id == parent.span_id
    assert child_span.parent_id == parent_span.span_id


def test_manager_increments_span_and_trace_counters():
    mgr = get_tracing_manager()
    mgr.setup("svc-test")
    assert mgr.span_count == 0
    assert mgr.trace_count == 0
    with trace_function("op1"):
        pass
    with trace_function("op2"):
        with trace_function("op2.inner"):
            pass
    assert mgr.span_count == 3
    # op1 + op2 are top-level → 2 traces
    assert mgr.trace_count == 2


def test_sibling_spans_share_root_trace_id_and_parent():
    """F2 fix-3: root span + two siblings must share trace_id and parent_id.

    Reproduces the F2 hidden bug where ``end_span`` always reset the active
    span to None, so the second sibling lost its parent context and got a
    brand new trace_id.
    """
    mgr = get_tracing_manager()
    mgr.setup("svc-siblings")
    with trace_function("root") as root:
        with trace_function("child1") as child1:
            pass
        with trace_function("child2") as child2:
            pass
    # All three share the same trace_id (siblings inherit from root).
    assert root.trace_id == child1.trace_id == child2.trace_id
    # Each child points back to the root, not to a sibling or None.
    assert child1.parent_id == root.span_id
    assert child2.parent_id == root.span_id
    # Root has no parent.
    assert root.parent_id is None
    # exporter captured all three
    finished = mgr.exporter.get_finished_spans()
    assert len(finished) == 3
    assert mgr.span_count == 3
    assert mgr.trace_count == 1  # all siblings belong to one trace


def test_sequential_root_spans_each_get_new_trace():
    """Sanity check: two top-level spans in sequence are independent traces."""
    mgr = get_tracing_manager()
    mgr.setup("svc-seq")
    with trace_function("a") as a:
        pass
    with trace_function("b") as b:
        pass
    assert a.trace_id != b.trace_id
    assert a.parent_id is None
    assert b.parent_id is None
    assert mgr.trace_count == 2


# --------------------------------------------------------------------------- #
# 4. emit_n_spans — 100-req → 100-spans contract
# --------------------------------------------------------------------------- #
def test_emit_n_spans_emits_exactly_n_spans():
    mgr = get_tracing_manager()
    mgr.setup("svc-100")
    spans = emit_n_spans(100, prefix="req")
    assert len(spans) == 100
    assert mgr.span_count == 100
    assert mgr.trace_count == 100
    exporter_spans = mgr.exporter.all()
    assert len(exporter_spans) == 100


def test_emit_n_spans_each_carries_required_fields():
    mgr = get_tracing_manager()
    mgr.setup("svc-fields")
    spans = emit_n_spans(10, prefix="x")
    for i, span in enumerate(spans):
        assert span.name == f"x.{i}"
        assert len(span.trace_id) == 32  # uuid4 hex
        assert len(span.span_id) == 16   # first 16 hex chars of uuid4
        assert span.start_time > 0.0
        assert span.end_time is not None
        assert span.duration_ms() is not None
        assert span.status == "ok"
        assert span.service == "svc-fields"
        assert span.attributes["iteration"] == i


def test_emit_n_spans_unique_trace_ids_per_call():
    """Each top-level emit creates its own trace (req.N independence)."""
    spans = emit_n_spans(10, prefix="x")
    trace_ids = {s.trace_id for s in spans}
    assert len(trace_ids) == 10


# --------------------------------------------------------------------------- #
# 5. Context managers + decorators
# --------------------------------------------------------------------------- #
def test_trace_function_records_span_on_success():
    mgr = get_tracing_manager()
    mgr.setup("svc-cm")
    with trace_function("do_work"):
        pass
    spans = mgr.exporter.all()
    assert len(spans) == 1
    assert spans[0].status == "ok"


def test_trace_function_records_error_status_on_exception():
    mgr = get_tracing_manager()
    mgr.setup("svc-cm-error")
    with pytest.raises(ValueError):
        with trace_function("do_work_failing"):
            raise ValueError("intentional")
    spans = mgr.exporter.all()
    assert len(spans) == 1
    assert spans[0].status == "error"
    assert "ValueError" in spans[0].attributes["status_message"]


def test_trace_sync_decorator_wraps_function():
    mgr = get_tracing_manager()
    mgr.setup("svc-sync")
    @trace_sync("my_op")
    def add(a: int, b: int) -> int:
        return a + b
    result = add(2, 3)
    assert result == 5
    spans = mgr.exporter.all()
    assert len(spans) == 1
    assert spans[0].name == "my_op"
    assert spans[0].status == "ok"


def test_trace_sync_decorator_default_name():
    mgr = get_tracing_manager()
    mgr.setup("svc-sync-default")
    @trace_sync()
    def my_func() -> int:
        return 42
    my_func()
    spans = mgr.exporter.all()
    assert len(spans) == 1
    assert spans[0].name.endswith("my_func")


def test_trace_async_decorator_wraps_async_function():
    mgr = get_tracing_manager()
    mgr.setup("svc-async")
    @trace_async("async_op")
    async def fetch() -> str:
        return "ok"
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(fetch())
    finally:
        loop.close()
    assert result == "ok"
    spans = mgr.exporter.all()
    assert len(spans) == 1
    assert spans[0].name == "async_op"
    assert spans[0].status == "ok"


# --------------------------------------------------------------------------- #
# 6. Jaeger / OTLP emission
# --------------------------------------------------------------------------- #
def test_emit_to_jaeger_returns_zero_when_no_endpoint():
    """Without OTEL_EXPORTER_OTLP_ENDPOINT we should bail out cleanly."""
    import os
    prev = os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    try:
        n = emit_to_jaeger([Span(name="x", trace_id="t", span_id="s", start_time=time.time())])
        assert n == 0
    finally:
        if prev is not None:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = prev


def test_emit_to_jaeger_posts_to_endpoint_with_otlp_json():
    """F2 fix-4: real HTTP POST to ``{endpoint}/v1/traces`` with OTLP JSON.

    Spins up an in-process HTTP server, points the OTLP endpoint env var at
    it, emits a small batch of spans, and asserts the server received a
    POST containing a parseable OTLP envelope that includes our spans.
    """
    import json
    import os
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    captured: dict = {"bodies": [], "headers": []}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            captured["bodies"].append(body)
            captured["headers"].append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_a, **_kw):  # silence the test stderr
            pass

    # Find a free port via OS (avoids flakes on parallel runs)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{port}"
        spans = [
            Span(
                name=f"otlp.test.{i}",
                trace_id="0123456789abcdef0123456789abcdef",
                span_id=f"spanid{i:012d}",
                parent_id="rootspanid0" if i > 0 else None,
                start_time=time.time(),
                service="svc-otlp",
            )
            for i in range(3)
        ]
        for s in spans:
            s.end(end_time=s.start_time + 0.05)
        n = emit_to_jaeger(spans, endpoint=url)
        assert n == 3
        # Server received exactly one POST
        assert len(captured["bodies"]) == 1
        body = captured["bodies"][0]
        # Body is OTLP JSON
        payload = json.loads(body.decode("utf-8"))
        assert "resourceSpans" in payload
        resource_spans = payload["resourceSpans"]
        assert len(resource_spans) >= 1
        scope_spans = resource_spans[0]["scopeSpans"]
        otlp_spans = scope_spans[0]["spans"]
        assert len(otlp_spans) == 3
        names = {sp["name"] for sp in otlp_spans}
        assert names == {"otlp.test.0", "otlp.test.1", "otlp.test.2"}
        # Parent linkage preserved in OTLP envelope
        parents = {sp["spanId"]: sp.get("parentSpanId") for sp in otlp_spans}
        assert parents["spanid000000000001"] == "rootspanid0"
        assert parents["spanid000000000002"] == "rootspanid0"
        # Root span has no parentSpanId field at all (.get() returns None)
        assert parents["spanid000000000000"] is None
        assert "parentSpanId" not in next(
            sp for sp in otlp_spans if sp["spanId"] == "spanid000000000000"
        )
        # Content-Type advertised as JSON
        assert "application/json" in captured["headers"][0].get("Content-Type", "")
    finally:
        server.shutdown()
        server.server_close()


def test_emit_to_jaeger_returns_zero_on_unreachable_endpoint():
    """Endpoint set but unreachable → no exception, returns 0."""
    import os
    prev = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    try:
        # Reserved-for-documentation IP that nobody listens on. The TCP
        # connection itself times out, exercising the network-failure path.
        n = emit_to_jaeger(
            [Span(name="x", trace_id="t", span_id="s", start_time=time.time())],
            endpoint="http://127.0.0.1:1",
        )
        assert n == 0
    finally:
        if prev is not None:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = prev
        else:
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)


def test_otlp_json_envelope_shape_is_valid():
    """Smoke-check the OTLP converter without involving the network."""
    from monitoring.tracing import _spans_to_otlp_json, _span_to_otlp_dict, _attrs_to_otlp

    span = Span(
        name="conv", trace_id="aa" * 16, span_id="bb" * 8,
        parent_id="cc" * 8, start_time=100.0, service="svc",
    )
    span.set_attribute("user_id", "u-1")
    span.set_attribute("count", 7)
    span.set_attribute("ok", True)
    span.set_status("ok")
    span.end(end_time=100.5)
    d = _span_to_otlp_dict(span)
    assert d["name"] == "conv"
    assert d["traceId"] == "aa" * 16
    assert d["spanId"] == "bb" * 8
    assert d["parentSpanId"] == "cc" * 8
    assert d["startTimeUnixNano"] == "100000000000"
    assert d["endTimeUnixNano"] == "100500000000"
    assert d["status"]["code"] == 1  # ok

    payload = _spans_to_otlp_json([span])
    assert "resourceSpans" in payload
    assert payload["resourceSpans"][0]["resource"]["attributes"][0]["key"] == "service.name"

    attrs = _attrs_to_otlp({"a": 1, "b": "x", "c": True})
    kinds = {a["key"]: list(a["value"].keys())[0] for a in attrs}
    assert kinds == {"a": "intValue", "b": "stringValue", "c": "boolValue"}


# --------------------------------------------------------------------------- #
# 7. Auto-instrumentation — graceful degradation
# --------------------------------------------------------------------------- #
def test_auto_instrument_returns_results_dict_even_when_libs_missing():
    mgr = get_tracing_manager()
    mgr.setup("svc-auto")
    # Pass mock objects; the OTel libs likely aren't present, so we expect
    # all four to come back as False (graceful degradation).
    class _Dummy: pass
    dummy = _Dummy()
    results = mgr.auto_instrument(
        fastapi_app=dummy,
        sqlalchemy_engine=dummy,
        redis_client=dummy,
        httpx_client=dummy,
    )
    assert "fastapi" in results
    assert "sqlalchemy" in results
    assert "redis" in results
    assert "httpx" in results
    for v in results.values():
        assert isinstance(v, bool)


# --------------------------------------------------------------------------- #
# 8. Environment status
# --------------------------------------------------------------------------- #
def test_environment_status_reflects_setup():
    mgr = get_tracing_manager()
    mgr.setup("svc-status")
    with trace_function("op"):
        pass
    status = get_environment_status()
    assert status["service_name"] == "svc-status"
    assert status["span_count"] == 1
    assert status["trace_count"] == 1
    assert "otel_api_available" in status
    assert "otel_sdk_available" in status


# --------------------------------------------------------------------------- #
# 9. Reset / singleton
# --------------------------------------------------------------------------- #
def test_reset_tracing_clears_singleton_and_spans():
    mgr = get_tracing_manager()
    mgr.setup("svc-reset")
    with trace_function("op"):
        pass
    assert mgr.exporter.count() == 1
    reset_tracing()
    # New singleton should have empty exporter
    new_mgr = get_tracing_manager()
    assert new_mgr is not mgr
    assert new_mgr.exporter.count() == 0


def test_singleton_returns_same_instance():
    a = get_tracing_manager()
    b = get_tracing_manager()
    assert a is b
