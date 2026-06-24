#!/usr/bin/env python3
"""下载最优本地模型 — 一键安装"""
import os, sys, subprocess

MODELS = {
    "bge-m3": {
        "name": "BAAI/bge-m3",
        "size": "2.2GB",
        "use": "文本嵌入+自动打标(中文最优)",
        "pip": "sentence-transformers",
        "code": "from sentence_transformers import SentenceTransformer\nmodel = SentenceTransformer('BAAI/bge-m3')"
    },
    "aesthetic-v2": {
        "name": "LAION-AI/aesthetic-predictor-v2",
        "size": "890MB",
        "use": "审美评分",
        "pip": "transformers torch",
        "code": "from transformers import pipeline\nscorer = pipeline('image-classification', model='LAION-AI/aesthetic-predictor-v2')"
    },
    "musiq": {
        "name": "google/musiq",
        "size": "100MB",
        "use": "图片质量评估(NR-IQA)",
        "pip": "transformers torch",
        "code": "from transformers import pipeline\nmusiq = pipeline('image-quality-assessment', model='google/musiq')"
    },
    "clip-vit": {
        "name": "openai/clip-vit-base-patch32",
        "size": "600MB",
        "use": "图片语义特征(替代pHash)",
        "pip": "transformers torch",
        "code": "from transformers import CLIPModel, CLIPProcessor\nmodel = CLIPModel.from_pretrained('openai/clip-vit-base-patch32')"
    }
}

print("=" * 60)
print("  IMDF 最优本地模型下载")
print("=" * 60)
print(f"  总大小: ~4GB")
print(f"  磁盘可用: {__import__('shutil').disk_usage('.').free // (1024**3)}GB")
print()

for key, info in MODELS.items():
    print(f"\n--- {info['name']} ({info['size']}) ---")
    print(f"  用途: {info['use']}")
    print(f"  安装: pip install {info['pip']}")
    print(f"  首次运行时自动下载模型文件")
    
    # 尝试预下载
    try:
        print(f"  预下载中...")
        exec(info['code'])
        print(f"  ✅ 下载完成")
    except ImportError:
        print(f"  ⚠️ 需先: pip install {info['pip']}")
    except Exception as e:
        print(f"  ⚠️ {str(e)[:80]}")

print(f"\n{'=' * 60}")
print("  下载完成。模型缓存于 ~/.cache/huggingface/")
print("  本地模型优于云API的场景: 低延迟/离线/隐私/免费用")
print(f"{'=' * 60}")
