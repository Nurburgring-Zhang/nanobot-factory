"""Aggressive newline insertion for 5 corrupted 1-line SFCs.

Strategy: Walk the script body character-by-character, track depth of (), {}, [], and string/comment state.
At depth 0, insert newlines:
- BEFORE any top-level keyword: import, export, const, let, var, function, class, interface, type, enum, onMounted, async
- AFTER any of: ; } (at top level) - then newline
- AFTER 'from "X"' or "from 'X'" (already handled by the first rule)
- AFTER `const { t } = useI18n();` and similar

Also fix:
- `}; async; function` -> `}\nasync function` (the `async;` is wrong - it should be `async `)
- `return '' const e =` -> `return '';\nconst e =` (missing semicolon)

Run the fix and then validate.
"""
import re
import sys

CORRUPTED_FILES = [
    'WorkflowBuilder.vue',
    'CapabilityRegistry.vue',
    'CollectionCenter.vue',
    'Delivery.vue',
    'PackManager.vue',
]


def split_statements(script_body):
    """Walk the script body, insert newlines at statement boundaries."""
    out = []
    n = len(script_body)
    i = 0
    depth = {'paren': 0, 'brace': 0, 'bracket': 0, 'template': 0}
    state = 'code'  # 'code', 'string', 'comment-line', 'comment-block', 'template'
    string_char = None

    def at_depth_zero():
        return all(d == 0 for d in depth.values())

    def peek_keyword(start):
        """If text starting at `start` is a top-level keyword (with optional whitespace before), return (end_offset, kw)."""
        # Match optional whitespace + keyword
        m = re.match(r'(?:\s*)(import|export|const|let|var|function|class|interface|type|enum|async|onMounted|computed|watch|watchEffect|provide|inject|reactive|toRef|toRefs|defineComponent|defineProps|defineEmits|withDefaults|useRoute|useRouter|useStore|useI18n|useMessage|useDialog|useNotification|useLoadingBar|storeToRefs|computed|getCurrentInstance)\b', script_body[start:])
        if m:
            return start + m.end(), m.group(1)
        return None

    # Statement terminators at depth 0: ; } ) and certain keywords
    # We insert newline AFTER terminators and BEFORE keywords

    while i < n:
        c = script_body[i]
        nxt = script_body[i+1] if i+1 < n else ''

        # Handle current state
        if state == 'string':
            out.append(c)
            if c == '\\' and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == string_char:
                state = 'code'
            i += 1
            continue

        if state == 'template':
            out.append(c)
            if c == '\\' and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == '`':
                state = 'code'
            i += 1
            continue

        if state == 'comment-line':
            out.append(c)
            if c == '\n':
                state = 'code'
            i += 1
            continue

        if state == 'comment-block':
            out.append(c)
            if c == '*' and nxt == '/':
                out.append(nxt)
                i += 2
                state = 'code'
                continue
            i += 1
            continue

        # state == 'code'
        if c == '/' and nxt == '/':
            state = 'comment-line'
            out.append(c)
            i += 1
            continue
        if c == '/' and nxt == '*':
            state = 'comment-block'
            out.append(c)
            i += 1
            continue
        if c in ('"', "'"):
            state = 'string'
            string_char = c
            out.append(c)
            i += 1
            continue
        if c == '`':
            state = 'template'
            out.append(c)
            i += 1
            continue

        if c == '(':
            depth['paren'] += 1
        elif c == ')':
            depth['paren'] -= 1
        elif c == '{':
            depth['brace'] += 1
        elif c == '}':
            depth['brace'] -= 1
        elif c == '[':
            depth['bracket'] += 1
        elif c == ']':
            depth['bracket'] -= 1

        # After a ; or } at depth 0, look ahead for a keyword
        if at_depth_zero() and c in (';', '}'):
            k = peek_keyword(i+1)
            if k:
                end, kw = k
                # Insert newline AFTER current char
                out.append(c)
                # If the keyword is `async`, it's a function modifier; insert newline + space + async
                if kw == 'async':
                    out.append('\n')
                else:
                    out.append('\n')
                i += 1
                continue

        # BEFORE a keyword at depth 0, insert newline
        if at_depth_zero() and i > 0 and script_body[i-1] not in (' ', '\n', '\t', '\r'):
            k = peek_keyword(i)
            if k:
                end, kw = k
                # Check this is at a real boundary (not part of a longer identifier)
                # We already verified via peek_keyword that it's a word boundary
                # But we need to be careful: the keyword shouldn't be inside an expression
                # At depth 0, the only place keywords appear is at statement start
                # unless we're in a function call arg list (but that's not at depth 0)
                # So safe to insert
                out.append('\n')
                out.append(c)
                i += 1
                continue

        out.append(c)
        i += 1

    return ''.join(out)


def fix_file(path):
    raw = open(path, 'rb').read()
    text = raw.decode('utf-8', errors='replace')

    if '\n' in text and text.count(chr(10)) > 100:
        print(f'  SKIP: {path} already has many newlines')
        return False

    # Find script block boundaries
    script_start_m = re.search(r'<script setup[^>]*>', text)
    script_end_m = re.search(r'</script>', text)
    if not script_start_m or not script_end_m:
        print(f'  FAIL: {path} no script block found')
        return False

    before = text[:script_start_m.end()]
    script_body = text[script_start_m.end():script_end_m.start()]
    after = text[script_end_m.start():]

    new_script = split_statements(script_body)
    new_text = before + new_script + after

    if new_text == text:
        print(f'  NO CHANGE: {path}')
        return False

    with open(path, 'wb') as f:
        f.write(new_text.encode('utf-8'))
    print(f'  FIXED: {path} -> {len(new_text)} chars, {new_text.count(chr(10))} newlines')
    return True


print('Fixing 5 corrupted 1-line SFCs (aggressive)...')
for fname in CORRUPTED_FILES:
    path = f'src/views/{fname}'
    print(f'\n{fname}:')
    fix_file(path)

print('\nDone.')
