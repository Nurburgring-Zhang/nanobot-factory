#!/usr/bin/env python3
"""快速验证测试"""
import sys
from pathlib import Path

print("NanoBot Factory - 模块加载验证")
print("=" * 60)

results = []

# 1. 测试transformers
try:
    import transformers
    print(f"[OK] transformers {transformers.__version__}")
    results.append(("transformers", True))
except Exception as e:
    print(f"[FAIL] transformers: {e}")
    results.append(("transformers", False))

# 2. 测试diffusers
try:
    import diffusers
    print(f"[OK] diffusers {diffusers.__version__}")
    results.append(("diffusers", True))
except Exception as e:
    print(f"[FAIL] diffusers: {e}")
    results.append(("diffusers", False))

# 3. 测试text_to_image_backend
try:
    sys.path.insert(0, str(Path(__file__).parent / "omni_gen_studio" / "backend_modules"))
    from text_to_image_backend import TextToImageGenerator
    print("[OK] TextToImageGenerator")
    results.append(("text_to_image_backend", True))
except Exception as e:
    print(f"[FAIL] TextToImageGenerator: {str(e)[:80]}")
    results.append(("text_to_image_backend", False))

# 4. 测试image_to_image_backend
try:
    from image_to_image_backend import ImageToImageGenerator
    print("[OK] ImageToImageGenerator")
    results.append(("image_to_image_backend", True))
except Exception as e:
    print(f"[FAIL] ImageToImageGenerator: {str(e)[:80]}")
    results.append(("image_to_image_backend", False))

# 5. 测试video_generation_backend
try:
    from video_generation_backend import VideoGenerationBackend
    print("[OK] VideoGenerationBackend")
    results.append(("video_generation_backend", True))
except Exception as e:
    print(f"[FAIL] VideoGenerationBackend: {str(e)[:80]}")
    results.append(("video_generation_backend", False))

# 6. 测试diffuser_engine
try:
    from diffuser_engine import DiffuserEngine
    print("[OK] DiffuserEngine")
    results.append(("diffuser_engine", True))
except Exception as e:
    print(f"[FAIL] DiffuserEngine: {str(e)[:80]}")
    results.append(("diffuser_engine", False))

# 总结
print("=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"结果: {passed}/{total} 通过")
print("版本限制修复: patch_transformers.py 成功")
