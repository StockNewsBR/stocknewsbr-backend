from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    score = float(row.get("institutional_bias", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    flow_persistence = float(row.get("flow_persistence", 0.0))
    large_flow_score = float(row.get("large_flow_score", 0.0))

    if score >= 75:
        state = "institutional_buying"
        comment = (
            f"{row['ticker']} mostra fluxo institucional comprador: RVOL {rel_volume:.2f}, persistência {flow_persistence:.1f}, fluxo grande {large_flow_score:.1f}."
        )
        trigger = "Continuação acima da VWAP com rel_volume sustentado."
        invalidation = "Perda da VWAP com enfraquecimento do volume."
    elif score >= 55:
        state = "institutional_interest"
        comment = (
            f"{row['ticker']} apresenta interesse institucional parcial: persistência {flow_persistence:.1f}, fluxo grande {large_flow_score:.1f}."
        )
        trigger = "Fechamento mais firme acima da faixa intraday."
        invalidation = "Retorno abaixo da VWAP e perda de força."
    elif score <= 25:
        state = "distribution_risk"
        comment = f"{row['ticker']} sugere risco de distribuição: RVOL {rel_volume:.2f} sem sustentação institucional."
        trigger = "Recuperação rápida da VWAP com aumento de volume."
        invalidation = "Novos fundos e pressão vendedora."
    else:
        state = "monitoring"
        comment = f"{row['ticker']} está em observação: fluxo institucional {score:.1f}, persistência {flow_persistence:.1f}."
        trigger = "Aumento de volume e definição de direção."
        invalidation = "Mercado sem continuidade de fluxo."

    metrics = {
        "institutional_bias": round(float(row.get("institutional_bias", 0.0)), 1),
        "volume_score": round(float(row.get("volume_score", 0.0)), 1),
        "trend_strength": round(float(row.get("trend_strength", 0.0)), 1),
        "rel_volume": round(rel_volume, 2),
        "flow_persistence": round(flow_persistence, 1),
        "large_flow_score": round(large_flow_score, 1),
        "above_vwap": bool(row.get("above_vwap", False)),
    }

    return build_payload(
        row=row,
        tool="institutional_flow",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
    )


def run_institutional_flow(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
