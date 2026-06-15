from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def normalize_master_score_display(value: Any) -> Tuple[float, str | None]:
    """Canonical product contract: Score Mestre exposed to users is always 0..10."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0, "master_score_display_invalid"

    if numeric < 0:
        logger.warning("Score Mestre negativo normalizado para display", extra={"raw_score": numeric, "display_score": 0.0})
        return 0.0, "master_score_display_clamped_below_0"
    if numeric > 10:
        display = min(10.0, round(numeric / 10.0, 1))
        logger.warning("Score Mestre bruto normalizado para escala 0..10", extra={"raw_score": numeric, "display_score": display})
        return display, "master_score_normalized_from_raw_100"
    return round(numeric, 1), None


def attach_master_score_display_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("master_score_raw")
    if raw in (None, ""):
        raw = row.get("master_score")
    if raw in (None, ""):
        raw = row.get("score")
    display, warning = normalize_master_score_display(raw)
    next_row = dict(row)
    try:
        raw_numeric = float(raw)
    except (TypeError, ValueError):
        raw_numeric = None
    if raw_numeric is not None:
        next_row["master_score_raw"] = round(raw_numeric, 1)
        next_row["master_score"] = display
        if next_row.get("tool") == "master_score":
            next_row["score"] = display
    block = next_row.get("master_score_block")
    if isinstance(block, dict):
        block_raw = block.get("score_raw")
        if block_raw in (None, ""):
            block_raw = block.get("raw_score")
        if block_raw in (None, ""):
            block_raw = block.get("score")
        block_score, block_warning = normalize_master_score_display(block_raw)
        next_block = dict(block)
        next_block["score_raw"] = block_raw
        next_block["score"] = block_score
        if block_warning:
            next_block["score_warning"] = block_warning
        next_row["master_score_block"] = next_block
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


def canonicalize_master_score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with public Score Mestre fields on the 0..10 product scale."""
    if not isinstance(row, dict):
        return row
    return attach_master_score_display_contract(row)


def master_score_sort_value(row: Dict[str, Any]) -> float:
    """Preserve internal ordering by raw score when the canonical score is exposed."""
    if not isinstance(row, dict):
        return 0.0
    for key in ("master_score_raw", "master_score", "score"):
        try:
            value = row.get(key)
            if value in (None, ""):
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0
