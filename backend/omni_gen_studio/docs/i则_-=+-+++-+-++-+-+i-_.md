---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 304502206d853882d49758140f1101c4e61bbcab4232ca8e930d5999f24a9415a62f20a002210094a41df549dc4e8e4334f6004ab7ab9f578f3dc907b91b25d72a6e0a8694ee88
    ReservedCode2: 3046022100fd09f73f753caf4f77866cc6de06894876a7be1ad66ae7fc6e7c721efc0f5d81022100a255592db88e866aa196e057dda9322ca779701d9905477092c6dcf9bfaa6a65
---

# General AIGC Enhanced 完整运行指南

## 🚀 快速启动

### 步骤1：环境设置
```bash
# 方法1：使用批处理文件（推荐）
双击 setup.bat

# 方法2：使用Python命令
python manage_venv.py setup
```

### 步骤2：启动程序
```bash
# 方法1：使用批处理文件（推荐）
双击 start.bat

# 方法2：使用Python命令
python main.py
```

## 📋 系统要求检查

### 最低要求
- **操作系统**: Windows 10/11, Linux, macOS
- **Python**: 3.8+
- **内存**: 8GB RAM（推荐16GB+）
- **硬盘**: 10GB可用空间
- **GPU**: NVIDIA GTX 1060+ 或 AMD RX 580+（可选）

### GPU要求（推荐）
- **最低**: NVIDIA GTX 1060 6GB
- **推荐**: NVIDIA RTX 3070+ 或 RTX 4060+
- **显存**: 8GB+（用于大模型）

## 🛠️ 环境自动安装

程序会自动处理以下环境设置：

### 1. 虚拟环境
- ✅ 自动创建虚拟环境 `venv_aigc`
- ✅ 隔离Python依赖，避免冲突
- ✅ 支持断点续传下载

### 2. 核心依赖
```python
# PyTorch生态
torch>=2.0.0          # 深度学习框架
diffusers>=0.21.0      # Hugging Face模型库
transformers>=4.25.0   # 预训练模型

# 图像处理
pillow>=9.0.0          # 图像处理
opencv-python>=4.5.0   # 计算机视觉
numpy>=1.21.0          # 数值计算

# 加速库
xformers>=0.0.20       # 内存效率优化
flash-attn              # 注意力机制加速（可选）
```

### 3. AI模型支持
```python
# 支持的模型格式
safetensors            # 安全张量格式
checkpoint              # PyTorch检查点
gguf                   # GGUF量化格式
AIO                    # All-in-One封装格式
```

## 🎯 功能验证清单

### 图片生成模块
- [ ] 模型加载（Z-Image、Qwen-Image、Flux.2 Klein）
- [ ] 提示词输入和编辑
- [ ] LoRA权重调节（最多3个）
- [ ] ControlNet集成
- [ ] 生成参数设置（步数、CFG、种子）
- [ ] 分辨率选择（预设和自定义）
- [ ] 画质优化选项

### 图片编辑模块
- [ ] 模型选择（Qwen Edit 2511、Flux.2 Klein）
- [ ] 单图/多图参考模式
- [ ] 局部重绘功能
- [ ] Mask局部重绘
- [ ] 人脸识别保持
- [ ] 特征迁移
- [ ] 风格转换

### 视频生成模块
- [ ] 模型支持（Wan 2.2、LTX-2）
- [ ] 帧数和帧率设置
- [ ] 首帧/尾帧参考
- [ ] 视频质量优化
- [ ] 输出格式选择

### 3D生成模块
- [ ] 模型支持（Hunyuan3D、Trellis-2）
- [ ] 单图转3D
- [ ] 输出格式（OBJ、PLY、STL、GLB）
- [ ] 3D模型预览

## 🔧 详细运行步骤

### 1. 第一次启动
```bash
# 进入项目目录
cd /path/to/AIGC_Enhanced

# 运行环境设置
python manage_venv.py setup

# 启动程序
python main.py
```

