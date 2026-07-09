# ==========================================================
# STOCKNEWSBR — MISSION 31B.1
# Identity Guard: anti-impersonation, reserved names, official links
# ==========================================================
#
# Single source of truth for deciding whether a display_name / username
# proposed by a REGULAR user is trying to impersonate the official
# StockNewsBR account, the official bot, support, admin, or the system.
#
# The check is normalization-first so that casing, spacing, underscores,
# hyphens, dots, accents, punctuation, invisible characters, verified
# emojis, simple homoglyphs and leet-speak cannot be used to smuggle a
# reserved identity past the gate.
#
# It never grants a badge — it can only BLOCK. Official/bot/verified state
# lives exclusively in trusted backend columns (see official_identity_service).

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


# ----------------------------------------------------------
# Official link whitelist (Mission 31B.1 §7)
# ----------------------------------------------------------
# Only these exact hostnames are considered official. Sub-domains,
# look-alikes and misleading substrings are rejected by hostname parse.
OFFICIAL_HOSTNAMES = frozenset(
    {
        "stocknewsbr.com",
        "www.stocknewsbr.com",
    }
)


# ----------------------------------------------------------
# Reserved identities (Mission 31B.1 §3)
# ----------------------------------------------------------
# Brand cores: any regular identity whose compact form CONTAINS one of these
# is treated as impersonation of the brand.
_BRAND_CORES = (
    "stocknewsbr",
    "stocknews",
    "snbr",
)

# Reserved role/system words: blocked when they appear as the identity
# (compact match or as a normalized standalone token).
_RESERVED_WORDS = frozenset(
    {
        "stocknewsbroficial",
        "oficialstocknewsbr",
        "stocknewsbot",
        "stocknewsbrbot",
        "admin",
        "administrador",
        "suporte",
        "suportestocknewsbr",
        "bot",
        "system",
        "sistema",
        "alerts",
        "alertas",
        "help",
        "verified",
        "verificado",
        "oficial",
        "official",
        "representante",
        "fundador",
        "equipe",
        "staff",
        "moderador",
        "owner",
        "ceo",
        "cto",
        "contaoficial",
        "botoficial",
        "adminoficial",
        "suporteoficial",
    }
)


# ----------------------------------------------------------
# Normalization primitives
# ----------------------------------------------------------
# Unicode categories that carry no visible glyph (format/control/surrogate/
# private-use/unassigned). Whitespace stays as a separator for token checks.
_INVISIBLE_CATEGORY_PREFIXES = ("C",)

# Simple homoglyph fold: common Cyrillic/Greek/full-width look-alikes -> latin.
_HOMOGLYPHS = {
    # Cyrillic
    "а": "a",  # а
    "е": "e",  # е
    "о": "o",  # о
    "р": "p",  # р
    "с": "c",  # с
    "у": "y",  # у
    "х": "x",  # х
    "А": "a",
    "Е": "e",
    "О": "o",
    "Р": "p",
    "С": "c",
    "Т": "t",  # Т
    "т": "t",  # т
    "В": "b",  # В
    "Н": "h",  # Н
    "М": "m",  # М
    "К": "k",  # К
    # Greek
    "ο": "o",  # ο
    "α": "a",  # α
    "ρ": "p",  # ρ
    "Ι": "i",  # Ι
    # Full-width digits/letters handled by NFKD below.
}

# Leet / punctuation-as-letter fold.
_LEET = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "8": "b",
    "9": "g",
    "@": "a",
    "$": "s",
    "!": "i",
    "|": "i",
}


def _strip_invisible(value: str) -> str:
    out: list[str] = []
    for char in str(value or ""):
        if char.isspace():
            out.append(" ")
            continue
        category = unicodedata.category(char)
        if category.startswith(_INVISIBLE_CATEGORY_PREFIXES):
            continue
        out.append(char)
    return "".join(out)


def _fold_homoglyphs(value: str) -> str:
    return "".join(_HOMOGLYPHS.get(char, char) for char in value)


def _remove_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_identity(value: str | None) -> str:
    """Compact, attack-resistant form: lowercase alnum only.

    Pipeline: strip invisible -> fold homoglyphs -> NFKD accent strip ->
    lowercase -> leet fold -> keep [a-z0-9] only. Two identities that a human
    would read as "the same" collapse to the same string here.
    """
    text = _strip_invisible(str(value or ""))
    text = _fold_homoglyphs(text)
    text = _remove_accents(text).lower()
    text = "".join(_LEET.get(char, char) for char in text)
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_tokens(value: str | None) -> list[str]:
    """Normalized whitespace/punct-separated tokens (for standalone matches)."""
    text = _strip_invisible(str(value or ""))
    text = _fold_homoglyphs(text)
    text = _remove_accents(text)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = text.lower()
    text = "".join(_LEET.get(char, char) if not char.isspace() else " " for char in text)
    return [tok for tok in re.split(r"[^a-z0-9]+", text) if tok]


# ----------------------------------------------------------
# Impersonation decision (Mission 31B.1 §3, §5)
# ----------------------------------------------------------
def is_reserved_identity(value: str | None) -> bool:
    """True if `value` normalizes to a reserved/official/brand identity."""
    compact = normalize_identity(value)
    if not compact:
        return False

    # Brand impersonation: compact contains the brand core anywhere.
    for core in _BRAND_CORES:
        if core in compact:
            return True

    # Reserved word as the whole compact identity.
    if compact in _RESERVED_WORDS:
        return True

    # Reserved role words appearing as standalone normalized tokens
    # (e.g. "Equipe Suporte", "Conta Oficial", "Bot").
    tokens = normalize_tokens(value)
    token_set = set(tokens)
    if token_set & _RESERVED_WORDS:
        return True
    # Joined adjacent tokens (e.g. "conta oficial" -> "contaoficial").
    joined = "".join(tokens)
    if joined in _RESERVED_WORDS:
        return True

    return False


def check_impersonation(
    display_name: str | None = None,
    username: str | None = None,
    *,
    is_privileged: bool = False,
) -> str | None:
    """Return a block reason if a NON-privileged user proposes a reserved
    identity, else None. Privileged (official/bot/admin) identities set by
    the backend are exempt.
    """
    if is_privileged:
        return None

    if display_name is not None and is_reserved_identity(display_name):
        return "impersonation_display_name_reserved"

    if username is not None and is_reserved_identity(username):
        return "impersonation_username_reserved"

    return None


# ----------------------------------------------------------
# Official link validation (Mission 31B.1 §7)
# ----------------------------------------------------------
def _hostname_of(url: str | None) -> str | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").strip().lower()
    return host or None


def is_official_link(url: str | None) -> bool:
    """True only if the URL's real hostname is an exact official host.

    Blocks misleading substrings ("fake.com/stocknewsbr.com"), malicious
    sub-domains ("stocknewsbr.com.fake.com"), look-alikes and encoded tricks
    because the decision is made purely on the parsed hostname.
    """
    host = _hostname_of(url)
    if host is None:
        return False
    return host in OFFICIAL_HOSTNAMES
