# User Guide — Nanobot Factory

> 给终端用户（标注员 / 设计师 / 产品经理 / 数据工程师）看的使用手册。
> 不涉及代码 / 部署 — 那是 `docs/deployment.md` 的事。

## 1. 平台是什么？

Nanobot Factory（智影数据工场）是一个 **多模态数据生产平台**。简单说：

```
       你上传素材 → 标注/编辑 → AI 生成/增强 → 质检/审核 → 导出训练集
```

适合场景：
- AI 公司：批量生产训练数据（图像、文本、3D）
- 电商：批量生成商品图（不同角度、不同背景、不同模特）
- 数字人 / Live2D：批量制作角色资产
- 研究团队：跨模态数据采集 + 标注

## 2. 登录

打开浏览器，输入：

| 环境 | URL |
|------|-----|
| **生产** | https://nanobot.example.com |
| **Staging** | https://staging.nanobot.example.com |
| **本地** | http://localhost:5173 |

登录方式：
- **API Key**：右上角头像 → Settings → API Keys → 复制
- **邮箱 + 密码**：默认开启；如果接入了 SSO（OIDC / SAML）会跳转

第一次登录会强制改默认密码（如果 admin 启用了策略）。

## 3. 界面导航

```
┌──────────────────────────────────────────────────────────────────┐
│ Logo  智影数据工场                              🔔  用户头像 ▾      │
├──────┬───────────────────────────────────────────────────────────┤
│ 侧栏 │                                                           │
│      │            主工作区 (Canvas / Studio / Dashboard)         │
│ 首页 │                                                           │
│ 画布 │                                                           │
│ 标注 │                                                           │
│ AIGC │                                                           │
│ 模板 │                                                           │
│ 导出 │                                                           │
│ 设置 │                                                           │
└──────┴───────────────────────────────────────────────────────────┘
```

### 3.1 侧栏模块

| 图标 | 名称 | 你能用它干什么 |
|------|------|----------------|
| 🏠 | 首页 (Dashboard) | 看个人待办、近期任务、统计 |
| 🎨 | 画布 (Canvas) | 拖拽节点编排工作流 |
| 🏷️ | 标注 (Annotation) | 图像 / 文本 / 3D 标注 |
| 🤖 | AIGC 工作台 | ComfyUI 渲染、Prompt 调参 |
| 📚 | 模板 (Templates) | Prompt / 风格 / 工作流模板 |
| 📦 | 导出 (Export) | 把数据导出成 COCO/YOLO/VOC |
| ⚙️ | 设置 (Settings) | 个人资料、API Key、Webhook |

## 4. 第一次跑通 — 10 分钟上手

### Step 1：上传一张图
1. 左侧 → "标注" → "+ 上传"
2. 拖一张 PNG/JPG 到对话框（或点"选择文件"）
3. 上传完成后，图会出现在图库里

### Step 2：标注一个对象
1. 选中刚上传的图 → "新建标注"
2. 工具栏选 **矩形 (Bbox)**，在图上画框
3. 右侧填标签：`shoe`
4. 保存 (Ctrl + S)

### Step 3：调一个 AIGC 模板
1. 左侧 → "模板" → 选 "product-shoe-side"（如果存在）
2. 改 `subject` 占位为 `red running shoe`
3. 点"在画布中打开"

### Step 4：在画布生成
1. 画布上会自动多一个 "render" 节点
2. 右键 → "运行" → 选 batch 大小 = 4
3. 等 30-60 秒 → 4 张图出现在 "outputs/" 标签

### Step 5：导出
1. 左侧 → "导出" → "新建导出"
2. 选数据集 + 格式 (COCO)
3. 等待生成 → 下载 zip

🎉 **恭喜 — 你完成了第一个完整工作流！**

## 5. 常用任务

### 5.1 批量上传

1. 进入 "资产" → "批量上传"
2. 拖多张图 / 选目录
3. 进度条显示每张状态

> 💡 提示：单个文件 ≤ 64 MB；批量 ≤ 100 个/请求。

### 5.2 多人协同画布

1. 打开画布 → 点右上角 "分享"
2. 输入协作者邮箱（可选角色）
3. 复制链接发给他们 → 多人同时编辑

> 协同通过 WebSocket 实时同步。光标会显示对方头像。

### 5.3 AI 自动标注

1. 进入 "标注" → 选图 → "AI 预标注"
2. 选模型（YOLOv8 / GroundingDINO / SAM）
3. 等待 5-30 秒
4. AI 生成的框会显示为半透明 — 你只需调整 / 确认

### 5.4 用 DeepSeek 做任务规划

