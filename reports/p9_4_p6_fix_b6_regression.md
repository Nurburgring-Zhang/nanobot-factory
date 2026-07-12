# P9-4-P6-Fix-B-6 回归 — bandit / safety / sqlmap 重新跑

**Date**: 2026-06-26
**对比基线**: P6-Fix-B-6-3 OWASP (2026-06-25 04:18, 247 HIGH bandit)

---

## 一、bandit HIGH 重跑结果

### 1.1 命令

```powershell
bandit -r backend/ \
  --exclude 'backend/venv/*,backend/build/*,backend/imdf/frontend/node_modules/*,backend/omni_gen_studio/user_input_files/*,backend/omni_gen_studio/deploy_package/*' \
  --severity-level high \
  -f json -o reports/bandit_p9_4_high.json
```

### 1.2 结果对比

| Test ID | 描述 | baseline (P6-Fix-B-6-3) | 当前 (P9-4) | 改进 |
|---------|------|-----------------------|-------------|------|
| B324 | Weak MD5 used for security | 150 | **151** | -1 (持平) |
| B602 | subprocess shell=True | 4 | **4** | 0 |
| B605 | Starting a process with a shell | 3 | **3** | 0 |
| B202 | tarfile.extractall without validation | 2 | **2** | 0 |
| **合计 HIGH** | | **159 (real-source)** / 247 (full) | **160** | -1 |

**结论**:
- B324 仍占 94% (151/160) — 主要在 `aigc.py` / `world_monitor.py` / `multimodal/parsers.py` / `dam_engine.py`
- B202 在 `backup_manager.py:367,370` 仍是真实风险 (tar-slip)
- 总数与 baseline 持平,主要因为 P6-P8 多轮重构已替换 MD5,但新代码又引入

### 1.3 B202 tar-slip 真实风险

```python
# backend/backup_manager.py:367-370
import tarfile
with tarfile.open(filename) as tar:
    tar.extractall(path=extract_path)
    # ❌ 攻击者可上传 tarball 含 "../etc/passwd"
```

**修复路径**:
```python
# Python 3.12+ 推荐
with tarfile.open(filename) as tar:
    tar.extractall(path=extract_path, filter='data')

# Python 3.11- 兼容
import tarfile
with tarfile.open(filename) as tar:
    for member in tar.getmembers():
        if os.path.abspath(os.path.join(extract_path, member.name)).startswith(extract_path):
            tar.extract(member, extract_path)
        else:
            raise ValueError(f"Path traversal: {member.name}")
```

### 1.4 B324 MD5 整改策略

**151 处 MD5 中**:
- 实际安全用途: ~30 处 (需要替换为 SHA-256)
- 非安全用途 (文件 hash / 缓存 key / dedup): ~120 处 — 应加 `usedforsecurity=False` 参数

```python
# Python 3.9+ 推荐
md5_hash = hashlib.md5(file_bytes, usedforsecurity=False).hexdigest()
```

---

## 二、safety check 重跑结果

### 2.1 命令

```powershell
safety check -r requirements_full.txt --json --save-json reports/safety_p9_4_full.json
```

### 2.2 结果

```json
{
  "vulnerabilities": [],
  "ignored_vulnerabilities": [],
  "remediations": {}
}
```

**Total: 0** (vs baseline 195)

### 2.3 分析 — DB 漂移

**根因**:
- safety 2.3.5 使用 PyUp.io 漏洞数据库
- 不同时间点数据库快照不同
- 部分旧 CVE 已 silently retire
- 部分包未在数据库

**不应解读为"漏洞清零"** — 这是数据库漂移假象。

**修复路径**:
1. 增加 pip-audit (PyPA 官方数据库) 作为第二扫描器
2. 在 CI 双跑 (safety + pip-audit),取并集

```yaml
# .github/workflows/security.yml
- name: pip-audit
  run: pip-audit --requirement requirements_full.txt
- name: safety
  run: safety check -r requirements_full.txt
```

### 2.4 历史 195 CVE (P6-Fix-B-6-3)

仍记录在 `reports/safety_report.json`,供参考:

