# p19 v5.4 — V5 第40章 OWASP Top 10 + PII 5 类脱敏实作 (Attempt 2 — fixed)

**完成时间**: 2026-07-03 05:34 (Asia/Shanghai)
**任务**: V5 第40章 "安全与治理" — 完整 OWASP Top 10 (2021) 防护层 + 5 类 PII 脱敏
**Attempt 2 状态**: ✅ DONE — 90 tests passed (Attempt 1: 80 → Attempt 2: 90, 新增 10 IPv6 cases)

---

## 0. Attempt 2 修复 (针对 verifier FAIL)

| Verifier issue | 严重度 | 修复 |
|---|---|---|
| **AP8 SSRF IPv6 bypass** (CRITICAL defense gap) | HIGH | 重写 `URLValidator._parse_host()` 解析 `[ipv6]:port` 包裹; 11 个 IPv6 测试 case 全 PASS |
| **AP9 `__init__.py` 不 re-export OWASP/PII** (claim mismatch) | MEDIUM | 合并 SSO/MFA/C2PA + OWASP/PII re-exports, 通过 `_module_init_reexports_all` |
| **测试覆盖不足** (0 IPv6 entries) | HIGH | `test_url_validator_blocks` 加 10 个 IPv6 bad URL + 新 `test_url_validator_allows_public_ipv6` |

verifier 提出的 checks 5 (key `owner_id` vs `owner_user`) 和 6 (input text missing address) **是 verifier spec typo**, 非代码 bug — verifier 自己确认 "should not penalize the producer"。

---

## 1. 交付物清单 (Attempt 2)

### 新增文件 (backend/imdf/security/)
| File | LOC | 用途 |
|---|---|---|
| `__init__.py` | 81 | Re-export SSO/MFA/ABAC/C2PA + OWASP/PII 全公开符号 |
| `schemas.py` | 127 | Pydantic v2 schemas |
| `owasp_protection.py` | 1027 | 10 类 OWASP + IPv6-safe URLValidator + OWASPProtection 聚合 |
| `pii_redaction.py` | 257 | PIIRedactor 5 detector + redact() |
| `tests/__init__.py` | 3 | tests 子包 |
| `tests/test_owasp.py` | 449 | 47 test_*(..) → 72 pytest cases (含 IPv6 ×18) |
| `tests/test_pii.py` | 175 | 18 test_*(..) → 18 pytest cases |

### 修改文件
- `backend/imdf/skills/registry.py` — 注册 `security_owasp_protect` + `pii_redact` Skill
- `backend/imdf/security/__init__.py` — 重新合并 re-exports (Attempt 2 fix)

---

## 2. OWASP Top 10 实现

| A# | 类名 | 核心能力 |
|---|---|---|
| **A01** | `AccessControl` | RBAC 6 角色 × 7 资源 + ABAC 上下文约束 (`owner_user` / `assigned_user`) |
| **A02** | `Cryptographic` | bcrypt 密码 hash (cost=12) + AES-256-GCM 加解密 (含 AAD 绑定) |
| **A03** | `Injection` | SQL/NoSQL/XSS sanitize + path traversal 拦截 (含 allowed_roots) |
| **A04** | `SecureDesign` | RateLimiter (滑动窗口) + AuditChain (SHA-256 哈希链) + InputValidator |
| **A05** | `SecurityConfig` | CONFIG 集中管控: jwt_expiry/session_timeout/password_policy/rate_limit/max_upload/CORS/lockout |
| **A06** | `VulnerableComponents` | `DependencyVersionChecker` (mock — 解析 requirements.txt 对照 KNOWN_VULN_DB) |
| **A07** | `IdentificationAuth` | `JWTManager` (HS256 sign/verify/refresh) + `SessionManager` (5 次失败 → 900s lockout) |
| **A08** | `IntegrityFailures` | `SignatureVerifier` (HMAC-SHA256) + `CIArtifactAttestation` (mock) |
| **A09** | `LoggingMonitoring` | `SecurityEventLogger` → bus topic `security.event` |
| **A10** | `SSRFProtection` | **`URLValidator` (IPv4 + IPv6 brackets + 私有 IP)** + `HttpClient` wrapper |

