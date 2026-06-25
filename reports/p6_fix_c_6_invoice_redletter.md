# P6-Fix-C-6: 发票红冲 (Invoice Red-Letter / 红冲发票)

**任务**: P6-Fix-C-6
**完成日期**: 2026-06-25
**状态**: ✅ 完成

---

## 1. 目标

实现国标发票红冲流程 (Chinese accounting practice):
- 标记原发票作废 (voided)
- 反向生成新发票 (负数金额 — 红字发票)
- 关联订单退款 (调用 `billing.OrderService.refund()`)
- 红冲记录 + 红冲对查询 + 防重入

## 2. 交付物

| 文件 | 行数 | 角色 |
|------|------|------|
| `backend/invoices/redletter.py` | 333 | 红冲模块 (主实现) |
| `backend/tests/invoices/test_redletter.py` | 480 | 39 个测试用例 |
| `reports/p6_fix_c_6_invoice_redletter.md` | — | 本报告 |

## 3. 公开 API (`redletter.py`)

### 3.1 主入口: `redletter()`
```python
def redletter(
    invoice_no: str,                   # 原发票号
    reason: str,                        # 红冲原因 (必填, ≤512 字符)
    refund_amount: Optional[float] = None,  # 默认 = 原发票全额
    operator: Optional[str] = None,
    order_service: Any = None,          # 订单服务 (Optional, 用于触发订单退款)
) -> RedLetterResult:
```

**行为**:
1. 校验原票存在 + 未被红冲 + 状态为 issued/verified
2. 计算退款金额 (默认 = 原票金额)
3. **标记原票作废** (`status = "voided"`) + 重算 SM3 哈希
4. **生成反向发票** (金额为负) + 存到 `_STORE`
5. **调用订单退款** (若提供 `order_service`) → `OrderService.refund(order_id, reason, amount_cents)`
6. 写红冲记录 (原票号 + 红冲票号 + 原因 + 退款金额 + 订单退款状态 + 操作人)

**红冲编号规则**: `INV-YYYYMMDD-NNNN-R1` (R2, R3... 顺序递增, 跨进程残留时跳过已占用号)

### 3.2 查询 API

| 函数 | 作用 |
|------|------|
| `is_redlettered(invoice_no)` | 是否已被红冲 |
| `get_redletter(invoice_no)` | 取红冲记录 (输入原票号) |
| `get_redletter_pair(invoice_no)` | 取红冲对 (原票, 红冲票) — 支持双向查询 |
| `get_reverse_invoice_no(original_invoice_no)` | 取反向发票号 |
| `list_redlettered(order_id=None)` | 列出所有红冲记录 (可按订单过滤) |

### 3.3 数据结构

```python
@dataclass
class RedLetterRecord:
    original_invoice_no: str        # 原发票号
    red_letter_invoice_no: str      # 红冲反向发票号
    reason: str                     # 红冲原因
    red_lettered_at: str            # 红冲时间 (ISO8601)
    refund_amount: float            # 退款金额
    refund_currency: str = "CNY"
    order_refund: Optional[Dict] = None   # 关联订单退款记录
    operator: Optional[str] = None

@dataclass
class RedLetterResult:
    original: Invoice               # 原票 (status=voided)
    red_letter: Invoice             # 红冲票 (amount=-refund)
    record: RedLetterRecord
```

## 4. 测试结果

### 4.1 必跑命令
```bash
cd backend
python -m pytest tests/invoices/test_redletter.py -v
```

### 4.2 结果: **39/39 PASS** (0.26s)

```
TestBasicRedLetter::test_redletter_marks_original_voided_and_creates_reverse PASSED
TestBasicRedLetter::test_redletter_record_has_required_fields PASSED
TestBasicRedLetter::test_redletter_stores_reverse_in_store PASSED
TestNegativeAmountAndTax::test_reverse_invoice_has_negative_amount PASSED
TestNegativeAmountAndTax::test_reverse_invoice_preserves_buyer_seller PASSED
TestQueryAndLookup::test_is_redlettered_true_false PASSED
TestQueryAndLookup::test_get_redletter_returns_record PASSED
TestQueryAndLookup::test_get_redletter_pair_by_original PASSED
TestQueryAndLookup::test_get_redletter_pair_by_reverse_no PASSED
TestQueryAndLookup::test_get_redletter_pair_not_found PASSED
TestQueryAndLookup::test_get_reverse_invoice_no PASSED
TestQueryAndLookup::test_list_redlettered_by_order_id PASSED
TestQueryAndLookup::test_list_redlettered_empty_for_unused_order PASSED
TestIdempotencyAndGuards::test_redletter_unknown_invoice_raises_keyerror PASSED
TestIdempotencyAndGuards::test_double_redletter_raises_valueerror PASSED
TestIdempotencyAndGuards::test_voided_invoice_cannot_be_redlettered PASSED
TestIdempotencyAndGuards::test_blank_reason_rejected PASSED
TestIdempotencyAndGuards::test_oversized_reason_rejected PASSED
TestIdempotencyAndGuards::test_zero_refund_amount_rejected PASSED
TestIdempotencyAndGuards::test_over_refund_amount_rejected PASSED
TestPartialRefund::test_partial_refund_amount PASSED
TestPartialRefund::test_default_refund_amount_is_full PASSED
TestOrderRefundIntegration::test_redletter_calls_order_refund_full PASSED
TestOrderRefundIntegration::test_redletter_calls_order_refund_partial PASSED
TestOrderRefundIntegration::test_redletter_order_refund_failure_does_not_block PASSED
TestOrderRefundIntegration::test_redletter_no_order_service PASSED
TestOrderRefundIntegration::test_redletter_order_service_without_refund_method PASSED
TestRenderAndHash::test_redletter_pdf_renderable PASSED
TestRenderAndHash::test_redletter_ofd_renderable PASSED
TestRenderAndHash::test_redletter_updates_original_hash_chain PASSED
TestRenderAndHash::test_redletter_reverse_has_hash_chain PASSED
TestRenderAndHash::test_original_verify_fails_after_redletter PASSED
TestRenderAndHash::test_reverse_invoice_verifies PASSED
TestNumbering::test_reverse_no_first_attempt_is_r1 PASSED
TestNumbering::test_reverse_no_avoids_existing PASSED
TestSerialization::test_redletter_result_to_dict PASSED
TestSerialization::test_redletter_record_to_dict PASSED
TestFullFlow::test_full_flow_paid_invoice_to_refund PASSED
TestFullFlow::test_multiple_orders_independent_redletter PASSED

========================== 39 passed in 0.26s ==========================
```

