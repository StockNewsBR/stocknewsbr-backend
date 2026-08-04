from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    trend_strength = float(row.get("trend_strength", 0.0))
    volatility_score = float(row.get("volatility_score", 0.0))
    momentum = float(row.get("momentum", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    price = float(row.get("price", 0.0))
    vwap = float(row.get("vwap", price))
    data_quality = str(row.get("data_quality") or "priced")
    source_score = float(row.get("source_score", 0.0))
    symbol_factor = float(row.get("symbol_factor", 50.0))
    above_vwap = bool(row.get("above_vwap", price >= vwap if vwap else False))
    reversal_risk = max(0.0, min(100.0, (100.0 - trend_strength) * 0.45 + volatility_score * 0.25 + abs(momentum) * 8.0))

    directional_score = max(0.0, min(100.0, trend_strength * 0.55 + abs(momentum) * 10.0 + max(rel_volume - 1.0, 0.0) * 10.0))
    score = directional_score

    if price <= 0 or data_quality == "score_only":
        score = max(0.0, min(55.0, 15.0 + source_score * 0.28 + symbol_factor * 0.08))
        state = "range"
        comment = f"{row['ticker']} está em regime pendente: sem preço real no ciclo, prior do scanner {source_score:.1f} e sem confirmação de tendência."
        trigger = "Classificar regime operacional somente com preço real, direção de média/VWAP e volume confirmando saída da lateralidade."
        invalidation = "Enquanto o ciclo continuar sem preço real, o regime permanece contexto e não deve comandar trade sozinho."
        trend_strength = min(55.0, score)
        volatility_score = min(volatility_score, 45.0)
        reversal_risk = max(reversal_risk, 50.0)
    elif volatility_score >= 72:
        state = "high_volatility"
        comment = f"{row['ticker']} está em regime de alta volatilidade: vol {volatility_score:.1f}, tendência {trend_strength:.1f}, reversão {reversal_risk:.1f}."
        trigger = "Persistência do range expandido com volume e respeito ao lado dominante."
        invalidation = "Volatilidade perder intensidade, preço comprimir ou reversão romper a média/VWAP."
    elif trend_strength >= 60 and momentum >= 0:
        state = "bull_trend"
        comment = f"{row['ticker']} está em alta: tendência {trend_strength:.1f}, momentum {momentum:.2f}, acima da VWAP={above_vwap}."
        trigger = "Continuidade acima da VWAP/média e defesa de suportes em pullback."
        invalidation = "Perda da tendência, quebra de estrutura ou fechamento abaixo da média/VWAP."
    elif trend_strength >= 60 and momentum < 0:
        state = "bear_trend"
        comment = f"{row['ticker']} está em baixa: tendência {trend_strength:.1f}, momentum {momentum:.2f}, acima da VWAP={above_vwap}."
        trigger = "Continuidade abaixo da VWAP/média e perda de suportes com volume."
        invalidation = "Recuperação da estrutura, fechamento acima da média/VWAP ou perda de força vendedora."
    else:
        state = "range"
        comment = f"{row['ticker']} está lateral: tendência {trend_strength:.1f}, reversão/média {reversal_risk:.1f}, RVOL {rel_volume:.2f}."
        trigger = "Saída da faixa com volume e fechamento fora do range."
        invalidation = "Ativo continuar preso no range ou falhar ao cruzar a média/VWAP."

    payload = build_payload(
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
            "above_vwap": above_vwap,
            "reversal_risk": round(reversal_risk, 1),
            "moving_average_proxy": round(vwap, 4),
        },
    )
    if price <= 0 or data_quality == "score_only":
        payload["_rank_score"] = round(
            source_score * 0.45 + reversal_risk * 0.30 + (100.0 - symbol_factor) * 0.25,
            4,
        )
    return payload


def run_market_regime(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
