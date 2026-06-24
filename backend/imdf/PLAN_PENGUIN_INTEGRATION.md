# Penguin Canvas v2.1.4 → IMDF 复刻计划

## 概述
将 Penguin Canvas v2.1.4 (React+TS+Electron) 的 16 个核心功能点复刻到 IMDF (Python+FastAPI) 中。
IMDF 是纯 Python 后端 + Web UI (FastAPI)，采用模块化引擎架构。

## 16 功能点分析

### 1. 3D全景/导演台/小人/姿势/遮挡板/导演视角/放大模式/多帧模式/动作生成/关节调节
- **源码位置**: `src/components/nodes/Panorama3DNode.tsx` (6062行), `src/utils/panorama3d.ts` (3217行), `src/components/nodes/PoseMasterNode.tsx` (3894行)
- **实现细节**:
  - Panorama3DNode: Three.js 360° 全景查看器，支持摄像机机位书签、热点导览、全景生成、多帧动作序列
  - PoseMasterNode: MediaPipe PoseLandmarker 姿态检测+手部控制，18个关节调节，100+动作预设，自然语言动作生成
  - panorama3d.ts: 完整类型系统(PanoramaCameraView/PanoramaHotspot/PanoramaAvatar)、生成提示词构建、动作规划器
- **IMDF方案**: 纯Python后端 + Three.js Web UI
  - `engines/data/data_3d.py` — 3D场景管理、姿势库、动作生成逻辑
  - `api/canvas_3d.py` — REST API端点 (姿势库CRUD、场景管理、动作规划)
  - 前端用 Three.js CDN + 节点式UI (通过 canvas_web.py 嵌入)
- **依赖**: numpy, three.js (CDN), mediapipe (姿势检测可选)
- **优先级**: P0 (核心差异化功能)
- **集成点**: `core/canvas_core.py` 新增 ElementType.PANORAMA_3D, ElementType.POSE_MASTER

### 2. Figma联动
- **源码位置**: `tools/figma-bridge/` (server.cjs, plugin/), `backend/src/routes/figma.js`, `backend/src/utils/figmaBridge.js`
- **实现细节**: 后端启动 localhost:3845 bridge；Figma插件轮询/claim导入素材；POST /api/figma/import 将素材放入队列
- **IMDF方案**: 纯Python后端端点 + Web UI 按钮
  - `api/figma_bridge.py` — Figma导入API端点 (素材队列管理)
  - 前端画布素材右键 → "发送到Figma" → POST /api/figma/bridge/import
- **依赖**: 无额外依赖 (纯HTTP协议)
- **优先级**: P1
- **集成点**: `engine_router.py` 新增 FigmaBridgeEngine；canvas_web.py 添加素材上下文菜单

### 3. 阿里云OSS及腾讯云COS
- **源码位置**: `backend/src/cloudUploads/` (settings.js + uploader.js), `backend/src/routes/cloudUploads.js`
- **实现细节**: 完整COS V5签名、OSS Header Authorization签名；配置检查(signed GET)、上传、错误分类；MIME/扩展名映射
- **IMDF方案**: `api/cloud_storage.py` — 通用OSS/COS接口
  - 支持腾讯云COS (V5签名) + 阿里云OSS (Header Authorization)
  - 配置检查、文件上传、对象键生成、错误分类
  - 设置管理
- **依赖**: requests/httpx (无额外SDK)
- **优先级**: P1
- **集成点**: canvas_web.py 配置面板新增云存储设置

### 4. 放置栏(快速调整素材位置)
- **源码位置**: (features.json "放置栏恢复" in v2.1.4 highlights)
- **实现细节**: 左下角折叠栏，显示最近5/20个素材节点，拖拽卡片移动原节点
- **IMDF方案**: 纯前端组件 (通过canvas_web.py HTML模板嵌入)
  - 记录最近使用素材节点
  - 折叠/展开UI
