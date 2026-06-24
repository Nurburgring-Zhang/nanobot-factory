# IMDF 完整使用指南

## 快速启动

```bash
# 1. 启动Web UI
cd /mnt/d/Hermes/infinite-multimodal-data-foundry
python3 api/canvas_web.py --port 8765
# 浏览器打开: http://localhost:8765

# 2. 或通过Hermes使用
hermes chat
# 然后说: "用imdf-infinite-canvas ..."
```

## 场景1: 做PPT

**方法A: Web UI**
```
在输入框输入: "做一份季度汇报PPT"
→ Master Agent自动规划4个Worker
→ 选择模板(34种可选)
→ 生成完整HTML幻灯片
```

**方法B: Python代码**
```python
from engines.ppt_engine import PPTEngine, SlideSpec, SlideType

engine = PPTEngine()
tmpl = engine.select_template("科技产品发布会")
slides = [
    SlideSpec(slide_type=SlideType.COVER, title="AI驱动未来"),
    SlideSpec(slide_type=SlideType.CONTENT, title="核心能力", 
              content=["大模型", "Agent", "多模态"]),
    SlideSpec(slide_type=SlideType.END, title="谢谢"),
]
html = engine.generate_full_html(slides, template_id="dark-tech", title="AI驱动未来")
with open("output.html", "w") as f:
    f.write(html)
```

## 场景2: 生图/信息图

**免费方案(HTML截图):**
```
输入: "做一张AI技术栈信息图,米色背景暖色风格"
→ EngineRouter检测到"信息图"
→ 用HTML模板+浏览器截图,0成本,5秒出图
```

**高质量方案(ComfyUI):**
```
→ 检测到需要高质量创意图
→ 调用ComfyUI工作流
→ 35个视频节点+SDXL/Flux
```

## 场景3: 做短视频

```
输入: "把这篇公众号文章做成短视频,竖屏9:16"
→ Master Agent规划5个Worker
→ EngineRouter选择html-video引擎(信息类最优)
→ 自动分段→生成画面→TTS配音→合成MP4
→ 输出: 9:16竖屏视频
```

## 场景4: 做短剧

```
输入: "把这个故事做成3分钟短剧"
→ 7阶段流水线:
  1. 需求理解
  2. 剧本生成(25个故事总纲自动匹配)
  3. 角色视觉锁定
  4. 智能分镜(灰白稿故事版)
  5. 逐镜头生成(Seedance/ComfyUI)
  6. 音画同步(TTS+BGM)
  7. 质量审计(Reviewer Agent)
→ 输出: 3分钟竖屏短剧
```

## 场景5: 做网页

```
输入: "做一个B2B SaaS官网"
→ 智能选风格(b2b-saas风格)
→ 宣告设计系统(Plus Jakarta Sans+Space Grotesk)
→ 生成v0原型(含占位符)
→ 填充内容
→ Reviewer审核(通过→导出HTML)
```

## 场景6: 生产训练数据

```
输入: "生成1000张图片编辑训练数据(Outpaint)"
→ 从图片目录读取
→ 自动裁剪+生成蒙版
→ 产出: 输入/输出/蒙版三件套
→ 格式: WebDataset/COCO
```

```
输入: "生成ControlNet Canny条件数据"
→ 读取图片
→ Canny边缘检测
→ 产出: 原图+条件图对
→ 格式: 目录结构
```

```
输入: "生成角色一致性训练数据"
→ 输入同角色多角度图
→ 生成正负样本对
→ 产出: JSON标注文件
```

## 场景7: 用API调用

```python
import requests

BASE = "http://localhost:8765"

# 规划生产
plan = requests.post(f"{BASE}/engine/plan", json={
    "user_input": "做一份产品发布PPT"
}).json()
print(f"主引擎: {plan['primary_engine']}")
print(f"Workers: {len(plan['workers'])}")

# 获取画布状态
state = requests.get(f"{BASE}/canvas/state").json()
print(f"画布: {state}")
```

## CLI命令速查

```bash
# 测试全部单元
python3 -m pytest tests/ -v

# 直接跑引擎
python3 -c "
import sys; sys.path.insert(0,'.')
from engines.ppt_engine import PPTEngine, SlideSpec, SlideType
e = PPTEngine()
print(e.get_available_templates())  # 查看34套模板
"

# 查看NanoBot Factory状态
python3 -c "
import sys; sys.path.insert(0,'.')
from api.nanobot_adapter import NanobotAdapter
import asyncio
async def test():
    a = NanobotAdapter()
    s = await a.check_health()
    print(f'NanoBot: {s}')
asyncio.run(test())
"
```

## 架构原理

```
用户输入 → Master Agent (内容分析)
  → EngineRouter (类型→最优引擎)
    → 具体引擎执行 (生产)
      → Quality Gate (独立Reviewer审核)
        → 输出

数据生产:
用户输入 → Master Agent (判断为数据生产)
  → DataEngine (T2I/Edit/Video/Drama/Book)
    → DataQualityEngine (质量评分/去重/NSFW)
      → DataFormatConverter (COCO/WebDataset/Parquet)
        → 输出到指定目录
```
