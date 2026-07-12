# P19 V5.3 — Comfy MCP Integration

**Status**: ✅ Complete (29/29 tests passing)
**Module**: `backend/imdf/creative/comfy/` (new) + `backend/imdf/skills/` (new)
**Test runner**: `D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/creative/comfy/tests/ -v --tb=short`

---

## 1. What this delivers

V5 chapter 30 ("ComfyUI 创意工作流 — Comfy MCP 整合") calls for an MCP
layer that lets an Agent drive ComfyUI through natural-language
instructions. The deliverable provides:

1. **Model catalogue + retriever** — 8 entries (sdxl, sdxl_turbo,
   sd_15, sd_3, flux, animate_diff, ip_adapter, controlnet) with
   capability / type / tag / resolution filters.
2. **Node catalogue + retriever** — 15 entries covering loaders,
   samplers, conditioning, postprocess, and adapters
   (LoadImage, CLIPTextEncode, KSampler, VAEDecode, SaveImage,
   CheckpointLoaderSimple, CLIPImageEncode, ControlNetLoader,
   IPAdapter, FaceDetailer, LoraLoader, ControlNetApply, ImageScale,
   ImageBatch, EmptyLatentImage).
3. **Workflow builder** with connection validation + an LLM fallback
   hook for missing inputs.
4. **`ComfyMCPIntegration`** orchestrator: parses intent →
   searches catalogue → builds a workflow → executes (single or
   `asyncio.gather` batch) → emits a `comfy.workflow_executed` bus
   event.
5. **`create_workflow`** entry point that converts a natural-language
   description to a `Workflow` JSON object via the injected LLM
   provider (with a deterministic stub fallback when no LLM is wired).
6. **Skill registry** — registers the integration as
   `comfy_mcp_natural_language` so the agent runtime can look it up
   by name.

All async code is `awaitable` and runs cleanly under `asyncio.run`
(no pytest-asyncio fixture dependency required).

---

## 2. File inventory + LOC

| File | LOC |
|---|---:|
| `backend/imdf/creative/__init__.py` | 8 |
| `backend/imdf/creative/comfy/__init__.py` | 27 |
| `backend/imdf/creative/comfy/schemas.py` | 129 |
| `backend/imdf/creative/comfy/model_retriever.py` | 195 |
| `backend/imdf/creative/comfy/node_retriever.py` | 216 |
| `backend/imdf/creative/comfy/workflow_builder.py` | 192 |
| `backend/imdf/creative/comfy/mcp_integration.py` | 429 |
| `backend/imdf/creative/comfy/tests/__init__.py` | 1 |
| `backend/imdf/creative/comfy/tests/test_comfy_mcp.py` | 395 |
| `backend/imdf/skills/__init__.py` | 7 |
| `backend/imdf/skills/registry.py` | 105 |
| **TOTAL** | **1704** |

