---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3045022100d6c491b04f9f0153f7fc4465778925ebb740f7f0b4186201ff4977406a4739bd02201c5e50f96d7bfc5a3fd171e8a73149a67b80eac653bf9a7afbe692c466ff3504
    ReservedCode2: 3045022100f2fc2f0cbfdae1e81e32fca3c484121e2ec902b026c468cc522ca467cc6cf5830220198885028c7a5701ff946591d93cc40b04883be1fa05e4b1e6f0025807b6a04c
---

# General AIGC Enhanced v7.0 - Web界面

基于用户提供的AIGC Batch Tool构建的专业级AI生成工具Web界面，模仿KritaAI增强版7.0的设计理念和功能。

## 🎯 项目概述

General AIGC Enhanced是一个现代化的Web应用，提供完整的AI生成工作流程：

- **图片生成**: 支持多种最新AI模型（z_image、qwen_image、Flux.2等）
- **图片编辑**: 使用Flux.2 Klein、qwen_image_edit等模型
- **视频生成**: 支持wan、ltx-2等视频生成模型
- **3D生成**: 集成Hunyuan3D、Trellis-2等3D模型

## ✨ 核心特性

### 🎨 用户界面
- **专业级UI设计**: 仿照General AIGC Enhanced v7.0的密集型工作区布局
- **深色主题**: Deep Indigo配色方案，专业视觉体验
- **响应式设计**: 支持多屏幕尺寸自适应
- **实时状态**: 任务进度轮询和状态更新

### 🔧 功能模块
每个主要功能模块包含7个子模块：
1. **模型模块** - 模型文件管理和自动更新
2. **提示词模块** - 批量处理和AI优化
3. **LoRA模块** - 多LoRA权重管理
4. **ControlNet模块** - 精确控制参数
5. **生图参数模块** - 推理步数、CFG、种子等
6. **分辨率模块** - 预设和自定义分辨率
7. **优化模块** - 高级算法和增强功能

### 🚀 后端服务
- **Supabase集成**: 完整的数据库、认证和存储服务
- **Edge Functions**: 无服务器AI推理服务
- **Python推理引擎**: 真正的AI模型推理（非模拟）
- **实时通信**: 任务状态实时更新

## 📁 项目结构

```
krita-ai-enhanced/
├── src/                          # 前端源码
│   ├── components/               # React组件
│   │   ├── layout/              # 布局组件
│   │   ├── ui/                  # 基础UI组件
│   │   ├── parameters/          # 参数面板组件
│   │   └── workspaces/          # 工作区组件
│   ├── contexts/                # React Context
│   ├── services/                # API服务
│   └── App.tsx                  # 主应用
├── supabase/                    # 后端配置
│   ├── functions/               # Edge Functions
│   │   ├── ai-generation/       # AI生成服务
│   │   ├── model-management/    # 模型管理服务
│   │   ├── file-processor/      # 文件处理服务
│   │   └── generation-status/   # 状态查询服务
│   ├── migrations/              # 数据库迁移
│   └── README.md                # 后端配置文档
├── docs/                        # 设计文档
│   ├── design-specification.md  # 设计规范
│   ├── design-tokens.json       # 设计令牌
│   └── content-structure-plan.md # 内容结构
├── setup_environment.sh         # 环境配置脚本
└── README.md                    # 项目文档
```

## 🛠️ 技术栈

### 前端
- **React 18** + TypeScript
- **Vite** 构建工具
- **Tailwind CSS** 样式框架
- **Lucide React** 图标库
- **Supabase JavaScript SDK**

### 后端
- **Supabase** 数据库和认证
- **Deno Edge Functions** 无服务器函数
- **Python** AI推理引擎
- **Diffusers** 深度学习模型库

### AI模型
- **Hugging Face Transformers**
- **Stable Diffusion** 系列
- **ComfyUI** 格式兼容
- **最新模型**: z_image, qwen_image, Flux.2, wan, ltx-2, Hunyuan3D, Trellis-2

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd krita-ai-enhanced

# 运行环境配置脚本
chmod +x setup_environment.sh
./setup_environment.sh
```

### 2. 前端启动

```bash
# 安装依赖
npm install
# 或者
pnpm install

# 启动开发服务器
npm run dev
# 或者
pnpm dev
```

### 3. 后端配置

#### Supabase设置

1. **创建Supabase项目**
   - 访问 [https://supabase.com](https://supabase.com)
   - 创建新项目，选择合适地区

2. **数据库迁移**
   ```bash
   # 安装Supabase CLI
   npm install -g @supabase/cli
   
   # 登录并链接项目
   supabase login
   supabase link --project-ref YOUR_PROJECT_ID
   
   # 运行迁移
   supabase db push
   ```

3. **存储桶配置**
   - 创建以下存储桶：
     - `models` - 模型文件存储
     - `generated-content` - 生成内容存储
     - `user-uploads` - 用户上传文件
     - `temp-files` - 临时文件

4. **Edge Functions部署**
   ```bash
   # 部署所有函数
   supabase functions deploy ai-generation
   supabase functions deploy model-management
   supabase functions deploy file-processor
   supabase functions deploy generation-status
   ```

5. **环境变量配置**
   ```bash
   # 设置必要的环境变量
   supabase secrets set DIFFUSERS_CACHE_DIR=/tmp/diffusers-cache
   supabase secrets set CUDA_VISIBLE_DEVICES=0
   ```

### 4. 前端环境配置

创建 `.env.local` 文件：

```env
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

