# IMDF 商用化完整规划方案 v2.0

## 三Agent互审互查监督 — 最终产出

---

## 第一阶段: 架构重塑(P0-基础设施) — 20个实施项

### 约束条件
- ❌ 无Docker
- ❌ 无PostgreSQL(但有psycopg2包)
- ❌ 无Redis(但有redis-py包)
- ✅ 有SQLite + SQLAlchemy + APScheduler

### 实施方案（非Docker方案）

#### P0-1: 数据库从SQLite升级到支持并发的方案
**方案**: 保留SQLite，但改用**SQLAlchemy ORM + WAL模式 + 连接池**方案
- 使用SQLAlchemy统一数据库接口(当前是aiosqlite裸查)
- SQLite启用WAL模式(journal_mode=WAL) + busy_timeout=10000
- 创建连接池(最多10个连接,信号量控制并发)
- 后续迁移到PostgreSQL只需改DATABASE_URL
- 已有依赖: SQLAlchemy 2.0.23, aiosqlite已安装

#### P0-2: 任务队列(无Celery/Redis方案)
**方案**: **APScheduler + SQLite持久化**
- AsyncIOScheduler + SQLiteJobStore实现持久化队列
- 所有耗时操作(导出/生成/清洗)推入队列
- worker从SQLite顺序消费
- 支持: 延迟执行/定时执行/重试(最多3次)+指数退避
- 已有依赖: APScheduler已安装, SQLite已存在

#### P0-3: API版本控制
**方案**: 所有路由加/api/v1/前缀
- `app.include_router(xxx_router, prefix="/api/v1")` 
- 旧路由保留作为向后兼容
- OpenAPI分版本显示

#### P0-4: 限流
**方案**: slowapi(内存模式) + 自定义IP/用户限流
- `@limiter.limit("100/minute")`装饰器
- 不需要Redis

#### P0-5: 结构化日志
**方案**: structlog + JSON格式 + 请求ID链路
- 中间件: 每个请求分配uuid request_id
- structlog配置: JSON处理器 + 时间戳 + request_id绑定

#### P0-6: 健康检查
**方案**: FastAPI原生`/health` + `/ready`端点
- `/health`: 返回200 + 组件状态
- `/ready`: 执行SQLite查询验证 + 磁盘空间检查 + ffmpeg可用性

#### P0-7: 密码加固
**方案**: argon2-cffi替代sha256
- 已有依赖: argon2-cffi已安装(25.1.0)
- register/login路由从hashlib切到argon2

#### P0-8: AI预标注(无GPU方案)
**方案**: DeepSeek API做预标注
- 已有: DeepSeek API key, nanobot_adapter已实现
- 新增: 预标注路由 POST /api/v1/prelabel
- 支持: BBox检测/分类/标签推荐

#### P0-9: 前段数据浏览器
**方案**: 内联HTML+AG Grid(社区版)集成到现有画布
- 不拆前端代码库,在当前HTML_TEMPLATE中新增tab
- AG Grid + 分页API
- 支持: 过滤/排序/搜索/预览

#### P0-10: 标注一致性评分
**方案**: sklearn.cohen_kappa_score + IoU计算
- 已有依赖: scikit-learn已安装
- 新增: 一致性评分引擎 + 看板展示

#### P0-11: 质量断言框架
**方案**: 自定义断言引擎(对标Great Expectations轻量版)
- Expectation类: 列约束/行约束/表约束
- ExpectationSuite: 断言集合
- Validation结果JSON输出 + 通过率/%展示

#### P0-12: 审计日志
**方案**: FastAPI中间件 + 独立audit_log表(SQLite)
- 所有写操作记录: 谁/什么时间/做了什么/数据变更前后
- 不可修改(追加写,无UPDATE/DELETE)
- 支持按时间/用户/操作类型查询

#### P0-13: 搜索/过滤/排序
**方案**: SQLite FTS5全文搜索 + 前端筛选面板
- 数据集搜索: FTS5虚拟表
- 标注搜索: 跨字段搜索

#### P0-14: 增量交付
**方案**: 版本差分算法 + 增量包生成
- 比较新旧版本的文件列表差异
- 只打包新增/修改的文件

#### P0-15: 运营看板
**方案**: 新增/ops/dashboard端点 + 前端图表
- 日活/生产量/交付量/质量趋势
- 团队效率排行
- 管道状态总览

#### P0-16: 优雅关闭
**方案**: FastAPI lifespan + signal处理
- SIGTERM/SIGINT时: 停止接受新请求→等待进行中任务完成→关闭数据库连接

#### P0-17: 实时管道监控
**方案**: APScheduler监控 + WebSocket推送
- 管道执行状态推送
- 失败报警

#### P0-18: 文件缩略图/预览
**方案**: Pillow缩略图 + ffmpeg视频首帧 + pdf2image

#### P0-19: 数据库迁移
**方案**: Alembic(已安装) + SQLAlchemy
- 已有依赖: alembic 1.13.0已安装

#### P0-20: 数据导入(标准格式)
**方案**: pandas + CSV/JSON/Excel导入端点

---

## 第二阶段: 节点化工作流引擎(P1, 实施顺序后移)

基于已产出的三层节点架构(docs/workflow_engine_v1.md)：
- 注册表: nodes/registry.py
- DAG执行引擎: nodes/engine.py
- 8维度 × 60能力 × N功能

---

## 实施顺序

### 第一阶段(当前会话)
1. 密码加固(argon2) — 最小改动,立即安全
2. 健康检查(/health /ready) — 无依赖,立即可用
3. 结构化日志(structlog) — 无依赖,后续全链路受益
4. 搜索/过滤(FTS5) — 用户体验关键
5. 标注一致性评分 — 业务核心
6. 质量断言框架 — 业务核心
7. 审计日志 — 安全基础
8. 任务队列(APScheduler) — 架构核心
9. API版本控制 — 架构核心
10. 限流(slowapi) — 架构核心

### 第二阶段(后续会话)
11. AI预标注
12. 前段数据浏览器
13. 运营看板
14. 文件预览
15. 增量交付
16. 数据导入
17. 优雅关闭
18. 实时监控
19. 数据库迁移(Alembic)
20. 节点化工作流引擎
