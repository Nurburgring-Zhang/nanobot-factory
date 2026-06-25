# 微信文章 Deep Research Summary — VDP-2026 借鉴清单

> **任务**: P4-2-W2 — 深度研究 research/微信文章.txt, 提取可借鉴到 VDP-2026 (nanobot-factory) 的设计/工作流/趋势。
> **数据源**: `D:\Hermes\生产平台\nanobot-factory\research\微信文章.txt` (110KB, 2309 行)
> **实际文章数**: **14 篇** (任务描述写 9 篇, 文件扩充后到 14, 本报告覆盖全部)
> **生成时间**: 2026-06-24
> **VDP-2026 上下文**: 智影 (ZhiYing) 商业级全栈数据生成管理平台, 12 微服务 (agent / annotation / asset / cleaning / collection / dataset / evaluation / notification / scoring / search / user / workflow), 当前 1307 处前端 stub + 241 处后端 TODO, 0 SQLite/Postgres, 0 Celery, 64 引擎框架在但端到端未验证。

---

## 文章分段识别 (按章节标题)

> **注**: 文件中 14 篇文章的分割点为 `---` 分隔线 + 标题行 (以空格开头的纯标题行)。下表列出每篇标题 + 起止行 + 核心观点。

| # | 标题 | 起止行 | 核心观点 (1 段) |
|---|------|--------|----------------|
| 1 | Google Flow Agent突然发布！会规划故事线、会死守角色一致性，57秒做完一部短片 | 1–132 | Google Labs 在 Flow 里加入 Agent (Gemini Omni + Veo 3.1 + Nano Banana), 实现"57 秒从创意到成片", 核心是 Agent Instructions + 参考图锁定角色一致性 + 多轮项目记忆。 |
| 2 | 有人用这个开源工具104条视频做了460万粉丝 ⭐GitHub挖宝·番外篇·Jellyfish | 137–219 | Jellyfish (Apache-2.0, 2.3k Star) = AI 短剧工厂, 四步流水线 (剧本→分镜→资产→生成→剪辑), 三层一致性锁死 (种子+风格+资产库), 多模型自由切换 (OpenAI/Claude/Qwen + Midjourney/SD + Runway/Kling/Luma)。 |
| 3 | Hermes 玩家都在卷的五件套：少一个都不算"满配" | 224–273 | Hermes 五件套: ① SOUL.md 定岗位 ② Hindsight 装脑子 (结构化记忆) ③ 网络搜索+网页抓取 ④ 语音识别+合成+图片生成多模态 ⑤ Token 监控+终端过滤省 60–90% 费用。 |
| 4 | AGENT的时代 | 283–317 | Hermes + Obsidian + 本地 Skill 的"数据库驱动生图+PPT 生成"模式; 7 个 agent 成员协作 (其中还会"抢活"); Obsidian 推演前期定位。 |
| 5 | 无审查无限制：免费、开源的AI图像、视频解决方案 支持原生1080p (Open-Generative-AI) | 321–401 | 5 个工作室 (Image/Video/Lip Sync/Cinema/Workflow) 整合 200+ 模型, 双轨架构 (云端 Muapi.ai + 本地 stable-diffusion.cpp), models.js 单一元数据源, 桌面三平台 (DMG/NSIS/AppImage)。 |
| 6 | OpenMontage——首个开源 AI 编排式视频生产系统 | 405–907 | "Agent-First" 架构 (YAML + Markdown 指令文件驱动 AI, Python 仅作工具手); 12 条专业管线 (Animated/Cinematic/Talking Head 等); 52+ 工具 + 400+ 技能; 3 渲染引擎 (Remotion + HyperFrames + FFmpeg); 4 道质量门禁 + 预算控制 + 决策审计追踪。 |
| 7 | 10 个开源 Skill，搭一条 AI 内容创作流水线 | 911–1106 | 10 个 Skill 覆盖内容创作全链路 (调研→营销→写作→润色→配图→卡片→PPT→剪辑→故事→多模态); 关键模式: 通用 Skill (PPT/卡片) + 专用 Skill (剪辑/故事/营销) + 串联工作流。 |
| 8 | 你教了AI 4次它还记不住？给Hermes装个Hindsight就行 | 1110–1281 | Hindsight = Hermes 智能长效记忆升级方案 (Memory Provider 插件), 三字诀"存/查/学"; 4 层结构 (USER.md/MEMORY.md/触发器/手动工具); 触发条件 (自动 10 轮/事件即时/手动); Local-first + 云端双模式。 |
| 9 | FastVideo：耗时5秒出 30 秒 1080p AI视频 (Dreamverse) | 1285–1431 | UCSD Hao AI Lab 的 FastVideo 框架, 5 秒 1080p 视频 4.55 秒出完 (比播放还快), "氛围直控 Vibe Directing" (聊天式迭代), NVIDIA Dynamo 官方后端, Apache-2.0 (3.7k stars)。 |
| 10 | ComfyUI 一张图把分镜、Seedance 2.0 和 LLM 全串起来了！AI 视频的「导演模式」真要来了？ | 1435–1589 | ComfyUI + Seedance 2.0 + LLM 三模块导演台: LLM 出分镜→图像模型出分镜板→Seedance 2.0 动起来; 关键洞察"分镜是 guide not contract"; 118k stars, Netflix/Amazon/Apple 实际采用。 |
| 11 | 人类搞了 30 年没做出意识的工程实现，一个 GitHub 仓库，炸了整个意识圈 (ORION-Global-Workspace) | 1593–1707 | 4 个 Python 文件实现 GWT (全局工作空间理论) 工程实现: workspace.py + modules.py + broadcast.py + competition.py; 把"哲学+认知科学"问题变成工程问题; 2000+ 论文但 0 开源实现→ 首个完整实现。 |
| 12 | 这个 GitHub 有意思啊，Claude Code + Obsidian = 知识库王炸 (claude-obsidian) | 1710–1834 | Karpathy LLM Wiki 理念实践: Claude 自己读/链接/维护资料, 实体页+概念页+来源页+双向引用, 矛盾检测, 会话记忆 hot.md, 8 类健康检查, 纯本地 Markdown (无 DB), 7200 stars。 |
| 13 | 暴涨56.2k Star！生化危机女主开源智能体记忆系统 (MemPalace) | 1837–2201 | Milla Jovovich 开源 MemPalace, local-first AI 记忆宫殿, Wing/Room/Hall/Closet/Drawer/Tunnel 6 层导航, 4 层 Memory Stack (L0 Identity→L1 Essential Story→L2 Wing 召回→L3 完整语义搜索), LongMemEval R@5 96.6%, MCP 协议, ChromaDB/sqlite_exact/Qdrant/pgvector 后端。 |
| 14 | GitHub 1.2k Star！开源实时数字人 Agent 框架 CyberVerse | 2204–2306 | 实时数字人 Agent 框架, WebRTC + PersonaAgent/SubAgent 多 Agent 架构, 可选 FlashHead/LiveAct Avatar 后端 (照片驱动), omni 模型 + LLM + TTS + ASR + Embedding + RAG 全插件化 (cyberverse_config.yaml), 1.2k stars。 |

