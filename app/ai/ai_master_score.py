from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


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
    existing_subscores = [
        row.get("institutional_flow_score"),
        row.get("accumulation_score"),
        row.get("volatility_squeeze_score"),
        row.get("liquidity_map_score"),
    ]
    valid_subscores = [float(value) for value in existing_subscores if value is not None]

    if valid_subscores:
        subscore_avg = sum(valid_subscores) / len(valid_subscores)
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

    comment = (
        f"{row['ticker']} recebeu Master Score {round(score, 1)}. "
        f"A oportunidade está classificada como {label}. "
        f"Pontos positivos: {', '.join(positives) if positives else 'limitados'}. "
        f"Riscos: {', '.join(risks) if risks else 'controlados'}."
    )

    trigger = "Melhora de tendência, volume e sustentação acima da VWAP."
    invalidation = "Perda de VWAP, enfraquecimento do volume ou reversão da estrutura."

    metrics = {
        "subscore_count": len(valid_subscores),
        "base_score": round(_base_score(row), 1),
        "master_label": label,
    }

    return build_payload(
        row=row,
        tool="master_score",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
    )


def run_master_score(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
