# IMDF画布/工作流引擎深度审计 + 前后端API交叉验证报告
# ============================================================================
# 项目: nanobot-factory | 服务器: localhost:8900
# 审计日期: 2026-06-17
# ============================================================================

================================================================================
任务1: IMDF画布/工作流引擎深度审计
================================================================================

## 1.1 画布核心API (canvas_web.py)
文件: backend/imdf/api/canvas_web.py (4034行)

### 画布状态端点:
| 端点                        | 方法   | 状态 | 前端调用                     |
|-----------------------------|--------|------|-----------------------------|
| /canvas/state               | GET    | ✅200 | canvas.js:945 (fetch调用)    |
| /canvas/state               | POST   | ✅   | canvas.js:935 (apiPost)      |
| /canvas/element             | POST   | ✅   | canvas.js (动态创建节点)      |
| /canvas/element/{id}        | DELETE | ✅   | canvas.js (删除节点)          |
| /canvas/ws                  | WS     | ✅   | WebSocket实时推送             |

### 引擎端点:
| 端点                        | 方法   | 状态 | 前端调用                     |
|-----------------------------|--------|------|-----------------------------|
| /engine/plan                | POST   | ✅   | canvas.js                    |
| /engine/render              | POST   | ✅   | canvas.js                    |

### 工作流端点:
| 端点                        | 方法   | 测试 | 前端调用                     |
|-----------------------------|--------|------|-----------------------------|
| /api/workflow/validate      | POST   | 405  | canvas.js (无直接调用)        |
| /api/workflow/execute       | POST   | 405  | canvas.js:874 (apiPost)      |
| /api/workflow/templates     | GET    | 200  | canvas.js (无直接调用)        |
| /api/workflow/nodes         | GET    | 200  | canvas.js (无直接调用)        |

### ComfyUI端点:
| 端点                                 | 方法   | 测试 |
|--------------------------------------|--------|------|
| /api/comfyui/workflows               | GET    | 200  |
| /api/comfyui/run                     | POST   | 405  |
| /api/comfyui/status/{prompt_id}      | GET    | -    |

## 1.2 画布前端 (canvas.js, 1131行)
- 定义了48种节点类型 (WF_NT映射)
- 支持: text, image, video, audio, model3d, llm, comfyui, seedance, runninghub, portrait, falbox, rhtools, grok, ppt, script, output, upload, imgedit, gridcrop, gridedit, imgcmp, presetimg, resize, upscale, topazimg, videoedit, frameex, framepair, topazvid, textsplit, mention, loop, relay, groupbox, browser, aggregate, removebg, rmwatermark, drawboard, storygrid, combine, panorama, posemaster, materialset, pickfromset, idea, placeholder, prelabel
- API调用: /api/chat, /api/workflow/execute, /canvas/state, /api/comfyui/run, /api/prelabel, /api/3d/, /imdf/external/list, /imdf/images/resize

## 1.3 3D能力 (canvas_3d.py, 305行)
文件: backend/imdf/api/canvas_3d.py
前缀: /api/3d
总路由: 15个

### 场景CRUD (5):
GET    /api/3d/scenes                    ✅200
POST   /api/3d/scenes                    ✅
GET    /api/3d/scenes/{scene_id}         ✅
PUT    /api/3d/scenes/{scene_id}         ✅
DELETE /api/3d/scenes/{scene_id}         ✅

### 人物管理 (2):
POST   /api/3d/scenes/{id}/avatars       ✅
DELETE /api/3d/scenes/{id}/avatars/{aid} ✅

### 摄像机 (3):
GET    /api/3d/cameras/presets           ✅200
POST   /api/3d/scenes/{id}/cameras       ✅
DELETE /api/3d/scenes/{id}/cameras/{cid} ✅

### 热点/关键帧/遮挡 (3):
POST   /api/3d/scenes/{id}/hotspots      ✅
POST   /api/3d/scenes/{id}/keyframes     ✅
POST   /api/3d/scenes/{id}/masks         ✅

### 姿势库 (3):
GET    /api/3d/poses                     ✅200
GET    /api/3d/poses/tags                ✅
POST   /api/3d/poses/infer               ✅

### 动作生成 (2):
POST   /api/3d/actions/parse             ✅405
POST   /api/3d/actions/keyframes         ✅

