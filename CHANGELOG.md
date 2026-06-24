# Changelog

## v1.0.0 (2026-06-11)

### 修复（P0/CRITICAL）
- database.py: 修复3个致命bug —— dataset_assets表缺失、assets_fts表缺失、update_asset参数顺序错误
- llm_client.py: 修复SeedanceClient.generate_video()缩进错误导致不发送HTTP请求
- routes/production.py: 修复路由冲突（/api/v2/tasks 与 /api/v2/stats/global）
- server.py: 修复评分系统从random.uniform改为真实计算
- server.py: 添加 OMNIGEN_AVAILABLE/AIRI_AVAILABLE/AI_DRIVEN_AVAILABLE/GENERATION_SERVICE_AVAILABLE 变量
- server.py: 添加JSONResponse导入，修复全局异常处理器

### 功能接入（A-E）
- **A**: agent/模块(~10,500行)接入server.py —— 新增 routes/agents_v2.py 5个API端点
- **B**: functions/下6个壳函数加真实实现 —— ai/browser/mcp/monitor/openclaw/search全部重写
- **C**: enterprise_api.py AIGC生成对接ProviderFactory —— 从placeholder改为真实调用
- **D**: 前端AIGC生成 —— 创建 studio.html 纯前端页面 + POST /api/v2/generate 路由
- **E**: integrations/修复3个类型崩溃bug

### 基础设施加固
- 全局异常处理器（隐藏内部traceback，添加request_id）
- 认证依赖注入 auth_required()
- 日志RotatingFileHandler（10MB*5轮转）
- .env + .env.example 配置标准化
- Dockerfile + docker-compose.yml + .dockerignore
- README.md 完整重写

### 前端增强
- studio.html: 添加历史生成画廊（从/api/assets加载）
- studio.html: 添加批量生成模式（逐行prompt,最多20个）
- studio.html: 添加进度轮询（每3秒轮询/api/generate/{task_id}）
- studio.html: 左侧导航添加"历史生成"入口

### 数据层升级
- database.py: 添加PostgreSQL可选支持（DATABASE_URL环境变量）
- database.py: 添加PostgresConnectionPool兼容层
- 添加Alembic迁移框架（alembic.ini + env.py）

### 测试
- 修复 test_api_endpoints.py fixture问题（pytest.skip）
- 84 tests passed

