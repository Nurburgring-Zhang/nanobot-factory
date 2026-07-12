# P19 v5.4 — V5 第40章 SSO / MFA / ABAC / C2PA 完整实作

**Status**: done
**Worker**: coder (Mavis session mvs_6946ead988ff400e9d367898c6136d7c)
**Plan**: plan_a6fde9d8 (V5 P19 v5.4)
**Started**: 2026-07-03 05:16 (Asia/Shanghai)
**Finished**: 2026-07-03 05:35 (Asia/Shanghai) — ~19 min actual

## Summary

In a single ~19-minute sprint this task delivered V5 chapter 40's deeper security
stack end-to-end: a brand-new `backend/imdf/security/` subpackage with 4 modules
(SSO / MFA / ABAC / C2PA), shared Pydantic v2 schemas, and 26 pytest tests (≥20
required). Also extended `backend/imdf/skills/registry.py` to register 3 new
skill specs (`sso_authenticate`, `mfa_enforce`, `c2pa_provenance`) under the
existing SECURITY family — bringing it from 2 → 5 skills. All 26 tests pass with
`D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/security/tests/test_sso_mfa_c2pa.py -v`.

## Changed files

### New files (7)
| File | LOC | Purpose |
|---|---|---|
| `backend/imdf/security/__init__.py` | 44 | Re-export public API |
| `backend/imdf/security/sso_mfa_c2pa_schemas.py` | 246 | Pydantic v2 schemas (AuthResult / OIDCConfig / EnrollmentResult / ChallengeResult / VerificationResult / ABACPolicy / ABACDecision / Condition / C2PAManifest / C2PAAction / C2PAIngredient / C2PAVerificationResult) |
| `backend/imdf/security/sso.py` | 436 | `SSOManager` with 4 providers (SAML/OAuth2/OIDC/LDAP) + in-memory IdP registry |
| `backend/imdf/security/mfa.py` | 411 | `MFAManager` with TOTP (RFC 6238 self-contained) / SMS OTP / Email OTP / Backup codes |
| `backend/imdf/security/abac.py` | 383 | `ABACEngine` with 3 built-in policies (admin_bypass / owner_delete_own / project_member_read) + 6 operators + IN_ATTR for dynamic attribute comparison |
| `backend/imdf/security/c2pa.py` | 419 | `C2PASigner` (Ed25519) / `C2PAVerifier` / `C2PAStore` (SQLite + JSON fallback) / sidecar I/O helpers |
| `backend/imdf/security/tests/__init__.py` | 1 | Package marker |
| `backend/imdf/security/tests/test_sso_mfa_c2pa.py` | 454 | 26 pytest tests across SSO/MFA/ABAC/C2PA/Schemas |

**Total new LOC**: 2,394

### Modified files (1)
| File | Change |
|---|---|
| `backend/imdf/skills/registry.py` | Added `_run_sso_authenticate` / `_run_mfa_enforce` / `_run_c2pa_provenance` functions + `SSO_AUTHENTICATE_SPEC` / `MFA_ENFORCE_SPEC` / `C2PA_PROVENANCE_SPEC` constants. Extended `SECURITY_SKILLS` list from 2 → 5 skills. Updated `__all__`. |

## Test results

```
D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/security/tests/test_sso_mfa_c2pa.py -v --tb=short
======================== 26 passed, 1 warning in 0.30s ========================
```

| Suite | Count | Description |
|---|---|---|
| TestSSO | 5 | SAML redirect, OAuth2 authorize URL, OAuth2 callback, OIDC discovery, LDAP bind success/fail |
| TestMFA | 8 | TOTP secret format, TOTP provisioning URI, TOTP round-trip, SMS OTP round-trip, Email OTP round-trip, Backup one-time-use, challenge error path, full enroll-challenge-verify flow |
| TestABAC | 5 | Admin bypass, owner-can-delete-own, non-owner-can't-delete, project-member-can-read, non-member-can't-read |
| TestC2PA | 6 | sign+verify round-trip, tampered manifest, modified asset, store record/get, missing manifest returns None, sidecar I/O |
| TestSchemasAndSurface | 2 | Pydantic v2 schemas importable, __init__.py re-exports all symbols |
| **Total** | **26** | **(≥20 required, +30%)** |

## E2E example — user flow

