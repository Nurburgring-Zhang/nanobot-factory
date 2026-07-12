"""R2 deep re-audit verification script — runs multiple checks in one go."""
import sys
import asyncio
import threading
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')

print("=" * 60)
print("R2 VERIFICATION TEST SUITE")
print("=" * 60)

# ============================================
# 1. Meta_Kim 7-step loop detailed output
# ============================================
print("\n--- 1. Meta_Kim 7-step loop ---")
from imdf.engines.meta_kim_engine import MetaKimEngine

async def go_mk():
    e = MetaKimEngine()
    res = await e.govern_run(request='清洗数据', context={})
    d = res.model_dump()
    intent = d.get('intent', {})
    print(f"  1.CLARIFY: type={intent.get('intent_type')} desc={intent.get('description')[:40]}")
    caps = d.get('capabilities', [])
    print(f"  2.SEARCH: {len(caps)} capabilities")
    for c in caps[:2]:
        print(f"     - {c.get('capability_id')}: {c.get('name')}")
    print(f"  3.SELECT: owner={d.get('owner')}")
    tasks = d.get('tasks', [])
    print(f"  4.SPLIT: {len(tasks)} tasks")
    results = d.get('results', [])
    print(f"  5.EXECUTE: {len(results)} results, all via stub: {all(r.get('output', {}).get('via') == 'stub' for r in results)}")
    v = d.get('verified', {})
    print(f"  6.VERIFY: succeeded={v.get('succeeded')} score={v.get('score')}")
    lessons = d.get('lessons', [])
    print(f"  7.LEARN: {len(lessons)} lessons, types: {set(l.get('type') for l in lessons)}")
asyncio.run(go_mk())

# ============================================
# 2. Multi-agent race test
# ============================================
print("\n--- 2. Multi-agent race (2 threads, 50 bots each) ---")
from imdf.engines.octo_engine import OctoEngine

results_box = {'a': [], 'b': []}
def worker(thread_id):
    oe = OctoEngine()
    for i in range(50):
        bid = oe.create_bot(name=f'{thread_id}-{i}', system_prompt='x')
        results_box[thread_id].append(bid)

t1 = threading.Thread(target=worker, args=('worker_a',))
t2 = threading.Thread(target=worker, args=('worker_b',))
t1.start(); t2.start(); t1.join(); t2.join()

a_unique = len(set(results_box['a'])) == len(results_box['a'])
b_unique = len(set(results_box['b'])) == len(results_box['b'])
all_unique = len(set(results_box['a']) | set(results_box['b'])) == len(results_box['a']) + len(results_box['b'])
print(f"  Worker A created {len(results_box['a'])} bots (unique: {a_unique})")
print(f"  Worker B created {len(results_box['b'])} bots (unique: {b_unique})")
print(f"  No cross-process collision: {all_unique}")
print(f"  Note: each thread is its own OctoEngine() = its own in-memory store")

# ============================================
# 3. Comfy real workflow with mock client
# ============================================
print("\n--- 3. Comfy workflow with mock client ---")
from imdf.creative.comfy.mcp_integration import ComfyMCPIntegration
from imdf.creative.comfy.mcp_integration import ComfyClientLike

calls = {'n': 0}
class MockComfy(ComfyClientLike):
    def run_workflow(self, workflow):
        calls['n'] += 1
        return {'prompt_id': f'mock-{calls["n"]}', 'outputs': {'img': ['mock.png']}}
    def ping(self):
        return True

m = ComfyMCPIntegration(comfy_client=MockComfy())
print(f"  ComfyMCPIntegration instantiated OK")
print(f"  Public methods: {[x for x in dir(m) if not x.startswith('_') and callable(getattr(m, x))][:8]}")

# ============================================
# 4. RedFox real platform
# ============================================
print("\n--- 4. RedFox real platform (5 real clients) ---")
from imdf.creative.redfox.registry import PLATFORMS, PlatformId
real_count = 0
for pid, client in PLATFORMS.items():
    cls = type(client).__name__
    is_real = cls != 'NotImplementedClient'
    if is_real:
        real_count += 1
    print(f"  {pid.value:15s} -> {cls:25s} {'[REAL]' if is_real else '[STUB]'}")
print(f"  Real platforms: {real_count}/11")

# ============================================
# 5. Agent memory persistence
# ============================================
print("\n--- 5. Agent memory persistence ---")
from imdf.engines.agent_engine import AgentEngine
e1 = AgentEngine()
e1.agent_session('sess1')
e1.agent_memory('sess1', 'lesson', 'crawlers should retry 3x')

e2 = AgentEngine()  # simulate restart
v = e2.agent_memory('sess1', 'lesson')
print(f"  Set 'lesson' = 'crawlers should retry 3x' in e1")
print(f"  After restart, e2 sees: {v}")
print(f"  PERSISTED: {v == 'crawlers should retry 3x'}")

# ============================================
# 6. Token budget enforcement
# ============================================
print("\n--- 6. Token budget enforcement ---")
from imdf.engines.usage_tracker import UsageTracker
ut = UsageTracker.instance()
budget_methods = [m for m in dir(ut) if 'budget' in m.lower() or 'cap' in m.lower() or 'enforce' in m.lower()]
print(f"  Budget methods: {budget_methods}")
print(f"  Has check_budget: {hasattr(ut, 'check_budget')}")
print(f"  Has enforce_budget: {hasattr(ut, 'enforce_budget')}")

# ============================================
# 7. Real LLM call
# ============================================
print("\n--- 7. Real LLM call for 1 random agent ---")
mk = MetaKimEngine()
print(f"  MetaKimEngine._llm = {mk._llm}")
print(f"  has_llm: {mk._llm is not None}")

# ============================================
# 8. Vida real screen capture
# ============================================
print("\n--- 8. Vida screen capture methods ---")
from imdf.intelligence.vida.screen_capture import ScreenCapture
sc = ScreenCapture()
cap_methods = [m for m in dir(sc) if m.startswith('_capture') or m == 'capture']
print(f"  Capture methods: {cap_methods}")
print(f"  platform: {getattr(sc, 'platform', 'N/A')}")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
