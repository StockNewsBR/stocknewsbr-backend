from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_CAUTION
from app.ai.operational_rules import OPERATIONAL_BLOCKED, OPERATIONAL_CAUTION, OPERATIONAL_READY
from app.services.snapshot_contract import audit_status_value
from app.system.system_metrics import record_institutional_priority_metrics


PRIORITY_CRITICAL = "🚨 CRÍTICA"
PRIORITY_HIGH = "🔥 ALTA"
PRIORITY_MEDIUM = "🟡 MÉDIA"
PRIORITY_LOW = "⚪ BAIXA"


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _risk_index(ai_tools: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    rows = ai_tools.get("risk") if isinstance(ai_tools, dict) else []
    if not isinstance(rows, list):
        return {}
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row)
        if ticker and ticker not in output:
            output[ticker] = row
    return output


def _risk_level(row: Dict[str, Any], risk_row: Dict[str, Any] | None) -> str:
    metrics = risk_row.get("metrics") if isinstance(risk_row, dict) and isinstance(risk_row.get("metrics"), dict) else {}
    score = _safe_float(metrics.get("risk_score") or (risk_row or {}).get("risk_score") or (risk_row or {}).get("score"), -1.0)
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("master_risk"),
            row.get("operational_risk_level"),
            row.get("ranking_risk_level"),
            row.get("radar_risk_level"),
            (risk_row or {}).get("state"),
            (risk_row or {}).get("ai_comment"),
            metrics.get("risk_summary"),
        )
    )
    if "critical" in text or "critico" in text or "crítico" in text or score >= 85:
        return "Crítico"
    if "alto" in text or "high" in text or score >= 70:
        return "Alto"
    if "moderado" in text or "medio" in text or "médio" in text or "medium" in text or score >= 45:
        return "Moderado"
    return "Baixo"


def _is_blocked(row: Dict[str, Any]) -> bool:
    return str(row.get("operational_status") or "").upper() == OPERATIONAL_BLOCKED


def _level(score: float, blocked: bool) -> str:
    if blocked:
        return PRIORITY_LOW
    if score >= 88:
        return PRIORITY_CRITICAL
    if score >= 74:
        return PRIORITY_HIGH
    if score >= 55:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def _score_and_factors(row: Dict[str, Any], risk_level: str, market_pulse: Dict[str, Any] | None) -> Tuple[float, List[str]]:
    if _is_blocked(row):
        factors = ["regras operacionais bloquearam a oportunidade"]
        factors.extend(str(item) for item in row.get("operational_blocks") or [] if str(item or "").strip())
        return 0.0, list(dict.fromkeys(factors))[:8]

    factors: List[str] = []
    score = 0.0
    score += _safe_float(row.get("radar_prioritization_score") or row.get("radar_priority_score"), 0.0) * 0.20
    score += _safe_float(row.get("ranking_opportunity_score"), 0.0) * 0.22
    score += _safe_float(row.get("conviction_score"), 0.0) * 0.24
    score += _safe_float(row.get("historical_confidence_score"), 0.0) * 0.10
    score += _safe_float(row.get("operational_score"), 0.0) * 0.14
    score += _safe_float(row.get("audit_score"), 70.0) * 0.05

    if str(row.get("radar_level") or row.get("radar_priority") or "").lower().find("prioridade alta") >= 0:
        score += 5.0
        factors.append("Radar prioridade alta")
    if str(row.get("ranking_classification") or "").lower().find("excelente") >= 0:
        score += 5.0
        factors.append("Ranking excelente")
    if str(row.get("conviction_level") or "").lower().find("muito alta") >= 0:
        score += 7.0
        factors.append("Convicção muito alta")
    elif str(row.get("conviction_level") or "").lower().find("baixa") >= 0:
        score -= 12.0
        factors.append("convicção baixa")
    if str(row.get("historical_confidence_label") or "").lower().find("alta") >= 0:
        score += 4.0
        factors.append("histórico favorável")
    elif str(row.get("historical_confidence_label") or "").lower().find("baixa") >= 0:
        score -= 8.0
        factors.append("histórico fraco")
    if audit_status_value(row) == AUDIT_APPROVED:
        score += 4.0
        factors.append("Auditor aprovado")
    elif audit_status_value(row) == AUDIT_CAUTION:
        score -= 8.0
        factors.append("Auditor caution")
    if str(row.get("operational_status") or "").upper() == OPERATIONAL_READY:
        score += 6.0
        factors.append("Operational READY")
    elif str(row.get("operational_status") or "").upper() == OPERATIONAL_CAUTION:
        score -= 7.0
        factors.append("Operational CAUTION")
    if risk_level == "Baixo":
        score += 5.0
        factors.append("risco baixo")
    elif risk_level == "Alto":
        score -= 12.0
        factors.append("risco alto")
    elif risk_level == "Crítico":
        score -= 24.0
        factors.append("risco crítico")
    sentiment = str((market_pulse or {}).get("sentiment") or "").lower() if isinstance(market_pulse, dict) else ""
    if sentiment in {"neutral", "mixed", "neutro", "range"}:
        score -= 6.0
        factors.append("Market Pulse neutro")
    return max(0.0, min(100.0, round(score, 2))), list(dict.fromkeys(factors))[:8]


