from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def normalize_master_score_display(value: Any) -> Tuple[float, str | None]:
    """Display-only contract: Score Mestre shown to users is always 0..10."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0, "master_score_display_invalid"

    if numeric < 0:
        logger.warning("Score Mestre negativo normalizado para display", extra={"raw_score": numeric, "display_score": 0.0})
        return 0.0, "master_score_display_clamped_below_0"
    if numeric > 20:
        display = min(10.0, round(numeric / 10.0, 1))
        if display >= 10.0:
            logger.warning("Score Mestre acima de 10 normalizado para display", extra={"raw_score": numeric, "display_score": display})
            return display, "master_score_display_clamped_above_10"
        return display, None
    if numeric > 10:
        logger.warning("Score Mestre acima de 10 normalizado para display", extra={"raw_score": numeric, "display_score": 10.0})
        return 10.0, "master_score_display_clamped_above_10"
    return round(numeric, 1), None


def attach_master_score_display_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("master_score", row.get("score"))
    display, warning = normalize_master_score_display(raw)
    next_row = dict(row)
    next_row["master_score_display"] = display
    if warning:
        existing = next_row.get("warnings")
        if isinstance(existing, list):
            warnings = list(existing)
        elif existing:
            warnings = [str(existing)]
        else:
            warnings = []
        if warning not in warnings:
            warnings.append(warning)
        next_row["warnings"] = warnings
        next_row["master_score_display_warning"] = warning
    return next_row
