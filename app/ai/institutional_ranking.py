from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Tuple

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.strategic_panel import ACTION_NO_TRADE
from app.services.snapshot_contract import (
    audit_status_value,
    coerce_data_quality,
    is_actionable_snapshot_row,
    is_auditor_blocked,
    master_status_value,
)
from app.system.system_metrics import record_institutional_ranking_metrics


RANKING_EXCELLENT = "🥇 Excelente"
RANKING_STRONG = "🥈 Forte"
RANKING_MODERATE = "🥉 Moderada"
RANKING_WATCH = "⚪ Observação"
RANKING_NO_TRADE = "NÃO OPERAR AGORA"

BLOCKED_QUALITIES = {"score_only", "stale", "invalid", "empty"}


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


def _risk_from_sources(row: Dict[str, Any], risk_row: Dict[str, Any] | None) -> Tuple[str, bool, float | None]:
    panel = row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {}
    risk_block = panel.get("risk_block") if isinstance(panel.get("risk_block"), dict) else {}
    risk_metrics = risk_row.get("metrics") if isinstance(risk_row, dict) and isinstance(risk_row.get("metrics"), dict) else {}
    risk_score = _safe_float(
        risk_metrics.get("risk_score")
        or (risk_row or {}).get("risk_score")
        or risk_block.get("score")
        or (risk_row or {}).get("score"),
        -1.0,
    )
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("master_risk"),
            row.get("radar_risk_level"),
            risk_block.get("level"),
            risk_block.get("visual_level"),
            (risk_row or {}).get("state"),
            (risk_row or {}).get("ai_comment"),
            (risk_row or {}).get("risk_summary"),
            risk_metrics.get("risk_summary"),
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


def _panel_blocks(row: Dict[str, Any]) -> Tuple[bool, List[str]]:
    panel = row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {}
    action_block = panel.get("recommended_action_block") if isinstance(panel.get("recommended_action_block"), dict) else {}
    recommended = str(panel.get("recommended_action") or row.get("recommended_action") or action_block.get("action") or "").upper().strip()
    blocked = bool(panel.get("no_trade_now") is True or action_block.get("no_trade_now") is True or recommended == ACTION_NO_TRADE)
    reasons = _listify(panel.get("no_trade_reasons")) + _listify(action_block.get("reasons"))
    return blocked, reasons


def _blocked_reasons(row: Dict[str, Any], risk_level: str, risk_critical: bool) -> List[str]:
    reasons: List[str] = []
    quality = coerce_data_quality(row)
    panel_blocked, panel_reasons = _panel_blocks(row)

    if is_auditor_blocked(row):
        reasons.extend(_listify(row.get("audit_blocks")) or ["auditor institucional bloqueou"])
    if master_status_value(row) == AUDIT_BLOCKED:
        reasons.append("score mestre bloqueou")
    if panel_blocked:
        reasons.extend(panel_reasons or ["painel estrategico bloqueou"])
    if row.get("radar_no_trade_now") is True:
        reasons.extend(_listify(row.get("radar_blocked_reasons")) or ["radar institucional bloqueou"])
    if row.get("decision_ready") is not True:
        reasons.append("decision_ready falso")
    if quality in BLOCKED_QUALITIES:
        reasons.append(f"data quality {quality}")
    if row.get("stale") is True or row.get("is_stale") is True:
        reasons.append("snapshot stale")
    if risk_critical or risk_level == "Crítico":
        reasons.append("risco critico")
    if not is_actionable_snapshot_row(row) and not reasons:
        reasons.append("ativo nao elegivel")

    return list(dict.fromkeys(reasons))


def _text_bonus(value: Any, high: float, medium: float, low: float) -> float:
    normalized = str(value or "").lower().strip()
    if not normalized:
        return 0.0
    if normalized.startswith("alta"):
        return high
    if normalized.startswith(("média", "media")):
        return medium
    return low


def _consensus_bonus(row: Dict[str, Any]) -> float:
    consensus = row.get("master_consensus") if isinstance(row.get("master_consensus"), dict) else {}
    if not consensus:
        return 0.0
    ratio = _safe_float(consensus.get("ratio"), 0.0)
    opposing = int(consensus.get("opposing_count", 0) or 0)
    if ratio >= 0.66 and opposing <= 1:
        return 10.0
    if ratio >= 0.44 and opposing <= 2:
        return 4.0
    return -12.0


def _market_pulse_bonus(row: Dict[str, Any], market_pulse: Dict[str, Any] | None) -> float:
    if not isinstance(market_pulse, dict):
        return 0.0
    direction = str(row.get("master_direction") or "").upper()
    sentiment = str(market_pulse.get("sentiment") or "").lower()
    bonus = 0.0
    if direction == "BULLISH" and sentiment == "bullish":
        bonus += 5.0
    elif direction == "BEARISH" and sentiment == "bearish":
        bonus += 5.0
    elif sentiment in {"defensive", "risk_off", "bearish"} and direction == "BULLISH":
        bonus -= 7.0
    elif sentiment in {"neutral", "mixed"}:
        bonus -= 2.0

    blocked = int(market_pulse.get("blocked_signals", 0) or 0)
    actionable = int(market_pulse.get("actionable_bullish", 0) or 0) + int(market_pulse.get("actionable_bearish", 0) or 0)
    if blocked > actionable:
        bonus -= 4.0
    return bonus


