"""P6-2 P1-5: wordlist_providers — pluggable wordlist sources for cleaning operators.

Replaces the hard-coded ``DEFAULT_TOXIC`` / ``DEFAULT_WORDS`` placeholder
lists in ``operators/text/toxicity.py`` and ``operators/text/sensitive.py``
with provider hooks.

Design
------
- :class:`WordlistProvider` is the abstract base.
- Three concrete providers ship out of the box:
    * :class:`InlineWordlistProvider`     — explicit list passed at init.
    * :class:`FileWordlistProvider`       — loads a JSON file at startup;
                                            can hot-reload if ``watch=True``.
    * :class:`HttpWordlistProvider`       — pulls from a remote HTTP API.
- A small :class:`ProviderRegistry` lets the operators look up the
  currently active provider by ``kind`` (``"toxic"`` or ``"sensitive"``)
  without knowing the concrete implementation.
- When no provider is configured, the registry falls back to a
  :class:`PlaceholderWordlistProvider` that returns the original
  hard-coded ``["toxic_word_1", ...]`` lists and logs a clear warning.
  This keeps the operators runnable in environments where no real
  provider has been deployed yet (e.g. local dev, CI).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cleaning.wordlist_providers")


# ═══════════════════════════════════════════════════════════════════════
# Abstract base
# ═══════════════════════════════════════════════════════════════════════

class WordlistProvider(ABC):
    """Abstract base — every provider returns a list of lowercase strings."""

    kind: str = ""

    @abstractmethod
    def get_words(self) -> List[str]:
        """Return the current word list (do not mutate the result)."""
        raise NotImplementedError

    def name(self) -> str:
        return type(self).__name__


# ═══════════════════════════════════════════════════════════════════════
# Inline provider — explicit list
# ═══════════════════════════════════════════════════════════════════════

class InlineWordlistProvider(WordlistProvider):
    """Hold a fixed list passed at construction time.

    Use case: small, known-good lists (e.g. project-specific banned terms)
    that you don't want to maintain in a separate file.
    """

    def __init__(self, words: List[str], *, kind: str = "inline"):
        self._words = [str(w).strip().lower() for w in words if w]
        self.kind = kind

    def get_words(self) -> List[str]:
        return list(self._words)


# ═══════════════════════════════════════════════════════════════════════
# File provider — load from JSON file
# ═══════════════════════════════════════════════════════════════════════

class FileWordlistProvider(WordlistProvider):
    """Load a word list from a JSON file.

    File format — one of:
      - ``["word1", "word2", ...]``
      - ``{"words": ["..."], "metadata": {...}}``

    Set ``watch=True`` to check the file's mtime on each ``get_words``
    call and reload if it changed.
    """

    def __init__(self, path: str, *, watch: bool = False,
                 kind: str = "file"):
        self.path = path
        self.watch = watch
        self.kind = kind
        # RLock (not Lock): ``get_words`` -> ``_maybe_reload`` may re-enter
        # the same lock on watch=True; using a regular Lock would deadlock
        # the very first call when the file's mtime > 0.
        self._lock = threading.RLock()
        self._mtime: float = 0.0
        self._words: List[str] = []

    def _load(self) -> List[str]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.warning("wordlist_file_missing path=%s", self.path)
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("wordlist_file_load_failed path=%s err=%s",
                           self.path, exc)
            return []
        if isinstance(data, list):
            return [str(w).strip().lower() for w in data if w]
        if isinstance(data, dict):
            words = data.get("words") or data.get("items") or []
            return [str(w).strip().lower() for w in words if w]
        logger.warning("wordlist_file_bad_shape path=%s type=%s",
                       self.path, type(data).__name__)
        return []

    def _maybe_reload(self) -> None:
        if not self.watch:
            return
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime > self._mtime:
            with self._lock:
                if mtime > self._mtime:
                    self._words = self._load()
                    self._mtime = mtime

    def get_words(self) -> List[str]:
        with self._lock:
            if not self._words and not self.watch:
                self._words = self._load()
                try:
                    self._mtime = os.path.getmtime(self.path)
                except OSError:
                    self._mtime = 0.0
            elif self.watch:
                self._maybe_reload()
                if not self._words:
                    self._words = self._load()
            return list(self._words)


# ═══════════════════════════════════════════════════════════════════════
# HTTP provider — pull from a remote API
# ═══════════════════════════════════════════════════════════════════════

class HttpWordlistProvider(WordlistProvider):
    """Fetch a word list from a remote HTTP API.

    Expected API contract::

        GET <url> → {"words": ["...", ...]}  (preferred)
        GET <url> → ["...", ...]             (also accepted)

    Caches the response for ``cache_ttl`` seconds (default 300).
    Network failures return the cached value if available, else ``[]``.
    """

    def __init__(self, url: str, *, cache_ttl: int = 300,
                 headers: Optional[Dict[str, str]] = None,
                 timeout: float = 5.0,
                 kind: str = "http"):
        self.url = url
        self.cache_ttl = cache_ttl
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.kind = kind
        self._lock = threading.Lock()
        self._cached: List[str] = []
        self._cached_at: float = 0.0

    def _fetch(self) -> List[str]:
        try:
            import httpx  # type: ignore
        except ImportError:
            logger.warning("httpx_missing_http_provider_disabled")
            return []
        try:
            resp = httpx.get(self.url, headers=self.headers,
                             timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("wordlist_http_fetch_failed url=%s err=%s",
                           self.url, exc)
            return []
        if isinstance(data, list):
            return [str(w).strip().lower() for w in data if w]
        if isinstance(data, dict):
            words = data.get("words") or data.get("items") or []
            return [str(w).strip().lower() for w in words if w]
        return []

    def get_words(self) -> List[str]:
        now = time.time()
        with self._lock:
            if self._cached and (now - self._cached_at) < self.cache_ttl:
                return list(self._cached)
        # Fetch outside the lock
        fresh = self._fetch()
        with self._lock:
            if fresh:
                self._cached = fresh
                self._cached_at = now
                return list(self._cached)
            # Network failed → return cached if any
            return list(self._cached) if self._cached else []


# ═══════════════════════════════════════════════════════════════════════
# Placeholder provider — fallback for local dev / CI
# ═══════════════════════════════════════════════════════════════════════

class PlaceholderWordlistProvider(WordlistProvider):
    """Returns the original hard-coded placeholder lists.

    Used only when no real provider has been wired in.  Logs a one-shot
    warning so the operator can spot the misconfiguration.
    """

    PLACEHOLDER_TOXIC = ["toxic_word_1", "toxic_word_2"]
    PLACEHOLDER_SENSITIVE = [
        "forbidden_word_1", "forbidden_word_2", "blocked_term",
    ]

    def __init__(self, kind: str):
        self.kind = kind
        self._warned = False

    def get_words(self) -> List[str]:
        if not self._warned:
            logger.warning(
                "wordlist_placeholder_in_use kind=%s — "
                "configure a real WordlistProvider for production",
                self.kind,
            )
            self._warned = True
        if self.kind == "toxic":
            return list(self.PLACEHOLDER_TOXIC)
        if self.kind == "sensitive":
            return list(self.PLACEHOLDER_SENSITIVE)
        return []


# ═══════════════════════════════════════════════════════════════════════
# Registry — looks up providers by kind
# ═══════════════════════════════════════════════════════════════════════

class ProviderRegistry:
    """Thread-safe singleton-ish registry mapping kind → provider."""

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: Dict[str, WordlistProvider] = {}

    def register(self, kind: str, provider: WordlistProvider) -> None:
        with self._lock:
            self._providers[kind] = provider

    def get(self, kind: str) -> WordlistProvider:
        with self._lock:
            prov = self._providers.get(kind)
        if prov is not None:
            return prov
        # Fallback to placeholder; this keeps the operators runnable.
        placeholder = PlaceholderWordlistProvider(kind=kind)
        with self._lock:
            self._providers[kind] = placeholder
        return placeholder

    def reset(self) -> None:
        with self._lock:
            self._providers.clear()


# Environment-driven bootstrap -----------------------------------------

_registry: Optional[ProviderRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> ProviderRegistry:
    """Return the process-global registry, bootstrapping from env vars."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ProviderRegistry()
                _bootstrap_from_env(_registry)
    return _registry


