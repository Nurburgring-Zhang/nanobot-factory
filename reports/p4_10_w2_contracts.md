# P4-10-W2 报告: 合同/发票/客户管理

## 1. 任务概要

实现 4 个商业化核心模块: PDF 合同生成、国标发票、客户管理 (CRM)、工单系统。目标是为 P4-10 商业化能力提供完整的售前-售中-售后链路。

## 2. 交付清单

### 2.1 Backend 模块 (4 个新模块, 8 个 .py 文件)

| 模块 | 主要功能 | 关键能力 |
|------|----------|----------|
| `backend/contracts/` | PDF 合同 + 数字签名 | 3 模板 (服务/DPA/SLA) + ReportLab PDF + SM3 哈希链 + SM2 签名可选 + 变量替换 + on_order_paid 钩子 |
| `backend/invoices/` | 国标发票 + 防篡改 | 3 类型 (增值税普通/专用/电子) + INV-YYYYMMDD-NNNN 编号 + 13% 税计算 + 中文 PDF (msyh.ttc) + OFD 国标电子发票 (zip+xml) + SM3 防篡改 |
| `backend/crm/` | 客户 + 联系人 | 5 分级 (个人/SMB/中型/大型/战略) + 5 类跟进 (沟通/合同/付款/投诉/其他) + 1 客户 1 manager + 6 角色联系人 + 搜索/标签/manager 筛选 |
| `backend/tickets/` | 工单 + SLA | 4 类型 + 4 优先级 (P0/P1/P2/P3) + 5 状态机 (new→assigned→in_progress→resolved→closed) + SLA 自动评估 (1h/4h/24h/72h) + P0 立即通知 oncall (webhook + log fallback) |

### 2.2 测试 (4 个测试文件, 33 测试全过)

| 测试文件 | 测试数 | 覆盖 |
|----------|--------|------|
| `tests/contracts/test_pdf.py` | 9 | SM3 哈希 + 3 模板参数化 + 签名 + 列表 + 错误处理 + 变量替换 |
| `tests/invoices/test_generator.py` | 9 | 编号 + 税计算 + SM3 防篡改 + OFD zip 解析 + PDF 字节流 + 列表 + 钩子 |
| `tests/crm/test_customers.py` | 5 | CRUD + 5 分级 + 搜索/筛选 + 5 跟进 + 4 角色联系人 + 套餐升级 |
| `tests/tickets/test_workflow.py` | 10 | 状态机正常 + 非法转移 + 4 SLA 等级 + 响应达标/违约 + P0 通知 + SLA 统计 + 钩子 |
| **合计** | **33** | **0.36s 全部 PASS** |

### 2.3 Frontend 6 view (Vue 3 SFC + naive-ui)

| 路径 | 功能 |
|------|------|
| `frontend-v2/src/views/billing/Pricing.vue` | 5 套餐对比 + 推荐标记 + 升级弹窗 |
| `frontend-v2/src/views/billing/Orders.vue` | 订单列表 (状态/支付方式/金额) + 新订单弹窗 |
| `frontend-v2/src/views/billing/Invoices.vue` | 发票列表 (3 类型) + 下载 PDF/OFD + SM3 验证弹窗 |
| `frontend-v2/src/views/contracts/Contracts.vue` | 合同列表 + 3 模板 + 创建 + 下载 PDF + 签名 |
| `frontend-v2/src/views/crm/Customers.vue` | 客户列表 + 5 分级 tag + 搜索/筛选 + 详情抽屉 (跟进 timeline) |
| `frontend-v2/src/views/tickets/Tickets.vue` | 工单列表 + 4 优先级 + 4 SLA 卡片 + 状态机 + 评论 timeline |
| `frontend-v2/src/router/index.ts` | 新增 6 路由: /pricing /orders /invoices /contracts /crm /tickets |

## 3. 关键验证结果

### 3.1 PDF 真实生成
- 服务协议 PDF: ~2700 字节, 头部 `%PDF-1.4` (ReportLab Platypus)
- 含 8 条款 + 签名区 + SM3 指纹
- 3 模板 (服务/DPA/SLA) 均通过参数化测试

### 3.2 OFD 真实生成
- 中国国标电子发票格式 (GB/T 33190-2016)
- zip 容器 (PK 头) + `ofd.xml` + `signature.xml` + `META/doc.json`
- 含 SM3 防篡改签名块 (Algorithm="SM3")

### 3.3 SM3 防篡改
- 改 amount 后 verify 立即返回 valid=False
- 100% 复算 + 比对 hash_chain[0]

### 3.4 SLA 达标率统计
- 4 优先级 (P0=1h, P1=4h, P2=24h, P3=72h) 独立计数
- 整体达标率 + 按优先级达标率
- 响应超时自动标记 `sla_breached=True`

### 3.5 39 业务路由
- 4 个 FastAPI router (contracts, invoices, crm_customers, crm_contacts, tickets)
- 39 个 API 端点 + 4 OpenAPI 默认

## 4. 与 P4-10-W1 集成点

虽然 W1 billing 模块未交付, 但 W2 已实现 2 个对接钩子:
- `invoices.on_order_paid(order_id, buyer_name, amount)` — W1 收到 Order paid 后可调用, 自动生成电子发票
- `crm.on_plan_upgrade(customer_id, new_plan)` — 客户升级套餐, 写跟进 + 同步提升 tier + 返回 Order 模板 (W1 据此创建新 Order)
- `contracts.on_order_paid(order_id, plan_name, amount, company, email)` — W1 Order paid 后自动生成服务协议
- `tickets.on_customer_ticket(customer_id, ...)` — CRM 集成, 为客户创建工单

W1 后续实现时, 在 Order paid webhook 处理器中依次调用 `invoices.on_order_paid` + `contracts.on_order_paid` 即可完成自动化。

## 5. 风险与限制

1. **存储层为内存** — 当前 4 模块都使用进程内 `_STORE: Dict[str, ...]`, 重启即丢失。生产部署需替换为 P2-1 已规划的 PG 表 (alembic 迁移)。
2. **SM3 hashlib 不可用** — Windows Python 3.11 无 `hashlib.sm3_hex`, 当前用 `SM3FALLBACK:<sha256>` 标记, 不影响防篡改语义, 但非严格 GM/T 0004。生产建议安装 `gmssl` 库。
3. **前端未联调** — 6 view 渲染用 mock data, 实际接入需在 views 中替换 `onMounted` 处的 mock 调用为真实 API。
4. **OFD 简化版** — 国标 OFD 有完整 XML Schema, 当前实现为可解析的简化版本, 含必要字段 (发票号/购买方/销售方/明细/税/SM3 签名)。生产可对接完整 OFD Reader SDK。
