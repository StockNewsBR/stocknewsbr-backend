from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.services.snapshot_contract import (
    QUALITY_CACHED,
    QUALITY_EMPTY,
    QUALITY_INVALID,
    QUALITY_REAL_TIME,
    QUALITY_SCORE_ONLY,
    QUALITY_STALE,
    coerce_data_quality,
    data_quality_label,
    data_quality_score,
)
from app.services.symbol_registry import canonical_symbol


import math

def safe_float(value: Any, default: Any = 0.0) -> Any:
    try:
        if value is None or value == "":
            return default
        f_val = float(value)
        if not math.isfinite(f_val):
            return default
        return f_val
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


def deal_timestamp(row: Dict[str, Any]) -> Any:
    for key in (
        "found_at",
        "first_seen_at",
        "deal_detected_at",
        "signal_detected_at",
    ):
        value = row.get(key)
        if value not in (None, ""):
            return value
    return market_timestamp(row)


def _min_iso(a: str, b: str) -> str:
    """Return the earlier of two ISO timestamps, tolerant of parse failures.

    Used to clamp worker-cycle timestamps so a signal is never reported as
    fresher than the market data it was derived from.
    """
    try:
        da = datetime.fromisoformat(a)
        db = datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return a
    return a if da <= db else b


def get_symbol(row: Dict[str, Any]) -> str:
    return canonical_symbol(
        row.get("ticker")
        or row.get("symbol")
        or row.get("canonical_symbol")
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

    data_quality = coerce_data_quality(row)
    is_stale = bool(row.get("stale") is True or row.get("is_stale") is True or data_quality == QUALITY_STALE)
    fallback_used = bool(row.get("fallback_used"))
    provider_error = row.get("provider_error")
    last_updated = row.get("last_updated") or row.get("updated_at") or row.get("generated_at") or market_timestamp(row)
    return {
        **row,
        "ticker": get_symbol(row),
        "symbol": get_symbol(row),
        "canonical_symbol": get_symbol(row),
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
        "data_quality": data_quality,
        "data_quality_label": data_quality_label(data_quality),
        "data_quality_score": data_quality_score(data_quality),
        "last_updated": last_updated,
        "is_stale": is_stale,
        "fallback_used": fallback_used,
        "provider_error": provider_error,
        "source": row.get("source") or ("market_snapshot" if data_quality in {QUALITY_REAL_TIME, QUALITY_CACHED} else "snapshot"),
    }


TONE_BULLISH = "bullish"
TONE_BEARISH = "bearish"
TONE_NEUTRAL = "neutral"
TONE_RISK = "risk"

# Machine state key -> (human label pt-BR, tone).
#
# `tone` is the ONLY directional field. `score` is a 0-100 magnitude (how strong
# the reading is), never a direction: several engines feed it abs(momentum) or
# raw intensity, so a bearish state can legitimately score 100. Colour the UI by
# `tone`, never by `score`.
AI_STATE_CATALOG: Dict[str, tuple[str, str]] = {
    # trend / regime
    "uptrend_structure": ("Estrutura de alta", TONE_BULLISH),
    "downtrend_structure": ("Estrutura de baixa", TONE_BEARISH),
    "structure_mixed": ("Estrutura indefinida", TONE_NEUTRAL),
    "trend_pending": ("Tendência pendente", TONE_NEUTRAL),
    "bull_trend": ("Tendência de alta", TONE_BULLISH),
    "bear_trend": ("Tendência de baixa", TONE_BEARISH),
    "range": ("Lateralizado", TONE_NEUTRAL),
    "high_volatility": ("Volatilidade alta", TONE_RISK),
    "reversal_up": ("Reversão para cima", TONE_BULLISH),
    "reversal_down": ("Reversão para baixo", TONE_BEARISH),
    # momentum / radar (radar score is direction-agnostic: velocity + RVOL + ATR)
    "momentum_expansion": ("Momentum em expansão", TONE_BULLISH),
    "bearish_momentum": ("Momentum vendedor", TONE_BEARISH),
    "momentum_watch": ("Momentum em formação", TONE_NEUTRAL),
    "momentum_quiet": ("Momentum fraco", TONE_NEUTRAL),
    "momentum_ignition": ("Ignição de movimento", TONE_NEUTRAL),
    "fast_move": ("Movimento acelerado", TONE_NEUTRAL),
    "early_radar": ("Ignição inicial", TONE_NEUTRAL),
    "quiet": ("Sem movimento relevante", TONE_NEUTRAL),
    # breakout / volatility squeeze
    "ready_to_break": ("Pronto para romper", TONE_BULLISH),
    "building_pressure": ("Pressão de rompimento", TONE_BULLISH),
    "not_ready": ("Sem gatilho de rompimento", TONE_NEUTRAL),
    "squeeze_ready": ("Compressão pronta", TONE_NEUTRAL),
    "compression": ("Em compressão", TONE_NEUTRAL),
    "already_expanded": ("Já expandido", TONE_NEUTRAL),
    # heat map / relative strength
    "strong_buying": ("Compra forte", TONE_BULLISH),
    "strong_selling": ("Venda forte", TONE_BEARISH),
    "mixed": ("Misto", TONE_NEUTRAL),
    # institutional flow / smart money / accumulation
    "institutional_buying": ("Compra institucional", TONE_BULLISH),
    "institutional_interest": ("Interesse institucional", TONE_BULLISH),
    "institutional_accumulation": ("Acumulação institucional", TONE_BULLISH),
    "institutional_distribution": ("Distribuição institucional", TONE_BEARISH),
    "institutional_defense": ("Defesa institucional", TONE_BULLISH),
    "distribution_risk": ("Risco de distribuição", TONE_BEARISH),
    "distribution_or_weak": ("Distribuição ou fraqueza", TONE_BEARISH),
    "accumulation": ("Acumulação", TONE_BULLISH),
    "early_accumulation": ("Acumulação inicial", TONE_BULLISH),
    "smart_money_active": ("Smart money ativo", TONE_BULLISH),
    "smart_money_interest": ("Interesse de smart money", TONE_BULLISH),
    "smart_money_neutral": ("Smart money neutro", TONE_NEUTRAL),
    "retail_noise": ("Ruído de varejo", TONE_NEUTRAL),
    "possible_manipulation": ("Possível manipulação", TONE_RISK),
    "monitoring": ("Em monitoramento", TONE_NEUTRAL),
    # liquidity
    "liquidity_hotspot": ("Concentração de liquidez", TONE_NEUTRAL),
    "liquidity_zone": ("Zona de liquidez", TONE_NEUTRAL),
    "liquidity_monitoring": ("Monitorando liquidez", TONE_NEUTRAL),
    "thin_liquidity": ("Liquidez fraca", TONE_RISK),
    "liquidity_trap": ("Armadilha de liquidez", TONE_RISK),
    "liquidity_sweep_detected": ("Varredura de liquidez detectada", TONE_RISK),
    "sweep_watch": ("Possível varredura", TONE_NEUTRAL),
    "no_sweep": ("Sem varredura", TONE_NEUTRAL),
    # risk
    "low_risk": ("Risco baixo", TONE_NEUTRAL),
    "medium_risk": ("Risco médio", TONE_NEUTRAL),
    "high_risk": ("Risco alto", TONE_RISK),
    "critical_risk": ("Risco crítico", TONE_RISK),
    # news
    "news_available": ("Notícias acopladas", TONE_NEUTRAL),
    "news_empty": ("Sem notícia relevante", TONE_NEUTRAL),
    "news_not_linked": ("Notícia não vinculada", TONE_NEUTRAL),
    "news_provider_failed": ("Falha no provedor de notícias", TONE_RISK),
    # macro
    "macro_context_available": ("Contexto macro disponível", TONE_NEUTRAL),
    "macro_news_only": ("Macro apenas por notícias", TONE_NEUTRAL),
    "macro_unavailable": ("Sem contexto macro", TONE_NEUTRAL),
    # master score
    "bullish_strong": ("Alta forte", TONE_BULLISH),
    "bullish_caution": ("Alta com cautela", TONE_BULLISH),
    "bearish_strong": ("Baixa forte", TONE_BEARISH),
    "bearish_caution": ("Baixa com cautela", TONE_BEARISH),
    "neutral_context": ("Contexto neutro", TONE_NEUTRAL),
    "blocked_context": ("Contexto bloqueado", TONE_RISK),
}


def describe_state(state: Any) -> tuple[str, str]:
    """Return (human label, tone) for a machine state key.

    An unknown key degrades to a neutral tone so a newly added engine state can
    never render as bullish by accident.
    """
    key = str(state or "").strip().lower()
    label, tone = AI_STATE_CATALOG.get(key, ("", TONE_NEUTRAL))
    return label or key.replace("_", " ").strip() or "Indefinido", tone


def signal_from_score(score: float) -> str:
    if score >= 75:
        return "WATCH"
    if score >= 55:
        return "WATCH"
    if score <= 25:
        return "WATCH"
    return "WAIT"


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
    ticker = get_symbol(row)

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
    for metric_key in (
        "data_quality",
        "source_score",
        "source_score_rank",
        "avg_volume",
        "rel_volume",
        "vwap",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
    ):
        if row.get(metric_key) not in (None, ""):
            metric_payload.setdefault(metric_key, row.get(metric_key))
    market_time = coerce_iso(market_timestamp(row))
    detected_time = coerce_iso(deal_timestamp(row), fallback=market_time)
    confirmed_time = coerce_iso(
        row.get("last_confirmed_at") or row.get("updated_at") or row.get("generated_at"),
        fallback=market_time,
    )
    # A confirmation timestamp reflects a worker cycle and can run ahead of the
    # market data the signal was derived from. Never report data as fresher
    # than its source: clamp the confirmation to the market timestamp.
    confirmed_time = _min_iso(confirmed_time, market_time)
    as_of = coerce_iso(row.get("as_of"), fallback=market_time)
    price = safe_float(row.get("price"))
    volume = safe_float(row.get("volume"))
    data_quality = coerce_data_quality(row)
    if data_quality in {QUALITY_EMPTY, QUALITY_INVALID} and price > 0 and volume > 0:
        data_quality = QUALITY_CACHED
    if data_quality == QUALITY_SCORE_ONLY and price > 0 and volume > 0 and row.get("source") in {"market", "real_time", "realtime"}:
        data_quality = QUALITY_REAL_TIME
    reason_text = reason or _reason_from_metrics(tool, state, score, metric_payload)
    signal = signal_from_score(score)
    decision_state = "WATCH" if signal == "WATCH" else "WAIT"
    state_label, tone = describe_state(state)
    payload = {
        "ticker": get_symbol(row),
        "symbol": get_symbol(row),
        "canonical_symbol": get_symbol(row),
        "name": row.get("name", get_symbol(row)),
        "tool": tool,
        "score": score,
        "signal": signal,
        "decision_state": decision_state,
        "decision_ready": False,
        "can_trade": False,
        "operational_message": "⚠️ NÃO OPERAR AGORA",
        "no_trade_reasons": ["contexto técnico insuficiente"],
        "state": state,
        "state_key": state,
        "state_label": state_label,
        "tone": tone,
        # `score` is magnitude, not direction. Never colour by it; use `tone`.
        "score_meaning": "risk_level" if tool == "risk" else "signal_strength",
        "confidence": confidence_from_inputs(row),
        "price": round(price, 4),
        "change_pct": round(safe_float(row.get("change_pct")), 2),
        "volume": safe_int(volume),
        "avg_volume": safe_int(row.get("avg_volume", row.get("average_volume"))),
        "rel_volume": round(safe_float(row.get("rel_volume")), 2),
        "vwap": round(safe_float(row.get("vwap")), 4),
        "rsi": round(safe_float(row.get("rsi", 50.0)), 2),
        "macd": round(safe_float(row.get("macd")), 4),
        "macd_signal": round(safe_float(row.get("macd_signal")), 4),
        "macd_histogram": round(safe_float(row.get("macd_histogram")), 4),
        "adx": round(safe_float(row.get("adx", 15.0)), 2),
        "atr_pct": round(safe_float(row.get("atr_pct", 1.0)), 2),
        "data_quality": data_quality,
        "data_quality_label": data_quality_label(data_quality),
        "data_quality_score": data_quality_score(data_quality),
        "quote_status": row.get("quote_status") or data_quality,
        "market_data_updated_at": market_time,
        "last_bar_at": coerce_iso(row.get("last_bar_at"), fallback=market_time),
        "last_updated": coerce_iso(row.get("last_updated") or row.get("updated_at"), fallback=market_time),
        "is_stale": bool(row.get("stale") is True or row.get("is_stale") is True or data_quality == QUALITY_STALE),
        "fallback_used": bool(row.get("fallback_used")),
        "provider_error": row.get("provider_error"),
        "source": row.get("source") or ("market_snapshot" if data_quality in {QUALITY_REAL_TIME, QUALITY_CACHED} else "snapshot"),
        "metrics": metric_payload,
        "ai_comment": ai_comment,
        "trigger": trigger,
        "invalidation": invalidation,
        "invalidacao": invalidation,
        "reason": reason_text,
        "news_context": news_context or _news_context(row),
        "found_at": detected_time,
        "first_seen_at": detected_time,
        "deal_detected_at": detected_time,
        "detected_at": detected_time,
        "updated_at": confirmed_time,
        "last_confirmed_at": confirmed_time,
        "as_of": as_of,
        "snapshot_generated_at": coerce_iso(row.get("snapshot_generated_at") or row.get("generated_at"), fallback=confirmed_time),
        "last_seen_at": confirmed_time,
    }
    if row.get("auditor") or row.get("audit_status") or row.get("blocked_by_auditor"):
        auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
        payload["auditor"] = auditor
        payload["institutional_auditor"] = row.get("institutional_auditor") if isinstance(row.get("institutional_auditor"), dict) else auditor
        payload["audit_status"] = row.get("audit_status") or auditor.get("audit_status")
        payload["auditor_status"] = row.get("auditor_status") or auditor.get("auditor_status") or payload.get("audit_status")
        payload["audit_score"] = row.get("audit_score") or auditor.get("audit_score")
        payload["auditor_score"] = row.get("auditor_score") or auditor.get("auditor_score") or payload.get("audit_score")
        payload["audit_confidence"] = row.get("audit_confidence") or auditor.get("audit_confidence")
        payload["audit_reason"] = row.get("audit_reason") or auditor.get("audit_reason")
        payload["audit_blocks"] = row.get("audit_blocks") or auditor.get("audit_blocks") or []
        payload["audit_warnings"] = row.get("audit_warnings") or auditor.get("audit_warnings") or []
        payload["audit_summary"] = row.get("audit_summary") or auditor.get("audit_summary")
        payload["auditor_summary"] = row.get("auditor_summary") or auditor.get("auditor_summary") or payload.get("audit_summary")
        payload["auditor_approved"] = bool(row.get("auditor_approved") is True or auditor.get("auditor_approved") is True)
        payload["blocked_by_auditor"] = bool(row.get("blocked_by_auditor") is True or auditor.get("blocked_by_auditor") is True)
    return payload


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
