# 智影 V4 设计文档 — 智能数据采集 (Intelligence Data Acquisition)

> **版本**: v4.0 — 全 agent 驱动的全网深度多渠道数据检索 / 溯源 / 采集 / 处理平台
> **日期**: 2026-07-01
> **核心定位**: 用户只需说"我要什么、不要什么、要多少",系统全自动在 agent 驱动下完成 检索 → 溯源 → 爬虫 → 下载 → 清洗 → 打标 → 评分 → 分类 → 存储 的全流程
> **架构**: 多智能体协作 (Multi-Agent Collaboration) + 自然语言指挥 (NL Command)

---

## 第 1 章 总体架构

### 1.1 设计原则

1. **零配置启动** — 用户自然语言描述需求,系统自动解析并执行
2. **可观测全程** — 每一步进度实时可见,可暂停/恢复/取消
3. **可审计可回滚** — 所有操作记录到 audit chain,可回滚
4. **多智能体协作** — 不同任务由不同 Agent 接管,通过总线协作
5. **统一指挥** — 一个对话窗口命令所有平台功能
6. **主权可控** — 数据源 / 规则 / 限速 / 边界完全由用户定义

### 1.2 V4 完整架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      Agent 对话指挥中心 (Chat)                            │
│  - 自然语言输入 / 流式响应 / 历史会话 / 多 Agent 协作可视化             │
│  - Vue 3 ChatPanel.vue + WebSocket 流式                                  │
└──────────────────────────────────────────────────────────────────────────┘
                                  ↓ WebSocket / SSE
┌──────────────────────────────────────────────────────────────────────────┐
│                  Agent Commands (intelligence/agent_commands/)            │
│  - intent_classifier: 意图识别 (采集/标注/审核/项目/工作流/...)         │
│  - command_parser: NL → 结构化指令                                        │
│  - command_router: 路由到对应的 Agent                                     │
│  - session_manager: 会话状态 / 历史 / 上下文                              │
└──────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────────┐
│                     平台 Agent 集 (intelligence/platform_agents/)        │
│  - DataAcquisitionAgent (主)    - AnnotationAgent                          │
│  - ReviewAgent                   - WorkflowAgent                            │
│  - ProjectAgent                  - UserAgent                                │
│  - PipelineAgent                  - QualityAgent                             │
└──────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────────┐
│        DataAcquisition 主 Agent (intelligence/data_acquisition/)         │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 1. 需求解析 → 结构化任务 (Requirements Parser)                     │ │
│  │ 2. 多渠道分派 (Multi-Channel Dispatcher)                          │ │
│  │ 3. 数据采集 (Multi-Channel Crawler × N)                            │ │
│  │ 4. 深度溯源 (Deep Source Tracer)                                   │ │
│  │ 5. 自适应爬虫生成 (Auto Crawler Generator)                         │ │
│  │ 6. 批量下载 (Multi-Thread Downloader)                              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────────┐
│        多渠道爬虫框架 (intelligence/crawler/)                           │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐            │
│  │ WebCrawler  │ APICrawler   │ RssCrawler  │SocialCrawler│            │
│  │ (Playwright)│ (REST/gRPC)  │             │ (公开 API)   │            │
│  ├──────────────┼──────────────┼──────────────┼──────────────┤            │
│  │ FileCrawler  │ SearchEngine │ DeepCrawler│ DarkCrawler │            │
│  │ (S3/OSS)    │ (SerpAPI)    │ (递归)      │(学术/预印本)│            │
│  └──────────────┴──────────────┴──────────────┴──────────────┘            │
└──────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────────┐
│        数据处理流水线 (intelligence/processing/)                        │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐            │
│  │  Dedupe     │   Clean     │  AutoLabel  │  Scoring    │            │
│  │  (去重)     │   (清洗)     │  (自动打标) │  (评分)      │            │
│  │ hash+simhash│ 文本+图像   │ Foundation  │ 质量/审美/   │            │
│  │             │ +元数据     │ Model+规则  │ 自定义       │            │
│  └──────────────┴──────────────┴──────────────┴──────────────┘            │
│  ┌──────────────┬──────────────┐                                            │
│  │ Classify    │ Store        │                                            │
│  │ (分类)      │ (存储)        │                                            │
│  │ 8 业务模态  │ MinIO + OSS   │                                            │
│  └──────────────┴──────────────┘                                            │
└──────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────────┐
│                     数据交付 (Delivery)                                  │
│  - Dataset 包 (按项目 / 模态 / 评分 分类)                                │
│  - 完整 lineage (RELATION_GRAPH 14 边)                                   │
│  - 完整 metadata (采集时间 / 渠道 / 来源 / 处理链路)                      │
│  - 自动入库 (ORM + OSS + 索引)                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.3 核心数据流

```
用户: "我想要 100 万张高质量猫狗图片,不要有水印,只要 1024x1024 以上"

Agent Command Parser 解析:
{
  "intent": "data_acquisition",
  "target": "image",
  "category": ["cat", "dog"],
  "count": 1_000_000,
  "constraints": {
    "min_resolution": "1024x1024",
    "no_watermark": True,
    "quality_threshold": 0.7
  }
}

↓ 任务规划

DataAcquisitionAgent:
1. 渠道选择: [Google Images via SerpAPI, Open Images Dataset, 
              ImageNet subset, Flickr CC, Pixabay, Unsplash, 
              公开学术数据集, RSS feeds]
2. 溯源: 追溯到原始数据集 / 原始发布者 / License
3. 爬虫生成: 为每个渠道生成专用爬虫
4. 并行下载: 100 渠道 × 10000 张/批 = 100 万张
5. 处理: dedupe → clean → label (cat/dog) → quality score
6. 分类存储: 按质量分桶,入库

↓ 实时进度

Agent 实时回报:
- 已启动渠道: 12/12
- 已下载: 230,000 (23%)
- 速度: 1,200 张/分钟
- 去重后: 187,000 实际有效
- 质量分布: 高 65% / 中 25% / 低 10%
- 预计完成: 4.2 小时

↓ 最终交付

Dataset: 187,000 张 (实际有效, 全部 ≥1024x1024, 无水印, 已 cat/dog 标签)
完整 lineage + metadata
可一键导入智影其他模块 (标注 / 训练 / 评测)
```

