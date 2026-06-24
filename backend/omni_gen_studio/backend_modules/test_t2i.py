#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试文生图模块"""

import sys
sys.path.insert(0, '.')

from text_to_image_backend import TextToImageGenerator, get_generator

print("Testing TextToImageGenerator...")

# 创建生成器实例
g = get_generator()
print(f"Device: {g.device}")
print(f"Available models: {g.get_available_models()}")
print(f"Available samplers: {g.get_available_samplers()}")
print(f"Available schedulers: {g.get_available_schedulers()}")
print(f"Memory info: {g.get_memory_info()}")

print("\nAll tests passed!")
