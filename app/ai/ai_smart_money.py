from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    rel_volume = float(row.get("rel_volume", 0.0))
    institutional_bias = float(row.get("institutional_bias", 0.0))
    accumulation_bias = float(row.get("accumulation_bias", 0.0))
    change_pct = float(row.get("change_pct", 0.0))
    absorption_score = float(row.get("absorption_score", 0.0))
    defended_level = str(row.get("defended_level") or "range_mid")

    score = max(
        0.0,
        min(
            100.0,
            institutional_bias * 0.45
            + accumulation_bias * 0.20
            + absorption_score * 0.20
            + max(rel_volume - 1.0, 0.0) * 18.0
            + max(change_pct, -2.0) * 4.0,
        ),
    )

    if score >= 72:
        state = "smart_money_active"
        comment = f"{row['ticker']} mostra smart money ativo: absorção {absorption_score:.1f}, defesa em {defended_level}, RVOL {rel_volume:.2f}."
        trigger = f"Confirmar defesa de {defended_level} com volume persistente e preço sem perder a zona."
        invalidation = "Fluxo some, preço perde a zona defendida ou volume vendedor domina o próximo candle."
    elif score >= 50:
        state = "smart_money_interest"
        comment = f"{row['ticker']} tem interesse parcial de player forte: posicionamento {institutional_bias:.1f}, absorção {absorption_score:.1f}."
        trigger = "Novo aumento de volume, candle de continuidade e defesa clara do nível."
        invalidation = "Falha de continuidade, perda da estrutura ou ausência de defesa no nível-chave."
    else:
        state = "retail_noise"
        comment = f"{row['ticker']} ainda parece ruído de varejo: absorção {absorption_score:.1f}, RVOL {rel_volume:.2f}."
        trigger = "Volume relativo saltar acima da média junto com defesa objetiva de VWAP/suporte."
        invalidation = "Mercado permanecer sem fluxo ou perder o nível antes de mostrar defesa."

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
            "absorption_score": round(absorption_score, 1),
            "defended_level": defended_level,
            "rel_volume": round(rel_volume, 2),
            "change_pct": round(change_pct, 2),
        },
    )


def run_smart_money(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
