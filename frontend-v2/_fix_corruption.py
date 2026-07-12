"""Fix corruption in 5 vue files: insert newlines after imports and statements."""
import re
import os

CORRUPTED_FILES = [
    'WorkflowBuilder.vue',
    'CapabilityRegistry.vue',
    'CollectionCenter.vue',
    'Delivery.vue',
    'PackManager.vue',
]

# The corruption pattern: statements are concatenated without semicolons/newlines.
# We need to add newlines after: imports, function decls, const/let/var decls, type/interface decls, end of statements

def fix_file(path):
    raw = open(path, 'rb').read()
    text = raw.decode('utf-8', errors='replace')

    if '\n' in text:
        print(f'  SKIP: {path} already has newlines ({text.count(chr(10))} newlines)')
        return False

    # Find script block boundaries
    script_start_m = re.search(r'<script setup[^>]*>', text)
    script_end_m = re.search(r'</script>', text)
    if not script_start_m or not script_end_m:
        print(f'  FAIL: {path} no script block found')
        return False

    script_start = script_start_m.end()
    script_end = script_end_m.start()

    before = text[:script_start]
    script_body = text[script_start:script_end]
    after = text[script_end:]

    print(f'  Script body: {len(script_body)} chars (offset {script_start}-{script_end})')

    # Add newlines:
    # 1. After each import statement: `from '...'` or `from "..."` followed by `const`/`import`/`function`/`type`/`interface`/`const`/`let`/`var`
    # 2. After `const { t } = useI18n()` followed by next statement
    # 3. After each top-level statement

    # Use a smart approach: split on `;` (which exist in original code) and on pattern boundaries
    # The corruption is: `from 'X'const` -> needs newline between
    # Also: `})const` -> needs newline
    # Also: `()const` -> needs newline

    # Strategy: find boundaries where a new statement should start
    # Insert newline before: `import `, `const `, `let `, `var `, `function `, `type `, `interface `, `export ` (at top level)
    # But careful: not before `const X` inside a function call like `foo(const = ...)`. So we only insert at top level.

    # Top-level detection: count unclosed `{}()` and only insert at depth 0
    fixed = []
    i = 0
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_string = None
    in_template = False
    in_comment = None  # 'line', 'block'
    prev_char = ''
    # We need to add \n when we encounter a top-level statement start
    statement_starts = (
        'import ', 'export ', 'const ', 'let ', 'var ',
        'function ', 'class ', 'interface ', 'type ', 'enum ',
    )

    # First, add \n after every `from '...'` and `from "..."`
    # Pattern: `from '(?:[^'\\]|\\.)*'` followed immediately by another keyword
    script_body = re.sub(
        r"(from\s+['\"][^'\"]*['\"])(?=(?:const|let|var|function|class|interface|type|enum|import|export|\(|\)|\}))",
        r"\1\n",
        script_body,
    )

    # Add \n after `const { t } = useI18n()` and similar destructuring
    # Pattern: `} = useI18n()` followed by keyword
    script_body = re.sub(
        r"(\}\s*=\s*useI18n\(\))(?=\s*(?:const|let|var|function|class|interface|type|enum|import|export|if|for|while|return))",
        r"\1\n",
        script_body,
    )

    # Add \n after `})` or `}))` (end of function calls/expressions) at top level before next statement
    # This is tricky - we'll do it character by character to track depth

    out = []
    i = 0
    n = len(script_body)
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_string = None
    in_template = False
    last_emit_nl = True  # we just emitted a newline (or starting)
    last_was_space = False
    while i < n:
        c = script_body[i]
        nxt = script_body[i+1] if i+1 < n else ''

        if in_string:
            out.append(c)
            if c == '\\' and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == in_string:
                in_string = None
            i += 1
            continue

        if in_template:
            out.append(c)
            if c == '\\' and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == '`':
                in_template = False
            i += 1
            continue

        if c == '/' and nxt == '/':
            # line comment
            j = script_body.find('\n', i)
            if j == -1:
                j = n
            out.append(script_body[i:j])
            i = j
            continue

        if c == '/' and nxt == '*':
            # block comment
            j = script_body.find('*/', i)
            if j == -1:
                j = n
            else:
                j += 2
            out.append(script_body[i:j])
            i = j
            continue

        if c in ('"', "'"):
            in_string = c
            out.append(c)
            i += 1
            continue

        if c == '`':
            in_template = True
            out.append(c)
            i += 1
            continue

        if c == '(':
            depth_paren += 1
        elif c == ')':
            depth_paren -= 1
        elif c == '{':
            depth_brace += 1
        elif c == '}':
            depth_brace -= 1
        elif c == '[':
            depth_bracket += 1
        elif c == ']':
            depth_bracket -= 1

        # At depth 0, if previous char was '}' or ')' or ';' and next chars are a statement start, insert newline
        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            if c in ('}', ')') or (c == ';' and not last_was_space):
                # Look ahead for a statement start
                rest = script_body[i+1:]
                # Check if a top-level keyword follows (allowing optional whitespace)
                m = re.match(r'\s*(import |export |const |let |var |function |class |interface |type |enum )', rest)
                if m:
                    out.append(c)
                    out.append('\n')
                    last_emit_nl = True
                    i += 1
                    continue

        out.append(c)
        i += 1
        last_emit_nl = (c == '\n')

    script_body = ''.join(out)

    new_text = before + script_body + after

    if new_text == text:
        print(f'  NO CHANGE: {path}')
        return False

    # Write back as UTF-8
    with open(path, 'wb') as f:
        f.write(new_text.encode('utf-8'))
    print(f'  FIXED: {path} -> {len(new_text)} chars, {new_text.count(chr(10))} newlines')
    return True


print('Fixing 5 corrupted 1-line SFCs...')
for fname in CORRUPTED_FILES:
    path = f'src/views/{fname}'
    print(f'\n{fname}:')
    fix_file(path)

print('\nDone.')
