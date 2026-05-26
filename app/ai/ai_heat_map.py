from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    change_pct = float(row.get("change_pct", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    trend_strength = float(row.get("trend_strength", 0.0))

    score = max(
        0.0,
        min(
            100.0,
            50.0 + change_pct * 9.0 + (rel_volume - 1.0) * 12.0 + (trend_strength - 50.0) * 0.25,
        ),
    )

    if score >= 65:
        state = "strong_buying"
        comment = f"{row['ticker']} aparece no heat map com dominancia compradora e fluxo sustentado."
        trigger = "Continuidade da cor verde com volume acima da media."
        invalidation = "Perda de volume e mudanca da leitura para neutra/vermelha."
    elif score <= 35:
        state = "strong_selling"
        comment = f"{row['ticker']} aparece no heat map com pressao vendedora relevante."
        trigger = "Persistencia da leitura vermelha e enfraquecimento do candle."
        invalidation = "Recuperacao da VWAP com melhora de fluxo."
    else:
        state = "mixed"
        comment = f"{row['ticker']} esta em leitura mista no heat map, sem dominancia clara."
        trigger = "Definicao de direcao e aumento do volume relativo."
        invalidation = "Mercado continuar lateral sem expansao."

    return build_payload(
        row=row,
        tool="heat_map",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics={
            "change_pct": round(change_pct, 2),
            "rel_volume": round(rel_volume, 2),
            "trend_strength": round(trend_strength, 1),
            "heat_color": "green" if score >= 65 else "red" if score <= 35 else "mixed",
        },
    )


def run_heat_map(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
