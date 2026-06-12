from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.operational_rules import OPERATIONAL_BLOCKED, OPERATIONAL_CAUTION, OPERATIONAL_READY
from app.services.snapshot_contract import audit_status_value
from app.system.system_metrics import record_final_decision_metrics


FINAL_CONFIRMED = "🟢 OPORTUNIDADE CONFIRMADA"
FINAL_FORMING = "🟡 OPORTUNIDADE EM FORMAÇÃO"
FINAL_OBSERVE = "⚪ OBSERVAR"
FINAL_WAIT = "⚪ AGUARDAR"
FINAL_NO_TRADE = "🔴 NÃO OPERAR AGORA"


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


def _risk_level(row: Dict[str, Any], risk_row: Dict[str, Any] | None) -> str:
    panel = row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {}
    risk_block = panel.get("risk_block") if isinstance(panel.get("risk_block"), dict) else {}
    metrics = risk_row.get("metrics") if isinstance(risk_row, dict) and isinstance(risk_row.get("metrics"), dict) else {}
    score = _safe_float(
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
            row.get("operational_risk_level"),
            row.get("priority_risk_level"),
            risk_block.get("level"),
            risk_block.get("visual_level"),
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


def _confidence_points(value: Any) -> float:
    text = str(value or "").lower().strip()
    if text.startswith("alta") or text.startswith("muito alta"):
        return 90.0
    if text.startswith(("média", "media", "moderada")):
        return 65.0
    if text.startswith("baixa"):
        return 35.0
    return 50.0


def _final_confidence(row: Dict[str, Any]) -> str:
    score = (
        _safe_float(row.get("conviction_score"), 0.0) * 0.35
        + _safe_float(row.get("historical_confidence_score"), 0.0) * 0.20
        + _safe_float(row.get("audit_score"), 60.0) * 0.15
        + _confidence_points(row.get("master_confidence")) * 0.15
        + _safe_float(row.get("priority_score"), 0.0) * 0.15
    )
    if score >= 78:
        return "Alta"
    if score >= 55:
        return "Média"
    return "Baixa"


def _blocking_reasons(row: Dict[str, Any], risk_level: str) -> List[str]:
    reasons: List[str] = []
    operational_status = str(row.get("operational_status") or "").upper().strip()
    audit_status = audit_status_value(row)

    if operational_status == OPERATIONAL_BLOCKED:
        reasons.extend(_listify(row.get("operational_blocks")) or ["regras operacionais bloquearam"])
    if audit_status == AUDIT_BLOCKED or row.get("blocked_by_auditor") is True:
        reasons.extend(_listify(row.get("audit_blocks")) or ["auditor bloqueado"])
    if row.get("decision_ready") is not True:
        reasons.append("decision_ready falso")
    if risk_level == "Crítico":
        reasons.append("risco crítico")
    reasons.extend(_listify(row.get("ranking_excluded_reasons")) if row.get("ranking_eligible") is False else [])
    reasons.extend(_listify(row.get("radar_blocked_reasons")) if row.get("radar_no_trade_now") is True else [])
    return list(dict.fromkeys(reasons))[:8]


def _score(row: Dict[str, Any], risk_level: str, market_pulse: Dict[str, Any] | None) -> float:
    score = (
        _safe_float(row.get("priority_score"), 0.0) * 0.24
        + _safe_float(row.get("conviction_score"), 0.0) * 0.22
        + _safe_float(row.get("ranking_opportunity_score"), 0.0) * 0.16
        + _safe_float(row.get("radar_prioritization_score") or row.get("radar_priority_score"), 0.0) * 0.12
        + _safe_float(row.get("historical_confidence_score"), 0.0) * 0.10
        + _safe_float(row.get("operational_score"), 0.0) * 0.10
        + _safe_float(row.get("audit_score"), 60.0) * 0.06
    )
    if audit_status_value(row) == AUDIT_CAUTION:
        score -= 8.0
    if str(row.get("operational_status") or "").upper() == OPERATIONAL_CAUTION:
        score -= 6.0
    if risk_level == "Moderado":
        score -= 4.0
    elif risk_level == "Alto":
        score -= 14.0
    sentiment = str((market_pulse or {}).get("sentiment") or "").lower() if isinstance(market_pulse, dict) else ""
    if sentiment in {"neutral", "mixed", "neutro", "range"}:
        score -= 4.0
    return max(0.0, min(100.0, round(score, 2)))


def _high_conviction(row: Dict[str, Any]) -> bool:
    level = str(row.get("conviction_level") or "").lower()
    return "muito alta" in level or ("alta" in level and "baixa" not in level)


def _high_priority(row: Dict[str, Any]) -> bool:
    level = str(row.get("priority_level") or "").lower()
    return "crítica" in level or "critica" in level or "alta" in level


def _strong_ranking(row: Dict[str, Any]) -> bool:
    value = str(row.get("ranking_classification") or "").lower()
    return "excelente" in value or "forte" in value


def _high_radar(row: Dict[str, Any]) -> bool:
    value = str(row.get("radar_level") or row.get("radar_priority") or "").lower()
    return "prioridade alta" in value


def _mixed_signals(row: Dict[str, Any], risk_level: str) -> bool:
    consensus = row.get("master_consensus") if isinstance(row.get("master_consensus"), dict) else {}
    consensus_low = _safe_float(consensus.get("ratio"), 1.0) < 0.44 if consensus else False
    return bool(
        audit_status_value(row) == AUDIT_CAUTION
        or str(row.get("operational_status") or "").upper() == OPERATIONAL_CAUTION
        or _listify(row.get("conviction_conflicts"))
        or "baixa" in str(row.get("conviction_level") or "").lower()
        or risk_level == "Alto"
        or consensus_low
    )


def _decision(row: Dict[str, Any], score: float, risk_level: str, blocks: List[str]) -> str:
    if blocks:
        return FINAL_NO_TRADE

    confirmed = (
        audit_status_value(row) == AUDIT_APPROVED
        and str(row.get("operational_status") or "").upper() == OPERATIONAL_READY
        and _high_conviction(row)
        and _high_priority(row)
        and _strong_ranking(row)
        and _high_radar(row)
        and risk_level in {"Baixo", "Moderado"}
    )
    if confirmed:
        return FINAL_CONFIRMED

    favorable = score >= 65 or (
        (_high_priority(row) or _strong_ranking(row) or _high_conviction(row))
        and str(row.get("operational_status") or "").upper() in {OPERATIONAL_READY, OPERATIONAL_CAUTION}
    )
    if favorable:
        return FINAL_FORMING
    if _mixed_signals(row, risk_level):
        return FINAL_OBSERVE
    return FINAL_WAIT


def _reason(row: Dict[str, Any], decision: str, risk_level: str, blocks: List[str]) -> str:
    if decision == FINAL_NO_TRADE:
        return "NÃO OPERAR AGORA: " + "; ".join(blocks[:4])

    parts: List[str] = []
    if audit_status_value(row) == AUDIT_APPROVED:
        parts.append("Auditor aprovado")
    elif audit_status_value(row) == AUDIT_CAUTION:
        parts.append("Auditor em atenção")
    if _high_conviction(row):
        parts.append(str(row.get("conviction_level") or "convicção alta").replace("🔥 ", "").replace("🟢 ", "Convicção "))
    if _high_priority(row):
        parts.append(str(row.get("priority_level") or "prioridade alta").replace("🚨 ", "prioridade ").replace("🔥 ", "prioridade "))
    if _strong_ranking(row):
        parts.append(str(row.get("ranking_classification") or "Ranking forte").replace("🥇 ", "Ranking ").replace("🥈 ", "Ranking "))
    if str(row.get("historical_confidence_label") or "").lower().find("alta") >= 0:
        parts.append("histórico favorável")
    if risk_level in {"Baixo", "Moderado"}:
        parts.append(f"risco {risk_level.lower()}")
    elif risk_level == "Alto":
        parts.append("risco alto")
    if not parts:
        parts.append(str(row.get("master_summary") or "evidência institucional insuficiente")[:120])
    return ", ".join(parts[:5]).rstrip(".") + "."


def _summary(decision: str, reason: str) -> str:
    summary = f"{decision}: {reason}"
    if len(summary) > 220:
        summary = summary[:217].rstrip(" ,.;") + "..."
    return summary


def enrich_final_decision_rows(
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
        blocks = _blocking_reasons(item, risk_level)
        score = 0.0 if blocks else _score(item, risk_level, market_pulse)
        decision = _decision(item, score, risk_level, blocks)
        reason = _reason(item, decision, risk_level, blocks)
        item["final_decision"] = decision
        item["final_decision_score"] = score
        item["final_decision_reason"] = reason
        item["final_decision_blocks"] = blocks
        item["final_decision_confidence"] = "Baixa" if blocks else _final_confidence(item)
        item["final_decision_summary"] = _summary(decision, reason)
        item["final_decision_risk_level"] = risk_level
        output.append(item)

    metrics = _metrics(output)
    if record_metrics:
        record_final_decision_metrics(metrics)
    return output, metrics


def ensure_final_decision_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = False,
) -> List[Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if safe_rows and all("final_decision" in row for row in safe_rows):
        return safe_rows
    enriched, _metrics = enrich_final_decision_rows(
        safe_rows,
        ai_tools=ai_tools,
        market_pulse=market_pulse,
        record_metrics=record_metrics,
    )
    return enriched


def final_decision_items(rows: Iterable[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    items = [dict(row) for row in rows or [] if isinstance(row, dict) and row.get("final_decision")]
    items.sort(key=lambda row: _safe_float(row.get("final_decision_score"), 0.0), reverse=True)
    return items[:limit]


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    levels = Counter(str(row.get("final_decision") or "") for row in rows or [] if isinstance(row, dict))
    return {
        "confirmed": int(levels.get(FINAL_CONFIRMED, 0)),
        "forming": int(levels.get(FINAL_FORMING, 0)),
        "observe": int(levels.get(FINAL_OBSERVE, 0)),
        "wait": int(levels.get(FINAL_WAIT, 0)),
        "no_trade": int(levels.get(FINAL_NO_TRADE, 0)),
    }
