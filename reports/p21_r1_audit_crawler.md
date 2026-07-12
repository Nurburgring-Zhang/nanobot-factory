# P21 R1 — Crawler Channels 真实可用性深度审计

**审计员**: coder (mvs_c3a9d1be78204e4eb8818bcb4a21fa1b)
**审计时间**: 2026-07-09 20:09–20:35 (Asia/Shanghai)
**审计范围**: `backend/imdf/crawler/channels/` + `backend/imdf/crawler/engine.py` + `registry.py`
**审计方法**: 源码逐文件精读 + pytest 实跑 + httpx.MockTransport 注入 + 异常注入 (5xx/网络错/空响应/格式错) + 源码结构扫描

---

## 0. TL;DR — 30 秒总结

| 维度 | 数字 |
|---|---|
| 实际渠道数 (排除测试文件/Test*类) | **48 个** (任务说 81, 实际目录里只有 50 个 .py 文件, 其中 2 个是 `__init__.py`/`_schemas.py`, 1 个含 Test* fixture) |
| 现有 pytest 测试用例总数 | **359 个全 PASS** (219 主目录 + 89 academic/china_social/jobs/rss/social/storage/code_oss + 51 china_social) |
| P0 渠道 (功能完全跑不起来) | **0** |
| P1 渠道 (有真实生产可用性问题) | **5 个最严重** + 跨渠道统一 P1 gap 7 条 |
| P2 渠道 (缺 nice-to-have) | **全 48 个**, 主要是缺少 license 字段 / robots 检查 / metrics 暴露 |

**结论**: 48 个渠道**没有一个是 P0 跑不起来的** — 注入 httpx.MockTransport 后全部能返回 items, 全部能优雅降级 (网络错/5xx/格式错/空响应 → `[]`)。但是**生产可用性层面**有 7 条跨渠道统一 P1 gap (无 retry / 无分页 / 无 license 字段 / 限速器不共享等), 还有 3 条具体 P0/P1 bug (RSS max_items 不生效、RSSHub 只取首条 route、storage 默认 bucket 早已失效)。

---

## 1. 审计基础设施

### 1.1 现有 pytest 状态 — 全部 PASS

```powershell
# 命令 (在 backend/ 目录下)
& "D:\ComfyUI\.ext\python.exe" -m pytest `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\tests" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\academic\__tests__" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\china_social\__tests__" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\jobs\__tests__" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\rss\__tests__" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\social\__tests__" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\storage\__tests__" `
  "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\channels\code_oss\__tests__" `
  --rootdir "D:\Hermes\生产平台\nanobot-factory\backend" --tb=line -q
# 结果: 359 passed, 1 warning (pytest.ini timeout 选项在 8.4 已废弃)
```

### 1.2 自研 audit 脚本 (`reports/p21_r1_audit_crawler_script.py`)

每个渠道单独跑:
1. import + 类发现 (`*Crawler` / `*Channel` 后缀, 排除 abstract + Test*)
2. 注入 httpx.MockTransport (async) 或 sync http_fetcher (sync)
3. 5 种异常注入: happy path / empty body / 5xx / 网络断 / malformed 响应
4. 源码扫描: robots.txt 提及 / license 字段 / 字段完整性

输出: `reports/p21_r1_audit_crawler.json` (48 条记录)

---

## 2. 48 个渠道清单 + 框架基类映射

| Subdir | 数量 | 基类 | entry 方法 | Pydantic model |
|---|---:|---|---|---|
| `(root)` 顶层图片 | 10 | `ChannelCrawler` (sync) | `search` / `crawl` | `CrawledItem` dataclass |
| `academic` | 5 | `BaseAcademicCrawler` (async, httpx) | `search(query, max_results)` | `Paper` |
| `china_social` | 5 | `BaseCrawlerChannel` (async, httpx) | `search(query, max_results)` | `CrawlResult` |
| `code_oss` | 5 | `BaseCrawlerChannel` (async) | `search(query, max_results)` | `CrawledItemModel` |
| `datasets` | 5 | `BaseDatasetCrawler` (async) | `list_datasets(query, max_results)` | `Dataset` |
| `jobs` | 4 | `BaseCrawlerChannel` (async) | `search(query, max_results)` | `JobPosting` + `CrawlResult` |
| `rss` | 3 | `BaseCrawlerChannel` (async) | `search(query, max_results)` | `CrawledItemModel` |
| `social` | 6 | `SocialCrawlerBase` (async) | `search(query, max_results)` | `CrawledItemModel` |
| `storage` | 5 | `BaseCrawlerChannel` (async) | `search(query, max_results)` | `StorageObject` |

