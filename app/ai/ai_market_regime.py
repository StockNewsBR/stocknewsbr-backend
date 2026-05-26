from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    trend_strength = float(row.get("trend_strength", 0.0))
    volatility_score = float(row.get("volatility_score", 0.0))
    momentum = float(row.get("momentum", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))

    directional_score = max(0.0, min(100.0, trend_strength * 0.55 + abs(momentum) * 10.0 + max(rel_volume - 1.0, 0.0) * 10.0))
    score = directional_score

    if volatility_score >= 72:
        state = "high_volatility"
        comment = f"{row['ticker']} esta em regime de alta volatilidade e exige manejo de risco mais apertado."
        trigger = "Persistencia do range expandido e volume."
        invalidation = "Volatilidade perder intensidade e mercado comprimir."
    elif trend_strength >= 60 and momentum >= 0:
        state = "bull_trend"
        comment = f"{row['ticker']} esta em regime de alta, com tendencia e momentum positivos."
        trigger = "Continuidade acima da VWAP e defesa de suportes."
        invalidation = "Perda da tendencia e quebra de estrutura."
    elif trend_strength >= 60 and momentum < 0:
        state = "bear_trend"
        comment = f"{row['ticker']} esta em regime de baixa, com tendencia negativa clara."
        trigger = "Continuidade abaixo da VWAP e novos fundos."
        invalidation = "Recuperacao da estrutura e perda de tendencia."
    else:
        state = "range"
        comment = f"{row['ticker']} esta em mercado lateral, pedindo leitura mais tatica."
        trigger = "Saida da faixa com volume."
        invalidation = "Ativo continuar preso no range."

    return build_payload(
        row=row,
        tool="market_regime",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics={
            "trend_strength": round(trend_strength, 1),
            "volatility_score": round(volatility_score, 1),
            "momentum": round(momentum, 2),
            "rel_volume": round(rel_volume, 2),
        },
    )


def run_market_regime(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