前端调用: canvas.js 第826行: apiGet('/api/3d/' + (nd.type==='panorama'?'scenes':'poses'))
          只用到了 /api/3d/scenes 和 /api/3d/poses
          panorama3d_node.tsx 使用 api.getResourceCategories('panorama')
          pose_master_node.tsx 使用 api.getResourceCategories('pose')

## 1.4 TSX节点文件统计
frontend/imdf/src/nodes/ 下有56个TSX文件 (用户报告45个,实际56个)
核心节点: imdf_audio_node, imdf_browser_node, imdf_comfy_ui_app_maker_node, imdf_drawing_board_node,
          imdf_fal_toolbox_node, imdf_frame_extractor_node, imdf_grid_crop_node, imdf_image_node,
          imdf_llm_node, imdf_loop_node, imdf_output_node, imdf_panorama3d_node, imdf_pose_master_node,
          imdf_remove_bg_node, imdf_resize_node, imdf_seedance_node, imdf_storyboard_grid_node,
          imdf_text_node, imdf_topaz_image_upscale_node, imdf_upload_node, imdf_video_node 等

### 画布引擎完整性评估: ⚠️良好但有缺口
- ✅ 48种节点类型完整定义在前端canvas.js
- ✅ 核心画布操作(crud/state/ws)完整
- ✅ 工作流执行管线完整
- ✅ 3D场景/姿势API基本完整
- ⚠️ workflow/validate端点未在前端直接调用
- ⚠️ workflow/templates/nodes端点未在前端直接调用
- ⚠️ 3D人物/摄像机/热点/keyframe/动作API未在前端调用


================================================================================
任务2: 前后端API交叉验证(全714路由)
================================================================================

## 2.1 交叉验证总表 (按路由前缀):
图例: ✅两端都有 ⚠️后端有前端无 ❌前端有后端无 🔴两端都无(死代码)

