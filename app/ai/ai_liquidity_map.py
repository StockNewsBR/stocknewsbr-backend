from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    score = (
        float(row.get("liquidity_magnet", 0.0)) * 0.55
        + float(row.get("volume_score", 0.0)) * 0.25
        + float(row.get("volatility_score", 0.0)) * 0.20
    )
    score = max(0.0, min(100.0, score))

    price = float(row.get("price", 0.0))
    high = float(row.get("high", price))
    low = float(row.get("low", price))
    day_range = max(high - low, 0.0001)
    upper_liquidity = high + day_range * 0.25
    lower_liquidity = low - day_range * 0.25

    if score >= 75:
        state = "liquidity_hotspot"
        comment = (
            f"{row['ticker']} tem zonas de liquidez relevantes próximas, com boa chance de reação ao tocar esses níveis."
        )
        trigger = "Aproximação de zona de liquidez com fluxo crescente."
        invalidation = "Rompimento limpo da zona sem reação."
    elif score >= 55:
        state = "liquidity_zone"
        comment = f"{row['ticker']} apresenta áreas úteis de liquidez, mas ainda sem magnetismo extremo."
        trigger = "Teste da zona com confirmação no fluxo."
        invalidation = "Mercado sem resposta na área."
    elif score <= 25:
        state = "thin_liquidity"
        comment = f"{row['ticker']} está com mapa de liquidez pouco claro neste momento."
        trigger = "Reorganização do range e aumento de volume."
        invalidation = "Continuação de fluxo ralo."
    else:
        state = "monitoring"
        comment = f"{row['ticker']} está em observação para novas zonas de liquidez."
        trigger = "Ampliação do range com melhor volume."
        invalidation = "Perda da referência do range."

    metrics = {
        "liquidity_magnet": round(float(row.get("liquidity_magnet", 0.0)), 1),
        "upper_liquidity": round(upper_liquidity, 4),
        "lower_liquidity": round(lower_liquidity, 4),
        "range_position": round(float(row.get("range_position", 0.5)), 3),
    }

    return build_payload(
        row=row,
        tool="liquidity_map",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
    )


def run_liquidity_map(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
