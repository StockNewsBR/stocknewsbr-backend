from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, top_n


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    score = float(row.get("squeeze_score", 0.0))
    momentum = float(row.get("momentum", 0.0))

    if score >= 75:
        state = "squeeze_ready"
        direction = "alta" if momentum >= 0 else "baixa"
        comment = (
            f"{row['ticker']} está em compressão relevante de volatilidade. "
            f"O ativo parece pronto para expansão, com viés de {direction}."
        )
        trigger = "Quebra da faixa com aumento de volume."
        invalidation = "Continuidade lateral sem expansão."
    elif score >= 55:
        state = "compression"
        comment = f"{row['ticker']} segue comprimido, mas ainda sem gatilho forte de expansão."
        trigger = "Rompimento da faixa curta com rel_volume melhorando."
        invalidation = "Perda do momentum antes do gatilho."
    elif score <= 25:
        state = "already_expanded"
        comment = (
            f"{row['ticker']} já não está em squeeze relevante; a volatilidade parece expandida demais "
            f"para esse setup."
        )
        trigger = "Nova compressão do range."
        invalidation = "Expansão adicional contra a estrutura."
    else:
        state = "monitoring"
        comment = f"{row['ticker']} está neutro para o setup de squeeze neste momento."
        trigger = "Compressão adicional e organização do preço."
        invalidation = "Perda de estrutura antes do gatilho."

    metrics = {
        "squeeze_score": round(float(row.get("squeeze_score", 0.0)), 1),
        "squeeze_ratio": round(float(row.get("squeeze_ratio", 0.0)), 4),
        "momentum": round(momentum, 3),
        "volatility_score": round(float(row.get("volatility_score", 0.0)), 1),
    }

    return build_payload(
        row=row,
        tool="squeeze",
        score=score,
        state=state,
        ai_comment=comment,
        trigger=trigger,
        invalidation=invalidation,
        metrics=metrics,
    )


def run_squeeze(rows: Iterable[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    return top_n((_score_row(row) for row in rows or []), limit=limit)
