from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    score = float(row.get("accumulation_bias", 0.0))

    if score >= 75:
        state = "accumulation"
        comment = (
            f"{row['ticker']} apresenta perfil claro de acumulação, com preço estável, "
            f"volume saudável e sustentação estrutural."
        )
        trigger = "Rompimento da faixa com manutenção do volume."
        invalidation = "Perda do suporte local e aumento da pressão vendedora."
    elif score >= 55:
        state = "early_accumulation"
        comment = f"{row['ticker']} mostra sinais iniciais de acumulação, mas ainda precisa de confirmação."
        trigger = "Fechamentos firmes acima da média de negociação."
        invalidation = "Aumento de volatilidade sem continuação."
    elif score <= 25:
        state = "distribution_or_weak"
        comment = f"{row['ticker']} não mostra padrão saudável de acumulação neste momento."
        trigger = "Recuperação estrutural com volume comprador progressivo."
        invalidation = "Continuação da fraqueza."
    else:
        state = "monitoring"
        comment = f"{row['ticker']} permanece em observação para acumulação."
        trigger = "Melhora gradual do volume e do preço."
        invalidation = "Perda de estrutura."

    metrics = {
        "accumulation_bias": round(float(row.get("accumulation_bias", 0.0)), 1),
        "rel_volume": round(float(row.get("rel_volume", 0.0)), 2),
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
