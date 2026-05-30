from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, clamp, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    change_pct = float(row.get("change_pct", 0.0))
    momentum = float(row.get("momentum", 0.0))
    rel_volume = float(row.get("rel_volume", 0.0))
    trend_strength = float(row.get("trend_strength", 0.0))
    volume = float(row.get("volume", 0.0))
    avg_volume = float(row.get("avg_volume", 0.0))
    atr_pct = float(row.get("atr_pct", 0.0))
    abnormal_move = float(row.get("abnormal_move_score", 0.0))

    volume_impulse = max(rel_volume - 1.0, 0.0)
    velocity = abs(change_pct) + abs(momentum) * 0.65
    unusual_volume = volume_impulse * 22.0
    structural_boost = max(trend_strength - 45.0, 0.0) * 0.28
    liquidity_boost = 8.0 if volume > 0 and avg_volume > 0 and volume >= avg_volume * 1.5 else 0.0

    score = clamp(
        velocity * 10.0
        + unusual_volume
        + structural_boost
        + liquidity_boost
        + max(atr_pct - 1.0, 0.0) * 4.0
        + abnormal_move * 0.25
    )

    if score >= 78:
        state = "momentum_ignition"
        comment = f"{row['ticker']} entrou no radar por aceleração {velocity:.2f}, movimento anormal {abnormal_move:.1f} e RVOL {rel_volume:.2f}."
        trigger = "Confirmar continuidade no próximo candle com momentum positivo e RVOL ainda acima da média."
        invalidation = "Sai do radar se velocidade cair, RVOL voltar para perto de 1.00 ou houver rejeição forte contra o movimento."
    elif score >= 58:
        state = "fast_move"
        comment = f"{row['ticker']} mostra deslocamento rápido: momentum {momentum:.2f}, variação {change_pct:.2f}% e RVOL {rel_volume:.2f}."
        trigger = "Aguardar novo deslocamento com volume acima da média e fechamento sem pavio de rejeição."
        invalidation = "Perde prioridade se devolver a maior parte da variação atual ou se o momentum zerar."
    elif score >= 38:
        state = "early_radar"
        comment = f"{row['ticker']} tem ignição inicial; movimento anormal {abnormal_move:.1f} ainda pede confirmação."
        trigger = "Monitorar aumento simultâneo de preço, momentum e RVOL antes de tratar como setup."
        invalidation = "Alerta inválido se o ativo ficar lateral com volume fraco ou perder a direção do candle."
    else:
        state = "quiet"
        comment = f"{row['ticker']} ainda não tem aceleração suficiente: velocidade {velocity:.2f} e RVOL {rel_volume:.2f}."
        trigger = "Entrar no radar somente com aceleração objetiva, momentum novo e volume incomum."
        invalidation = "Sem setup enquanto velocidade, momentum e volume seguirem baixos."

    return build_payload(
        row=row,
        tool="radar",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics={
            "velocity": round(velocity, 2),
            "change_pct": round(change_pct, 2),
            "momentum": round(momentum, 2),
            "rel_volume": round(rel_volume, 2),
            "volume_impulse": round(volume_impulse, 2),
            "abnormal_move": round(abnormal_move, 1),
            "atr_pct": round(atr_pct, 2),
            "radar_reason": state,
        },
    )


def run_radar(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