1. 画布 → 顶部输入框："生成 5 张不同角度的咖啡杯图"
2. Master Agent 会拆解任务：
   ```
   t1: 选定参考图 (3 张)
   t2: 调用 sdxl_txt2img × 5
   t3: 自动抠图 + 拼版
   ```
3. 每个任务可手动重跑 / 跳过

### 5.5 版权扫描

1. 资产详情 → "扫描版权"
2. 平台会比对内置库 + 可选 Perplexity / Google 搜索
3. 输出 risk score (0-100)，> 70 标记为高风险

## 6. 角色与权限

| 你能做什么 | admin | manager | reviewer | annotator | viewer |
|-----------|-------|---------|----------|-----------|--------|
| 上传资产 | ✓ | ✓ | ✓ | ✓ | ✗ |
| 创建标注 | ✓ | ✓ | ✓ | ✓ | ✗ |
| 审批标注 | ✓ | ✓ | ✓ | ✗ | ✗ |
| 提交渲染 | ✓ | ✓ | ✓ | ✓ (限频) | ✗ |
| 导出数据集 | ✓ | ✓ | ✓ | ✗ | ✗ |
| 管理用户 | ✓ | ✗ | ✗ | ✗ | ✗ |
| 查看审计 | ✓ | ✓ | ✗ | ✗ | ✗ |

## 7. 快捷键

| 操作 | Windows / Linux | macOS |
|------|-----------------|-------|
| 保存 | `Ctrl + S` | `⌘ + S` |
| 撤销 | `Ctrl + Z` | `⌘ + Z` |
| 重做 | `Ctrl + Shift + Z` | `⌘ + ⇧ + Z` |
| 复制 | `Ctrl + C` | `⌘ + C` |
| 粘贴 | `Ctrl + V` | `⌘ + V` |
| 缩放画布 | `Ctrl + 滚轮` | `⌘ + 滚轮` |
| 画框 | `B` | `B` |
| 多边形 | `P` | `P` |
| 移动选区 | `方向键` | `方向键` |
| 删除 | `Delete` | `Delete` |
| 全屏 | `F11` | `⌃⌘F` |
| 命令面板 | `Ctrl + K` | `⌘ + K` |

## 8. 常见问题 (FAQ)

**Q: 我上传的文件在哪里？**
A: 文件存储在 `data/uploads/{yyyy}/{mm}/{sha256前2位}/{sha256}.{ext}`。普通用户看不到这个路径，是系统内部组织。

**Q: 渲染任务一直 queued？**
A: 检查 "AIGC 工作台" 顶部的 ComfyUI 状态条。绿色 = OK；红色 = 后端不可用，请联系管理员。

**Q: 为什么我看不到 admin 菜单？**
A: 你的角色不是 admin。联系项目管理员申请。

**Q: 误删了资产怎么办？**
A: 软删除 30 天内可在 "资产 → 回收站" 恢复。超过 30 天物理删除，无法恢复。

**Q: 标注保存失败？**
A: 通常是网络抖动 — 重试即可。若持续失败，看浏览器 DevTools 的 Network 面板，把 4xx/5xx 截图发给管理员。

**Q: WebSocket 一直转圈？**
A: 可能是公司代理阻断了 WS。让 IT 把 `wss://nanobot.example.com/ws/*` 加白名单。

**Q: 我能在手机上用吗？**
A: Web UI 支持响应式，但**画布 / 标注**建议桌面端 ≥ 1280×720。移动端适合审批 / 查看。

## 9. 进阶 — 自定义工作流

如果你熟悉 Python，可以用 SDK 直接调用：

```python
from nanobot_sdk import NanobotClient

client = NanobotClient(
    base_url="https://nanobot.example.com",
    api_key="sk-...",
)

# 1. 创建数据集
ds = client.datasets.create(name="shoes-v1", labels=["shoe","sneaker"])

# 2. 批量上传
asset_ids = client.assets.upload_many(["s1.jpg","s2.jpg","s3.jpg"])

# 3. AI 预标注
for aid in asset_ids:
    pre = client.ai.preannotate(aid, model="yolov8n")
    print(aid, pre.annotations)

# 4. 导出
export = client.exports.create(dataset_id=ds.id, format="coco")
print(export.download_url)   # 24h 有效
```

详见 [`docs/api.md`](./api.md)。

## 10. 反馈

- 🐛 Bug：Settings → "反馈" → 选 "Bug report"
- 💡 Feature request：Settings → "反馈" → 选 "Feature"
- 💬 群：内部 Slack `#nanobot-users`

---

_最后更新：2026-06-21 — 适用版本 appVersion 1.0.0_

_给非技术读者：如果哪个章节看不懂，请直接联系 onboarding 团队，我们来解释。_