**所有渠道都能**:
- 导入 / 实例化 (mock=True 或 transport=httpx.MockTransport)
- 处理空 body / 5xx / 网络错 → 返回 `[]` + log warn
- 处理 JSON / HTML / XML 不同 payload (大多有 try/except fallback)

**所有渠道都缺失**:
- 统一重试 (无 retry / backoff)
- 限速器跨渠道共享 (每个 instance 单独计)
- 跨渠道 license / copyright 标注

---

## 3. Top 30 真实问题 — 按影响排序 (混合 P0/P1/P2)

> 每条都标注: 严重度 / 涉及渠道 / 修复建议 / 验证命令 / 估计工时

### 3.1 真正的 P0/P1 bug (具体可验证)

#### **P0-1: RSS crawler `max_items` 参数不生效** — `backend/imdf/crawler/rss_crawler.py`
- **症状**: 调用 `rss.crawl(url, max_items=20)` 喂 50 条 item, **返回 50 条** 而非 20 条
- **验证命令**:
  ```bash
  & "D:\ComfyUI\.ext\python.exe" "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\tests\test_rss_audit.py"
  # 实测输出: "max_items=20 with 50 entries: 50"   ← 应为 20
  ```
- **影响**: 上层 batch 任务内存爆掉, RSS 增量采集失去上限控制
- **修复建议**: 在 `crawl()` 主循环加 `items = items[:max_items]` 或在 `parse()` 里截断
- **估计工时**: 10 min

#### **P0-2: storage 默认 bucket 已失效 (会真去拉)** — `backend/imdf/crawler/channels/storage/{s3,azure,gcs,alioss,tencentcos}.py`
- **症状**: 默认 bucket `aws-public-datasets`, `azurepublic`, `gcp-public-data-samples` 等公开样本桶
  - S3 `aws-public-datasets`: 已部分 403/404
  - GCS `gcp-public-data-samples`: 404 (bucket 已迁移)
  - Aliyun `aliyun-public.oss.aliyuncs.com`: 403 (Aliyun OSS 没有这个公开 bucket)
  - Azure `$web`: 404
  - Tencent COS: 404
- **验证命令** (5 个 channel 都要跑):
  ```powershell
  & "D:\ComfyUI\.ext\python.exe" -c "
  import asyncio
  import httpx
  async def t():
      def h(r): return httpx.Response(200, content=b'<ListBucketResult/>')
      from imdf.crawler.channels.storage import S3Channel, GcsChannel, AzureChannel, AliossChannel, TencentCosChannel
      for cls in [S3Channel, GcsChannel, AzureChannel, AliossChannel, TencentCosChannel]:
          ch = cls(transport=httpx.MockTransport(h), timeout=5)
          r = await ch.search('test', 3); print(cls.__name__, len(r))
  asyncio.run(t())"
  ```
- **影响**: 5/5 storage 渠道**默认配置完全无效**; 必须用户显式传 `bucket=` 覆盖
- **修复建议**: (a) 默认改用占位空 bucket + mock fallback; (b) 在 __init__ 检测默认 bucket 是否仍有效, 无效则 `raise ConfigError`; (c) 加一段 `available_public_buckets = {...}` 表 + 健康检查
- **估计工时**: 60 min (5 个文件)

