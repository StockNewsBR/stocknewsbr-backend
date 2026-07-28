from __future__ import annotations

import math

import re
from typing import Any, Iterable


_QUERY_RE = re.compile(r"[?&=]")
_B3_RE = re.compile(r"^[A-Z][A-Z0-9]{3,4}(3|4|5|6|7|11|32|34)$")
_B3_WITH_SUFFIX_RE = re.compile(r"^([A-Z][A-Z0-9]{3,4}(?:3|4|5|6|7|11|32|34))SA$")
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

_US_MARKET_QUALIFIERS = {"AMEX", "ARCA", "BATS", "CBOE", "NASDAQ", "NYSE", "NYSEARCA", "OTC"}

KNOWN_BDR_SYMBOLS = {
    "A1MD34",
    "AAPL34",
    "AMZO34",
    "BABA34",
    "BERK34",
    "GOGL34",
    "ITLC34",
    "JBSS32",
    "M1TA34",
    "MELI34",
    "MSFT34",
    "NFLX34",
    "NVDC34",
    "PFIZ34",
    "PYPL34",
    "QCOM34",
    "TSLA34",
}

KNOWN_NON_BDR_B3_SYMBOLS = {
    "IVVB11",
}

US_EXCHANGE_BY_SYMBOL = {
    "AAL": "NASDAQ",
    "AAPL": "NASDAQ",
    "ADBE": "NASDAQ",
    "AMD": "NASDAQ",
    "AMZN": "NASDAQ",
    "AVGO": "NASDAQ",
    "BABA": "NYSE",
    "BULL": "NASDAQ",
    "BYDDY": "OTC",
    "COIN": "NASDAQ",
    "COST": "NASDAQ",
    "CRM": "NYSE",
    "GOOGL": "NASDAQ",
    "INTC": "NASDAQ",
    "META": "NASDAQ",
    "MSFT": "NASDAQ",
    "NFLX": "NASDAQ",
    "NVDA": "NASDAQ",
    "ORCL": "NYSE",
    "PDD": "NASDAQ",
    "PLTR": "NASDAQ",
    "PYPL": "NASDAQ",
    "QCOM": "NASDAQ",
    "SHOP": "NYSE",
    "SPY": "NYSEARCA",
    "QQQ": "NASDAQ",
    "SPCX": "NASDAQ",
    "SNOW": "NYSE",
    "TSLA": "NASDAQ",
    "UBER": "NYSE",
    "BA": "NYSE",
    "BAC": "NYSE",
    "BNY": "NYSE",
    "CVX": "NYSE",
    "DIA": "NYSEARCA",
    "DIS": "NYSE",
    "F": "NYSE",
    "GE": "NYSE",
    "GM": "NYSE",
    "GS": "NYSE",
    "IWM": "NYSEARCA",
    "JPM": "NYSE",
    "TSM": "NYSE",
    "VOO": "NYSEARCA",
    "WMT": "NYSE",
    "XOM": "NYSE",
}