---

## 第 2 章 多渠道爬虫框架

### 2.1 渠道总览

智影 V4 支持 **8 大类 50+ 渠道**:

| 类别 | 渠道数 | 示例 |
|---|---|---|
| **Web 爬虫** | 8 | Generic Playwright, Selenium, Scrapy, BeautifulSoup, Newspaper3k, Trafilatura, Curl_cffi, AIOHTTP |
| **公开 API** | 12 | Open Images, COCO, ImageNet, Flickr, Pixabay, Unsplash, Pexels, Wikipedia, Wikidata, arXiv, Semantic Scholar, GitHub |
| **搜索引擎** | 5 | SerpAPI, Google CSE, Bing Search, DuckDuckGo, Brave Search |
| **RSS / 订阅** | 6 | Generic RSS/Atom, YouTube Channels, Substack, Medium, WordPress, Hexo |
| **社交媒体 (公开)** | 6 | Reddit JSON, Twitter API v2, Mastodon, Lemmy, HackerNews, Dev.to |
| **文件 / OSS** | 4 | S3, GCS, Azure Blob, MinIO |
| **学术 / 预印本** | 5 | arXiv, PubMed, Semantic Scholar, OpenReview, PapersWithCode |
| **P2P / Dark** | 4 | IPFS, BitTorrent DHT, I2P (合规), 学术 FTP |

> **合规原则**: 默认所有渠道遵守 robots.txt / ToS / 速率限制;每个渠道有合规审查标记;操作员可配置"内部资产"白名单;所有活动全程审计。

### 2.2 8 渠道深度设计

#### 2.2.1 WebCrawler (Playwright 驱动)

```python
# intelligence/crawler/web_crawler.py
class WebCrawler:
    """
    通用 Web 爬虫 — Playwright 驱动
    
    能力:
    - JavaScript 渲染 (SPA 友好)
    - 无限滚动 (infinite scroll)
    - 反爬绕过 (指纹 / User-Agent / Proxy 轮换)
    - 智能等待 (waitFor API 触发)
    - 自动翻页
    - 多 tab 并行
    """
    
    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.playwright = None
        self.proxy_pool = ProxyPool(...)
        self.ua_pool = UserAgentPool(...)
        self.fingerprint_rotator = FingerprintRotator(...)
    
    async def crawl(self, seed_urls: List[str]) -> AsyncIterator[RawDocument]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless,
                proxy=self.proxy_pool.get_next()
            )
            for url in seed_urls:
                page = await browser.new_page(...)
                await page.goto(url, wait_until="networkidle")
                # 智能等待
                await page.wait_for_selector(...)
                # 内容提取
                content = await self._extract_content(page)
                yield content
```

#### 2.2.2 DeepCrawler (递归深爬)

```python
# intelligence/crawler/deep_crawler.py
class DeepCrawler:
    """
    递归深爬 — BFS/DFS + URL 去重 + 深度限制
    
    场景:
    - 学术网 (论文引用网络)
    - 电商网 (商品分类树)
    - 社交网 (用户关注)
    - 知识图谱 (Wikipedia 链接图)
    """
    
    def __init__(self, max_depth=3, max_pages=10000, same_domain=True):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.same_domain = same_domain
        self.visited = set()
        self.queue = asyncio.Queue()
    
    async def crawl(self, seed_url: str) -> AsyncIterator[Page]:
        await self.queue.put((seed_url, 0))
        async with self._worker_pool() as pool:
            while not self.queue.empty() and len(self.visited) < self.max_pages:
                url, depth = await self.queue.get()
                if url in self.visited or depth > self.max_depth:
                    continue
                self.visited.add(url)
                
                page = await self._fetch(url)
                yield page
                
                # 提取链接入队
                links = await self._extract_links(page, url)
                for link in links:
                    if self.same_domain and not same_domain(link, seed_url):
                        continue
                    await self.queue.put((link, depth + 1))
```

#### 2.2.3 SourceTracer (深度溯源)

```python
# intelligence/crawler/source_tracer.py
class SourceTracer:
    """
    深度溯源 — 任何数据都能追溯到原始来源
    
    能力:
    - 沿 RELATION_GRAPH 反向回溯
    - WHOS 记录 (原始创建者 / 机构 / 时间)
    - 许可证追踪 (CC-BY / Apache / 公开 / 内部)
    - 派生链 (被哪些数据集 / 模型使用)
    - 数字签名 (C2PA / Hash 验证)
    """
    
    async def trace(self, doc: Document) -> SourceChain:
        chain = SourceChain()
        
        # 1. 直系来源
        if doc.source_url:
            chain.add(await self._fetch_origin_page(doc.source_url))
        
        # 2. 沿血缘反查
        lineage = await self.bus.lineage_for("document", doc.id)
        chain.add_ancestors(lineage)
        
        # 3. License 验证
        chain.license = await self._resolve_license(doc)
        
        # 4. C2PA / Hash 验证
        chain.c2pa_signature = await self._verify_c2pa(doc)
        
        return chain
```

#### 2.2.4 AutoCrawlerGenerator (自适应爬虫生成)

```python
# intelligence/crawler/auto_generator.py
class AutoCrawlerGenerator:
    """
    自适应爬虫生成 — 分析目标页面自动生成专用爬虫
    
    流程:
    1. 给定 seed URL, 抓取样本页面
    2. LLM 分析页面结构 (DOM + 视觉)
    3. 生成 CSS Selector / XPath / API endpoint
    4. 验证准确率 ≥95%
    5. 注册到爬虫库
    """
    
    async def generate(self, seed_url: str, target_count: int) -> CrawlerConfig:
        # 抓样本
        samples = await self._fetch_samples(seed_url, n=10)
        
        # LLM 分析
        structure = await self.llm.extract_structure(
            f"Analyze this page. Identify the CSS selectors for: "
            f"main content, images, links, pagination, lazy-load triggers."
        )
        
        # 生成爬虫
        config = CrawlerConfig(
            url=seed_url,
            selectors=structure.selectors,
            pagination=structure.pagination,
            wait_triggers=structure.wait_triggers,
        )
        
        # 验证
        accuracy = await self._validate(config)
        if accuracy < 0.95:
            raise InsufficientAccuracyError(accuracy)
        
        return config
```

