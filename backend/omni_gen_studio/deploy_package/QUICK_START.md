---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 30450220416fb402efed8d93c96afa408bb381e517d6bd4f83273515054d57404cd725d0022100f2e09c312500533000fd977c37c244f66f679cdd74d0ac3ceedd826b24274e73
    ReservedCode2: 3046022100c7de096c11603e5b4c0f9318e94d017b534da9b806f7248eedce0d8a7b5db790022100d4ac4e38fea0a554c43656d1bd3c47bf9477691bcbcf06aa31d653651efd31ba
---

# 🚀 快速开始 - General AIGC Enhanced

## 5分钟快速启动

### Windows用户
1. **解压文件** - 将压缩包解压到任意目录
2. **运行脚本** - 双击 `start.bat`
3. **打开浏览器** - 访问 http://localhost:3000

### Linux/macOS用户  
1. **解压文件** - 解压到目录
2. **运行脚本** - 在终端执行 `./start.sh`
3. **打开浏览器** - 访问 http://localhost:3000

## 🔧 系统检查

运行 `check_system.bat` (Windows) 或手动检查：
- ✅ Python 3.8+
- ✅ 8GB+ 内存
- ✅ 20GB+ 存储空间
- ✅ NVIDIA显卡（可选）

## 🛑 停止服务

- **Windows**: 双击 `stop.bat`
- **Linux/macOS**: 在终端执行 `./stop.sh`

## 📁 重要文件

- `start.bat/sh` - 启动服务
- `stop.bat/sh` - 停止服务  
- `check_system.bat` - 系统检查
- `README.md` - 详细说明
- `config/application.json` - 配置文件

## ⚠️ 故障排除

**端口占用**: 修改 `config/application.json` 中的端口号  
**Python问题**: 安装Python 3.8+并添加到PATH  
**GPU驱动**: 安装最新NVIDIA驱动

## 🎯 下一步

启动成功后，浏览器会打开应用界面，您可以：
- 配置本地AI模型
- 开始生成图像、视频、3D内容
- 管理项目和工作流

**详细文档**: 请查看 `README.md`