import re

from fastapi import APIRouter, Depends

from app.api.routes_public_market_live import (
    _is_blocked_public_symbol,
    _payload_matches_requested_symbol as _quote_identity_matches_symbol,
)
from app.dependencies import require_channel_access
from app.services.public_ai_tools_service import build_public_ai_tools_payload
from app.services.public_news_service import build_public_news_payload
from app.services.quote_service import (
    empty_quote_payload,
    get_cached_quote_payload,
    get_quote_payload,
    is_usable_quote_payload,
    with_quote_diagnostics,
)
from app.services.symbol_registry import canonical_symbol_aliases, is_ambiguous_crypto_symbol, is_bdr_proxy_payload, is_bdr_symbol
from app.services.symbol_sanitizer import sanitize_market_symbol


router = APIRouter(prefix="/public", tags=["Public Market"])

_CME_FUTURES_PROVIDER_SYMBOLS = {
    "NQ": "NQ=F",
    "MNQ": "MNQ=F",
    "MNO": "MNQ=F",
    "ES": "ES=F",
    "MES": "MES=F",
    "YM": "YM=F",
    "MYM": "MYM=F",
}

_B3_MINI_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").upper().strip()


def _symbol_aliases(symbol: str) -> list[str]:
    raw = _normalize_symbol(symbol)
    if not raw:
        return []

    base = raw[:-3] if raw.endswith(".SA") else raw
    compact = base.replace("-USD", "USD")
    if compact.endswith("USDT"):
        compact = f"{compact[:-4]}USD"

    aliases = [raw, base, compact]
    if compact in _CME_FUTURES_PROVIDER_SYMBOLS:
        aliases.append(_CME_FUTURES_PROVIDER_SYMBOLS[compact])
    if _B3_MINI_FUTURE_RE.match(compact):
        aliases.append(f"{compact}.SA")
    if compact.endswith("USD"):
        aliases.extend([compact.replace("USD", "-USD"), compact.replace("USD", "USDT")])
    if re.match(r"^[A-Z]{4}(3|4|5|6|11)$", base) or re.match(r"^[A-Z]{4,5}34$", base):
        aliases.append(f"{base}.SA")

    seen: set[str] = set()
    return [alias for alias in aliases if alias and not (alias in seen or seen.add(alias))]


def _response_symbol(symbol: str) -> str:
    value = _normalize_symbol(symbol)
    if value.endswith(".SA"):
        value = value[:-3]
    if value.endswith("-USD"):
        value = value.replace("-USD", "USD")
    if value.endswith("USDT"):
        value = f"{value[:-4]}USD"
    return value


def _safe_response_symbol(symbol: str) -> str:
    sanitized = sanitize_market_symbol(symbol, allow_provider_symbols=True)
    if sanitized:
        return _response_symbol(sanitized)
    raw = _normalize_symbol(symbol)
    safe = re.sub(r"[^A-Z0-9._=-]", "", raw)[:32]
    return safe or "INVALID_SYMBOL"


def _has_quote_value(payload: dict | None) -> bool:
    return is_usable_quote_payload(payload, allow_stale=False)


def _resolve_query_symbol(symbol: str) -> str:
    normalized_symbol = _normalize_symbol(symbol)
    candidates = [normalized_symbol, *canonical_symbol_aliases(symbol), symbol]
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = _normalize_symbol(candidate)
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        sanitized = sanitize_market_symbol(normalized_candidate, allow_provider_symbols=True)
        if sanitized:
            return sanitized
    return ""


@router.get("/market/quote/{symbol}", dependencies=[Depends(require_channel_access("web"))])
def public_quote(symbol: str, refresh: str | None = None):
    if is_ambiguous_crypto_symbol(symbol):
        return empty_quote_payload(_safe_response_symbol(symbol), quote_status="ambiguous_symbol", reason="missing_quote_asset")
    sanitized_symbol = _resolve_query_symbol(symbol)
    if not sanitized_symbol:
        return empty_quote_payload(_safe_response_symbol(symbol), quote_status="invalid_symbol")
    query_symbol = _normalize_symbol(sanitized_symbol)
    response_symbol = _response_symbol(sanitized_symbol)
    if _is_blocked_public_symbol(query_symbol):
        return empty_quote_payload(response_symbol, quote_status="blocked_symbol", reason="blocked_symbol")
    aliases = []
    seen_aliases: set[str] = set()
    for alias in [query_symbol, sanitized_symbol, *canonical_symbol_aliases(query_symbol), *_symbol_aliases(query_symbol)]:
        normalized_alias = _normalize_symbol(alias)
        if normalized_alias and normalized_alias not in seen_aliases:
            seen_aliases.add(normalized_alias)
            aliases.append(normalized_alias)
    for alias in aliases:
        payload = get_cached_quote_payload(alias)
        if not payload:
            continue
        if is_bdr_symbol(query_symbol) and is_bdr_proxy_payload(payload):
            continue
        if not _quote_identity_matches_symbol(payload, query_symbol, require_identity=True):
            continue
        normalized_payload = {**payload, "symbol": response_symbol}
        if _has_quote_value(payload):
            return with_quote_diagnostics(normalized_payload) or normalized_payload
    return empty_quote_payload(response_symbol)


@router.get("/market/news/{symbol}")
def public_news(symbol: str, limit: int = 6, refresh: str | None = None, locale: str = "pt-BR"):
    kwargs = {"limit": limit, "source": "public", "allow_fetch": False, "schedule_warmup": True}
    if locale != "pt-BR":
        kwargs["locale"] = locale
    return build_public_news_payload(_normalize_symbol(symbol), **kwargs)


@router.get("/market/ai-tools")
def public_ai_tools(symbol: str | None = None, tool: str | None = None, timeframe: str | None = None):
    return build_public_ai_tools_payload(symbol=symbol, tool=tool, timeframe=timeframe)
