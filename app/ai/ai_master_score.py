from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, clamp, safe_float, top_n
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.services.snapshot_contract import (
    BULLISH_ACTIONS,
    BEARISH_ACTIONS,
    ACTIONABLE_SIGNALS,
    coerce_data_quality,
    data_quality_label,
    data_quality_score,
    snapshot_signal_value,
)


MASTER_BULLISH = "BULLISH"
MASTER_BEARISH = "BEARISH"
MASTER_NEUTRAL = "NEUTRAL"
MASTER_DIRECTIONS = {MASTER_BULLISH, MASTER_BEARISH, MASTER_NEUTRAL}
MASTER_STATUSES = {AUDIT_APPROVED, AUDIT_CAUTION, AUDIT_BLOCKED}

OFFICIAL_AI_TOOLS = (
    "flow",
    "liquidity",
    "trend",
    "momentum",
    "smart_money",
    "risk",
    "news",
    "macro",
    "regime",
)

REASON_FIELDS = {
    "flow": "flow_reason",
    "liquidity": "liquidity_reason",
    "trend": "trend_reason",
    "momentum": "momentum_reason",
    "smart_money": "smart_money_reason",
    "risk": "risk_reason",
    "news": "news_reason",
    "macro": "macro_reason",
    "regime": "regime_reason",
}

AI_WEIGHTS = {
    "flow": 0.13,
    "liquidity": 0.10,
    "trend": 0.14,
    "momentum": 0.10,
    "smart_money": 0.14,
    "risk": 0.10,
    "news": 0.07,
    "macro": 0.07,
    "regime": 0.15,
}

CORE_CONTEXT_TOOLS = ("flow", "liquidity", "trend", "smart_money", "regime")
STRUCTURE_TOOLS = ("trend", "regime")
INSTITUTIONAL_TOOLS = ("flow", "liquidity", "smart_money")

MASTER_CONTRACT_FIELDS = (
    "master_score",
    "master_direction",
    "master_conviction",
    "master_confidence",
    "master_summary",
    "master_reasoning",
    "master_risk",
    "master_status",
    "master_visual_status",
    "master_visual_label",
    "master_consensus",
    "master_components",
    "opinion_change_conditions",
)


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _state(value: Any) -> str:
    return str(value or "").strip().lower()


