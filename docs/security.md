# Security — Nanobot Factory

> 适用版本 **appVersion 1.0.0**。本文档列出 **安全模型、威胁面、缓解措施、合规清单**。
>
> 阅读对象：架构师、SRE、安全工程师、合规审计。

## 1. 安全目标

| 目标 | 描述 | 优先级 |
|------|------|--------|
| **机密性** | 用户数据、API Key、模型权重不外泄 | P0 |
| **完整性** | 标注数据、训练样本不被篡改 | P0 |
| **可用性** | 99.5% 在线 (SLO) | P0 |
| **可审计** | 所有写操作可追溯到 actor + IP | P0 |
| **最小权限** | 每个角色只能做其工作必需的事 | P1 |

## 2. 信任边界

```
┌─────────────────────────────────────────────────────────────────────┐
│  Untrusted (Internet)                                                │
│  ─────────────────────                                               │
│  Browser ←─HTTPS─→ nginx (TLS terminator)                            │
│  Mobile / SDK  ←─HTTPS─→  ↑                                          │
│  Webhook client ←─HTTPS─→ ↑                                          │
│                                                                       │
│  Trusted (cluster internal)                                          │
│  ─────────────────────────                                           │
│  FastAPI (uvicorn) ──→ SQLite / Redis                                │
│                  ──→ ComfyUI (HTTP, mTLS optional)                   │
│                  ──→ LLM providers (HTTPS, signed)                   │
│                  ──→ File storage (PVC)                              │
└─────────────────────────────────────────────────────────────────────┘
```

**外部不可信区域** 到 **内部可信区域** 之间的唯一入口是 nginx + FastAPI。
所有依赖调用必须显式声明在 `backend/imdf/api/clients/`。

## 3. 认证 (Authentication)

### 3.1 API Key

- 用途：服务间调用、SDK、CI 脚本
- 格式：`sk-<32 位 base62>`
- 存储：bcrypt hash (cost 12) — 数据库里不可逆
- 传递：`X-API-Key: sk-...` header
- 生命周期：默认不过期；可由 admin 撤销 / 设过期

```python
# 生成
import secrets
api_key = "sk-" + secrets.token_urlsafe(24)

# 验证 (伪代码)
key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=12))
match = bcrypt.checkpw(received.encode(), stored_hash)
```

### 3.2 JWT

- 用途：浏览器会话
- 算法：HS256 (默认) 或 RS256 (生产推荐)
- 有效期：默认 24h，可配置
- Refresh token：单独 endpoint `/api/v1/auth/refresh`，7 天有效
- 撤销：黑名单存 Redis，TTL = 剩余有效期

### 3.3 OIDC / SAML

- 通过 OAuth2 代理（oauth2-proxy / Pomerium）
- 不直接暴露给 FastAPI — 代理层注入 `X-Forwarded-User`

## 4. 授权 (Authorization)

### 4.1 RBAC 模型

5 个内置角色（见 `docs/user-guide.md`）：

| 角色 | 默认权限 |
|------|----------|
| admin | 全权限 + 用户管理 |
| manager | 团队管理 + 审批 + 导出 |
| reviewer | 审批标注 |
| annotator | 上传 + 标注 + 触发渲染（限频） |
| viewer | 只读 |

### 4.2 资源所有权

标注、画布、模板都绑定到 **owner_user_id**。
非 owner 不可写；admin 可绕过；manager 可在团队范围内代管。

### 4.3 强制实现位置

- FastAPI Depends: `Depends(require_role("annotator"))`
- 数据库 row-level filter: `WHERE owner_user_id = :current_user_id`
- 单元测试覆盖：每个 endpoint 一个 403 测试

## 5. 注入防护

### 5.1 SQL

- ❌ 禁止 f-string 拼 SQL
- ✅ **必须**用 SQLAlchemy ORM 或参数化 `text("... WHERE id = :id", {"id": x})`
- Code review checklist: `grep -r "execute(.*+.*\"" backend/`

### 5.2 NoSQL / 文件路径

- 路径遍历：`os.path.realpath` + 白名单 + 拒绝 `..`
- 文件名：UUID 重命名 + 单独保存原名到 DB
- ZIP 解压：限制 entry 数 + 单 entry size + 拒绝绝对路径

### 5.3 Shell

```python
# ❌ BAD
os.system(f"ffmpeg -i {user_input}")

# ✅ GOOD
subprocess.run(
    ["ffmpeg", "-i", validated_path, output],
    shell=False,
    timeout=30,
    check=True,
    capture_output=True,
)
```