def _opportunity_score(row: Dict[str, Any], risk_level: str, market_pulse: Dict[str, Any] | None) -> float:
    master_score = _safe_float(row.get("master_score") or row.get("score"), 0.0)
    audit_score = _safe_float(row.get("audit_score"), 70.0)
    radar_score = _safe_float(row.get("radar_prioritization_score") or row.get("radar_priority_score"), 50.0)
    score = master_score * 0.42 + radar_score * 0.24 + audit_score * 0.10
    score += _text_bonus(row.get("master_conviction"), high=8.0, medium=4.0, low=-8.0)
    score += _text_bonus(row.get("master_confidence"), high=8.0, medium=4.0, low=-10.0)
    score += _consensus_bonus(row)
    score += _market_pulse_bonus(row, market_pulse)

    audit_status = audit_status_value(row) or AUDIT_APPROVED
    if audit_status == AUDIT_APPROVED:
        score += 4.0
    elif audit_status == AUDIT_CAUTION:
        score -= 8.0

    if risk_level == "Baixo":
        score += 5.0
    elif risk_level == "Moderado":
        score -= 4.0
    elif risk_level == "Alto":
        score -= 16.0

    return max(0.0, min(100.0, round(score, 2)))


def _classification(score: float) -> str:
    if score >= 86:
        return RANKING_EXCELLENT
    if score >= 74:
        return RANKING_STRONG
    if score >= 60:
        return RANKING_MODERATE
    return RANKING_WATCH


def _reason(row: Dict[str, Any], risk_level: str) -> str:
    parts: List[str] = []
    master_score = _safe_float(row.get("master_score") or row.get("score"), 0.0)
    if master_score >= 80:
        parts.append("Score Mestre elevado")
    elif master_score >= 65:
        parts.append("Score Mestre consistente")
    if audit_status_value(row) == AUDIT_APPROVED:
        parts.append("Auditor aprovado")
    elif audit_status_value(row) == AUDIT_CAUTION:
        parts.append("Auditor em atenção")

    conviction = str(row.get("master_conviction") or "").lower()
    confidence = str(row.get("master_confidence") or "").lower()
    if conviction.startswith("alta"):
        parts.append("convicção alta")
    elif conviction.startswith(("média", "media")):
        parts.append("convicção média")
    if confidence.startswith("alta"):
        parts.append("confiança alta")
    elif confidence.startswith("baixa"):
        parts.append("confiança baixa")

    if _safe_float(row.get("radar_prioritization_score") or row.get("radar_priority_score"), 0.0) >= 80:
        parts.append("Radar em prioridade alta")
    if risk_level:
        parts.append(f"risco {risk_level.lower()}")

    if not parts:
        parts.append(str(row.get("master_summary") or row.get("radar_reason") or "Contexto institucional em formação")[:140])
    return ", ".join(parts[:5]).rstrip(".") + "."


def _summary(row: Dict[str, Any], reason: str, classification: str) -> str:
    panel_summary = str(row.get("strategic_panel_summary") or "").strip()
    radar_summary = str(row.get("radar_summary") or "").strip()
    base = panel_summary or radar_summary or reason
    summary = f"{base} Ranking: {classification}."
    if len(summary) > 220:
        summary = summary[:217].rstrip(" ,.;") + "..."
    return summary


def enrich_institutional_ranking_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    risk_rows = _risk_index(ai_tools)
    metrics = {"eligible": 0, "excluded": 0, "promoted": 0, "top_ranking": 0}
    output: List[Dict[str, Any]] = []

    for row in safe_rows:
        ticker = _ticker(row)
        risk_level, risk_critical, risk_score = _risk_from_sources(row, risk_rows.get(ticker))
        blocked = _blocked_reasons(row, risk_level, risk_critical)
        item = dict(row)
        item["ranking_risk_level"] = risk_level
        item["ranking_risk_score"] = risk_score
        item["ranking_excluded_reasons"] = blocked
        item["ranking_eligible"] = not bool(blocked)

        if blocked:
            metrics["excluded"] += 1
            item["ranking_opportunity_score"] = 0.0
            item["ranking_classification"] = RANKING_NO_TRADE
            item["ranking_reason"] = "NÃO OPERAR AGORA: " + "; ".join(blocked[:4])
            item["ranking_summary"] = _summary(item, item["ranking_reason"], RANKING_NO_TRADE)
            output.append(item)
            continue

        score = _opportunity_score(item, risk_level, market_pulse)
        classification = _classification(score)
        reason = _reason(item, risk_level)
        item["ranking_opportunity_score"] = score
        item["ranking_classification"] = classification
        item["ranking_reason"] = reason
        item["ranking_summary"] = _summary(item, reason, classification)
        metrics["eligible"] += 1
        if score >= 60:
            metrics["promoted"] += 1
        else:
            item["ranking_observation_only"] = True
        output.append(item)

    top_count = len(institutional_ranking_items(output, limit=10))
    metrics["top_ranking"] = top_count
    if record_metrics:
        record_institutional_ranking_metrics(metrics)
    return output, metrics


def institutional_ranking_items(rows: Iterable[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    items = [
        dict(row)
        for row in rows or []
        if isinstance(row, dict)
        and row.get("ranking_eligible") is True
        and _safe_float(row.get("ranking_opportunity_score"), 0.0) >= 45.0
        and is_actionable_snapshot_row(row)
    ]
    items.sort(key=lambda row: _safe_float(row.get("ranking_opportunity_score"), 0.0), reverse=True)
    return items[:limit]


def ensure_institutional_ranking_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = False,
) -> List[Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if any("ranking_opportunity_score" in row for row in safe_rows):
        return safe_rows
    enriched, _metrics = enrich_institutional_ranking_rows(
        safe_rows,
        ai_tools=ai_tools,
        market_pulse=market_pulse,
        record_metrics=record_metrics,
    )
    return enriched
