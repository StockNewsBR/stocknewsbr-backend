from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import clamp, safe_float


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


def _action_after_block(action: str, bullish: float, bearish: float, row: Dict[str, Any], blocked: List[str]) -> str:
    if not blocked:
        return action

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

    if row.get("data_quality") == "score_only":
        warnings.append("score_only_sem_preco_real")

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
        warnings.append("trend_not_confirmed")
    if regime_state == "high_volatility" and action in {"BUY", "SHORT"}:
        warnings.append("high_volatility_entry")

    final_action = _action_after_block(action, bullish, bearish, row, blocked)
    instructions = _build_trade_instructions(final_action, row, blocked, warnings)

    return {
        "proposed_action": action,
        "final_action": final_action,
        "coherence_status": "blocked" if blocked else "watch" if warnings else "ok",
        "blocked_reasons": blocked,
        "warnings": warnings,
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

    side_confidence = long_confidence if action in {"BUY", "SELL"} else short_confidence
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
    }[action]

    reason = _decision_reason(action, bullish, bearish, row, conflicts)

    return {
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
            "reason": "Sem master score suficiente para consolidar uma decisao.",
            "decision_ready": False,
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
    else:
        resolved = resolve_trade_action(top)

    resolved["ticker"] = top.get("ticker") or top.get("symbol") or "UNKNOWN"
    resolved["score"] = round(safe_float(top.get("score"), 0.0), 1)
    resolved["decision_ready"] = resolved.get("trade_action") in {"BUY", "SELL", "SHORT", "COVER"}
    return resolved