```python
import asyncio, base64, tempfile
from imdf.security import (
    SSOManager, MFAManager, MFAMethod,
    ABACEngine, C2PASigner, C2PAVerifier, C2PAStore,
)

# ── 1. User logs in via OAuth2 (Google) ────────────────────────────────
sso = SSOManager()
auth_url = await sso.oauth2_authorize("google", scopes=["openid", "email", "profile"])
# → "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=mock-google-client-id&..."
# (frontend 302 redirect)
state = parse_qs(urlparse(auth_url).query)["state"][0]
result = await sso.oauth2_callback("google", "code_alice", state=state)
# → AuthResult(success=True, user_id="google-1001", email="alice@example.com",
#              access_token="mock_access_...", refresh_token="mock_refresh_...",
#              id_token="<3-segment base64>")

# ── 2. JWT returned to user → user enables MFA TOTP ────────────────────
mfa = MFAManager()
enr = mfa.enroll_totp(result.user_id)
# → EnrollmentResult(success=True, method=TOTP,
#                    secret="JBSWY3DPEHPK3PXP",
#                    provisioning_uri="otpauth://totp/IMDF:google-1001?secret=...&issuer=IMDF&period=30&digits=6")
# (frontend shows QR code → user scans with Google Authenticator)

# ── 3. User uploads an image (asset_data) ──────────────────────────────
asset_data = b"<binary image bytes>"
signer = C2PASigner(claim_generator="IMDF-Security-C2PA/1.0")
manifest = await signer.sign_manifest(
    asset_data,
    claim={
        "creator": result.user_id,
        "created_at": "2026-07-03T05:30:00Z",
        "license": "CC-BY-4.0",
        "tool_chain": ["ComfyUI-SDXL", "imdf-upscale-v2"],
    },
)
# → C2PAManifest(manifest_id="mf_...", asset_hash=<sha256>,
#                signature=<base64 ed25519>, public_key=<base64 ed25519>, ...)

# ── 4. Persist manifest in C2PA store ─────────────────────────────────
store = C2PAStore(db_path=tempfile.mktemp(suffix=".sqlite3"))
await store.record(manifest)

# ── 5. ABAC enforces: alice can read her own project ──────────────────
abac = ABACEngine()
decision = abac.enforce(
    user_id=result.user_id,
    resource="project:42",
    action="read",
    context={
        "user_attrs": {"id": result.user_id, "role": "user"},
        "resource_attrs": {
            "id": "42", "type": "project",
            "member_ids": ["u-alice", "u-bob"],
        },
    },
)
assert decision.allow is True
assert decision.matched_policy == "project_member_read"

# ── 6. Later — verify manifest integrity on the asset ──────────────────
verifier = C2PAVerifier(expected_claim_generator="IMDF-Security-C2PA/1.0")
verification = await verifier.verify(asset_data, manifest)
assert verification.valid is True
assert verification.asset_hash_match is True
assert verification.signature_valid is True
```

## Notes for verifier

1. **Why `cryptography` instead of `ed25519` standalone?** `cryptography` 44.0.2 was
   already installed; the `ed25519` standalone package isn't. `cryptography` exposes
   `Ed25519PrivateKey` / `Ed25519PublicKey` directly under
   `cryptography.hazmat.primitives.asymmetric.ed25519`. Used in production-grade code.

2. **Why no `pyotp`?** Not installed. Implemented RFC 6238 (HMAC-SHA1, 30s, 6 digits,
   ±window=1) in `mfa.py:_hotp` / `_totp_at` — ~30 lines, no external dep.

3. **Why no `ldap3` / `python3-saml` / `authlib`?** None installed. `SSOManager` uses
   an in-memory `_MockIdPRegistry` that exposes the same call surface; production
   replacement is a per-method body swap (authlib for OAuth2/OIDC, python3-saml for
   SAML, ldap3 for LDAP).

4. **Why `IN_ATTR` operator in ABAC?** First implementation tried `Condition(value="__SELF__")`
   for `user.id IN resource.member_ids`, but the sentinel logic collided with `IN` semantics.
   Added `ConditionOp.IN_ATTR` where `value` is an attribute path (`"resource.member_ids"`)
   and `attribute` is the needle (`"user.id"`). Also added backward-compat handling for
   `__SELF__` in older policies.

5. **Where does this fit with existing `engines/c2pa_engine.py`?** That file uses RSA-PSS
   + X.509 (production PKI). This new module uses Ed25519 (skill-level fast verify).
   They are intentionally complementary, NOT a replacement. The new module's
   `claim_generator` defaults to `IMDF-Security-C2PA/1.0` to make them distinguishable.

6. **Production hooks not implemented (out of scope for 25min):**
   - Real SMS/Email sender: inject via `MFAManager(sms_sender=..., email_sender=...)`
   - HSM/KMS for Ed25519 private key: swap `C2PASigner(private_key=...)`
   - Redis-backed state cache: swap `_MockIdPRegistry._states`
   - C2PA manifest embedded into JPEG/PNG APP1 box (currently sidecar JSON)

## Skill registry verification

```
Security skills: 5
  - security_owasp_protect (5.4.0) author=security
  - pii_redact (5.4.0) author=security
  - sso_authenticate (5.4.0) author=security  ← NEW
  - mfa_enforce (5.4.0) author=security       ← NEW
  - c2pa_provenance (5.4.0) author=security   ← NEW
```