### 2.3 反爬与自适应

```python
# intelligence/crawler/anti_detection.py
class AntiDetection:
    """
    自适应反爬应对:
    - UA 轮换 (1000+ UA)
    - 代理池 (1M+ IP)
    - TLS 指纹 (curl_cffi 模拟浏览器)
    - 行为模拟 (人类操作模式)
    - Cookie 自动管理
    - 验证码识别 (2Captcha / 商业 API)
    - 速率自适应 (基于目标响应)
    """
    
    class Config:
        rotation_strategy: Literal["round_robin", "least_used", "random"]
        rate_limit: RateLimit
        captcha_solver: Optional[CaptchaSolver]
        human_simulation: bool  # 鼠标轨迹 / 滚动模式
```

### 2.4 合规与主权

```python
# intelligence/crawler/compliance.py
class CompliancePolicy:
    """
    合规策略 (操作员可配置):
    - robots.txt: 默认尊重, 可关闭
    - ToS: 默认尊重, 可标记 "internal_asset" 跳过
    - Rate limit: 默认遵守 server hints, 可配置硬上限
    - Audit: 100% 活动记录到 audit chain
    - Whitelist: 操作员可声明 "this domain is our own asset"
    - Geographic: 可限制到特定国家
    - Time window: 可限制到非高峰时段
    """

class SovereigntyMode(str, Enum):
    STRICT = "strict"           # 全尊重
    INTERNAL_ONLY = "internal"  # 仅内部白名单
    AUDIT_MODE = "audit"        # 全跑但所有活动审计
    RESEARCH = "research"       # 学术研究模式
```

---

## 第 3 章 数据处理流水线

### 3.1 流水线总览

```
Raw Documents (N) 
  ↓
[1] Dedupe (去重) 
  ↓ Unique docs (0.6-0.8N)
[2] Clean (清洗) 
  ↓ Clean docs
[3] AutoLabel (自动打标) 
  ↓ Labeled docs
[4] Scoring (评分) 
  ↓ Scored docs (quality / aesthetic / custom)
[5] Classify (分类) 
  ↓ Categorized (8 业务模态)
[6] Store (存储) 
  ↓ Datasets + Lineage + Metadata
```

### 3.2 去重 DedupeEngine

```python
# intelligence/processing/dedupe.py
class DedupeEngine:
    """
    多级去重:
    1. URL 精确匹配
    2. URL 规范化匹配 (query 参数 / fragment)
    3. 内容 SHA256 hash
    4. 感知 hash (pHash) — 图像
    5. SimHash — 文本
    6. 语义 embedding (向量聚类)
    """
    
    def __init__(self):
        self.url_cache = set()
        self.content_hash = set()
        self.phash_index = {}  # 图像
        self.simhash_index = {}  # 文本
        self.embedding_index = None  # 向量
    
    async def dedupe(self, docs: List[Document]) -> Tuple[List[Document], List[DedupeMatch]]:
        unique = []
        duplicates = []
        for doc in docs:
            match = await self._find_match(doc)
            if match is None:
                unique.append(doc)
                await self._index(doc)
            else:
                duplicates.append(DedupeMatch(doc=doc, duplicate_of=match))
        return unique, duplicates
```

### 3.3 清洗 CleaningEngine

```python
# intelligence/processing/cleaning.py
class CleaningEngine:
    """
    多模态清洗:
    - 文本: HTML 去除 / 编码修复 / 语言检测 / 长度过滤
    - 图像: 水印检测 / NSFW 检测 / 模糊检测 / 尺寸过滤 / EXIF 清理
    - 音频: 静音检测 / 噪声检测 / 时长过滤
    - 视频: 关键帧提取 / 字幕提取 / 黑边检测
    - 元数据: 标准化 / 字段映射
    """
    
    def __init__(self):
        self.watermark_detector = WatermarkDetector()
        self.nsfw_detector = NSFWDetector()
        self.blur_detector = BlurDetector()
        self.html_cleaner = HTMLCleaner()
    
    async def clean(self, doc: Document, rules: CleaningRules) -> CleanDocument:
        if doc.type == "image":
            return await self._clean_image(doc, rules)
        elif doc.type == "text":
            return await self._clean_text(doc, rules)
        # ... 8 模态
```

### 3.4 自动打标 AutoLabelEngine

```python
# intelligence/processing/auto_label.py
class AutoLabelEngine:
    """
    多策略自动打标:
    1. Foundation Model 打标 (CLIP / BLIP-2 / LLaVA / InternVL)
    2. 规则打标 (关键词 / 正则 / 阈值)
    3. 主动学习 (模型不确定的样本 → 人工)
    4. 多模型投票 (Consensus)
    """
    
    def __init__(self):
        self.clip = CLIPLabeler()
        self.llava = LLaVALabeler()
        self.rule_engine = RuleEngine()
        self.voting = VotingEngine()
    
    async def label(self, doc: Document, schema: LabelSchema) -> Labels:
        # 多模型并行
        labels_list = await asyncio.gather(
            self.clip.label(doc, schema),
            self.llava.label(doc, schema),
            self.rule_engine.label(doc, schema),
        )
        # 投票
        return self.voting.consensus(labels_list, threshold=0.8)
```

### 3.5 评分 ScoringEngine