def _listify(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _audit_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
    institutional = row.get("institutional_auditor") if isinstance(row.get("institutional_auditor"), dict) else {}
    return {**auditor, **institutional, **{key: row.get(key) for key in row if str(key).startswith("audit_") or str(key).startswith("auditor_")}}


def _audit_status(row: Dict[str, Any]) -> str:
    audit = _audit_payload(row)
    status = str(
        row.get("audit_status")
        or row.get("auditor_status")
        or audit.get("audit_status")
        or audit.get("auditor_status")
        or AUDIT_APPROVED
    ).upper().strip()
    return status if status in MASTER_STATUSES else AUDIT_APPROVED


def _audit_score(row: Dict[str, Any]) -> float:
    audit = _audit_payload(row)
    return clamp(safe_float(row.get("audit_score") or row.get("auditor_score") or audit.get("audit_score") or audit.get("auditor_score"), 92.0))


def _tool_index(ai_tools: Dict[str, Any] | None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    output: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if not isinstance(ai_tools, dict):
        return output
    for tool, rows in ai_tools.items():
        if not isinstance(rows, list):
            continue
        output[str(tool)] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = _ticker(row)
            if ticker and ticker not in output[str(tool)]:
                output[str(tool)][ticker] = row
    return output


def _tool_row(index: Dict[str, Dict[str, Dict[str, Any]]], tool: str, ticker: str) -> Dict[str, Any]:
    return dict(index.get(tool, {}).get(ticker, {}))


def _metric(row: Dict[str, Any], key: str, default: Any = None) -> Any:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return metrics.get(key, row.get(key, default))


def _pseudo_tool_rows_from_feature_row(row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    flow_score = safe_float(row.get("institutional_flow_score"), safe_float(row.get("flow_score"), 50.0))
    liquidity_sweep = safe_float(row.get("liquidity_sweep_score"), 50.0)
    liquidity_map = safe_float(row.get("liquidity_map_score"), 50.0)
    momentum_score = max(
        safe_float(row.get("radar_score"), 0.0),
        safe_float(row.get("breakout_probability_score"), 0.0),
        safe_float(row.get("heat_map_score"), 0.0),
        safe_float(row.get("momentum_score"), 0.0),
    )
    smart_score = max(
        safe_float(row.get("smart_money_score"), 0.0),
        safe_float(row.get("accumulation_score"), 0.0),
        safe_float(row.get("absorption_score"), 0.0),
    )
    trend_score = safe_float(row.get("trend_strength"), safe_float(row.get("trend_score"), 50.0))
    regime_score = safe_float(row.get("market_regime_score"), safe_float(row.get("regime_score"), 50.0))
    risk_level = str(row.get("risk_level") or "").lower()
    risk_score = {"baixo": 25.0, "low": 25.0, "medio": 55.0, "medium": 55.0, "moderado": 55.0, "alto": 82.0, "high": 82.0}.get(risk_level, 38.0)
    return {
        "flow": {"ticker": _ticker(row), "tool": "flow", "score": flow_score, "state": row.get("institutional_flow_state") or row.get("flow_state")},
        "liquidity": {"ticker": _ticker(row), "tool": "liquidity", "score": max(liquidity_sweep, liquidity_map), "state": row.get("liquidity_map_state") or row.get("liquidity_sweep_state")},
        "trend": {"ticker": _ticker(row), "tool": "trend", "score": trend_score, "state": row.get("trend_state") or row.get("chart_regime_state") or row.get("market_regime_state")},
        "momentum": {"ticker": _ticker(row), "tool": "momentum", "score": momentum_score, "state": row.get("radar_state") or row.get("breakout_probability_state") or row.get("heat_map_state")},
        "smart_money": {"ticker": _ticker(row), "tool": "smart_money", "score": smart_score, "state": row.get("smart_money_state") or row.get("accumulation_state")},
        "risk": {"ticker": _ticker(row), "tool": "risk", "score": risk_score, "state": row.get("risk_state") or risk_level or "low_risk", "metrics": {"risk_score": risk_score}},
        "news": {"ticker": _ticker(row), "tool": "news", "score": safe_float(row.get("news_score"), 35.0), "state": row.get("news_state") or "news_not_linked"},
        "macro": {"ticker": _ticker(row), "tool": "macro", "score": safe_float(row.get("macro_score"), 35.0), "state": row.get("macro_state") or "macro_unavailable"},
        "regime": {"ticker": _ticker(row), "tool": "regime", "score": regime_score, "state": row.get("market_regime_state") or row.get("regime_state"), "metrics": {"regime_state": row.get("market_regime_state") or row.get("regime_state")}},
    }


def _direction_from_text(tool: str, row: Dict[str, Any], base_row: Dict[str, Any]) -> str:
    if not row:
        return MASTER_NEUTRAL

    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    state = _state(row.get("state") or metrics.get(f"{tool}_state") or metrics.get("regime_state"))
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("signal"),
            row.get("trade_action"),
            row.get("ai_comment"),
            row.get("reason"),
            state,
            metrics.get("impact"),
            metrics.get("macro_state"),
            metrics.get("news_state"),
        )
    )
    score = clamp(safe_float(row.get("score"), 50.0))

    if tool == "risk":
        return MASTER_NEUTRAL

    bearish_terms = (
        "bear",
        "baixa",
        "downtrend",
        "selling",
        "sell",
        "short",
        "distribution",
        "distribuicao",
        "distribuição",
        "vendedor",
        "strong_selling",
        "downtrend_structure",
        "institutional_distribution",
        "bear_trend",
        "trend_down",
        "macro negativo",
        "negative",
    )
    bullish_terms = (
        "bull",
        "alta",
        "uptrend",
        "buying",
        "buy",
        "long",
        "accumulation",
        "acumulacao",
        "acumulação",
        "comprador",
        "strong_buying",
        "uptrend_structure",
        "institutional_accumulation",
        "institutional_buying",
        "bull_trend",
        "trend_up",
        "positive",
        "positivo",
    )
    neutral_terms = (
        "neutral",
        "neutro",
        "range",
        "sideways",
        "lateral",
        "not_linked",
        "unavailable",
        "empty",
        "mixed",
        "monitoring",
    )

    bullish_hit = any(term in text for term in bullish_terms)
    bearish_hit = any(term in text for term in bearish_terms)
    if bullish_hit and not bearish_hit:
        return MASTER_BULLISH
    if bearish_hit and not bullish_hit:
        return MASTER_BEARISH
    if any(term in text for term in neutral_terms):
        return MASTER_NEUTRAL

    if tool in {"flow", "liquidity", "trend", "momentum", "smart_money", "regime"} and score >= 72:
        signal = snapshot_signal_value(base_row)
        if signal in BULLISH_ACTIONS:
            return MASTER_BULLISH
        if signal in BEARISH_ACTIONS:
            return MASTER_BEARISH
    return MASTER_NEUTRAL


def _risk_level(row: Dict[str, Any], tool_rows: Dict[str, Dict[str, Any]]) -> str:
    risk_row = tool_rows.get("risk", {})
    metrics = risk_row.get("metrics") if isinstance(risk_row.get("metrics"), dict) else {}
    state_text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("risk_level"),
            row.get("risk"),
            risk_row.get("state"),
            risk_row.get("ai_comment"),
            metrics.get("risk_summary"),
        )
    )
    risk_score = clamp(safe_float(metrics.get("risk_score") or risk_row.get("risk_score") or risk_row.get("score"), 45.0))
    if "critical" in state_text or "critico" in state_text or "crítico" in state_text or "alto" in state_text or "high" in state_text or risk_score >= 70:
        return "Alto"
    if "medium" in state_text or "medio" in state_text or "médio" in state_text or "moderado" in state_text or risk_score >= 45:
        return "Moderado"
    return "Baixo"