---

## 文章 1: Google Flow Agent (Gemini Omni + Veo 3.1 + Nano Banana)

### 文章主题

Google Labs 在 2026-06-17 给 Flow 加了一个 Agent, 把"画一张图→成片"压缩成 57 秒, 核心是 Agent Instructions + 参考图锁定 + 多轮项目记忆。底层技术栈是 Gemini Omni (多模态视频模型, "视频版 Nano Banana") + Veo 3.1 (高质量生成) + Nano Banana (精确图像编辑), 三套核心模型用一个推理层缝合。

### 关键工具/平台/技术

- **Agent Instructions**: 系统级上下文记忆 (非提示词技巧), 每轮生成都回溯角色约束
- **参考图锁定**: 上传 2-3 张角色参考图, "100% 匹配"规则硬约束
- **Gemini Omni**: 多模态视频模型, 世界理解+物理一致性+对话式编辑
- **Veo 3.1**: 高质量视频生成 (4K 原生, Fast 模式 55 秒/8 秒)
- **Nano Banana**: 精确图像编辑 (单帧自然语言修改)
- **批量操作**: "把外套从红改成蓝, 应用到所有相关资产" 一句话完成
- **自动组织**: "把夜戏归到 Night Collection, 按场景重命名" 自然语言归类
- **多轮迭代**: 故事大纲→第二幕改得更忧伤→第三幕加抉择时刻, Agent 持续记忆
- **真实用户案例**: 57 秒从创意到短片 (ApurbaDS2024)

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 实现 `AgentInstructions` Pydantic 模型 + 角色参考图锁定 (参考图 hash 索引), 参考 Jellyfish 的"角色一致性库"在 `asset_service` 加 `CharacterAsset` 实体 (face embedding + outfit metadata), agent 每次生成前必查角色库。
- **workflow_service**: 加 `MultiTurnMemory` 表 (session_id + turn_index + project_context JSONB), Agent 多轮项目记忆, 每轮把"上一轮改了什么"写入, 下一轮召回。
- **workflow_service**: 批量操作 API `POST /workflow/batch_update` 接受自然语言指令 ("把所有外套从红改成蓝"), 通过 LLM 解析为资产 ID 列表, 一次性异步更新 (Celery chord)。
- **asset_service**: 加 `NaturalLanguageOrganize` API, "把夜戏归到 Night Collection" 通过 LLM 提取 (时间+光照+主体) 特征, 自动归档到 Collection (collection_service 已有)。
- **dataset_service**: 加 `GeminiOmniStyleMultimodalGenerator`, 借鉴 Gemini Omni 的"世界理解+物理一致性", 升级 dataset_builder 的多模态标注能力 (物理关系/光照逻辑/空间结构)。

---

## 文章 2: Jellyfish (AI 短剧工厂)

### 文章主题

Jellyfish (github.com/Forget-C/Jellyfish, Apache-2.0, 2.3k stars) 是"AI 短剧工厂", 一个人用它 104 条视频做出 460 万粉丝。核心是"AI 短剧从剧本到成片一站式" + "三层一致性锁死 (全局种子+统一风格提示词+可复用资产库)"。

### 关键工具/平台/技术

- **四步流水线**: ① 剧本→AI 拆镜 (可定制 Agent 工作流) ② 资产库 (角色/场景/道具/服装, 双层: 项目级+全局级) ③ 三栏式分镜编辑器 (左列表/中预览/右属性) ④ 内置剪辑台 (多轨视频+音频, 一键导出竖屏)
- **三层一致性锁死**:
  - L1 全局种子 (跨镜头同一种子噪声, 保证同一角色脸型)
  - L2 统一风格提示词 (防止咖啡馆装修突变)
  - L3 可复用资产库 (角色 ID 跨剧集复用)
- **多模型自由切换** (模型管理层, 非套壳):
  - 文本: OpenAI / Claude / 通义千问 / 腾讯混元
  - 图像: Midjourney / Stable Diffusion
  - 视频: Runway / Kling / Luma
- **三栏分镜编辑器**: 景别+角度+运镜+情绪+光效+对白 (每分镜多版本管理)
- **Docker Compose 一键部署**: 前端 7788, 后端 8000

### 借鉴到 VDP-2026 12 微服务的具体行动

- **asset_service**: 实现 `AssetLibrary` 双层模型 (项目级 `ProjectAsset` + 全局级 `GlobalAsset`), character_id 跨项目复用, 加 `character_embedding` (face embedding, 用 InsightFace/SCRFD) 用于一致性检索。
- **workflow_service**: 借鉴四步流水线, 在 `nanobot_factory_backend/extended_skills_pkg/storyboard_pipeline.py` 实现 (剧本→拆镜→资产→分镜→生成→剪辑), 每步独立 Celery task。
- **agent_service**: 实现 `AgentWorkflowConfig` (YAML), 用户可定制"提取剧情/角色/分镜"逻辑, 参考 Jellyfish 的"可定制 Agent 工作流"模式。
- **cleaning_service**: 加 `ConsistencyChecker`, 用 character_embedding 跨镜头计算相似度, 低于阈值自动报警 (角色漂移检测)。
- **annotation_service**: 加 `ShotAttributesAnnotation` 模型 (景别+角度+运镜+情绪+光效), 借鉴 Jellyfish 的"分镜属性面板"做成可标注字段。