```python
# intelligence/processing/scoring.py
class ScoringEngine:
    """
    多维度评分:
    1. 质量分 (Quality):
       - 清晰度 (图像/视频)
       - 信息量 (text entropy)
       - 完整性 (无遮挡 / 无截断)
       - 美学 (构图 / 色彩)
    2. 美学分 (Aesthetic):
       - CLIP-Aesthetic score
       - LAION aesthetic predictor
       - 构图 / 色彩 / 光线
    3. 自定义分 (Custom):
       - 用户可定义任意 scorer
    """
    
    async def score(self, doc: Document, dimensions: List[ScoreDim]) -> Score:
        scores = {}
        for dim in dimensions:
            if dim == ScoreDim.QUALITY:
                scores.quality = await self._quality(doc)
            elif dim == ScoreDim.AESTHETIC:
                scores.aesthetic = await self._aesthetic(doc)
            elif dim == ScoreDim.CUSTOM:
                scores.custom = await self._custom(doc)
        return scores
```

### 3.6 分类与存储

```python
# intelligence/processing/classify_store.py
class ClassifyStore:
    """
    智能分类:
    - 按 8 业务模态分 (image/video/text/audio/multimodal/sketch/drama/picturebook)
    - 按评分分桶 (high/medium/low)
    - 按类别 (cat/dog/...) 
    - 按来源 (channel)
    - 按时间 (date)
    
    智能存储:
    - MinIO 原始文件
    - OSS 三桶 (raw/curated/archive)
    - ORM 元数据 + lineage
    - 向量索引 (RAG 可检索)
    - 全文索引
    """
```

---

## 第 4 章 Agent 对话指挥中心

### 4.1 架构

```
用户输入: "我想要 100 万张猫狗图片, ≥1024px, 无水印"
  ↓
[1] Intent Classifier (LLM)
  intent = "data_acquisition"
  confidence = 0.98
  ↓
[2] Command Parser
  structured_command = {
    "intent": "data_acquisition",
    "entity": "image",
    "category": ["cat", "dog"],
    "count": 1_000_000,
    "filters": {"min_size": "1024x1024", "no_watermark": True},
    "compliance": "strict"
  }
  ↓
[3] Command Router
  → 路由到 DataAcquisitionAgent
  ↓
[4] Agent 接收任务, 实时回报进度
  ↓
[5] WebSocket / SSE 推送到前端
```

### 4.2 意图识别

```python
# intelligence/agent_commands/intent_classifier.py
class IntentClassifier:
    """
    意图分类 — 7 大类平台功能:
    1. data_acquisition (数据采集) - 最常用
    2. annotation (标注)
    3. review (审核)
    4. qc (质检)
    5. workflow (工作流)
    6. project (项目管理)
    7. user (用户/权限)
    
    平台其他子功能:
    - dataset_management
    - export_format
    - delivery_share
    - billing
    - monitoring
    """
```

### 4.3 命令路由器

```python
# intelligence/agent_commands/command_router.py
class CommandRouter:
    """
    NL → Structured → Agent → Action → Result
    
    支持:
    - 单步命令 ("查询项目 X 的状态")
    - 多步工作流 ("创建项目并分配给 3 个标注员")
    - 异步长任务 ("下载 100 万张图片,完成后通知我")
    - 中断/恢复 ("暂停下载,我想调整规则")
    - 撤销/回滚 ("取消刚才的操作")
    """
```

### 4.4 平台 Agent 集

```python
# intelligence/platform_agents/

class AnnotationAgent:
    """接管标注任务 — 自动分配, AI 预标注, 监控进度"""
    async def handle(self, command):
        # "给项目 X 分配 3 个标注员,每个 1000 条"
        # → 拆任务,自动分配,启动 AI 预标注

class ReviewAgent:
    """接管审核 — 质量审核, AQL 抽样, 报告生成"""
    async def handle(self, command):
        # "对项目 X 跑 AQL 1.0 抽样"
        # → 启动 QC,生成报告

class WorkflowAgent:
    """接管工作流 — 创建模板, 启动, 监控"""
    async def handle(self, command):
        # "用短剧模板建一个工作流,需求是..."
        # → 创建 DAG,启动,实时监控

class ProjectAgent:
    """接管项目 — CRUD, 成员, 时间线"""
    async def handle(self, command):
        # "创建一个 P0 项目,owner 是我,成员加张三李四"
        # → ORM 写入,触发事件

class UserAgent:
    """接管用户/权限 — 邀请, 角色, 配额"""
    async def handle(self, command):
        # "给张三分配 reviewer 角色,quota 调为 5000 次/天"
        # → 权限更新,审计

class PipelineAgent:
    """接管采集管线 — 创建/编辑/启动/停止"""
    async def handle(self, command):
        # "启动一个图片采集管线,目标 100 万张, 来源 12 个渠道"
        # → 创建 + 启动 + 监控

class QualityAgent:
    """接管质量 — 配置规则, 跑质量, 报告"""
    async def handle(self, command):
        # "配置数据 Profile: image 必须有 EXIF, ≥1024px, 无水印"
        # → 创建规则,应用到 pipeline
```

---

## 第 5 章 完整实现路线图

### 5.1 工作量

| 模块 | 工作量 | 优先级 |
|---|---|---|
| intelligence/crawler/ (8 渠道) | 8 周 | P0 |
| intelligence/processing/ (6 模块) | 6 周 | P0 |
| intelligence/agent_commands/ | 3 周 | P0 |
| intelligence/platform_agents/ (7 agents) | 4 周 | P1 |
| intelligence/data_acquisition/ (主 Agent) | 3 周 | P0 |
| 前端 ChatPanel.vue + WebSocket | 2 周 | P0 |
| 集成测试 | 2 周 | P0 |
| **总计 (P0)** | **~28 工程师-周 (5 人 × 6 周)** | |

### 5.2 4 阶段交付

| 阶段 | 时间 | 内容 |
|---|---|---|
| **Phase 1: 核心采集 (Week 1-3)** | 3 周 | 8 渠道爬虫 + 去重 + 清洗 + 简单评分 + DataAcquisitionAgent 主流程 |
| **Phase 2: 智能处理 (Week 4-5)** | 2 周 | 自动打标 + 多维度评分 + 分类 + 存储 |
| **Phase 3: 对话指挥 (Week 6)** | 1 周 | Intent Classifier + Command Router + WebSocket |
| **Phase 4: 平台 Agent 集 (V4.1)** | 4 周 | 7 个平台 Agent 完整接管所有功能 |

---

(更多内容见后续章节)

