"""VDP-2026 R6 — AI Provider Registry.

Extend the existing ``model_gateway.py`` with a clean registry abstraction
that:

  - tracks every provider configuration (openai / claude / deepseek / qwen /
    doubao / gemini / kimi / zhipu / baidu / tencent / mistral / cohere /
    minimax / stepfun / nova / comfyui / mock)
  - records cost / quota / latency per provider
  - exposes a single ``route()`` endpoint that selects the cheapest capable
    provider for a given model family
  - falls back to the cheaper provider on 4xx/5xx / timeout

This module is read-mostly plus cost tracking — the actual request handling
stays in the gateway layer; here we add the operational scaffolding.

P19-A2 batch 2 additions: gemini / kimi / zhipu / baidu / tencent.
P19-B2 batch 3 additions: mistral / cohere / minimax / stepfun / nova.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = __import__("logging").getLogger(__name__)


_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        backend = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend / "data" / "providers.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _init_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    p = get_db_path()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                family TEXT NOT NULL,                -- openai | claude | deepseek | qwen | doubao | comfyui | mock
                api_base TEXT DEFAULT '',
                default_model TEXT NOT NULL,
                price_per_1k_input REAL DEFAULT 0,
                price_per_1k_output REAL DEFAULT 0,
                quota_per_minute INTEGER DEFAULT 60,
                latency_p50_ms INTEGER DEFAULT 1000,
                latency_p99_ms INTEGER DEFAULT 3000,
                trust_level TEXT DEFAULT 'verified',
                status TEXT NOT NULL DEFAULT 'active',
                config_json TEXT DEFAULT '{}',
                registered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_calls_provider ON provider_calls(provider_id, created_at DESC);
            """
        )


