from __future__ import annotations

import re
from typing import Any, Iterable


_QUERY_RE = re.compile(r"[?&=]")
_B3_RE = re.compile(r"^[A-Z][A-Z0-9]{3,4}(3|4|5|6|11|34)$")
_B3_WITH_SUFFIX_RE = re.compile(r"^([A-Z][A-Z0-9]{3,4}(?:3|4|5|6|11|34))SA$")
_B3_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")
_CRYPTO_RE = re.compile(r"^([A-Z0-9]{2,8})(USD|USDT)$")
_US_RE = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")

CRYPTO_BASES = {
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "MATIC",
    "AVAX",
    "LINK",
}

US_EXCHANGE_BY_SYMBOL = {
    "AAL": "NASDAQ",
    "AAPL": "NASDAQ",
    "AMD": "NASDAQ",
    "AMZN": "NASDAQ",
    "AVGO": "NASDAQ",
    "COST": "NASDAQ",
    "GOOGL": "NASDAQ",
    "INTC": "NASDAQ",
    "META": "NASDAQ",
    "MSFT": "NASDAQ",
    "NVDA": "NASDAQ",
    "PLTR": "NASDAQ",
    "QCOM": "NASDAQ",
    "SPY": "NYSEARCA",
    "QQQ": "NASDAQ",
    "SNOW": "NYSE",
    "TSLA": "NASDAQ",
    "BA": "NYSE",
    "BAC": "NYSE",
    "CVX": "NYSE",
    "DIS": "NYSE",
    "F": "NYSE",
    "GE": "NYSE",
    "GM": "NYSE",
    "GS": "NYSE",
    "JPM": "NYSE",
    "TSM": "NYSE",
    "WMT": "NYSE",
    "XOM": "NYSE",
}

_CURATED_ALIASES: dict[str, tuple[str, ...]] = {
    "ASAI3": ("ASAI3.SA", "ASAI3 B3", "BVMF:ASAI3", "BMFBOVESPA:ASAI3"),
    "AZUL4": ("AZUL4.SA", "AZUL4 B3", "BVMF:AZUL4", "BMFBOVESPA:AZUL4"),
    "B3SA3": ("B3SA3.SA", "B3SA3 B3", "BVMF:B3SA3", "BMFBOVESPA:B3SA3"),
    "AXIA6": ("AXIA6.SA", "AXIA6 B3", "ELET6", "ELET6.SA", "BVMF:ELET6", "BMFBOVESPA:ELET6", "BMFBOVESPA:AXIA6"),
    "PETR4": ("PETR4.SA", "PETR4 B3", "PETR", "BVMF:PETR4", "BMFBOVESPA:PETR4"),
    "VALE3": ("VALE3.SA", "VALE3 B3", "VALE", "BVMF:VALE3", "BMFBOVESPA:VALE3"),
    "ITUB4": ("ITUB4.SA", "ITUB4 B3", "ITUB", "BVMF:ITUB4", "BMFBOVESPA:ITUB4"),
    "BBAS3": ("BBAS3.SA", "BBAS3 B3", "BBAS", "BVMF:BBAS3", "BMFBOVESPA:BBAS3"),
    "WIN": ("WIN$", "WINFUT", "WIN1!", "BMFBOVESPA:WIN1!"),
    "AAPL": ("NASDAQ:AAPL", "AAPL.US"),
    "MSFT": ("NASDAQ:MSFT", "MSFT.US"),
    "NVDA": ("NASDAQ:NVDA", "NVDA.US"),
    "TSLA": ("NASDAQ:TSLA", "TSLA.US"),
    "SPY": ("NYSEARCA:SPY", "SPY.US"),
    "QQQ": ("NASDAQ:QQQ", "QQQ.US"),
}


def _alias_key(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw or _QUERY_RE.search(raw):
        return ""

    raw = re.sub(r"\s+", " ", raw)
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1].strip()
    raw = re.sub(r"\s+(B3|BVMF|BMFBOVESPA)$", "", raw).strip()
    raw = raw.removeprefix("$")

    for suffix in (".SA", ".US"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]

    compact = (
        raw.replace(" ", "")
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
    )
    compact = compact.strip()

    if compact.endswith("SA"):
        match = _B3_WITH_SUFFIX_RE.match(compact)
        if match:
            compact = match.group(1)

    if compact.startswith("XBT"):
        compact = f"BTC{compact[3:]}"

    crypto_match = _CRYPTO_RE.match(compact)
    if crypto_match and crypto_match.group(1) in CRYPTO_BASES:
        compact = f"{crypto_match.group(1)}USD"

    return compact


def _build_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}

    for canonical, aliases in _CURATED_ALIASES.items():
        for alias in (canonical, *aliases):
            key = _alias_key(alias)
            if key:
                alias_map[key] = canonical

    for base in CRYPTO_BASES:
        canonical = f"{base}USD"
        crypto_aliases = (
            base,
            canonical,
            f"{base}USDT",
            f"{base}/USD",
            f"{base}/USDT",
            f"{base}-USD",
            f"{base}-USDT",
            f"BINANCE:{base}USDT",
        )
        if base == "BTC":
            crypto_aliases = (*crypto_aliases, "XBTUSD", "XBTUSDT", "XBT/USD")
        for alias in crypto_aliases:
            key = _alias_key(alias)
            if key:
                alias_map[key] = canonical

    for symbol, exchange in US_EXCHANGE_BY_SYMBOL.items():
        for alias in (symbol, f"{exchange}:{symbol}", f"{symbol}.US"):
            key = _alias_key(alias)
            if key:
                alias_map[key] = symbol

    return alias_map


