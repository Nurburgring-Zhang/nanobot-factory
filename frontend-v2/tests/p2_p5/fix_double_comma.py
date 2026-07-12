#!/usr/bin/env python3
"""Fix double commas introduced by previous fix scripts.

Pattern: 'value',, // TODO: native review
Target:  'value', // TODO: native review
"""
import os

LOCALES_DIR = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales"

NON_EN_FILES = ["zh-CN.ts", "ja-JP.ts", "ko-KR.ts", "fr-FR.ts", "de-DE.ts",
                "es-ES.ts", "ru-RU.ts", "ar-SA.ts", "pt-PT.ts"]

for fname in NON_EN_FILES:
    path = os.path.join(LOCALES_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Replace ',, // TODO' with ', // TODO'
    new_content = content.replace(",, // TODO", ", // TODO")
    # Also handle ',,\n    // TODO' for the last-key case
    new_content = new_content.replace(",,\n    // TODO", ",\n    // TODO")
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Fixed double-comma in {fname}")
    else:
        print(f"  No double-comma in {fname}")