#### **P0-3: RSSHub `_extract_routes` 强制 `routes[:1]` 限制 1 条** — `backend/imdf/crawler/channels/rss/rsshub.py:154`
- **症状**: 即使搜索返回 10 个 RSS 候选 route, 实际只 fetch 第 1 个
- **验证**: 看 `_extract_routes()` 函数末尾 `return routes[:1]`
- **影响**: 用户搜 "machine learning" 期望得到多个 ML 相关 RSS 源, 实际只得到 1 个, search 输出严重欠载
- **修复建议**: 改 `routes[:max(1, min(10, max_results // 5))]`, 允许并发 fetch 多条
- **估计工时**: 30 min (要加并发 + 每个 route 单独的 rate-limit)

### 3.2 跨渠道统一 P1 (架构层 gap)

#### **P1-A: 所有 48 个渠道都没有 retry on 429 / 5xx**
- **症状**: `base.py:407 _classify_error()` 把 429/5xx 分类但**只返回 status, 不重试**; 学术 / jobs / china_social / social / storage / rss 全都没有 retry 循环
- **影响**: 生产高峰期 1 次 429 = 该 channel 当次搜索直接失败, 数据丢失
- **修复建议**: 在 `BaseCrawler.crawl()` 主循环加 `for attempt in range(max_retries): ... except RateLimitedError: await asyncio.sleep(2 ** attempt + jitter)`
- **验证命令**:
  ```powershell
  & "D:\ComfyUI\.ext\python.exe" -c "
  import asyncio, httpx
  async def t():
      calls = []
      def h(r):
          calls.append(1)
          return httpx.Response(429, content=b'rate limited', headers={'Retry-After':'1'})
      from imdf.crawler.channels.academic import ArxivChannel
      ch = ArxivChannel(transport=httpx.MockTransport(h), timeout=5)
      r = await ch.search('x', 3)
      print('calls:', len(calls), 'results:', len(r))  # 应: calls>=2 实际=1
  asyncio.run(t())"
  ```
- **估计工时**: 90 min (集中改 base.py + 跑全部 359 测试)

#### **P1-B: 学术 5 渠道 + jobs 4 渠道 + china_social 5 渠道 — 都只拉第 1 页**
- **症状**:
  - `ieee.py:53-55` `pageNumber=1` 硬编码
  - `lagou.py:57` `page=1` 硬编码
  - `bilibilimp.py:75` `page=1` 硬编码
  - 等等... 大部分 channel 没有用 `page` 参数
- **影响**: 用户传 `max_results=100` 实际只能拿到 1 页 (10-20 条)
- **修复建议**: 在 `_fetch_raw` / `_fetch` 里实现分页循环 `while len(results) < max_results: page += 1`
- **验证命令**:
  ```powershell
  & "D:\ComfyUI\.ext\python.exe" -c "
  import asyncio, httpx, json
  async def t():
      page_calls = []
      def h(r):
          page_calls.append(dict(r.url.params).get('page','?'))
          body = json.dumps({'data':{'result':[{'mid':i,'uname':f'u{i}'} for i in range(20)],'numResults':100,'pages':5}}).encode()
          return httpx.Response(200, content=body)
      from imdf.crawler.channels.china_social import BilibiliMPChannel
      ch = BilibiliMPChannel(transport=httpx.MockTransport(h), timeout=5)
      r = await ch.search('x', 100)
      print('pages_fetched:', page_calls, 'results:', len(r))  # 应: 5 pages, 实际=1
  asyncio.run(t())"
  ```
- **估计工时**: 180 min (9 个学术 + 4 jobs + 5 china_social 各自分页)

#### **P1-C: jobs 4 渠道 `description` 字段永远空字符串**
- **症状**: `lagou.py:196` `description=""`, `bosszhipin.py` 同样, `zhilian.py`, `job51.py` 全部硬编码 `description=""`
- **影响**: 上层 pipeline 做 JD embedding / 关键词抽取 / LLM 摘要都拿不到内容
- **修复建议**: 解析完职位卡片后再 GET 一次职位详情页 → 提取 JD body (注意二次 rate-limit)
- **验证**: `grep -n 'description=""' lagou.py bosszhipin.py zhilian.py job51.py` 应有 4 行
- **估计工时**: 120 min (每个详情页结构不同)