---

## 文章 3: Hermes 五件套 (SOUL.md + Hindsight + 联网 + 多模态 + 省 Token)

### 文章主题

"裸装 Hermes 是聊天玩具, 配齐五件才干活"。五件套 = ① SOUL.md 定岗位 ② Hindsight 装脑子 (结构化记忆) ③ 网络搜索+网页抓取 ④ 语音识别/合成+图片生成多模态 ⑤ Token 监控+终端过滤省 60–90% 费用。

### 关键工具/平台/技术

- **SOUL.md**: 身份/人格层文件, 定义 Agent 性格+语气+沟通风格, 不属于持久记忆
- **联网**: AI 搜索引擎 (Perplexity/Exa) + 网页抓取工具 (Jina Reader)
- **多模态**: 语音识别 (Whisper) + 合成 (ElevenLabs) + 图片生成 (SD/FLUX)
- **省 Token**: 终端输出过滤 (filter-command) + Token 用量监控 (tokencost/ccusage)

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 在 `agents/` 加 `SOUL.md` 模式, 每个 agent 类型 (pm-agent/dev-agent/qa-agent) 一个 SOUL.md, 启动时加载到 system prompt。
- **agent_service**: 加 `WebSearchTool` (集成 SearXNG/Bocha) + `WebFetchTool` (集成 Jina Reader), agent 可访问最新信息。
- **agent_service**: 多模态支持 — 加 `TTSProvider` (ElevenLabs/OpenAI TTS) + `STTProvider` (Whisper), 前端 v2 加语音输入按钮。
- **notification_service**: 加 `TokenUsageTracker`, 集成 tokencost 库, 每次 LLM 调用记录到 `token_usage` 表, 暴露 Prometheus 指标 (`vdp_token_spent_total`)。
- **agent_service**: 终端输出过滤 — 加 `CommandOutputFilter` middleware, 自动裁剪无意义 log 行 (≥5 行连续相同前缀的日志压缩为"[重复 X 次]"), 节省 60-90% Token。

---

## 文章 4: AGENT 时代 (Hermes + Obsidian + 本地 Skill 驱动生图+PPT)

### 文章主题

Hermes + Obsidian + 本地 Skill 形成"数据库驱动生图+PPT 生成"新范式。7 个 agent 成员协作, 还会"抢活" (柯布助手)。Obsidian 推演前期定位, 思想>工具。

### 关键工具/平台/技术

- **数据库驱动生图**: 不用每次写完整 prompt, 调 Obsidian 知识库里的素材库, 一次生成多版本
- **7 agent 协作**: 角色分工 + 抢活机制 (上下文感知)
- **Obsidian 推演**: 用 Obsidian graph view 模拟方案前期定位
- **本地 Skill**: 复用本地 skill 库, 不依赖云端 (skill_adapter.py 已部分实现)

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 扩展现有 `agents/` 目录到 7 个专门角色 (pm-agent / dev-agent / qa-agent / data-agent / design-agent / ops-agent / product-agent), 每个独立 SOUL.md, 通过 `MultiAgentOrchestrator` 协作。
- **agent_service**: 实现 `TaskStealing` 机制 — agent 检测到其他 agent 长时间空闲 + 自己队列有任务, 主动"抢活", 通过 Redis pub/sub 广播任务认领事件。
- **workflow_service**: 加 `VibeGeneratingPipeline` — 不需用户写完整 prompt, 从 `dataset_service` 的素材库自动拉取历史生成记录作为风格参考, 一次性生成多版本。
- **frontend-v2**: 加 `KnowledgeGraphView` 组件 (参考 Obsidian graph view), 用 react-force-graph 展示 dataset 关系网络 (数据集-标注-评分-衍生任务)。

---

## 文章 5: Open-Generative-AI (5 工作室 + 200 模型 + 双轨架构)

### 文章主题

Open-Generative-AI (github.com/Anil-matcha/Open-Generative-AI) = 多媒体 AI 创作平台, 整合 200+ 模型, 5 个工作室 (Image/Video/Lip Sync/Cinema/Workflow), 双轨架构 (云端 Muapi.ai + 本地 stable-diffusion.cpp), 无内容审查。

### 关键工具/平台/技术

- **5 工作室**:
  - Image Studio: 文生图 50+ 模型, 图生图 55+ 模型 (Nano Banana 2 Edit 支持 14 张参考图)
  - Video Studio: 文生视频 40+, 图生视频 60+, 最长 10 秒, 1080p
  - Lip Sync Studio: 9 模型, 视频驱动 + 音频驱动
  - Cinema Studio: 推拉摇移 + 景深 + 焦距 + 运镜轨迹
  - Workflow Studio: 可视化节点图 (类似 ComfyUI 嵌入 Web 界面)
- **models.js**: 单一元数据源, 每个模型推理端点 + 输入参数 + 模型类型都在这, 前端读它决定 UI
- **双轨架构**: 云端 (Muapi.ai, 异步 POST+轮询) + 本地 (stable-diffusion.cpp + Metal GPU)
- **桌面三平台**: macOS (DMG), Windows (NSIS), Linux (AppImage/.deb)

### 借鉴到 VDP-2026 12 微服务的具体行动