### 5. 构建和部署

```bash
# 构建生产版本
npm run build
# 或者
pnpm build

# 部署到生产环境
# （根据你的部署平台配置）
```

## 🔧 配置说明

### AI模型配置

#### 支持的模型类型
- **Checkpoint**: 主模型（SDXL, Flux, etc.）
- **LoRA**: 风格和特征微调
- **ControlNet**: 精确控制网络
- **VAE**: 变分自编码器
- **CLIP**: 文本编码器

#### 模型路径配置
```typescript
// 模型应放在以下目录结构
models/
├── checkpoints/     # 主模型
├── lora/           # LoRA模型
├── controlnet/     # ControlNet模型
├── vae/           # VAE模型
└── clip/          # CLIP模型
```

### 参数预设配置

#### 内置预设
- **风格预设**: 写实、动漫、艺术等
- **参数预设**: 快速生成、高质量、批量处理
- **分辨率预设**: 标准宽高比配置

#### 自定义预设
用户可以保存和分享参数预设。

## 🎨 设计规范

### 色彩系统
```json
{
  "primary": {
    "50": "#f8fafc",
    "100": "#f1f5f9",
    "800": "#1e293b",
    "900": "#0f172a"
  },
  "accent": {
    "400": "#22d3ee",
    "500": "#06b6d4"
  }
}
```

### 布局系统
- **Sidebar**: 240px宽度，可收缩
- **Workspace**: 自适应主要内容区
- **ParameterPanel**: 360px宽度，可隐藏

### 组件规范
- **按钮**: 高度32px，圆角4px
- **输入框**: 高度36px，聚焦状态强调
- **卡片**: 圆角6px，边框1px

## 📱 使用指南

### 基本工作流程

1. **选择模块**: 在侧边栏选择功能模块
2. **加载模型**: 在模型面板选择AI模型
3. **设置参数**: 配置生成参数和优化选项
4. **输入提示**: 编写或优化提示词
5. **开始生成**: 点击生成按钮
6. **查看结果**: 在工作区查看生成内容
7. **管理历史**: 在历史视图查看所有任务

### 高级功能

#### 批量处理
- 支持批量TXT文件导入提示词
- 自动处理多行提示词
- 批量下载生成结果

#### 模型管理
- 自动检测模型更新
- 支持模型上传和管理
- 模型性能优化

#### 实时监控
- 任务进度实时显示
- GPU使用率监控
- 生成时间估算

## 🔍 故障排除

### 常见问题

#### 1. 前端无法连接后端
```bash
# 检查环境变量
echo $VITE_SUPABASE_URL
echo $VITE_SUPABASE_ANON_KEY

# 检查网络连接
curl $VITE_SUPABASE_URL/rest/v1/
```

#### 2. Edge Functions部署失败
```bash
# 检查Supabase CLI
supabase --version

# 重新部署函数
supabase functions deploy --no-verify-jwt
```

#### 3. Python环境问题
```bash
# 激活虚拟环境
source ./krita-ai-env/bin/activate

# 检查Python包
pip list | grep torch
pip list | grep transformers
```

#### 4. 模型加载失败
- 检查模型文件路径
- 验证模型文件完整性
- 确保有足够GPU显存

### 日志查看

```bash
# Supabase函数日志
supabase functions logs ai-generation

# Python推理日志
tail -f /tmp/krita_ai_inference.log

# 前端控制台
# 浏览器开发者工具 > Console
```

## 🚀 性能优化

### 前端优化
- **代码分割**: 按路由懒加载组件
- **图片优化**: WebP格式和响应式图片
- **缓存策略**: API响应缓存
- **Bundle分析**: 使用webpack-bundle-analyzer

### 后端优化
- **数据库索引**: 优化查询性能
- **CDN加速**: 静态资源CDN分发
- **连接池**: 数据库连接复用
- **缓存层**: Redis缓存热点数据

### AI推理优化
- **模型量化**: INT8/FP16精度优化
- **批处理**: 合并多个推理请求
- **GPU内存**: 优化显存使用
- **推理缓存**: 缓存中间结果

## 🤝 贡献指南

### 开发环境设置
1. Fork项目到你的GitHub账户
2. 克隆你的fork到本地
3. 创建开发分支
4. 设置环境并运行
5. 提交Pull Request

### 代码规范
- **TypeScript**: 严格类型检查
- **ESLint**: 代码风格检查
- **Prettier**: 代码格式化
- **Commit规范**: 使用Conventional Commits

### 测试要求
- 单元测试覆盖率 > 80%
- 集成测试覆盖主要流程
- 性能测试验证关键指标

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- **Hugging Face**: 感谢提供优秀的AI模型库
- **Supabase**: 感谢提供完整的后端服务
- **React**: 感谢提供优秀的UI框架
- **Krita团队**: 感谢提供设计灵感

## 📞 支持

如果你在使用过程中遇到问题：

1. **查看文档**: 首先查阅本文档和代码注释
2. **搜索Issue**: 在GitHub仓库搜索相关问题
3. **创建Issue**: 如果问题未解决，请创建详细的问题报告
4. **社区讨论**: 参与GitHub Discussions讨论

---

**General AIGC Enhanced v7.0** - 让AI创作更简单、更专业 🚀