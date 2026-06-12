from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from app.ai.institutional_auditor import AUDIT_BLOCKED
from app.services.signal_history import get_history
from app.services.snapshot_contract import audit_status_value, coerce_data_quality
from app.system.system_metrics import record_historical_confidence_metrics


HISTORICAL_HIGH = "🟢 Alta Confiança Histórica"
HISTORICAL_MODERATE = "🟡 Confiança Histórica Moderada"
HISTORICAL_LOW = "🔴 Baixa Confiança Histórica"
HISTORICAL_INSUFFICIENT = "⚪ Amostra Insuficiente"

MIN_SAMPLE_SIZE = 8
MIN_CONTEXT_MATCH = 50.0


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _master_direction(row: Dict[str, Any]) -> str:
    value = str(row.get("master_direction") or "").upper().strip()
    if value in {"BULLISH", "BEARISH", "NEUTRAL"}:
        return value
    signal = str(row.get("trade_action") or row.get("signal") or "").upper().strip()
    if signal in {"BUY", "COVER", "WATCH_BUY"}:
        return "BULLISH"
    if signal in {"SELL", "SHORT", "WATCH_SHORT"}:
        return "BEARISH"
    return "NEUTRAL"


def _score_bucket(value: Any) -> str:
    score = _safe_float(value, -1.0)
    if score < 0:
        return "unknown"
    if score >= 80:
        return "very_high"
    if score >= 65:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _label_bucket(value: Any) -> str:
    text = _normalized_text(value)
    if text.startswith("alta") or text.startswith("high"):
        return "high"
    if text.startswith(("média", "media", "medium")):
        return "medium"
    if text.startswith("baixa") or text.startswith("low"):
        return "low"
    return "unknown"


def _priority_bucket(value: Any) -> str:
    text = _normalized_text(value)
    if "alta" in text or "excelente" in text or "prioridade alta" in text:
        return "high"
    if "forte" in text or "média" in text or "media" in text or "moderada" in text:
        return "medium"
    if "observ" in text:
        return "watch"
    if "bloque" in text or "não operar" in text or "nao operar" in text:
        return "blocked"
    return "unknown"


