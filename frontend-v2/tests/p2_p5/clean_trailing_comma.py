#!/usr/bin/env python3
"""Remove trailing comma after TODO comment."""
import os
import re

LOCALES_DIR = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales"

LOCALES = ["en-US.ts", "zh-CN.ts", "ja-JP.ts", "ko-KR.ts", "fr-FR.ts",
           "de-DE.ts", "es-ES.ts", "ru-RU.ts", "ar-SA.ts", "pt-PT.ts"]

for fname in LOCALES:
    path = os.path.join(LOCALES_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Replace `, // TODO: native review,` with `, // TODO: native review`
    new_content = content.replace("review,", "review", 1)  # Only replace once per file? No, all
    # Use regex
    new_content = re.sub(r"(review),\s*$", r"\1", content, flags=re.MULTILINE)
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Cleaned trailing comma in {fname}")
    else:
        print(f"  No trailing comma in {fname}")
