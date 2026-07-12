# P11 Sprint A Report: call_provider_smart 路由 inert 修复

**Date**: 2026-06-26
**Author**: coder (mvs_4f3bf48135964d3eb613065f9b59a304)
**Scope**: 2h, 1 P1 (P11-A: Provider Registry 默认 enabled + 路由去重)
**Status**: ✅ COMPLETE
**Test pass rate**: 44/44 PASS (12 new + 25 existing + 7 existing)

完整 deliverable + 详细路由图见:
`C:\Users\Administrator\.mavis\plans\plan_d0803a33\outputs\p11_sprint_a_routing\deliverable.md`

---

## 1. Summary

3 处改动 + 16 个新测试:

| # | 文件 | 改动 |
|---|---|---|
| 1 | `backend/imdf/engines/provider_registry.py` | `_get_default_providers()` 中 `openai-compatible.enabled = True`, 加默认 baseUrl / chatModels / imageModels |
| 2 | `backend/imdf/api/canvas_web.py` | chat_api 从 `/api/chat` 迁到 `/api/v1/chat/smart` (避免与 unified_chat 冲突) |
| 3 | `backend/imdf/api/model_routes.py` | unified_chat 内部从 `gateway.chat()` 切换到 `call_provider_smart` |

| # | 文件 | 新增 |
|---|---|---|
| 4 | `backend/imdf/tests/test_provider_registry.py` | +4 测试 (TestP11ADefaultProvidersEnabled) |
| 5 | `backend/imdf/tests/test_chat_routing.py` | +12 测试 (新文件, 路由去重 + 集成验证) |

## 2. Test Results (44/44 PASS)

```
backend/imdf/tests/test_chat_routing.py ............ 12 passed
backend/imdf/tests/test_provider_registry.py ....... 25 passed (4 new + 21 existing)
backend/imdf/tests/test_chat_provider_smart.py .....  7 passed (P10-B 不回退)
TOTAL: 44/44 PASS in 2.72s
```

## 3. End-to-End Smoke Test

```
POST /api/chat {"messages": [{"role": "user", "content": "hello"}], "model": "auto"}
→ 200 OK
→ success=True, content="Hi from P11-A unified_chat"
→ provider="openai-compatible", cost_usd=0.0001
→ call_provider_smart 被命中 (限流/熔断/mock/usage/audit 全链路可达)
```

## 4. 路由图 (修复后)

```
POST /api/chat          → unified_chat    → call_provider_smart (P5-W1 入口)
POST /api/v1/chat       → v1_chat_api     → NanobotAdapter (legacy, 不变)
POST /api/v1/chat/smart → chat_api        → call_provider_smart (P10-B 入口)
```

3 个 chat 端点, 0 冲突, 每个路径只有 1 个 POST handler。

## 5. P11-A 未做的项目 (建议 P11-B+ 跟进)

- locust 100 req/s /api/chat, P95 < 100ms
- 其他 4 个 provider (modelscope/volcengine/comfyui/jimeng-cli) 的 enabled 策略
- 前端 /api/chat vs /api/v1/chat/smart 路径统一