## 第 6 章 详细模块设计 (V4 完整实现)

### 6.1 多渠道爬虫详细 API

#### 6.1.1 CrawlerConfig

```python
# intelligence/crawler/config.py
@dataclass
class CrawlerConfig:
    """爬虫配置 — 操作员可全维度配置"""
    name: str
    channel_type: ChannelType
    seed_urls: List[str]
    
    # 合规
    compliance: CompliancePolicy = CompliancePolicy.STRICT
    respect_robots_txt: bool = True
    respect_rate_limit: bool = True
    rate_limit_rps: float = 1.0  # requests per second
    
    # 反爬
    user_agent_pool: List[str] = field(default_factory=lambda: DEFAULT_UA_POOL)
    proxy_pool: List[str] = field(default_factory=list)
    rotate_proxy_every: int = 10  # requests
    use_browser_fingerprint: bool = True
    captcha_solver: Optional[str] = None  # 2captcha / anti-captcha
    
    # 内容提取
    selectors: Dict[str, str] = field(default_factory=dict)  # css selectors
    wait_selectors: List[str] = field(default_factory=list)  # wait_for
    scroll_to_bottom: bool = False
    click_selectors: List[str] = field(default_factory=list)  # 触发翻页
    
    # 深度
    max_depth: int = 0  # 0 = 单页, >0 = 递归
    max_pages: int = 100
    same_domain_only: bool = True
    
    # 过滤
    url_include_patterns: List[str] = field(default_factory=list)
    url_exclude_patterns: List[str] = field(default_factory=list)
    min_content_length: int = 100
    language_filter: Optional[List[str]] = None
    
    # 输出
    output_format: Literal["raw", "markdown", "structured", "embedding"] = "raw"
    extract_metadata: bool = True
    extract_links: bool = True
    extract_images: bool = True
    
    # 存储
    storage_backend: Literal["minio", "oss", "local", "s3"] = "minio"
    storage_bucket: str = "imdf-crawled"
    storage_prefix: str = ""
    
    # 调度
    parallel_workers: int = 4
    rate_per_worker: float = 0.5
    batch_size: int = 100
```

#### 6.1.2 BaseCrawler 抽象基类

```python
# intelligence/crawler/base.py
class BaseCrawler(ABC):
    """所有爬虫的基类"""
    
    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.session = None
        self.proxy_pool = ProxyPool(config.proxy_pool)
        self.ua_pool = UserAgentPool(config.user_agent_pool)
        self.metrics = CrawlerMetrics()
        self.audit_chain = AuditChain()
        self.compliance = ComplianceChecker(config.compliance)
    
    @abstractmethod
    async def fetch(self, url: str) -> RawDocument:
        """子类实现具体抓取"""
        pass
    
    async def crawl(self, urls: List[str]) -> AsyncIterator[RawDocument]:
        """标准 crawl 流程 — 通用调度"""
        semaphore = asyncio.Semaphore(self.config.parallel_workers)
        async def _process(url):
            async with semaphore:
                # 合规检查
                if not await self.compliance.can_fetch(url):
                    self.metrics.blocked += 1
                    return None
                # 限速
                await self._rate_limit()
                # 抓取
                doc = await self.fetch(url)
                # 审计
                await self.audit_chain.append(...)
                return doc
        tasks = [_process(url) for url in urls]
        for coro in asyncio.as_completed(tasks):
            doc = await coro
            if doc:
                yield doc
```

#### 6.1.3 8 个具体爬虫

