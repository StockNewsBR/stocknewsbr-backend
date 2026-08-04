from __future__ import annotations

import logging
import math
from typing import Any, Dict, Literal, Tuple

logger = logging.getLogger(__name__)
_DISPLAY_WARNING_KEYS: set[tuple[str, float, float]] = set()
_DISPLAY_WARNING_KEY_LIMIT = 2048
_DISPLAY_WARNING_CODES = {
    "master_score_normalized_from_raw_100",
    "master_score_display_invalid",
    "master_score_display_clamped_below_0",
    "master_score_display_clamped_above_10",
}
ScoreScale = Literal["0_10", "0_100"]
_VALID_SCORE_SCALES = {"0_10", "0_100"}

# Mission 31C contract:
# - master_score_raw is the internal 0..100 source score.
# - master_score and public score fields are exposed on the 0..10 product scale.
# - master_score_source_scale records the explicit scale used to derive the public score.


def _master_source_scale_hint(row: Dict[str, Any]) -> ScoreScale | None:
    for key in ("master_score_source_scale", "master_score_scale", "source_scale"):
        if key not in row or row.get(key) in (None, ""):
            continue
        value = str(row.get(key) or "").strip()
        if value in _VALID_SCORE_SCALES:
            return value  # type: ignore[return-value]
        raise ValueError(f"Unsupported master score source scale: {value}")
    return None


def _score_source_scale_hint(row: Dict[str, Any]) -> ScoreScale | None:
    for key in ("score_source_scale", "source_scale"):
        if key not in row or row.get(key) in (None, ""):
            continue
        value = str(row.get(key) or "").strip()
        if value in _VALID_SCORE_SCALES:
            return value  # type: ignore[return-value]
        raise ValueError(f"Unsupported score source scale: {value}")
    return None


def _warning_key(kind: str, raw_score: float, display_score: float) -> tuple[str, float, float]:
    return (kind, round(float(raw_score), 4), round(float(display_score), 4))


def _log_display_warning_once(message: str, kind: str, raw_score: float, display_score: float) -> None:
    key = _warning_key(kind, raw_score, display_score)
    if key in _DISPLAY_WARNING_KEYS:
        return
    _DISPLAY_WARNING_KEYS.add(key)
    if len(_DISPLAY_WARNING_KEYS) > _DISPLAY_WARNING_KEY_LIMIT:
        _DISPLAY_WARNING_KEYS.pop()
    logger.warning(message, extra={"raw_score": raw_score, "display_score": display_score})


def _numeric_score_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    except (TypeError, ValueError):
        return None


def _round_display_score(value: float) -> float:
    return math.floor(float(value) * 10.0 + 0.5) / 10.0


def _valid_for_scale(numeric: float, source_scale: ScoreScale) -> bool:
    if source_scale == "0_100":
        return 0.0 <= numeric <= 100.0
    return 0.0 <= numeric <= 10.0


def _scale_for_value(value: Any, scale_hint: ScoreScale | None, *, raw_default: bool = False) -> ScoreScale:
    if scale_hint:
        return scale_hint
    numeric = _numeric_score_or_none(value)
    if raw_default:
        return "0_100"
    if numeric is not None and numeric > 10.0:
        return "0_100"
    return "0_10"


def _scale_for_display_field(value: Any, scale_hint: ScoreScale | None = None) -> ScoreScale:
    return _scale_for_value(value, scale_hint, raw_default=False)


def _scale_for_master_candidate(row: Dict[str, Any], key: str, value: Any) -> ScoreScale:
    if key == "master_score_raw":
        return "0_100"
    hint = _score_source_scale_hint(row) if key == "score" else _master_source_scale_hint(row)
    numeric = _numeric_score_or_none(value)
    if hint == "0_10":
        return "0_10"
    if hint == "0_100" and numeric is not None and numeric > 10.0:
        return "0_100"
    if hint == "0_100":
        return "0_10"
    return _scale_for_display_field(value, None)


def _scale_for_block_candidate(block: Dict[str, Any], key: str, value: Any) -> ScoreScale:
    if key in {"score_raw", "raw_score"}:
        return "0_100"
    hint = _score_source_scale_hint(block)
    numeric = _numeric_score_or_none(value)
    if hint == "0_10":
        return "0_10"
    if hint == "0_100" and numeric is not None and numeric > 10.0:
        return "0_100"
    if hint == "0_100":
        return "0_10"
    return _scale_for_display_field(value, None)


