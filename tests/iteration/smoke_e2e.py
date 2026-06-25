"""P4-5-W2: end-to-end HTTP smoke (standalone iteration router, no main.py)."""
import json
import os
import sys

ROOT = "D:/Hermes/生产平台/nanobot-factory"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/backend")
os.environ["ITERATION_DATA_DIR"] = ROOT + "/backend/services/asset_service/iteration/store/data_test"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.asset_service.iteration.routes import router as iteration_router

app = FastAPI(title="iteration-standalone")
app.include_router(iteration_router)
c = TestClient(app)

print("=" * 60)
print("P4-5-W2 iteration HTTP smoke (standalone)")
print("=" * 60)

# 1
r = c.get("/api/v1/assets/agents")
print(f"[1] agents: status={r.status_code} count={r.json()['count']}")
assert r.status_code == 200 and r.json()["count"] == 7

# 2
r = c.post(
    "/api/v1/assets/sessions",
    json={"owner_id": "u1", "project_id": "p1", "modality": "image",
          "initial_prompt": "a knight", "title": "knight"},
)
sid = r.json()["session_id"]
print(f"[2] create session: status={r.status_code} sid={sid}")
assert r.status_code == 201 and r.json()["state"] == "draft"

# 3 - 3 iterations
for i in (2, 3):
    r = c.post(
        f"/api/v1/assets/sessions/{sid}/iterate",
        json={"text": f"a knight v{i}", "note": f"round{i}"},
    )
    assert r.status_code == 201
sess = c.get(f"/api/v1/assets/sessions/{sid}").json()
assert len(sess["prompt_versions"]) == 3
assert sess["state"] == "review"
print(f"[3] iterate x2: 3 versions, state={sess['state']}")

# 4 - AB test (3 variants)
pv_id = sess["prompt_versions"][2]["version_id"]
r = c.post(
    f"/api/v1/assets/sessions/{sid}/ab_test",
    json={"parent_prompt_version_id": pv_id,
          "variants": [{"text": "vA"}, {"text": "vB"}, {"text": "vC"}]},
)
ab = r.json(); aid = ab["ab_id"]
assert r.status_code == 201 and len(ab["variants"]) == 3
print(f"[4] ab_test: status={r.status_code} variants={len(ab['variants'])}")

# 5 - score + best
v0, v1, v2 = ab["variants"][0]["version_id"], ab["variants"][1]["version_id"], ab["variants"][2]["version_id"]
r = c.post(
    f"/api/v1/assets/sessions/{sid}/ab_test/{aid}/score",
    json={"scores": {v0: 0.6, v1: 0.92, v2: 0.78}},
)
assert r.status_code == 200
r = c.post(f"/api/v1/assets/sessions/{sid}/ab_test/{aid}/best")
assert r.status_code == 200
assert r.json()["winner_variant_id"] == v1
print(f"[5] ab best: winner=v1")

# 6 - multi-agent
r = c.post(
    "/api/v1/assets/multi_generate",
    json={"brief": {"script": "Scene 1: hero enters tavern.\n\nScene 2: hero meets wizard.",
                    "characters": ["hero"], "shots_per_scene": 1},
          "character_pool": {"hero": {"character_id": "hero", "reference_url": "/c/hero.png"}}},
)
multi = r.json()
mc = {}
for a in multi["asset_pool"]:
    mc[a["modality"]] = mc.get(a["modality"], 0) + 1
print(f"[6] multi_generate: ok={multi['ok']} modality={mc} scores={len(multi['qa_scores'])}")
assert multi["ok"] is True

# 7 - consistency
r = c.post(
    "/api/v1/assets/consistency/run",
    json={"project_id": "p1", "brief": {"script": "single scene"},
          "config": {"target_score": 0.85, "max_rounds": 3}},
)
cons = r.json()
print(f"[7] consistency: passed={cons['passed']} rounds={len(cons['rounds'])} final={cons['final_avg_score']:.2f}")

# 8 - history
r = c.get("/api/v1/assets/multi_generate/runs")
print(f"[8] runs history: count={r.json()['count']}")
r = c.get("/api/v1/assets/consistency/report")
print(f"[9] consistency history: count={r.json()['count']}")

print("=" * 60)
print("ALL OK")
print("=" * 60)