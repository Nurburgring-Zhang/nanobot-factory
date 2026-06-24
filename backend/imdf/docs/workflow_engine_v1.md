# IMDF 节点化工作流引擎架构 v1.0 — 工程视角

## 核心概念：三层节点 + 自由组合

用户可以通过拖拽组合"维度节点→能力节点→功能节点"形成任意工作流。

```
工作流模板 = [维度节点] × [能力节点] × [功能节点] 的有向无环组合
               ↓
        例: 商品图片标注管线
        数据接入(维度) → 图片采集(能力) → Web爬虫(功能)
                       → 图片清洗(能力) → 去重(功能) + 质量评分(功能)
                       → AI预标注(能力) → BBox检测(功能) → 人工审核(功能)
                       → 数据交付(维度) → COCO导出(能力) → 版本标记(功能)
```

### 1. 维度节点(Dimension Node)

代表数据生产的完整阶段。共8个维度节点：
```
DIM_INGESTION    = "数据接入"    颜色: #4A90D9
DIM_PROCESSING   = "数据处理"    颜色: #50C878
DIM_MANAGEMENT   = "数据管理"    颜色: #FFB347
DIM_ANNOTATION   = "标注生产"    颜色: #E74C3C
DIM_QUALITY      = "评测质量"    颜色: #9B59B6
DIM_COLLAB       = "团队协作"    颜色: #1ABC9C
DIM_OPS          = "运营分析"    颜色: #34495E
DIM_PLATFORM     = "平台工程"    颜色: #7F8C8D
```

### 2. 能力节点(Capability Node)

维度下的子阶段。共60个能力节点：
```
例: 数据接入(维度)下的能力节点:
  CAP_COLLECTOR   = "采集器"
  CAP_PARSER      = "格式解析"  
  CAP_ROUTER      = "数据路由"

例: 标注生产(维度)下的能力节点:
  CAP_2D_TOOLS    = "2D标注工具"
  CAP_3D_TOOLS    = "3D标注工具"
  CAP_VIDEO       = "视频标注"
  CAP_AUDIO       = "音频标注"
  CAP_SAM         = "SAM自动分割"
  CAP_AI_PRELABEL = "AI预标注"
  CAP_TRACKING    = "跟踪标注"
  CAP_MEDICAL     = "医学影像"
```

### 3. 功能节点(Function Node)

具体的可执行单元。每个功能节点包含：
```
{
  "id": "FN_001",           // 全局唯一ID
  "name": "Web爬虫采集",     // 中文名
  "dimension": "DIM_INGESTION",
  "capability": "CAP_COLLECTOR",  
  "type": "executor",       // executor/trigger/condition/gateway
  "params": {               // 参数配置
    "url": "",
    "depth": 1,
    "interval": 3600,
    "filters": []
  },
  "inputs": ["url", "config"],
  "outputs": ["html", "metadata"],
  "engine": "crawl4ai",     // 后端引擎
  "timeout": 300,
  "retry": 3,
  "status": "ready",        // ready/running/completed/failed
  "version": "1.0.0",
  "tags": ["采集", "爬虫"],
  "icon": "spider",
  "description": "从URL采集网页内容"
}
```

### 4. 工作流模板(Workflow Template)

预定义的节点组合，用户可直接使用或修改：
```
模板: 商品图片标注管线
├── 数据采集(维度)
│   ├── 图片爬虫(功能)
│   └── 云存储导入(功能)
├── 数据处理(维度)
│   ├── 去重(功能)
│   ├── 质量评分(功能)
│   └── NSFW过滤(功能)
├── 标注生产(维度)
│   ├── AI预标注-BBox(功能)
│   └── 人工审核(功能)
├── 评测质量(维度)
│   ├── 标注一致性检查(功能)
│   └── BadCase筛选(功能)
└── 数据交付(维度)
    ├── COCO导出(功能)
    └── 版本标记(功能)

模板: 模型评测管线
├── 数据管理(维度)
│   ├── 数据集版本加载(功能)
│   └── 数据浏览器(功能)
├── 评测质量(维度)
│   ├── EvalRunner(功能)
│   ├── 模型对比(功能)
│   └── BadCase追踪(功能)
└── 运营分析(维度)
    ├── 评测看板(功能)
    └── 质量报告PDF(功能)
```

### 5. 组合规则

节点组合必须遵守以下规则：
1. 维度顺序可任意排列(用户决定DAG流向)
2. 每个维度内能力节点可选0-N个
3. 能力节点内的功能节点可选1-N个
4. 前一个功能节点的outputs必须匹配后一个节点的inputs
5. 同一节点可出现多次(如: 不同阶段的AI对话)
6. 节点间支持条件分支(if/else)、并行(fork/join)、循环(loop)

### 6. 后端引擎映射

每个功能节点映射到现有引擎：
```
FN_001(Web爬虫) → engines/operators_lib.py Operator(id="source.web_scraper")
FN_101(BBox检测) → engines/algorithm_review.py AlgorithmReview
FN_201(AI对话) → api/nanobot_adapter.py NanobotAdapter.chat()
FN_301(COCO导出) → engines/dataset_manager.py DatasetManager.export_coco()
FN_401(PPT生成) → engines/ppt_engine.py PPTEngine.generate_full_html()
...
```

### 7. 实现步骤

Step 1: 创建节点注册表(nodes/registry.py)
Step 2: 前段节点选择器(维度→能力→功能三级下拉)
Step 3: 后端DAG执行引擎(DAG解析→拓扑排序→并行/串行执行)
Step 4: 工作流模板存储/加载/分享
Step 5: 执行状态追踪(日志/进度/重试)