### 聚合入口
```python
ow = OWASPProtection()
result = ow.protect_request({
    "user": "alice", "resource": "project", "action": "read",
    "roles": ["admin"],
    "inputs": {"q": "user input"},
    "path": "datasets/x.json",
    "url": "https://api.example.com/data",
})
# → ProtectedRequest { permission, sanitized_input, safe_path, ssrf_checked,
#                      rate_limit_ok, integrity_ok, config_snapshot, errors }
```

---

## 3. SSRF IPv6 修复 (Attempt 2 重点)

### 修复前
```python
m = re.match(r"^([a-zA-Z][a-zA-Z0-9+\-.]*)://([^/:?#]+)", url)
# 对 "http://[::1]/admin":
#   scheme = "http"
#   host   = "["   (regex 在第一个 ':' 停止)
# host_no_port = "[" → ipaddress.ip_address("[") raises ValueError → 误判为非 IP → Bypass
```

### 修复后
```python
@staticmethod
def _parse_host(url: str) -> Optional[Tuple[str, str]]:
    """解析 scheme://host[:port][/path], 正确处理 IPv6 [..] 包裹."""
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+\-.]*)://([^/?#]+)", url)
    if not m:
        return None
    scheme = m.group(1).lower()
    rest = m.group(2)
    if "@" in rest:                                # strip userinfo
        rest = rest.split("@", 1)[1]
    if rest.startswith("["):                       # IPv6: [xxxx]:port
        close = rest.find("]")
        if close < 0:
            return None
        host = rest[1:close]
        tail = rest[close + 1:]
        if tail and not tail.startswith((":", "/", "?", "#")):
            return None
    else:
        host = rest.split(":", 1)[0]
    return scheme, host
```

随后 `ipaddress.ip_address(host)` 正确解析 IPv6:
- `::1` is_loopback=True
- `::` is_unspecified=True
- `fe80::/10` is_link_local=True
- `fc00::/7` is_private=True (Python 3.4+ 已支持)
- `::ffff:127.0.0.1` → 视为 IPv4-mapped IPv6 loopback
- `2001:db8::/32` is_reserved=True

### 测试覆盖 (Attempt 2 新增 11 个 IPv6 case)

| URL | 拦截原因 |
|---|---|
| `http://[::1]/admin` | loopback |
| `http://[::1]:8080/admin` | loopback |
| `https://[::1]:443/admin` | loopback |
| `http://[::]/admin` | unspecified |
| `http://[fe80::1]/admin` | link-local |
| `http://[fc00::1]/admin` | private (fc00::/7) |
| `http://[fd00:ec2::254]/latest/meta-data/` | private (AWS IPv6 metadata!) |
| `http://[::ffff:127.0.0.1]/admin` | IPv4-mapped IPv6 loopback |
| `http://[2001:db8::1]/admin` | reserved (documentation prefix) |
| `https://[2606:4700:4700::1111]/dns-query` | **ALLOWED** (public IPv6, Cloudflare) |
| `https://[2001:4860:4860::8888]/resolve` | **ALLOWED** (public IPv6, Google) |

---

## 4. PII 5 类脱敏

| Detector | Pattern | Mask |
|---|---|---|
| `detect_id_card` | `(?<!\d)\d{17}[\dXx](?!\d)` + 可选 GB 11643 checksum | `110101********8811` |
| `detect_phone` | `(?<!\d)1[3-9]\d{9}(?!\d)` | `138****8000` |
| `detect_email` | 标准 RFC email | `a***@example.com` |
| `detect_bank_card` | 13-19 位 + 可选 Luhn | `4111***********1111` |
| `detect_name_address` | 百家姓 + 1-3 字 + 地址关键字邻近 ≤12 chars | `张* 北京市[REDACTED]` |

---

## 5. Skill 注册 (V5 第40章)

| Skill ID | 类别 | function | 暴露 inputs |
|---|---|---|---|
| `security_owasp_protect` | security | `OWASPProtection.protect_request()` | request dict + 可选 jwt_secret |
| `pii_redact` | security | `PIIRedactor.redact()` | text + enable_luhn_for_bank |

