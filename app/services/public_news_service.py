import re
from typing import Any

from app.services.news_service import (
    get_cached_symbol_news,
    get_news_cache_info,
    get_news_cached_report,
    get_symbol_news,
)

_SYMBOL_NEWS_ALIASES = {
    "F": ("ford", "ford motor", "ford motor company"),
}


def _normalize_symbol(symbol: str | None) -> str:
    value = str(symbol or "").upper().strip()
    if value.endswith(".SA"):
        value = value[:-3]
    if value.endswith("-USD"):
        value = value.replace("-USD", "USD")
    if value.endswith("USDT"):
        value = f"{value[:-4]}USD"
    return value


def _news_item_symbol(item: dict[str, Any]) -> str:
    return _normalize_symbol(str(item.get("ticker") or item.get("symbol") or ""))


def _item_belongs_to_symbol(item: dict[str, Any], symbol: str) -> bool:
    normalized = _normalize_symbol(symbol)
    item_symbol = _news_item_symbol(item)
    if item_symbol and item_symbol == normalized:
        return True

    related = item.get("related_tickers") or item.get("relatedTickers") or item.get("entities") or []
    if isinstance(related, list):
        normalized_related: set[str] = set()
        for value in related:
            if isinstance(value, dict):
                normalized_related.add(_normalize_symbol(value.get("ticker") or value.get("symbol") or value.get("name")))
            else:
                normalized_related.add(_normalize_symbol(str(value)))
        if normalized in normalized_related:
            return True

    aliases = _SYMBOL_NEWS_ALIASES.get(normalized) or ()
    if aliases:
        parts = [
            item.get("title"),
            item.get("summary"),
            item.get("card_summary"),
            item.get("trader_takeaway"),
            item.get("why_it_matters"),
            item.get("market_context"),
        ]
        if isinstance(related, list):
            parts.extend(value.get("name") if isinstance(value, dict) else value for value in related)
        text = _normalize_news_text(" ".join(str(part or "") for part in parts))
        if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases):
            return True

    return False


def _normalize_news_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\u00c0-\u024f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _news_dedupe_key(item: dict[str, Any]) -> str:
    story_key = _normalize_news_text(item.get("story_key"))
    if story_key:
        return f"story:{story_key}"

    url = str(item.get("url") or "").strip().lower()
    if url:
        return f"url:{url.split('#', 1)[0].split('?', 1)[0].rstrip('/')}"

    for field in ("title", "trader_takeaway", "card_summary", "summary"):
        text = _normalize_news_text(item.get(field))
        if text:
            return f"text:{text[:180]}"

    return f"id:{item.get('id') or id(item)}"


def _dedupe_news_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    unique_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _news_dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
        if len(unique_items) >= limit:
            break
    return unique_items


def _build_news_state(symbol: str, items: list[dict[str, Any]], cache: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    cache_status = str(cache.get("status") or "cold")
    provider_status = str(cache.get("provider_status") or "not_checked")
    provider_error = cache.get("provider_error")

    if items:
        status = "ok"
        message = f"News filtradas e validadas para {symbol}."
        if cache_status == "stale_fallback":
            status = "stale_fallback"
            message = f"Usando noticia antiga de {symbol}; provider atual nao entregou item novo."
    else:
        status = "empty"
        message = f"Sem noticia real para {symbol} agora; nenhuma noticia de outro ticker foi reaproveitada."
        if provider_error:
            status = "provider_error"
            message = f"Provider de news falhou para {symbol}: {provider_error}."
        elif provider_status in {"empty", "no_news", "error"}:
            message = f"Provider retornou {provider_status} para {symbol}; tela deve mostrar estado vazio explicito."

    return {
        "symbol": symbol,
        "status": status,
        "message": message,
        "cache_status": cache_status,
        "provider": cache.get("provider") or "yfinance",
        "provider_status": provider_status,
        "provider_error": provider_error,
        "report_status": report.get("status") or ("ok" if items else "empty"),
        "items": len(items),
    }


def build_public_news_payload(symbol: str, limit: int = 6, source: str | None = None, allow_fetch: bool = True) -> dict:
    ticker = _normalize_symbol(symbol)
    safe_limit = max(1, min(int(limit or 6), 20))
    fetched_items = (
        get_symbol_news(ticker, limit=safe_limit)
        if allow_fetch
        else get_cached_symbol_news(ticker, limit=safe_limit)
    )
    scoped_items = [item for item in fetched_items if isinstance(item, dict) and _item_belongs_to_symbol(item, ticker)]
    items = _dedupe_news_items(scoped_items, safe_limit)
    report = get_news_cached_report(ticker, items)
    cache = get_news_cache_info(ticker)
    state = _build_news_state(ticker, items, cache, report)
    payload = {
        "symbol": ticker,
        "requested_symbol": str(symbol or "").upper().strip(),
        "items": items,
        "count": len(items),
        "status": state["status"],
        "state": state,
        "message": state["message"],
        "scope": {
            "type": "ticker",
            "symbol": ticker,
            "mixed_ticker_allowed": False,
            "filtered_out": max(0, len(fetched_items) - len(scoped_items)),
            "duplicates_removed": max(0, len(scoped_items) - len(items)),
        },
        "report": report,
        "cache": cache,
        "cache_only": not allow_fetch,
    }
    if source:
        payload["source"] = source
    return payload