```python
# 1. WebCrawler (Playwright)
class WebCrawler(BaseCrawler):
    """通用 Web 爬虫 - JavaScript 渲染友好"""
    
    async def fetch(self, url: str) -> RawDocument:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": self.proxy_pool.get_next()} if self.proxy_pool.has_proxies() else None
            )
            context = await browser.new_context(
                user_agent=self.ua_pool.get_next(),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # 智能等待
            for sel in self.config.wait_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                except: pass
            
            # 滚动触发懒加载
            if self.config.scroll_to_bottom:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
            
            # 点击翻页按钮
            for sel in self.config.click_selectors:
                try:
                    await page.click(sel)
                    await page.wait_for_timeout(1000)
                except: pass
            
            # 提取
            html = await page.content()
            text = await page.evaluate("() => document.body.innerText")
            images = await page.query_selector_all("img")
            image_urls = [await img.get_attribute("src") for img in images]
            links = await page.query_selector_all("a")
            link_urls = [await link.get_attribute("href") for link in links]
            metadata = await page.evaluate("""() => ({
                title: document.title,
                description: document.querySelector('meta[name="description"]')?.content,
                keywords: document.querySelector('meta[name="keywords"]')?.content,
                og_image: document.querySelector('meta[property="og:image"]')?.content,
                author: document.querySelector('meta[name="author"]')?.content
            })""")
            
            await browser.close()
            
            return RawDocument(
                url=url, html=html, text=text, images=image_urls,
                links=link_urls, metadata=metadata
            )


# 2. APICrawler (REST/GraphQL/gRPC)
class APICrawler(BaseCrawler):
    """API 爬虫 - 支持 REST / GraphQL / gRPC"""
    
    async def fetch(self, url: str) -> RawDocument:
        if self.config.api_type == "rest":
            response = await self.session.get(url, headers=self.config.headers)
            return RawDocument(url=url, json=response.json())
        elif self.config.api_type == "graphql":
            response = await self.session.post(url, json={"query": self.config.graphql_query})
            return RawDocument(url=url, json=response.json())
        elif self.config.api_type == "grpc":
            # gRPC client
            return await self._grpc_call(url)


# 3. RssCrawler
class RssCrawler(BaseCrawler):
    """RSS / Atom 订阅爬虫"""
    
    async def fetch(self, url: str) -> RawDocument:
        import feedparser
        feed = feedparser.parse(url)
        return RawDocument(
            url=url,
            items=[{
                "title": entry.title,
                "link": entry.link,
                "published": entry.published,
                "summary": entry.summary,
                "content": entry.content[0].value if entry.content else ""
            } for entry in feed.entries]
        )


# 4. SocialCrawler (公开 API)
class SocialCrawler(BaseCrawler):
    """社交媒体爬虫 - 公开 API (Twitter/Reddit/Mastodon)"""
    
    async def fetch(self, url: str) -> RawDocument:
        # Twitter API v2
        if "twitter.com" in url or "x.com" in url:
            return await self._twitter_fetch(url)
        # Reddit JSON API
        if "reddit.com" in url:
            return await self._reddit_fetch(url)
        # Mastodon API
        if "mastodon" in url:
            return await self._mastodon_fetch(url)
        # HackerNews
        if "news.ycombinator.com" in url:
            return await self._hn_fetch(url)


# 5. FileCrawler
class FileCrawler(BaseCrawler):
    """文件 / OSS 爬虫 - S3/GCS/Azure/MinIO"""
    
    async def fetch(self, url: str) -> RawDocument:
        if url.startswith("s3://"):
            return await self._s3_fetch(url)
        if url.startswith("gs://"):
            return await self._gcs_fetch(url)
        if url.startswith("minio://"):
            return await self._minio_fetch(url)


# 6. SearchEngineCrawler
class SearchEngineCrawler(BaseCrawler):
    """搜索引擎爬虫 - SerpAPI/Google CSE/Bing"""
    
    async def fetch(self, url: str) -> RawDocument:
        results = await self.serpapi.search(q=url, num=100)
        return RawDocument(
            url=url, items=[{
                "title": r.title, "link": r.link, "snippet": r.snippet
            } for r in results]
        )


# 7. DeepCrawler (递归深爬)
class DeepCrawler(BaseCrawler):
    """深度递归爬虫 - 学术网/电商树/社交图谱"""
    
    async def crawl(self, urls):
        # BFS/DFS 递归
        queue = asyncio.Queue()
        for url in urls:
            await queue.put((url, 0))
        visited = set()
        while not queue.empty() and len(visited) < self.config.max_pages:
            url, depth = await queue.get()
            if url in visited or depth > self.config.max_depth:
                continue
            visited.add(url)
            
            doc = await self.fetch(url)
            yield doc
            
            # 递归
            for link in doc.links:
                if link not in visited and self._should_follow(link):
                    await queue.put((link, depth + 1))


# 8. DarkCrawler (学术/预印本)
class DarkCrawler(BaseCrawler):
    """学术/预印本爬虫 - arXiv/PubMed/Semantic Scholar"""
    
    async def fetch(self, url: str) -> RawDocument:
        if "arxiv.org" in url:
            return await self._arxiv_fetch(url)
        if "pubmed" in url:
            return await self._pubmed_fetch(url)
        if "semanticscholar" in url:
            return await self._semantic_scholar_fetch(url)
```

### 6.2 数据处理流水线详细 API

#### 6.2.1 DedupeEngine

```python
# intelligence/processing/dedupe.py
class DedupeEngine:
    """
    多级去重引擎:
    Level 1: URL 精确匹配 (最快)
    Level 2: URL 规范化匹配 (去掉 query / fragment)
    Level 3: 内容 SHA256 hash (精确内容去重)
    Level 4: 感知 hash pHash (图像近似去重)
    Level 5: SimHash (文本近似去重)
    Level 6: Embedding 语义聚类 (最慢,最智能)
    """
    
    def __init__(self, level: int = 4):
        self.level = level
        self.url_exact = set()
        self.url_normalized = set()  # url_normalize
        self.content_sha = {}  # sha256 -> doc_id
        self.phash_index = {}  # 64-bit pHash -> doc_id
        self.simhash_index = {}  # 64-bit SimHash -> doc_id
        self.embedding_index = None  # FAISS HNSW
    
    async def dedupe(self, docs: List[Document]) -> DedupeResult:
        unique = []
        duplicates = []
        for doc in docs:
            match = await self._find_match(doc)
            if match is None:
                unique.append(doc)
                await self._index(doc)
            else:
                duplicates.append(DedupeMatch(
                    doc=doc, 
                    duplicate_of=match.doc_id,
                    similarity=match.similarity,
                    method=match.method
                ))
        return DedupeResult(unique=unique, duplicates=duplicates)
    
    async def _find_match(self, doc):
        # Level 1-6 逐级匹配
        if doc.url in self.url_exact:
            return Match(doc_id=..., similarity=1.0, method="url_exact")
        if self._normalize_url(doc.url) in self.url_normalized:
            return Match(..., method="url_normalized")
        # ... 等等
```

#### 6.2.2 CleaningEngine

```python
# intelligence/processing/cleaning.py
class CleaningEngine:
    """
    8 模态清洗规则
    """
    
    async def clean(self, doc: Document, rules: CleaningRules) -> CleanResult:
        cleaner = self._get_cleaner(doc.type)
        return await cleaner.clean(doc, rules)
    
    # 文本清洗
    async def _clean_text(self, doc, rules):
        text = doc.text
        # HTML 去除
        if rules.strip_html:
            text = BeautifulSoup(text, "html.parser").get_text()
        # 编码修复
        text = text.encode("utf-8", errors="ignore").decode("utf-8")
        # 语言检测
        lang = detect(text)
        if rules.language_filter and lang not in rules.language_filter:
            return CleanResult(rejected=True, reason=f"language={lang} not in filter")
        # 长度过滤
        if len(text) < rules.min_length:
            return CleanResult(rejected=True, reason="too short")
        # 敏感词过滤
        if rules.sensitive_words and any(w in text for w in rules.sensitive_words):
            return CleanResult(rejected=True, reason="sensitive words")
        return CleanResult(clean_text=text, language=lang, length=len(text))
    
    # 图像清洗
    async def _clean_image(self, doc, rules):
        from PIL import Image
        img = Image.open(doc.path)
        # 尺寸过滤
        if rules.min_size:
            if img.size[0] < rules.min_size[0] or img.size[1] < rules.min_size[1]:
                return CleanResult(rejected=True, reason=f"size < {rules.min_size}")
        # 水印检测
        if rules.no_watermark:
            if await self.watermark_detector.detect(img):
                return CleanResult(rejected=True, reason="watermark detected")
        # NSFW 检测
        if rules.no_nsfw:
            if await self.nsfw_detector.detect(img):
                return CleanResult(rejected=True, reason="NSFW")
        # 模糊检测
        if rules.min_sharpness:
            sharpness = self._calc_sharpness(img)
            if sharpness < rules.min_sharpness:
                return CleanResult(rejected=True, reason=f"too blurry ({sharpness:.2f})")
        return CleanResult(image=img, size=img.size, sharpness=sharpness)
    
    # 视频清洗
    async def _clean_video(self, doc, rules):
        # 关键帧提取
        if rules.extract_keyframes:
            frames = await self._extract_keyframes(doc.path, n=rules.keyframe_count)
        # 黑边检测
        if rules.no_black_bars:
            has_bars = await self._detect_black_bars(doc.path)
            if has_bars:
                return CleanResult(rejected=True, reason="black bars")
        # 字幕提取
        subtitles = await self._extract_subtitles(doc.path)
        return CleanResult(frames=frames, subtitles=subtitles)
```