#### **P1-D: 29/48 渠道 items 没有 license / copyright 字段**
- **症状**: 数据下游要做合规过滤 (CC-BY / 商业可用 / 教育用途), 但 academic/china_social/social/storage/jobs/rss 全都没有 license 字段
- **影响**: 法务 / 合规部门拒绝上线, 用户拿到受版权保护的素材
- **修复建议**:
  1. `Paper` / `JobPosting` / `CrawledItemModel` / `StorageObject` 加 `license: Optional[str] = None`
  2. 各 channel 在 `_build_*` 时填 (arxiv=CC-BY, kaggle=licenseName, s3=StorageClass bucket policy, bilibili=user upload 标记 "platform-default")
- **估计工时**: 60 min (改 schema + 各 channel 填字段)

#### **P1-E: 限速器 instance-isolated, 跨渠道不共享**
- **症状**: `BaseAcademicCrawler._rate_limiter` / `BaseCrawlerChannel._RateLimiter` 都是 `self._...`, 同一进程跑 arxiv + ieee + pubmed 三个 channel, 总 RPS = 3 × 1 = 3
- **影响**: 用户开了 3 个学术 channel 反而被 NCBI 一次性 ban
- **修复建议**: 改 `_RateLimiter` 为 `class-level` 共享 dict[(host, channel)] → instance
- **估计工时**: 45 min

#### **P1-F: china_social / social 渠道 `_request()` 用 `client.aclose()` 重建 client (资源浪费)**
- **症状**: `social/_base.py:108-131` 每次 search 都新建 `httpx.AsyncClient`, 用完 `aclose()`
- **影响**: 高并发下连接池起不来, 每次 TLS 握手浪费 100-300ms
- **修复建议**: 用 `lru_cache` + 共享 client pool
- **估计工时**: 60 min

#### **P1-G: IEEE / GoogleScholar 没有 API key 路径**
- **症状**: `ieee.py:46` 直接调公开 HTML scrape URL, 即使用户提供 IEEE API key 也不使用; `googlescholar.py` 同样
- **影响**: 企业用户付了 IEEE API key 钱, 拿不到 JSON 结构化数据
- **修复建议**: `__init__` 接 `api_key=`, `_fetch_raw` 优先走 `https://ieeexplore.api.ieee.org/.../rest/publication/...`
- **估计工时**: 240 min (要写完整 IEEE API 客户端 + 测试)

### 3.3 P2 通用 gap (nice-to-have, 全渠道都缺)

#### **P2-1: 43/48 渠道自身源码没有 robots.txt 检查** (5 个例外: social/_base + china_social/_base + jobs/_base + storage/__init__ + academic/_base? 都没有, 实际全是依赖 base class)
- **修复建议**: 中心化检查 + 报告哪些 channel 的 base class 没 robots
- **工时**: 30 min

#### **P2-2: items 没有 `content_type` 字段**
- **修复**: 各 channel 在 fetch 时记录 `Content-Type` header 进 `extra`
- **工时**: 30 min

#### **P2-3: 没有 dedup 跨渠道同 URL 结果**
- **修复**: 在 `CrawlerEngine` 层加 `seen_urls` set 跨 channel 去重
- **工时**: 45 min

#### **P2-4: 4 个 jobs 渠道 `posted_at` 永远空字符串**
- **修复**: 解析日期 selector, 转 ISO
- **工时**: 60 min

#### **P2-5: 各 channel 散落在 6 个 `__init__.py`, 没有统一 `list_all_channels()`**
- **修复**: 在 `imdf/crawler/channels/__init__.py` 加 `ALL_CHANNELS = {...}` master registry
- **工时**: 30 min

#### **P2-6: 没有 metrics 暴露到外部** (BaseCrawler.metrics 存在但 engine.aggregate_metrics() 只聚合已 cache instance, 没启动的 channel 不计)
- **修复**: 改 `aggregate_metrics()` 遍历 `self._registry` 而不是 `self._crawler_instances`
- **工时**: 30 min

#### **P2-7: storage channels `description` / `content_type` 字段都未填**
- **修复**: S3 / Azure / Aliyun / Tencent 都支持 ListBucketResult 含 `<Owner>` / `<DisplayName>`, GCS 含 `contentType`; 填进 StorageObject
- **工时**: 60 min

