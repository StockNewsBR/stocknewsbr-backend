from __future__ import annotations

from typing import Dict, Iterable, List

from app.ai.ai_common import build_payload, normalize_row, top_n


def _score_row(source: Dict[str, object]) -> Dict[str, object]:
    row = normalize_row(source)
    range_position = float(row.get("range_position", 0.5))
    intraday_range_pct = float(row.get("intraday_range_pct", 0.0))
    atr_pct = float(row.get("atr_pct", 0.0))
    change_pct = float(row.get("change_pct", 0.0))
    false_breakout_risk = float(row.get("false_breakout_risk", 0.0))

    sweep_intensity = abs(change_pct) * 12.0 + intraday_range_pct * 8.0 + atr_pct * 6.0
    rejection_bonus = abs(range_position - 0.5) * 40.0
    stop_hunt_score = max(0.0, min(100.0, sweep_intensity + rejection_bonus + false_breakout_risk * 0.25))
    reaction_side = "reação compradora" if range_position <= 0.35 else "reação vendedora" if range_position >= 0.65 else "sem reação clara"
    score = stop_hunt_score

    if score >= 70:
        state = "liquidity_sweep_detected"
        comment = f"{row['ticker']} sugere stop hunt: varredura {stop_hunt_score:.1f}, risco de falso rompimento {false_breakout_risk:.1f}, {reaction_side}."
        trigger = "Confirmar reversão após a varredura com rejeição da extrema e volume contra o rompimento falso."
        invalidation = "Preço aceitar acima/abaixo da área varrida e seguir sem rejeição invalida o trap."
    elif score >= 48:
        state = "sweep_watch"
        comment = f"{row['ticker']} está em zona de possível sweep: varredura {stop_hunt_score:.1f}, {reaction_side}."
        trigger = "Esperar rejeição mais clara da extrema do range antes de tratar como reversão."
        invalidation = "Mercado perder a leitura de rejeição ou romper limpo com continuidade."
    else:
        state = "no_sweep"
        comment = f"{row['ticker']} não mostra stop hunt relevante; varredura {stop_hunt_score:.1f}."
        trigger = "Só reavaliar com ampliação abrupta do range e falha de continuidade."
        invalidation = "Mercado continuar limpo, sem trap ou sem reação na extremidade."

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
            "stop_hunt_score": round(stop_hunt_score, 1),
            "false_breakout_risk": round(false_breakout_risk, 1),
            "reaction_side": reaction_side,
        },
    )


def run_liquidity_sweep(rows: Iterable[Dict[str, object]], limit: int = 12) -> List[Dict[str, object]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
