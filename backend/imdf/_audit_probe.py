"""Adversarial probe: verify P10-B claims end-to-end.

Tests:
1. multimodal routes are mounted in canvas_web (TestClient can hit /api/v1/multimodal/*)
2. /api/chat endpoint exists and uses call_provider_smart
3. embedding.py: get_embedding returns 1024-dim vectors
4. rag.py uses get_embedding (not old embedder.embed)
5. model_gateway: chat_with_observability integrates cost/usage/audit
"""
import os
import sys
import tempfile

# Set offline mode like conftest does
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

sys.path.insert(0, ".")

# Force the multimodal module to mark _REAL_PROBED = True
import multimodal.types as _t
if hasattr(_t, "_REAL_PROBED"):
    _t._REAL_PROBED = True

from fastapi.testclient import TestClient

results = []

# Probe 1: TestClient to canvas_web, hit multimodal endpoints
print("=" * 60)
print("PROBE 1: multimodal routes mounted in canvas_web (real TestClient)")
print("=" * 60)
try:
    from api.canvas_web import app
    client = TestClient(app)

    # Try the healthz endpoint
    r = client.get("/api/v1/multimodal/healthz")
    print(f"  GET /api/v1/multimodal/healthz -> {r.status_code}: {r.text[:200]}")
    results.append(("multimodal_healthz", r.status_code != 404))

    # Try providers endpoint
    r2 = client.get("/api/v1/multimodal/providers")
    print(f"  GET /api/v1/multimodal/providers -> {r2.status_code}: {r2.text[:200]}")
    results.append(("multimodal_providers", r2.status_code != 404))
except Exception as e:
    print(f"  ERROR: {e}")
    results.append(("multimodal_healthz", False))
    results.append(("multimodal_providers", False))

# Probe 2: TestClient to /api/chat
print()
print("=" * 60)
print("PROBE 2: /api/chat endpoint works")
print("=" * 60)
try:
    from api.canvas_web import app
    client = TestClient(app)
    r = client.post("/api/chat", json={"user_input": "hello"})
    print(f"  POST /api/chat -> {r.status_code}: {r.text[:300]}")
    # Check response shape
    data = r.json()
    has_shape = isinstance(data, dict) and "success" in data
    print(f"  Response has 'success' key: {has_shape}")
    results.append(("chat_endpoint", has_shape))
except Exception as e:
    print(f"  ERROR: {e}")
    results.append(("chat_endpoint", False))

# Probe 3: get_embedding returns 1024-dim
print()
print("=" * 60)
print("PROBE 3: get_embedding returns 1024-dim vectors")
print("=" * 60)
try:
    from multimodal.embedding import get_embedding, get_global_embedder, UNIFIED_DIM
    print(f"  UNIFIED_DIM = {UNIFIED_DIM}")
    results.append(("unified_dim_1024", UNIFIED_DIM == 1024))

    from multimodal.types import MediaRef, ModalKind
    ref = MediaRef(kind=ModalKind.TEXT, text="hello world")
    vec = get_embedding(ref)
    print(f"  get_embedding(text) -> dim={len(vec)}")
    results.append(("text_1024_dim", len(vec) == 1024))
except Exception as e:
    print(f"  ERROR: {e}")
    results.append(("unified_dim_1024", False))
    results.append(("text_1024_dim", False))

# Probe 4: rag.py uses get_embedding (not old embedder.embed)
print()
print("=" * 60)
print("PROBE 4: rag.py uses get_embedding shim")
print("=" * 60)
try:
    import multimodal.rag as rag_mod
    src = open(rag_mod.__file__, encoding="utf-8").read()
    uses_get_embedding = "get_embedding" in src
    uses_old_embedder = "self.embedder.embed" in src or "embedder.embed(ref)" in src
    print(f"  rag.py uses 'get_embedding': {uses_get_embedding}")
    print(f"  rag.py uses old 'self.embedder.embed': {uses_old_embedder}")
    results.append(("rag_uses_get_embedding", uses_get_embedding))
    results.append(("rag_drops_old_embed", not uses_old_embedder))
except Exception as e:
    print(f"  ERROR: {e}")
    results.append(("rag_uses_get_embedding", False))

# Probe 5: model_gateway.chat_with_observability integrates cost + audit
print()
print("=" * 60)
print("PROBE 5: model_gateway cost/usage/audit integration")
print("=" * 60)
try:
    from engines import model_gateway as mg
    has_cost = hasattr(mg, "compute_cost_usd")
    has_infer = hasattr(mg, "_infer_provider")
    has_record = hasattr(mg, "_record_call_observability")
    has_usage = hasattr(mg, "_usage_dict_compat")
    has_table = hasattr(mg, "_DEFAULT_MODEL_COST_TABLE")
    # 5 providers?
    providers = list(mg._DEFAULT_MODEL_COST_TABLE.keys()) if has_table else []
    print(f"  compute_cost_usd: {has_cost}")
    print(f"  _infer_provider: {has_infer}")
    print(f"  _record_call_observability: {has_record}")
    print(f"  _usage_dict_compat: {has_usage}")
    print(f"  _DEFAULT_MODEL_COST_TABLE providers: {providers}")
    results.append(("model_gateway_5_providers", len(providers) >= 5))
    results.append(("model_gateway_all_funcs", has_cost and has_infer and has_record and has_usage))

    # Compute cost for real
    cost = mg.compute_cost_usd(
        model="gpt-4o",
        tokens={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
        provider="openai",
    )
    print(f"  compute_cost_usd(gpt-4o, 1000/500, openai) = {cost} USD")
    expected = (1000 / 1000.0) * 0.005 + (500 / 1000.0) * 0.015  # 0.005 + 0.0075
    print(f"  expected = {expected} USD")
    results.append(("cost_calc_correct", abs(cost - expected) < 1e-6))
except Exception as e:
    print(f"  ERROR: {e}")
    results.append(("model_gateway_5_providers", False))

# Summary
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
for name, passed in results:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
all_pass = all(p for _, p in results)
print()
print(f"OVERALL: {'PASS' if all_pass else 'FAIL'} ({sum(1 for _, p in results if p)}/{len(results)})")
sys.exit(0 if all_pass else 1)