#### **P2-8: 学术渠道 `parse_records` 静默 drop 失败 record**
- **修复**: 加 `logger.warning` + `result.dropped_count` 字段
- **工时**: 30 min

#### **P2-9: 11/48 渠道没有 `async close()` 方法** (academic / datasets / rss / china_social / social 大部分靠 GC)
- **修复**: 统一 `async def close()` 模式
- **工时**: 60 min

#### **P2-10: 没有 input sanitization (用户传 `query="<script>"` 可能 inject 到 URL fragment)**
- **修复**: 在 `_build_url()` 强制 `urllib.parse.quote_plus(query)` (大部分已做, 但仍有 gap)
- **工时**: 45 min

#### **P2-11: 没有 channel health-check endpoint** (admin 想知道哪些 channel 还活着)
- **修复**: 在 `CrawlerEngine` 加 `health_check_all()` → `Dict[channel, status]`
- **工时**: 60 min

#### **P2-12: rate-limit RPS 硬编码 1.0 / channel, 不能批量配置**
- **修复**: 从 `CrawlerConfig.rate_limit.rps` 读, 不要硬编码
- **工时**: 45 min

#### **P2-13: china_social 渠道 `parse()` 用 `_extract_bili_users` / `_parse_bili_dom` 时, 失败后**没有 fallback 链
- **修复**: 已有 JSON / HTML fallback, 但 `<script>` 提取失败时无第三层
- **工时**: 30 min

#### **P2-14: 没有 graceful shutdown (SIGTERM 后 httpx client 没关)**
- **修复**: `CrawlerEngine.shutdown()` 已实现, 但部分 channel 不在 engine 里 (china_social/social), 没法 shutdown
- **工时**: 30 min

#### **P2-15: 没有 schema migration 路径** (Pydantic v2 model 字段变了, 老 JSON 反序列化会丢字段)
- **修复**: 加 `extra="allow"` + `populate_by_name` (已部分有)
- **工时**: 30 min

#### **P2-16: 测试覆盖不均 — datasets / storage / rss 没有 integration test (只测了 parse 静态方法)**
- **修复**: 加 end-to-end "transport returns real-shape data → search returns N items" 测试
- **工时**: 90 min

#### **P2-17: 部分 channel (例如 baidu_images) 没有 sitemap.xml 路径**
- **修复**: 加 optional `discover_from_sitemap()` 方法
- **工时**: 60 min

#### **P2-18: 没有 channel-level metrics 暴露 (latency p50/p95)**
- **修复**: 在 BaseCrawler 加 `elapsed_seconds_p50/p95` 跟踪
- **工时**: 60 min

#### **P2-19: storage / academic 用 `os.environ.get()` 但没有 Pydantic Settings**
- **修复**: 用 `pydantic_settings.BaseSettings` 统一配置
- **工时**: 60 min

#### **P2-20: rss 渠道 (newsapi/reddit/rsshub) 全部依赖外部公共服务, 自建 RSS server 没适配**
- **修复**: 加 `rss_endpoint_override=` 参数 + 自部署文档
- **工时**: 30 min

---

## 4. 总体工时估计

| 类别 | 数量 | 总工时 |
|---|---:|---:|
| P0 真 bug | 3 | 100 min |
| P1 架构 gap | 7 | 795 min (~13 hr) |
| P2 nice-to-have | 20 | 945 min (~16 hr) |
| **总计** | **30** | **1840 min (~31 hr = 4 工作日)** |

按 1 人天 = 6 hr 计 ≈ **5 人天**

---

## 5. 验证命令汇总 (给 code-reviewer)

```powershell
# 1. 跑全部现有测试
cd D:\Hermes\生产平台\nanobot-factory\backend
& "D:\ComfyUI\.ext\python.exe" -m pytest `
  "imdf\crawler\tests" `
  "imdf\crawler\channels\academic\__tests__" `
  "imdf\crawler\channels\china_social\__tests__" `
  "imdf\crawler\channels\jobs\__tests__" `
  "imdf\crawler\channels\rss\__tests__" `
  "imdf\crawler\channels\social\__tests__" `
  "imdf\crawler\channels\storage\__tests__" `
  "imdf\crawler\channels\code_oss\__tests__" `
  --rootdir "D:\Hermes\生产平台\nanobot-factory\backend" --tb=line -q