def normalize_master_score_display(value: Any, *, source_scale: ScoreScale) -> Tuple[float, str | None]:
    """Canonical product contract: Score Mestre exposed to users is always 0..10."""
    if source_scale not in _VALID_SCORE_SCALES:
        raise ValueError(f"Unsupported master score source scale: {source_scale}")
    numeric = _numeric_score_or_none(value)
    if numeric is None:
        return 0.0, "master_score_display_invalid"

    if numeric < 0:
        _log_display_warning_once("Score Mestre negativo normalizado para display", "below_0", numeric, 0.0)
        return 0.0, "master_score_display_clamped_below_0"
    if source_scale == "0_100":
        if numeric > 100:
            _log_display_warning_once("Score Mestre bruto acima do limite 0..100", "raw_above_100", numeric, 0.0)
            return 0.0, "master_score_display_invalid"
        display = max(0.0, min(10.0, _round_display_score(numeric / 10.0)))
        logger.debug(
            "Score Mestre bruto normalizado para escala 0..10",
            extra={"raw_score": numeric, "display_score": display},
        )
        return display, "master_score_normalized_from_raw_100"
    if source_scale != "0_10":
        raise ValueError(f"Unsupported master score source scale: {source_scale}")
    if numeric > 10:
        _log_display_warning_once("Score Mestre acima do limite de display 0..10", "above_10", numeric, 10.0)
        return 10.0, "master_score_display_clamped_above_10"
    return _round_display_score(numeric), None


def _without_display_warnings(value: Any) -> list[str]:
    if isinstance(value, list):
        warnings = [str(item) for item in value if str(item or "").strip()]
    elif value:
        warnings = [str(value)]
    else:
        warnings = []
    return [warning for warning in warnings if warning not in _DISPLAY_WARNING_CODES]


def resolve_master_score_display_value(row: Dict[str, Any]) -> tuple[float | None, str | None, ScoreScale | None]:
    invalid_display = row.get("master_score_display_warning") == "master_score_display_invalid"
    invalid_display_value = _numeric_score_or_none(row.get("master_score_display"))
    for key in ("master_score_raw", "master_score", "score"):
        raw = row.get(key)
        numeric_score = _numeric_score_or_none(raw)
        if numeric_score is None:
            continue
        if (
            invalid_display
            and invalid_display_value is not None
            and key in {"master_score", "score"}
            and _round_display_score(numeric_score) == _round_display_score(invalid_display_value)
        ):
            continue
        source_scale = _scale_for_master_candidate(row, key, raw)
        display_score, warning = normalize_master_score_display(raw, source_scale=source_scale)
        if warning != "master_score_display_invalid":
            return display_score, warning, source_scale
    return None, None, None


