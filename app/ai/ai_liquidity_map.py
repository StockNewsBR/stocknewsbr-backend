from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    price = float(row.get("price", 0.0))
    data_quality = str(row.get("data_quality") or "priced")
    score = (
        float(row.get("liquidity_magnet", 0.0)) * 0.55
        + float(row.get("volume_score", 0.0)) * 0.25
        + float(row.get("volatility_score", 0.0)) * 0.20
    )
    score = max(0.0, min(100.0, score))

    high = float(row.get("high", price))
    low = float(row.get("low", price))
    day_range = max(high - low, 0.0001)
    upper_liquidity = high + day_range * 0.25
    lower_liquidity = low - day_range * 0.25

    if price <= 0 or data_quality == "score_only":
        state = "thin_liquidity" if score <= 25 else "monitoring"
        comment = f"{row['ticker']} ainda não tem preço intraday válido para mapa de liquidez; leitura usa apenas prior do scanner."
        trigger = "Ativar mapa somente quando houver preço real, faixa negociada e reação de volume em zona objetiva."
        invalidation = "Sem preço negociado válido, qualquer zona projetada permanece apenas contexto e não vira gatilho operacional."
    elif score >= 75:
        state = "liquidity_hotspot"
        comment = (
            f"{row['ticker']} tem zonas de liquidez relevantes próximas, com boa chance de reação ao tocar esses níveis."
        )
        trigger = (
            f"Confirmação de aproximação da faixa entre {lower_liquidity:.4f} e {upper_liquidity:.4f} "
            "com fluxo e volume sustentando a defesa da zona."
        )
        invalidation = (
            f"Romper a faixa entre {lower_liquidity:.4f} e {upper_liquidity:.4f} sem reação do preço "
            "ou sem defesa do fluxo comprador/vendedor."
        )
    elif score >= 55:
        state = "liquidity_zone"
        comment = f"{row['ticker']} apresenta áreas úteis de liquidez, mas ainda sem magnetismo extremo."
        trigger = (
            f"Teste da zona entre {lower_liquidity:.4f} e {upper_liquidity:.4f} com confirmação de fluxo "
            "e aceitação do preço."
        )
        invalidation = (
            "Mercado atravessar a faixa sem rejeição clara ou sem acelerar depois do teste."
        )
    elif score <= 25:
        state = "thin_liquidity"
        comment = f"{row['ticker']} está com mapa de liquidez pouco claro neste momento."
        trigger = (
            "Reorganização do range com entrada de volume suficiente para formar nova referencia."
        )
        invalidation = (
            "Continuidade de fluxo ralo, sem formação de referencia clara ou nivel defendido."
        )
    else:
        state = "monitoring"
        comment = (
            f"{row['ticker']} segue em observação, com liquidez ainda difusa e sem uma zona institucional "
            "forte o suficiente para virar referência operacional."
        )
        trigger = (
            "Ampliação do range com volume acima da média, reação clara do preço e formação de uma nova zona de defesa."
        )
        invalidation = (
            "Perder a referência do range atual sem reação relevante de fluxo e sem formar uma nova zona institucional defendida."
        )

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