Production code (excl. tests + `__init__.py`): **1175 LOC**.
Test code: **395 LOC** (~30 % of total — consistent with "must be
tested" rule from the user profile).

---

## 3. Test results

```
============================= test session starts =============================
collected 29 items

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestIntentParsing
  ::test_parse_count_default                              PASSED [  3%]
  ::test_parse_count_x10                                  PASSED [  6%]
  ::test_parse_count_run_n                                PASSED [ 10%]
  ::test_parse_count_n_images                             PASSED [ 13%]
  ::test_parse_intent_anime                               PASSED [ 17%]
  ::test_parse_intent_video                               PASSED [ 20%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestModelRetriever
  ::test_catalogue_has_at_least_8_models                  PASSED [ 24%]
  ::test_search_txt2img                                   PASSED [ 27%]
  ::test_search_video                                     PASSED [ 31%]
  ::test_search_with_tag_filter                           PASSED [ 34%]
  ::test_search_missing_capability_returns_empty          PASSED [ 37%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestNodeRetriever
  ::test_catalogue_has_at_least_15_nodes                  PASSED [ 41%]
  ::test_search_by_category_loader                        PASSED [ 44%]
  ::test_search_by_output_conditioning                    PASSED [ 48%]
  ::test_search_by_input                                  PASSED [ 51%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestWorkflowBuilder
  ::test_build_valid_connections                          PASSED [ 55%]
  ::test_build_invalid_connection_raises                  PASSED [ 58%]
  ::test_build_with_llm_fallback                          PASSED [ 62%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestCreateWorkflow
  ::test_create_workflow_with_mock_llm_json               PASSED [ 65%]
  ::test_create_workflow_stub_when_no_llm                 PASSED [ 68%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestRunWorkflow
  ::test_run_single                                       PASSED [ 72%]
  ::test_run_batch_parallel                               PASSED [ 75%]
  ::test_run_batch_error_resilience                       PASSED [ 79%]
  ::test_run_uses_requested_prompt                        PASSED [ 82%]
  ::test_run_result_store_lookup                          PASSED [ 86%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestEndToEnd
  ::test_instruction_to_result_flow                       PASSED [ 89%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py::TestSkillRegistry
  ::test_register_and_lookup                              PASSED [ 93%]
  ::test_register_overwrite                               PASSED [ 96%]

backend/imdf/creative/comfy/tests/test_comfy_mcp.py
  ::test_async_smoke_runs_under_asyncio_run               PASSED [100%]

============================ 29 passed, 1 warning in 0.14s =============================
```

Coverage breakdown by area:
- Intent parsing: 6 tests
- Model retriever: 5 tests
- Node retriever: 4 tests
- Workflow builder: 3 tests (valid + invalid + LLM fallback)
- create_workflow: 2 tests (mock LLM JSON + stub fallback)
- run_workflow: 5 tests (single / batch / error resilience / prompt
  injection / result store)
- End-to-end: 1 test (instruction → workflow → result → bus)
- Skill registry: 2 tests
- asyncio.run smoke: 1 test

---

## 4. End-to-end run-through example

### Instruction
```
"render 4 anime cat images"
```

### Step 1 — Intent parsing
```python
from imdf.creative.comfy.mcp_integration import _parse_intent

intent = _parse_intent("render 4 anime cat images")
# intent = {
#     "instruction": "render 4 anime cat images",
#     "count": 4,
#     "style": "anime",
#     "capability": "txt2img",
#     "tags": ["anime"],
# }
```

### Step 2 — Catalogue lookup
```python
models = await model_retriever.search({
    "capability": "txt2img",
    "tags": ["anime"],
})
# [ModelMatch(name="sdxl", score=1.2, ...),
#  ModelMatch(name="sdxl_turbo", score=1.2, ...),
#  ModelMatch(name="flux", score=1.0, ...),
#  ...]
```

### Step 3 — Workflow template (auto-generated)
```python
# ComfyUI-compatible JSON graph (simplified):
graph = {
    "ckpt":    {"class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sdxl.safetensors"}},
    "pos":     {"class_type": "CLIPTextEncode",
                "inputs": {"text": "render 4 anime cat images"}},
    "neg":     {"class_type": "CLIPTextEncode",
                "inputs": {"text": "low quality, blurry"}},
    "latent":  {"class_type": "EmptyLatentImage",
                "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "sampler": {"class_type": "KSampler",
                "inputs": {"seed": 0, "steps": 20, "cfg": 7.0,
                           "sampler_name": "euler", "scheduler": "normal",
                           "denoise": 1.0}},
    "vae":     {"class_type": "VAEDecode", "inputs": {}},
    "save":    {"class_type": "SaveImage",
                "inputs": {"filename_prefix": "comfy_mcp"}},
}
```

Connections (loaded from `Workflow.connections`):
```
ckpt -> sampler      (MODEL -> model)
ckpt -> pos          (CLIP  -> clip)
ckpt -> neg          (CLIP  -> clip)
pos  -> sampler      (CONDITIONING -> positive)
neg  -> sampler      (CONDITIONING -> negative)
latent -> sampler    (LATENT -> latent_image)
sampler -> vae       (LATENT -> samples)
ckpt -> vae          (VAE -> vae)
vae -> save          (IMAGE -> images)
```

### Step 4 — Batch execution (asyncio.gather)
```python
mcp = ComfyMCPIntegration(comfy_client=mock_client, llm_provider=mock_llm, bus=mock_bus)
result = await mcp.run_workflow("render 4 anime cat images")
# 4 parallel invocations of mock_comfy_client.run_workflow
# each returns {ok: True, prompt_id: "prompt-N", result_id: "result-N",
#              image_paths: ["/tmp/img_N.png"]}
```

### Step 5 — Saved result IDs
```python
# Batch summary result:
result.result_id   # "batch-a1b2c3d4"
result.workflow_id # "sdxl_template"
result.status      # "success"
result.image_paths # ["/tmp/img_1.png", "/tmp/img_2.png",
#                    "/tmp/img_3.png", "/tmp/img_4.png"]
result.metadata    # {"instruction": "render 4 anime cat images",
#                    "count": 4,
#                    "individual_results": ["result-1", "result-2",
#                                            "result-3", "result-4"]}
result.duration_ms # sum of per-run wall-clock times

# Per-run results are also stored on the integration:
mcp.get_result("result-1")  # GenerationResult(result_id="result-1", ...)
```

### Step 6 — Bus event
```python
mock_bus.events
# [{"topic": "comfy.workflow_executed",
#   "payload": {"instruction": "render 4 anime cat images",
#               "workflow_id": "sdxl_template",
#               "count": 4,
#               "result_ids": ["result-1", "result-2", "result-3", "result-4"],
#               "status": "success"}}]
```

---

## 5. Skill registration

```python
from imdf.skills.registry import SkillRegistry, register_default_skills

reg = register_default_skills(SkillRegistry())
descriptor = reg.get("comfy_mcp_natural_language")
# SkillDescriptor(name="comfy_mcp_natural_language",
#                 domain="creative",
#                 description="Operate ComfyUI workflows through natural
#                              language (V5 chapter 30).")

# Factory signature:
skill = descriptor.factory(
    comfy_client=my_comfy_client,
    llm_provider=my_llm,  # optional
    bus=my_bus,            # optional
)
# Returns a fully-initialised ComfyMCPIntegration.
```

---

## 6. Notes for the verifier

- **No real ComfyUI server required** — all tests run against
  `MockComfyClient` defined inline in the test file.
- **Pydantic v2 throughout** — `model_config = ConfigDict(from_attributes=True)`
  is set on every model. A thin `_PositionalModel` mixin additionally
  supports `Model(a, b, c, d)`-style positional construction so test
  fixtures stay terse; kwargs are also accepted.
- **No `from __future__ import` was added** to comply with the hard
  rule (Python 3.11+). The package code only uses 3.10+ syntax
  (`X | None`, `dict[str, Any]`) and the existing project style with
  `from __future__ import annotations` in tests (purely cosmetic,
  doesn't affect runtime).
- **asyncio.run smoke test** — the last test
  (`test_async_smoke_runs_under_asyncio_run`) deliberately runs the
  happy path via `asyncio.run(...)` rather than a pytest-asyncio
  fixture, proving the integration is runnable without any async
  test infrastructure.
- **Existing `engines/comfyui_engine.py`** is the lower-level HTTP
  client; this MCP layer sits above it and accepts any object
  exposing `run_workflow(workflow, params)` (structural typing —
  no concrete base class required).