from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable
from urllib.parse import unquote


@dataclass(frozen=True)
class SocialGuardianDecision:
    allowed: bool
    reason: str
    category: str = "safe"
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


class SocialGuardian:
    """Single social-safety gate used before any community content is persisted."""

    TRUST_MIN = 0
    TRUST_MAX = 100
    TRUST_START = 70
    APPROVED_POST_DELTA = 2
    APPROVED_INTERACTION_DELTA = 1
    REPORT_DELTA = -10
    REMOVED_POST_DELTA = -15

    REPORT_REASONS = {
        "spam": "Spam",
        "golpe": "Golpe",
        "manipulacao": "Manipulacao",
        "ofensivo": "Ofensivo",
        "fake_news": "Fake News",
        "outro": "Outro",
    }

    _LINK_PATTERNS = (
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\bw\s*\.\s*w\s*\.\s*w\b", re.IGNORECASE),
        re.compile(r"\bwww\b", re.IGNORECASE),
        re.compile(
            r"(?:^|[\s/:])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\s*\.\s*"
            r"(?:com(?:\s*\.\s*br)?|net|org|gov|io|ai|xyz|co(?:\s*\.\s*uk)?)\b",
            re.IGNORECASE,
        ),
    )
    _EMAIL_PATTERNS = (
        re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.IGNORECASE),
        re.compile(r"\b(?:gmail|hotmail|outlook|yahoo|icloud|proton)\b", re.IGNORECASE),
    )
    _PHONE_PATTERNS = (
        re.compile(r"\+55\b", re.IGNORECASE),
        re.compile(r"\(\s*\d{2}\s*\)", re.IGNORECASE),
        re.compile(r"\b\d{2}\s?\d{4,5}[-\s]?\d{4}\b", re.IGNORECASE),
        re.compile(r"\b(?:whatsapp|telegram)\b", re.IGNORECASE),
    )
    _BETTING_TERMS = (
        "bet",
        "betting",
        "casino",
        "cassino",
        "aposta",
        "apostar",
        "tigrinho",
        "blaze",
        "stake",
        "betano",
        "superbet",
        "bet365",
        "brazino",
        "esportes da sorte",
        "pixbet",
    )
    _BETTING_PATTERN = re.compile(
        r"\b(?:"
        + "|".join(re.escape(term).replace(r"\ ", r"\s+") for term in _BETTING_TERMS)
        + r")\b",
        re.IGNORECASE,
    )

    @classmethod
    def normalize_text(cls, value: str | None) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def validate_content(cls, text: str | None, *, content_type: str = "post") -> SocialGuardianDecision:
        del content_type
        normalized = cls.normalize_text(text)

        if not normalized:
            return SocialGuardianDecision(True, "allowed")

        for pattern in cls._LINK_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return SocialGuardianDecision(False, "link_detected", "link", (match.group(0).strip(),))

        for pattern in cls._EMAIL_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return SocialGuardianDecision(False, "email_detected", "email", (match.group(0).strip(),))

        for pattern in cls._PHONE_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return SocialGuardianDecision(False, "phone_detected", "phone", (match.group(0).strip(),))

        match = cls._BETTING_PATTERN.search(normalized)
        if match:
            return SocialGuardianDecision(False, "betting_detected", "betting", (match.group(0).strip(),))

        return SocialGuardianDecision(True, "allowed")

    @classmethod
    def validate_attachment_url(cls, image_url: str | None) -> SocialGuardianDecision:
        value = str(image_url or "").strip()
        if not value:
            return SocialGuardianDecision(True, "allowed")
        if cls._is_safe_media_path(value):
            return SocialGuardianDecision(True, "allowed")
        normalized = unquote(value).replace("\\", "/").lstrip("/")
        if normalized.startswith("media/"):
            return SocialGuardianDecision(False, "attachment_path_traversal", "attachment", (value,))
        return cls.validate_content(value, content_type="attachment")

    @classmethod
    def _is_safe_media_path(cls, value: str) -> bool:
        try:
            normalized = unquote(str(value or "").strip()).replace("\\", "/")
            if normalized.startswith("/"):
                normalized = normalized[1:]
            path = PurePosixPath(normalized)
        except Exception:
            return False

        parts = path.parts
        if len(parts) < 2 or parts[0] != "media":
            return False
        return all(part not in {"", ".", ".."} for part in parts)

    @classmethod
    def normalize_report_reason(cls, reason: str | None) -> str:
        normalized = cls.normalize_text(reason).replace(" ", "_")
        aliases = {
            "manipulacao": "manipulacao",
            "manipulacao_de_mercado": "manipulacao",
            "manipulation": "manipulacao",
            "ofensivo": "ofensivo",
            "offensive": "ofensivo",
            "fake_news": "fake_news",
            "fakenews": "fake_news",
            "golpe": "golpe",
            "scam": "golpe",
            "spam": "spam",
            "other": "outro",
            "outro": "outro",
        }
        return aliases.get(normalized, "outro")

    @classmethod
    def trust_label(cls, score: int | float | None) -> str:
        numeric = cls.clamp_score(score)
        if numeric >= 75:
            return "Verde"
        if numeric >= 45:
            return "Amarelo"
        return "Vermelho"

    @classmethod
    def clamp_score(cls, score: int | float | None) -> int:
        try:
            numeric = int(round(float(score)))
        except Exception:
            numeric = cls.TRUST_START
        return max(cls.TRUST_MIN, min(cls.TRUST_MAX, numeric))

    @classmethod
    def approved_delta(cls, content_type: str) -> int:
        return cls.APPROVED_POST_DELTA if content_type == "post" else cls.APPROVED_INTERACTION_DELTA

    @classmethod
    def blocked_terms(cls) -> dict[str, Iterable[str]]:
        return {
            "links": ("http", "https", "www", "w.w.w", ".com", ".com.br", ".net", ".org", ".gov", ".io", ".ai", ".xyz", ".co", ".co.uk"),
            "emails": ("@", "gmail", "hotmail", "outlook", "yahoo", "icloud", "proton"),
            "phones": ("+55", "(16)", "WhatsApp", "Telegram"),
            "bets": cls._BETTING_TERMS,
        }
