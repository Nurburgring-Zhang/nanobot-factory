---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 304402204f02d6a47e887831777522071447c0d1043c12912ee3b5b93cb5a7c816f3669a022062b521ab8c46def96a2f32901f91a8a5d0a14482d1fad41c1867051c1218cdb9
    ReservedCode2: 3045022100b6ef47ecd07c1d9907799529b43c549d3e89d5f67844f389087dd986a5d3117802205511ce33924af0d848076d0bb879f1cf40626c0ac441ae650bbd3cba43b463d3
---

# AIGC批处理工具 v5.4 - Windows版本

## 🎯 快速开始

### 方法一：使用Windows批处理文件 (推荐)
双击运行 `启动工具.bat` 文件即可自动完成所有设置并启动程序。

### 方法二：使用Python启动器
```bash
python quick_start.py
```

### 方法三：使用虚拟环境管理器
```bash
# 创建虚拟环境并运行
python manage_venv.py run

# 或者分步骤执行
python manage_venv.py create    # 创建虚拟环境
python manage_venv.py install   # 安装依赖
python manage_venv.py run       # 运行程序
```

## 🔧 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.8 或更高版本
- **内存**: 最少 4GB RAM (推荐 8GB+)
- **硬盘**: 至少 2GB 可用空间
- **显卡**: 支持 CUDA 的 NVIDIA 显卡 (可选，用于AI加速)

## 📦 文件说明

| 文件名 | 用途 | 说明 |
|--------|------|------|
| `启动工具.bat` | Windows批处理启动器 | 主要启动方式，自动处理虚拟环境和依赖 |
| `quick_start.py` | Python快速启动器 | 简化版本，适合有经验的用户 |
| `manage_venv.py` | 虚拟环境管理器 | 完整的环境管理功能 |
| `requirements_windows.txt` | Windows优化依赖 | 专门为Windows优化的依赖列表 |
| `main.py` | 主程序入口 | 应用程序主文件 |
| `README_Windows.md` | 本说明文档 | 详细使用指南 |

## 🚀 启动方式详解

### 1. 批处理文件启动 (最简单)

1. 确保已安装Python 3.8+
2. 双击 `启动工具.bat`
3. 等待自动配置完成
4. 程序将自动启动

### 2. Python脚本启动

```bash
# 方法一：快速启动
python quick_start.py

# 方法二：完整管理
python manage_venv.py run
```

### 3. 手动虚拟环境管理

```bash
# 创建虚拟环境
python -m venv venv_aigc

# 激活虚拟环境 (Windows)
venv_aigc\Scripts\activate

# 安装依赖
pip install -r requirements_windows.txt

# 运行程序
python main.py
```

## ⚠️ 常见问题解决

### 问题1：Python未安装
**症状**: 提示"python不是内部或外部命令"
**解决**: 
1. 访问 https://www.python.org/downloads/
2. 下载并安装Python 3.8+
3. 安装时勾选"Add Python to PATH"

### 问题2：依赖安装失败
**症状**: pip安装包时出错
**解决**: 
1. 确保网络连接正常
2. 尝试使用国内镜像源：
   ```bash
   pip install -r requirements_windows.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

### 问题3：虚拟环境创建失败
**症状**: venv创建时出错
**解决**: 
1. 检查Python版本 (需要3.8+)
2. 以管理员身份运行命令提示符
3. 尝试清理缓存：`pip cache purge`

### 问题4：程序启动报错
**症状**: 主程序运行时出现错误
**解决**: 
1. 检查Python和依赖版本
2. 查看详细错误信息
3. 尝试重新安装依赖：`pip install --force-reinstall -r requirements_windows.txt`

### 问题5：编码问题
**症状**: 中文显示乱码
**解决**: 
1. 确保使用UTF-8编码保存的文件
2. Windows命令行使用 `chcp 65001` 设置编码
3. 使用IDE时设置文件编码为UTF-8

## 🔍 环境诊断

运行诊断脚本检查环境：
```bash
python manage_venv.py check
```

这将显示：
- Python版本信息
- 项目目录路径
- 虚拟环境状态
- 依赖包安装情况

## 🛠️ 高级配置

### 自定义依赖
如果需要安装额外的依赖包，可以：
1. 编辑 `requirements_windows.txt` 文件
2. 添加所需的包名和版本
3. 重新运行安装命令

### 性能优化
对于有NVIDIA显卡的用户，可以安装CUDA版本的PyTorch：
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 代理设置
如果需要使用代理安装包：
```bash
pip install -r requirements_windows.txt --proxy http://proxy:port
```

## 📞 技术支持

如果遇到问题：

1. **首先检查**:
   - Python版本是否满足要求
   - 网络连接是否正常
   - 是否有足够的磁盘空间

2. **查看日志**:
   - 检查控制台输出的错误信息
   - 运行诊断脚本获取详细信息

3. **重新安装**:
   - 删除虚拟环境文件夹
   - 重新运行启动脚本

## 🎉 功能特色

- ✅ **自动化环境配置**: 无需手动设置虚拟环境
- ✅ **UTF-8编码支持**: 完美支持中文显示
- ✅ **Windows优化**: 针对Windows系统特别优化
- ✅ **依赖智能检测**: 自动检查和安装必要依赖
- ✅ **错误诊断**: 提供详细的错误诊断信息
- ✅ **多启动方式**: 支持多种启动方式适应不同需求

## 📝 更新日志

### v5.4 Windows版本
- 🆕 新增Windows专用启动器
- 🆕 集成虚拟环境管理
- 🔧 优化依赖包管理
- 🔧 修复UTF-8编码问题
- 🔧 改进错误诊断功能
- 📦 更新requirements文件

---

**版本**: v5.4 Windows版本  
**更新日期**: 2026-01-30  
**兼容性**: Python 3.8+, Windows 10/11