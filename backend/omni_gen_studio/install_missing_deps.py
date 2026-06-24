#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动安装缺失依赖的脚本
专门解决FlashAttention2等加速库安装问题

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import subprocess
import sys
import os
from pathlib import Path

def print_header():
    """打印标题"""
    print("=" * 60)
    print("🔧 FlashAttention2 和依赖安装工具")
    print("=" * 60)
    print("📅 2026-02-04")
    print("👨‍💻 MiniMax Agent")
    print("=" * 60)

def check_pytorch():
    """检查PyTorch安装情况"""
    print("🔍 检查PyTorch安装...")
    try:
        import torch
        print(f"✅ PyTorch版本: {torch.__version__}")
        
        # 检查CUDA支持
        if torch.cuda.is_available():
            cuda_version = torch.version.cuda
            print(f"✅ CUDA支持: {torch.cuda.get_device_name(0)} (CUDA {cuda_version})")
            return True
        else:
            print("⚠️ 未检测到CUDA，使用CPU模式")
            return True
    except ImportError:
        print("❌ PyTorch未安装")
        return False

def install_pytorch():
    """安装PyTorch"""
    print("\n📦 安装PyTorch...")
    
    # 检测CUDA版本
    cuda_version = None
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'], 
                             capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 检测到NVIDIA GPU")
            cuda_version = "cu126"  # 最新的CUDA版本
        else:
            print("⚠️ 未检测到NVIDIA GPU，将安装CPU版本")
    except FileNotFoundError:
        print("⚠️ nvidia-smi命令未找到，将安装CPU版本")
    
    # 安装命令
    if cuda_version:
        cmd = [
            sys.executable, "-m", "pip", "install", 
            "torch", "torchvision", "torchaudio", 
            "--index-url", f"https://download.pytorch.org/whl/{cuda_version}"
        ]
    else:
        cmd = [
            sys.executable, "-m", "pip", "install", 
            "torch", "torchvision", "torchaudio"
        ]
    
    try:
        print("正在安装PyTorch...")
        subprocess.run(cmd, check=True)
        print("✅ PyTorch安装成功")
        return True
    except subprocess.CalledProcessError:
        print("❌ PyTorch安装失败")
        return False

def install_flash_attention():
    """安装FlashAttention2"""
    print("\n🚀 安装FlashAttention2...")
    
    # FlashAttention2需要特定的PyTorch版本支持
    try:
        import torch
        torch_version = torch.__version__
        print(f"📋 检测到PyTorch版本: {torch_version}")
        
        # 根据PyTorch版本选择合适的FlashAttention2版本
        if "cu126" in torch_version:
            # CUDA 12.6
            cmd = [sys.executable, "-m", "pip", "install", "flash-attn", "--no-build-isolation"]
        elif "cu124" in torch_version:
            # CUDA 12.4
            cmd = [sys.executable, "-m", "pip", "install", "flash-attn", "--no-build-isolation"]
        elif "cu118" in torch_version:
            # CUDA 11.8
            cmd = [sys.executable, "-m", "pip", "install", "flash-attn", "--no-build-isolation"]
        else:
            # 通用安装
            cmd = [sys.executable, "-m", "pip", "install", "flash-attn"]
        
        print("正在安装FlashAttention2...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ FlashAttention2安装成功")
            
            # 测试导入
            try:
                import flash_attn
                print("✅ FlashAttention2导入测试通过")
                return True
            except ImportError:
                print("⚠️ FlashAttention2安装完成但导入测试失败，可能是版本兼容性问题")
                return True
        else:
            print(f"❌ FlashAttention2安装失败:")
            print(f"错误信息: {result.stderr}")
            return False
            
    except ImportError:
        print("❌ 需要先安装PyTorch")
        return False

def install_xformers():
    """安装xFormers"""
    print("\n⚡ 安装xFormers...")
    
    try:
        import torch
        torch_version = torch.__version__
        
        # 根据CUDA版本选择xFormers版本
        if torch.cuda.is_available():
            if "cu126" in torch_version:
                cmd = [sys.executable, "-m", "pip", "install", "xformers", "--index-url", "https://wheels.xformers.dev/"]
            elif "cu124" in torch_version:
                cmd = [sys.executable, "-m", "pip", "install", "xformers", "--index-url", "https://wheels.xformers.dev/"]
            else:
                cmd = [sys.executable, "-m", "pip", "install", "xformers"]
        else:
            # CPU版本
            cmd = [sys.executable, "-m", "pip", "install", "xformers"]
        
        print("正在安装xFormers...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ xFormers安装成功")
            
            # 测试导入
            try:
                import xformers
                print("✅ xFormers导入测试通过")
                return True
            except ImportError:
                print("⚠️ xFormers安装完成但导入测试失败")
                return True
        else:
            print(f"❌ xFormers安装失败:")
            print(f"错误信息: {result.stderr}")
            return False
            
    except ImportError:
        print("❌ 需要先安装PyTorch")
        return False