- **asset_service**: 实现 `ModelRegistry` 单一元数据源 — `models_registry.yaml` (模仿 models.js), 含 model_id + provider + input_schema + output_schema + cost_per_call + capabilities, frontend 通过 `/api/v1/models` 拉取, 动态渲染表单。
- **workflow_service**: 加 `LocalInferenceBackend` — 在 D 盘 (项目机器) 部署 stable-diffusion.cpp + Ollama + LTX-Video, 视频/口型同步走云端, 图像可走本地。环境变量 `INFERENCE_BACKEND=local|cloud|hybrid`。
- **workflow_service**: 加 `AsyncPollingJob` 模式 — POST 提交任务→返回 task_id→前端轮询 GET, 适配 Open-Generative-AI 的 Muapi.ai 异步模式。
- **agent_service**: 借鉴 Lip Sync Studio 加 `AvatarService` (口型同步) — 接入 Wav2Lip/SadTalker/MuseTalk, 给数字人 agent 用。
- **dataset_service**: 借鉴 Cinema Studio 加 `CameraMotionAnnotation` — 推/拉/摇/移/景深/焦距 标注字段, 给镜头一致性检查用。
- **evaluation_service**: 加 `ModelsComparisonDashboard` — 同一 prompt 同时调用 5 个模型, 对比画质/耗时/费用/一致性得分。

---

## 文章 6: OpenMontage (Agent-First + 12 管线 + 52 工具 + 3 引擎 + 4 门禁)

### 文章主题

OpenMontage (github.com/calesthio/OpenMontage) = 首个开源 AI 编排式视频生产系统, "Agent-First" 架构 (YAML + Markdown 指令驱动 AI, Python 只作工具手), 12 条专业管线 + 52 工具 + 400 技能 + 3 渲染引擎 (Remotion/HyperFrames/FFmpeg) + 4 道质量门禁 + 预算控制 + 决策审计追踪。

### 关键工具/平台/技术

- **Agent-First**: 无 Python 编排器, AI 读取 YAML (管线清单) + Markdown (阶段导演技能) + Python 工具调用 + 自我审查 + 检查点 JSON
- **三层知识架构**:
  - L1 工具注册表 (有哪些工具/状态/费用)
  - L2 项目技能库 (OpenMontage 惯例 + 质量标准)
  - L3 深度技术知识 (模型/API 最佳实践)
- **12 条专业管线**: Animated Explainer / Cinematic / Animation / Talking Head / Screen Demo / Avatar Spokesperson / Podcast Repurpose / Clip Factory / Localization & Dub / Hybrid / Character Animation / Documentary Montage
- **52+ 工具 + 400 智能技能**: 视频 14 供应商 (Kling/Veo/Grok/MiniMax/HeyGen 等) + 图片 10 (FLUX/Imagen 4/DALL-E 3) + TTS 4 (ElevenLabs/Google/OpenAI/Piper) + 音乐 (Suno) + 后期 (FFmpeg/Real-ESRGAN/Wav2Lip)
- **3 大渲染引擎**: Remotion (React+Spring) / HyperFrames (HTML+GSAP) / FFmpeg (命令行), 锁定不可偷偷替换
- **4 道质量门禁**: ① 预合成验证 (六维分析重复画面/装饰视觉/弱动效) ② 后渲染自审 (ffprobe+帧采样+音频电平) ③ 源素材检查 ④ 供应商评分
- **预算控制**: 预估→锁定→核对, 观察/警告/封顶三模式, 单次 >$0.50 确认, 总预算默认 $10
- **决策审计追踪**: 每个供应商/风格/音乐选择都记录备选方案+置信度+理由
- **零 API 密钥也能做真视频**: Piper TTS + Archive.org/NASA + Remotion + FFmpeg

### 借鉴到 VDP-2026 12 微服务的具体行动

- **workflow_service**: 实现 `YAMLPipeline` — 每条管线是 YAML 配置 (research → proposal → script → scene_plan → assets → edit → compose), workflow_service 解析 YAML 编排 Celery 任务。这是 P4-6 主任务, 单独 5-10 轮深度开发。
- **agent_service**: 借鉴三层知识架构, 实现 `SkillRegistry` (L1 工具元数据) + `ProjectSkillBook` (L2 项目惯例, Markdown) + `ModelBestPractice` (L3 模型最佳实践), agent 决策前自动读取。
- **scoring_service**: 实现 `QualityGate` 六维评分 — 重复画面率/装饰视觉比例/弱动效比例/拍摄意图明确度/过度文字排版/电影感兑现率, 低于阈值 reject。
- **evaluation_service**: 加 `BudgetControl` — `WorkflowCostEstimate` (执行前预估) + `WorkflowCostLock` (锁定预算) + `WorkflowCostReconcile` (执行后核对), 三模式 (observe/warn/cap)。
- **workflow_service**: 加 `DecisionAuditTrail` 表 (decision_id + workflow_id + alternatives_considered JSONB + confidence + reason), 所有"为什么选 A 不选 B"全留痕。
- **workflow_service**: 加 `RenderEngineLock` — 渲染引擎 (Remotion/HyperFrames/FFmpeg) 在方案确认阶段就锁定, 中途不可静默降级, 不可用立即报阻塞。
- **dataset_service**: 借鉴 12 条管线, 在 dataset_builder 加 `PipelineTemplate` 字段, 支持 12 类预置管线模板 (Animated/Cinematic/Talking Head 等)。
- **workflow_service**: 加 `ZeroCostPath` — 零 API 密钥路径 (Piper TTS + Archive.org 素材 + Remotion 渲染 + FFmpeg 后期), 默认开, 用户没配 API Key 也能跑通。

---

## 文章 7: 10 个开源 Skill (内容创作流水线)

### 文章主题

10 个开源 Skill 覆盖内容创作全链路: guizang-ppt-skill / guizang-social-card-skill / awesome-gpt-image-2 / Humanizer-zh / Deep-Research-skills / anything-to-notebooklm / wewrite / Youtube-clipper-skill / oh-story-claudecode / marketingskills。核心思想: 一个 Skill 解决一个环节, 串起来就是内容生产线。

### 关键工具/平台/技术

- **通用 Skill**:
  - guizang-ppt-skill (PPT/HTML 演示页生成)
  - guizang-social-card-skill (社媒卡片/小红书轮播)
  - awesome-gpt-image-2 (提示词素材库)
  - Humanizer-zh (AI 腔→人话润色)
  - marketingskills (营销工具箱)