def _reason_for_tool(tool: str, row: Dict[str, Any], direction: str) -> str:
    if not row:
        return f"{tool} sem leitura suficiente no snapshot."
    score = clamp(safe_float(row.get("score"), 0.0))
    state = row.get("state") or _metric(row, f"{tool}_state") or "sem estado"
    comment = str(row.get("ai_comment") or row.get("reason") or "").strip()
    prefix = f"{tool} {direction.lower()} com score {score:.1f} e estado {state}."
    if comment:
        return f"{prefix} {comment[:180]}"
    return prefix


def _context_available(directions: Dict[str, str], direction: str) -> bool:
    core = sum(1 for tool in CORE_CONTEXT_TOOLS if directions.get(tool) == direction)
    structure = sum(1 for tool in STRUCTURE_TOOLS if directions.get(tool) == direction)
    institutional = sum(1 for tool in INSTITUTIONAL_TOOLS if directions.get(tool) == direction)
    return core >= 3 and structure >= 1 and institutional >= 1


def _weighted_direction_score(tool_rows: Dict[str, Dict[str, Any]], directions: Dict[str, str], direction: str) -> float:
    total_weight = 0.0
    weighted = 0.0
    for tool in OFFICIAL_AI_TOOLS:
        if tool == "risk" or directions.get(tool) != direction:
            continue
        row = tool_rows.get(tool, {})
        score = clamp(safe_float(row.get("score"), 50.0))
        weight = AI_WEIGHTS.get(tool, 0.0)
        total_weight += weight
        weighted += score * weight
    return weighted / total_weight if total_weight else 0.0


def _choose_direction(directions: Dict[str, str], tool_rows: Dict[str, Dict[str, Any]]) -> str:
    bullish_ok = _context_available(directions, MASTER_BULLISH)
    bearish_ok = _context_available(directions, MASTER_BEARISH)
    bullish_score = _weighted_direction_score(tool_rows, directions, MASTER_BULLISH)
    bearish_score = _weighted_direction_score(tool_rows, directions, MASTER_BEARISH)
    bullish_opposition = sum(1 for value in directions.values() if value == MASTER_BEARISH)
    bearish_opposition = sum(1 for value in directions.values() if value == MASTER_BULLISH)

    if bullish_ok and bearish_ok:
        if abs(bullish_score - bearish_score) < 8 or abs(bullish_opposition - bearish_opposition) <= 1:
            return MASTER_NEUTRAL
        return MASTER_BULLISH if bullish_score > bearish_score else MASTER_BEARISH
    if bullish_ok and bullish_score >= 58 and bullish_opposition <= 3:
        return MASTER_BULLISH
    if bearish_ok and bearish_score >= 58 and bearish_opposition <= 3:
        return MASTER_BEARISH
    return MASTER_NEUTRAL


