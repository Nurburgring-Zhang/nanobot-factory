"""P4-5-W2: final verification - 3 acceptance demos."""
import os
import sys

ROOT = "D:/Hermes/生产平台/nanobot-factory"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/backend")
os.environ["ITERATION_DATA_DIR"] = ROOT + "/backend/services/asset_service/iteration/store/data_test"

from services.asset_service.iteration.session import get_session_store
from services.asset_service.iteration.agents import get_orchestrator
from services.asset_service.iteration.consistency import ConsistencyConfig, get_workflow

print("=" * 60)
print("P4-5-W2: 3 acceptance demos")
print("=" * 60)

# Demo 1: 3-turn dialogue -> 3 variants
store = get_session_store()
s = store.create_session(owner_id="demo", project_id="p1", modality="image",
                          initial_prompt="v1: a cat")
sid = s["session_id"]
store.iterate_prompt(sid, "v2: a cat wearing a hat")
store.iterate_prompt(sid, "v3: a cat wearing a wizard hat")
sess = store.get_session(sid)
print(f"[1] Multi-turn dialogue: {len(sess['prompt_versions'])} versions, state={sess['state']}")
assert len(sess["prompt_versions"]) == 3

# Demo 2: multi-agent
report = get_orchestrator().run_sync(
    brief={"script": "Scene 1: hero enters tavern.\n\nScene 2: hero meets wizard.",
           "characters": ["hero"], "shots_per_scene": 1},
    character_pool={"hero": {"character_id": "hero", "reference_url": "/c/hero.png"}},
)
mc = {}
for a in report.asset_pool:
    mc[a["modality"]] = mc.get(a["modality"], 0) + 1
print(f"[2] Multi-agent: ok={report.ok} modality={mc} chars={list(report.character_state.keys())}")
assert report.ok and len(report.asset_pool) >= 4

# Demo 3: 5-round consistency convergence
state = {"calls": 0}

def improving_scorer(_a):
    state["calls"] += 1
    return min(0.96, 0.5 + state["calls"] * 0.05)

cons = get_workflow().run(
    project_id="demo-final",
    brief={"script": "single scene"},
    config=ConsistencyConfig(target_score=0.85, max_rounds=5, nsfw_threshold=0.40),
    scorer=improving_scorer,
)
print(f"[3] Consistency: passed={cons.passed} rounds={len(cons.rounds)} "
      f"final={cons.final_avg_score:.2f} (>=0.85)")
assert cons.final_avg_score >= 0.85

print("=" * 60)
print("ALL DEMOS PASS")
print("=" * 60)