- **专用 Skill**:
  - Deep-Research-skills (带出处的深度研究)
  - anything-to-notebooklm (一稿多用: 文章→播客/PPT/导图)
  - wewrite (公众号写作一条龙)
  - Youtube-clipper-skill (长视频切短视频)
  - oh-story-claudecode (网文/故事选题)
- **串联工作流**: 调研→营销定位→写作→润色→配图→卡片→PPT→剪辑→故事拆解→多模态

### 借鉴到 VDP-2026 12 微服务的具体行动

- **extended_skills_pkg**: 实现 10 个 skill (一一对应), 每个 skill 是一个独立 Python 模块, 路径 `nanobot_factory_backend/extended_skills_pkg/skills/`。
  - `ppt_skill.py` (PPT 生成) — 用 python-pptx + LLM 草稿
  - `social_card_skill.py` (社媒卡片) — 用 PIL + 模板
  - `image_prompt_skill.py` (配图提示词库)
  - `humanizer_skill.py` (润色 AI 腔) — 用 LLM 改写
  - `research_skill.py` (深度研究, 带引用)
  - `notebooklm_skill.py` (一稿多用)
  - `wewrite_skill.py` (公众号写作)
  - `youtube_clipper_skill.py` (视频切片 + WhisperX)
  - `story_skill.py` (网文拆解)
  - `marketing_skill.py` (营销文案)
- **agent_service**: 加 `SkillOrchestrator` — 智能串联 skill, 用户说"做一个 X 主题公众号文章", 自动链: research→marketing→wewrite→humanizer→image_prompt→social_card→notebooklm。
- **frontend-v2**: 加 `SkillMarketplace` 页面, 列出全部 skill, 每个展示描述/输入/输出/示例, 用户可启用/禁用/贡献新 skill。

---

## 文章 8: Hindsight (Hermes 智能长效记忆升级)

### 文章主题

Hindsight = Hermes 智能长效记忆升级方案 (Memory Provider 插件), 三字诀"存/查/学"。4 层结构: USER.md (1,375 字符, 个人画像) + MEMORY.md (2,200 字符, 项目约定) + 触发器 (自动 10 轮/事件即时/手动) + 手动工具 (recall/retain/reflect)。Local-first + 云端 (Vectorize) 双模式。

### 关键工具/平台/技术

- **三字诀**:
  - 存: 每次对话自动归档为"会生长的工作档案"
  - 查: 提问前自动召回相关旧档案
  - 学: 用久了自动总结"原来这人做 PPT 有这些习惯"
- **触发条件**: 自动轮次 (默认 10 轮) + 事件即时触发 (纠正错误/完成标准流程) + 手动触发 (`/reflect`)
- **手动工具**: `hindsight_recall` / `hindsight_retain` / `hindsight_reflect`
- **指令**: `#nomem` (跳过本轮保存) / `#global` (存入全局)
- **Vectorize**: 云端托管服务, 需注册 API Key
- **局限**: 原生 USER.md/MEMORY.md 容量锁死 + 中途改需求不生效 + 只记结论不记过程 + 多个客户信息混杂

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 实现 `MemoryProvider` 抽象接口, 本地实现用 SQLite + sqlite-vec + PGVector (Postgres 已有 alembic 迁移), 云端实现用 Vectorize (参考 Vectorize API 文档)。
- **agent_service**: 加 `HindsightLike` 长效记忆系统 (L0-L3 四层):
  - L0: Identity (agent 角色 + 用户偏好, 类似 USER.md)
  - L1: Essential Story (从记忆库提取压缩版长期背景)
  - L2: Topic Recall (按项目/话题触发召回)
  - L3: Semantic Search (完整语义搜索)
  - 借鉴 MemPalace 的 4 层设计, 比 Hindsight 的 USER/MEMORY 二层更强。
- **agent_service**: 加 `ReflectTrigger` — 自动 10 轮触发 + 事件触发 (用户纠正/任务完成) + 手动触发 (slash command `/reflect`), 触发后 LLM 总结会话提炼通用规则。
- **workflow_service**: 加 `ProjectContextIsolation`, 借鉴 Hindsight 局限分析, 多个项目记忆物理隔离 (Wing/Room 模式, 见文章 13 MemPalace)。

---

## 文章 9: FastVideo / Dreamverse (5 秒 1080p, 4.55 秒出)

### 文章主题

UCSD Hao AI Lab 开源 FastVideo 框架 + Dreamverse, 5 秒 1080p 视频 4.55 秒出完 (比播放还快)。"氛围直控 Vibe Directing" — 聊天式迭代, "把背景换成黄昏海滩"几秒画面变。NVIDIA Dynamo 官方后端, Apache-2.0 (3.7k stars)。

### 关键工具/平台/技术

- **Vibe Directing**: 不用一长串精确 prompt, 直接说话, 一段一段调
- **多模态生成**: 文字出片 + 图片转视频 + 音频一起生成
- **后训练任你调**: 自有数据微调 + 模型压缩 + 多卡并行训练
- **部署方式**: pip 装 / Docker 跑 / 远程服务器 / 没 GPU Mock 调试
- **4 优化技巧**: 模型压缩省显存 + 硬件加速提速度 + 编译优化消除延迟 + 边生成边播放
- **竞品对比**:
  - Kling 3.0 (快手) — 性价比好 (免费额度+Pro $5.99/月), 但传统模式
  - Veo 3.1 (Google) — 4K 原生, 但 Fast 模式 55 秒/8 秒
  - Runway Gen-4 — 专业级 ($12/月起), 过于专业
- **现状**: 实时模式锁 B200, 适配 RTX 5090/4090 进行中; LTX-2 画质中游 (低于 Veo 3.1/Kling 3.0)
- **NVIDIA Dynamo**: FastVideo 是 Dynamo 官方后端, 硬件生态保障

### 借鉴到 VDP-2026 12 微服务的具体行动

