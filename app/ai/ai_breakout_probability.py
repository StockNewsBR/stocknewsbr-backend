from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    breakout_pressure = float(row.get("breakout_pressure", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    range_position = float(row.get("range_position", 0.5))
    adx = float(row.get("adx", 0.0))
    resistance = float(row.get("resistance", row.get("high", row.get("price", 0.0))))
    false_breakout_risk = float(row.get("false_breakout_risk", 0.0))
    distance_to_resistance = float(row.get("distance_to_resistance_pct", 0.0))

    score = max(
        0.0,
        min(
            100.0,
            breakout_pressure * 0.52
            + max(rel_volume - 1.0, 0.0) * 18.0
            + range_position * 18.0
            + adx * 0.22
            - false_breakout_risk * 0.10,
        ),
    )

    if score >= 75:
        state = "ready_to_break"
        comment = f"{row['ticker']} pressiona resistência {resistance:.4f}: pressão {breakout_pressure:.1f}, RVOL {rel_volume:.2f}, risco de falha {false_breakout_risk:.1f}."
        trigger = f"Comprar/acompanhar só no rompimento de {resistance:.4f} com RVOL sustentado e fechamento acima da faixa."
        invalidation = "Falha se romper e voltar para dentro do range ou se o volume secar antes da continuação."
    elif score >= 55:
        state = "building_pressure"
        comment = f"{row['ticker']} acumula pressão de breakout, ainda a {distance_to_resistance:.2f}% da resistência e com RVOL {rel_volume:.2f}."
        trigger = "Exigir expansão de range, aproximação da máxima e RVOL acima da média antes de validar."
        invalidation = "Perde leitura se sair da parte alta da faixa ou se o risco de falso rompimento aumentar."
    else:
        state = "not_ready"
        comment = f"{row['ticker']} ainda não mostra breakout institucional: pressão {breakout_pressure:.1f}, RVOL {rel_volume:.2f}."
        trigger = "Só reavaliar com melhora do volume e nova aproximação da máxima/resistência."
        invalidation = "Volume fraco, perda de momentum ou rejeição na resistência anulam o setup."

    return build_payload(
        row=row,
        tool="breakout_probability",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics={
            "breakout_pressure": round(breakout_pressure, 1),
            "rel_volume": round(rel_volume, 2),
            "range_position": round(range_position, 2),
            "adx": round(adx, 1),
            "resistance": round(resistance, 4),
            "distance_to_resistance_pct": round(distance_to_resistance, 2),
            "false_breakout_risk": round(false_breakout_risk, 1),
        },
    )


def run_breakout_probability(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
