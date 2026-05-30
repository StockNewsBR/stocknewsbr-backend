from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    change_pct = float(row.get("change_pct", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    trend_strength = float(row.get("trend_strength", 0.0))
    relative_strength = float(row.get("relative_strength_score", 50.0))
    relative_weakness = float(row.get("relative_weakness_score", 50.0))

    score = max(
        0.0,
        min(
            100.0,
            50.0
            + (relative_strength - relative_weakness) * 0.42
            + change_pct * 7.0
            + (rel_volume - 1.0) * 9.0
            + (trend_strength - 50.0) * 0.18,
        ),
    )
    heat_intensity = abs(score - 50.0) + abs(change_pct) * 4.0 + max(rel_volume - 1.0, 0.0) * 6.0

    if score >= 65:
        state = "strong_buying"
        comment = f"{row['ticker']} lidera o heat map: força relativa {relative_strength:.1f}, variação {change_pct:.2f}% e RVOL {rel_volume:.2f}."
        trigger = f"Manter força relativa acima de {max(55.0, relative_strength - 8.0):.1f} e RVOL acima de 1.00 no próximo candle."
        invalidation = "Perde leitura se voltar para o meio do ranking relativo ou se RVOL cair com candle vendedor dominante."
    elif score <= 35:
        state = "strong_selling"
        comment = f"{row['ticker']} aparece como fraqueza relativa: pressão {relative_weakness:.1f}, variação {change_pct:.2f}% e RVOL {rel_volume:.2f}."
        trigger = f"Confirmar venda/defesa se fraqueza relativa ficar acima de {max(55.0, relative_weakness - 8.0):.1f} e preço não recuperar VWAP."
        invalidation = "Invalida se recuperar força relativa, virar acima da VWAP ou surgir volume comprador superior ao vendedor."
    else:
        state = "mixed"
        comment = f"{row['ticker']} está no miolo do heat map: força {relative_strength:.1f}, fraqueza {relative_weakness:.1f}, sem domínio claro."
        trigger = "Só vira alerta operacional se sair do miolo relativo com RVOL acima da média e direção definida."
        invalidation = "Enquanto força e fraqueza seguirem equilibradas, a leitura permanece neutra."

    payload = build_payload(
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
            "relative_strength": round(relative_strength, 1),
            "relative_weakness": round(relative_weakness, 1),
            "heat_intensity": round(heat_intensity, 1),
            "heat_color": "green" if score >= 65 else "red" if score <= 35 else "mixed",
        },
    )
    payload["_sort_score"] = round(heat_intensity, 4)
    return payload


def run_heat_map(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    results = [_score_row(row) for row in rows or []]
    return sorted(results, key=lambda item: item.get("_sort_score", 0), reverse=True)[: max(1, limit)]
