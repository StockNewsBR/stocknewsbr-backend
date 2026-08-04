from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from app.ai.institutional_auditor import AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.strategic_panel import ACTION_NO_TRADE
from app.services.snapshot_contract import (
    audit_status_value,
    coerce_data_quality,
    data_quality_score,
    is_auditor_blocked,
    master_status_value,
)
from app.system.system_metrics import record_operational_rules_metrics


OPERATIONAL_READY = "READY"
OPERATIONAL_CAUTION = "CAUTION"
OPERATIONAL_BLOCKED = "BLOCKED"

OPERATIONAL_VISUAL = {
    OPERATIONAL_READY: "🟢 READY",
    OPERATIONAL_CAUTION: "🟡 CAUTION",
    OPERATIONAL_BLOCKED: "🔴 BLOCKED",
}

BLOCKED_QUALITIES = {"score_only", "stale", "invalid", "empty"}
MIN_HISTORICAL_SAMPLE = 8


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _listify(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return [str(value).strip()]


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


def _risk_level(row: Dict[str, Any], risk_row: Dict[str, Any] | None) -> Tuple[str, bool, float | None]:
    panel = row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {}
    risk_block = panel.get("risk_block") if isinstance(panel.get("risk_block"), dict) else {}
    metrics = risk_row.get("metrics") if isinstance(risk_row, dict) and isinstance(risk_row.get("metrics"), dict) else {}
    risk_score = _safe_float(
        metrics.get("risk_score")
        or (risk_row or {}).get("risk_score")
        or risk_block.get("score")
        or (risk_row or {}).get("score"),
        -1.0,
    )
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("master_risk"),
            row.get("ranking_risk_level"),
            row.get("radar_risk_level"),
            risk_block.get("level"),
            risk_block.get("visual_level"),
            (risk_row or {}).get("state"),
            (risk_row or {}).get("ai_comment"),
            (risk_row or {}).get("risk_summary"),
            metrics.get("risk_summary"),
        )
    )
    if "critical" in text or "critico" in text or "crítico" in text or risk_score >= 85:
        return "Crítico", True, risk_score if risk_score >= 0 else None
    if "alto" in text or "high" in text or risk_score >= 70:
        return "Alto", False, risk_score if risk_score >= 0 else None
    if "moderado" in text or "médio" in text or "medio" in text or "medium" in text or risk_score >= 45:
        return "Moderado", False, risk_score if risk_score >= 0 else None
    if "baixo" in text or "low" in text or risk_score >= 0:
        return "Baixo", False, risk_score if risk_score >= 0 else None
    return str(row.get("master_risk") or "Baixo"), False, None


def _panel_no_trade(row: Dict[str, Any]) -> Tuple[bool, List[str]]:
    panel = row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {}
    action_block = panel.get("recommended_action_block") if isinstance(panel.get("recommended_action_block"), dict) else {}
    recommended = str(panel.get("recommended_action") or row.get("recommended_action") or action_block.get("action") or "").upper().strip()
    blocked = bool(panel.get("no_trade_now") is True or action_block.get("no_trade_now") is True or recommended == ACTION_NO_TRADE)
    reasons = _listify(panel.get("no_trade_reasons")) + _listify(action_block.get("reasons"))
    return blocked, reasons


def _blocked_reasons(row: Dict[str, Any], risk_level: str, risk_critical: bool) -> List[str]:
    reasons: List[str] = []
    quality = coerce_data_quality(row)
    panel_blocked, panel_reasons = _panel_no_trade(row)

    if is_auditor_blocked(row):
        reasons.extend(_listify(row.get("audit_blocks")) or ["auditor bloqueado"])
    if master_status_value(row) == AUDIT_BLOCKED:
        reasons.append("score mestre bloqueado")
    if row.get("decision_ready") is not True:
        reasons.append("decision_ready falso")
    if quality in BLOCKED_QUALITIES:
        reasons.append(f"data quality {quality}")
    if row.get("stale") is True or row.get("is_stale") is True:
        reasons.append("snapshot stale")
    if risk_critical or risk_level == "Crítico":
        reasons.append("risco critico")
    if row.get("radar_no_trade_now") is True:
        reasons.extend(_listify(row.get("radar_blocked_reasons")) or ["radar institucional bloqueou"])
    if panel_blocked:
        reasons.extend(panel_reasons or ["painel estrategico indicou nao operar"])

    return list(dict.fromkeys(reasons))


def _consensus_warning(row: Dict[str, Any]) -> str | None:
    consensus = row.get("master_consensus") if isinstance(row.get("master_consensus"), dict) else {}
    if not consensus:
        return None
    ratio = _safe_float(consensus.get("ratio"), 0.0)
    opposing = int(consensus.get("opposing_count", 0) or 0)
    if ratio < 0.44 or opposing >= 3:
        return "consenso baixo"
    return None


def _market_pulse_warning(market_pulse: Dict[str, Any] | None) -> str | None:
    if not isinstance(market_pulse, dict):
        return None
    sentiment = str(market_pulse.get("sentiment") or "").lower().strip()
    if sentiment in {"neutral", "mixed", "neutro", "range"}:
        return "market pulse neutro"
    return None


