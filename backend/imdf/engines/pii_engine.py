"""
P1-A2-W1: PII Auto-Detection Engine
======================================
Auto-detects Personally Identifiable Information (PII) in free-form text and
structured fields. Supports:

  * Regex-based detection for high-precision PII (email, phone, ID, credit
    card, IP, address, passport, bank card)
  * Field-name heuristics (e.g. column 'email' is PII by definition)
  * Luhn checksum validation for credit card numbers
  * Chinese ID card (18-digit GB 11643-1999) checksum validation
  * Optional spaCy NER for person names (graceful fallback if unavailable)
  * 4 redaction strategies: mask, replace, hash, remove

The engine is pure-Python, dependency-free at the core, and stateless at the
class level. The PII_PATTERN_TABLE can be extended at runtime.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── PII types and labels ────────────────────────────────────────────────────
PII_TYPE_EMAIL = "email"
PII_TYPE_PHONE_CN = "phone_cn"
PII_TYPE_PHONE_INTL = "phone_intl"
PII_TYPE_ID_CARD_CN = "id_card_cn"
PII_TYPE_SSN_US = "ssn_us"
PII_TYPE_CREDIT_CARD = "credit_card"
PII_TYPE_IPV4 = "ipv4"
PII_TYPE_IPV6 = "ipv6"
PII_TYPE_ADDRESS_CN = "address_cn"
PII_TYPE_PASSPORT_CN = "passport_cn"
PII_TYPE_BANK_CARD_CN = "bank_card_cn"
PII_TYPE_NAME = "name"
PII_TYPE_GENERIC = "generic_pii"

PII_LABELS = {
    PII_TYPE_EMAIL: "Email Address",
    PII_TYPE_PHONE_CN: "Chinese Mobile Phone",
    PII_TYPE_PHONE_INTL: "International Phone Number",
    PII_TYPE_ID_CARD_CN: "Chinese National ID",
    PII_TYPE_SSN_US: "US Social Security Number",
    PII_TYPE_CREDIT_CARD: "Credit Card Number",
    PII_TYPE_IPV4: "IPv4 Address",
    PII_TYPE_IPV6: "IPv6 Address",
    PII_TYPE_ADDRESS_CN: "Chinese Address",
    PII_TYPE_PASSPORT_CN: "Chinese Passport",
    PII_TYPE_BANK_CARD_CN: "Chinese Bank Card",
    PII_TYPE_NAME: "Person Name (NER)",
    PII_TYPE_GENERIC: "Generic PII",
}


# ── Result dataclass ────────────────────────────────────────────────────────
@dataclass
class PIIMatch:
    """A single PII match in a text or field."""
    type: str
    label: str
    value: str
    start: int
    end: int
    confidence: float
    strategy: str = "regex"  # regex | ml | heuristic

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Validators ──────────────────────────────────────────────────────────────
def _luhn_check(num: str) -> bool:
    """Luhn checksum for credit card / IMEI etc.

    Returns True if the digit string passes Luhn validation.
    """
    digits = [int(c) for c in re.sub(r"\D", "", num)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = (len(digits) - 2) % 2
    for i, d in enumerate(digits[:-1]):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    checksum += digits[-1]
    return checksum % 10 == 0


def _verify_cn_id_checksum(id_str: str) -> bool:
    """Verify Chinese 18-digit ID card checksum (GB 11643-1999)."""
    if len(id_str) != 18:
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_chars = "10X98765432"
    try:
        total = sum(int(id_str[i]) * weights[i] for i in range(17))
        return check_chars[total % 11] == id_str[17].upper()
    except (ValueError, IndexError):
        return False


# ── Pattern table ───────────────────────────────────────────────────────────
def _default_pattern_table() -> List[Tuple[str, re.Pattern, float]]:
    """Return the default PII regex pattern table.

    Each entry: (pii_type, compiled regex, base confidence).
    Order matters: more specific patterns first (CN ID, then phone, then email).
    """
    return [
        # Chinese ID card (18 digits, with checksum validation done after match)
        (PII_TYPE_ID_CARD_CN, re.compile(
            r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"
        ), 0.98),
        # Chinese mobile phone
        (PII_TYPE_PHONE_CN, re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), 0.95),
        # International phone (E.164: +countrycode followed by 6-14 digits)
        (PII_TYPE_PHONE_INTL, re.compile(
            r"(?<!\d)\+(?:[1-9]\d{0,2})[\s\-]?\d{4,14}(?!\d)"
        ), 0.85),
        # Email
        (PII_TYPE_EMAIL, re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
        ), 0.97),
        # IPv4
        (PII_TYPE_IPV4, re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ), 0.92),
        # IPv6
        (PII_TYPE_IPV6, re.compile(
            r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|"
            r"\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b|"
            r"\b:(?::[0-9a-fA-F]{1,4}){1,7}\b"
        ), 0.90),
        # SSN (US): 3-2-4 with hyphens
        (PII_TYPE_SSN_US, re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0.95),
        # Credit card: 13-19 digits with optional spaces/dashes (Luhn checked post-match)
        (PII_TYPE_CREDIT_CARD, re.compile(
            r"\b(?:\d[ \-]?){12,18}\d\b"
        ), 0.85),
        # Chinese passport
        (PII_TYPE_PASSPORT_CN, re.compile(r"\b[EG]\d{8}\b"), 0.90),
        # Chinese bank card (16-19 digits, starting with major network BIN)
        (PII_TYPE_BANK_CARD_CN, re.compile(
            r"\b(?:62|60|58|55|52|53|54|51|50|49|48|47|46|45|44|43|42|41)\d{14,17}\b"
        ), 0.85),
        # Chinese address keyword heuristic
        # Require either a province/city/district prefix (strong location) OR
        # a long-enough sequence (>=8 Chinese chars) of location-like keywords.
        # Avoids false positives like "身份证号" (which contains "号").
        (PII_TYPE_ADDRESS_CN, re.compile(
            r"(?:"
            r"(?:[\u4e00-\u9fff]{2,6}?(?:省|市|自治区|特别行政区))"
            r"[\u4e00-\u9fff\d]{0,20}?(?:市|区|县|镇|村|路|街|巷|号|楼|栋|室)"
            r"[\u4e00-\u9fff\d号弄室栋层]*?"
            r"|"
            r"[\u4e00-\u9fff]{0,4}?(?:区|县)[\u4e00-\u9fff]{0,4}?(?:路|街|巷|镇)[\u4e00-\u9fff\d]{0,15}?(?:号|楼|栋)"
            r"[\u4e00-\u9fff\d号弄室栋层]*?"
            r")"
            r"(?=[，。,\.\s]|$)"
        ), 0.70),
    ]


# ── Field-name heuristic table ──────────────────────────────────────────────
FIELD_HEURISTIC_PII: Dict[str, str] = {
    # Common column / form names that almost always carry PII
    "email": PII_TYPE_EMAIL,
    "e_mail": PII_TYPE_EMAIL,
    "mail": PII_TYPE_EMAIL,
    "phone": PII_TYPE_PHONE_CN,
    "phone_number": PII_TYPE_PHONE_CN,
    "mobile": PII_TYPE_PHONE_CN,
    "tel": PII_TYPE_PHONE_CN,
    "telephone": PII_TYPE_PHONE_CN,
    "id_card": PII_TYPE_ID_CARD_CN,
    "id_card_no": PII_TYPE_ID_CARD_CN,
    "id_number": PII_TYPE_ID_CARD_CN,
    "national_id": PII_TYPE_ID_CARD_CN,
    "ssn": PII_TYPE_SSN_US,
    "social_security": PII_TYPE_SSN_US,
    "credit_card": PII_TYPE_CREDIT_CARD,
    "cc_number": PII_TYPE_CREDIT_CARD,
    "card_number": PII_TYPE_CREDIT_CARD,
    "bank_card": PII_TYPE_BANK_CARD_CN,
    "passport": PII_TYPE_PASSPORT_CN,
    "ip": PII_TYPE_IPV4,
    "ip_address": PII_TYPE_IPV4,
    "user_ip": PII_TYPE_IPV4,
    "client_ip": PII_TYPE_IPV4,
    "name": PII_TYPE_NAME,
    "full_name": PII_TYPE_NAME,
    "real_name": PII_TYPE_NAME,
    "username": PII_TYPE_NAME,
    "first_name": PII_TYPE_NAME,
    "last_name": PII_TYPE_NAME,
    "address": PII_TYPE_ADDRESS_CN,
    "home_address": PII_TYPE_ADDRESS_CN,
    "shipping_address": PII_TYPE_ADDRESS_CN,
    "billing_address": PII_TYPE_ADDRESS_CN,
}


# ── ML (spaCy) loader — optional, graceful fallback ────────────────────────
def _try_load_spacy():
    """Try to load spaCy Chinese NER model. Returns None if unavailable."""
    try:
        import spacy  # type: ignore

        # Prefer the small Chinese model; if not present, try en core
        for model_name in ("zh_core_web_sm", "en_core_web_sm"):
            try:
                return spacy.load(model_name), model_name
            except Exception:
                continue
        return None, None
    except Exception:
        return None, None


# ── The Engine ──────────────────────────────────────────────────────────────
class PIIEngine:
    """PII auto-detection engine.

    Usage:
        engine = PIIEngine(use_ml=False)
        matches = engine.detect("Email me at alice@example.com")
        for m in matches:
            print(m.type, m.value, m.confidence)
        clean = engine.redact("My email is alice@example.com", strategy="mask")
    """

    def __init__(self, use_ml: bool = False, pattern_table: Optional[List[Tuple[str, re.Pattern, float]]] = None):
        self.regex_patterns: List[Tuple[str, re.Pattern, float]] = (
            pattern_table if pattern_table is not None else _default_pattern_table()
        )
        self.use_ml = use_ml
        self.ml_model = None
        self.ml_model_name: Optional[str] = None
        if use_ml:
            nlp, name = _try_load_spacy()
            if nlp is not None:
                self.ml_model = nlp
                self.ml_model_name = name
                logger.info(f"PIIEngine: loaded spaCy model {name}")
            else:
                logger.warning(
                    "PIIEngine: use_ml=True requested but no spaCy model available. "
                    "Install with: python -m spacy download zh_core_web_sm"
                )

    # ── Detection ───────────────────────────────────────────────────────────
    def detect(
        self,
        text: str,
        types: Optional[Iterable[str]] = None,
        min_confidence: float = 0.0,
    ) -> List[PIIMatch]:
        """Detect PII in text.

        Args:
            text: Free-form text (UTF-8 string).
            types: Optional iterable of PII types to filter on.
            min_confidence: Drop matches below this confidence.

        Returns:
            List of PIIMatch sorted by start offset.
        """
        if not text:
            return []
        filter_set = set(types) if types else None
        results: List[PIIMatch] = []
        for pii_type, regex, base_conf in self.regex_patterns:
            if filter_set and pii_type not in filter_set:
                continue
            for m in regex.finditer(text):
                value = m.group()
                # Post-match validation
                if pii_type == PII_TYPE_ID_CARD_CN:
                    if not _verify_cn_id_checksum(value):
                        continue
                    conf = base_conf
                elif pii_type == PII_TYPE_CREDIT_CARD:
                    if not _luhn_check(value):
                        continue
                    conf = base_conf
                elif pii_type == PII_TYPE_BANK_CARD_CN:
                    if not _luhn_check(value):
                        continue
                    conf = base_conf
                elif pii_type == PII_TYPE_ADDRESS_CN:
                    # Address heuristic is noisy; require at least 4 Chinese chars
                    stripped = re.sub(r"[\u4e00-\u9fff]", "", value)
                    if len(stripped) > len(value) * 0.7:
                        continue
                    conf = base_conf
                else:
                    conf = base_conf
                if conf < min_confidence:
                    continue
                results.append(
                    PIIMatch(
                        type=pii_type,
                        label=PII_LABELS.get(pii_type, pii_type),
                        value=value,
                        start=m.start(),
                        end=m.end(),
                        confidence=round(conf, 3),
                        strategy="regex",
                    )
                )

        # ML detection: person names via spaCy
        if self.ml_model is not None and (filter_set is None or PII_TYPE_NAME in filter_set):
            try:
                doc = self.ml_model(text[:100000])  # cap to avoid huge inputs
                for ent in doc.ents:
                    if ent.label_ in ("PERSON", "PER"):
                        results.append(
                            PIIMatch(
                                type=PII_TYPE_NAME,
                                label=PII_LABELS[PII_TYPE_NAME],
                                value=ent.text,
                                start=ent.start_char,
                                end=ent.end_char,
                                confidence=0.80,
                                strategy="ml",
                            )
                        )
            except Exception as e:
                logger.debug(f"spaCy NER failed: {e}")

        # Sort by start, then by confidence desc
        results.sort(key=lambda m: (m.start, -m.confidence))
        return results

    # ── Field heuristic ─────────────────────────────────────────────────────
    def scan_field(self, field_name: str, value: Any) -> Dict[str, Any]:
        """Scan a single structured field for PII.

        Combines:
          * field_name heuristic (column name → pii type)
          * value regex scan (with type filter from heuristic)

        Returns:
            {
                'is_pii': bool,
                'type': str | None,
                'action': 'redact' | 'warn' | 'block' | 'allow',
                'matches': List[PIIMatch],
                'field': str,
            }
        """
        # Field-name heuristic
        norm_name = (field_name or "").strip().lower().replace("-", "_")
        inferred_type = FIELD_HEURISTIC_PII.get(norm_name)

        # Value-based detection
        matches: List[PIIMatch] = []
        if isinstance(value, str) and value:
            filter_types: Optional[List[str]] = [inferred_type] if inferred_type else None
            matches = self.detect(value, types=filter_types)

        is_pii = bool(inferred_type) or len(matches) > 0
        if not is_pii:
            return {
                "is_pii": False,
                "type": None,
                "action": "allow",
                "matches": [],
                "field": field_name,
            }

        # Determine action
        pii_type = inferred_type or (matches[0].type if matches else PII_TYPE_GENERIC)
        # High-sensitivity PII → block / redact
        high_sens = {
            PII_TYPE_ID_CARD_CN, PII_TYPE_CREDIT_CARD, PII_TYPE_BANK_CARD_CN,
            PII_TYPE_SSN_US, PII_TYPE_PASSPORT_CN,
        }
        if pii_type in high_sens:
            action = "block"
        elif pii_type in {PII_TYPE_EMAIL, PII_TYPE_PHONE_CN, PII_TYPE_PHONE_INTL}:
            action = "redact"
        else:
            action = "warn"

        return {
            "is_pii": True,
            "type": pii_type,
            "action": action,
            "matches": [m.to_dict() for m in matches],
            "field": field_name,
        }

    # ── Redaction ───────────────────────────────────────────────────────────
    def redact(
        self,
        text: str,
        strategy: str = "mask",
        types: Optional[Iterable[str]] = None,
        mask_char: str = "*",
    ) -> str:
        """Redact PII from text.

        Strategies:
          * mask      — replace with same-length mask characters (default: *)
          * replace   — partially mask (e.g. alice@example.com → al***@e*****.com)
          * hash      — replace with [HASH:12-hex] tag
          * remove    — replace with empty string (whitespace normalized)
        """
        if not text:
            return text
        matches = self.detect(text, types=types)
        if not matches:
            return text

        if strategy == "remove":
            # Remove + collapse spaces
            out = []
            last = 0
            for m in sorted(matches, key=lambda x: x.start):
                out.append(text[last:m.start])
                last = m.end
            out.append(text[last:])
            result = "".join(out)
            return re.sub(r"\s{2,}", " ", result).strip()

        if strategy == "hash":
            return self._apply_redaction(text, matches, "hash", mask_char)

        if strategy == "replace":
            return self._apply_redaction(text, matches, "replace", mask_char)

        # Default: full mask
        return self._apply_redaction(text, matches, "mask", mask_char)

    def _apply_redaction(
        self,
        text: str,
        matches: List[PIIMatch],
        strategy: str,
        mask_char: str,
    ) -> str:
        # Process from end to start so offsets remain valid
        out = text
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            replacement = self._format_replacement(m, strategy, mask_char)
            out = out[:m.start] + replacement + out[m.end:]
        return out

    def _format_replacement(self, m: PIIMatch, strategy: str, mask_char: str) -> str:
        value = m.value
        if strategy == "hash":
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
            return f"[HASH:{digest}]"
        if strategy == "replace":
            return self._partial_mask(m.type, value, mask_char)
        # mask
        return mask_char * len(value)

    def _partial_mask(self, pii_type: str, value: str, mask_char: str) -> str:
        if pii_type == PII_TYPE_EMAIL and "@" in value:
            local, _, domain = value.partition("@")
            head = local[:1] if local else ""
            mid = mask_char * max(1, len(local) - 1)
            dhead = domain[:1] if domain else ""
            dmid = mask_char * max(1, len(domain) - 1)
            return f"{head}{mid}@{dhead}{dmid}"
        if pii_type in (PII_TYPE_PHONE_CN, PII_TYPE_BANK_CARD_CN, PII_TYPE_CREDIT_CARD):
            if len(value) >= 7:
                return value[:3] + mask_char * (len(value) - 7) + value[-4:]
            return mask_char * len(value)
        if pii_type == PII_TYPE_ID_CARD_CN and len(value) == 18:
            return value[:6] + mask_char * 8 + value[-4:]
        if pii_type == PII_TYPE_SSN_US:
            return f"***-**-{value[-4:]}"
        if pii_type == PII_TYPE_PASSPORT_CN:
            return value[:1] + mask_char * 7 + value[-1:]
        if pii_type == PII_TYPE_IPV4:
            parts = value.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{mask_char * len(parts[2])}.{mask_char * len(parts[3])}"
        if pii_type == PII_TYPE_NAME and len(value) >= 2:
            return value[0] + mask_char * (len(value) - 1)
        # Generic partial mask
        if len(value) <= 2:
            return mask_char * len(value)
        return value[0] + mask_char * (len(value) - 2) + value[-1]

    # ── Utility ─────────────────────────────────────────────────────────────
    def supported_types(self) -> List[str]:
        """Return the list of PII types this engine can detect."""
        base = [t for t, _, _ in self.regex_patterns]
        if self.ml_model is not None:
            base.append(PII_TYPE_NAME)
        return sorted(set(base))

    def normalize_text(self, text: str) -> str:
        """NFKC-normalize Unicode (handles full-width digits, etc.)."""
        return unicodedata.normalize("NFKC", text)
