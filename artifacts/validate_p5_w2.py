"""Validate backup_cron.sh / restore.sh / backup_cron.service / backup_cron.timer structure."""
import re
import sys
from pathlib import Path

ROOT = Path(r'D:\Hermes\生产平台\nanobot-factory')

def check_file(label: str, path: Path, must_contain: list[str], forbidden: list[str] = None) -> bool:
    if not path.exists():
        print(f'FAIL {label}: {path} not found')
        return False
    text = path.read_text(encoding='utf-8')
    missing = [m for m in must_contain if m not in text]
    if missing:
        print(f'FAIL {label}: missing strings: {missing}')
        return False
    if forbidden:
        for f in forbidden:
            if f in text:
                print(f'FAIL {label}: forbidden string present: {f}')
                return False
    print(f'PASS {label}: {path.name} ({len(text)} bytes)')
    return True

results = []

# backup_cron.sh
results.append(check_file(
    'backup_cron.sh',
    ROOT / 'deploy/bare_metal/backup_cron.sh',
    [
        'set -euo pipefail',
        'backup_pg()',
        'backup_redis()',
        'backup_oss()',
        'migrate_tiers()',
        'verify_sample()',
        'HOT_TIER_DAYS',
        'WARM_TIER_DAYS',
        'COLD_TIER_DAYS',
        'pg_dump',
        'redis-cli',
        'mc mirror',
        '/var/backups/imdf',
        'LOG_DIR',
        'acquire_lock',
    ],
))

# restore.sh
results.append(check_file(
    'restore.sh',
    ROOT / 'deploy/bare_metal/restore.sh',
    [
        'set -euo pipefail',
        '--component',
        '--list',
        '--verify',
        '--latest',
        'restore_pg',
        'restore_redis',
        'restore_oss',
        'psql',
        'redis-cli',
        'mc mirror',
        'verify_backup',
        'list_backups',
    ],
))

# backup_cron.service
results.append(check_file(
    'backup_cron.service',
    ROOT / 'deploy/bare_metal/backup_cron.service',
    [
        '[Unit]',
        '[Service]',
        '[Install]',
        'Type=oneshot',
        'EnvironmentFile=/etc/imdf/imdf.env',
        'ExecStart=/opt/nanobot-factory/deploy/bare_metal/backup_cron.sh',
        'User=imdf',
    ],
))

# backup_cron.timer
results.append(check_file(
    'backup_cron.timer',
    ROOT / 'deploy/bare_metal/backup_cron.timer',
    [
        '[Unit]',
        '[Timer]',
        '[Install]',
        'OnCalendar',
        'Persistent=true',
        'Unit=imdf-backup.service',
        'WantedBy=timers.target',
    ],
))

# README update
readme = ROOT / 'deploy/bare_metal/README.md'
if readme.exists():
    text = readme.read_text(encoding='utf-8')
    must = [
        'backup_cron.sh',
        'backup_cron.service',
        'backup_cron.timer',
        'restore.sh',
        'systemd timer',
        '7.1 Backup schedule',
        '7.2 Install',
        '7.3 Retention tiers',
        '7.4 Restore',
        '7.5 Disaster recovery',
    ]
    missing = [m for m in must if m not in text]
    if missing:
        print(f'FAIL README: missing: {missing}')
        results.append(False)
    else:
        print(f'PASS README: all backup sections present')
        results.append(True)
else:
    results.append(False)

# Prometheus rules
rules = ROOT / 'monitoring/prometheus-rules.yaml'
if rules.exists():
    text = rules.read_text(encoding='utf-8')
    must = [
        'groups:',
        'severity: critical',
        'severity: warning',
        'severity: info',
        'category: service',
        'category: resource',
        'category: business',
        'category: security',
    ]
    missing = [m for m in must if m not in text]
    if missing:
        print(f'FAIL prometheus-rules.yaml: missing: {missing}')
        results.append(False)
    else:
        # count alerts
        n = text.count('\n      - alert:')
        print(f'PASS prometheus-rules.yaml: {n} alerts')
        if n < 20:
            print(f'  WARNING: < 20 alerts')
            results.append(False)
        else:
            results.append(True)
else:
    results.append(False)

# Alertmanager
am = ROOT / 'deploy/bare_metal/configs/alertmanager.yml'
if am.exists():
    text = am.read_text(encoding='utf-8')
    must = [
        'routes:',
        'receivers:',
        'inhibit_rules:',
        'slack-critical',
        'slack-warn',
        'slack-info',
        'pagerduty',
        'slack-security',
        'slack-business',
        'pagerduty-security',
    ]
    missing = [m for m in must if m not in text]
    if missing:
        print(f'FAIL alertmanager.yml: missing: {missing}')
        results.append(False)
    else:
        print(f'PASS alertmanager.yml: 5 receivers + 5 inhibit rules')
        results.append(True)
else:
    results.append(False)

# Grafana dashboards
for name in ['overview.json', 'microservices.json', 'database.json', 'ai_business.json',
             'dashboard-vdp-overview.json', 'dashboard-vdp-business.json',
             'dashboard-vdp-infrastructure.json', 'dashboard-vdp-ai.json']:
    p = ROOT / 'monitoring' / 'grafana-dashboards' / name
    if not p.exists():
        print(f'FAIL dashboard {name}: not found')
        results.append(False)
    else:
        text = p.read_text(encoding='utf-8')
        if '"panels":' not in text or '"title":' not in text:
            print(f'FAIL dashboard {name}: missing panels/title')
            results.append(False)
        else:
            n = text.count('"id":')
            print(f'PASS dashboard {name}: {n} panel ids')
            results.append(True)

# e2e test files
for name in ['test_01_auth.py', 'test_02_dashboard.py', 'test_03_canvas.py',
             'test_04_assets.py', 'test_05_projects.py']:
    p = ROOT / 'tests' / 'e2e' / name
    if not p.exists():
        print(f'FAIL e2e test {name}: not found')
        results.append(False)
    else:
        text = p.read_text(encoding='utf-8')
        n = text.count('def test_')
        print(f'PASS e2e test {name}: {n} test methods')
        results.append(True)

ok = sum(1 for r in results if r)
total = len(results)
print(f'\n=== {ok}/{total} checks passed ===')
sys.exit(0 if ok == total else 1)