def _consensus(directions: Dict[str, str], direction: str) -> Dict[str, Any]:
    counts = {
        MASTER_BULLISH: sum(1 for value in directions.values() if value == MASTER_BULLISH),
        MASTER_BEARISH: sum(1 for value in directions.values() if value == MASTER_BEARISH),
        MASTER_NEUTRAL: sum(1 for value in directions.values() if value == MASTER_NEUTRAL),
    }
    aligned = counts.get(direction, 0) if direction in {MASTER_BULLISH, MASTER_BEARISH} else max(counts.values() or [0])
    opposite = counts[MASTER_BEARISH] if direction == MASTER_BULLISH else counts[MASTER_BULLISH] if direction == MASTER_BEARISH else min(counts[MASTER_BULLISH], counts[MASTER_BEARISH])
    ratio = aligned / max(1, len(OFFICIAL_AI_TOOLS))
    return {
        "aligned_count": aligned,
        "opposing_count": opposite,
        "neutral_count": counts[MASTER_NEUTRAL],
        "bullish_count": counts[MASTER_BULLISH],
        "bearish_count": counts[MASTER_BEARISH],
        "total": len(OFFICIAL_AI_TOOLS),
        "ratio": round(ratio, 4),
        "directions": dict(directions),
    }


def _conviction(status: str, direction: str, consensus: Dict[str, Any]) -> str:
    if status == AUDIT_BLOCKED or direction == MASTER_NEUTRAL:
        return "Baixa"
    aligned = int(consensus.get("aligned_count", 0) or 0)
    opposing = int(consensus.get("opposing_count", 0) or 0)
    if aligned >= 6 and opposing <= 1:
        return "Alta"
    if aligned >= 4 and opposing <= 2:
        return "Média"
    return "Baixa"


def _confidence(status: str, row: Dict[str, Any], consensus: Dict[str, Any]) -> str:
    if status == AUDIT_BLOCKED:
        return "Baixa"
    quality = data_quality_score(coerce_data_quality(row))
    audit = _audit_score(row)
    ratio = float(consensus.get("ratio", 0.0) or 0.0) * 100.0
    conflict_penalty = 25.0 if row.get("conflict_detected") else 0.0
    value = quality * 0.38 + audit * 0.27 + ratio * 0.25 + max(0.0, 100.0 - conflict_penalty) * 0.10
    if status == AUDIT_CAUTION:
        value = min(value, 74.0)
    if value >= 78:
        return "Alta"
    if value >= 55:
        return "Média"
    return "Baixa"


def _score_band(score: float, status: str) -> tuple[str, str]:
    if status == AUDIT_BLOCKED:
        return "Não Operar", "🔴 Não Operar"
    if score >= 80:
        return "Forte", "🟢 Forte"
    if score >= 60:
        return "Atenção", "🟡 Atenção"
    if score >= 40:
        return "Atenção", "🟡 Atenção"
    return "Não Operar", "🔴 Não Operar"


def _master_score_value(
    *,
    status: str,
    direction: str,
    row: Dict[str, Any],
    tool_rows: Dict[str, Dict[str, Any]],
    consensus: Dict[str, Any],
    risk: str,
) -> float:
    audit = _audit_score(row)
    quality = data_quality_score(coerce_data_quality(row))

    if status == AUDIT_BLOCKED:
        return round(min(39.0, max(0.0, audit)), 1)

    if direction == MASTER_NEUTRAL:
        neutral_base = 42.0 + min(12.0, consensus.get("neutral_count", 0) * 2.0) + quality * 0.06
        if status == AUDIT_CAUTION:
            neutral_base = min(neutral_base, 55.0)
        return round(clamp(neutral_base, 0.0, 59.0), 1)

    aligned_score = _weighted_direction_score(tool_rows, consensus.get("directions", {}), direction)
    consensus_score = float(consensus.get("ratio", 0.0) or 0.0) * 100.0
    score = aligned_score * 0.50 + consensus_score * 0.22 + audit * 0.17 + quality * 0.11
    score += 5.0 if _context_available(consensus.get("directions", {}), direction) else -12.0
    score -= int(consensus.get("opposing_count", 0) or 0) * 4.0
    if risk == "Alto":
        score -= 18.0
    elif risk == "Moderado":
        score -= 6.0
    if status == AUDIT_CAUTION:
        score = min(score, 79.0)
    return round(clamp(score), 1)


