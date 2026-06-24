---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3044022001fa2ed37bd4bec4abbd502330c3ef5b0c36d2611f9e220bd1645904f6821b1802204a85f566dd5d6347e6b3345dde04e05b5d9f632d9f4afbd0a98b28f4e691fc24
    ReservedCode2: 3046022100de066baf537de5177fd1e75a057802f7c661e2a9faf215fcaf68b3b164b455c3022100b5268757941a22b3f46b9ee7e19bb13750fe40419e84d89023f1d764345bd7bc
---

# AIGC批处理工具 v5.4 - 快速启动指南

## 🚀 一键启动（推荐）

**方法1：使用批处理文件（推荐）**
1. 双击 `setup.bat` 进行环境配置
2. 等待自动设置虚拟环境（约2-3分钟）
3. 双击 `start.bat` 启动程序
4. 选择要运行的程序：
   - 主程序：运行AIGC批处理工具界面
   - ComfyUI：运行ComfyUI图形界面
   - WebUI：运行WebUI界面

**方法2：使用Python脚本**
```bash
python manage_venv.py setup
python manage_venv.py run
```

## ✨ 主要功能

### 🎨 图像处理
- 图像生成（文本到图像）
- 图像编辑和修复
- 图像超分辨率放大
- ControlNet控制

### 🎬 视频处理  
- 文本到视频生成
- 视频编辑和增强
- 视频风格转换

### 🎮 3D生成
- 文本到3D模型生成
- 3D场景构建
- 模型优化

### 🤖 AI集成
- **ComfyUI**: 高级工作流界面
- **WebUI**: 用户友好的图形界面

## 🛠️ 环境管理

### 虚拟环境
- 自动创建本地虚拟环境 `venv_aigc`
- 隔离依赖，避免冲突
- 支持Python 3.8+

### 依赖管理
- 自动安装所需Python包
- 支持CUDA（如果可用）
- 优化的Windows兼容性

## 📋 使用说明

### 第一次使用
1. 确保网络连接（需要下载依赖）
2. 双击 `setup.bat` 进行环境配置
3. 耐心等待环境配置完成
4. 双击 `start.bat` 启动程序

### 日常使用
1. 双击 `start.bat` 启动程序
2. 选择要运行的程序

### 故障排除
- **问题**: 批处理文件显示乱码
- **解决**: 确保使用支持UTF-8的文本编辑器打开

- **问题**: 虚拟环境创建失败
- **解决**: 检查Python是否正确安装，确保网络连接正常

## 🔧 高级配置

### 自定义设置
编辑 `manage_venv.py` 可自定义：
- 虚拟环境路径
- 依赖安装选项
- 启动参数

### 模型文件
- 首次运行时将自动下载基础模型
- 大型模型需要手动下载
- 详见 `README_Windows.md`

## 📞 技术支持

如遇问题，请：
1. 查看 `README_Windows.md` 详细文档
2. 检查 `logs/` 目录中的日志文件
3. 确保系统满足最低要求

---
**版本**: v5.4 Final Windows Optimized  
**更新**: 2026-01-30  
**特色**: 完整Windows兼容 + ComfyUI/WebUI集成