### 4.3 回归验证
- `tests/invoices/test_generator.py` (baseline 9 tests): **9/9 PASS**
- 总计 invoices 模块: **48/48 PASS, 0 regression**

### 4.4 测试覆盖矩阵

| 维度 | 用例数 | 覆盖 |
|------|--------|------|
| 基本流程 (原票作废 + 红冲票生成 + 记录) | 3 | ✓ |
| 红字发票 (负数金额 + 负数税额 + 保留购销方) | 2 | ✓ |
| 查询 API (is_redlettered/get/pair/list) | 8 | ✓ |
| 防重入 + 边界校验 (KeyError/ValueError) | 7 | ✓ |
| 部分退款 (refund_amount < amount) | 2 | ✓ |
| 关联订单退款 (full/partial/失败/无 service/无方法) | 5 | ✓ |
| 渲染 + SM3 (PDF/OFD/哈希链/verify) | 6 | ✓ |
| 编号生成 (R1/R2 后缀 + 跳过已占用) | 2 | ✓ |
| 序列化 (to_dict 结构) | 2 | ✓ |
| 端到端 + 多订单独立 | 2 | ✓ |
| **合计** | **39** | ✓ |

## 5. 设计要点

### 5.1 为什么直接修改 Invoice.status 而不是删原票?
- 财务审计要求原票**作废但可追溯** (国标《发票管理办法》)
- 红冲链路是双向闭环: 原票 → 红冲 → 新红字发票
- 反向发票的 SM3 哈希链也含原票号, 防篡改

### 5.2 为什么红冲票也存到 `_STORE`?
- 红冲票本身是有效发票, 需要支持查询 / 验证 / 下载 PDF/OFD
- 与原票生命周期独立: 原票 voided, 红冲票 issued
- 财务对账时红冲票可作为冲账凭证

### 5.3 订单退款金额转换
- `refund_amount` (元) → `amount_cents` (分)
- 全额退款时传 `amount_cents=None` (OrderService 语义: None=退剩余全额)
- 部分退款时 `int(round(refund_amount * 100))`

### 5.4 订单退款失败的优雅降级
- 订单服务调用失败时, **红冲仍正常完成**
- 失败信息存入 `record.order_refund["error"]`, 供审计排查
- 这是有意设计: 发票红冲与订单退款是两个独立事务, 不应互相阻塞

### 5.5 守卫顺序: `is_redlettered` 优先于 `voided` 检查
- 第一次红冲后原票状态 = voided
- 第二次调用会先匹配 `is_redlettered` (返回具体反向票号), 给出最精确的错误信息
- 而非宽泛的 "already voided"

## 6. 上下游集成

### 6.1 复用现有模块
- `invoices._STORE` / `_BY_ORDER` — 共享存储
- `invoices.generate_invoice()` — 红冲票的元数据
- `invoices.calc_tax()` — 税额计算 (取负)
- `invoices.render_invoice_pdf()` / `render_invoice_ofd()` — 红冲票的 PDF/OFD 渲染
- `invoices.verify_invoice()` — 红冲后原票 verify 失败 (status=voided 改了 hash)
- `billing.OrderService.refund()` — 关联订单退款 (可选)

### 6.2 路由层 (下一步可加)
当前 `routes.py` 未包含红冲 API。下一步可加:
```python
@router.post("/{invoice_no}/redletter")
def redletter_endpoint(invoice_no: str, req: RedLetterRequest):
    ...
```

但当前任务范围仅 `redletter.py` + 测试, 路由留给后续 worker。

## 7. 已知限制 / 未来扩展

1. **进程内存储**: `_REDLETTER_STORE` / `_RED_BY_REVERSE` / `_RED_BY_ORDER` 与 invoices 一致, 进程重启丢失
   - 迁移到 SQLite/PG 时, 这三个表需建库表
2. **未提供 HTTP 路由**: 仅函数层 API, FastAPI 路由待 P-后续任务
3. **退款失败时不重试**: 订单服务失败时仅记录错误, 不自动重试 — 留给 ops 手动处理
4. **不支持链式红冲**: 同一原票红冲一次后, R2 仅在跨进程残留时触发 (现有 voided 守卫拦截)

## 8. 验证清单

- [x] 硬启动检查: `Test-Path 'backend\invoices'` PASS
- [x] `redletter.py` 实现: 333 行, 含 dataclass + 守卫 + 查询 API
- [x] `test_redletter.py`: 39 测试, 全 PASS
- [x] 必跑命令: `pytest backend/invoices/tests/test_redletter.py -v` → 39/39
- [x] 回归: invoices 9 baseline + 39 new = 48/48 PASS
- [x] 报告: `reports/p6_fix_c_6_invoice_redletter.md`
- [x] 进度板: `board.md` 已更新
