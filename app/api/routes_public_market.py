import re

from fastapi import APIRouter

from app.services.public_ai_tools_service import build_public_ai_tools_payload
from app.services.public_news_service import build_public_news_payload
from app.services.quote_service import empty_quote_payload, get_cached_quote_payload, is_usable_quote_payload


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


def _has_quote_value(payload: dict | None) -> bool:
    return is_usable_quote_payload(payload)


@router.get("/market/quote/{symbol}")
def public_quote(symbol: str):
    query_symbol = _normalize_symbol(symbol)
    response_symbol = _response_symbol(symbol)
    for alias in _symbol_aliases(query_symbol):
        payload = get_cached_quote_payload(alias)
        if not payload:
            continue
        normalized_payload = {**payload, "symbol": response_symbol}
        if _has_quote_value(payload):
            return normalized_payload
    return empty_quote_payload(response_symbol)


@router.get("/market/news/{symbol}")
def public_news(symbol: str, limit: int = 6):
    return build_public_news_payload(_normalize_symbol(symbol), limit=limit, source="public", allow_fetch=False)


@router.get("/market/ai-tools")
def public_ai_tools():
    return build_public_ai_tools_payload()