_CURATED_ALIASES: dict[str, tuple[str, ...]] = {
    "ASAI3": ("ASAI3.SA", "ASAI3 B3", "BVMF:ASAI3", "BMFBOVESPA:ASAI3"),
    # Corporate-action remaps (old B3 tickers -> live successors on Yahoo):
    "BRAV3": ("BRAV3.SA", "BRAV3 B3", "RRRP3", "RRRP3.SA", "BVMF:BRAV3", "BMFBOVESPA:BRAV3", "BVMF:RRRP3", "BMFBOVESPA:RRRP3"),
    "MBRF3": ("MBRF3.SA", "MBRF3 B3", "MRFG3", "MRFG3.SA", "BRFS3", "BRFS3.SA", "BVMF:MBRF3", "BMFBOVESPA:MBRF3", "BVMF:MRFG3", "BMFBOVESPA:MRFG3", "BVMF:BRFS3", "BMFBOVESPA:BRFS3"),
    "EMBJ3": ("EMBJ3.SA", "EMBJ3 B3", "EMBR3", "EMBR3.SA", "BVMF:EMBJ3", "BMFBOVESPA:EMBJ3", "BVMF:EMBR3", "BMFBOVESPA:EMBR3"),
    # B3 renamed AZUL ON from AZUL4 to AZUL54 (Dec/2025); Yahoo serves AZUL54.SA.
    "AZUL54": ("AZUL54.SA", "AZUL54 B3", "AZUL4", "AZUL4.SA", "BVMF:AZUL54", "BMFBOVESPA:AZUL54", "BVMF:AZUL4", "BMFBOVESPA:AZUL4"),
    # CPLE6 still trades on B3 as its own line — do NOT fold it into CPLE3.
    "CPLE3": ("CPLE3.SA", "CPLE3 B3", "CPLE5", "CPLE5.SA", "BVMF:CPLE3", "BMFBOVESPA:CPLE3"),
    "JBSS32": ("JBSS32.SA", "JBSS32 B3", "JBSS3", "JBSS3.SA", "BVMF:JBSS32", "BMFBOVESPA:JBSS32", "BVMF:JBSS3", "BMFBOVESPA:JBSS3"),
    "B3SA3": ("B3SA3.SA", "B3SA3 B3", "BVMF:B3SA3", "BMFBOVESPA:B3SA3"),
    "AXIA3": ("AXIA3.SA", "AXIA3 B3", "AXIA6", "AXIA6.SA", "ELET3", "ELET3.SA", "ELET6", "ELET6.SA", "BVMF:ELET3", "BVMF:ELET6", "BMFBOVESPA:ELET3", "BMFBOVESPA:ELET6", "BMFBOVESPA:AXIA6"),
    "AXIA7": ("AXIA7.SA", "AXIA7 B3"),
    "PETR4": ("PETR4.SA", "PETR4 B3", "PETR", "BVMF:PETR4", "BMFBOVESPA:PETR4"),
    "VALE3": ("VALE3.SA", "VALE3 B3", "VALE", "BVMF:VALE3", "BMFBOVESPA:VALE3"),
    "ITUB4": ("ITUB4.SA", "ITUB4 B3", "ITUB", "BVMF:ITUB4", "BMFBOVESPA:ITUB4"),
    "BBAS3": ("BBAS3.SA", "BBAS3 B3", "BBAS", "BVMF:BBAS3", "BMFBOVESPA:BBAS3"),
    "WIN": ("WIN$", "WINFUT", "WIN1!", "BMFBOVESPA:WIN1!"),
    "AAPL": ("NASDAQ:AAPL", "AAPL.US"),
    "BNY": ("NYSE:BNY", "BNY.US"),
    "BULL": ("NASDAQ:BULL", "BULL.US"),
    "BYDDY": ("OTC:BYDDY", "BYDDY.US"),
    "CRM": ("NYSE:CRM", "CRM.US"),
    "DIA": ("NYSEARCA:DIA", "DIA.US"),
    "F": ("NYSE:F", "F.US"),
    "IWM": ("NYSEARCA:IWM", "IWM.US"),
    "MSFT": ("NASDAQ:MSFT", "MSFT.US"),
    "NVDA": ("NASDAQ:NVDA", "NVDA.US"),
    "TSLA": ("NASDAQ:TSLA", "TSLA.US"),
    "VOO": ("NYSEARCA:VOO", "VOO.US"),
    "SPY": ("NYSEARCA:SPY", "SPY.US"),
    "QQQ": ("NASDAQ:QQQ", "QQQ.US"),
    "A1MD34": ("AMD34", "AMD34.SA", "A1MD34.SA"),
    "AMZO34": ("AMZN34", "AMZN34.SA", "AMZO34.SA"),
    "ITLC34": ("INTC34", "INTC34.SA", "I1NC34", "I1NC34.SA", "ITLC34.SA"),
    "M1TA34": ("META34", "META34.SA", "M1TA34.SA"),
}

_TRADINGVIEW_SYMBOL_FALLBACKS: dict[str, tuple[str, ...]] = {
    "AXIA3": ("BMFBOVESPA:AXIA3", "BMFBOVESPA:AXIA6", "BMFBOVESPA:ELET6", "BMFBOVESPA:ELET3"),
    "AXIA7": ("BMFBOVESPA:AXIA7",),
}


def _has_us_market_qualifier_raw(raw: str) -> bool:
    if not raw:
        return False
    if raw.endswith(".US"):
        return True
    if ":" not in raw:
        return False
    prefix = raw.split(":", 1)[0].strip()
    return prefix in _US_MARKET_QUALIFIERS


