# Infinite Multimodal Data Foundry (IMDF)

**Agent驱动的无限画布多模态生产系统 — 图片/视频/短剧/PPT/网页全自动生成 + 训练数据生产**

## 快速启动

```bash
# Web UI
cd /mnt/d/Hermes/infinite-multimodal-data-foundry
python3 api/canvas_web.py --port 8765
# 浏览器: http://localhost:8765

# 用Hermes调用
hermes chat → "用imdf-infinite-canvas帮我做个PPT"
```

## 项目结构 (26个py文件, 5809行)

```
imdf/
├── core/                          # 核心
│   ├── canvas_core.py    440行    # 无限画布(CanvasState+SceneGraph+History)
│   └── data_quality.py   273行    # 数据质量引擎(美学/NSFW/去重/格式转换)
├── engines/                       # 生产引擎
│   ├── engine_router.py  262行    # 5引擎统一调度决策
│   ├── video_engine.py   846行    # 5合一视频(html-video/HyperFrames/ComfyUI)
│   ├── drama_engine.py   304行    # 7阶段短剧流水线
│   ├── ppt_engine.py     288行    # 34模板+Claude Design
│   ├── story_arc_engine. 387行    # 25故事总纲+情绪引擎+Reviewer
│   ├── web_engine.py     362行    # 21风格+Claude Design
│   └── data/                      # 训练数据生产(新增5引擎)
│       ├── data_t2i.py   170行    # 文生图训练数据
│       ├── data_edit.py  193行    # 图片编辑训练数据
│       └── data_video.py 286行    # 视频/影视/绘本训练数据
├── agent/
│   └── master_agent.py  403行     # Goal Hive+Quality Gate
├── api/
│   ├── canvas_web.py    783行     # Web UI画布+API
│   └── nanobot_adapter. 392行     # NanoBot Factory集成(90+API)
├── tests/                         # 41/41 ✅
├── skill.yaml                     # Hermes Skill
├── start_webui.sh                 # 启动脚本
└── docs/
    └── data_production_knowledge_base.md  # 数据生产知识库
```

## 6大能力域

| 分类 | 引擎 | 功能 |
|------|------|------|
| 🖼️ 文生图 | T2I引擎 + Nanobot | 生成/编辑/ControlNet/RLHF |
| ✏️ 图片编辑 | Edit引擎 | Outpaint/Inpaint/超分/去水印 |
| 🎬 视频 | Video引擎(5合一) | 信息/品牌/创意/数学视频 |
| 🎭 短剧 | Drama引擎(7阶段) | 剧本→角色→分镜→视频→合成 |
| 📊 PPT | PPT引擎 | 34模板+Claude Design+评审 |
| 🌐 网页 | Web引擎 | 21风格+设计系统+Reviewer |

## 数据生产能力

| 方向 | 生产内容 | 格式 |
|------|---------|------|
| 文生图 | 预训练图文对/微调数据/ControlNet条件对 | WebDataset/COCO/Parquet |
| 图片编辑 | Outpaint/Inpaint/超分辨率数据对 | 输入输出对+蒙版 |
| 视频 | 帧提取/文生视频对/视频编辑对 | ffmpeg管线 |
| 影视 | 多镜头叙事对/角色一致性对/风格一致性对 | JSON结构化 |
| 绘本 | 页面布局/适龄参数/风格一致性 | JSON结构化 |

## NanoBot Factory集成

IMDF可通过NanobotAdapter调用NanoBot Factory的16个数据生产管线(12K行代码):
data_annotation_pipeline/data_controlnet_pipeline/data_dataset_manager/data_dense_caption/data_edit_pipeline/data_face_pipeline/data_mllm_pipeline/data_video_pipeline/data_video_caption/data_video_dedup/data_video_quality/data_watermark/data_nsfw_classifier/data_quality_engine/data_quality_advanced/data_multimodal_benchmark

## 源码镜像

vendor源码在 /mnt/d/Hermes/imdf_vendor/:
- html-video (nexu-io, 2.4K★)
- hyperframes (HeyGen, 9.6K★)
- frontend-slides (zarazhangrui, 20.5K★, 34套模板)
- garden-skills (ConardLi, 7K★)

## Hermes Skill

`imdf-infinite-canvas` 已注册。支持用自然语言调用。
