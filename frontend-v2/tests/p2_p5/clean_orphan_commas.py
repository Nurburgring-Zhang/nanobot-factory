#!/usr/bin/env python3
"""Clean up orphan comma lines in all 10 locale files.

The previous add script left lines like:
    t033: 'value'
  ,
    t034: 'next value',

We want to merge the orphan comma into the previous line:
    t033: 'value',
    t034: 'next value',
"""
import os
import re

LOCALES_DIR = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales"

LOCALES = ["en-US.ts", "zh-CN.ts", "ja-JP.ts", "ko-KR.ts", "fr-FR.ts",
           "de-DE.ts", "es-ES.ts", "ru-RU.ts", "ar-SA.ts", "pt-PT.ts"]

for fname in LOCALES:
    path = os.path.join(LOCALES_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Replace pattern:  line ending with `\n  ,\n` with `,\n`
    # Use regex: capture the line that doesn't end with a comma, then `  ,\n`
    new_content = re.sub(r"([^,\n])\n(\s+),\n", r"\1,\n", content)
    
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Cleaned orphan commas in {fname}")
    else:
        print(f"  No orphan commas in {fname}")
