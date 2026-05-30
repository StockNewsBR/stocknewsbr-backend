from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n
from app.ai.trade_decision import resolve_trade_action


def _base_score(row: Dict[str, Any]) -> float:
    return (
        float(row.get("trend_strength", 0.0)) * 0.20
        + float(row.get("volume_score", 0.0)) * 0.20
        + float(row.get("squeeze_score", 0.0)) * 0.15
        + float(row.get("breakout_pressure", 0.0)) * 0.15
        + float(row.get("institutional_bias", 0.0)) * 0.15
        + float(row.get("accumulation_bias", 0.0)) * 0.15
    )


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    component_scores = {
        "heat_map": row.get("heat_map_score"),
        "radar": row.get("radar_score"),
        "breakout_probability": row.get("breakout_probability_score"),
        "institutional_flow": row.get("institutional_flow_score"),
        "smart_money": row.get("smart_money_score"),
        "accumulation": row.get("accumulation_score"),
        "volatility_squeeze": row.get("volatility_squeeze_score"),
        "liquidity_sweep": row.get("liquidity_sweep_score"),
        "liquidity_map": row.get("liquidity_map_score"),
        "market_regime": row.get("market_regime_score"),
    }
    weights = {
        "heat_map": 0.09,
        "radar": 0.08,
        "breakout_probability": 0.11,
        "institutional_flow": 0.14,
        "smart_money": 0.12,
        "accumulation": 0.09,
        "volatility_squeeze": 0.07,
        "liquidity_sweep": 0.08,
        "liquidity_map": 0.08,
        "market_regime": 0.14,
    }
    valid_components = {
        key: float(value)
        for key, value in component_scores.items()
        if value is not None
    }

    if valid_components:
        weight_sum = sum(weights.get(key, 0.0) for key in valid_components) or 1.0
        subscore_avg = sum(valid_components[key] * weights.get(key, 0.0) for key in valid_components) / weight_sum
        score = subscore_avg * 0.65 + _base_score(row) * 0.35
    else:
        score = _base_score(row)

    score = max(0.0, min(100.0, score))

    if score >= 85:
        state = "high_conviction"
        label = "forte"
    elif score >= 70:
        state = "tradable"
        label = "moderada"
    elif score >= 50:
        state = "neutral_setup"
        label = "neutra"
    else:
        state = "weak_setup"
        label = "fraca"

    positives = []
    risks = []

    if row.get("above_vwap", False):
        positives.append("acima da VWAP")
    else:
        risks.append("abaixo da VWAP")

    if float(row.get("rel_volume", 0.0)) >= 1.2:
        positives.append("volume relativo forte")
    else:
        risks.append("volume sem convicção")

    if float(row.get("adx", 0.0)) >= 20:
        positives.append("tendência presente")
    else:
        risks.append("tendência fraca")

    strongest = sorted(valid_components.items(), key=lambda item: item[1], reverse=True)[:3]
    weakest = sorted(valid_components.items(), key=lambda item: item[1])[:2]
    strongest_text = ", ".join(f"{key} {value:.1f}" for key, value in strongest) if strongest else "sem componentes fortes"
    weakest_text = ", ".join(f"{key} {value:.1f}" for key, value in weakest) if weakest else "sem componentes fracos"

    comment = (
        f"{row['ticker']} recebeu Master Score {round(score, 1)}. "
        f"A oportunidade está classificada como {label}. "
        f"Composição: forças em {strongest_text}; fragilidades em {weakest_text}. "
        f"Pontos positivos: {', '.join(positives) if positives else 'limitados'}. "
        f"Riscos: {', '.join(risks) if risks else 'controlados'}."
    )

    metrics = {
        "subscore_count": len(valid_components),
        "base_score": round(_base_score(row), 1),
        "master_label": label,
        "component_scores": {key: round(value, 1) for key, value in valid_components.items()},
        "weights": weights,
        "strongest_components": [key for key, _ in strongest],
        "weakest_components": [key for key, _ in weakest],
    }

    decision = resolve_trade_action({**row, "score": score})
    trigger = decision["trigger"]
    invalidation = decision["invalidation"]
    metrics.update(
        {
            "trade_action": decision["trade_action"],
            "trade_direction": decision["trade_direction"],
            "trade_confidence": decision["trade_confidence"],
            "trade_bias": decision["trade_bias"],
            "bullish_pressure": decision["bullish_pressure"],
            "bearish_pressure": decision["bearish_pressure"],
            "coherence_status": decision["coherence_status"],
            "decision_ready": decision.get("decision_ready", False),
            "conflict_detected": decision.get("conflict_detected", False),
            "blocked_reasons": decision["blocked_reasons"],
            "warnings": decision["warnings"],
            "coherence_rules": decision["coherence_rules"],
            "risk_level": decision["risk_level"],
        }
    )
    comment = f"{comment} Decisão final: {decision['trade_action']}. {decision['risk']}"

    payload = build_payload(
        row=row,
        tool="master_score",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
        reason=(
            f"Score Mestre ponderou {len(valid_components)} IAs: forças {strongest_text}; "
            f"riscos {weakest_text}; base quantitativa {_base_score(row):.1f}."
        ),
    )
    payload["signal"] = decision["trade_action"]
    payload["trade_action"] = decision["trade_action"]
    payload["trade_direction"] = decision["trade_direction"]
    payload["trade_confidence"] = decision["trade_confidence"]
    payload["trade_bias"] = decision["trade_bias"]
    payload["bullish_pressure"] = decision["bullish_pressure"]
    payload["bearish_pressure"] = decision["bearish_pressure"]
    payload["decision_reason"] = decision["reason"]
    payload["decision_conflicts"] = decision["conflicts"]
    payload["decision_ready"] = decision.get("decision_ready", False)
    payload["conflict_detected"] = decision.get("conflict_detected", False)
    payload["coherence_status"] = decision["coherence_status"]
    payload["blocked_reasons"] = decision["blocked_reasons"]
    payload["warnings"] = decision["warnings"]
    payload["coherence_rules"] = decision["coherence_rules"]
    payload["risk"] = decision["risk"]
    payload["risk_level"] = decision["risk_level"]
    payload["market_regime_state"] = decision["market_regime_state"]
    return payload


def run_master_score(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
