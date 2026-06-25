#!/usr/bin/env python3
"""模型与环境下载脚本 — 首次部署时运行"""
import os, sys, subprocess, urllib.request, json

BASE = os.path.dirname(os.path.abspath(__file__))

def step(msg):
    print(f"  [{msg}]", end=" ", flush=True)

def ok():
    print("✅")

def warn(msg=""):
    print(f"⚠️ {msg}")

# ===== ComfyUI 必需模型清单 =====
COMFY_MODELS = {
    "checkpoints": [
        {"name": "sd_xl_base_1.0.safetensors", "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors", "size": "6.94GB"},
    ],
    "vae": [
        {"name": "sdxl_vae.safetensors", "url": "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/diffusion_pytorch_model.safetensors", "size": "335MB"},
    ],
    "clip": [
        {"name": "clip_l.safetensors", "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors", "size": "246MB"},
    ],
    "controlnet": [
        {"name": "control_lora_rank256.safetensors", "url": "https://huggingface.co/stabilityai/control-lora/resolve/main/control-LoRAs-rank256/control-lora-canny-rank256.safetensors", "size": "738MB"},
    ],
}

# 轻量级标注模型(无需GPU)
LIGHTWEIGHT_MODELS = {
    "aesthetic": {
        "name": "aesthetic_scorer",
        "type": "pip",
        "package": "clip-interrogator",
        "size": "~50MB"
    },
    "classification": {
        "name": "zero-shot-classifier",
        "type": "pip",
        "package": "sentence-transformers",
        "size": "~100MB"
    },
}

def download_comfy_models():
    """下载ComfyUI模型(首次运行从HuggingFace自动下载)"""
    models_dir = os.path.join(BASE, "comfyui", "models")
    os.makedirs(models_dir, exist_ok=True)
    
    for category, models in COMFY_MODELS.items():
        cat_dir = os.path.join(models_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        for m in models:
            path = os.path.join(cat_dir, m["name"])
            if os.path.exists(path):
                step(f"已存在 {category}/{m['name']}"); ok()
                continue
            
            step(f"下载 {m['name']} ({m['size']})")
            print(f"\n    从 {m['url']}")
            print("    ⚠️ 大文件,请手动下载或首次运行ComfyUI时自动下载")
            # HuggingFace下载需要token,建议手动
            warn("跳过大文件")

def install_lightweight_models():
    """安装轻量级AI模型(通过pip)"""
    for key, info in LIGHTWEIGHT_MODELS.items():
        step(f"安装 {info['name']}")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", info["package"]],
                         capture_output=True, timeout=120)
            ok()
        except:
            warn(f"如需{info['name']}功能,请手动: pip install {info['package']}")

def verify_environment():
    """验证环境"""
    print("\n=== 环境验证 ===")
    checks = []
    
    # Python版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    checks.append(("Python 3.12+", py_ver >= "3.12", py_ver))
    
    # 核心依赖
    for mod, name in [("fastapi","FastAPI"), ("PIL","Pillow"), ("uvicorn","Uvicorn"),
                       ("argon2","Argon2"), ("sqlalchemy","SQLAlchemy"), ("apscheduler","APScheduler"),
                       ("sklearn","Scikit-learn"), ("rank_bm25","BM25"), ("httpx","HTTPx")]:
        try: __import__(mod); checks.append((name, True, "✓"))
        except: checks.append((name, False, "✗"))
    
    # PyTorch
    try:
        import torch; checks.append(("PyTorch", True, torch.__version__))
    except: checks.append(("PyTorch", False, "✗ (ComfyUI需要)"))
    
    # ffmpeg
    try:
        subprocess.run(["ffmpeg","-version"], capture_output=True, timeout=5)
        checks.append(("ffmpeg", True, "✓"))
    except: checks.append(("ffmpeg", False, "✗ (视频/音频需要)"))
    
    # 磁盘空间
    import shutil
    disk = shutil.disk_usage(BASE)
    free_gb = disk.free / (1024**3)
    checks.append((f"磁盘空间", free_gb > 20, f"{free_gb:.1f}GB可用"))
    
    for name, ok, detail in checks:
        print(f"  {'✅' if ok else '❌'} {name}: {detail}")

if __name__ == "__main__":
    print("=" * 50)
    print("  IMDF + nanobot-factory 环境配置")
    print("=" * 50)
    
    print("\n--- 轻量模型 ---")
    install_lightweight_models()
    
    print("\n--- ComfyUI模型 ---")
    download_comfy_models()
    
    verify_environment()
    
    print("\n" + "=" * 50)
    print("  环境配置完成")
    print("  启动: python server_unified.py --port 8899")
    print("=" * 50)
    print("\nComfyUI大模型首次使用时会从HuggingFace自动下载")
    print("或手动放置到: comfyui/models/ 对应目录")