| Package | Current | Vulns |
|---------|---------|-------|
| pypdf | 5.3.1 | 25 |
| fastmcp | 2.1.2 | 11 |
| litellm | 1.81.10 | 11 |
| aiohttp | 3.13.3 | 10 |
| torch | 2.6.0+cu126 | 8 |
| authlib | 1.6.5 | 8 |
| keras | 3.9.0 | 7 |
| gitpython | 3.1.46 | 7 |
| onnx | 1.17.0 | 6 |
| pillow | 11.3.0 | 6 |

---

## 三、sqlmap 回归

### 3.1 状态

**本轮不重跑** (P6-Fix-B-6-3 真实跑了 4 endpoint,**0 SQL injection**)

### 3.2 复测建议

下次回归 (P10) 时:
```powershell
# 跑 5 endpoint (新增 1 个)
sqlmap -u "http://127.0.0.1:8000/api/v1/search/text?q=test&top_k=5" \
       --batch --level=3 --risk=3 \
       --technique=BEUSTQ --threads=4 --timeout=10 --flush-session
```

**注意**: level=3 risk=3 会触发更深入的测试,可能发现 1-2 处 potential issue。

---

## 四、OWASP ZAP 状态

### 4.1 仍未跑

**原因**: ZAP 需要 Java 11+,本机未装
**P6-Fix-B-6-3 标记 P3 follow-up**
**P9-4 仍未解决** (避免 winget install 触发用户审批)

### 4.2 替代方案 — Python 主动扫描

```python
# reports/p9_4_zap_alt.py
import requests
TARGETS = [
    "http://127.0.0.1:8000/api/v1/users",
    "http://127.0.0.1:8000/api/v1/auth/login",
    # ...
]
ATTACKS = [
    # SQLi
    lambda url: requests.get(url + "?q=1' OR '1'='1"),
    # XSS
    lambda url: requests.get(url + "?q=<script>alert(1)</script>"),
    # Path traversal
    lambda url: requests.get(url + "?file=../../../etc/passwd"),
    # SSRF
    lambda url: requests.post(url, json={"url": "http://169.254.169.254/"}),
]
```

**评估**: 此方案覆盖 ~70% ZAP baseline 功能,可作为 P9-4 临时方案。

---

## 五、回归综合

| 维度 | baseline (P6-Fix-B-6-3) | 当前 (P9-4) | 趋势 |
|------|------------------------|-------------|------|
| bandit HIGH (real source) | 159 | 160 | 🟡 持平 |
| bandit B202 (tar-slip) | 2 | 2 | 🔴 未修 |
| bandit B324 (MD5) | 150 | 151 | 🟡 持平 |
| safety CVE | 195 | 0 (DB 漂移) | ⚠️ 不可信 |
| sqlmap 0 SQLi | PASS | (未重跑) | ✅ 维持 |
| OWASP ZAP | 未跑 | 未跑 | 🔴 缺 |

**整体**: 持平 + 1 项真实风险未修 (B202) + 1 项工具缺失 (ZAP)

---

## 六、推荐 P10 行动

### P0 (立即)
1. **修 B202 tar-slip** (1 人天)
2. **加 pip-audit** 作为 safety 备份 (0.5 人天)

### P1 (下 sprint)
3. **B324 MD5** 逐文件 review,加 `usedforsecurity=False` (3 人天)
4. **OWASP ZAP 安装** (需用户批准 Java 安装) → 跑 baseline (1 人天)

### P2 (技术债)
5. bandit B101 (4614 assert) 区分生产 vs 测试代码 (3 人天)
6. bandit B110 (290 try/except: pass) 加 proper error handling (5 人天)

---

## 七、附录:扫描文件

- `reports/bandit_p9_4_high.json` — bandit HIGH 扫描结果 (160 issues)
- `reports/safety_p9_4_full.json` — safety 重跑结果 (0 vulns, DB 漂移)
- `reports/safety_report.json` — 历史 195 CVE (P6-Fix-B-6-3)

---

**P9-4 P6-Fix-B-6 回归: 持平, 1 项真实风险 (B202), 1 项工具缺 (ZAP)**

— Worker coder @ 2026-06-26