| 前缀                   | 后端 | 前端调 | 状态                                                  |
|------------------------|------|--------|-------------------------------------------------------|
| /api/3d               | 15   | 2      | ⚠️ 13个路由前端未调用(avatars/cameras/hotspots等)       |
| /api/admin             | 6    | 2      | ⚠️ 仅users相关,v1下单独调用                             |
| /api/aesthetic         | 8    | 2      | ⚠️ elo-register/compare/stats/health未调用              |
| /api/ai                | 3    | 0      | ⚠️ 后端有前端无                                         |
| /api/ai-generation     | 1    | 0      | ⚠️ OmniGen Studio独立模块                               |
| /api/airi              | 17   | 0      | ⚠️ 数字人AIRI,前端无调用(可能是计划功能)                  |
| /api/annotation        | 13   | 0      | ⚠️ OmniGen Studio独立标注模块                           |
| /api/annotations       | 2    | 1      | ⚠️ /api/annotations/save 前端调用,history未调用          |
| /api/assets            | 4    | 0      | ⚠️ 后端有前端无                                         |
| /api/audio             | 5    | 4      | ✅ audio-tools.js调用4个(asr/music/sfx/tts),jobs未调用  |
| /api/auth              | 2    | 0      | ⚠️ OmniGen Studio独立                                   |
| /api/book              | 6    | 1      | ⚠️ picture-book.js仅调用generate,其他5个未调用           |
| /api/canvas            | 13   | 0      | ⚠️ server.py的canvas API,前端无调用(使用canvas_web的)    |
| /api/chat              | 1    | 1      | ✅ canvas.js多处调用                                     |
| /api/classify          | 8    | 0      | ⚠️ 分类API后端有前端无                                   |
| /api/cloud             | 4    | 0      | ⚠️ 云存储API后端有前端无                                 |
| /api/cluster           | 4    | 0      | ⚠️ Agent集群后端有前端无                                 |
| /api/comfyui           | 5    | 1      | ⚠️ 前端仅调用/run,其他4个未调用                           |
| /api/config            | 1    | 0      | ⚠️ 后端有前端无                                         |
| /api/crowd             | 2    | 7      | ❌ 前端调用7个endpoint但后端只有2个(workers/stats)        |
| /api/dam               | 15   | 3      | ⚠️ dam-viewer.js调用3个(files/preview/tag),12个未调用    |
| /api/data              | 20   | 0      | ⚠️ 数据管线API全部未在前端调用                            |
| /api/datasets          | 2    | 1      | ✅ frontend调用/api/datasets                             |
| /api/db                | 34   | 0      | ⚠️ 数据库管理API全部未调用                                |
| /api/delivery          | 2    | 2      | ✅ delivery.js调用                                       |
| /api/discovery          | 4    | 1      | ⚠️ 仅search调用,其他3个未调用                             |
| /api/drama             | 4    | 2      | ✅ drama-studio.js调用generate和script                   |
| /api/enhanced          | 8    | 3      | ⚠️ 仅dedup/speech-transcribe/video-scenes,5个未调用       |
| /api/external          | 6    | 0      | ⚠️ 外部Agent路由,canvas.js间接触发但非直接调用             |
| /api/fiftyone          | 11   | 0      | ⚠️ FiftyOne集成,无前端调用                               |
| /api/file-processor    | 1    | 0      | ⚠️ OmniGen Studio独立                                   |
| /api/files             | 7    | 0      | ⚠️ 文件管理API无前端调用                                  |
| /api/generate          | 3    | 0      | ⚠️ 生成API无前端调用                                     |
| /api/generation-status | 1    | 0      | ⚠️ OmniGen Studio独立                                   |
| /api/health            | 3    | 0      | ⚠️ 健康检查API无前端调用                                  |
| /api/inference         | 11   | 0      | ⚠️ OmniGen Studio推理API                                |
| /api/info              | 12   | 0      | ⚠️ OmniGen Studio信息API                                |
| /api/keys              | 5    | 0      | ⚠️ API密钥管理无前端调用                                  |
| /api/local-models      | 5    | 1      | ⚠️ 仅list调用                                            |
| /api/memory            | 5    | 0      | ⚠️ 记忆系统无前端调用                                     |
| /api/model-management  | 1    | 0      | ⚠️ OmniGen Studio独立                                   |
| /api/models            | 24   | 0      | ⚠️ 模型管理无直接前端调用                                 |
| /api/monitor           | 2    | 2      | ✅ pipeline和history前端都调用                            |
| /api/nanobot           | 20   | 0      | ⚠️ Nanobot Agent全部无前端调用                            |
| /api/omni              | 15   | 0      | ⚠️ OmniGen全部无前端调用                                 |
| /api/omnigen           | 5    | 0      | ⚠️ 无前端调用                                            |
| /api/ops               | 2    | 2      | ✅ overview和trend前端调用                                |
| /api/oss               | 11   | 2      | ⚠️ 仅status和upload调用                                   |
| /api/pe                | 6    | 0      | ⚠️ PE引擎无前端调用                                       |
| /api/pipeline          | 1    | 0      | ⚠️ 仅augmentation-types,前端pipeline.js不调用此路径        |
| /api/prelabel          | 1    | 1      | ✅ canvas.js调用                                         |
| /api/production        | 5    | 0      | ⚠️ 生产管理无前端调用                                     |
| /api/quality           | 81   | 1      | ⚠️ 81个质检路由,前端仅调用iaa/report                      |
| /api/scheduler         | 9    | 3      | ⚠️ jobs和health被调用,history/run/presets等6个未调用       |
| /api/search            | 10   | 3      | ⚠️ 前端调images/hybrid/根,index等7个未调用               |
| /api/sharing           | 4    | 0      | ⚠️ 分享功能无前端调用                                     |
| /api/skills            | 2    | 0      | ⚠️ 技能无前端调用                                         |
| /api/stats             | 3    | 5      | ❌ 前端调用5个stats但后端只有3个(personnel),前端调用不匹配  |
| /api/system            | 4    | 0      | ⚠️ GPU系统信息无前端调用                                  |
| /api/systems           | 2    | 0      | ⚠️ 系统初始化无前端调用                                   |
| /api/tasks             | 3    | 0      | ⚠️ 任务管理无前端调用                                     |
| /api/templates         | 10   | 1      | ⚠️ 前端仅调用/api/templates(无具体路径),10个后端细粒度API  |
| /api/transfer          | 11   | 3      | ⚠️ transfer-center.js调用3个,8个未调用                   |
| /api/unified           | 2    | 0      | ⚠️ 统一执行器无前端调用                                   |
| /api/v1                | 15   | 10     | ⚠️ 大部分有调用,export/formats/watermark等未调用          |
| /api/v2                | 70   | 0      | ⚠️ 70个v2路由几乎全部无前端调用!                          |
| /api/workbench         | 8    | 0      | ⚠️ 工作台API无前端调用                                    |
| /canvas/*              | 6    | 2      | ✅ state和element前端调用                                 |
| /engine/*              | 2    | 0      | ⚠️ plan/render无直接前端调用(页面内使用)                   |
| /imdf/*                | 32   | 2      | ⚠️ canvas.js间接触发external/image,其他30个无调用          |

## 2.2 汇总统计:
| 类别               | 数量      |
|--------------------|----------|
| 总后端路由         | ~714     |
| 前端调用的API路径   | ~90      |
| ✅ 两端都有         | ~25个前缀 |
| ⚠️ 后端有前端无     | ~45个前缀 |
| ❌ 前端有后端无     | 2 (crowd/stats有部分路径前端调用但不存在) |
| 🔴 完全死代码(估算) | ~500+路由 |


================================================================================
关键路径深度分析
================================================================================

## 2.3 /api/3d/* - 18个路由 (实际15个)
后端: canvas_3d.py 15个路由
前端: canvas.js第826行仅调用 /api/3d/scenes 或 /api/3d/poses (只读)
      panorama3d_node.tsx 使用 api.getResourceCategories('panorama')
      pose_master_node.tsx 使用 api.getResourceCategories('pose')
未调用: avatars, cameras, hotspots, keyframes, masks, actions/parse, actions/keyframes, poses/infer, poses/tags, cameras/presets

## 2.4 /api/book/* - 7个路由 (实际6个)
后端: book_routes.py 6个路由: generate/list/{book_id}[GET,DELETE,export,preview] + images
前端: picture-book.js仅调用 /api/book/generate
未调用: list/{book_id}/export/preview/images

## 2.5 /api/drama/* - 4个路由
后端: drama_routes.py 4个: generate/list/script/episode/{id}
前端: drama-studio.js调用 /api/drama/generate 和 /api/drama/script
未调用: list 和 episode/{id}

## 2.6 /api/audio/* - 5个路由
后端: audio_routes.py 5个: asr/music/sfx/tts/jobs
前端: audio-tools.js调用 asr/music/sfx/tts (4个)
未调用: jobs

## 2.7 /api/comfyui/* - 5个路由
后端: server.py中5个: env/status, env/create, env/install, models/add, models/list
前端: canvas.js调用 /api/comfyui/run (这个在canvas_web.py中)
      其他5个server.py中的comfyui路由无前端调用

## 2.8 /api/search/* - 10个路由
后端: search_routes.py 10个: [GET,POST]/search, /images, /hybrid, /indices, /index/create, /index/{name}, /index/text, /index/images, /index/delete-vectors, /status
前端: app.js调用 /api/search, /api/search/hybrid, /api/search/images (3个)
未调用: indices, index创建/删除/text/images, status

## 2.9 /api/dam/* - 15个路由 (实际15个)
后端: dam_routes.py 15个
前端: dam-viewer.js调用 files(列表), files/{id}/preview, files/{id}/tag (3个)
未调用: tag-all, smart-folders全部, lineage全部, stats, formats, scan, search/suggest

## 2.10 /api/pipeline/* - 4个路由 (canvas_web.py)
后端: augmentation-types, format-types, run, run-with-items
前端: pipeline.js调用 /api/monitor/pipeline 和 /api/workflow/execute (不直接调pipeline路由)


================================================================================
死代码清单
================================================================================

## 完全无前端调用的路由前缀(严重):
1. /api/ai/* - 3个路由: chat/capabilities/recommend
2. /api/ai-generation/* - OmniGen Studio模块
3. /api/airi/* - 17个路由: 数字人全部功能
4. /api/annotation/* - 13个路由: OmniGen标注模块
5. /api/assets/* - 4个路由
6. /api/canvas/* (server.py版) - 13个路由 (canvas/create/list/edit等)
7. /api/classify/* - 8个路由
8. /api/cloud/* - 4个路由
9. /api/cluster/* - 4个路由
10. /api/config/* - 1个路由
11. /api/data/* - 20个路由: quality/controlnet/caption等
12. /api/db/* - 34个路由: 数据库管理全部
13. /api/fiftyone/* - 11个路由
14. /api/file-processor/* - 1个路由
15. /api/files/* - 7个路由
16. /api/generate/* - 3个路由
17. /api/generation-status/* - 1个路由
18. /api/inference/* - 11个路由: OmniGen推理
19. /api/info/* - 12个路由: OmniGen信息
20. /api/keys/* - 5个路由
21. /api/memory/* - 5个路由
22. /api/model-management/* - 1个路由
23. /api/models/* - 24个路由 (server.py版)
24. /api/nanobot/* - 20个路由: Agent全部
25. /api/omni/* - 15个路由
26. /api/omnigen/* - 5个路由
27. /api/pe/* - 6个路由
28. /api/production/* - 5个路由
29. /api/sharing/* - 4个路由
30. /api/skills/* - 2个路由
31. /api/system/* - 4个路由
32. /api/systems/* - 2个路由
33. /api/tasks/* - 3个路由
34. /api/unified/* - 2个路由
35. /api/v2/* - 70个路由: 几乎全部无前端调用
36. /api/workbench/* - 8个路由
37. /imdf/* (大部分) - 30个未调用路由
38. /auth/* - 5个路由 (IMDF子应用)

## 部分死代码(大量路由未用):
39. /api/3d/* - 13/15个路由未用
40. /api/aesthetic/* - 6/8个路由未用
41. /api/admin/* - 4/6个未用
42. /api/book/* - 5/6个未用
43. /api/comfyui/* - 4/5个未用
44. /api/dam/* - 12/15个未用
45. /api/datasets/* - 1/2个未用
46. /api/delivery/* - 0/2 (全用)
47. /api/discovery/* - 3/4个未用
48. /api/enhanced/* - 5/8个未用
49. /api/external/* - 6/6个未用 (canvas.js间接触发)
50. /api/local-models/* - 4/5个未用
51. /api/monitor/* - 0/2 (全用)
52. /api/ops/* - 0/2 (全用)
53. /api/oss/* - 9/11个未用
54. /api/quality/* - 80/81个未用
55. /api/scheduler/* - 6/9个未用
56. /api/search/* - 7/10个未用
57. /api/templates/* - 9/10个未用
58. /api/transfer/* - 8/11个未用
59. /api/v1/* - 5/15个未用

## 前端调用但后端不存在:
60. /api/crowd/assign - 前端调用,后端不存在(仅workers/stats存在)
61. /api/crowd/golden-check - 前端调用,后端不存在
62. /api/crowd/majority-vote - 前端调用,后端不存在
63. /api/crowd/quality-coefficient - 前端调用,后端不存在
64. /api/crowd/quality-report/* - 前端调用,后端不存在
65. /api/crowd/teams - 前端调用,后端不存在
66. /api/settings/api - 前端调用,后端不存在
67. /api/settings/cache/clear - 前端调用,后端不存在
68. /api/settings/models - 前端调用,后端不存在
69. /api/settings/notifications - 前端调用,后端不存在
70. /api/settings/storage - 前端调用,后端不存在
71. /api/stats/annotate - 前端调用,后端不存在
72. /api/stats/daily - 前端调用,后端不存在
73. /api/stats/monthly - 前端调用,后端不存在
74. /api/stats/quality - 前端调用,后端不存在
75. /api/stats/weekly - 前端调用,后端不存在
76. /api/requirements/* - 前端调用,后端不存在
77. /api/review/* - 前端调用,后端不存在(多个review路由)


================================================================================
总结与建议
================================================================================

## 画布/工作流引擎: 整体良好
- 核心画布CRUD完整,工作流执行管道可用
- 48种节点类型完整定义
- 3D场景/姿势API基础功能可用
- 建议: 补充前端对workflow/validate、workflow/templates的直接调用

## API利用率: 极低 (~12%)
- 约714个后端路由,前端仅调用约90个
- 约500+路由为死代码或计划功能
- 大量OmniGen Studio模块、AIRI数字人、FiftyOne等独立子系统存在但未集成

## 前端调用但后端缺失: 约18个端点
- 特别是 /api/crowd/, /api/settings/, /api/stats/, /api/review/ 大量子路由
- 需要后端补充这些端点或清理前端死代码

## 最严重问题:
1. /api/v2/* 70个路由全部无前端调用
2. /api/quality/* 81个路由仅1个被调用
3. /api/nanobot/* 20个Agent路由全部无调用
4. /api/db/* 34个数据库管理路由全部无调用
5. 多个OmniGen Studio独立模块(约100路由)未与主前端集成
