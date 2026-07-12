"""V5 第40章 — SSO 集成 (SAML / OAuth2 / OIDC / LDAP).

实现重点: 接口完整 + 业务可调用,真实 IdP 交互用 in-memory mock 替代;
生产替换说明见每个方法 docstring.

SSOManager 暴露 4 类入口:
  * SAML:        initiate_saml_login → RedirectResponse; handle_saml_callback → AuthResult
  * OAuth2:      oauth2_authorize(provider, scopes) → auth URL; oauth2_callback → AuthResult
  * OIDC:        oidc_discovery(issuer) → OIDCConfig (RFC 8414)
  * LDAP:        ldap_bind(dn, password) → bool

设计选择:
  * 不强依赖 python3-saml / authlib / ldap3 — 全部 mock;生产替换时
    把每个方法体里的 _mock_* 调用换成真实 client 即可.
  * 状态(state, nonce) 内存存,30min 自动过期.生产应换 Redis.
  * id_token 不做 JWT signature verify (mocked);生产用 authlib.jose.jwt.decode.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

from .sso_mfa_c2pa_schemas import AuthResult, OIDCConfig, SSOProvider

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# In-memory mock IdP registry
# ════════════════════════════════════════════════════════════════════════
class _MockIdPRegistry:
    """集中存放 mock IdP 数据: 用户 / token / discovery docs."""

    def __init__(self) -> None:
        # provider → {client_id, client_secret, authorize_url, token_url, userinfo_url, users}
        self.oauth_providers: Dict[str, Dict[str, Any]] = {}
        # issuer → OIDC discovery dict
        self.oidc_issuers: Dict[str, Dict[str, Any]] = {}
        # authorization_codes (one-time)
        self.auth_codes: Dict[str, Dict[str, Any]] = {}
        # access_tokens (mapped)
        self.access_tokens: Dict[str, Dict[str, Any]] = {}
        # LDAP users (DN → password)
        self.ldap_users: Dict[str, str] = {}
        # SAML pending requests (relay_state → SAMLRequest + state)
        self.saml_pending: Dict[str, Dict[str, Any]] = {}
        # state/nonce (state → expiry + provider)
        self._states: Dict[str, Dict[str, Any]] = {}

        # Register some defaults for quick demo
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register_oauth_provider(
            "google",
            client_id="mock-google-client-id",
            client_secret="mock-google-secret",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            users={
                "alice@example.com": {"sub": "google-1001", "name": "Alice Google", "email": "alice@example.com"},
                "bob@example.com": {"sub": "google-1002", "name": "Bob Google", "email": "bob@example.com"},
            },
        )
        self.register_oauth_provider(
            "github",
            client_id="mock-github-client-id",
            client_secret="mock-github-secret",
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
            users={
                "carol": {"sub": "gh-2001", "name": "Carol Dev", "email": "carol@github.com"},
            },
        )
        self.register_oidc_issuer(
            "https://accounts.google.com",
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
            jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
            scopes_supported=["openid", "email", "profile"],
            response_types_supported=["code", "id_token", "token"],
            subject_types_supported=["public"],
        )
        self.register_ldap_user("uid=alice,ou=users,dc=example,dc=com", "alice-pwd")
        self.register_ldap_user("uid=bob,ou=users,dc=example,dc=com", "bob-pwd")
        self.register_ldap_user("uid=admin,ou=admins,dc=example,dc=com", "admin-pwd")

    # ── OAuth provider registration ─────────────────────────────────────
    def register_oauth_provider(
        self, name: str, *,
        client_id: str, client_secret: str,
        authorize_url: str, token_url: str, userinfo_url: str,
        users: Dict[str, Dict[str, Any]],
    ) -> None:
        self.oauth_providers[name] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "authorize_url": authorize_url,
            "token_url": token_url,
            "userinfo_url": userinfo_url,
            "users": users,
        }

    def register_oidc_issuer(
        self, issuer: str, *,
        authorization_endpoint: str, token_endpoint: str,
        userinfo_endpoint: Optional[str] = None,
        jwks_uri: Optional[str] = None,
        scopes_supported: Optional[List[str]] = None,
        response_types_supported: Optional[List[str]] = None,
        subject_types_supported: Optional[List[str]] = None,
    ) -> None:
        self.oidc_issuers[issuer] = {
            "issuer": issuer,
            "authorization_endpoint": authorization_endpoint,
            "token_endpoint": token_endpoint,
            "userinfo_endpoint": userinfo_endpoint,
            "jwks_uri": jwks_uri,
            "scopes_supported": scopes_supported or ["openid"],
            "response_types_supported": response_types_supported or ["code"],
            "subject_types_supported": subject_types_supported or ["public"],
        }

    def register_ldap_user(self, dn: str, password: str) -> None:
        self.ldap_users[dn] = password

    # ── State / nonce management ────────────────────────────────────────
    def save_state(self, state: str, provider: str, *, extra: Optional[Dict[str, Any]] = None) -> None:
        self._states[state] = {
            "provider": provider,
            "created_at": time.time(),
            "extra": extra or {},
        }

    def consume_state(self, state: str) -> Optional[Dict[str, Any]]:
        s = self._states.pop(state, None)
        if not s:
            return None
        if time.time() - s["created_at"] > 1800:  # 30min
            return None
        return s


# ════════════════════════════════════════════════════════════════════════
# SSOManager
# ════════════════════════════════════════════════════════════════════════
class SSOManager:
    """统一 SSO 入口 — 4 个 provider 共用 1 个 in-memory IdP registry.

    Args:
        saml_idp_entity_id: SAML IdP entity id
        saml_idp_sso_url: SAML IdP SSO redirect URL
        sp_entity_id: SP (this service) entity id
        sp_acs_url: SP (this service) assertion consumer URL
        default_redirect_uri: oauth2 callback default
    """

    def __init__(
        self,
        *,
        saml_idp_entity_id: str = "https://idp.example.com/saml/metadata",
        saml_idp_sso_url: str = "https://idp.example.com/saml/sso",
        sp_entity_id: str = "https://imdf.example.com/saml/metadata",
        sp_acs_url: str = "https://imdf.example.com/saml/acs",
        default_redirect_uri: str = "https://imdf.example.com/oauth/callback",
    ) -> None:
        self.saml_idp_entity_id = saml_idp_entity_id
        self.saml_idp_sso_url = saml_idp_sso_url
        self.sp_entity_id = sp_entity_id
        self.sp_acs_url = sp_acs_url
        self.default_redirect_uri = default_redirect_uri
        self.idp = _MockIdPRegistry()

    # ── SAML ────────────────────────────────────────────────────────────
    def initiate_saml_login(
        self,
        request: Optional[Dict[str, Any]] = None,
        *,
        relay_state: Optional[str] = None,
    ) -> "RedirectResponse":
        """构造 SAML AuthnRequest 重定向到 IdP SSO URL.

        Args:
            request: 可选 fastapi Request (含 host/url); 不传则仅构造 redirect
            relay_state: 业务上下文 (登录后原路返回); 不传则生成随机

        Returns:
            RedirectResponse (FastAPI) — 含 Location header 指向 IdP.
        """
        # 1. SAMLRequest = base64(deflated XML)
        authn_request_xml = (
            f'<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
            f' ID="_{uuid.uuid4().hex[:16]}" Version="2.0"'
            f' IssueInstant="{datetime.now(timezone.utc).isoformat()}"'
            f' AssertionConsumerServiceURL="{self.sp_acs_url}"'
            f' ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
            f'<saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">{self.sp_entity_id}</saml:Issuer>'
            f'</samlp:AuthnRequest>'
        )
        # 不真用 deflate (避免引入 zlib 复杂度),直接 base64
        saml_request_b64 = base64.b64encode(authn_request_xml.encode("utf-8")).decode("ascii")

        if relay_state is None:
            relay_state = secrets.token_urlsafe(16)
        self.idp.saml_pending[relay_state] = {
            "saml_request_id": authn_request_xml.split('ID="')[1].split('"')[0],
            "created_at": time.time(),
        }

        qs = urlencode({
            "SAMLRequest": saml_request_b64,
            "RelayState": relay_state,
        })
        location = f"{self.saml_idp_sso_url}?{qs}"

        # Lazy import fastapi (避免 hard dep)
        try:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=location, status_code=302)
        except ImportError:
            # Fallback: 返回纯 dict,业务方自己处理
            return {"location": location, "status_code": 302, "_type": "RedirectResponse"}

    async def handle_saml_callback(
        self,
        request: Dict[str, Any],
    ) -> AuthResult:
        """处理 IdP POST 回来的 SAMLResponse.

        Args:
            request: dict 形如 {"SAMLResponse": "<base64>", "RelayState": "..."}

        生产替换: 解析 SAMLResponse → validate signature → extract assertion →
        映射 NameID/Attributes 到 user_id / email / display_name.
        """
        saml_response_b64 = request.get("SAMLResponse", "")
        relay_state = request.get("RelayState", "")
        if not saml_response_b64:
            return AuthResult(success=False, provider=SSOProvider.SAML, error="missing SAMLResponse")
        # 验证 RelayState 在 pending 列表中
        if relay_state not in self.idp.saml_pending:
            return AuthResult(
                success=False, provider=SSOProvider.SAML,
                error="invalid or expired RelayState",
            )
        # 模拟:解 base64 后,从 NameID 提 user_id
        try:
            xml = base64.b64decode(saml_response_b64).decode("utf-8", errors="ignore")
        except Exception:
            xml = ""
        # 简易 mock: 如果包含 "alice" 视为 alice@example.com
        if "alice@example.com" in xml:
            user_id = "alice"
            email = "alice@example.com"
            display_name = "Alice SAML"
        elif "bob@example.com" in xml:
            user_id = "bob"
            email = "bob@example.com"
            display_name = "Bob SAML"
        else:
            return AuthResult(
                success=False, provider=SSOProvider.SAML,
                error="could not extract user from SAMLResponse",
            )
        # 清理 pending
        del self.idp.saml_pending[relay_state]
        return AuthResult(
            success=True,
            user_id=user_id,
            email=email,
            display_name=display_name,
            provider=SSOProvider.SAML,
            raw_claims={"relay_state": relay_state, "xml_preview": xml[:200]},
        )

    # ── OAuth2 ──────────────────────────────────────────────────────────
    async def oauth2_authorize(
        self,
        provider: str,
        scopes: Optional[List[str]] = None,
        *,
        state: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> str:
        """构造 OAuth2 / OIDC authorize URL.

        Args:
            provider:  "google" / "github" / 其他 register_oauth_provider 注册的
            scopes:    ["openid", "email", "profile"]
            state:     CSRF token; 不传则生成
            redirect_uri: 回调地址; 不传则用 self.default_redirect_uri

        Returns:
            authorize URL (前端 302 到这里)
        """
        if provider not in self.idp.oauth_providers:
            raise ValueError(f"unknown oauth provider: {provider}")
        cfg = self.idp.oauth_providers[provider]
        if state is None:
            state = secrets.token_urlsafe(24)
        if redirect_uri is None:
            redirect_uri = self.default_redirect_uri
        scope_str = " ".join(scopes or ["openid", "email", "profile"])
        self.idp.save_state(state, provider, extra={"redirect_uri": redirect_uri, "scopes": scopes or []})
        qs = urlencode({
            "response_type": "code",
            "client_id": cfg["client_id"],
            "redirect_uri": redirect_uri,
            "scope": scope_str,
            "state": state,
        })
        return f"{cfg['authorize_url']}?{qs}"

    async def oauth2_callback(
        self,
        provider: str,
        code: str,
        *,
        state: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        code_verifier: Optional[str] = None,  # for PKCE — mock only
    ) -> AuthResult:
        """处理 OAuth2 / OIDC callback.code 换 access_token + userinfo.

        生产替换: 用 authlib (或 httpx + provider's token endpoint) 真正换 token.
        这里 mock: 在 idp 内直接生成 access_token / refresh_token / id_token.
        """
        if provider not in self.idp.oauth_providers:
            return AuthResult(
                success=False, provider=SSOProvider.OAUTH2,
                error=f"unknown provider: {provider}",
            )
        cfg = self.idp.oauth_providers[provider]
        # state 校验
        if state is not None:
            saved = self.idp.consume_state(state)
            if not saved or saved["provider"] != provider:
                return AuthResult(
                    success=False, provider=SSOProvider.OAUTH2,
                    error="invalid or expired state",
                )
        # mock: code 形如 "code_<provider>_<username>" 直接映射到 user
        # 或 任意 code 配默认 user
        username = code.split("_")[-1] if code.startswith("code_") else "alice"
        users = cfg.get("users", {})
        user_info = users.get(username) or next(iter(users.values()), None)
        if user_info is None:
            return AuthResult(
                success=False, provider=SSOProvider.OAUTH2,
                error="no user found for code",
            )
        access_token = f"mock_access_{uuid.uuid4().hex[:16]}"
        refresh_token = f"mock_refresh_{uuid.uuid4().hex[:16]}"
        # id_token (mocked JWT-like 三段,无 signature)
        header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        payload_dict = {
            "iss": cfg["authorize_url"].split("/o/oauth2")[0],
            "sub": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "aud": cfg["client_id"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        payload = base64.urlsafe_b64encode(
            json.dumps(payload_dict, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        id_token = f"{header}.{payload}.mocksig"

        # 缓存 token 以备 test 验证
        self.idp.access_tokens[access_token] = {
            "provider": provider,
            "user": user_info,
            "expires_at": time.time() + 3600,
        }

        return AuthResult(
            success=True,
            user_id=user_info.get("sub"),
            email=user_info.get("email"),
            display_name=user_info.get("name"),
            provider=SSOProvider.OAUTH2,
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            expires_at=datetime.fromtimestamp(payload_dict["exp"], tz=timezone.utc),
            raw_claims={
                "provider": provider,
                "username": username,
                "scope": "openid email profile",
            },
        )

    # ── OIDC discovery ──────────────────────────────────────────────────
    async def oidc_discovery(self, issuer: str) -> OIDCConfig:
        """RFC 8414 OIDC discovery: GET {issuer}/.well-known/openid-configuration.

        Args:
            issuer: Issuer URL (e.g. "https://accounts.google.com")

        Returns:
            OIDCConfig 包含 authorization_endpoint / token_endpoint / etc.
        """
        # mock: 直接从 idp.oidc_issuers 拿
        if issuer in self.idp.oidc_issuers:
            d = self.idp.oidc_issuers[issuer]
            return OIDCConfig(**d)
        # 真实实现: httpx.get(f"{issuer}/.well-known/openid-configuration").json()
        raise ValueError(f"OIDC discovery failed for issuer: {issuer}")

    # ── LDAP ────────────────────────────────────────────────────────────
    async def ldap_bind(self, dn: str, password: str) -> bool:
        """简单 LDAP bind 验证 — DN + 密码匹配即 True.

        生产替换: ldap3.Connection(server, user=dn, password=password).bind()
        """
        expected = self.idp.ldap_users.get(dn)
        if expected is None:
            return False
        # constant-time 比较
        return hmac.compare_digest(expected, password)


__all__ = ["SSOManager"]