def install_diffusers():
    """安装Diffusers和相关库"""
    print("\n🤗 安装Diffusers和相关库...")
    
    packages = [
        "diffusers>=0.21.0",
        "transformers>=4.25.0",
        "accelerate>=0.20.0",
        "safetensors>=0.3.0",
        "bitsandbytes>=0.41.0"
    ]
    
    for package in packages:
        try:
            print(f"正在安装 {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
            print(f"✅ {package} 安装成功")
        except subprocess.CalledProcessError:
            print(f"❌ {package} 安装失败")
            return False
    
    return True

def install_other_deps():
    """安装其他依赖"""
    print("\n📦 安装其他依赖...")
    
    packages = [
        "pillow>=9.0.0",
        "numpy>=1.21.0",
        "opencv-python>=4.5.0",
        "scikit-image>=0.19.0",
        "requests>=2.25.0",
        "tqdm>=4.62.0"
    ]
    
    for package in packages:
        try:
            print(f"正在安装 {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
            print(f"✅ {package} 安装成功")
        except subprocess.CalledProcessError:
            print(f"❌ {package} 安装失败")
    
    return True

def test_installation():
    """测试安装"""
    print("\n🧪 测试安装结果...")
    
    # 测试PyTorch
    try:
        import torch
        print(f"✅ PyTorch: {torch.__version__}")
        if torch.cuda.is_available():
            print(f"✅ CUDA: {torch.cuda.get_device_name(0)}")
        else:
            print("⚠️ CPU模式")
    except ImportError:
        print("❌ PyTorch导入失败")
    
    # 测试FlashAttention2
    try:
        import flash_attn
        print("✅ FlashAttention2: 可用")
    except ImportError:
        print("⚠️ FlashAttention2: 不可用（可能是版本兼容性）")
    
    # 测试xFormers
    try:
        import xformers
        print("✅ xFormers: 可用")
    except ImportError:
        print("⚠️ xFormers: 不可用")
    
    # 测试Diffusers
    try:
        import diffusers
        print(f"✅ Diffusers: {diffusers.__version__}")
    except ImportError:
        print("❌ Diffusers导入失败")

def main():
    """主函数"""
    print_header()
    
    # 检查当前环境
    current_dir = Path(__file__).parent
    venv_path = current_dir / "venv_aigc"
    
    print(f"📍 当前目录: {current_dir}")
    print(f"🐍 虚拟环境: {venv_path}")
    
    # 检查是否在虚拟环境中
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if not in_venv:
        print("⚠️ 警告: 当前不在虚拟环境中")
        response = input("是否继续安装? (y/N): ").strip().lower()
        if response not in ['y', 'yes', '是']:
            print("安装取消")
            return
    else:
        print("✅ 检测到虚拟环境")
    
    # 询问安装范围
    print("\n请选择安装范围:")
    print("1. 完整安装 (推荐) - PyTorch + FlashAttention2 + xFormers + Diffusers")
    print("2. 仅安装FlashAttention2")
    print("3. 仅安装xFormers")
    print("4. 仅安装PyTorch")
    print("5. 自定义安装")
    
    choice = input("请选择 (1-5): ").strip()
    
    # 根据选择执行安装
    success = True
    
    if choice in ['1', '5']:
        # 安装PyTorch
        if not check_pytorch():
            if not install_pytorch():
                success = False
        
        # 安装其他依赖
        if success and choice == '1':
            install_other_deps()
    
    if choice in ['1', '2']:
        if success:
            install_flash_attention()
    
    if choice in ['1', '3']:
        if success:
            install_xformers()
    
    if choice in ['1', '5']:
        if success:
            install_diffusers()
    
    # 测试安装
    test_installation()
    
    # 结果总结
    print("\n" + "=" * 60)
    if success:
        print("🎉 安装完成!")
        print("现在可以运行: python main.py")
    else:
        print("⚠️ 部分安装失败")
        print("请检查错误信息并重试")
    print("=" * 60)

if __name__ == "__main__":
    main()
