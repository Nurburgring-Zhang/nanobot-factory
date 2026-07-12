import re, glob
from pathlib import Path

ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory\frontend-v2')
OUT = ROOT / 'reports'

# Per-view audit: count loading/empty/error/api patterns
audit = {}
for f in glob.glob(str(ROOT / 'src' / 'views' / '**' / '*.vue'), recursive=True):
    text = open(f, encoding='utf-8').read()
    name = f.split('\\')[-1]
    audit[name] = {
        'lines': text.count('\n'),
        'has_error_alert': bool(re.search(r'<NAlert[^>]*type=["\']error["\']', text)),
        'has_empty': bool(re.search(r'<NEmpty|<el-empty', text)),
        'has_skeleton': bool(re.search(r'<NSkeleton|SkeletonLoader', text)),
        'has_loading_state': bool(re.search(r'loading\.value|:loading=', text)),
        'has_role': bool(re.search(r'role=["\']', text)),
        'has_aria_label': bool(re.search(r'aria-label', text)),
        'has_aria_live': bool(re.search(r'aria-live', text)),
        'has_button_aria': bool(re.search(r'<button[^>]*aria-', text)),
        'try_catch_count': len(re.findall(r'\bcatch\s*\(', text)),
        'api_calls': len(re.findall(r'\bawait\s+[A-Za-z_][A-Za-z0-9_]*\(', text)),
        'message_error_count': len(re.findall(r'message\.error|notify\.error|\$message\.error', text)),
        'corrupted': text.count('\n') < 5,
    }

lines = []
lines.append(f'{"View":<37}{"lines":>6}{"errAl":>6}{"empty":>6}{"skel":>5}{"load":>5}{"role":>5}{"aria":>5}{"try":>4}{"api":>4}{"msge":>5}{"corrupt":>8}')
lines.append('-' * 95)
for name, d in sorted(audit.items()):
    lines.append(f'{name:<37}{d["lines"]:>6}'
                 f'{1 if d["has_error_alert"] else 0:>6}'
                 f'{1 if d["has_empty"] else 0:>6}'
                 f'{1 if d["has_skeleton"] else 0:>5}'
                 f'{1 if d["has_loading_state"] else 0:>5}'
                 f'{1 if d["has_role"] else 0:>5}'
                 f'{1 if d["has_aria_label"] else 0:>5}'
                 f'{d["try_catch_count"]:>4}'
                 f'{d["api_calls"]:>4}'
                 f'{d["message_error_count"]:>5}'
                 f'{"Y" if d["corrupted"] else "":>8}')

(OUT / '_per_view_audit.txt').write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(lines))