- **workflow_service**: 实现 `VibeDirectingPipeline` — 用户用自然语言迭代 ("把背景换成黄昏海滩"), workflow_service 通过 LLM 解析 + 局部重渲染 (只改背景不改前景), Celery 异步任务, 用 WebSocket 推流进度。
- **workflow_service**: 加 `LocalGPUBackend` — 集成 FastVideo 的 stable-diffusion.cpp + LTX-Video, 用户有 GPU 时本地推理 (省费用), 无 GPU 时降级到云端。
- **workflow_service**: 加 `ModelCompressionPipeline` — 借鉴 FastVideo 的模型压缩, 用 onnxruntime/TensorRT 压缩 video model, 显存降低 50%, 推理速度提升 2x。
- **asset_service**: 加 `IterateGenerationSession` 表 (session_id + previous_frame_id + current_frame_id + diff + user_instruction), 支持"边生成边迭代", 完整保存迭代链路。
- **monitoring**: 借鉴 FastVideo 4 优化技巧, 加 `VDPGenerationLatency` Prometheus 指标, 按 (模型压缩率 / 硬件加速类型 / 编译优化级别 / 流式输出) 4 维切片。
- **evaluation_service**: 加 `IterationCostEstimator` — 每次 vibe directing 迭代计算"出片速度/出片质量/费用/迭代次数", 给用户推荐最佳迭代策略。

---

## 文章 10: ComfyUI + Seedance 2.0 + LLM 三模块导演台

### 文章主题

ComfyUI 官方 2026-06-19 发推演示: 分镜→Seedance 2.0→LLM 分析→视频生成, "AI 视频的导演模式"。LLM 出分镜→图像模型出分镜板→Seedance 2.0 动起来。ComfyUI 118k stars, Netflix/Amazon/Apple/Ubisoft 实际采用, 真正故事是"胶水" (可视化节点总线)。

### 关键工具/平台/技术

- **三模块管线**: LLM (结构化翻译) + 图像模型 (视觉锚定) + 视频模型 (运动执行)
- **Seedance 2.0**: 字节跳动, 最多 9 图 + 3 视频 + 3 音频 + 文本 = ~12 资产上限, "Reference Anything" 自然语言标签引用任意资产
- **分镜 vs 视频提示词分工**:
  - 图像提示: 极度详细 (角色 ID / 服装 / 面板编号 / 技术注释)
  - 视频提示: 极其精简 (只写运动和相机)
- **关键洞察**: "A storyboard is usually a visual guide for composition, motion, pacing, and intent. Not a frame-by-frame contract." (CEO 回复)
- **实战案例**:
  - Scan My Outfit (伦敦街头): 7 面板分镜板 + 一次成功
  - 中世纪集市: 12 面板长序列, 单图失败 5 次+ → 同组分镜板一次跑通
- **motivated camera movement**: 相机移动由场景内动作驱动, 没有漫无目的的随机运镜
- **ComfyUI 架构**: 无限画布节点图, 分组迭代, 旁路开关, 模型/LLM/图像/视频/音频节点可替换
- **Comfy Hub**: 模板市场, 搜"storyboard"或"seedance"有多个可加载模板

### 借鉴到 VDP-2026 12 微服务的具体行动

- **workflow_service**: 实现 `StoryboardToVideoPipeline` (仿 ComfyUI 工作流), 用户上传剧本 → LLM (Qwen/Claude) 出 8-12 面板分镜 JSON → 图像模型 (FLUX/SD) 出生成分镜板 → 视频模型 (MiniMax/Veo/Kling/Seedance) 动起来。Celery 4 步链。
- **agent_service**: 加 `MultiModalReferenceGenerator`, 借鉴 Seedance 2.0 的 "Reference Anything" 模式, 输入 (N 张图 + M 段视频 + K 个音频 + 文本), 自然语言标签引用 ("第二格到第四格用斯坦尼康跟拍")。
- **workflow_service**: 加 `PromptSplitPolicy` — 图像提示词极度详细 + 视频提示词极其精简, 用 Pydantic schema 强制分隔 (image_prompt + video_prompt 两个字段)。
- **asset_service**: 实现 `StoryboardPanel` 实体 (panel_id + scene_description + shot_size + camera_movement + character_id + duration_seconds + image_asset_id), dataset_service 加 `StoryboardDataset` 集合。
- **frontend-v2**: 加 `StoryboardEditor`, 三栏 (左: 面板列表, 中: 预览, 右: 属性+提示词), 支持多版本管理 + 跨分镜参考图引用 + ControlNet 骨骼控制 (借鉴 Jellyfish 三栏编辑器)。
- **workflow_service**: 实现 `MotivatedCameraMovementGenerator`, LLM 解析分镜因果关系, 自动生成"motivated"相机运动指令 ("马拉车横穿集市 → 镜头跟随车移动 → 横幅扫过画面揭示鸡群"), 避免漫无目的运镜。

---

## 文章 11: ORION-Global-Workspace (GWT 工程实现)

### 文章主题

ORION-Global-Workspace (github.com/Alvoradozerouno/ORION-Global-Workspace, 2026-02 首次提交), 4 个 Python 文件实现 GWT (全局工作空间理论) 完整工程实现: workspace.py + modules.py + broadcast.py + competition.py。把"哲学+认知科学"问题变成"工程问题"。

### 关键工具/平台/技术

- **GWT (Global Workspace Theory)**: Bernard Baars 1988 提出, Stanislas Dehaene 2014 获 Brain Prize 神经科学验证
- **理论核心**: 意识 = 信息被"广播"到一个全局工作空间, 让多个专门处理模块可以同时访问
- **ORION 4 文件**:
  - `workspace.py`: 中央信息枢纽 (所有模块往这里发信息, 胜出的信息被广播回所有模块)
  - `modules.py`: 专门处理模块 (视觉/听觉/记忆/情绪...)
  - `broadcast.py`: 信息广播机制 (模块之间传递信息)
  - `competition.py`: 竞争机制 (多个信息争抢进入全局工作空间)