#### 6.2.3 AutoLabelEngine

```python
# intelligence/processing/auto_label.py
class AutoLabelEngine:
    """
    多策略自动打标
    """
    
    async def label(self, doc: Document, schema: LabelSchema) -> Labels:
        # 策略 1: Foundation Model 打标
        fm_labels = await self._foundation_model_label(doc, schema)
        # 策略 2: 规则打标
        rule_labels = await self._rule_label(doc, schema)
        # 策略 3: 主动学习
        if schema.allow_active_learning:
            al_labels = await self._active_learning_label(doc, schema)
        else:
            al_labels = None
        # 策略 4: 多模型投票
        return await self._voting([fm_labels, rule_labels, al_labels])
    
    async def _foundation_model_label(self, doc, schema):
        # CLIP zero-shot
        if doc.type == "image":
            labels = await self.clip.zero_shot(doc.image, schema.candidates)
        # LLaVA 多模态对话
        elif doc.type == "image":
            labels = await self.llava.describe(doc.image, schema.prompt)
        # BLIP-2 captioning
        elif doc.type == "image":
            caption = await self.blip2.caption(doc.image)
        # Whisper ASR
        elif doc.type == "audio":
            text = await self.whisper.transcribe(doc.audio)
        return labels
    
    async def _voting(self, label_sets):
        """Consensus voting — 多模型投票"""
        from collections import Counter
        all_labels = []
        for labels in label_sets:
            if labels:
                all_labels.extend(labels)
        counts = Counter(all_labels)
        # 阈值 0.8 = 至少 2/3 模型同意
        threshold = len(label_sets) * 0.8
        consensus = [label for label, count in counts.items() if count >= threshold]
        return Labels(
            labels=consensus,
            confidence=counts[consensus[0]] / len(label_sets) if consensus else 0,
            method="voting"
        )
```

#### 6.2.4 ScoringEngine

```python
# intelligence/processing/scoring.py
class ScoringEngine:
    """
    多维度评分
    """
    
    async def score(self, doc: Document, dimensions: List[ScoreDim]) -> Scores:
        scores = Scores()
        for dim in dimensions:
            if dim == ScoreDim.QUALITY:
                scores.quality = await self._quality(doc)
            elif dim == ScoreDim.AESTHETIC:
                scores.aesthetic = await self._aesthetic(doc)
            elif dim == ScoreDim.CUSTOM:
                scores.custom = await self._custom(doc)
        return scores
    
    async def _quality(self, doc):
        if doc.type == "image":
            # CLIP-IQA, MUSIQ, MANIQA
            return await self.musiq.score(doc.image)
        elif doc.type == "text":
            # TextRank, perplexity, length, vocabulary richness
            return self._text_quality(doc.text)
    
    async def _aesthetic(self, doc):
        if doc.type == "image":
            return await self.laion_aesthetic.score(doc.image)
    
    async def _custom(self, doc):
        # 用户自定义 scorer
        for scorer in self.custom_scorers:
            score = await scorer(doc)
            yield score
```

#### 6.2.5 ClassifyStore

```python
# intelligence/processing/classify_store.py
class ClassifyStore:
    """
    智能分类与存储
    """
    
    async def classify_and_store(self, doc: ScoredDocument, schema: ClassifySchema):
        # 1. 多维分类
        classification = {
            "modality": doc.modality,  # image/video/text/audio/...
            "category": doc.category,   # cat/dog/...
            "quality_bucket": self._bucket(doc.score.quality),  # high/medium/low
            "source_channel": doc.source_channel,
            "date": doc.crawl_date,
        }
        
        # 2. 路由到存储桶
        storage_path = self._compute_path(classification, doc)
        
        # 3. 存储
        await self.minio.put(storage_path, doc.content)
        
        # 4. ORM 元数据
        await self.orm.insert_document(doc, classification)
        
        # 5. Lineage 记录
        await self.bus.record_lineage(...)
        
        # 6. 向量索引
        if doc.embedding:
            await self.vector_index.add(doc.id, doc.embedding)
        
        return classification
```

### 6.3 Agent 对话指挥详细 API

#### 6.3.1 IntentClassifier

```python
# intelligence/agent_commands/intent_classifier.py
class IntentClassifier:
    """
    7 大平台功能 + 12 子功能
    """
    
    INTENTS = {
        "data_acquisition": "数据采集",
        "annotation": "标注",
        "review": "审核",
        "qc": "质检",
        "workflow": "工作流",
        "project": "项目",
        "user": "用户/权限",
        "dataset_management": "数据集",
        "export_format": "导出",
        "delivery_share": "交付分享",
        "billing": "计费",
        "monitoring": "监控",
    }
    
    async def classify(self, text: str) -> Intent:
        prompt = f"""
        Classify the following user request into one of these intents:
        {list(self.INTENTS.keys())}
        
        User request: "{text}"
        
        Return JSON: {{"intent": "...", "confidence": 0.0-1.0, "entities": {{...}}}}
        """
        result = await self.llm.complete(prompt, response_format="json")
        return Intent(**result)
```

