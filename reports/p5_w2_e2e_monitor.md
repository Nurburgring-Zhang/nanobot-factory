# P5-W2 Report — e2e + Monitoring + Backup

| 项 | 数值 |
|---|---|
| 路径 1 (e2e) | 4 → 5 路径 (auth/dashboard/canvas/assets/**projects**) |
| 路径 2 (Grafana) | 3 → 4 dashboards (overview/microservices/database/**ai-business**) |
| 路径 3 (Alertmanager) | 5 → **21 alerts** + 8 receivers + 5 inhibits |
| 路径 4 (Backup) | 单脚本 → **PG+Redis+OSS + 3-tier + restore.sh** |
| 总 panels | 9 + 10 + 13 + 14 = **46** |
| 总 e2e tests | 4 + 2 + 4 + 4 + 9 = **23** Playwright 用例 |
| 综合校验 | **20/20 PASS** |

## 核心改动

- `tests/e2e/test_05_projects.py` — 新增 9 个 project CRUD 端到端测试 (含负向)
- `monitoring/grafana-dashboards/ai_business.json` — 4th dashboard, 12 viz panels + 3 templating + 2 annotations
- `monitoring/prometheus-rules.yaml` — 21 alerts (4 组: service 7 / resource 6 / business 5 / security 3)
- `deploy/bare_metal/backup_cron.sh` — PG + Redis + OSS 统一备份, 3-tier 自动迁移
- `deploy/bare_metal/backup_cron.{service,timer}` — systemd 调度 (替代 cron)
- `deploy/bare_metal/restore.sh` — 统一 restore 入口 (--list / --verify / --latest)
- `deploy/bare_metal/configs/alertmanager.yml` — 8 receivers / 7 routes / 5 inhibits
- `deploy/bare_metal/README.md` Section 7 — 重写为 5 个子节 (schedule / install / tiers / restore / DR)

## 验证摘要

| 检查 | 命令 | 结果 |
|---|---|---|
| bash 语法 | `bash -n` × 2 | exit 0 |
| Python 编译 | `py_compile` × 2 | exit 0 |
| pytest collect | `pytest tests/e2e/ --collect-only` | 43 items |
| JSON 解析 | `json.loads` × 8 | 全通过 |
| YAML 解析 | `yaml.safe_load` × 2 | 21 alerts / 8 receivers |
| 综合 | `validate_p5_w2.py` | 20/20 PASS |

## 风险 / 后续

- 沙箱无 `promtool` / `amtool`, 用 Python 替代校验; 生产环境用 `promtool check rules` 最终确认
- `backup_cron.sh` 依赖 Linux (`/var/backups`, `systemctl`); 沙箱仅做语法检查, 真实部署按 README 7.2
- 4 个 `dashboard-vdp-*.json` 是源 JSON 精确副本, 配合 `grafana-dashboards.yml` auto-provisioning

详见 `outputs/p5_w2_e2e_monitor/deliverable.md`。
