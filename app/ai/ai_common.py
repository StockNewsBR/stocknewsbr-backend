from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def pct(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return clamp(((value - low) / (high - low)) * 100.0, 0.0, 100.0)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def coerce_iso(value: Any, fallback: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return raw

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            pass

    return fallback or now_iso()


def market_timestamp(row: Dict[str, Any]) -> Any:
    for key in (
        "market_data_updated_at",
        "last_bar_at",
        "bar_time",
        "time",
        "timestamp",
        "quote_time",
        "provider_timestamp",
        "detected_at",
        "updated_at",
        "last_seen_at",
    ):
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def get_symbol(row: Dict[str, Any]) -> str:
    return (
        row.get("ticker")
        or row.get("symbol")
        or row.get("asset")
        or row.get("code")
        or "UNKNOWN"
    )


def get_name(row: Dict[str, Any]) -> str:
    symbol = get_symbol(row)
    return (
        row.get("name")
        or row.get("company")
        or row.get("description")
        or _fallback_name(symbol)
    )


def _fallback_name(symbol: str) -> str:
    normalized = str(symbol or "").upper().strip()
    if not normalized:
        return "UNKNOWN"
    if normalized.endswith(".SA"):
        base = normalized[:-3]
        if base.endswith("34"):
            return f"{base} BDR"
        return base
    if normalized.endswith("-USD"):
        return normalized.replace("-USD", " Crypto")
    if normalized.isalpha() and len(normalized) <= 6:
        return f"{normalized} US"
    return normalized


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(
        row.get("price", row.get("close", row.get("last", row.get("last_price"))))
    )
    prev_close = safe_float(row.get("prev_close", row.get("previous_close", price)))
    high = safe_float(row.get("high", price))
    low = safe_float(row.get("low", price))
    open_price = safe_float(row.get("open", row.get("open_price", price)))
    volume = safe_float(row.get("volume", row.get("total_volume")))
    avg_volume = safe_float(row.get("avg_volume", row.get("average_volume")))
    rel_volume = safe_float(
        row.get("rel_volume", row.get("relative_volume", 0.0))
    )
    if rel_volume <= 0 and avg_volume > 0:
        rel_volume = volume / avg_volume if avg_volume else 0.0

    vwap = safe_float(row.get("vwap", price))
    rsi = safe_float(row.get("rsi", 50.0))
    adx = safe_float(row.get("adx", 15.0))
    atr_pct = safe_float(row.get("atr_pct", row.get("atr_percent", 1.0)))
    bb_width = safe_float(row.get("bb_width", row.get("bollinger_width", 0.0)))
    kc_width = safe_float(row.get("kc_width", row.get("keltner_width", 0.0)))
    momentum = safe_float(row.get("momentum", row.get("mom", 0.0)))
    change_pct = safe_float(
        row.get(
            "change_pct",
            row.get("percent_change", ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0),
        )
    )

    return {
        **row,
        "ticker": get_symbol(row),
        "name": get_name(row),
        "price": price,
        "prev_close": prev_close,
        "high": high,
        "low": low,
        "open": open_price,
        "volume": volume,
        "avg_volume": avg_volume,
        "rel_volume": rel_volume,
        "vwap": vwap,
        "rsi": rsi,
        "adx": adx,
        "atr_pct": atr_pct,
        "bb_width": bb_width,
        "kc_width": kc_width,
        "momentum": momentum,
        "change_pct": change_pct,
    }


def signal_from_score(score: float) -> str:
    if score >= 75:
        return "BUY"
    if score >= 55:
        return "WATCH"
    if score <= 25:
        return "SELL"
    return "NEUTRAL"


def confidence_from_inputs(row: Dict[str, Any], extra: float = 0.0) -> int:
    base = safe_float(row.get("feature_confidence", 0.0))
    if base <= 0:
        filled = 0
        total = 8
        keys = ["price", "volume", "rel_volume", "vwap", "rsi", "adx", "atr_pct", "change_pct"]
        for key in keys:
            if safe_float(row.get(key)) != 0:
                filled += 1
        base = (filled / total) * 100.0
    return safe_int(clamp(base + extra, 5, 100))


def _news_context(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("news_context") or row.get("news") or row.get("news_report")
    ticker = str(row.get("ticker") or row.get("symbol") or "UNKNOWN")

    if isinstance(raw, dict):
        context = dict(raw)
        context.setdefault("ticker", ticker)
        context.setdefault("status", "available")
        return context

    if isinstance(raw, list):
        return {
            "ticker": ticker,
            "status": "available" if raw else "empty",
            "items": raw[:3],
        }

    return {
        "ticker": ticker,
        "status": "not_linked",
        "summary": "Sem noticia acoplada ao ciclo deste alerta.",
    }


def _reason_from_metrics(tool: str, state: str, score: float, metrics: Dict[str, Any]) -> str:
    metric_parts = []
    for key, value in list((metrics or {}).items())[:5]:
        if isinstance(value, float):
            metric_parts.append(f"{key}={value:.2f}")
        else:
            metric_parts.append(f"{key}={value}")
    metric_text = ", ".join(metric_parts) if metric_parts else "sem metricas adicionais"
    return f"{tool} calculou estado {state} com score {score:.1f}; base: {metric_text}."


def build_payload(
    row: Dict[str, Any],
    tool: str,
    score: float,
    state: str,
    ai_comment: str,
    trigger: str,
    invalidation: str,
    metrics: Optional[Dict[str, Any]] = None,
    reason: str | None = None,
    news_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    score = round(clamp(score), 1)
    metric_payload = dict(metrics or {})
    for metric_key in ("data_quality", "source_score", "source_score_rank"):
        if row.get(metric_key) not in (None, ""):
            metric_payload.setdefault(metric_key, row.get(metric_key))
    timestamp = coerce_iso(market_timestamp(row))
    reason_text = reason or _reason_from_metrics(tool, state, score, metric_payload)
    return {
        "ticker": row.get("ticker", "UNKNOWN"),
        "name": row.get("name", row.get("ticker", "UNKNOWN")),
        "tool": tool,
        "score": score,
        "signal": signal_from_score(score),
        "state": state,
        "confidence": confidence_from_inputs(row),
        "price": round(safe_float(row.get("price")), 4),
        "change_pct": round(safe_float(row.get("change_pct")), 2),
        "volume": safe_int(row.get("volume")),
        "rel_volume": round(safe_float(row.get("rel_volume")), 2),
        "vwap": round(safe_float(row.get("vwap")), 4),
        "rsi": round(safe_float(row.get("rsi", 50.0)), 2),
        "adx": round(safe_float(row.get("adx", 15.0)), 2),
        "atr_pct": round(safe_float(row.get("atr_pct", 1.0)), 2),
        "metrics": metric_payload,
        "ai_comment": ai_comment,
        "trigger": trigger,
        "invalidation": invalidation,
        "invalidacao": invalidation,
        "reason": reason_text,
        "news_context": news_context or _news_context(row),
        "detected_at": timestamp,
        "updated_at": timestamp,
        "last_seen_at": timestamp,
    }


def top_n(results: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return sorted(
        results,
        key=lambda x: (
            x.get("_rank_score", x.get("_sort_score", x.get("score", 0))),
            x.get("score", 0),
            x.get("confidence", 0),
        ),
        reverse=True,
    )[: max(1, limit)]