class ProviderFamily(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    DOUBAO = "doubao"
    GEMINI = "gemini"
    KIMI = "kimi"
    ZHIPU = "zhipu"
    BAIDU = "baidu"
    TENCENT = "tencent"
    MISTRAL = "mistral"        # P19-B2 batch 3
    COHERE = "cohere"          # P19-B2 batch 3
    MINIMAX = "minimax"        # P19-B2 batch 3
    STEPFUN = "stepfun"        # P19-B2 batch 3
    NOVA = "nova"              # P19-B2 batch 3
    AGNES = "agnes"
    COMFYUI = "comfyui"
    MOCK = "mock"


@dataclass
class Provider:
    id: str
    name: str
    family: str
    default_model: str
    api_base: str = ""
    price_per_1k_input: float = 0.0
    price_per_1k_output: float = 0.0
    quota_per_minute: int = 60
    latency_p50_ms: int = 1000
    latency_p99_ms: int = 3000
    trust_level: str = "verified"
    status: str = "active"
    config: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 7 starter providers, prices taken from public lists (2026-02 snapshot)
SAMPLE_PROVIDERS = [
    Provider(
        id="openai", name="OpenAI", family=ProviderFamily.OPENAI.value,
        default_model="gpt-4o-mini",
        api_base="https://api.openai.com/v1",
        price_per_1k_input=0.00015, price_per_1k_output=0.0006,
        latency_p50_ms=600, latency_p99_ms=1800,
        trust_level="official",
    ),
    Provider(
        id="claude", name="Anthropic Claude", family=ProviderFamily.CLAUDE.value,
        default_model="claude-3-5-sonnet-20241022",
        api_base="https://api.anthropic.com/v1",
        price_per_1k_input=0.003, price_per_1k_output=0.015,
        latency_p50_ms=900, latency_p99_ms=2200,
        trust_level="official",
    ),
    Provider(
        id="deepseek", name="DeepSeek", family=ProviderFamily.DEEPSEEK.value,
        default_model="deepseek-chat",
        api_base="https://api.deepseek.com/v1",
        price_per_1k_input=0.00014, price_per_1k_output=0.00028,
        latency_p50_ms=300, latency_p99_ms=900,
        trust_level="verified",
    ),
    Provider(
        id="qwen", name="阿里通义千问", family=ProviderFamily.QWEN.value,
        default_model="qwen-plus",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        price_per_1k_input=0.0004, price_per_1k_output=0.0012,
        latency_p50_ms=400, latency_p99_ms=1200,
        trust_level="verified",
    ),
    Provider(
        id="doubao", name="字节豆包", family=ProviderFamily.DOUBAO.value,
        default_model="doubao-seed-1-6-250615",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        price_per_1k_input=0.0008, price_per_1k_output=0.002,
        latency_p50_ms=500, latency_p99_ms=1500,
        trust_level="verified",
        config={
            "models": ["doubao-seed-1-6-250615", "doubao-1-5-vision-pro-250328",
                        "doubao-pro-32k-241215", "doubao-lite-32k-241215"],
            "image_model": "doubao-seedream-4-0-250828",
            "video_model": "doubao-seedance-2-0-260128",
        },
    ),
    Provider(
        id="agnes", name="Agnes 免费全模态", family=ProviderFamily.AGNES.value,
        default_model="agnes-2.0-flash",
        api_base="https://platform.agnes-ai.com/api/v1",
        price_per_1k_input=0.0, price_per_1k_output=0.0,
        quota_per_minute=120, latency_p50_ms=400, latency_p99_ms=1500,
        trust_level="verified",
        config={
            "models": ["agnes-2.0-flash", "agnes-image-2.1-flash",
                        "agnes-video-2.0", "agnes-drama-1.0"],
            "free": True,
            "modalities": ["text", "image", "video", "drama"],
        },
    ),
    # ----- P19-A2 batch 2: gemini / kimi / zhipu / baidu / tencent -----
    Provider(
        id="gemini", name="Google Gemini", family=ProviderFamily.GEMINI.value,
        default_model="gemini-2.0-flash",
        api_base="https://generativelanguage.googleapis.com/v1beta",
        price_per_1k_input=0.0007, price_per_1k_output=0.0021,
        latency_p50_ms=600, latency_p99_ms=1800,
        trust_level="official",
        config={
            "protocol": "gemini", "auth": "x-goog-api-key",
            "models": ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.0-flash-vision"],
            "vision_models": ["gemini-2.0-flash-vision", "gemini-2.0-flash", "gemini-2.5-pro"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
        },
    ),
    Provider(
        id="kimi", name="月之暗面 Kimi", family=ProviderFamily.KIMI.value,
        default_model="kimi-k2.7",
        api_base="https://api.moonshot.cn/v1",
        price_per_1k_input=0.0003, price_per_1k_output=0.0009,
        latency_p50_ms=700, latency_p99_ms=2000,
        trust_level="verified",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["kimi-k2.7", "moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"],
            "vision_models": ["kimi-k2.7-vision", "moonshot-v1-8k-vision-preview"],
            "supports_streaming": True, "supports_vision": True,
            "max_context_tokens": 128000,
        },
    ),
    Provider(
        id="zhipu", name="智谱 GLM", family=ProviderFamily.ZHIPU.value,
        default_model="glm-4-plus",
        api_base="https://open.bigmodel.cn/api/paas/v4",
        price_per_1k_input=0.0004, price_per_1k_output=0.0012,
        latency_p50_ms=500, latency_p99_ms=1500,
        trust_level="verified",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["glm-4-plus", "glm-4v-plus", "glm-4-air", "glm-4-flash"],
            "vision_models": ["glm-4v-plus", "glm-4v"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
        },
    ),
    Provider(
        id="baidu", name="百度文心 ERNIE", family=ProviderFamily.BAIDU.value,
        default_model="ernie-4.0-turbo",
        api_base="https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        price_per_1k_input=0.00035, price_per_1k_output=0.001,
        latency_p50_ms=800, latency_p99_ms=2200,
        trust_level="verified",
        config={
            "protocol": "baidu", "auth": "client_credentials",
            "oauth_base": "https://aip.baidubce.com",
            "models": ["ernie-4.0-turbo", "ernie-4.0-8k", "ernie-3.5-8k", "ernie-3.5-4k"],
            "vision_models": ["ernie-4.0-turbo-vision"],
            "supports_streaming": True, "supports_vision": True,
        },
    ),
    Provider(
        id="tencent", name="腾讯混元 Hunyuan", family=ProviderFamily.TENCENT.value,
        default_model="hunyuan-pro",
        api_base="https://hunyuan.tencent.com/v1",
        price_per_1k_input=0.0003, price_per_1k_output=0.0009,
        latency_p50_ms=600, latency_p99_ms=1800,
        trust_level="verified",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["hunyuan-pro", "hunyuan-standard", "hunyuan-turbo", "hunyuan-vision"],
            "vision_models": ["hunyuan-vision", "hunyuan-turbo-vision"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
        },
    ),
    # ----- P19-B2 batch 3: mistral / cohere / minimax / stepfun / nova -----
    Provider(
        id="mistral", name="Mistral AI (欧洲)", family=ProviderFamily.MISTRAL.value,
        default_model="mistral-large-latest",
        api_base="https://api.mistral.ai/v1",
        price_per_1k_input=0.002, price_per_1k_output=0.006,
        latency_p50_ms=700, latency_p99_ms=2000,
        trust_level="official",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["mistral-large-latest", "mistral-small-latest", "mixtral-8x7b",
                       "open-mistral-7b", "open-mixtral-8x22b"],
            "vision_models": ["pixtral-12b-2409", "pixtral-large-latest"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
            "region": "eu", "max_context_tokens": 128000,
        },
    ),
    Provider(
        id="cohere", name="Cohere (RAG 优化)", family=ProviderFamily.COHERE.value,
        default_model="command-r-plus",
        api_base="https://api.cohere.ai/v1",
        price_per_1k_input=0.0025, price_per_1k_output=0.01,
        latency_p50_ms=600, latency_p99_ms=1800,
        trust_level="official",
        config={
            "protocol": "cohere", "auth": "bearer",
            "models": ["command-r-plus", "command-r", "command", "command-light"],
            "embed_models": ["embed-english-v3.0", "embed-multilingual-v3.0",
                             "embed-english-light-v3.0"],
            "rerank_models": ["rerank-english-v3.0", "rerank-multilingual-v3.0"],
            "supports_streaming": True, "supports_function_call": True,
            "supports_rag": True, "supports_embed": True, "supports_rerank": True,
            "max_context_tokens": 128000,
        },
    ),
    Provider(
        id="minimax", name="MiniMax (MiniMax abab)", family=ProviderFamily.MINIMAX.value,
        default_model="abab-6.5s",
        api_base="https://api.minimax.chat/v1",
        price_per_1k_input=0.0006, price_per_1k_output=0.0018,
        latency_p50_ms=600, latency_p99_ms=2000,
        trust_level="verified",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["abab-6.5s", "abab-6.5-chat", "abab-6.5t", "abab-5.5-chat"],
            "vision_models": ["abab-6.5s"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
            "region": "cn", "max_context_tokens": 200000,
        },
    ),
    Provider(
        id="stepfun", name="阶跃星辰 Stepfun", family=ProviderFamily.STEPFUN.value,
        default_model="step-1-8k",
        api_base="https://api.stepfun.com/v1",
        price_per_1k_input=0.00025, price_per_1k_output=0.00075,
        latency_p50_ms=500, latency_p99_ms=1500,
        trust_level="verified",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["step-1-8k", "step-1-32k", "step-1-128k",
                       "step-1v-8k", "step-1v-32k"],
            "vision_models": ["step-1v-8k", "step-1v-32k"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
            "region": "cn",
        },
    ),
    Provider(
        id="nova", name="零一万物 Nova", family=ProviderFamily.NOVA.value,
        default_model="yi-34b",
        api_base="https://api.lingyiwanwu.com/v1",
        price_per_1k_input=0.0002, price_per_1k_output=0.0006,
        latency_p50_ms=500, latency_p99_ms=1500,
        trust_level="verified",
        config={
            "protocol": "openai-compatible", "auth": "bearer",
            "models": ["yi-34b", "yi-6b", "yi-6b-chat", "yi-34b-chat", "yi-vl-6b"],
            "vision_models": ["yi-vl-6b"],
            "supports_streaming": True, "supports_vision": True,
            "supports_function_call": True,
            "region": "cn", "max_context_tokens": 200000,
        },
    ),
    Provider(
        id="comfyui", name="ComfyUI Local", family=ProviderFamily.COMFYUI.value,
        default_model="sdxl_base_1.0",
        api_base="http://localhost:8188",
        price_per_1k_input=0.0, price_per_1k_output=0.0,
        quota_per_minute=10, latency_p50_ms=5000, latency_p99_ms=20000,
        trust_level="internal",
    ),
    Provider(
        id="mock", name="本地 Mock", family=ProviderFamily.MOCK.value,
        default_model="mock-1",
        price_per_1k_input=0.0, price_per_1k_output=0.0,
        quota_per_minute=99999, latency_p50_ms=10, latency_p99_ms=20,
        trust_level="internal",
        status="active",
    ),
]


class ProviderRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def ensure_samples(self) -> None:
        with _conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
        if count > 0:
            return
        for p in SAMPLE_PROVIDERS:
            self.upsert(p)

    def upsert(self, p: Provider) -> None:
        with self._lock:
            with _conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO providers (
                        id, name, family, api_base, default_model,
                        price_per_1k_input, price_per_1k_output, quota_per_minute,
                        latency_p50_ms, latency_p99_ms, trust_level,
                        status, config_json, registered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p.id, p.name, p.family, p.api_base, p.default_model,
                        p.price_per_1k_input, p.price_per_1k_output, p.quota_per_minute,
                        p.latency_p50_ms, p.latency_p99_ms, p.trust_level,
                        p.status, json.dumps(p.config, ensure_ascii=False),
                        p.registered_at,
                    ),
                )

    def list(self) -> List[Provider]:
        with _conn() as conn:
            rows = conn.execute("SELECT * FROM providers").fetchall()
        return [self._row(r) for r in rows]

    def get(self, pid: str) -> Optional[Provider]:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM providers WHERE id = ?", (pid,)).fetchone()
        if not row:
            return None
        return self._row(row)

    def by_family(self, family: str) -> List[Provider]:
        return [p for p in self.list() if p.family == family]

    def _row(self, r: sqlite3.Row) -> Provider:
        return Provider(
            id=r["id"], name=r["name"], family=r["family"], api_base=r["api_base"],
            default_model=r["default_model"],
            price_per_1k_input=r["price_per_1k_input"], price_per_1k_output=r["price_per_1k_output"],
            quota_per_minute=r["quota_per_minute"], latency_p50_ms=r["latency_p50_ms"],
            latency_p99_ms=r["latency_p99_ms"], trust_level=r["trust_level"],
            status=r["status"], config=json.loads(r["config_json"] or "{}"),
            registered_at=r["registered_at"],
        )

    # ---- routing logic -----------------------------------------------
    def route(
        self,
        family: str,
        prefer: str = "cost",
        exclude: Optional[List[str]] = None,
    ) -> Optional[Provider]:
        """Pick the best provider for a family.

        ``prefer`` is one of: cost (cheapest), speed (lowest p50),
        trust (highest trust_level).
        """
        exclude = exclude or []
        cands = [p for p in self.by_family(family) if p.status == "active" and p.id not in exclude]
        if not cands:
            # fall back to mock so requests never fail in dev environments
            return self.get("mock")
        if prefer == "speed":
            return min(cands, key=lambda p: p.latency_p50_ms)
        if prefer == "trust":
            order = {"internal": 0, "community": 1, "verified": 2, "official": 3}
            return max(cands, key=lambda p: order.get(p.trust_level, 0))
        return min(cands, key=lambda p: p.price_per_1k_input + p.price_per_1k_output)

    # ---- call accounting ---------------------------------------------
    def record_call(
        self, provider_id: str, model: str,
        input_tokens: int = 0, output_tokens: int = 0,
        latency_ms: int = 0, status: str = "success",
    ) -> None:
        p = self.get(provider_id)
        cost = 0.0
        if p:
            cost = (input_tokens / 1000) * p.price_per_1k_input + (output_tokens / 1000) * p.price_per_1k_output
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO provider_calls (
                    provider_id, model, input_tokens, output_tokens,
                    cost_usd, latency_ms, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (provider_id, model, input_tokens, output_tokens,
                 round(cost, 6), latency_ms, status,
                 datetime.now(timezone.utc).isoformat()),
            )

    def call_summary(self) -> Dict[str, Any]:
        with _conn() as conn:
            rows = conn.execute("SELECT * FROM provider_calls").fetchall()
        by_provider: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            d = by_provider.setdefault(r["provider_id"], {
                "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "errors": 0,
            })
            d["calls"] += 1
            d["input_tokens"] += r["input_tokens"]
            d["output_tokens"] += r["output_tokens"]
            d["cost_usd"] += r["cost_usd"]
            if r["status"] != "success":
                d["errors"] += 1
        return {
            "providers": by_provider,
            "total_calls": len(rows),
            "total_cost_usd": round(sum(d["cost_usd"] for d in by_provider.values()), 4),
        }


_REGISTRY: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ProviderRegistry()
        _REGISTRY.ensure_samples()
    return _REGISTRY


def reset_registry_for_test() -> None:
    global _REGISTRY
    _REGISTRY = None