def _summary(direction: str, status: str, risk: str, tool_rows: Dict[str, Dict[str, Any]], consensus: Dict[str, Any], row: Dict[str, Any]) -> str:
    audit = _audit_payload(row)
    blocks = _listify(row.get("audit_blocks") or audit.get("audit_blocks"))
    warnings = _listify(row.get("audit_warnings") or audit.get("audit_warnings"))
    if status == AUDIT_BLOCKED:
        reasons = blocks or warnings or ["bloqueio institucional"]
        return "⚠️ NÃO OPERAR AGORA. Motivos: " + "; ".join(reasons[:5]) + "."

    readable = {
        "flow": "fluxo",
        "liquidity": "liquidez",
        "trend": "tendência",
        "momentum": "momentum",
        "smart_money": "smart money",
        "news": "notícias",
        "macro": "macro",
        "regime": "regime",
    }
    aligned = [
        readable[tool]
        for tool, direction_value in (consensus.get("directions") or {}).items()
        if tool in readable and direction_value == direction
    ][:4]
    if direction == MASTER_BULLISH:
        base = "Viés comprador"
    elif direction == MASTER_BEARISH:
        base = "Viés vendedor"
    else:
        base = "Cenário neutro"
    if aligned:
        return f"{base}: {', '.join(aligned)} alinhados. Risco {risk.lower()} e consenso {consensus.get('aligned_count', 0)}/{consensus.get('total', 9)}."
    return f"{base}: contexto ainda sem alinhamento institucional suficiente. Risco {risk.lower()}."


def _opinion_change_conditions(direction: str, status: str, risk: str, row: Dict[str, Any]) -> List[str]:
    audit = _audit_payload(row)
    blocks = _listify(row.get("audit_blocks") or audit.get("audit_blocks"))
    if status == AUDIT_BLOCKED:
        conditions = [f"resolver bloqueio: {block}" for block in blocks[:4]]
        return conditions or ["restaurar data quality", "normalizar liquidez", "remover conflito institucional"]
    if direction == MASTER_BULLISH:
        conditions = [
            "perda da VWAP",
            "fluxo vendedor persistente",
            "aumento do risco",
            "deterioração da liquidez",
            "regime migrar para lateral ou baixa",
        ]
    elif direction == MASTER_BEARISH:
        conditions = [
            "recuperação da VWAP",
            "fluxo comprador persistente",
            "smart money voltar a acumular",
            "redução da pressão vendedora",
            "regime deixar de favorecer queda",
        ]
    else:
        conditions = [
            "confirmação de tendência",
            "fluxo institucional dominante",
            "liquidez adequada",
            "redução dos conflitos entre IAs",
        ]
    if risk == "Alto" and "redução do risco" not in conditions:
        conditions.append("redução do risco")
    return conditions