def _warnings(row: Dict[str, Any], risk_level: str, market_pulse: Dict[str, Any] | None) -> List[str]:
    warnings: List[str] = []
    if audit_status_value(row) == AUDIT_CAUTION or master_status_value(row) == AUDIT_CAUTION:
        warnings.append("auditor caution")
    confidence = str(row.get("master_confidence") or "").lower().strip()
    if confidence.startswith("baixa") or confidence.startswith("low"):
        warnings.append("confiança baixa")
    consensus = _consensus_warning(row)
    if consensus:
        warnings.append(consensus)
    if risk_level == "Alto":
        warnings.append("risco alto")
    sample_size = int(row.get("historical_sample_size", 0) or 0)
    historical_label = str(row.get("historical_confidence_label") or "").lower()
    if sample_size < MIN_HISTORICAL_SAMPLE or "amostra insuficiente" in historical_label:
        warnings.append("amostra histórica insuficiente")
    elif "baixa" in historical_label:
        warnings.append("confiança histórica baixa")
    market_warning = _market_pulse_warning(market_pulse)
    if market_warning:
        warnings.append(market_warning)
    if str(row.get("ranking_classification") or "").lower().find("observ") >= 0:
        warnings.append("ranking em observação")
    if str(row.get("radar_level") or "").lower().find("observ") >= 0:
        warnings.append("radar em observação")
    return list(dict.fromkeys(warnings))


def _risk_score_component(risk_level: str) -> float:
    if risk_level == "Baixo":
        return 100.0
    if risk_level == "Moderado":
        return 68.0
    if risk_level == "Alto":
        return 35.0
    if risk_level == "Crítico":
        return 0.0
    return 60.0


def _operational_score(row: Dict[str, Any], risk_level: str, blocks: List[str], warnings: List[str]) -> float:
    if blocks:
        return 0.0
    master_score = _safe_float(row.get("master_score") or row.get("score"), 0.0)
    ranking_score = _safe_float(row.get("ranking_opportunity_score"), master_score)
    radar_score = _safe_float(row.get("radar_prioritization_score") or row.get("radar_priority_score"), master_score)
    audit_score = _safe_float(row.get("audit_score"), 70.0)
    historical_score = _safe_float(row.get("historical_confidence_score"), 50.0)
    quality_score = data_quality_score(coerce_data_quality(row))
    score = (
        master_score * 0.25
        + ranking_score * 0.20
        + radar_score * 0.15
        + audit_score * 0.15
        + historical_score * 0.10
        + quality_score * 0.10
        + _risk_score_component(risk_level) * 0.05
    )
    score -= min(24.0, len(warnings) * 6.0)
    if warnings:
        score = min(score, 79.0)
    return max(0.0, min(100.0, round(score, 2)))


def _summary(status: str, blocks: List[str], warnings: List[str]) -> str:
    if status == OPERATIONAL_BLOCKED:
        reason = "; ".join(blocks[:4]) if blocks else "condições mínimas ausentes"
        return f"🔴 NÃO OPERAR AGORA. Motivos: {reason}."
    if status == OPERATIONAL_CAUTION:
        warning = "; ".join(warnings[:4]) if warnings else "contexto requer confirmação"
        return f"Contexto parcialmente favorável, porém {warning}."
    return "Condições mínimas presentes: leitura institucional, qualidade de dados e risco compatíveis com operação."


def enrich_operational_rules_rows(
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
        ticker = _ticker(row)
        item = dict(row)
        risk_level, risk_critical, risk_score = _risk_level(item, risk_rows.get(ticker))
        blocks = _blocked_reasons(item, risk_level, risk_critical)
        warnings = _warnings(item, risk_level, market_pulse) if not blocks else []
        status = OPERATIONAL_BLOCKED if blocks else OPERATIONAL_CAUTION if warnings else OPERATIONAL_READY
        item["operational_status"] = status
        item["operational_visual_status"] = OPERATIONAL_VISUAL[status]
        item["operational_ready"] = status == OPERATIONAL_READY
        item["operational_score"] = _operational_score(item, risk_level, blocks, warnings)
        item["operational_blocks"] = blocks
        item["operational_warnings"] = warnings
        item["operational_summary"] = _summary(status, blocks, warnings)
        item["operational_risk_level"] = risk_level
        item["operational_risk_score"] = risk_score
        output.append(item)

    metrics = _metrics(output)
    if record_metrics:
        record_operational_rules_metrics(metrics)
    return output, metrics


def apply_operational_rules_by_ticker(
    rows: Iterable[Dict[str, Any]],
    operational_rows: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    index = {
        _ticker(row): row
        for row in operational_rows or []
        if isinstance(row, dict) and _ticker(row)
    }
    fields = (
        "operational_status",
        "operational_visual_status",
        "operational_ready",
        "operational_score",
        "operational_blocks",
        "operational_warnings",
        "operational_summary",
        "operational_risk_level",
        "operational_risk_score",
    )
    output: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        operational = index.get(_ticker(item))
        if operational:
            for field in fields:
                item[field] = operational.get(field)
        output.append(item)
    return output


def ensure_operational_rules_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = False,
) -> List[Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if any("operational_status" in row for row in safe_rows):
        return safe_rows
    enriched, _metrics = enrich_operational_rules_rows(
        safe_rows,
        ai_tools=ai_tools,
        market_pulse=market_pulse,
        record_metrics=record_metrics,
    )
    return enriched


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    status_counts = Counter(str(row.get("operational_status") or "").upper() for row in safe_rows)
    blocks = Counter(reason for row in safe_rows for reason in _listify(row.get("operational_blocks")))
    warnings = Counter(reason for row in safe_rows for reason in _listify(row.get("operational_warnings")))
    return {
        "ready": int(status_counts.get(OPERATIONAL_READY, 0)),
        "caution": int(status_counts.get(OPERATIONAL_CAUTION, 0)),
        "blocked": int(status_counts.get(OPERATIONAL_BLOCKED, 0)),
        "top_blocks": dict(blocks.most_common(8)),
        "top_warnings": dict(warnings.most_common(8)),
    }
