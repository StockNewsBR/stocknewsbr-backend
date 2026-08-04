from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    score = float(row.get("accumulation_bias", 0.0))
    stability_score = float(row.get("stability_score", 0.0))
    absorption_score = float(row.get("absorption_score", 0.0))
    discrete_buying_score = float(row.get("discrete_buying_score", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))

    if score >= 75:
        state = "accumulation"
        comment = (
            f"{row['ticker']} apresenta acumulação: compra discreta {discrete_buying_score:.1f}, estabilidade {stability_score:.1f}, absorção {absorption_score:.1f}."
        )
        trigger = "Rompimento da faixa com manutenção do volume e sem perda da estabilidade do preço."
        invalidation = "Perda do suporte local, aumento da pressão vendedora ou queda brusca da absorção."
    elif score >= 55:
        state = "early_accumulation"
        comment = f"{row['ticker']} mostra acumulação inicial: estabilidade {stability_score:.1f}, RVOL {rel_volume:.2f}."
        trigger = "Fechamentos firmes acima da média de negociação com volume comprador progressivo."
        invalidation = "Aumento de volatilidade sem continuação ou perda da zona de absorção."
    elif score <= 25:
        state = "distribution_or_weak"
        comment = f"{row['ticker']} não mostra acumulação saudável; estabilidade {stability_score:.1f} e absorção {absorption_score:.1f} estão fracas."
        trigger = "Recuperação estrutural com volume comprador progressivo e estabilização do range."
        invalidation = "Continuação da fraqueza ou aumento de volume vendedor em suporte."
    else:
        state = "monitoring"
        comment = f"{row['ticker']} permanece em observação para acumulação: compra discreta {discrete_buying_score:.1f}."
        trigger = "Melhora gradual do volume, estabilidade do preço e defesa de suporte/VWAP."
        invalidation = "Perda de estrutura ou sumiço da absorção antes da confirmação."

    metrics = {
        "accumulation_bias": round(float(row.get("accumulation_bias", 0.0)), 1),
        "discrete_buying_score": round(discrete_buying_score, 1),
        "stability_score": round(stability_score, 1),
        "absorption_score": round(absorption_score, 1),
        "rel_volume": round(rel_volume, 2),
        "rsi": round(float(row.get("rsi", 50.0)), 2),
        "above_vwap": bool(row.get("above_vwap", False)),
    }

    return build_payload(
        row=row,
        tool="accumulation",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
    )


def run_accumulation(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
