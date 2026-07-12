#!/usr/bin/env python3
"""Fix TODO comment placement for apostrophe-containing strings.

For lines like:
    t020: 'Nombre d\'éléments' // TODO: native review,
the comma is inside the comment. We need:
    t020: 'Nombre d\'éléments', // TODO: native review
"""
import os
import re

LOCALES_DIR = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales"

NON_EN_FILES = ["zh-CN.ts", "ja-JP.ts", "ko-KR.ts", "fr-FR.ts", "de-DE.ts",
                "es-ES.ts", "ru-RU.ts", "ar-SA.ts", "pt-PT.ts"]

def fix_line(line):
    """If a line has the broken pattern (no comma between value and // comment),
    insert a comma. Return (new_line, changed).
    """
    if '// TODO: native review' not in line:
        return line, False

    # Find the start of the string (first single quote after the colon)
    colon_idx = line.find(':')
    if colon_idx < 0:
        return line, False

    # Find the opening single quote
    quote_idx = line.find("'", colon_idx)
    if quote_idx < 0:
        return line, False

    # Walk through the string, tracking escapes
    pos = quote_idx + 1
    while pos < len(line):
        ch = line[pos]
        if ch == '\\' and pos + 1 < len(line):
            pos += 2
            continue
        if ch == "'":
            break
        pos += 1

    if pos >= len(line):
        return line, False

    # pos is at the closing single quote
    # Now find the comment start
    comment_start = line.find('//', pos)
    if comment_start < 0:
        return line, False

    # Check what's between the closing quote and the comment
    between = line[pos+1:comment_start]
    stripped_between = between.strip()
    if stripped_between == '':
        # No comma between value and comment - need to add one
        new_line = line[:pos+1] + ',' + line[pos+1:]
        return new_line, True
    elif stripped_between == ',':
        # Comma already there, OK
        return line, False
    else:
        return line, False

for fname in NON_EN_FILES:
    path = os.path.join(LOCALES_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split('\n')
    new_lines = []
    changed_count = 0
    for line in lines:
        new_line, was_changed = fix_line(line)
        new_lines.append(new_line)
        if was_changed:
            changed_count += 1
    
    if changed_count:
        new_content = '\n'.join(new_lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Fixed {changed_count} lines in {fname}")
    else:
        print(f"  No fix needed in {fname}")
