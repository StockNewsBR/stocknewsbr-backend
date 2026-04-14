from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    breakout_pressure = float(row.get("breakout_pressure", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    range_position = float(row.get("range_position", 0.5))
    adx = float(row.get("adx", 0.0))

    score = max(
        0.0,
        min(
            100.0,
            breakout_pressure * 0.55 + max(rel_volume - 1.0, 0.0) * 20.0 + range_position * 20.0 + adx * 0.25,
        ),
    )

    if score >= 75:
        state = "ready_to_break"
        comment = f"{row['ticker']} mostra pressao real de rompimento, com range comprimido e volume apoiando."
        trigger = "Rompimento da resistencia intraday com continuidade."
        invalidation = "Falha no rompimento e retorno para dentro da faixa."
    elif score >= 55:
        state = "building_pressure"
        comment = f"{row['ticker']} esta acumulando pressao para breakout, mas ainda sem confirmacao total."
        trigger = "Expansao de range e rel_volume acima da media."
        invalidation = "Perda da parte alta da faixa."
    else:
        state = "not_ready"
        comment = f"{row['ticker']} ainda nao mostra probabilidade alta de breakout."
        trigger = "Melhora do volume e aproximacao da maxima."
        invalidation = "Volume fraco e perda de momentum."

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
        },
    )


def run_breakout_probability(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