def _alias_key(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw or _QUERY_RE.search(raw):
        return ""
    if ".." in raw or "\\" in raw:
        return ""
    has_us_market_qualifier = _has_us_market_qualifier_raw(raw)

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

    if has_us_market_qualifier and compact.endswith("34"):
        return ""

    crypto_match = _CRYPTO_RE.match(compact)
    if crypto_match and crypto_match.group(1) in CRYPTO_BASES:
        compact = f"{crypto_match.group(1)}USD"

    return compact


def _has_market_qualifier(value: Any) -> bool:
    raw = str(value or "").strip().upper()
    return _has_us_market_qualifier_raw(raw)


def has_us_market_qualifier(value: Any) -> bool:
    return _has_market_qualifier(value)


_BDR_PROXY_SOURCES = {"proxy_market", "reference_proxy"}
_BDR_PROXY_FALLBACK_TYPES = {
    "foreign_underlying_context_only",
    "foreign_underlying_proxy",
    "reference_proxy",
}


def is_bdr_proxy_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    source = str(payload.get("source") or "").lower().strip()
    fallback_type = str(payload.get("fallback_type") or "").lower().strip()
    return source in _BDR_PROXY_SOURCES or fallback_type in _BDR_PROXY_FALLBACK_TYPES


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


def _is_ambiguous_crypto_key(key: str, value: Any) -> bool:
    return key in CRYPTO_BASES and not _has_market_qualifier(value)


def _is_disallowed_qualified_crypto_pair(key: str, value: Any) -> bool:
    crypto_match = _CRYPTO_RE.match(key or "")
    return bool(
        _has_market_qualifier(value)
        and crypto_match
        and crypto_match.group(1) in CRYPTO_BASES
    )


def _is_disallowed_qualified_b3_key(key: str, value: Any) -> bool:
    return bool(
        _has_market_qualifier(value)
        and (_B3_RE.match(key or "") or _B3_FUTURE_RE.match(key or ""))
        and key not in US_EXCHANGE_BY_SYMBOL
    )


def _is_unlisted_bdr_key(key: str) -> bool:
    return key.endswith(("32", "34")) and key not in KNOWN_BDR_SYMBOLS


def canonical_symbol_or_none(value: Any) -> str | None:
    key = _alias_key(value)
    if not key:
        return None
    crypto_match = _CRYPTO_RE.match(key)
    if _is_disallowed_qualified_crypto_pair(key, value):
        return None
    if key in CRYPTO_BASES:
        if _is_ambiguous_crypto_key(key, value):
            return None
        return key if key in US_EXCHANGE_BY_SYMBOL else None
    if _is_disallowed_qualified_b3_key(key, value):
        return None

    mapped = _ALIAS_TO_CANONICAL.get(key)
    if mapped:
        return mapped

    if _B3_RE.match(key):
        if _is_unlisted_bdr_key(key):
            return None
        return key

    if _B3_FUTURE_RE.match(key):
        return key

    if crypto_match and crypto_match.group(1) in CRYPTO_BASES:
        return f"{crypto_match.group(1)}USD"

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
    if key in CRYPTO_BASES:
        if _is_ambiguous_crypto_key(key, value) or key not in US_EXCHANGE_BY_SYMBOL:
            return ""
    if key and _is_disallowed_qualified_crypto_pair(key, value):
        return ""
    if key and _is_disallowed_qualified_b3_key(key, value):
        return ""
    if key and _is_unlisted_bdr_key(key):
        return ""
    if key and re.fullmatch(r"[A-Z][A-Z0-9]{0,15}", key):
        return key
    return ""


def is_ambiguous_crypto_symbol(value: Any) -> bool:
    return _alias_key(value) in CRYPTO_BASES and not _has_market_qualifier(value)


def is_known_bdr_symbol(value: Any) -> bool:
    canonical = canonical_symbol(value, fallback=False)
    key = _alias_key(value)
    return bool((canonical and canonical in KNOWN_BDR_SYMBOLS) or (key and key in KNOWN_BDR_SYMBOLS))


def is_bdr_symbol(value: Any) -> bool:
    return is_known_bdr_symbol(value)


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
        aliases.update({f"{base}USDT", f"{base}-USD", f"{base}-USDT", f"{base}/USD", f"{base}/USDT"})
        if base == "BTC":
            aliases.update({"XBTUSD", "XBTUSDT"})

    if canonical in US_EXCHANGE_BY_SYMBOL:
        exchange = US_EXCHANGE_BY_SYMBOL[canonical]
        aliases.update({f"{exchange}:{canonical}", f"{canonical}.US"})

    if canonical == "WIN":
        aliases.update({"WIN$", "WINFUT", "WIN1!", "BMFBOVESPA:WIN1!"})

    return list(dict.fromkeys(alias for alias in aliases if alias))


def resolve_tradingview_symbol_candidates(value: Any) -> tuple[str, ...]:
    canonical = canonical_symbol(value)
    if not canonical:
        return tuple()

    curated_fallbacks = _TRADINGVIEW_SYMBOL_FALLBACKS.get(canonical)
    if curated_fallbacks:
        return curated_fallbacks

    if canonical == "WIN":
        return ("BMFBOVESPA:WIN1!",)

    if canonical.endswith("USD") and canonical[:-3] in CRYPTO_BASES:
        return (f"BINANCE:{canonical[:-3]}USDT",)

    if _B3_RE.match(canonical):
        return (f"BMFBOVESPA:{canonical}",)

    return (f"{US_EXCHANGE_BY_SYMBOL.get(canonical, 'NASDAQ')}:{canonical}",)


def resolve_tradingview_symbol(value: Any) -> str:
    candidates = resolve_tradingview_symbol_candidates(value)
    return candidates[0] if candidates else ""


def tradingview_symbol(value: Any) -> str:
    return resolve_tradingview_symbol(value)


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
    if is_bdr_symbol(canonical):
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
        item["tradingview_symbol_candidates"] = item.get("tradingview_symbol_candidates") or list(
            resolve_tradingview_symbol_candidates(resolved)
        )
        item["symbol_category"] = item.get("symbol_category") or symbol_category(resolved)
    return item


def _row_quality_score(row: dict[str, Any]) -> tuple[float, float, float]:
    def safe_float(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            f_val = float(value)
            if not math.isfinite(f_val):
                return 0.0
            return f_val
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
