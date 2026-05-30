from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    score = float(row.get("squeeze_score", 0.0))
    momentum = float(row.get("momentum", 0.0))
    atr_pct = float(row.get("atr_pct", 0.0))
    squeeze_ratio = float(row.get("squeeze_ratio", 0.0))
    volatility_score = float(row.get("volatility_score", 0.0))
    source_score = float(row.get("source_score", 0.0))
    symbol_factor = float(row.get("symbol_factor", 50.0))
    data_quality = str(row.get("data_quality") or "priced")
    contraction = max(0.0, 100.0 - volatility_score)

    if score >= 75:
        state = "squeeze_ready"
        direction = "alta" if momentum >= 0 else "baixa"
        comment = (
            f"{row['ticker']} está em compressão relevante: ATR {atr_pct:.2f}%, squeeze {score:.1f}, viés de {direction}."
        )
        trigger = "Quebra da faixa com aumento de volume e ATR começando a expandir."
        invalidation = "Continuidade lateral sem expansão ou perda do momentum antes do rompimento."
    elif score >= 55:
        state = "compression"
        comment = f"{row['ticker']} segue comprimido, com ATR {atr_pct:.2f}% e contração {contraction:.1f}, mas sem gatilho forte."
        trigger = "Rompimento da faixa curta com RVOL melhorando e ATR deixando a zona de contração."
        invalidation = "Perda do momentum antes do gatilho ou expansão falsa sem direção."
    elif score <= 25:
        state = "already_expanded"
        comment = (
            f"{row['ticker']} já não está em squeeze relevante; ATR {atr_pct:.2f}% e volatilidade {volatility_score:.1f} indicam expansão."
        )
        trigger = "Nova compressão do range."
        invalidation = "Expansão adicional contra a estrutura."
    else:
        state = "monitoring"
        comment = f"{row['ticker']} está neutro para squeeze: ATR {atr_pct:.2f}%, ratio {squeeze_ratio:.4f}."
        trigger = "Compressão adicional e organização do preço."
        invalidation = "Perda de estrutura antes do gatilho."

    metrics = {
        "squeeze_score": round(float(row.get("squeeze_score", 0.0)), 1),
        "squeeze_ratio": round(squeeze_ratio, 4),
        "momentum": round(momentum, 3),
        "atr_pct": round(atr_pct, 2),
        "contraction_score": round(contraction, 1),
        "volatility_score": round(volatility_score, 1),
    }

    payload = build_payload(
        row=row,
        tool="volatility_squeeze",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
    )
    if data_quality == "score_only":
        payload["_rank_score"] = round(
            (100.0 - source_score) * 0.45 + contraction * 0.35 + (100.0 - symbol_factor) * 0.20,
            4,
        )
    return payload


def run_squeeze(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