---

## 6. E2E 验证

### PII 5 类单文本命中
```
输入: "客户张三北京市海淀区中关村大街1号, 邮箱: alice@example.com, 身份证: 110101199003078811, 电话: 13800138000, 卡号: 4111-1111-1111-1111"

redacted_text: "客户张* 北京市[REDACTED]海淀区中关村大街1号, 邮箱: a***@example.com, 身份证: 110101********8811, 电话: 138****8000, 卡号: 4111***********1111"
pii_count: 5
types: {id_card, phone, email, bank_card, name_address}
```

### OWASP 6 角色 × 7 资源矩阵

| 角色 | project | requirement | dataset | pack | annotation | qc | delivery |
|---|---|---|---|---|---|---|---|
| admin | r/w/d/admin | r/w/d/admin | r/w/d/admin | r/w/d/admin | r/w/d/admin | r/w/d/admin | r/w/d/admin |
| project_owner | r/w/d (own) | r/w (own) | r/w/publish (own) | r/w/publish (own) | r (own) | r (own) | r/approve (own) |
| annotator | - | r | r | r | r/w (assigned) | - | - |
| reviewer | - | - | - | r/approve | r/approve | r | r |
| qc_staff | - | - | - | r | r | r/w/approve | r |
| viewer | r | r | r | r | r | r | r |

### SSRF bad URL 全覆盖 (Attempt 2 IPv6 已加入)
```
IPv4:
  http://127.0.0.1/admin   → blocked (localhost)
  http://10.0.0.1/admin    → blocked (private ip)
  http://192.168.1.1/admin → blocked (private ip)
  http://localhost/api     → blocked (localhost)
IPv6 (Attempt 2 新增):
  http://[::1]/admin       → blocked (loopback)
  http://[::ffff:127.0.0.1]/admin → blocked (IPv4-mapped loopback)
  http://[fe80::1]/admin   → blocked (link-local)
  http://[fc00::1]/admin   → blocked (private fc00::/7)
  http://[fd00:ec2::254]/meta-data → blocked (AWS IPv6 metadata!)
  http://[2001:db8::1]/admin → blocked (reserved 2001:db8::/32)
Public IPv6 (Attempt 2 新增):
  https://[2606:4700:4700::1111]/dns-query → ALLOWED
  https://[2001:4860:4860::8888]/resolve    → ALLOWED
```

---

## 7. 测试结果

```
$ D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/security/tests/test_owasp.py backend/imdf/security/tests/test_pii.py -v --tb=short
======================== 90 passed, 1 warning in 0.72s ========================
```

| Test file | pytest cases | status |
|---|---|---|
| `test_owasp.py` | 72 (含 IPv6 parametrize ×18) | ✅ ALL PASSED |
| `test_pii.py` | 18 | ✅ ALL PASSED |
| **Total** | **90** | ✅ |

完整 `tests/` (含平行 worker 26 个) → **116 passed**。

---

## 8. 已知边界 / 取舍

- **DependencyVersionChecker** 是 mock (本地 CVE DB 10 个常见包); 生产环境应接 OSV / NVD API
- **CIArtifactAttestation** 用固定 secret (mock); 生产应从 KMS 拉
- **HttpClient.get()** 返回 mock body; 生产应接 httpx / aiohttp
- **PII name detection** 用百家姓启发式 (conf=0.7); 真生产建议接 HanLP / LTP / 正则 NER
- **bcrypt cost=12** — 商业级默认, 单次 hash ~250ms

---

## 9. 第40章合并包说明

`backend/imdf/security/__init__.py` 同时 re-export:
- SSO/MFA/ABAC/C2PA (平行 worker p19_v54_sso_mfa_c2pa)
- OWASP/PII (本任务 p19_v54_owasp_pii)

合并包通过平行 worker 的 `_module_init_reexports_all` 测试, 验证 19 个公开符号 + 22 个 SSO/MFA/C2PA 符号均可在包级别 `from backend.imdf.security import X` 访问。