### 5.4 LLM Prompt

- 用户输入拼到 Prompt 前做长度截断 (≤ 4k token)
- 不允许 `system` 字段被 API 调用方直接覆盖
- LLM 输出经结构化校验 (Pydantic) 后再执行

## 6. 速率限制 & 防滥用

| 资源 | 默认上限 | 可配置 |
|------|----------|--------|
| 全局 API | 100 req/min/IP | `RATE_LIMIT_REQUESTS` |
| 上传 | 10 req/min/user | hard-coded |
| 渲染 | 5 batch/min/user | `MAX_CONCURRENT_BATCHES` |
| WebSocket 单房间 | 50 连接 | hard-coded |
| LLM 计划请求 | 20 req/hour/user | `LLM_PLAN_RATE_LIMIT` |

实现：slowapi + 自定义装饰器

## 7. 数据保护

### 7.1 静态加密 (Encryption at rest)

- PVC：底层云盘自带加密 (AES-256, AWS EBS / GCP PD / 阿里云)
- SQLite：可选用 SQLCipher (`PRAGMA key`)
- 备份：加密 tar (`gpg --symmetric`)

### 7.2 传输加密 (Encryption in transit)

- TLS 1.2+ 强制（nginx 配置：`ssl_protocols TLSv1.2 TLSv1.3`）
- 强加密套件优先：`ssl_ciphers HIGH:!aNULL:!MD5`
- HSTS：`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- Internal service-to-service：mTLS (Istio / Linkerd / 自签 cert)

### 7.3 字段级加密

- 用户的 PII 字段 (邮箱 / 手机 / 身份证号) — Fernet (AES-128-CBC + HMAC)
- 密钥：`KEY_ENCRYPTION_KEY` 环境变量 (KMS 管理)

```python
from cryptography.fernet import Fernet
cipher = Fernet(os.environ["KEY_ENCRYPTION_KEY"].encode())
encrypted = cipher.encrypt(plaintext.encode())
```

## 8. 审计 (Auditability)

### 8.1 应用层审计

每个写操作产生一条审计事件：

```json
{
  "id": "evt_...",
  "actor_id": "u_42",
  "actor_ip": "1.2.3.4",
  "actor_ua": "Mozilla/5.0 ...",
  "action": "annotation.create",
  "target_type": "annotation",
  "target_id": "ann_88",
  "before": null,
  "after": { /* snapshot */ },
  "ts": "2026-06-21T08:00:00Z",
  "trace_id": "01HX..."
}
```

事件走独立 `audit_events` 表 + 异步同步到 SIEM。

### 8.2 K8s 审计

- 启用 kube-apiserver audit log
- 写到 Loki / ELK
- 至少保留 90 天

### 8.3 nginx 访问日志

- 至少保留 30 天
- 包含：方法 / 路径 / 状态 / 耗时 / 上游耗时 / UA / IP

## 9. 密钥管理

| 密钥 | 来源 | 轮换周期 |
|------|------|----------|
| `JWT_SECRET` | KMS / sealed-secret | 90 天 |
| `KEY_ENCRYPTION_KEY` | KMS (envelope encryption) | 365 天 |
| `DEEPSEEK_API_KEY` | LLM provider | 180 天 |
| `COMFYUI_API_KEY` | ComfyUI 启动时生成 | 永久 |
| `POSTGRES_PASSWORD` | K8s secret (random) | 365 天 |
| API Key (用户) | 系统生成 | 用户撤销 |
| TLS cert | cert-manager + letsencrypt | 60 天 (自动续期) |

**绝对禁止**：
- ❌ 提交 .env 文件
- ❌ 把密钥写进 README / Issue
- ❌ 把密钥 echo 进 stdout (会被日志收)

## 10. 镜像安全

### 10.1 构建

- Multi-stage：runtime 镜像无 build tool
- 基础镜像固定 minor：`python:3.11.9-slim` 而非 `python:3.11`
- `pip install --require-hashes` (生产环境)
- `npm ci --ignore-scripts` (避免 postinstall 跑任意代码)

### 10.2 扫描

CI 跑：
- Trivy：扫 `os,library` 类漏洞，CRITICAL/HIGH 必须 fail
- Snyk (可选)：许可证 + 漏洞
- Grype (备选)

### 10.3 签名

- cosign keyless (`cosign sign --yes ghcr.io/...`)
- 部署前 verify：`cosign verify --certificate-identity ...`

### 10.4 SBOM

- `syft` 生成 CycloneDX SBOM
- 推到 GHCR 的 `sbom-<sha>` tag

## 11. 运行时安全

| 措施 | 实现 |
|------|------|
| 非 root 用户 | Dockerfile `USER 101`；K8s `runAsNonRoot: true` |
| 只读根文件系统 | `readOnlyRootFilesystem: true`；tmp / cache 走 emptyDir |
| 最小能力 | `capabilities.drop: ["ALL"]` |
| seccomp | `RuntimeDefault` |
| NetworkPolicy | 默认 deny + 白名单 (Helm chart 后续 PR 添加) |
| AppArmor (可选) | `container.apparmor.security.beta.kubernetes.io/...` |
| Image pull policy | `IfNotPresent`；私有 registry 用 imagePullSecrets |
| Pod 安全标准 | PSA `restricted` (Chart 默认) |

## 12. 依赖供应链

- Dependabot：每周 PR (`.github/dependabot.yml`)
- `npm audit` / `pip-audit`：每周 cron 跑
- 所有锁文件 (package-lock.json / requirements.txt) **必须**随版本提交
- 内部 SDK / 共用库走内部 registry (npm + pypi private)

## 13. 隐私 / 合规

### 13.1 GDPR / CCPA

- 用户可导出 / 删除所有个人数据（`/api/v1/users/me/export`）
- 删除请求 30 天后清除 DB + 备份 + 日志中的 PII
- 同意管理：`/api/v1/consent`

### 13.2 数据驻留

- 通过 K8s nodeSelector + taints 强制 region
- 备份加密 + 跨 region 复制

### 13.3 数据脱敏

- 自动人脸模糊 (`/api/v1/privacy/redact?field=face`)
- 自动车牌模糊
- 邮箱 / 手机号正则替换 (`john@x.com` → `j***@x.com`)

## 14. 事件响应

| 事件 | 检测 | 响应 | 责任人 |
|------|------|------|--------|
| **数据泄露** | 异常出站流量 / SIEM 告警 | 立即断网 + 通知用户 + 报告监管 | Security Officer |
| **RCE 漏洞** | Trivy / CVE 公告 | 24h 内 patch + 回滚策略 | Backend Lead |
| **DDoS** | Cloudflare / nginx 异常 5xx | 启用 rate-limit + 调 CDN | SRE |
| **凭证泄露** | GitHub secret scanning | 立刻 rotate + 撤销 token | Security Officer |
| **内部滥用** | 审计日志异常 | 冻结账号 + 取证 | Compliance |

## 15. 安全 checklist (部署前)

- [ ] `JWT_SECRET` 已替换为 ≥ 32 随机字符
- [ ] `KEY_ENCRYPTION_KEY` 从 KMS 注入
- [ ] `ALLOWED_ORIGINS` 精确列表（**非** `*`）
- [ ] `DEV_MODE=false`
- [ ] `CORS_ALLOW_ALL=false`
- [ ] TLS 证书已配置并验证 (`curl -I https://...`)
- [ ] NetworkPolicy 应用（限制 Pod-to-Pod）
- [ ] PodSecurityAdmission = `restricted`
- [ ] 镜像已签名 + SBOM 上传
- [ ] Trivy 扫描 0 critical
- [ ] 备份恢复演练最近 30 天内做过
- [ ] 审计日志已接入 SIEM
- [ ] 所有 admin 账号强制 2FA (OIDC 层)
- [ ] 异常登录告警已配置

## 16. 安全测试

| 类型 | 频率 | 工具 |
|------|------|------|
| 依赖漏洞扫描 | 每周 + CI | Trivy, Snyk, npm audit, pip-audit |
| SAST | 每次 PR | Bandit (Python), Semgrep |
| DAST | 每月 | OWASP ZAP |
| 渗透测试 | 每年 | 第三方 |
| 红蓝对抗 | 每年 | 第三方 |
| Secret 扫描 | 每次 push | gitleaks |

## 17. 报告安全问题

- **邮箱**: security@example.com (PGP key 见 https://example.com/.well-known/pgp-key.txt)
- **GPG fingerprint**: `8B4E 0F4A 1C3D ...`
- **响应时间**: 24h 确认 / 72h 初步评估 / 30 天修复

---

_最后更新：2026-06-21 — 适用版本 appVersion 1.0.0_