def _decision_from_master(row: Dict[str, Any], direction: str, status: str, score: float, confidence: str) -> Dict[str, Any]:
    signal = snapshot_signal_value(row)
    aligned = (
        direction == MASTER_BULLISH and signal in BULLISH_ACTIONS
    ) or (
        direction == MASTER_BEARISH and signal in BEARISH_ACTIONS
    )
    if status == AUDIT_BLOCKED or direction == MASTER_NEUTRAL or signal not in ACTIONABLE_SIGNALS or not aligned:
        reasons = []
        if status == AUDIT_BLOCKED:
            reasons.append("auditor bloqueou")
        if direction == MASTER_NEUTRAL:
            reasons.append("contexto institucional insuficiente")
        if signal in ACTIONABLE_SIGNALS and not aligned:
            reasons.append("direção do Score Mestre não confirma o sinal")
        return {
            "signal": "NO_DECISION",
            "trade_action": "NO_DECISION",
            "trade_direction": "flat",
            "trade_confidence": 0.0,
            "decision_ready": False,
            "decision_state": "DO_NOT_TRADE" if status == AUDIT_BLOCKED else "NO_TRADE",
            "operational_message": "⚠️ NÃO OPERAR AGORA",
            "no_trade_reasons": reasons or ["sem contexto operacional"],
            "can_trade": False,
        }
    confidence_value = {"Alta": 88.0, "Média": 68.0, "Baixa": 42.0}.get(confidence, 42.0)
    confidence_value = clamp((confidence_value + score) / 2.0)
    return {
        "signal": signal,
        "trade_action": signal,
        "trade_direction": {"BUY": "long", "COVER": "exit_short", "SELL": "exit_long", "SHORT": "short"}.get(signal, "flat"),
        "trade_confidence": round(confidence_value, 1),
        "decision_ready": bool(row.get("decision_ready") is True and status != AUDIT_BLOCKED),
        "decision_state": row.get("decision_state") or {"BUY": "BUY_READY", "SHORT": "SHORT_READY", "SELL": "SELL_READY", "COVER": "SELL_READY"}.get(signal),
        "operational_message": row.get("operational_message") or "",
        "no_trade_reasons": list(row.get("no_trade_reasons") or []),
        "can_trade": bool(row.get("can_trade") is True or row.get("decision_ready") is True),
    }


def _score_row(
    row: Dict[str, Any],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ticker = _ticker(row) or "UNKNOWN"
    index = _tool_index(ai_tools)
    pseudo_rows = _pseudo_tool_rows_from_feature_row(row)
    tool_rows = {
        tool: _tool_row(index, tool, ticker) or pseudo_rows.get(tool, {})
        for tool in OFFICIAL_AI_TOOLS
    }
    directions = {tool: _direction_from_text(tool, tool_rows.get(tool, {}), row) for tool in OFFICIAL_AI_TOOLS}
    status = _audit_status(row)
    risk = _risk_level(row, tool_rows)
    direction = MASTER_NEUTRAL if status == AUDIT_BLOCKED else _choose_direction(directions, tool_rows)
    consensus = _consensus(directions, direction)
    conviction = _conviction(status, direction, consensus)
    confidence = _confidence(status, row, consensus)
    score = _master_score_value(
        status=status,
        direction=direction,
        row=row,
        tool_rows=tool_rows,
        consensus=consensus,
        risk=risk,
    )
    visual_status, visual_label = _score_band(score, status)
    reasoning = {
        field: _reason_for_tool(tool, tool_rows.get(tool, {}), directions.get(tool, MASTER_NEUTRAL))
        for tool, field in REASON_FIELDS.items()
    }
    summary = _summary(direction, status, risk, tool_rows, consensus, row)
    opinion_change_conditions = _opinion_change_conditions(direction, status, risk, row)
    decision = _decision_from_master(row, direction, status, score, confidence)
    market_pulse_payload = dict(market_pulse) if isinstance(market_pulse, dict) else {}

    state = {
        (MASTER_BULLISH, "Forte"): "bullish_strong",
        (MASTER_BULLISH, "Atenção"): "bullish_caution",
        (MASTER_BEARISH, "Forte"): "bearish_strong",
        (MASTER_BEARISH, "Atenção"): "bearish_caution",
        (MASTER_NEUTRAL, "Atenção"): "neutral_context",
        (MASTER_NEUTRAL, "Não Operar"): "blocked_context",
    }.get((direction, visual_status), "blocked_context" if status == AUDIT_BLOCKED else "neutral_context")

    metrics = {
        "master_score": score,
        "master_direction": direction,
        "master_status": status,
        "master_conviction": conviction,
        "master_confidence": confidence,
        "master_risk": risk,
        "consensus": consensus,
        "component_directions": directions,
        "component_scores": {tool: round(clamp(safe_float(tool_rows.get(tool, {}).get("score"), 0.0)), 1) for tool in OFFICIAL_AI_TOOLS},
        "data_quality": coerce_data_quality(row),
        "data_quality_label": data_quality_label(coerce_data_quality(row)),
        "data_quality_score": data_quality_score(coerce_data_quality(row)),
        "audit_status": status,
        "audit_score": _audit_score(row),
        "market_pulse": market_pulse_payload,
    }
    payload = build_payload(
        row=row,
        tool="master_score",
        score=score,
        state=state,
        ai_comment=summary,
        trigger=decision.get("operational_message") or "Aguardar confirmação do Score Mestre antes de executar.",
        invalidation="; ".join(opinion_change_conditions[:4]),
        metrics=metrics,
        reason=(
            f"Score Mestre sintetizou {len(OFFICIAL_AI_TOOLS)} IAs, Auditor {status}, "
            f"Market Pulse {market_pulse_payload.get('sentiment', 'indefinido')} e risco {risk}."
        ),
    )
    payload.update(decision)
    payload.update(
        {
            "ticker": ticker,
            "symbol": ticker,
            "score": score,
            "_rank_score": score,
            "master_score": score,
            "master_direction": direction,
            "master_conviction": conviction,
            "master_confidence": confidence,
            "master_summary": summary,
            "master_reasoning": reasoning,
            "master_risk": risk,
            "master_status": status,
            "master_visual_status": visual_status,
            "master_visual_label": visual_label,
            "master_consensus": consensus,
            "master_components": metrics["component_scores"],
            "opinion_change_conditions": opinion_change_conditions,
            "audit_status": status,
            "auditor_status": status,
            "audit_score": row.get("audit_score") or _audit_score(row),
            "audit_confidence": row.get("audit_confidence"),
            "audit_reason": row.get("audit_reason"),
            "audit_blocks": _listify(row.get("audit_blocks")),
            "audit_warnings": _listify(row.get("audit_warnings")),
            "audit_summary": row.get("audit_summary"),
            "auditor_approved": status != AUDIT_BLOCKED,
            "blocked_by_auditor": bool(row.get("blocked_by_auditor") is True or status == AUDIT_BLOCKED),
        }
    )
    return payload


def master_score_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row)
        if ticker and ticker not in output:
            output[ticker] = dict(row)
    return output