### 2. 验证安装
启动后检查控制台输出：
```
✅ PyTorch: 2.0.0
✅ GPU: NVIDIA RTX 4060 (8.0GB) | FlashAttn2: ✓ | xFormers: ✓
✅ 虚拟环境: venv_aigc
✅ 后端集成模块导入成功
✅ 新UI架构导入成功
```

### 3. GUI界面验证
启动成功后应看到：
- 4个主要功能模块标签页
- 每个模块包含7个子功能模组
- 专业的参数设置界面
- 实时配置摘要显示

## 📁 文件结构验证

### 核心文件
```
📁 项目根目录/
├── 📄 main.py                    # 主程序入口
├── 📄 manage_venv.py             # 虚拟环境管理器
├── 📄 requirements_windows.txt    # 依赖列表
├── 📄 setup.bat                 # Windows设置脚本
├── 📄 start.bat                 # Windows启动脚本
└── 📁 venv_aigc/               # 虚拟环境目录
```

### UI组件
```
📁 ui_components/
├── 📄 image_generation_page.py        # 图片生成页面
├── 📄 image_generation_*.py           # 图片生成子模块
├── 📄 redesigned_*.py                 # 重新设计的模块
└── 📁 enhanced_*.py                   # 增强功能组件
```

### 后端模块
```
📁 backend_modules/
├── 📄 backend_integration.py          # 后端集成
├── 📄 image_editing_backend.py       # 图片编辑后端
├── 📄 video_generation_backend.py    # 视频生成后端
└── 📄 threed_generation_backend.py   # 3D生成后端
```

## 🔍 功能测试步骤

### 测试1：图片生成功能
1. 点击"图片生成"标签页
2. 在模型模组中选择一个模型
3. 在提示词模组中输入文本
4. 设置生成参数（步数、CFG等）
5. 点击"开始生成"
6. 检查是否生成图片

### 测试2：模型加载
1. 在模型模组中点击"浏览"
2. 选择本地模型文件（.safetensors, .ckpt）
3. 验证模型是否成功加载
4. 检查模型信息显示

### 测试3：提示词处理
1. 在提示词模组中选择风格模板
2. 测试批量加载功能
3. 验证模板应用效果
4. 测试AI优化功能

### 测试4：ControlNet
1. 在ControlNet模组中选择类型
2. 加载参考图片
3. 调整控制权重
4. 测试预览功能

### 测试5：参数设置
1. 调整推理步数滑块
2. 修改CFG值
3. 更换采样器和调度器
4. 设置随机种子
5. 验证参数实时更新

## 🚨 常见问题解决

### 问题1：虚拟环境创建失败
```bash
# 解决：手动创建
python -m venv venv_aigc
venv_aigc\Scripts\activate  # Windows
source venv_aigc/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements_windows.txt
```

### 问题2：GPU检测失败
```bash
# 检查CUDA安装
nvidia-smi

# 检查PyTorch CUDA支持
python -c "import torch; print(torch.cuda.is_available())"
```

### 问题3：模型加载失败
- 检查模型文件路径
- 验证文件格式兼容性
- 确认磁盘空间充足

### 问题4：内存不足
- 关闭其他程序释放内存
- 使用较小的模型
- 调整批处理大小

## 📞 技术支持

### 日志文件位置
```
📁 logs/
├── 📄 app.log              # 应用程序日志
├── 📄 backend.log          # 后端服务日志
└── 📄 model.log            # 模型加载日志
```

### 性能监控
程序提供实时性能监控：
- GPU使用率
- 内存占用
- 生成进度
- 错误日志

## 🎯 性能优化建议

### 1. GPU优化
- 使用最新CUDA驱动
- 安装FlashAttention2
- 启用xFormers优化

### 2. 内存管理
- 及时清理缓存
- 使用混合精度推理
- 调整批处理大小

### 3. 存储优化
- 使用SSD存储
- 定期清理临时文件
- 压缩保存结果

---

**版本**: v6.0 (2026-02-04)  
**更新**: 最新功能集成  
**支持**: 完整的AIGC工作流