def _regime(row: Dict[str, Any]) -> str:
    for key in ("market_regime_state", "chart_regime_state", "regime_state", "regime"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("state")
        text = _normalized_text(value)
        if text:
            return text
    return "unknown"


def _timestamp(row: Dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "generated_at", "detected_at", "market_data_updated_at", "last_updated", "updated_at"):
        value = row.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)):
            try:
                raw = float(value)
                if raw > 10_000_000_000:
                    raw /= 1000.0
                return datetime.fromtimestamp(raw, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                continue
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                parsed = datetime.fromisoformat(text)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def _time_bucket(row: Dict[str, Any]) -> str:
    parsed = _timestamp(row)
    if not parsed:
        return "unknown"
    hour = parsed.hour
    if 10 <= hour < 12:
        return "opening"
    if 12 <= hour < 16:
        return "midday"
    if 16 <= hour < 19:
        return "closing"
    return "outside"


def _context(row: Dict[str, Any]) -> Dict[str, str]:
    return {
        "ticker": _ticker(row),
        "direction": _master_direction(row),
        "score_bucket": _score_bucket(row.get("master_score") or row.get("score")),
        "conviction": _label_bucket(row.get("master_conviction")),
        "confidence": _label_bucket(row.get("master_confidence")),
        "audit_status": str(audit_status_value(row) or row.get("master_status") or "").upper().strip() or "UNKNOWN",
        "radar_priority": _priority_bucket(row.get("radar_level") or row.get("radar_priority")),
        "ranking_classification": _priority_bucket(row.get("ranking_classification")),
        "regime": _regime(row),
        "time_bucket": _time_bucket(row),
        "data_quality": coerce_data_quality(row),
    }


def _known_outcome(row: Dict[str, Any]) -> Tuple[bool | None, Dict[str, Any]]:
    text = _normalized_text(
        row.get("historical_result")
        or row.get("outcome")
        or row.get("result")
        or row.get("trade_result")
        or row.get("signal_result")
    )
    if text in {"win", "winner", "acerto", "gain", "success", "true_positive"}:
        return True, {}
    if text in {"loss", "loser", "erro", "failure", "fail", "false_positive"}:
        return False, {}
    for key in ("hit", "is_win", "success"):
        if isinstance(row.get(key), bool):
            return bool(row.get(key)), {}
    for key in ("return_pct", "pnl_pct", "future_return_pct", "movement_pct"):
        if row.get(key) not in (None, ""):
            value = _safe_float(row.get(key), 0.0)
            direction = _master_direction(row)
            if direction == "BEARISH":
                return value < 0, {"movement_pct": value}
            return value > 0, {"movement_pct": value}
    favorable = row.get("favorable_move_pct")
    adverse = row.get("adverse_move_pct")
    if favorable not in (None, "") or adverse not in (None, ""):
        fav = abs(_safe_float(favorable, 0.0))
        adv = abs(_safe_float(adverse, 0.0))
        return fav > adv, {"favorable_move_pct": fav, "adverse_move_pct": adv}
    if row.get("false_positive") is True:
        return False, {}
    if row.get("false_negative") is True:
        return False, {"false_negative": True}
    return None, {}


def _context_match(current: Dict[str, str], historical: Dict[str, str]) -> float:
    if current.get("ticker") and historical.get("ticker") and current["ticker"] != historical["ticker"]:
        return 0.0
    if current.get("direction") in {"BULLISH", "BEARISH"} and historical.get("direction") in {"BULLISH", "BEARISH"}:
        if current["direction"] != historical["direction"]:
            return 0.0

    weighted_fields = (
        ("direction", 22.0),
        ("score_bucket", 15.0),
        ("conviction", 10.0),
        ("confidence", 10.0),
        ("audit_status", 10.0),
        ("radar_priority", 9.0),
        ("ranking_classification", 9.0),
        ("regime", 7.0),
        ("time_bucket", 4.0),
        ("data_quality", 4.0),
    )
    total = 0.0
    matched = 0.0
    for field, weight in weighted_fields:
        current_value = current.get(field, "unknown")
        historical_value = historical.get(field, "unknown")
        if current_value == "unknown" or historical_value == "unknown":
            continue
        total += weight
        if current_value == historical_value:
            matched += weight
    if total <= 0:
        return 0.0
    return round((matched / total) * 100.0, 2)


def _history_rows(history_rows: Iterable[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    if history_rows is not None:
        return [dict(row) for row in history_rows or [] if isinstance(row, dict)]
    try:
        return [dict(row) for row in get_history() if isinstance(row, dict)]
    except Exception:
        return []


def _label(score: float, sample_size: int) -> str:
    if sample_size < MIN_SAMPLE_SIZE:
        return HISTORICAL_INSUFFICIENT
    if score >= 75:
        return HISTORICAL_HIGH
    if score >= 55:
        return HISTORICAL_MODERATE
    return HISTORICAL_LOW


def _reason(label: str, sample_size: int, win_rate: float | None, context_match: float, row: Dict[str, Any]) -> str:
    direction = _master_direction(row).lower()
    if sample_size < MIN_SAMPLE_SIZE:
        return "Poucos sinais similares encontrados para validar historicamente."
    rate = round(float(win_rate or 0.0), 1)
    if label == HISTORICAL_HIGH:
        return f"Leituras {direction} semelhantes tiveram bom desempenho historico, com win rate de {rate}% e contexto semelhante."
    if label == HISTORICAL_MODERATE:
        return f"Leituras {direction} semelhantes tiveram desempenho moderado, com win rate de {rate}% e match de contexto de {round(context_match, 1)}%."
    return f"Leituras {direction} semelhantes tiveram desempenho fraco, com win rate de {rate}% nos registros comparaveis."


def _warning(row: Dict[str, Any], sample_size: int, label: str) -> str:
    warnings: List[str] = []
    if sample_size < MIN_SAMPLE_SIZE:
        warnings.append("Amostra insuficiente; não tratar como verdade estatística.")
    if audit_status_value(row) == AUDIT_BLOCKED or str(row.get("master_status") or "").upper() == AUDIT_BLOCKED:
        warnings.append("Auditor/Score Mestre bloqueado; confiança histórica não libera operação.")
    quality = coerce_data_quality(row)
    if quality in {"score_only", "stale", "invalid", "empty"}:
        warnings.append(f"Data quality {quality}; leitura histórica apenas informativa.")
    if label == HISTORICAL_LOW and sample_size >= MIN_SAMPLE_SIZE:
        warnings.append("Histórico desfavorável; usar apenas como alerta operacional.")
    return " ".join(warnings)


def _confidence_for_row(row: Dict[str, Any], history_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_context = _context(row)
    matches: List[Tuple[float, bool, Dict[str, Any]]] = []
    for historical in history_rows:
        outcome, stats = _known_outcome(historical)
        if outcome is None:
            continue
        match = _context_match(current_context, _context(historical))
        if match >= MIN_CONTEXT_MATCH:
            matches.append((match, outcome, stats))

    sample_size = len(matches)
    if sample_size <= 0:
        score = 0.0
        win_rate = None
        context_match = 0.0
    else:
        wins = sum(1 for _match, outcome, _stats in matches if outcome)
        win_rate = round((wins / sample_size) * 100.0, 2)
        context_match = round(sum(match for match, _outcome, _stats in matches) / sample_size, 2)
        score = round((win_rate * 0.72) + (context_match * 0.28), 2)

    label = _label(score, sample_size)
    if sample_size < MIN_SAMPLE_SIZE:
        score = 0.0
        win_rate = None if sample_size == 0 else win_rate

    result_stats = {
        "wins": sum(1 for _match, outcome, _stats in matches if outcome),
        "losses": sum(1 for _match, outcome, _stats in matches if not outcome),
    }
    favorable_values = [_safe_float(stats.get("favorable_move_pct"), 0.0) for _match, _outcome, stats in matches if "favorable_move_pct" in stats]
    adverse_values = [_safe_float(stats.get("adverse_move_pct"), 0.0) for _match, _outcome, stats in matches if "adverse_move_pct" in stats]
    if favorable_values:
        result_stats["avg_favorable_move_pct"] = round(sum(favorable_values) / len(favorable_values), 2)
    if adverse_values:
        result_stats["avg_adverse_move_pct"] = round(sum(adverse_values) / len(adverse_values), 2)

    return {
        "historical_confidence_score": score,
        "historical_confidence_label": label,
        "historical_sample_size": sample_size,
        "historical_win_rate": win_rate,
        "historical_context_match": context_match,
        "historical_reason": _reason(label, sample_size, win_rate, context_match, row),
        "historical_warning": _warning(row, sample_size, label),
        "historical_result_stats": result_stats,
    }


def enrich_historical_confidence_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    history_rows: Iterable[Dict[str, Any]] | None = None,
    record_metrics: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    history = _history_rows(history_rows)
    output: List[Dict[str, Any]] = []
    for row in safe_rows:
        item = dict(row)
        item.update(_confidence_for_row(item, history))
        output.append(item)

    metrics = _metrics(output)
    if record_metrics:
        record_historical_confidence_metrics(metrics)
    return output, metrics


def historical_confidence_items(rows: Iterable[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    items = [
        dict(row)
        for row in rows or []
        if isinstance(row, dict) and "historical_confidence_score" in row
    ]
    items.sort(
        key=lambda row: (
            int(row.get("historical_sample_size", 0) or 0),
            _safe_float(row.get("historical_confidence_score"), 0.0),
        ),
        reverse=True,
    )
    return items[:limit]


def apply_historical_confidence_by_ticker(
    rows: Iterable[Dict[str, Any]],
    historical_rows: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    index = {
        _ticker(row): row
        for row in historical_rows or []
        if isinstance(row, dict) and _ticker(row)
    }
    output: List[Dict[str, Any]] = []
    fields = (
        "historical_confidence_score",
        "historical_confidence_label",
        "historical_sample_size",
        "historical_win_rate",
        "historical_context_match",
        "historical_reason",
        "historical_warning",
        "historical_result_stats",
    )
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        historical = index.get(_ticker(item))
        if historical:
            for field in fields:
                item[field] = historical.get(field)
        output.append(item)
    return output


def ensure_historical_confidence_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    history_rows: Iterable[Dict[str, Any]] | None = None,
    record_metrics: bool = False,
) -> List[Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if any("historical_confidence_score" in row for row in safe_rows):
        return safe_rows
    enriched, _metrics = enrich_historical_confidence_rows(
        safe_rows,
        history_rows=history_rows,
        record_metrics=record_metrics,
    )
    return enriched


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    with_samples = [row for row in safe_rows if int(row.get("historical_sample_size", 0) or 0) >= MIN_SAMPLE_SIZE]
    by_ticker: Dict[str, Dict[str, Any]] = {}
    for row in safe_rows:
        ticker = _ticker(row)
        if not ticker:
            continue
        by_ticker[ticker] = {
            "historical_confidence_score": row.get("historical_confidence_score"),
            "historical_sample_size": row.get("historical_sample_size"),
            "historical_win_rate": row.get("historical_win_rate"),
            "historical_confidence_label": row.get("historical_confidence_label"),
        }
    avg_confidence = round(
        sum(_safe_float(row.get("historical_confidence_score"), 0.0) for row in with_samples) / max(1, len(with_samples)),
        2,
    )
    avg_sample = round(
        sum(int(row.get("historical_sample_size", 0) or 0) for row in safe_rows) / max(1, len(safe_rows)),
        2,
    )
    aggregate_win_rate = round(
        sum(_safe_float(row.get("historical_win_rate"), 0.0) for row in with_samples) / max(1, len(with_samples)),
        2,
    )
    return {
        "signals": len(safe_rows),
        "average_confidence_score": avg_confidence,
        "average_sample_size": avg_sample,
        "signals_without_sample": sum(1 for row in safe_rows if int(row.get("historical_sample_size", 0) or 0) < MIN_SAMPLE_SIZE),
        "aggregate_win_rate": aggregate_win_rate,
        "by_ticker": by_ticker,
    }
