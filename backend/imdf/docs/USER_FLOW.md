# IMDF 用户流程文档 (User Flow Guide)

> Infinite Multimodal Data Foundry — 多模态数据生产平台
> 版本: 2.0.0 | 最后更新: 2026-06-15

---

## 目录

1. [角色概览](#角色概览)
2. [管理员首次设置流程](#管理员首次设置流程)
3. [标注员日常工作流](#标注员日常工作流)
4. [审核员审核流程](#审核员审核流程)
5. [项目经理查看统计](#项目经理查看统计)
6. [需求方查看进度](#需求方查看进度)
7. [API 参考](#api-参考)

---

## 角色概览

| 角色 | 权限范围 | 典型任务 |
|------|---------|---------|
| **admin** | 系统管理、用户管理、配置 | 创建用户、系统配置、备份 |
| **project_manager** | 项目管理、资源分配、统计 | 创建项目、分配任务、查看报表 |
| **data_labeler** | 数据标注、质量反馈 | 图像标注、文本标注、音频标注 |
| **reviewer** | 审核标注结果、质量控制 | 审核标注、打回修正、金标准检测 |
| **requester** | 提交需求、查看进度 | 提交数据需求、追踪交付状态 |

---

## 管理员首次设置流程

### 1. 创建管理员账号

```bash
# 方式1: 使用脚本创建
python scripts/create_admin.py --username admin --password MySecurePass123 --role admin

# 方式2: 通过API注册 (需要先启动服务)
curl -X POST http://localhost:8765/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"MySecurePass123","role":"admin"}'
```

### 2. 启动服务

```bash
# 开发模式
python api/canvas_web.py --port 8765

# 生产模式 (systemd)
sudo systemctl start imdf
sudo systemctl enable imdf   # 开机自启
```

### 3. 登录并获取Token

```bash
curl -X POST http://localhost:8765/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"MySecurePass123"}'

# 响应:
# {"access_token": "eyJ...", "token_type": "bearer"}
```

保存返回的 `access_token`, 后续所有API请求都需要在Header中携带:
`Authorization: Bearer <access_token>`

### 4. 配置系统参数

编辑项目根目录的 `.env` 文件:

```bash
# 服务配置
IMDF_WEB_HOST=0.0.0.0
IMDF_WEB_PORT=8765
UVICORN_WORKERS=4

# 并发保护
MAX_CONCURRENT_REQUESTS=100
REQUEST_TIMEOUT_SECONDS=30
ENABLE_ROBUSTNESS_MIDDLEWARE=true

# 限流
RATE_LIMIT_DEFAULT=200/minute

# 日志
LOG_LEVEL=INFO
```

### 5. 创建项目团队

```bash
# 创建团队
curl -X POST http://localhost:8765/api/crowd/teams \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"数据生产一组","leader":"pm_zhang","members":["labeler_01","reviewer_01"]}'

# 注册标注员
curl -X POST http://localhost:8765/api/crowd/workers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"标注员小王","skills":["image","text"]}'
```

### 6. 验证系统健康

```bash
# 检查健康状态
curl http://localhost:8765/api/v1/health/ready

# 查看鲁棒性统计
curl http://localhost:8765/api/v1/robustness/stats

# 运行健康检查脚本
python scripts/health_check.py
```

### 7. 配置自动备份

```bash
# 手动备份
python scripts/backup.py

# 查看备份列表
python scripts/backup.py --list

# 备份文件位于: data/backups/imdf_backup_YYYYMMDD_HHMMSS.tar.gz
```

---

## 标注员日常工作流

### 1. 登录系统

```bash
# 使用分配好的账号登录
curl -X POST http://localhost:8765/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"labeler_01","password":"WorkerPass123"}'

# 保存返回的 access_token
export TOKEN="eyJ..."
```

### 2. 查看分配的任务

```bash
# 通过Web界面访问: http://localhost:8765/
# 或通过API查看需求列表
curl http://localhost:8765/api/requirements/ \
  -H "Authorization: Bearer $TOKEN"
```

### 3. 执行数据标注

#### 图像标注
1. 在Web界面的无限画布上加载图像
2. 使用标注工具绘制边界框
3. 填写标签名称和属性
4. 提交标注结果

#### 文本标注
1. 加载文本数据到画布
2. 选中需要标注的文本片段
3. 选择标注类型(实体/关系/情感等)
4. 保存标注

#### 音频标注
1. 上传音频文件
2. 使用音频标注工具标记时间段
3. 填写转录文本
4. 提交标注

### 4. 提交标注结果

```bash
# 提交完成的任务
curl -X POST http://localhost:8765/api/crowd/assign \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"task_001","required_skills":["image"]}'
```

### 5. 处理打回的标注

```bash
# 查看被审核员打回的任务
# 打回的任务会在任务列表中标记为 "rejected"
# 标注员需要根据审核意见修正后重新提交
```

### 6. 日常检查

- 每天查看分配的新任务
- 检查自己的标注质量统计
- 查看金标准测试结果

```bash
# 查看质检报告
curl http://localhost:8765/api/crowd/quality-report/labeler_01 \
  -H "Authorization: Bearer $TOKEN"
```

---

## 审核员审核流程

### 1. 登录

审核员使用自己的账号登录 (role: reviewer 或 admin)。

### 2. 查看待审核队列

```bash
# 查看待审核列表
curl http://localhost:8765/api/review/ \
  -H "Authorization: Bearer $TOKEN"

# 查看交付待审核
curl http://localhost:8765/api/delivery/review \
  -H "Authorization: Bearer $TOKEN"
```

### 3. 审核标注结果

审核员需要在Web界面或通过API审核每一条标注:

**审核操作:**
- **通过 (approved)**: 标注质量合格
- **打回 (rejected)**: 标注需要修正,附带修改意见
- **标记为金标准**: 质量特别好的标注可以作为金标准

```bash
# 提交审核结果
curl -X POST http://localhost:8765/api/delivery/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_id": "d_abc123",
    "reviewer": "reviewer_01",
    "verdict": "approved"
  }'
```

### 4. 金标准检测

审核员可以创建金标准条目用于检测标注员质量:

```bash
# 创建金标准
curl -X POST http://localhost:8765/api/crowd/golden-check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "golden_id": "golden_img_001",
    "correct_answer": "cat",
    "field_name": "label",
    "action": "create"
  }'

# 检查标注员的金标准准确率
curl -X POST http://localhost:8765/api/crowd/golden-check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "golden_id": "golden_img_001",
    "worker_id": "labeler_01",
    "worker_answer": "cat",
    "action": "check"
  }'
```

### 5. 多数表决

当多个标注员标注同一数据时,使用多数表决确定最终结果:

```bash
# 投票
curl -X POST http://localhost:8765/api/crowd/majority-vote \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_123",
    "worker_id": "labeler_01",
    "answer": "cat",
    "action": "vote"
  }'

# 查看表决结果
curl -X POST http://localhost:8765/api/crowd/majority-vote \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_123",
    "min_voters": 2,
    "action": "result"
  }'
```

### 6. 设置质检系数

审核员可以调整标注员的质检系数:

```bash
curl -X POST http://localhost:8765/api/crowd/quality-coefficient \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"worker_id":"labeler_01","coefficient":0.95}'
```

---

## 项目经理查看统计

### 1. 日常统计

```bash
curl http://localhost:8765/api/stats/daily \
  -H "Authorization: Bearer $TOKEN"
```

**返回内容:**
- 今日新增数据量
- 今日标注完成数
- 今日审核通过率
- 在线标注员数量
- 各项目进度

### 2. 周报/月报

```bash
# 周报
curl http://localhost:8765/api/stats/weekly \
  -H "Authorization: Bearer $TOKEN"

# 月报
curl http://localhost:8765/api/stats/monthly \
  -H "Authorization: Bearer $TOKEN"

# 周期对比
curl http://localhost:8765/api/stats/compare \
  -H "Authorization: Bearer $TOKEN"
```

### 3. 团队绩效

```bash
# 查看团队列表
curl http://localhost:8765/api/crowd/teams \
  -H "Authorization: Bearer $TOKEN"

# 查看质量报告
curl http://localhost:8765/api/crowd/quality-report/worker_id \
  -H "Authorization: Bearer $TOKEN"
```

### 4. 运营看板

通过Web界面的运营看板可查看:
- 实时并发请求数和CPU/内存使用率
- 各标注员效率和准确率排行榜
- 项目完成进度甘特图
- 数据质量趋势图

```bash
# 鲁棒性统计
curl http://localhost:8765/api/v1/robustness/stats \
  -H "Authorization: Bearer $TOKEN"

# 健康指标汇总
curl http://localhost:8765/api/v1/health/metrics-summary \
  -H "Authorization: Bearer $TOKEN"
```

### 5. 备份管理

```bash
# 创建备份
python scripts/backup.py

# 列出备份
python scripts/backup.py --list

# 恢复备份
python scripts/restore.py data/backups/imdf_backup_20260615_120000.tar.gz
python scripts/restore.py backup.tar.gz --dry-run   # 预览
python scripts/restore.py backup.tar.gz --db-only    # 仅恢复DB
```

---

## 需求方查看进度

### 1. 提交需求

```bash
curl -X POST http://localhost:8765/api/requirements/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "图像分类数据集-动物识别",
    "type": "data_production",
    "priority": "high"
  }'
```

### 2. 查看需求状态

```bash
# 查看所有需求
curl http://localhost:8765/api/requirements/ \
  -H "Authorization: Bearer $TOKEN"
```

需求状态流转:
```
created → assigned → in_progress → verified → closed
  ↓         ↓           ↓            ↓
rejected ← (可打回到任意阶段)
```

### 3. 查看交付物

```bash
# 查看交付列表
curl http://localhost:8765/api/delivery/ \
  -H "Authorization: Bearer $TOKEN"

# 创建交付
curl -X POST http://localhost:8765/api/delivery/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataset_version":"1.0","requester":"requester_01"}'

# 提交审核
curl -X POST http://localhost:8765/api/delivery/submit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"delivery_id":"d_abc123","content":"数据集已就绪"}'
```

### 4. 数据导出

需求方可以对已审批的数据进行导出:

```bash
# 查看备份/导出列表
curl http://localhost:8765/api/v1/backup \
  -H "Authorization: Bearer $TOKEN"

# 下载备份 (需知道backup_id)
curl http://localhost:8765/api/v1/backup/{backup_id}/download \
  -H "Authorization: Bearer $TOKEN" \
  -o dataset_export.tar.gz
```

### 5. 查看统计报表

```bash
# 查看个人相关统计
curl http://localhost:8765/api/stats/daily \
  -H "Authorization: Bearer $TOKEN"
```

---

## API 参考

### 认证

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册新用户 |
| POST | `/auth/login` | 登录获取JWT |
| GET | `/auth/me` | 获取当前用户信息 |
| PUT | `/auth/password` | 修改密码 |
| POST | `/auth/refresh` | 刷新Token |

### API密钥

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/api-keys/create` | 创建API Key |
| GET | `/api/v1/api-keys` | 列出我的Key |
| DELETE | `/api/v1/api-keys/{id}` | 吊销Key |

### 数据导入

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/ingest/csv` | 导入CSV |
| POST | `/api/v1/ingest/json` | 导入JSON |
| POST | `/api/v1/ingest/excel` | 导入Excel |
| POST | `/api/v1/ingest/import` | 文件导入 |
| GET | `/api/v1/ingest/history` | 导入历史 |

### 需求管理

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/requirements/create` | 创建需求 |
| POST | `/api/requirements/assign` | 分配需求 |
| POST | `/api/requirements/verify` | 验证需求 |
| POST | `/api/requirements/close` | 关闭需求 |
| GET | `/api/requirements/` | 需求列表 |

### 审核

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/review/submit` | 提交审核 |
| POST | `/api/review/pre_review` | 预审核 |
| POST | `/api/review/approve` | 审核通过 |
| POST | `/api/review/deploy` | 部署 |
| GET | `/api/review/` | 审核列表 |

### 统计

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/stats/daily` | 日报 |
| GET | `/api/stats/weekly` | 周报 |
| GET | `/api/stats/monthly` | 月报 |
| GET | `/api/stats/compare` | 周期对比 |

### 健康检查

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/health` | 基础健康 |
| GET | `/api/health/ready` | 就绪检查 |
| GET | `/api/health/live` | 存活检查 |
| GET | `/api/v1/robustness/stats` | 并发统计 |

---

## 故障排查

### 服务无法启动

```bash
# 检查端口占用
lsof -i :8765

# 检查日志
tail -f logs/error.log
tail -f logs/access.log

# 运行健康检查
python scripts/health_check.py --retry 5
```

### 并发过高导致503

- 检查 `MAX_CONCURRENT_REQUESTS` 设置
- 增加 `UVICORN_WORKERS`
- 查看 `/api/v1/robustness/stats` 确认当前并发数

### 数据库问题

```bash
# 恢复备份
python scripts/restore.py data/backups/imdf_backup_latest.tar.gz

# 验证数据库
python -c "
import sqlite3
conn = sqlite3.connect('data/imdf.db')
print(conn.execute('PRAGMA integrity_check').fetchone())
"
```

### 日志轮转异常

```bash
# 验证日志轮转
python scripts/log_rotation_verify.py --check-production

# 运行完整测试
python scripts/log_rotation_verify.py
```
