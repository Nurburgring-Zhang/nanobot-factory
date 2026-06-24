---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3046022100e5b17bde1e1e816127abc5f54b99870378f1f71d87733b4e24e639956cb58099022100e255f038b5713166f30c50ba00d1fdae9723715922018e23e4a30b42918de0d6
    ReservedCode2: 304402200428bace1a5423b85d1008b66d62a065d1a1fc164ed8df80a81134efd2f0373a0220038092b00f66c186e62667cc9259522aab6c687f276031c8ccba1074dbf36136
---

# General AIGC Enhanced - 本地化部署版本

## 简介

General AIGC Enhanced 是一个完全本地化的AI生成工具，支持图像、视频、3D模型生成，无需依赖云端服务。

## 主要特性

- ✅ **本地化AI生成** - 无需云端依赖，保护隐私
- ✅ **多模态支持** - 图像、视频、3D模型生成
- ✅ **GPU加速** - 支持RTX4090等高端显卡
- ✅ **ComfyUI集成** - 可视化工作流编辑
- ✅ **WebUI支持** - Stable Diffusion WebUI集成
- ✅ **离线运行** - 完全脱离网络运行

## 系统要求

### 最低要求
- **操作系统**: Windows 10+, macOS 10.14+, Linux (Ubuntu 18.04+)
- **Python**: 3.8+
- **内存**: 8GB RAM
- **存储**: 20GB 可用空间

### 推荐配置
- **显卡**: NVIDIA RTX 3060+ (推荐RTX 4090)
- **内存**: 16GB+ RAM
- **存储**: 100GB+ SSD

## 快速开始

### Windows用户

1. **下载并解压**
   ```
   下载 deploy_package.zip 并解压到任意目录
   ```

2. **运行启动脚本**
   ```
   双击 start.bat 或在命令提示符中运行 start.bat
   ```

3. **访问应用**
   ```
   浏览器访问: http://localhost:3000
   ```

### Linux/macOS用户

1. **下载并解压**
   ```bash
   unzip deploy_package.zip
   cd deploy_package
   ```

2. **运行启动脚本**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

3. **访问应用**
   ```
   浏览器访问: http://localhost:3000
   ```

## 目录结构

```
deploy_package/
├── start.bat              # Windows启动脚本
├── start.sh               # Linux/macOS启动脚本
├── README.md              # 说明文档
├── config/                # 配置文件
│   └── application.json   # 应用配置
├── frontend/              # 前端文件
│   ├── index.html         # 主页
│   └── assets/            # 静态资源
└── backend/               # 后端文件
    ├── main.py            # FastAPI主程序
    ├── requirements_windows.txt  # Python依赖
    ├── quick_start.py     # 快速启动脚本
    ├── setup.bat          # Windows环境设置
    ├── backend_modules/   # 后端模块
    └── src/              # React源码
```

## 配置说明

### 端口配置
- **前端端口**: 3000
- **后端端口**: 8000
- **API文档**: http://localhost:8000/docs

### 模型配置
应用支持以下模型类型：
- **图像生成**: Stable Diffusion, SDXL, ControlNet
- **视频生成**: AnimateDiff, SVD
- **3D模型**: DreamFusion, Magic3D

## 故障排除

### 常见问题

**1. Python环境问题**
```
错误: 'python' 不是内部或外部命令
解决: 安装Python 3.8+并添加到PATH
```

**2. 端口占用问题**
```
错误: [Errno 10048] 通常每个套接字地址(协议/网络地址/端口)只允许使用一次
解决: 关闭占用端口的程序或修改配置文件中的端口
```

**3. GPU驱动问题**
```
错误: CUDA error: no kernel image is available for execution on the device
解决: 安装最新NVIDIA驱动和CUDA toolkit
```

**4. 依赖安装失败**
```
错误: pip install失败
解决: 
1. 更新pip: python -m pip install --upgrade pip
2. 使用国内镜像: pip install -r requirements_windows.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 日志查看

- **后端日志**: `backend/backend.log`
- **前端日志**: `frontend/frontend.log`

## 开发信息

### 技术栈
- **前端**: React 18 + TypeScript + Tailwind CSS
- **后端**: Python 3.8+ + FastAPI + SQLAlchemy
- **AI框架**: PyTorch + Diffusers + Transformers
- **UI库**: Radix UI + Lucide Icons

### API文档
启动服务后访问: http://localhost:8000/docs

## 更新日志

### v1.0.0 (2026-02-04)
- ✅ 初始版本发布
- ✅ 完整本地化架构
- ✅ React + FastAPI双端架构
- ✅ ComfyUI/WebUI集成
- ✅ 多模态AI生成支持

## 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 支持

如有问题，请查看故障排除部分或查看项目文档。

---

**General AIGC Enhanced v1.0.0**  
*本地化AI生成工具，让AI创作更自由*