from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import clamp, safe_float

OPERATIONAL_ACTIONS = {"BUY", "SELL", "SHORT", "COVER"}
ENTRY_OR_COVER_ACTIONS = {"BUY", "SHORT", "COVER"}
NO_DECISION_ACTION = "NO_DECISION"


_BULLISH_COMPONENTS = (
    ("institutional_flow_score", 0.28),
    ("smart_money_score", 0.24),
    ("accumulation_score", 0.20),
    ("breakout_probability_score", 0.18),
    ("heat_map_score", 0.10),
)

_STATE_BULLISH_BOOSTS = {
    "institutional_flow_state": {
        "institutional_buying": 8.0,
        "institutional_interest": 4.0,
    },
    "smart_money_state": {
        "smart_money_active": 7.0,
        "smart_money_interest": 3.0,
    },
    "accumulation_state": {
        "accumulation": 7.0,
        "early_accumulation": 4.0,
    },
    "breakout_probability_state": {
        "ready_to_break": 6.0,
        "building_pressure": 3.0,
    },
    "heat_map_state": {
        "strong_buying": 6.0,
        "mixed": 1.5,
    },
}

_STATE_BEARISH_BOOSTS = {
    "institutional_flow_state": {
        "distribution_risk": 8.0,
    },
    "smart_money_state": {
        "retail_noise": 4.0,
    },
    "accumulation_state": {
        "distribution_or_weak": 7.0,
    },
    "breakout_probability_state": {
        "not_ready": 3.0,
    },
    "heat_map_state": {
        "strong_selling": 6.0,
        "mixed": 1.5,
    },
}