def reset_registry_for_tests() -> None:
    """Drop the singleton (test helper)."""
    global _registry
    with _registry_lock:
        _registry = None


def _bootstrap_from_env(reg: ProviderRegistry) -> None:
    """Read env vars and register providers.

    Supported variables (all optional):
        CLEANING_TOXIC_WORDS_FILE       — path to a JSON word list
        CLEANING_SENSITIVE_WORDS_FILE   — path to a JSON word list
        CLEANING_TOXIC_WORDS_URL        — HTTP API endpoint
        CLEANING_SENSITIVE_WORDS_URL    — HTTP API endpoint
        CLEANING_TOXIC_WORDS_INLINE     — comma-separated inline list
        CLEANING_SENSITIVE_WORDS_INLINE — comma-separated inline list
    """
    toxic_file = os.environ.get("CLEANING_TOXIC_WORDS_FILE", "").strip()
    sensitive_file = os.environ.get(
        "CLEANING_SENSITIVE_WORDS_FILE", "").strip()
    toxic_url = os.environ.get("CLEANING_TOXIC_WORDS_URL", "").strip()
    sensitive_url = os.environ.get(
        "CLEANING_SENSITIVE_WORDS_URL", "").strip()
    toxic_inline = os.environ.get(
        "CLEANING_TOXIC_WORDS_INLINE", "").strip()
    sensitive_inline = os.environ.get(
        "CLEANING_SENSITIVE_WORDS_INLINE", "").strip()

    if toxic_file:
        reg.register(
            "toxic",
            FileWordlistProvider(toxic_file, watch=True, kind="toxic-file"),
        )
        logger.info("wordlist_registered kind=toxic source=file path=%s",
                    toxic_file)
    elif toxic_url:
        reg.register(
            "toxic",
            HttpWordlistProvider(toxic_url, kind="toxic-http"),
        )
        logger.info("wordlist_registered kind=toxic source=http url=%s",
                    toxic_url)
    elif toxic_inline:
        words = [w.strip() for w in toxic_inline.split(",") if w.strip()]
        reg.register("toxic", InlineWordlistProvider(words, kind="toxic-inline"))
        logger.info("wordlist_registered kind=toxic source=inline n=%d",
                    len(words))

    if sensitive_file:
        reg.register(
            "sensitive",
            FileWordlistProvider(sensitive_file, watch=True,
                                 kind="sensitive-file"),
        )
        logger.info(
            "wordlist_registered kind=sensitive source=file path=%s",
            sensitive_file,
        )
    elif sensitive_url:
        reg.register(
            "sensitive",
            HttpWordlistProvider(sensitive_url, kind="sensitive-http"),
        )
        logger.info(
            "wordlist_registered kind=sensitive source=http url=%s",
            sensitive_url,
        )
    elif sensitive_inline:
        words = [w.strip() for w in sensitive_inline.split(",") if w.strip()]
        reg.register(
            "sensitive",
            InlineWordlistProvider(words, kind="sensitive-inline"),
        )
        logger.info(
            "wordlist_registered kind=sensitive source=inline n=%d",
            len(words),
        )


__all__ = [
    "WordlistProvider",
    "InlineWordlistProvider",
    "FileWordlistProvider",
    "HttpWordlistProvider",
    "PlaceholderWordlistProvider",
    "ProviderRegistry",
    "get_registry",
    "reset_registry_for_tests",
]