_ALIAS_TO_CANONICAL = _build_alias_map()


def canonical_symbol_or_none(value: Any) -> str | None:
    key = _alias_key(value)
    if not key:
        return None

    mapped = _ALIAS_TO_CANONICAL.get(key)
    if mapped:
        return mapped

    if _B3_RE.match(key):
        return key

    if _B3_FUTURE_RE.match(key):
        return key

    crypto_match = _CRYPTO_RE.match(key)
    if crypto_match and crypto_match.group(1) in CRYPTO_BASES:
        return f"{crypto_match.group(1)}USD"

    if key in CRYPTO_BASES:
        return f"{key}USD"

    if _US_RE.match(key):
        return key

    return None


def canonical_symbol(value: Any, *, fallback: bool = True) -> str:
    resolved = canonical_symbol_or_none(value)
    if resolved:
        return resolved
    if not fallback:
        return ""
    key = _alias_key(value)
    if key and re.fullmatch(r"[A-Z][A-Z0-9]{0,15}", key):
        return key
    return ""


def canonical_symbol_aliases(value: Any) -> list[str]:
    canonical = canonical_symbol(value)
    if not canonical:
        return []

    aliases = {canonical}
    for alias_key, mapped in _ALIAS_TO_CANONICAL.items():
        if mapped == canonical:
            aliases.add(alias_key)

    if _B3_RE.match(canonical):
        aliases.add(f"{canonical}.SA")
        aliases.add(f"BMFBOVESPA:{canonical}")

    if canonical.endswith("USD"):
        base = canonical[:-3]
        aliases.update({base, f"{base}USDT", f"{base}-USD", f"{base}-USDT", f"{base}/USD", f"{base}/USDT"})
        if base == "BTC":
            aliases.update({"XBTUSD", "XBTUSDT"})

    if canonical in US_EXCHANGE_BY_SYMBOL:
        exchange = US_EXCHANGE_BY_SYMBOL[canonical]
        aliases.update({f"{exchange}:{canonical}", f"{canonical}.US"})

    if canonical == "WIN":
        aliases.update({"WIN$", "WINFUT", "WIN1!", "BMFBOVESPA:WIN1!"})

    return list(dict.fromkeys(alias for alias in aliases if alias))


def tradingview_symbol(value: Any) -> str:
    canonical = canonical_symbol(value)
    if not canonical:
        return "BMFBOVESPA:PETR4"

    if canonical == "WIN":
        return "BMFBOVESPA:WIN1!"

    if canonical.endswith("USD") and canonical[:-3] in CRYPTO_BASES:
        return f"BINANCE:{canonical[:-3]}USDT"

    if _B3_RE.match(canonical):
        return f"BMFBOVESPA:{canonical}"

    return f"{US_EXCHANGE_BY_SYMBOL.get(canonical, 'NASDAQ')}:{canonical}"


def provider_symbol(value: Any) -> str:
    canonical = canonical_symbol(value)
    if not canonical:
        return ""

    if canonical == "WIN":
        return "WIN1!"

    if canonical.endswith("USD") and canonical[:-3] in CRYPTO_BASES:
        return f"{canonical[:-3]}-USD"

    if _B3_RE.match(canonical):
        return f"{canonical}.SA"

    return canonical


def symbol_category(value: Any) -> str:
    canonical = canonical_symbol(value)
    if not canonical:
        return ""
    if canonical.endswith("USD") and canonical[:-3] in CRYPTO_BASES:
        return "Crypto"
    if canonical.endswith("34") or canonical == "IVVB11":
        return "BDR"
    if _B3_RE.match(canonical) or _B3_FUTURE_RE.match(canonical) or canonical == "WIN":
        return "B3"
    return "USA"


def canonicalize_symbol_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    raw_symbol = item.get("canonical_symbol") or item.get("ticker") or item.get("symbol")
    resolved = canonical_symbol(raw_symbol)
    if resolved:
        item["canonical_symbol"] = resolved
        item["ticker"] = resolved
        item["symbol"] = resolved
        item["provider_symbol"] = item.get("provider_symbol") or provider_symbol(resolved)
        item["tradingview_symbol"] = item.get("tradingview_symbol") or tradingview_symbol(resolved)
        item["symbol_category"] = item.get("symbol_category") or symbol_category(resolved)
    return item


def _row_quality_score(row: dict[str, Any]) -> tuple[float, float, float]:
    def safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return (
        safe_float(row.get("master_score_raw")),
        safe_float(row.get("master_score")),
        safe_float(row.get("score")),
    )


def dedupe_canonical_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    best_scores: dict[str, tuple[float, float, float]] = {}
    order: list[str] = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = canonicalize_symbol_row(row)
        symbol = item.get("canonical_symbol") or item.get("ticker") or item.get("symbol")
        if not symbol:
            continue
        key = str(symbol)
        score = _row_quality_score(item)
        if key not in best:
            order.append(key)
            best[key] = item
            best_scores[key] = score
            continue
        if score > best_scores[key]:
            best[key] = item
            best_scores[key] = score

    return [best[key] for key in order]