def _state(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_positive_value(row: Dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = safe_float(row.get(key), 0.0)
        if value > 0:
            return True
    return False


def _market_data_guard(row: Dict[str, Any]) -> tuple[bool, List[str], List[str]]:
    reasons: List[str] = []
    warnings: List[str] = []
    data_quality = _state(row.get("data_quality"))

    if data_quality == "score_only":
        reasons.append("score_only_sem_preco_real")

    if not _has_positive_value(row, "price", "close", "last_price"):
        reasons.append("price_missing_or_zero")

    if not _has_positive_value(row, "volume", "last_volume"):
        reasons.append("volume_missing_or_zero")

    if row.get("volume_known") is False and "volume_missing_or_zero" not in reasons:
        warnings.append("volume_provider_incompleto")

    return not reasons, reasons, warnings


def _directional_text(row: Dict[str, Any]) -> str:
    fields = (
        "signal",
        "trade_action",
        "trade_direction",
        "trend",
        "state",
        "ai_comment",
        "market_regime_state",
        "chart_regime_state",
        "institutional_flow_state",
        "smart_money_state",
    )
    return " ".join(str(row.get(field) or "").lower() for field in fields)


def _explicit_side_from_row(row: Dict[str, Any]) -> str:
    text = _directional_text(row)
    bullish_words = ("buy", "long", "compra", "comprador", "alta", "bull", "accumulation", "institutional_buying")
    bearish_words = ("short", "sell short", "venda descoberta", "vendedor", "baixa", "bear", "distribution", "queda")
    bullish = any(word in text for word in bullish_words)
    bearish = any(word in text for word in bearish_words)
    if bullish and not bearish:
        return "bullish"
    if bearish and not bullish:
        return "bearish"
    return "mixed"


def _detect_decision_conflicts(
    row: Dict[str, Any],
    action: str,
    bullish: float | None = None,
    bearish: float | None = None,
) -> List[str]:
    conflicts: List[str] = []
    action = str(action or "").upper()
    bullish = safe_float(bullish, safe_float(row.get("bullish_pressure"), 0.0))
    bearish = safe_float(bearish, safe_float(row.get("bearish_pressure"), 0.0))
    score = safe_float(row.get("source_score", row.get("score", row.get("master_score"))), 0.0)
    side = _explicit_side_from_row(row)

    buy_score = max(
        safe_float(row.get("score_buy"), 0.0),
        safe_float(row.get("buy_score"), 0.0),
        safe_float(row.get("long_score"), 0.0),
        bullish,
    )
    short_score = max(
        safe_float(row.get("score_short"), 0.0),
        safe_float(row.get("short_score"), 0.0),
        safe_float(row.get("sell_score"), 0.0),
        bearish,
    )
    raw_signal = _state(row.get("signal"))
    raw_direction = _state(row.get("trade_direction"))

    if action == "SHORT" and (
        raw_signal in {"buy", "watch_buy", "long"}
        or raw_direction == "long"
        or side == "bullish"
        or buy_score >= short_score + 18.0
        or (score >= 70.0 and bullish >= bearish + 10.0)
    ):
        conflicts.append("score_buy_vs_final_short")
    if action == "BUY" and (
        raw_signal in {"short", "watch_short", "sell_short"}
        or raw_direction == "short"
        or side == "bearish"
        or short_score >= buy_score + 18.0
        or (score >= 70.0 and bearish >= bullish + 10.0)
    ):
        conflicts.append("score_short_vs_final_buy")
    if action in ENTRY_OR_COVER_ACTIONS and score >= 70.0 and bullish <= 0.0 and bearish <= 0.0 and side == "mixed":
        conflicts.append("strong_score_without_directional_evidence")

    return conflicts


def _score(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    return clamp(safe_float(row.get(key), default), 0.0, 100.0)


def _is_bullish_squeeze(row: Dict[str, Any]) -> bool:
    squeeze_state = _state(row.get("volatility_squeeze_state"))
    if squeeze_state not in {"squeeze_ready", "compression"}:
        return False

    bullish_context = (
        bool(row.get("above_vwap", False))
        or _score(row, "smart_money_score") >= 60
        or _score(row, "institutional_flow_score") >= 60
        or _score(row, "heat_map_score", 50.0) >= 62
    )
    return bool(bullish_context)


def _breakout_without_volume(row: Dict[str, Any]) -> bool:
    if row.get("volume_known") is False:
        return False

    breakout_state = _state(row.get("breakout_probability_state"))
    breakout_score = _score(row, "breakout_probability_score")
    rel_volume = safe_float(row.get("rel_volume"), 0.0)
    volume_score = _score(row, "volume_score")

    if breakout_state in {"ready_to_break", "building_pressure"} or breakout_score >= 55:
        return rel_volume < 1.05 and volume_score < 35
    return False


def _chart_regime(row: Dict[str, Any]) -> str:
    return _state(row.get("chart_regime_state") or row.get("market_structure_state"))


def _liquidity_event(row: Dict[str, Any]) -> str:
    return _state(row.get("liquidity_event") or row.get("liquidity_read"))


def _institutional_confidence(row: Dict[str, Any], side: str, pressure: float, opposite: float) -> float:
    regime_state = _state(row.get("market_regime_state"))
    chart_regime = _chart_regime(row)
    liquidity_event = _liquidity_event(row)
    trend_strength = safe_float(row.get("trend_strength"), 0.0)
    rel_volume = safe_float(row.get("rel_volume"), 0.0)
    flow_score = _score(row, "institutional_flow_score", 50.0)
    smart_money_score = _score(row, "smart_money_score", 50.0)

    edge = pressure - opposite
    confidence = 42.0 + max(-18.0, min(22.0, edge * 1.15))
    confidence += max(0.0, min(16.0, (trend_strength - 35.0) * 0.35))
    confidence += max(0.0, min(10.0, (rel_volume - 1.0) * 10.0))

    if side == "long":
        if regime_state == "bull_trend":
            confidence += 8.0
        if chart_regime in {"trend_up", "breakout_up", "reversal_up"}:
            confidence += 8.0
        if liquidity_event in {"sweep_low_reclaim", "bear_trap", "demand_absorption"}:
            confidence += 6.0
        if flow_score >= 65:
            confidence += 5.0
        if smart_money_score >= 65:
            confidence += 5.0
        if regime_state == "bear_trend" and liquidity_event not in {"sweep_low_reclaim", "bear_trap"}:
            confidence -= 18.0
    else:
        if regime_state == "bear_trend":
            confidence += 8.0
        if chart_regime in {"trend_down", "breakout_down", "reversal_down"}:
            confidence += 8.0
        if liquidity_event in {"sweep_high_reject", "bull_trap", "supply_absorption"}:
            confidence += 6.0
        if flow_score <= 35:
            confidence += 5.0
        if smart_money_score <= 35:
            confidence += 5.0
        if regime_state == "bull_trend" and liquidity_event not in {"sweep_high_reject", "bull_trap"}:
            confidence -= 18.0

    if chart_regime in {"chop", "range", "squeeze"}:
        confidence -= 10.0
    if row.get("data_quality") == "score_only":
        confidence -= 12.0

    return clamp(confidence, 5.0, 100.0)


def _reversal_exception(row: Dict[str, Any], side: str) -> bool:
    sweep_state = _state(row.get("liquidity_sweep_state"))
    if sweep_state != "liquidity_sweep_detected":
        return False

    above_vwap = bool(row.get("above_vwap", False))
    smart_money_score = _score(row, "smart_money_score")
    flow_score = _score(row, "institutional_flow_score")
    change_pct = safe_float(row.get("change_pct"), 0.0)

    if side == "long":
        return above_vwap and change_pct >= 0 and max(smart_money_score, flow_score) >= 60
    if side == "short":
        return (not above_vwap) and change_pct <= 0 and max(100 - smart_money_score, 100 - flow_score) >= 55
    return False


def _risk_level(blocked: List[str], warnings: List[str], row: Dict[str, Any]) -> str:
    if blocked:
        return "alto"
    if _state(row.get("market_regime_state")) == "high_volatility":
        return "alto"
    if warnings or row.get("data_quality") == "score_only" or row.get("volume_known") is False:
        return "medio"
    return "baixo"


def _action_after_block(
    action: str,
    bullish: float,
    bearish: float,
    row: Dict[str, Any],
    blocked: List[str],
    hard_block: bool = False,
) -> str:
    if not blocked:
        return action

    if hard_block:
        return NO_DECISION_ACTION

    if action == "BUY":
        return "SELL"
    if action == "SHORT":
        return "COVER"
    if action == "SELL":
        if "sell_into_bullish_squeeze" in blocked or bullish >= bearish:
            return "BUY"
        return "SELL"
    if action == "COVER":
        if bearish > bullish + 10 and _state(row.get("market_regime_state")) == "bear_trend":
            return "SHORT"
        return "COVER"
    return action


def _build_trade_instructions(action: str, row: Dict[str, Any], blocked: List[str], warnings: List[str]) -> Dict[str, Any]:
    ticker = row.get("ticker") or row.get("symbol") or "UNKNOWN"
    regime = _state(row.get("market_regime_state")) or "unknown"
    rel_volume = safe_float(row.get("rel_volume"), 0.0)
    volume_known = row.get("volume_known") is not False
    buy_volume_clause = (
        f"RVOL acima de {max(1.10, rel_volume):.2f}"
        if volume_known
        else "volume real confirmado no tape/terminal, pois o provider publico nao trouxe volume confiavel"
    )
    short_volume_clause = (
        "volume confirmando a quebra"
        if volume_known
        else "volume real confirmado no tape/terminal, pois o provider publico nao trouxe volume confiavel"
    )
    risk_parts = list(blocked or warnings or [])
    if row.get("data_quality") == "score_only":
        risk_parts.append("dados sem preco/volume real no ciclo")
    if not volume_known:
        risk_parts.append("volume real ausente no provider publico")
    if regime == "high_volatility":
        risk_parts.append("volatilidade alta")

    if action == "BUY":
        trigger = (
            f"Entrar comprado em {ticker} somente com regime nao baixista, preco defendendo VWAP/media, "
            f"fluxo comprador confirmado e {buy_volume_clause}."
        )
        invalidation = "Zerar compra se perder VWAP/suporte, fluxo institucional virar distribuicao ou regime mudar para baixa."
    elif action == "SHORT":
        trigger = (
            f"Abrir venda descoberta em {ticker} somente com regime baixista, perda de suporte/media, "
            f"pressao vendedora dominante e {short_volume_clause}."
        )
        invalidation = "Encerrar short se recuperar VWAP/resistencia, surgir absorcao compradora ou squeeze comprador ganhar confirmacao."
    elif action == "SELL":
        trigger = (
            f"Encerrar posicao comprada em {ticker} quando houver perda de tendencia, fluxo comprador fraco "
            "ou conflito de regime/liquidez contra a compra."
        )
        invalidation = "Cancelar venda/saida se o preco recuperar VWAP, volume voltar comprador e regime seguir de alta."
    elif action == "COVER":
        trigger = (
            f"Encerrar venda descoberta em {ticker} quando houver recuperacao de VWAP/media, absorcao compradora "
            "ou risco de squeeze contra o short."
        )
        invalidation = "Manter short apenas se perder suporte novamente com volume vendedor e sem defesa institucional."
    elif action == NO_DECISION_ACTION:
        trigger = (
            f"Sem decisão operacional em {ticker}: aguardar preço, volume real, qualidade de dado e coerência entre score e direção."
        )
        invalidation = "Liberar operação somente quando dados reais e direção institucional estiverem alinhados."
    else:
        trigger = "Aguardar alinhamento entre regime, liquidez, fluxo, tendencia e volatilidade."
        invalidation = "Sem entrada enquanto os filtros operacionais continuarem conflitantes."

    risk = "Risco baixo: filtros principais alinhados."
    if risk_parts:
        risk = f"Risco {_risk_level(blocked, warnings, row)}: " + "; ".join(dict.fromkeys(risk_parts[:5])) + "."

    return {
        "trigger": trigger,
        "invalidation": invalidation,
        "risk": risk,
        "risk_level": _risk_level(blocked, warnings, row),
    }


def evaluate_trade_coherence(
    row: Dict[str, Any],
    proposed_action: str,
    bullish: float | None = None,
    bearish: float | None = None,
) -> Dict[str, Any]:
    action = str(proposed_action or "SELL").upper()
    bullish = safe_float(bullish, 0.0)
    bearish = safe_float(bearish, 0.0)
    blocked: List[str] = []
    warnings: List[str] = []

    regime_state = _state(row.get("market_regime_state"))
    smart_money_state = _state(row.get("smart_money_state"))
    institutional_state = _state(row.get("institutional_flow_state"))
    liquidity_state = _state(row.get("liquidity_map_state"))
    chart_regime = _chart_regime(row)
    liquidity_event = _liquidity_event(row)
    trend_strength = safe_float(row.get("trend_strength"), 0.0)
    has_complete_market_data, data_blockers, data_warnings = _market_data_guard(row)
    decision_conflicts = _detect_decision_conflicts(row, action, bullish=bullish, bearish=bearish)

    if row.get("data_quality") == "score_only":
        warnings.append("score_only_sem_preco_real")
    warnings.extend(data_warnings)

    if action in OPERATIONAL_ACTIONS and not has_complete_market_data:
        blocked.extend(data_blockers)
    if action in OPERATIONAL_ACTIONS and decision_conflicts:
        blocked.extend(decision_conflicts)

    if action == "BUY":
        if chart_regime in {"chop", "range"} and not _reversal_exception(row, "long"):
            warnings.append("range_requires_breakout_confirmation")
        if regime_state == "bear_trend" and not _reversal_exception(row, "long"):
            blocked.append("buy_in_downtrend")
        if _breakout_without_volume(row):
            blocked.append("breakout_without_volume")
        if smart_money_state == "retail_noise" or institutional_state == "distribution_risk":
            blocked.append("buy_against_flow")
        if liquidity_event in {"sweep_high_reject", "bull_trap", "supply_absorption"}:
            blocked.append("buy_into_supply_liquidity")
        if liquidity_state == "thin_liquidity":
            warnings.append("thin_liquidity_for_long")

    elif action == "SELL":
        if _is_bullish_squeeze(row):
            blocked.append("sell_into_bullish_squeeze")
        if regime_state == "bull_trend" and _score(row, "smart_money_score") >= 60 and _score(row, "master_score", _score(row, "score")) >= 60:
            blocked.append("sell_against_bull_regime")
        if chart_regime in {"trend_up", "breakout_up"} and bullish > bearish + 8:
            warnings.append("exit_long_against_uptrend_continuation")

    elif action == "SHORT":
        if chart_regime in {"chop", "range"} and not _reversal_exception(row, "short"):
            warnings.append("range_requires_breakdown_confirmation")
        if regime_state == "bull_trend" and not _reversal_exception(row, "short"):
            blocked.append("short_in_bulltrend")
        if _is_bullish_squeeze(row):
            blocked.append("short_into_bullish_squeeze")
        if smart_money_state in {"smart_money_active", "smart_money_interest"} and regime_state != "bear_trend":
            blocked.append("short_against_smart_money")
        if _breakout_without_volume(row):
            blocked.append("short_without_volume_confirmation")
        if liquidity_event in {"sweep_low_reclaim", "bear_trap", "demand_absorption"}:
            blocked.append("short_into_demand_liquidity")

    elif action == "COVER":
        if regime_state == "bear_trend" and institutional_state == "distribution_risk" and not _reversal_exception(row, "long"):
            warnings.append("cover_against_bearish_flow")
        if chart_regime in {"trend_down", "breakout_down"} and bearish > bullish + 8:
            warnings.append("exit_short_against_downtrend_continuation")

    if regime_state == "range" and action in {"BUY", "SHORT"} and trend_strength < 35:
        blocked.append("range_without_confirmation")
    if regime_state == "high_volatility" and action in {"BUY", "SHORT"}:
        warnings.append("high_volatility_entry")

    blocked = list(dict.fromkeys(blocked))
    warnings = list(dict.fromkeys(warnings))
    hard_block = any(
        reason in set(data_blockers + decision_conflicts)
        for reason in blocked
    )
    final_action = _action_after_block(action, bullish, bearish, row, blocked, hard_block=hard_block)
    instructions = _build_trade_instructions(final_action, row, blocked, warnings)

    return {
        "proposed_action": action,
        "final_action": final_action,
        "coherence_status": "blocked" if blocked else "watch" if warnings else "ok",
        "blocked_reasons": blocked,
        "warnings": warnings,
        "decision_ready": final_action in OPERATIONAL_ACTIONS and not hard_block and not blocked,
        "conflict_detected": bool(decision_conflicts),
        "data_quality_blocked": bool(data_blockers),
        "rules": {
            "regime": regime_state or "unknown",
            "chart_regime": chart_regime or "unknown",
            "liquidity": liquidity_state or "unknown",
            "liquidity_event": liquidity_event or "none",
            "flow": institutional_state or "unknown",
            "smart_money": smart_money_state or "unknown",
            "trend_strength": round(trend_strength, 1),
            "volatility_squeeze": _state(row.get("volatility_squeeze_state")) or "unknown",
        },
        **instructions,
    }


def _weighted_component_score(row: Dict[str, Any]) -> float:
    bullish = 0.0
    bearish = 0.0

    for field, weight in _BULLISH_COMPONENTS:
        score = clamp(safe_float(row.get(field), 50.0), 0.0, 100.0)
        bullish += score * weight
        bearish += (100.0 - score) * weight

    return bullish, bearish


def _apply_state_boosts(row: Dict[str, Any], bullish: float, bearish: float) -> tuple[float, float, List[str]]:
    conflicts: List[str] = []

    regime_state = _state(row.get("market_regime_state"))
    if regime_state == "bull_trend":
        bullish += 10.0
        bearish -= 6.0
    elif regime_state == "bear_trend":
        bearish += 10.0
        bullish -= 6.0
    elif regime_state == "high_volatility":
        bullish -= 2.5
        bearish -= 2.5
        conflicts.append("high_volatility")
    elif regime_state == "range":
        conflicts.append("range")

    for field, mapping in _STATE_BULLISH_BOOSTS.items():
        state = _state(row.get(field))
        if state in mapping:
            bullish += mapping[state]
            if state in {"mixed", "building_pressure", "smart_money_interest", "early_accumulation"}:
                conflicts.append(f"{field}:{state}")

    for field, mapping in _STATE_BEARISH_BOOSTS.items():
        state = _state(row.get(field))
        if state in mapping:
            bearish += mapping[state]
            if state in {"mixed", "not_ready"}:
                conflicts.append(f"{field}:{state}")

    liquidity_state = _state(row.get("liquidity_sweep_state"))
    above_vwap = bool(row.get("above_vwap", False))
    change_pct = safe_float(row.get("change_pct"), 0.0)

    if liquidity_state == "liquidity_sweep_detected":
        if above_vwap and change_pct >= 0:
            bullish += 9.0
            conflicts.append("bullish_sweep_reversal")
        elif not above_vwap and change_pct <= 0:
            bearish += 9.0
            conflicts.append("bearish_sweep_breakdown")
        else:
            bullish += 2.0
            bearish += 2.0
            conflicts.append("sweep_unclear")
    elif liquidity_state == "sweep_watch":
        bullish += 1.5
        bearish += 1.5
        conflicts.append("sweep_watch")

    squeeze_state = _state(row.get("volatility_squeeze_state"))
    if squeeze_state == "squeeze_ready" and above_vwap:
        bullish += 4.0
    elif squeeze_state == "already_expanded" and not above_vwap:
        bearish += 4.0

    return bullish, bearish, conflicts


def _decision_reason(action: str, bullish: float, bearish: float, row: Dict[str, Any], conflicts: List[str]) -> str:
    ticker = row.get("ticker") or row.get("symbol") or "UNKNOWN"
    regime_state = row.get("market_regime_state") or "n/a"
    support = []
    if row.get("above_vwap"):
        support.append("acima da VWAP")
    if safe_float(row.get("rel_volume"), 0.0) >= 1.2:
        support.append("volume relativo forte")
    if safe_float(row.get("trend_strength"), 0.0) >= 55:
        support.append("tendencia confirmada")

    if action == "BUY":
        lead = "compra sustentada"
    elif action == "SHORT":
        lead = "pressao vendedora dominante"
    elif action == "SELL":
        lead = "perda de conviccao compradora"
    elif action == "COVER":
        lead = "risco de reversao contra a venda"
    else:
        lead = "leitura neutra"

    support_text = ", ".join(support) if support else "sinais ainda mistos"
    conflict_text = f" Conflitos: {', '.join(conflicts[:4])}." if conflicts else ""
    return (
        f"{ticker} ficou com leitura de {lead} ({support_text}). "
        f"Pressao compradora={bullish:.1f} e vendedora={bearish:.1f}; regime={regime_state}."
        f"{conflict_text}"
    )


def _neutralize_operational_decision(
    resolved: Dict[str, Any],
    row: Dict[str, Any],
    action: str,
    bullish: float | None = None,
    bearish: float | None = None,
) -> Dict[str, Any]:
    has_complete_market_data, data_blockers, data_warnings = _market_data_guard(row)
    decision_conflicts = _detect_decision_conflicts(row, action, bullish=bullish, bearish=bearish)
    blocked_reasons = list(dict.fromkeys(list(resolved.get("blocked_reasons") or []) + data_blockers + decision_conflicts))
    warnings = list(dict.fromkeys(list(resolved.get("warnings") or []) + data_warnings))
    hard_block = bool(data_blockers or decision_conflicts)

    if action in OPERATIONAL_ACTIONS and hard_block:
        resolved["signal"] = NO_DECISION_ACTION
        resolved["trade_action"] = NO_DECISION_ACTION
        resolved["trade_direction"] = "flat"
        resolved["trade_confidence"] = 0.0
        resolved["coherence_status"] = "blocked"
        resolved["trigger"] = (
            "Sem decisão operacional: aguardando preço, volume real, qualidade de dado e coerência entre score e direção."
        )
        resolved["invalidation"] = "Operar somente quando o dado real e a direção institucional estiverem alinhados."
        resolved["risk"] = "Risco alto: " + "; ".join(blocked_reasons[:6]) + "."
        resolved["risk_level"] = "alto"
        resolved["reason"] = resolved.get("reason") or "Decisão bloqueada por trava de segurança."

    resolved["blocked_reasons"] = blocked_reasons
    resolved["warnings"] = warnings
    resolved["decision_ready"] = bool(
        resolved.get("trade_action") in OPERATIONAL_ACTIONS
        and has_complete_market_data
        and not decision_conflicts
        and not blocked_reasons
    )
    resolved["conflict_detected"] = bool(decision_conflicts or resolved.get("conflict_detected"))
    resolved["data_quality_blocked"] = bool(data_blockers)
    resolved["data_quality"] = row.get("data_quality") or ("priced" if has_complete_market_data else "score_only")
    return resolved


def resolve_trade_action(row: Dict[str, Any]) -> Dict[str, Any]:
    bullish, bearish = _weighted_component_score(row)
    bullish, bearish, conflicts = _apply_state_boosts(row, bullish, bearish)

    bullish = clamp(bullish, 0.0, 100.0)
    bearish = clamp(bearish, 0.0, 100.0)
    diff = bullish - bearish
    regime_state = _state(row.get("market_regime_state"))
    above_vwap = bool(row.get("above_vwap", False))
    liquidity_state = _state(row.get("liquidity_sweep_state"))
    chart_regime = _chart_regime(row)
    liquidity_event = _liquidity_event(row)

    long_confidence = _institutional_confidence(row, "long", bullish, bearish)
    short_confidence = _institutional_confidence(row, "short", bearish, bullish)

    if chart_regime in {"trend_down", "breakout_down"} and short_confidence >= 62 and bearish >= bullish:
        bearish += 5.0
    if chart_regime in {"trend_up", "breakout_up"} and long_confidence >= 62 and bullish >= bearish:
        bullish += 5.0
    if liquidity_event in {"sweep_high_reject", "bull_trap", "supply_absorption"}:
        bearish += 4.0
        bullish -= 2.0
        conflicts.append(liquidity_event)
    elif liquidity_event in {"sweep_low_reclaim", "bear_trap", "demand_absorption"}:
        bullish += 4.0
        bearish -= 2.0
        conflicts.append(liquidity_event)

    bullish = clamp(bullish, 0.0, 100.0)
    bearish = clamp(bearish, 0.0, 100.0)
    diff = bullish - bearish
    long_confidence = _institutional_confidence(row, "long", bullish, bearish)
    short_confidence = _institutional_confidence(row, "short", bearish, bullish)

    action = "SELL"
    if diff >= 16.0 and bullish >= 60.0 and long_confidence >= 58:
        action = "BUY"
    elif diff <= -16.0 and bearish >= 60.0 and short_confidence >= 58:
        action = "SHORT"
    elif regime_state == "bear_trend" and bearish >= bullish:
        action = "SHORT" if bearish >= 55.0 and short_confidence >= 56 else "COVER"
    elif regime_state == "bull_trend" and bullish >= bearish:
        action = "BUY" if bullish >= 55.0 and long_confidence >= 56 else "SELL"
    elif liquidity_state == "liquidity_sweep_detected" and above_vwap and bullish >= bearish:
        action = "BUY"
    elif liquidity_state == "liquidity_sweep_detected" and not above_vwap and bearish >= bullish:
        action = "SHORT"
    elif chart_regime in {"breakout_down", "trend_down"} and short_confidence >= 62 and bearish >= bullish + 4:
        action = "SHORT"
    elif chart_regime in {"breakout_up", "trend_up"} and long_confidence >= 62 and bullish >= bearish + 4:
        action = "BUY"
    elif bullish >= bearish:
        action = "BUY" if bullish >= 52.0 and long_confidence >= 58 else "SELL"
    else:
        action = "SHORT" if bearish >= 52.0 and short_confidence >= 58 else "COVER"

    if action == "SELL" and bearish > bullish and regime_state in {"bear_trend", "high_volatility"}:
        action = "COVER"
    if action == "COVER" and bullish > bearish + 10.0 and above_vwap:
        action = "BUY"

    coherence = evaluate_trade_coherence(row, action, bullish=bullish, bearish=bearish)
    action = coherence["final_action"]

    side_confidence = 0.0 if action == NO_DECISION_ACTION else long_confidence if action in {"BUY", "SELL"} else short_confidence
    confidence = clamp(side_confidence + (safe_float(row.get("score"), 0.0) - 50.0) * 0.08, 5.0, 100.0)
    confidence = clamp(
        confidence
        - len(coherence["blocked_reasons"]) * 12.0
        - len(coherence["warnings"]) * 4.0,
        5.0,
        100.0,
    )

    trade_direction = {
        "BUY": "long",
        "SELL": "exit_long",
        "SHORT": "short",
        "COVER": "exit_short",
        NO_DECISION_ACTION: "flat",
    }.get(action, "flat")

    reason = _decision_reason(action, bullish, bearish, row, conflicts)

    payload = {
        "signal": action,
        "trade_action": action,
        "trade_direction": trade_direction,
        "trade_confidence": round(confidence, 1),
        "long_confidence": round(long_confidence, 1),
        "short_confidence": round(short_confidence, 1),
        "trade_bias": round(bullish - bearish, 1),
        "bullish_pressure": round(bullish, 1),
        "bearish_pressure": round(bearish, 1),
        "market_regime_state": regime_state or "unknown",
        "chart_regime_state": chart_regime or "unknown",
        "liquidity_event": liquidity_event or "none",
        "conflicts": conflicts[:6],
        "conflict_detected": bool(coherence.get("conflict_detected")),
        "decision_ready": bool(coherence.get("decision_ready")),
        "data_quality": row.get("data_quality") or ("priced" if not coherence.get("data_quality_blocked") else "score_only"),
        "coherence_status": coherence["coherence_status"],
        "blocked_reasons": coherence["blocked_reasons"],
        "warnings": coherence["warnings"],
        "coherence_rules": coherence["rules"],
        "trigger": coherence["trigger"],
        "invalidation": coherence["invalidation"],
        "risk": coherence["risk"],
        "risk_level": coherence["risk_level"],
        "reason": reason,
    }
    return _neutralize_operational_decision(payload, row, action, bullish=bullish, bearish=bearish)


def summarize_trade_decision(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = [row for row in rows or [] if isinstance(row, dict)]

    if not candidates:
        return {
            "signal": "NO_DECISION",
            "trade_action": "NO_DECISION",
            "trade_direction": "flat",
            "trade_confidence": 0.0,
            "trade_bias": 0.0,
            "bullish_pressure": 0.0,
            "bearish_pressure": 0.0,
            "market_regime_state": "unknown",
            "conflicts": [],
            "conflict_detected": False,
            "reason": "Sem master score suficiente para consolidar uma decisao.",
            "decision_ready": False,
            "data_quality": "score_only",
        }

    top = max(
        candidates,
        key=lambda row: (
            safe_float(row.get("trade_confidence"), 0.0),
            safe_float(row.get("score"), 0.0),
        ),
    )
    if top.get("trade_action") or top.get("signal") in {"BUY", "SELL", "SHORT", "COVER"}:
        resolved = dict(top)
        action = str(resolved.get("trade_action") or resolved.get("signal") or "SELL").upper()
        resolved["signal"] = action
        resolved["trade_action"] = action
        resolved["trade_direction"] = resolved.get("trade_direction") or {
            "BUY": "long",
            "SELL": "exit_long",
            "SHORT": "short",
            "COVER": "exit_short",
            NO_DECISION_ACTION: "flat",
        }.get(action, "exit_long")
        resolved["trade_confidence"] = round(safe_float(resolved.get("trade_confidence"), safe_float(resolved.get("confidence"), 0.0)), 1)
        resolved["trade_bias"] = round(safe_float(resolved.get("trade_bias"), 0.0), 1)
        resolved["bullish_pressure"] = round(safe_float(resolved.get("bullish_pressure"), 0.0), 1)
        resolved["bearish_pressure"] = round(safe_float(resolved.get("bearish_pressure"), 0.0), 1)
        resolved["market_regime_state"] = resolved.get("market_regime_state") or "unknown"
        resolved["conflicts"] = list(resolved.get("conflicts") or [])
        resolved["reason"] = resolved.get("reason") or "Master score consolidado."
        resolved.setdefault("coherence_status", "unknown")
        resolved.setdefault("blocked_reasons", [])
        resolved.setdefault("warnings", [])
        resolved.setdefault("coherence_rules", {})
        resolved.setdefault("trigger", "Aguardar confirmacao operacional antes de executar.")
        resolved.setdefault("invalidation", "Sair se o contexto de regime, fluxo ou liquidez virar contra.")
        resolved.setdefault("risk", "Risco nao detalhado no payload original.")
        resolved.setdefault("risk_level", "medio")
        resolved = _neutralize_operational_decision(
            resolved,
            top,
            action,
            bullish=safe_float(resolved.get("bullish_pressure"), None),
            bearish=safe_float(resolved.get("bearish_pressure"), None),
        )
    else:
        resolved = resolve_trade_action(top)

    resolved["ticker"] = top.get("ticker") or top.get("symbol") or "UNKNOWN"
    resolved["score"] = round(safe_float(top.get("score"), 0.0), 1)
    if resolved.get("trade_action") not in OPERATIONAL_ACTIONS:
        resolved["decision_ready"] = False
    return resolved