def attach_master_score_display_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    existing_warning = str(row.get("master_score_display_warning") or "")
    existing_display = _numeric_score_or_none(row.get("master_score_display"))
    candidate_raw = None
    candidate_source_scale: ScoreScale = "0_10"
    candidate_raw_is_true_source = False
    candidate_invalid: tuple[Any, ScoreScale] | None = None
    candidate_display: float | None = None
    for key in ("master_score_raw", "master_score", "score"):
        candidate = row.get(key)
        numeric = _numeric_score_or_none(candidate)
        if numeric is None:
            continue
        candidate_scale = _scale_for_master_candidate(row, key, candidate)
        candidate_display_value, candidate_warning = normalize_master_score_display(candidate, source_scale=candidate_scale)
        if candidate_warning == "master_score_display_invalid":
            if candidate_invalid is None:
                candidate_invalid = (candidate, candidate_scale)
            continue
        candidate_raw = candidate
        candidate_source_scale = candidate_scale
        candidate_raw_is_true_source = bool(candidate_scale == "0_100")
        candidate_display = candidate_display_value
        break
    if candidate_raw is None and candidate_invalid is not None:
        candidate_raw, candidate_source_scale = candidate_invalid
        candidate_display = normalize_master_score_display(candidate_raw, source_scale=candidate_source_scale)[0]
    reuse_existing_display = (
        existing_warning in _DISPLAY_WARNING_CODES
        and existing_display is not None
        and 0.0 <= existing_display <= 10.0
        and row.get("master_score_raw") in (None, "")
        and (
            candidate_display is None
            or _round_display_score(candidate_display) == _round_display_score(existing_display)
        )
    )
    raw = candidate_raw
    source_scale: ScoreScale = candidate_source_scale
    raw_is_true_source = False
    warning = None
    if reuse_existing_display:
        raw = existing_display
        display = existing_display
        warning = existing_warning
        source_scale = "0_10"
    else:
        raw_is_true_source = candidate_raw_is_true_source
        display, warning = normalize_master_score_display(raw, source_scale=source_scale)
    next_row = dict(row)
    raw_numeric = _numeric_score_or_none(raw)
    if raw_numeric is not None and raw_is_true_source:
        next_row["master_score_raw"] = round(raw_numeric, 1)
    else:
        next_row.pop("master_score_raw", None)
        if warning == "master_score_display_invalid":
            source_scale = "0_10"
    next_row["master_score"] = display
    next_row["master_score_source_scale"] = source_scale
    next_row.pop("master_score_display_warning", None)
    next_row.pop("master_score_display_invalid", None)
    if next_row.get("tool") == "master_score":
        next_row["score"] = display
    block = next_row.get("master_score_block")
    if isinstance(block, dict):
        existing_block_warning = str(block.get("score_warning") or "")
        existing_block_score = _numeric_score_or_none(block.get("score"))
        block_candidate_raw = None
        block_candidate_scale: ScoreScale = "0_10"
        block_candidate_invalid: tuple[Any, ScoreScale] | None = None
        block_candidate_display: float | None = None
        for key in ("score_raw", "raw_score", "score"):
            candidate = block.get(key)
            block_numeric_hint = _numeric_score_or_none(candidate)
            if block_numeric_hint is None:
                continue
            candidate_scale = _scale_for_block_candidate(block, key, candidate)
            block_display_value, block_warning_value = normalize_master_score_display(candidate, source_scale=candidate_scale)
            if block_warning_value == "master_score_display_invalid":
                if block_candidate_invalid is None:
                    block_candidate_invalid = (candidate, candidate_scale)
                continue
            block_candidate_raw = candidate
            block_candidate_scale = candidate_scale
            block_candidate_display = block_display_value
            break
        if block_candidate_raw is None and block_candidate_invalid is not None:
            block_candidate_raw, block_candidate_scale = block_candidate_invalid
            block_candidate_display = normalize_master_score_display(
                block_candidate_raw,
                source_scale=block_candidate_scale,
            )[0]
        reuse_existing_block = (
            existing_block_warning in _DISPLAY_WARNING_CODES
            and existing_block_score is not None
            and 0.0 <= existing_block_score <= 10.0
            and block.get("score_source_scale") in {"0_10", "0_100"}
            and block.get("score_raw") in (None, "")
            and block.get("raw_score") in (None, "")
            and (
                block_candidate_display is None
                or _round_display_score(block_candidate_display) == _round_display_score(existing_block_score)
            )
        )
        block_raw = block_candidate_raw
        block_scale: ScoreScale = block_candidate_scale
        if reuse_existing_block:
            block_raw = existing_block_score
            block_numeric = None
            block_score = existing_block_score
            block_warning = existing_block_warning
            block_scale = "0_10"
        else:
            block_numeric = _numeric_score_or_none(block_raw)
            block_score, block_warning = normalize_master_score_display(block_raw, source_scale=block_scale)
        next_block = dict(block)
        if block_numeric is not None and 0.0 <= block_numeric <= 100.0 and block_scale == "0_100":
            next_block["score_raw"] = round(block_numeric, 1)
        else:
            next_block.pop("score_raw", None)
            if block_warning == "master_score_display_invalid":
                block_scale = "0_10"
        next_block.pop("raw_score", None)
        next_block["score"] = block_score
        next_block["score_source_scale"] = block_scale
        if block_warning:
            next_block["score_warning"] = block_warning
        else:
            next_block.pop("score_warning", None)
        next_row["master_score_block"] = next_block
    next_row["master_score_display"] = display
    warnings = _without_display_warnings(next_row.get("warnings"))
    if warning:
        if warning not in warnings:
            warnings.append(warning)
        next_row["warnings"] = warnings
        next_row["master_score_display_warning"] = warning
    elif warnings:
        next_row["warnings"] = warnings
    else:
        next_row.pop("warnings", None)
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