def _signal_aligns_with_master(row: Dict[str, Any], direction: str) -> bool:
    signal = snapshot_signal_value(row)
    if signal not in ACTIONABLE_SIGNALS:
        return True
    if direction == MASTER_BULLISH:
        return signal in BULLISH_ACTIONS
    if direction == MASTER_BEARISH:
        return signal in BEARISH_ACTIONS
    return False


def apply_master_scores_by_ticker(rows: Iterable[Dict[str, Any]], master_scores: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index = master_score_index(master_scores)
    output: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        master = index.get(_ticker(item))
        if not master:
            output.append(item)
            continue
        for field in MASTER_CONTRACT_FIELDS:
            if field in master:
                item[field] = master[field]
        if master.get("master_status") == AUDIT_BLOCKED:
            blocked = _listify(item.get("blocked_reasons"))
            blocked.extend(["master_score_blocked", * _listify(master.get("audit_blocks"))])
            item["blocked_reasons"] = list(dict.fromkeys(blocked))
            item["decision_ready"] = False
            item["can_trade"] = False
            item["decision_state"] = "DO_NOT_TRADE"
            item["operational_message"] = "⚠️ NÃO OPERAR AGORA"
            reasons = _listify(item.get("no_trade_reasons"))
            reasons.append("score mestre bloqueou")
            item["no_trade_reasons"] = list(dict.fromkeys(reasons))
        elif not _signal_aligns_with_master(item, str(master.get("master_direction") or MASTER_NEUTRAL)):
            blocked = _listify(item.get("blocked_reasons"))
            blocked.append("master_score_context_not_confirmed")
            item["blocked_reasons"] = list(dict.fromkeys(blocked))
            item["decision_ready"] = False
            item["can_trade"] = False
            item["decision_state"] = "NO_TRADE"
            item["operational_message"] = "⚠️ NÃO OPERAR AGORA"
            reasons = _listify(item.get("no_trade_reasons"))
            reasons.append("score mestre não confirmou contexto")
            item["no_trade_reasons"] = list(dict.fromkeys(reasons))
        output.append(item)
    return output


def run_master_score(
    rows: Iterable[Dict[str, Any]],
    limit: int = 12,
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return top_n(
        (
            _score_row(row, ai_tools=ai_tools, market_pulse=market_pulse)
            for row in rows or []
            if isinstance(row, dict)
        ),
        limit=limit,
    )
