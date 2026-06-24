#!/bin/bash
# General AIGC Enhanced - Environment Setup Script
# 自动环境配置脚本

set -e

echo "🚀 General AIGC Enhanced 环境配置开始..."

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查操作系统
check_os() {
    echo -e "${BLUE}检查操作系统...${NC}"
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        echo -e "${GREEN}✓ 检测到 Linux 系统${NC}"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        echo -e "${GREEN}✓ 检测到 macOS 系统${NC}"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
        echo -e "${GREEN}✓ 检测到 Windows 系统${NC}"
    else
        echo -e "${RED}✗ 不支持的操作系统: $OSTYPE${NC}"
        exit 1
    fi
}

# 检查Python版本
check_python() {
    echo -e "${BLUE}检查 Python 环境...${NC}"
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
        
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
            echo -e "${GREEN}✓ Python $PYTHON_VERSION 版本满足要求${NC}"
            PYTHON_CMD="python3"
        else
            echo -e "${RED}✗ Python $PYTHON_VERSION 版本过低，需要 Python 3.8+${NC}"
            exit 1
        fi
    else
        echo -e "${RED}✗ 未找到 Python3，请先安装 Python 3.8+${NC}"
        exit 1
    fi
}

# 检查pip
check_pip() {
    echo -e "${BLUE}检查 pip...${NC}"
    
    if command -v pip3 &> /dev/null; then
        echo -e "${GREEN}✓ pip3 已安装${NC}"
        PIP_CMD="pip3"
    elif command -v pip &> /dev/null; then
        echo -e "${GREEN}✓ pip 已安装${NC}"
        PIP_CMD="pip"
    else
        echo -e "${RED}✗ 未找到 pip，请先安装 pip${NC}"
        exit 1
    fi
}

# 检查CUDA（如果需要）
check_cuda() {
    echo -e "${BLUE}检查 CUDA 环境...${NC}"
    
    if command -v nvidia-smi &> /dev/null; then
        CUDA_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1)
        echo -e "${GREEN}✓ NVIDIA 驱动版本: $CUDA_VERSION${NC}"
        
        if command -v nvcc &> /dev/null; then
            NVCC_VERSION=$(nvcc --version | grep "release" | sed 's/.*release \([0-9]*\.[0-9]*\).*/\1/')
            echo -e "${GREEN}✓ CUDA 版本: $NVCC_VERSION${NC}"
        else
            echo -e "${YELLOW}⚠ 未找到 nvcc，CUDA 工具包可能未安装${NC}"
        fi
        
        GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        if [ "$GPU_MEMORY" -gt 8000 ]; then
            echo -e "${GREEN}✓ GPU 显存: ${GPU_MEMORY}MB (足够运行大型模型)${NC}"
        else
            echo -e "${YELLOW}⚠ GPU 显存: ${GPU_MEMORY}MB (建议 8GB+ 以获得最佳性能)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ 未检测到 NVIDIA GPU，将使用 CPU 模式${NC}"
    fi
}

# 创建虚拟环境
create_venv() {
    echo -e "${BLUE}创建 Python 虚拟环境...${NC}"
    
    VENV_DIR="./krita-ai-env"
    
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}⚠ 虚拟环境已存在，跳过创建${NC}"
    else
        $PYTHON_CMD -m venv $VENV_DIR
        echo -e "${GREEN}✓ 虚拟环境创建成功: $VENV_DIR${NC}"
    fi
    
    # 激活虚拟环境
    if [[ "$OS" == "windows" ]]; then
        source $VENV_DIR/Scripts/activate
    else
        source $VENV_DIR/bin/activate
    fi
    
    echo -e "${GREEN}✓ 虚拟环境已激活${NC}"
}

# 安装基础依赖
install_base_deps() {
    echo -e "${BLUE}安装基础依赖...${NC}"
    
    # 升级pip
    $PIP_CMD install --upgrade pip
    
    # 安装基础包
    $PIP_CMD install wheel setuptools numpy
    
    echo -e "${GREEN}✓ 基础依赖安装完成${NC}"
}

# 安装PyTorch（根据CUDA情况）
install_pytorch() {
    echo -e "${BLUE}安装 PyTorch...${NC}"
    
    if command -v nvidia-smi &> /dev/null; then
        echo -e "${BLUE}检测到 NVIDIA GPU，安装 CUDA 版本 PyTorch...${NC}"
        $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
        echo -e "${GREEN}✓ CUDA 版本 PyTorch 安装完成${NC}"
    else
        echo -e "${BLUE}安装 CPU 版本 PyTorch...${NC}"
        $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
        echo -e "${GREEN}✓ CPU 版本 PyTorch 安装完成${NC}"
    fi
}

# 安装AI相关依赖
install_ai_deps() {
    echo -e "${BLUE}安装 AI 相关依赖...${NC}"
    
    # 基础AI库
    $PIP_CMD install \
        transformers \
        diffusers \
        accelerate \
        safetensors \
        xformers \
        huggingface_hub \
        opencv-python \
        pillow \
        scipy \
        scikit-image \
        matplotlib
    
    # 可选：安装flash-attention（如果支持）
    if command -v nvidia-smi &> /dev/null; then
        echo -e "${BLUE}安装 Flash Attention...${NC}"
        $PIP_CMD install flash-attn --no-build-isolation || echo -e "${YELLOW}⚠ Flash Attention 安装失败，跳过${NC}"
    fi
    
    # 可选：安装额外模型支持
    $PIP_CMD install \
        modelcards \
        datasets \
        evaluate \
        tensorboard
    
    echo -e "${GREEN}✓ AI 依赖安装完成${NC}"
}

