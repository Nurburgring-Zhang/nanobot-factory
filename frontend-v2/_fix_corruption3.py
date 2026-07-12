"""Aggressive regex-based newline insertion for 5 corrupted 1-line SFCs."""
import re

CORRUPTED_FILES = [
    'WorkflowBuilder.vue',
    'CapabilityRegistry.vue',
    'CollectionCenter.vue',
    'Delivery.vue',
    'PackManager.vue',
]

# All these keywords can start a new top-level statement
KEYWORDS = (
    'import', 'export', 'const', 'let', 'var', 'function', 'class',
    'interface', 'type', 'enum', 'async',
    'onMounted', 'onBeforeMount', 'onBeforeUnmount', 'onUnmounted',
    'onUpdated', 'onBeforeUpdate', 'onActivated', 'onDeactivated',
    'onErrorCaptured', 'computed', 'watch', 'watchEffect', 'watchPostEffect',
    'watchSyncEffect', 'provide', 'inject', 'reactive', 'toRef', 'toRefs',
    'defineComponent', 'defineProps', 'defineEmits', 'withDefaults',
    'useRoute', 'useRouter', 'useStore', 'useI18n', 'useMessage',
    'useDialog', 'useNotification', 'useLoadingBar', 'storeToRefs',
    'getCurrentInstance', 'nextTick', 'ref',
)


def split_statements(script_body):
    """Insert newlines at statement boundaries using regex patterns."""
    s = script_body

    # 1. After `from 'X'` or `from "X"` (with possible whitespace) - if followed by a keyword
    s = re.sub(
        r"(from\s+['\"][^'\"]*['\"])(?=\s*(?:const|let|var|function|class|interface|type|enum|import|export|onMounted|computed|watch|ref|reactive|useI18n|async))",
        r"\1\n",
        s,
    )

    # 2. After `} = useI18n()` (destructured useI18n) followed by a keyword
    s = re.sub(
        r"(\}\s*=\s*useI18n\(\))(?=\s*(?:const|let|var|function|class|interface|type|enum|import|export|onMounted|computed|watch|ref|reactive|async))",
        r"\1\n",
        s,
    )

    # 3. After `= useI18n();` (when preceded by destructured const) followed by import
    s = re.sub(
        r"(=\s*useI18n\(\);)(?=\s*import)",
        r"\1\n",
        s,
    )

    # 4. After a single character that's ; or } or ) at depth 0 followed by a keyword
    # This is hard to do purely with regex, but we can do it iteratively
    # Pattern: `(char)const` or `(char)function` etc.
    kw_pattern = '|'.join(KEYWORDS)
    # Match: } const, }function, } const, ;const, ;function, etc.
    s = re.sub(
        r"([;}\)])(?=\s*(?:" + kw_pattern + r")\b)",
        r"\1\n",
        s,
    )

    # 5. Now the reverse: keyword followed by ; at depth 0 then another keyword
    # Pattern: `const X = Y; const Z = W;` - need newline before const Z
    # This is already handled by rule 4 (we insert \n after each ;)

    # 6. After `})` end of function call - already handled
    # 7. After `})` end of object - already handled

    # 8. Before async at depth 0: ensure newline
    # Pattern: `}async` -> `}\nasync`
    s = re.sub(
        r"([;}\)])\s*(?=async\s+(?:function|\())",
        r"\1\n",
        s,
    )

    # 9. Handle `}; async` pattern - the `;` after `}` is wrong
    # Pattern: `};` followed by async -> `}\n`
    s = re.sub(
        r"\}\s*;\s*(?=async)",
        r"}\n",
        s,
    )

    return s


def fix_file(path):
    raw = open(path, 'rb').read()
    text = raw.decode('utf-8', errors='replace')

    if text.count(chr(10)) > 100:
        print(f'  SKIP: {path} already has many newlines')
        return False

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


print('Fixing 5 corrupted 1-line SFCs (regex aggressive)...')
for fname in CORRUPTED_FILES:
    path = f'src/views/{fname}'
    print(f'\n{fname}:')
    fix_file(path)

print('\nDone.')
