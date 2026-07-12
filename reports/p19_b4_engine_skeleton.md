# P19-B4 — 6 大引擎骨架 报告

> **完成时间**: 2026-07-01 16:46 → 17:05 (Asia/Shanghai)
> **测试**: 72 passed / 7 test files / 0 failed
> **任务**: P19-B4 / plan_84e3e1db

## 6 大引擎 (V5)

| # | 引擎 | 模块 | V5 章节 | 测试数 | 关键接口 |
|---|---|---|---|---|---|
| 1 | **CrawlerEngine** | `crawler_engine.py` | §15 | 9 | `start_crawl / pause_job / resume_job / stop_job / status / metrics` |
| 2 | **AgentEngine**   | `agent_engine.py`   | §16 | 9 | `invoke_agent / agent_session / agent_memory` |
| 3 | **OctoEngine**    | `octo_engine.py`    | §25 | 12 | `create_bot/channel/matter / execute_collab (6 模式)` |
| 4 | **VidaEngine**    | `vida_engine.py`    | §26 | 12 | `capture / analyze / predict / execute (cu MCP)` |
| 5 | **MetaKimEngine** | `meta_kim_engine.py`| §27 | 10 | `run_governance_loop (8 阶段) / record_lesson` |
| 6 | **DramaEngine**   | `drama_harness.py`  | §29 | 16 | `create_drama_project / generate_script / design_character / design_scene / generate_shot / generate_video / assemble` |

**集成测试**: `test_engine_router_integration.py` (4 tests) — 验证 6 个 engine 通过 `engine_router.get_engine()` 全部可访问 + 启停。

## 文件清单

### 新增 (7 源文件 + 7 测试文件 = 14)
```
backend/imdf/engines/crawler_engine.py          (~360 行)
backend/imdf/engines/agent_engine.py            (~270 行)
backend/imdf/engines/octo_engine.py             (~360 行)
backend/imdf/engines/vida_engine.py             (~280 行)
backend/imdf/engines/meta_kim_engine.py         (~340 行)
backend/imdf/engines/drama_harness.py           (~390 行)
backend/imdf/engines/tests/__init__.py
backend/imdf/engines/tests/test_crawler_engine.py
backend/imdf/engines/tests/test_agent_engine.py
backend/imdf/engines/tests/test_octo_engine.py
backend/imdf/engines/tests/test_vida_engine.py
backend/imdf/engines/tests/test_meta_kim_engine.py
backend/imdf/engines/tests/test_drama_engine.py
backend/imdf/engines/tests/test_engine_router_integration.py
backend/imdf/drama/__init__.py                  (满足硬启动 v3 检查)
```

### 修改 (1 增量)
```
backend/imdf/engines/engine_router.py           (追加 6 engine 注册段, 273 → 387 行)
```

## 统一接口契约

```python
# 每个 engine 都有
engine.start()      # → "running"
engine.pause()      # → "paused"
engine.resume()     # → "running"
engine.stop()       # → "stopped"
engine.status()     # → {"state": ..., ...}
```

通过 `engine_router`:
```python
from engines.engine_router import get_engine, start_all_engines, stop_all_engines
get_engine("crawler")       # → CrawlerEngine singleton
get_engine("agent")         # → AgentEngine singleton
get_engine("octo")          # → OctoEngine singleton
get_engine("vida")          # → VidaEngine singleton
get_engine("meta_kim")      # → MetaKimEngine singleton
get_engine("drama")         # → DramaEngine singleton
start_all_engines()         # → {name: {"state": "running", ...}}
stop_all_engines()          # → {name: {"state": "stopped", ...}}
reset_engine_singletons()   # test-only
```

## 测试结果

```
backend/imdf/engines/tests/test_crawler_engine.py ............ 9 passed
backend/imdf/engines/tests/test_agent_engine.py .............. 9 passed
backend/imdf/engines/tests/test_octo_engine.py ............... 12 passed
backend/imdf/engines/tests/test_vida_engine.py ............... 12 passed
backend/imdf/engines/tests/test_meta_kim_engine.py ........... 10 passed
backend/imdf/engines/tests/test_drama_engine.py .............. 16 passed
backend/imdf/engines/tests/test_engine_router_integration.py  4 passed
                                                       =============
                                                       72 passed
```

## 关键设计决策

1. **Wrap vs build fresh**: CrawlerEngine / AgentEngine / DramaEngine wrap
   existing engines (`data_collection_engine` / `agent_router` /
   `ShortDramaEngine`); OctoEngine / VidaEngine / MetaKimEngine are built
   fresh per V5 specs.

2. **Lazy import**: AgentEngine uses `_ensure_agent_classes()` so the
   `imdf.agents.*` import (which transitively pulls `services.*`) only
   happens on first instantiation, not at module load.

3. **Resilient import path**: AgentEngine tries `imdf.agents.base` first
   then `agents.base` (for both `PYTHONPATH=backend` and
   `PYTHONPATH=backend/imdf` setups).

4. **Graceful degradation**: MetaKimEngine logs a warning when AuditChain
   isn't available and runs without audit. VidaEngine falls back to
   deterministic mock when MCP daemon is unreachable. DramaEngine falls
   back to stubs when `ShortDramaEngine.phase_*` raises.

5. **In-memory + persistence**: each engine keeps authoritative in-memory
   state but mirrors lifecycle transitions into the underlying store
   (CrawlerEngine → JSON state, MetaKimEngine → AuditChain when available,
   DramaEngine → `_output_dir`).

6. **Job vs engine lifecycle**: CrawlerEngine distinguishes
   engine-level (`start/stop/pause/resume/status()` — no args) from
   job-level (`pause_job/resume_job/stop_job/status(job_id)` — job_id).

## 与 V5 章节对应

| V5 章节 | 标题 | 状态 |
|---|---|---|
| §15 | 爬虫引擎 (83 渠道) | ✅ skeleton |
| §16 | Agent 引擎 (13 Agent) | ✅ skeleton |
| §25 | Octo 引擎 (Bot/Channel/Matter + 6 协作模式) | ✅ skeleton |
| §26 | Vida 引擎 (屏幕感知) | ✅ skeleton |
| §27 | Meta-Kim 治理循环 | ✅ skeleton |
| §29 | 短剧 Harness | ✅ skeleton |

## VERDICT

```
[PASS] 6 engines instantiate + lifecycle OK
[PASS] 6 engines integrate via engine_router
[PASS] 72/72 unit tests pass
[PASS] No regression on existing engines
[PASS] V5 §15/§16/§25/§26/§27/§29 skeleton complete
```