- **依赖**: 无
- **优先级**: P2
- **集成点**: canvas_web.py 画布状态tracker

### 5. veo-omni (10秒1积分)
- **源码位置**: VideoNode.tsx (veo-omni-10s 分支), 后端 `/v1/videos` multipart协议
- **实现细节**: 模型值映射(veo-omni-10s → omni_flash-10s)，需1张参考图，16:9 10秒
- **IMDF方案**: `engines/video_engine.py` 扩展 veo_omni_provider
  - 调用外部API (兼容OpenAI格式)
  - 模型映射、参考图处理、任务轮询
- **依赖**: httpx
- **优先级**: P2
- **集成点**: VideoEngine新增VeoOmniMode

### 6. 提示词模板系统 (文本+视频+图像+音频)
- **源码位置**: `src/data/promptTemplateLibrary.ts`, `src/services/promptTemplateLibrary.ts`, `src/components/PromptTemplateLibraryModal.tsx`, `PromptTextarea.tsx`
- **实现细节**: 图像/视频双库切换、内置模板(每类≥100)、自定义模板、媒体附件、导入导出、分类管理
- **IMDF方案**: `api/prompt_templates.py` + 前端模态框
  - 内置模板JSON数据
  - 自定义模板CRUD (SQLite或JSON文件)
  - 分类管理、导入导出
- **依赖**: 无
- **优先级**: P1
- **集成点**: canvas_web.py 新增提示词模板路由和WebSocket事件

### 7. ComfyUI remote模式 + Docker
- **源码位置**: `backend/src/providers/comfyui.js`, `comfyuiAccess.js`, `src/components/nodes/ComfyUIStoreNode.tsx`, Dockerfile
- **实现细节**: ComfyUI API adapter、安全校验(默认localhost)、高危开关(allowRemote)、Docker部署入口
- **IMDF方案**: `engines/comfyui_engine.py`
  - ComfyUI API代理
  - 地址安全校验
  - Workflow模板管理
- **依赖**: httpx, websockets
- **优先级**: P2
- **集成点**: EngineRouter新增ComfyUIEngine

### 8. NewAPI分组令牌高级模式
- **源码位置**: features.json v2.1.1 section - 公开扩展插槽+providerParams透传
- **实现细节**: API Key分组管理(通用Key/分类独立Key)、providerParams透传、清空按钮
- **IMDF方案**: `api/api_key_manager.py` — API Key管理端点
  - 分组Key管理 (通用/分类)
  - 清空/测试功能
- **依赖**: 无
- **优先级**: P2
- **集成点**: canvas_web.py 设置面板

### 9. LLM/VISION节点流式删除
- **源码位置**: features.json v2.1.2 highlights - 删除某条assistant流式结果
- **实现细节**: 手动删除某条生成结果，同步刷新输出字段
- **IMDF方案**: 前端组件增强
  - LLM输出区删除按钮
  - 状态同步清理
- **依赖**: 无
- **优先级**: P3
- **集成点**: canvas_web.py WebSocket消息处理

### 10. 分类独立APIKEY删除功能
- **源码位置**: features.json v2.1.1 highlights
- **实现细节**: 每个分类API Key设置增加清空按钮
- **IMDF方案**: 前端UI增强 (API设置面板清空按钮)
- **依赖**: 无
- **优先级**: P3
- **集成点**: canvas_web.py 设置面板

### 11. 素材拖到浏览器外文件夹 (Electron)
- **源码位置**: features.json v2.1.2 highlights - DownloadURL/text/uri-list拖拽数据
- **实现细节**: 图像/视频/音频素材写入DownloadURL/text/uri-list，支持浏览器拖到外部文件夹
- **IMDF方案**: 前端HTML5拖拽API增强
  - 素材元素设置 draggable + dataTransfer 数据
- **依赖**: 无
- **优先级**: P3
- **集成点**: canvas_web.py canvas元素渲染