# 安装其他工具
install_tools() {
    echo -e "${BLUE}安装其他工具...${NC}"
    
    # Supabase客户端
    npm install -g @supabase/cli || echo -e "${YELLOW}⚠ Supabase CLI 安装失败${NC}"
    
    # 其他有用的工具
    $PIP_CMD install \
        requests \
        aiohttp \
        python-dotenv \
        tqdm \
        psutil
    
    echo -e "${GREEN}✓ 工具安装完成${NC}"
}

# 创建配置目录
create_config_dirs() {
    echo -e "${BLUE}创建配置目录...${NC}"
    
    mkdir -p ./models/checkpoints
    mkdir -p ./models/lora
    mkdir -p ./models/controlnet
    mkdir -p ./models/vae
    mkdir -p ./models/clip
    mkdir -p ./temp
    mkdir -p ./output
    mkdir -p ./logs
    mkdir -p ./cache
    
    echo -e "${GREEN}✓ 配置目录创建完成${NC}"
}

# 创建环境变量文件
create_env_file() {
    echo -e "${BLUE}创建环境变量文件...${NC}"
    
    cat > .env << EOF
# General AIGC Enhanced 环境配置

# 基础路径配置
MODELS_DIR=./models
TEMP_DIR=./temp
OUTPUT_DIR=./output
LOGS_DIR=./logs
CACHE_DIR=./cache

# AI模型配置
DIFFUSERS_CACHE_DIR=./cache/diffusers
TRANSFORMERS_CACHE_DIR=./cache/transformers
COMFYUI_MODELS_DIR=./models

# GPU配置
CUDA_VISIBLE_DEVICES=0
TORCH_CUDA_ARCH_LIST=8.6;8.9;9.0

# API配置（可选）
OLLAMA_API_URL=http://localhost:11434
VLLM_API_URL=http://localhost:8001
LM_STUDIO_API_URL=http://localhost:1234

# 文件处理配置
MAX_FILE_SIZE=2147483648
MAX_BATCH_SIZE=4

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=./logs/krita-ai.log
EOF
    
    echo -e "${GREEN}✓ 环境变量文件创建完成: .env${NC}"
}

# 测试安装
test_installation() {
    echo -e "${BLUE}测试安装...${NC}"
    
    # 测试Python包导入
    $PYTHON_CMD -c "
import torch
import transformers
import diffusers
import PIL
print('✓ PyTorch 版本:', torch.__version__)
print('✓ CUDA 可用:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('✓ GPU 设备:', torch.cuda.get_device_name(0))
print('✓ Transformers 可用')
print('✓ Diffusers 可用')
print('✓ PIL 可用')
print('✓ 安装测试通过!')
" || {
    echo -e "${RED}✗ 安装测试失败${NC}"
    exit 1
}
    
    echo -e "${GREEN}✓ 安装测试通过${NC}"
}

# 显示使用说明
show_usage() {
    echo -e "\n${GREEN}🎉 General AIGC Enhanced 环境配置完成!${NC}\n"
    echo -e "${BLUE}使用说明:${NC}"
    echo -e "1. 激活虚拟环境:"
    echo -e "   ${YELLOW}source ./krita-ai-env/bin/activate${NC}  (Linux/macOS)"
    echo -e "   ${YELLOW}./krita-ai-env/Scripts/activate${NC}     (Windows)"
    echo -e ""
    echo -e "2. 运行应用:"
    echo -e "   ${YELLOW}python ai_inference.py --config config.json${NC}"
    echo -e ""
    echo -e "3. 下载模型:"
    echo -e "   ${YELLOW}python -m transformers-cli download stabilityai/stable-diffusion-xl-base-1.0${NC}"
    echo -e ""
    echo -e "4. 配置 Supabase:"
    echo -e "   - 创建 Supabase 项目"
    echo -e "   - 运行数据库迁移: ${YELLOW}supabase db push${NC}"
    echo -e "   - 部署 Edge Functions: ${YELLOW}supabase functions deploy${NC}"
    echo -e ""
    echo -e "${BLUE}注意事项:${NC}"
    echo -e "- 确保有足够的磁盘空间 (建议 50GB+)"
    echo -e "- GPU 用户建议安装 CUDA 工具包"
    echo -e "- 首次运行需要下载模型，请耐心等待"
    echo -e ""
    echo -e "${BLUE}支持:${NC}"
    echo -e "- 文档: ./docs/README.md"
    echo -e "- 日志: ./logs/krita-ai.log"
}

# 主函数
main() {
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN} General AIGC Enhanced 环境配置工具 ${NC}"
    echo -e "${GREEN}================================${NC}\n"
    
    check_os
    check_python
    check_pip
    check_cuda
    create_venv
    install_base_deps
    install_pytorch
    install_ai_deps
    install_tools
    create_config_dirs
    create_env_file
    test_installation
    show_usage
    
    echo -e "\n${GREEN}🎉 环境配置完成! 祝您使用愉快!${NC}"
}

# 运行主函数
main "$@"