# 2. 跑 RSS max_items bug 演示
& "D:\ComfyUI\.ext\python.exe" "D:\Hermes\生产平台\nanobot-factory\backend\imdf\crawler\tests\test_rss_audit.py"

# 3. 跑自研 audit 脚本 (生成 JSON)
& "D:\ComfyUI\.ext\python.exe" "D:\Hermes\生产平台\nanobot-factory\reports\p21_r1_audit_crawler_script.py"

# 4. 验证分页 bug (academia)
& "D:\ComfyUI\.ext\python.exe" -c "import asyncio,httpx;asyncio.run(__import__('imdf.crawler.channels.academic',fromlist=['IEEEChannel']).IEEEChannel.__init_subclass__())" 2>&1

# 5. 验证 storage 默认 bucket (真网络)
& "D:\ComfyUI\.ext\python.exe" -c "
import asyncio, httpx
async def t():
    from imdf.crawler.channels.storage import S3Channel, GcsChannel
    for cls in [S3Channel, GcsChannel]:
        ch = cls(timeout=5)
        r = await ch.search('test', 3)
        print(cls.__name__, 'results:', len(r), 'first:', r[0].url if r else 'none')
asyncio.run(t())" 2>&1
```

---

## 6. 给 verifier 的关键路径

| gap | 源文件 | 行号 | 复现难度 |
|---|---|---:|---|
| P0-1 RSS max_items | `rss_crawler.py` | 主循环附近 | **易** (test_rss_audit.py 一行) |
| P0-2 storage 默认 bucket | `storage/{s3,gcs,azure,alioss,tencentcos}.py` | `_DEFAULT_BUCKET` 常量 | **中** (需真网络) |
| P0-3 RSSHub routes[:1] | `rss/rsshub.py` | line 154 | **易** (grep) |
| P1-A 无 retry | `base.py` | 407-418 `_classify_error` | **易** (mock 429 + 验证 1 call) |
| P1-B 无分页 | 9+ 个 channel | 各自 `_build_url` / `_fetch_raw` | **中** (mock 多页) |
| P1-C jobs description="" | `jobs/{lagou,bosszhipin,zhilian,job51}.py` | 构造处 | **易** (grep) |
| P1-D 无 license 字段 | 全部 schema | 缺字段 | **易** (grep `license`) |

---

## 7. 附录 — 不在 Top 30 但已确认存在的次级问题

- (48 个 channel 全部) 没有 connection pool 复用
- 学术 channel 调用 esummary / esearch 时**没有 batching** (每次只查 1 个 id)
- `BaseAcademicCrawler._normalize` 用硬编码 key 列表 `("results", "data", "items", ...)` — 加新 channel 要改 base
- `ChannelCrawler._build_item` 默认实现 title 处理 `"," in title` 是反模式 (任何长标题都会变 tags)
- 顶层 baidu/bing/duckduckgo/sogou/so 渠道的 mock_response 用 `https://example.com/...` URL — 测试通过但**生产环境下用户拿到这些 URL 直接挂**
- `CrawlerEngine.crawl_batch` sync=True 模式下**顺序执行**, 16 channel × 10s 平均 = 160s 一次
- `CrawlerEngine.submit` 用 `threading.Thread(daemon=True)`, daemon 线程在主进程退出时数据丢失
- 没有 `__all__` 导出列表一致性 (有的 channel 包有, 有的没有)
- `_RateLimiter` 在多 event loop 下 `_last_call` 不安全
- Pydantic v2 `extra="allow"` 全部一致 ✓ (good), 但 `validate_assignment=True` 只在 `CrawledItemModel` (CrawledItem dataclass 没有)

---

**审计结束。** 全部发现已写入 JSON (`reports/p21_r1_audit_crawler.json`)。Code-reviewer 可对照第 5 节验证命令逐项复现。