#### 6.3.2 CommandParser

```python
# intelligence/agent_commands/command_parser.py
class CommandParser:
    """
    NL → Structured Command
    """
    
    COMMAND_SCHEMAS = {
        "data_acquisition": {
            "entity": "image|video|text|audio|multimodal",
            "category": ["cat", "dog", ...],  # 自动从 entity 推断
            "count": int,
            "filters": {
                "min_size": "1024x1024",
                "no_watermark": bool,
                "quality_threshold": float,
                "language": ["en", "zh"],
            },
            "channels": ["google_images", "open_images", ...],  # 默认自动选
            "compliance": "strict|internal|audit|research",
            "output_format": "raw|structured|embedding",
        },
        "annotation": {...},
        ...
    }
    
    async def parse(self, text: str, intent: Intent) -> Command:
        schema = self.COMMAND_SCHEMAS[intent.intent]
        prompt = f"""
        Extract structured parameters from this user request.
        Schema: {schema}
        Request: "{text}"
        
        Return JSON matching the schema.
        """
        return await self.llm.complete(prompt, schema=schema)
```

#### 6.3.3 CommandRouter

```python
# intelligence/agent_commands/command_router.py
class CommandRouter:
    """
    Command → Agent → Action → Result
    """
    
    AGENTS = {
        "data_acquisition": DataAcquisitionAgent,
        "annotation": AnnotationAgent,
        "review": ReviewAgent,
        "qc": QualityAgent,
        "workflow": WorkflowAgent,
        "project": ProjectAgent,
        "user": UserAgent,
    }
    
    async def route(self, command: Command, session: Session) -> Task:
        agent_class = self.AGENTS.get(command.intent)
        if not agent_class:
            return await self._handle_unknown(command)
        agent = agent_class(session=session)
        task = await agent.handle(command)
        return task
```

#### 6.3.4 SessionManager

```python
# intelligence/agent_commands/session_manager.py
class SessionManager:
    """
    会话状态管理:
    - 会话历史
    - 多 Agent 协作上下文
    - 用户偏好
    - 任务编排
    """
    
    async def create_session(self, user_id: str) -> Session:
        session = Session(
            id=uuid4().hex,
            user_id=user_id,
            history=[],
            context={},
            created_at=datetime.now()
        )
        await self.store.save(session)
        return session
    
    async def add_message(self, session_id: str, role: str, content: str):
        # 保存到 history, 同时 WebSocket 推送给前端
        ...
    
    async def stream_response(self, session_id: str, response: AsyncIterator[str]):
        # 流式推送到前端
        async for chunk in response:
            await self.ws.send(session_id, chunk)
```

### 6.4 平台 Agent 集

```python
# intelligence/platform_agents/annotation_agent.py
class AnnotationAgent:
    """标注 Agent — 自动分配任务, AI 预标, 监控"""
    
    async def handle(self, command: AnnotationCommand):
        if command.action == "create_tasks":
            # "给项目 X 创建 1000 个标注任务,3 个标注员"
            tasks = await self.workbench.enqueue_tasks(
                project_id=command.project_id,
                count=command.count,
                assignees=command.assignees,
                geometry_type=command.geometry
            )
            # 启动 AI 预标注
            if command.ai_prelabel:
                await self.ai_prelabel(tasks)
        
        elif command.action == "ai_label":
            # "用 SAM 给这些图片预标"
            results = await self.sam.predict(command.images)
        
        elif command.action == "monitor":
            # "项目 X 进度怎么样"
            return await self.workbench.get_stats(command.project_id)


# intelligence/platform_agents/review_agent.py
class ReviewAgent:
    """审核 Agent — 分配审核员, AQL, 报告"""
    
    async def handle(self, command: ReviewCommand):
        if command.action == "start_review":
            return await self.review_engine.start(command.dataset_id, command.reviewers)
        if command.action == "aql_sample":
            return await self.qc_engine.aql_sample(
                dataset_id=command.dataset_id,
                aql_level=command.aql_level,
                lot_size=command.lot_size
            )


# intelligence/platform_agents/workflow_agent.py
class WorkflowAgent:
    """工作流 Agent — 创建/启动/监控"""
    
    async def handle(self, command: WorkflowCommand):
        if command.action == "create_from_template":
            # "用短剧模板建一个工作流,需求是..."
            template = await self.wb.get_template(command.template)
            return await self.wb.create_workflow(
                template=template,
                params=command.params,
                owner_id=command.user_id
            )


# intelligence/platform_agents/project_agent.py
class ProjectAgent:
    """项目 Agent — CRUD + 成员 + 时间线"""
    
    async def handle(self, command: ProjectCommand):
        if command.action == "create":
            return await self.project_engine.create_project(
                name=command.name, owner_id=command.user_id,
                members=command.members, priority=command.priority
            )


# intelligence/platform_agents/user_agent.py
class UserAgent:
    """用户/权限 Agent"""
    
    async def handle(self, command: UserCommand):
        if command.action == "invite":
            return await self.user_service.invite(
                email=command.email, role=command.role
            )
        if command.action == "set_quota":
            return await self.user_service.set_quota(
                username=command.username, quota=command.quota
            )


# intelligence/platform_agents/pipeline_agent.py
class PipelineAgent:
    """采集管线 Agent"""
    
    async def handle(self, command: PipelineCommand):
        if command.action == "create":
            return await self.acquisition.create_pipeline(
                config=command.config
            )
        if command.action == "start":
            return await self.acquisition.start_pipeline(command.pipeline_id)
        if command.action == "stop":
            return await self.acquisition.stop_pipeline(command.pipeline_id)


# intelligence/platform_agents/quality_agent.py
class QualityAgent:
    """质量 Agent — 配置规则, 跑质量, 报告"""
    
    async def handle(self, command: QualityCommand):
        if command.action == "configure_profile":
            return await self.qc_engine.create_profile(command.rules)
        if command.action == "run_quality":
            return await self.qc_engine.full_check(command.dataset_id)
```

---

(更多章节见后续: V4 集成测试、API 设计、WebSocket 协议、前端 ChatPanel)
