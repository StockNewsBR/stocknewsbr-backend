from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    rel_volume = float(row.get("rel_volume", 0.0))
    institutional_bias = float(row.get("institutional_bias", 0.0))
    accumulation_bias = float(row.get("accumulation_bias", 0.0))
    change_pct = float(row.get("change_pct", 0.0))

    score = max(
        0.0,
        min(
            100.0,
            institutional_bias * 0.45
            + accumulation_bias * 0.25
            + max(rel_volume - 1.0, 0.0) * 18.0
            + max(change_pct, -2.0) * 6.0,
        ),
    )

    if score >= 72:
        state = "smart_money_active"
        comment = f"{row['ticker']} apresenta assinatura de smart money com fluxo e volume acima do normal."
        trigger = "Persistencia de volume e defesa acima da VWAP."
        invalidation = "Fluxo some e o ativo volta para baixo da VWAP."
    elif score >= 50:
        state = "smart_money_interest"
        comment = f"{row['ticker']} mostra interesse parcial de player forte, ainda pedindo confirmacao."
        trigger = "Novo aumento de volume ou candle de continuidade."
        invalidation = "Falha de continuidade e perda da estrutura."
    else:
        state = "retail_noise"
        comment = f"{row['ticker']} ainda parece dominado por ruido de varejo, sem leitura forte de smart money."
        trigger = "Volume relativo saltar acima da media."
        invalidation = "Mercado permanecer sem fluxo."

    return build_payload(
        row=row,
        tool="smart_money",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics={
            "institutional_bias": round(institutional_bias, 1),
            "accumulation_bias": round(accumulation_bias, 1),
            "rel_volume": round(rel_volume, 2),
            "change_pct": round(change_pct, 2),
        },
    )


def run_smart_money(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