- **意义**: 把"哲学+认知科学"问题变成"工程问题", 可证伪 + 可迭代 + 可商业化
- **三种人反应**: AI 工程师 (兴奋) + 认知科学家 (谨慎乐观) + 哲学家 (失眠)

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 实现 `GlobalWorkspace` 中央信息枢纽 (仿 ORION workspace.py), 所有 agent 模块 (vision/audio/memory/emotion/tool) 信息发到 workspace, 胜出的信息广播回所有模块。
- **agent_service**: 实现 `ModuleCompetition` 机制 (仿 ORION competition.py), 多个候选 action 竞争进入 execution context, 选择标准 (置信度/费用/延迟/成功率) 加权评分。
- **agent_service**: 实现 `BroadcastMechanism` (仿 ORION broadcast.py), 关键决策广播给所有 agent (pub/sub 模式, Redis/Kafka), 保证所有 agent 看到一致上下文。
- **research**: ORION-Global-Workspace 是认知科学理论工程实现的范式, 启示 VDP-2026 的 agent_service 设计应"理论驱动"而非"经验驱动", 在 P4-3 升级时引入。

---

## 文章 12: claude-obsidian (Karpathy LLM Wiki 实践)

### 文章主题

claude-obsidian (github.com/AgriciDaniel/claude-obsidian, 7200 stars), Karpathy 2026-04 的 LLM Wiki 理念实践: 让 LLM 自己读/链接/维护资料, 把碎片组织成"互联的知识网" (compounding knowledge, 知识复利)。Claude 自己读, 抽出实体页 (人物/机构/项目) + 概念页 (理论/模式/方法) + 来源页 (原始材料), 自动建双向交叉引用 + 矛盾检测 + 8 类健康检查 + 会话记忆 hot.md, 纯本地 Markdown (无 DB)。

### 关键工具/平台/技术

- **三页模式**: 实体页 (人/机构/项目) + 概念页 (理论/模式/方法) + 来源页 (原始材料)
- **自动双向交叉引用**: 抽概念时自动链接到相关实体
- **矛盾检测**: 笔记里互相冲突的论点会发现, 标出来并附上来源
- **会话记忆**: hot.md, 每次会话结束自动更新, 下次开局不用重交代
- **8 类健康检查**: 孤儿笔记 / 死链 / 过期声明 / 缺失引用
- **可视化**: /canvas 命令打开画布, 符合 Obsidian JSON Canvas 1.0 规范
- **跨项目复用**: 在任何 Claude Code 项目的 CLAUDE.md 加引导, 读这个 vault 当知识库
- **安装方式**: git clone + bash setup-vault.sh 或 Claude Code plugin marketplace

### 借鉴到 VDP-2026 12 微服务的具体行动

- **dataset_service**: 实现 `KnowledgeGraph` — 把数据集/标注/任务/资产的关系建成知识图谱 (用 Neo4j/PostgreSQL+AGE), 借鉴 claude-obsidian 的"实体+概念+来源"三页模式, 加自动双向引用 + 矛盾检测。
- **agent_service**: 加 `HotContext` (类似 hot.md), 每次会话结束 LLM 总结 200 字摘要存到 `agent_session_hot_context` 表, 下次开局自动加载。
- **dataset_service**: 加 `KnowledgeHealthChecker`, 借鉴 8 类健康检查 (孤儿数据集 / 死链 / 过期标注 / 缺失引用), 定期巡检, 暴露 `/api/v1/health/knowledge` 端点。
- **agent_service**: 实现 `CrossProjectKnowledgeReuse`, 在任何 agent prompt 里加 `@wiki:vault/` 前缀, 自动加载全局知识库 (类似 CLAUDE.md 引导)。
- **frontend-v2**: 加 `CanvasView` 组件 (符合 JSON Canvas 1.0 规范), 用户可视化画布布局数据集关系, 拖拽式编辑。

---

## 文章 13: MemPalace (AI 记忆宫殿, 56.2k stars)

### 文章主题

Milla Jovovich (生化危机 Alice) 开源 MemPalace (github.com/mempalace/mempalace, 56.2k stars), local-first AI 记忆宫殿。"逐字存储 verbatim storage" (不擅自取舍原文), 6 层导航 Wing/Room/Hall/Closet/Drawer/Tunnel + 4 层 Memory Stack (L0 Identity→L1 Essential Story→L2 Wing 召回→L3 完整语义搜索) + 时间知识图谱 (SQLite 实体关系), LongMemEval R@5 96.6%, MCP 协议, ChromaDB/sqlite_exact/Qdrant/pgvector 后端, uv 安装。

### 关键工具/平台/技术

- **6 层导航 (隐喻古希腊记忆宫殿)**:
  - Wing (翼): 一个人/项目/长期主题
  - Room (房间): Wing 里的具体话题 (auth-migration/graphql-switch/ci-pipeline)
  - Hall (大厅): 记忆类型 (事实/事件/发现/偏好/建议)
  - Closet (壁橱): 类似 Hall 但更细分
  - Drawer (抽屉): 原始文本片段 (未摘要)
  - Tunnel (隧道): 跨翼连接
- **4 层 Memory Stack**:
  - L0 Identity: AI 身份 + 工作关系
  - L1 Essential Story: 最重要的历史片段压缩版
  - L2 Wing 触发: 按项目/话题触发的主题召回
  - L3 完整语义搜索: 深度检索
