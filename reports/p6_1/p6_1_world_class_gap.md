# P6-1: World-Class Gap Analysis (Labelbox / Scale AI / Snorkel / etc.)

> Comparing our 12 microservices + 1 gateway to **10+ best-in-class data platforms**.
> Gap = feature our peers have, we don't yet, that real customers would notice.
> Generated 2026-06-24.

---

## Comparison Matrix

| Platform | Best-known for | Our equivalent | Gap | Severity |
|---|---|---|---|---|
| **Labelbox** | Catalog + ontology + batch labeling + quality scoring | dataset_service (CRUD) + annotation_service (operators) + scoring_service (15 ops) | **No ontology schema editor**, **No labeling quality scoring** (we have generic scoring, not inter-annotator agreement / Cohen's kappa) | **P0** |
| **Scale AI** | Rapid (labeling) + Studio (custom workflows) + Dynamics (eval) | workflow_service (DAG, 50+ templates) + agent_service (15 agents) + evaluation_service | **No Dynamics-equivalent** (model-in-the-loop eval), **No Rapid turnaround SLA** | **P1** |
| **Snorkel** | Programmatic labeling + weak supervision | annotation_service + agent_service | **No labeling functions (LF)**, **No weak supervision label model** (we don't compute noisy label probabilities) | **P0** |
| **SuperAnnotate** | Pixel-perfect segmentation + 3D point cloud | annotation_service (mostly bbox/text) | **No segmentation mask tools**, **No 3D cuboid / point cloud annotation** | **P1** |
| **Encord** | Active learning loop | annotation_service + agent_service | **No AL sampler** (we don't pick hardest examples to label next) | **P1** |
| **V7 Darwin** | Auto-annotation + auto-train | annotation_service + agent_service | **No model-assisted prelabel** (we have `/api/prelabel` but it's simple) | **P1** |
| **Kili** | Multi-modal collaboration + project mgmt | collection_service + workflow_service | **No project dashboard**, **No reviewer assignment workflow** | **P2** |
| **Roboflow** | Visual data + model training | dataset_service + asset_service (image/video) | **No hosted training**, **No model export pipeline** | **P1** |
| **Hugging Face Datasets** | Versioned datasets + collaboration + parquet streaming | dataset_service (in-memory) | **No git-LFS-style versioning**, **No parquet streaming**, **No community cards** | **P0** |
| **ComfyUI** | Node-based visual workflow | workflow_service (DAG + 50 templates) | **No live visual editor in UI** (templates defined in code, not drag-drop) | **P1** |
| **Runway / Pika / Luma** | Video generation | asset_service (image/video generators) | **No Gen-3 / Sora-class video model**, **No camera motion control** | **P1** |
| **HeyGen** | Digital human / talking head | asset_service (voices, characters, consistency_check) | **No talking-head synthesis**, **No lip sync** | **P2** |
| **Weights & Biases** | Experiment tracking + sweeps | (none — gap) | **No ML experiment tracking**, **No hyperparam sweeps** | **P2** |
| **Neptune.ai** | Model registry + metadata | (none — gap) | **No model registry** (we have `/api/v1/models` but it's a stub) | **P2** |
| **Comet.ml** | LLM tracing + prompt mgmt | agent_service (memory, hindsight) | **No LLM call tracing**, **No prompt version mgmt** | **P2** |
| **LangSmith** | LLM eval + datasets | agent_service + evaluation_service | **No chain-of-thought visualization**, **No eval dataset curation** | **P2** |

---

## Top 10 P0/P1 Gaps (block real-customer value)

### 1. **No dataset versioning (git-LFS style)** — P0

**Current**: `dataset_service` has CRUD + sample listing, but no commit history, no diff between versions, no rollback.
**World-class**: HF Datasets has commit hashes + parquet streaming + dataset cards.
**Effort**: 2 weeks (need DVC or lakeFS integration + UI).
**Value**: Customers can't reproduce experiments without versioning.

### 2. **No ontology / schema editor** — P0

**Current**: Annotation task is free-form (`/api/v1/tasks` accepts arbitrary fields).
**World-class**: Labelbox lets you define `BBox(class="car", attributes={occluded, truncated})` in a UI, then export the schema for annotators.
**Effort**: 1 week (schema model + JSON schema validation + UI).
**Value**: Real customers need structured labeling specs.

### 3. **No weak supervision / programmatic labeling** — P0

**Current**: Annotation is manual via operators.
**World-class**: Snorkel lets you write Labeling Functions (Python functions that vote on labels), then trains a label model to denoise.
**Effort**: 3 weeks (LF runner + label model training + UI for LF authoring).
**Value**: 10x cheaper annotation for industrial-scale data.

### 4. **No inter-annotator agreement / quality scoring** — P0

**Current**: `scoring_service` has 15 generic operators (aesthetic, NSFW, etc.) but no IAA metrics.
**World-class**: Labelbox computes Cohen's kappa, Krippendorff's alpha, majority vote agreement.
**Effort**: 1 week.
**Value**: Without IAA, you can't tell if your labels are reliable.

### 5. **No active learning loop** — P1

**Current**: Annotators see a random sample.
**World-class**: Encord picks the next batch by uncertainty (model says "I'm 51% sure on these").
**Effort**: 2 weeks (uncertainty sampler + integration with `/api/prelabel`).
**Value**: 3-5x annotation efficiency on hard datasets.

### 6. **No model-assisted prelabel UI** — P1

**Current**: `/api/prelabel` exists but is a thin API.
**World-class**: V7 Darwin shows prelabels overlaid on the image; annotator just confirms or corrects.
**Effort**: 2 weeks (SAM/SAM2 integration + UI overlay).
**Value**: 4x throughput on segmentation tasks.

### 7. **No pixel-level segmentation tools** — P1

**Current**: `annotation_service` has bbox + text operators, no mask tools.
**World-class**: SuperAnnotate has polygon, brush, smart-segment, SAM-prompted segmentation.
**Effort**: 3 weeks (frontend + SAM2 backend).
**Value**: Required for medical imaging, autonomous driving.

### 8. **No 3D point cloud / cuboid annotation** — P1

**Current**: No 3D endpoints.
**World-class**: Scale AI's Rapid has full 3D cuboid + point cloud workflows.
**Effort**: 6 weeks (3D viewer + lidar rendering).
**Value**: Required for robotics / autonomous driving customers.

### 9. **No live visual workflow editor** — P1

**Current**: `workflow_service` has 50+ templates defined in `templates.py` (Python code).
**World-class**: ComfyUI has drag-drop node editor + live preview + share-by-URL.
**Effort**: 4 weeks (React Flow + WebSocket preview).
**Value**: Power users expect visual workflow editing.

### 10. **No model registry / experiment tracking** — P1 (or P2 for narrow use)

**Current**: `/api/v1/models` exists in routes.yaml (line 227) but is a stub pointing to monolith.
**World-class**: W&B / Neptune track every training run with metrics, params, artifacts.
**Effort**: 3 weeks (MLflow integration + UI).
**Value**: ML teams need this for reproducibility.

---

## Where We Are Competitive

Don't undersell what we have. We **DO** compete in:

| Capability | Evidence | Comparable to |
|---|---|---|
| Multimodal data ingest (image + video + voice + music + storyboard) | `asset_service/generators.py` + 11 endpoints | Runway / Pika / HeyGen (narrower than us) |
| Multi-agent orchestration (15 agent types + memory + hindsight) | `agent_service` (107 routes, 10 skills) | LangChain / AutoGen (we have more bounded context) |
| DAG workflow with 50+ templates | `workflow_service` (94 routes, templates.py) | ComfyUI (we have more production templates) |
| PII / aesthetic / NSFW scoring | `scoring_service` (15 operators) | Hive / Imagga (similar coverage) |
| RAG + multimodal search | `search_service` (43 routes, multimodal_rag.py) | Vespa / Weaviate (smaller scale but multimodal-native) |
| Multi-tenant notification + WebSocket inbox | `notification_service` (24 routes, /ws) | Knock / SendBird (similar) |

---

## Realistic 12-Month Roadmap to World-Class

### Quarter 1: Foundation (current P3-P5 work)
- ✅ 12 microservices + gateway + common lib (DONE)
- ⏳ Celery + Redis queue (P3-3) — IN PROGRESS
- ⏳ PG + OSS production deploy (P4)
- ⏳ E2E + load test (P5)

### Quarter 2: Data Quality Pillar
- **Dataset versioning** (git-LFS / DVC) — P0
- **Inter-annotator agreement** metrics — P0
- **Active learning loop** with model-assisted prelabel — P1
- **Ontology schema editor** — P0

### Quarter 3: Advanced Modalities
- **Pixel-level segmentation** (SAM2 + brush) — P1
- **3D cuboid / point cloud** — P1 (only if robotics customers exist)
- **Talking head synthesis** (HeyGen-class) — P2

### Quarter 4: ML Platform
- **Model registry + experiment tracking** (MLflow) — P1
- **Weak supervision** (Snorkel-style LF + label model) — P0
- **Live visual workflow editor** (React Flow + WS) — P1

### Year 2: Differentiators
- Vertical-specific templates (medical, autonomous, retail)
- Marketplace (community workflows, model zoo)
- White-label deployment (multi-tenant SaaS)

---

## Bottom Line

**Today**: We are a **mid-tier industrial data platform** with strong agentic AI + multimodal generation + workflow orchestration. Closer to an "AI-native Labelbox" than "ML platform".

**To match world-class**: Need 5 things in priority order —
1. Dataset versioning (P0)
2. Ontology schema + IAA (P0)
3. Weak supervision (P0)
4. Active learning loop (P1)
5. Pixel / 3D annotation (P1)

Total effort: ~12-18 person-months across 12 months. Achievable with current 12-service architecture as the foundation.

**Strategic positioning**: Lean into **agentic AI workflows** (our unique strength vs Labelbox/Scale). Position as "the AI-native data factory" rather than competing head-on with pure-labeling tools.