def _summary(level: str, factors: List[str]) -> str:
    base = ", ".join(factors[:4]) if factors else "Evidência em formação"
    return f"{level}: prioridade definida por {base}."


def enrich_institutional_priority_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    risk_rows = _risk_index(ai_tools)
    output: List[Dict[str, Any]] = []

    for row in safe_rows:
        item = dict(row)
        risk_level = _risk_level(item, risk_rows.get(_ticker(item)))
        score, factors = _score_and_factors(item, risk_level, market_pulse)
        level = _level(score, _is_blocked(item))
        item["priority_score"] = score
        item["priority_level"] = level
        item["priority_rank"] = None
        item["priority_factors"] = factors
        item["priority_summary"] = _summary(level, factors)
        item["priority_risk_level"] = risk_level
        output.append(item)

    eligible = [
        row
        for row in output
        if not _is_blocked(row)
        and str(row.get("operational_status") or "").upper() in {OPERATIONAL_READY, OPERATIONAL_CAUTION}
        and row.get("ranking_eligible") is not False
        and row.get("radar_no_trade_now") is not True
    ]
    eligible.sort(key=lambda row: _safe_float(row.get("priority_score"), 0.0), reverse=True)
    for index, row in enumerate(eligible, start=1):
        row["priority_rank"] = index

    metrics = _metrics(output)
    if record_metrics:
        record_institutional_priority_metrics(metrics)
    return output, metrics


def apply_priority_by_ticker(rows: Iterable[Dict[str, Any]], priority_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index = {
        _ticker(row): row
        for row in priority_rows or []
        if isinstance(row, dict) and _ticker(row)
    }
    fields = ("priority_score", "priority_level", "priority_rank", "priority_summary", "priority_factors", "priority_risk_level")
    output: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        priority = index.get(_ticker(item))
        if priority:
            for field in fields:
                item[field] = priority.get(field)
        output.append(item)
    return output


def ensure_institutional_priority_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = False,
) -> List[Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if safe_rows and all("priority_score" in row for row in safe_rows):
        return safe_rows
    enriched, _metrics = enrich_institutional_priority_rows(
        safe_rows,
        ai_tools=ai_tools,
        market_pulse=market_pulse,
        record_metrics=record_metrics,
    )
    return enriched


def priority_items(rows: Iterable[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    items = [dict(row) for row in rows or [] if isinstance(row, dict) and row.get("priority_rank") is not None]
    items.sort(key=lambda row: int(row.get("priority_rank", 9999) or 9999))
    return items[:limit]


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    levels = Counter(str(row.get("priority_level") or "") for row in rows or [] if isinstance(row, dict))
    return {
        "critical": int(levels.get(PRIORITY_CRITICAL, 0)),
        "high": int(levels.get(PRIORITY_HIGH, 0)),
        "medium": int(levels.get(PRIORITY_MEDIUM, 0)),
        "low": int(levels.get(PRIORITY_LOW, 0)),
    }