### 12. 即梦CLI + Seedance2.0 + Seedream4.5-5.0
- **源码位置**: `backend/src/providers/jimengCli.js` (784行), VideoNode.tsx seedance分支
- **实现细节**: dreamina CLI包装(WSL兼容)、模型版本管理(seedream-4.5~5.0, seedance2.0变体)、分辨率管理
- **IMDF方案**: `engines/jimeng_engine.py`
  - dreamina CLI包装器
  - 模型版本映射
  - WSL兼容
- **依赖**: subprocess, (可选) WSL检测
- **优先级**: P2
- **集成点**: EngineRouter新增JimengEngine

### 13. 上游文本联动@模式
- **源码位置**: `src/components/nodes/MentionPromptInput.tsx`, `mediaMentions.ts`
- **实现细节**: @弹出上游素材选择列表(图像/视频/音频/文本)，选中后插入引用标记
- **IMDF方案**: 前端组件(MentionPromptInput)
  - @触发上游素材列表
  - 选中后插入引用标记
  - 运行时解析引用为实际素材URL
- **依赖**: 无
- **优先级**: P1
- **集成点**: canvas_web.py 所有文本输入框

### 14. 画布教程模块
- **源码位置**: src/App.tsx (CANVAS_TUTORIALS常量, 9个教程入口)
- **实现细节**: 顶部栏入口→弹出浮层→Bilibili/YouTube链接列表
- **IMDF方案**: 前端组件(静态URL列表)
  - 教程JSON数据
  - 浮层UI
- **依赖**: 无
- **优先级**: P3
- **集成点**: canvas_web.py 顶部栏

### 15. 圣斗士主题 (附加)
- **源码位置**: 全面覆盖圣斗士主题、宝箱、战斗、十二宫
- **IMDF方案**: 前端主题系统扩展 (非Python后端)
- **优先级**: P4

### 16. FAL工具箱 (附加)
- **源码位置**: 40+ endpoint, Fal超市节点, 3D模型预览
- **IMDF方案**: 外部API代理层
- **优先级**: P4

## 依赖清单 (汇总)
| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| numpy | 3D计算 | pip install numpy |
| httpx | HTTP客户端(云存储/API代理) | pip install httpx |
| three.js | 3D全景Web渲染 | CDN (已内嵌) |
| websockets | ComfyUI实时 | pip install websockets |
| ffmpeg | 视频处理(已有) | 系统安装 |

## 优先级矩阵
| 优先级 | 功能 | 估算工时 |
|--------|------|---------|
| P0 | 3D全景/导演台/姿势库 | 8h |
| P1 | 提示词模板系统 | 4h |
| P1 | 云存储集成 | 4h |
| P1 | Figma联动 | 3h |
| P1 | @上游文本联动 | 3h |
| P2 | 放置栏 | 2h |
| P2 | veo-omni | 4h |
| P2 | ComfyUI remote | 6h |
| P2 | NewAPI分组令牌 | 3h |
| P2 | 即梦CLI/Seedance | 6h |
| P3 | LLM流式删除 | 1h |
| P3 | API KEY清空 | 1h |
| P3 | 素材拖出文件夹 | 2h |
| P3 | 画布教程模块 | 1h |
| P4 | 主题扩展 | 4h |
| P4 | FAL工具箱 | 8h |

## 现有IMDF引擎集成点
| IMDF组件 | 需要扩展内容 |
|-----------|-------------|
| `core/canvas_core.py` | 新增 ElementType: PANORAMA_3D, POSE_MASTER, MODEL_3D |
| `engines/video_engine.py` | 新增 VeoOmniMode, SeedanceMode |
| `engines/engine_router.py` | 新增 ComfyUIEngine, JimengEngine, FigmaBridgeEngine |
| `api/canvas_web.py` | 新增路由: 3D API, 云存储, 提示词模板, Figma |
| `core/scene_graph.py` | 新增3D场景图节点类型 |
