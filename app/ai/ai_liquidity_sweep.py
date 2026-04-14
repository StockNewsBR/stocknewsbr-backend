from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    range_position = float(row.get("range_position", 0.5))
    intraday_range_pct = float(row.get("intraday_range_pct", 0.0))
    atr_pct = float(row.get("atr_pct", 0.0))
    change_pct = float(row.get("change_pct", 0.0))

    sweep_intensity = abs(change_pct) * 12.0 + intraday_range_pct * 8.0 + atr_pct * 6.0
    rejection_bonus = abs(range_position - 0.5) * 40.0
    score = max(0.0, min(100.0, sweep_intensity + rejection_bonus))

    if score >= 70:
        state = "liquidity_sweep_detected"
        comment = f"{row['ticker']} sugere varredura de liquidez com expansao de range e rejeicao da ponta."
        trigger = "Confirmacao da reversao apos a varredura."
        invalidation = "Preco aceitar acima/abaixo da area varrida e seguir sem rejeicao."
    elif score >= 48:
        state = "sweep_watch"
        comment = f"{row['ticker']} esta em zona de possivel sweep, ainda sem assinatura completa."
        trigger = "Rejeicao mais clara da extrema do range."
        invalidation = "Mercado perder a leitura de rejeicao."
    else:
        state = "no_sweep"
        comment = f"{row['ticker']} nao mostra leitura forte de liquidity sweep no momento."
        trigger = "Ampliacao abrupta do range com falha de continuidade."
        invalidation = "Mercado continuar limpo, sem trap."

    return build_payload(
        row=row,
        tool="liquidity_sweep",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics={
            "range_position": round(range_position, 2),
            "intraday_range_pct": round(intraday_range_pct, 2),
            "atr_pct": round(atr_pct, 2),
            "change_pct": round(change_pct, 2),
        },
    )


def run_liquidity_sweep(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