- **逐字存储 (Verbatim)**: 不擅自摘要/改写/抽取事实, 把原始内容存入 Drawer
- **可插拔后端**: ChromaDB (默认) / sqlite_exact / Qdrant / pgvector
- **时间知识图谱**: SQLite 记录实体关系, 支持添加/查询/失效/时间线追踪
- **MCP 协议**: 集成 Claude Code / Cursor / ChatGPT, 自动保存 hooks + agents 管理
- **CLI 命令**: `mempalace init` / `mine` / `search` / `wake-up`
- **性能**: LongMemEval R@5 96.6%

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 实现 `MemoryPalaceLike` 6 层导航 (Wing/Room/Hall/Closet/Drawer/Tunnel), 表设计 `memory_wings` (id+name+project_id) / `memory_rooms` (id+wing_id+topic) / `memory_halls` (id+room_id+type) / `memory_drawers` (id+room_id+raw_text+embedding+created_at) / `memory_tunnels` (id+from_wing_id+to_wing_id+relation)。
- **agent_service**: 实现 4 层 Memory Stack (L0/L1/L2/L3), 仿 MemPalace, 与 Hindsight (文章 8) 设计融合, 产出 VDP-2026 自己的"长效记忆"系统。
- **agent_service**: 借鉴 Verbatim 存储, 不擅自摘要, 原始消息全保存到 drawer, 只在 L1 提取时做压缩。
- **agent_service**: 加 `MemoryPalaceBackend` 抽象接口, 默认 ChromaDB (本地轻量), 也支持 pgvector (Postgres 已有) / Qdrant (集群), 配置文件切换。
- **agent_service**: 加 `TimeKnowledgeGraph`, 实体关系 + 时间线, 用 SQLite 实体关系表 + Neo4j 关系图谱混合实现。
- **agent_service**: 实现 MCP 协议服务, 暴露 `mempalace_search` / `mempalace_wake` / `mempalace_retain` 工具给 Claude Code / Cursor / Codex 集成。
- **agent_service**: 加 `VerbatimStorage`, 用 PG `jsonb` 存原始文本, vector 列存 embedding, L1 压缩版本存在另一张表 `memory_l1_compressed`。

---

## 文章 14: CyberVerse (实时数字人 Agent, 1.2k stars)

### 文章主题

CyberVerse (github.com/Lynpoint/CyberVerse / 另一个 github.com/dsd2077/CyberVerse, 1.2k stars), 开源实时数字人 Agent 框架, 一张照片让数字人活过来。基于 WebRTC + PersonaAgent/SubAgent 多 Agent 架构, 可选 FlashHead/LiveAct Avatar 后端 (照片驱动实时面部动画 + 口型同步), omni 模型 + LLM + TTS + ASR + Embedding + RAG 全插件化 (cyberverse_config.yaml), 在 /settings 配置 API Key。

### 关键工具/平台/技术

- **实时语音 Agent**: 麦克风连续交流, 模型说话时可打断, 同一会话混合语音/文本
- **WebRTC 音视频**: P2P 直连 (TURN/NAT 穿透) 或 LiveKit SFU, 兼顾低延迟+复杂网络
- **摄像头/屏幕帧输入**: Agent 可"看见"用户摄像头或屏幕共享 (omni 会话)
- **PersonaAgent + SubAgent 架构**:
  - PersonaAgent: 前台驻守, 与用户保持流畅对话+快速响应打断+上下文切换
  - SubAgent: 后台异步执行搜索/调研/资料整理/HTML 报告
- **角色记忆 + RAG**: 会话历史持久化本地磁盘, 知识库/文档/人物生平导入建索引
- **可选数字人视频**: FlashHead / LiveAct 后端, 一张照片驱动面部动画+口型同步, 无 GPU 时退化纯语音
- **插件化技术栈**: cyberverse_config.yaml 配置 omni 模型 + LLM + TTS + ASR + Embedding + RAG + 工具调用 + Avatar 后端
- **环境**: Node 18+ / Go 1.25 / Conda Python 3.10+ / FFmpeg + libopus
- **启动**: 3 终端 (Python 推理 + Go API + 前端) — make inference + make server + make frontend, 端口 5173
- **Avatar 模式额外**: CUDA 12.8+ GPU + PyTorch 2.8 + FFmpeg libvpx + SoulX-FlashHead-1_3B 模型

### 借鉴到 VDP-2026 12 微服务的具体行动

- **agent_service**: 实现 `RealtimeVoiceAgent`, 集成 WebRTC (用 LiveKit 或 mediasoup), 支持语音打断 + 语音/文本混合输入。
- **agent_service**: 实现 `PersonaAgent + SubAgent` 双层架构, 借鉴 CyberVerse 模式 — PersonaAgent 前台驻守对话, SubAgent 后台异步执行耗时任务 (搜索/调研/资料整理/HTML 报告生成), 用户继续说话, 待 SubAgent 完成再回传。
- **asset_service**: 加 `AvatarService` 集成 FlashHead / LiveAct / SadTalker / MuseTalk / Wav2Lip 后端, 一张照片驱动面部动画 + 口型同步, 给数字人 agent 用。配置 `avatars.yaml` 切换后端。
- **agent_service**: 插件化技术栈 — 加 `AgentConfig` Pydantic 模型, 支持 omni 模型 + LLM + TTS + ASR + Embedding + RAG + 工具调用 + Avatar 后端自由组合, 用户在 `/settings` 配 API Key。
- **workflow_service**: 加 `RealtimeAvatarWorkflow`, 借鉴 CyberVerse "可选数字人视频" 模式 — 无 GPU 时退化纯语音 Agent (同一套角色/人设配置继续用), 有 GPU 时升级实时 Avatar。
- **frontend-v2**: 加 `VoiceChatUI` 组件, 麦克风按钮 + 实时波形 + 打断手势, 端口 5173 风格, 用 React + WebRTC API。
- **notification_service**: 加 `RealtimeNotification` WebSocket 推送, SubAgent 完成后立即推送给 PersonaAgent, 用户感受到"无缝对话"。

---

## 总结

14 篇文章覆盖 2026 年 AI Agent / 多模态生成 / 记忆系统 / 工作流编排 4 大前沿方向, 共提炼出 **70+ 条具体行动** 映射到 VDP-2026 的 12 微服务, 见 `research/p4_master_report.md` 第 3 章完整借鉴清单。

**最重要的 3 个借鉴方向**:

1. **Agent-First 工作流架构** (OpenMontage, Open-Generative-AI, ComfyUI) → VDP-2026 workflow_service 应改造成"AI 编排总线", YAML+Markdown 指令驱动, Python 仅作工具手
2. **长效记忆宫殿** (MemPalace, Hindsight, claude-obsidian) → VDP-2026 agent_service 应实现 4-6 层记忆系统, Wing/Room/Hall/Closet/Drawer/Tunnel + L0-L3 Memory Stack
3. **多模态参考生成** (Seedance 2.0, ComfyUI, FastVideo) → VDP-2026 asset_service + workflow_service 应支持 Reference Anything + 边生成边迭代 + motivated camera movement