from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.operational_rules import OPERATIONAL_BLOCKED
from app.services.snapshot_contract import audit_status_value, master_status_value
from app.system.system_metrics import record_institutional_conviction_metrics


CONVICTION_VERY_HIGH = "🔥 MUITO ALTA"
CONVICTION_HIGH = "🟢 ALTA"
CONVICTION_MODERATE = "🟡 MODERADA"
CONVICTION_LOW = "🔴 BAIXA"

_BULLISH_TERMS = ("bull", "buy", "comprador", "alta", "acumul", "positivo", "uptrend", "favoravel", "favorável")
_BEARISH_TERMS = ("bear", "sell", "short", "vendedor", "baixa", "distrib", "negativo", "downtrend", "desfavoravel", "desfavorável")


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


def _tool_index(ai_tools: Dict[str, Any] | None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not isinstance(ai_tools, dict):
        return {}
    output: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for tool, rows in ai_tools.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = _ticker(row)
            if not ticker:
                continue
            output.setdefault(ticker, {})
            output[ticker].setdefault(str(tool), row)
    return output


def _direction(row: Dict[str, Any]) -> str:
    value = str(row.get("master_direction") or "").upper().strip()
    if value in {"BULLISH", "BEARISH", "NEUTRAL"}:
        return value
    signal = str(row.get("trade_action") or row.get("signal") or "").upper().strip()
    if signal in {"BUY", "COVER", "WATCH_BUY"}:
        return "BULLISH"
    if signal in {"SELL", "SHORT", "WATCH_SHORT"}:
        return "BEARISH"
    return "NEUTRAL"


def _text_direction(*values: Any) -> str:
    text = " ".join(str(value or "").lower() for value in values)
    bullish = any(term in text for term in _BULLISH_TERMS)
    bearish = any(term in text for term in _BEARISH_TERMS)
    if bullish and not bearish:
        return "BULLISH"
    if bearish and not bullish:
        return "BEARISH"
    return "NEUTRAL"


def _tool_direction(row: Dict[str, Any]) -> str:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return _text_direction(row.get("state"), row.get("signal"), row.get("ai_comment"), row.get("reason"), " ".join(str(value) for value in metrics.values()))


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


def _consensus(row: Dict[str, Any]) -> Tuple[float, int]:
    consensus = row.get("master_consensus") if isinstance(row.get("master_consensus"), dict) else {}
    return _safe_float(consensus.get("ratio"), 0.0), int(consensus.get("opposing_count", 0) or 0)


def _label(score: float) -> str:
    if score >= 86:
        return CONVICTION_VERY_HIGH
    if score >= 72:
        return CONVICTION_HIGH
    if score >= 52:
        return CONVICTION_MODERATE
    return CONVICTION_LOW


def _alignment_score(
    row: Dict[str, Any],
    risk_level: str,
    market_pulse: Dict[str, Any] | None,
) -> Tuple[float, List[str], List[str]]:
    factors: List[str] = []
    conflicts: List[str] = []
    score = 45.0

    audit_status = audit_status_value(row)
    if audit_status == AUDIT_APPROVED:
        score += 10.0
        factors.append("auditor aprovado")
    elif audit_status == AUDIT_CAUTION:
        score -= 10.0
        conflicts.append("Auditor CAUTION")
    elif audit_status == AUDIT_BLOCKED:
        score -= 18.0
        conflicts.append("Auditor BLOCKED")

    ratio, opposing = _consensus(row)
    if ratio >= 0.66 and opposing <= 1:
        score += 15.0
        factors.append("consenso institucional alto")
    elif ratio < 0.44 or opposing >= 3:
        score -= 16.0
        conflicts.append("consenso institucional baixo")

    confidence = str(row.get("master_confidence") or "").lower()
    if confidence.startswith("alta"):
        score += 10.0
        factors.append("confiança alta")
    elif confidence.startswith("baixa"):
        score -= 12.0
        conflicts.append("confiança baixa")

    if str(row.get("radar_level") or row.get("radar_priority") or "").lower().find("prioridade alta") >= 0:
        score += 9.0
        factors.append("Radar prioridade alta")
    elif str(row.get("radar_level") or "").lower().find("observ") >= 0:
        score -= 5.0
        conflicts.append("Radar em observação")

    ranking = str(row.get("ranking_classification") or "").lower()
    if "excelente" in ranking:
        score += 9.0
        factors.append("Ranking excelente")
    elif "forte" in ranking:
        score += 6.0
        factors.append("Ranking forte")
    elif "observ" in ranking:
        score -= 5.0
        conflicts.append("Ranking em observação")

    historical_label = str(row.get("historical_confidence_label") or "").lower()
    historical_score = _safe_float(row.get("historical_confidence_score"), 0.0)
    if "alta" in historical_label or historical_score >= 75:
        score += 8.0
        factors.append("histórico favorável")
    elif "baixa" in historical_label or (historical_score > 0 and historical_score < 45):
        score -= 10.0
        conflicts.append("histórico fraco")
    elif "amostra insuficiente" in historical_label or int(row.get("historical_sample_size", 0) or 0) < 8:
        score -= 5.0
        conflicts.append("amostra histórica insuficiente")

    if str(row.get("operational_status") or "").upper() == "READY":
        score += 6.0
        factors.append("regras operacionais prontas")
    elif str(row.get("operational_status") or "").upper() == OPERATIONAL_BLOCKED:
        conflicts.append("operação bloqueada pelas regras operacionais")

    if risk_level == "Baixo":
        score += 8.0
        factors.append("risco baixo")
    elif risk_level == "Alto":
        score -= 12.0
        conflicts.append("risco elevado")
    elif risk_level == "Crítico":
        score -= 20.0
        conflicts.append("risco crítico")

    direction = _direction(row)
    sentiment = str((market_pulse or {}).get("sentiment") or "").lower() if isinstance(market_pulse, dict) else ""
    if sentiment in {"neutral", "mixed", "neutro", "range"}:
        score -= 7.0
        conflicts.append("Market Pulse neutro")
    elif direction == "BULLISH" and sentiment == "bullish":
        score += 5.0
        factors.append("Market Pulse alinhado")
    elif direction == "BEARISH" and sentiment == "bearish":
        score += 5.0
        factors.append("Market Pulse alinhado")
    elif direction in {"BULLISH", "BEARISH"} and sentiment in {"bullish", "bearish"}:
        score -= 8.0
        conflicts.append("Market Pulse divergente")

    return score, factors, conflicts


def _tool_conflicts(row: Dict[str, Any], ticker_tools: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    direction = _direction(row)
    factors: List[str] = []
    conflicts: List[str] = []
    for tool in ("flow", "liquidity", "trend", "momentum", "smart_money", "news", "macro", "regime"):
        tool_row = ticker_tools.get(tool)
        if not isinstance(tool_row, dict):
            continue
        tool_direction = _tool_direction(tool_row)
        label = tool.replace("_", " ").title()
        if tool_direction in {"BULLISH", "BEARISH"} and direction in {"BULLISH", "BEARISH"}:
            if tool_direction == direction:
                factors.append(f"{label} alinhado")
            else:
                readable = "bullish" if tool_direction == "BULLISH" else "bearish"
                conflicts.append(f"{label} {readable}")
    return factors, conflicts


def _summary(level: str, factors: List[str], conflicts: List[str]) -> str:
    if conflicts:
        base = ", ".join(factors[:3]) if factors else "Evidência institucional parcial"
        conflict = ", ".join(conflicts[:3])
        return f"{level}: {base}. Conflitos: {conflict}."
    base = ", ".join(factors[:4]) if factors else "Evidência institucional ainda em formação"
    return f"{level}: {base}."


def enrich_institutional_conviction_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    tools_by_ticker = _tool_index(ai_tools)
    output: List[Dict[str, Any]] = []

    for row in safe_rows:
        item = dict(row)
        ticker = _ticker(item)
        risk_level = _risk_level(item, tools_by_ticker.get(ticker, {}).get("risk"))
        score, factors, conflicts = _alignment_score(item, risk_level, market_pulse)
        tool_factors, tool_conflicts = _tool_conflicts(item, tools_by_ticker.get(ticker, {}))
        factors.extend(tool_factors)
        conflicts.extend(tool_conflicts)
        score += min(10.0, len(tool_factors) * 2.0)
        score -= min(22.0, len(tool_conflicts) * 5.0)
        if master_status_value(item) == AUDIT_BLOCKED:
            conflicts.append("Score Mestre BLOCKED")
        score = max(0.0, min(100.0, round(score, 2)))
        level = _label(score)
        item["conviction_score"] = score
        item["conviction_level"] = level
        item["conviction_factors"] = list(dict.fromkeys(factors))[:10]
        item["conviction_conflicts"] = list(dict.fromkeys(conflicts))[:10]
        item["conviction_summary"] = _summary(level, item["conviction_factors"], item["conviction_conflicts"])
        output.append(item)

    metrics = _metrics(output)
    if record_metrics:
        record_institutional_conviction_metrics(metrics)
    return output, metrics


def apply_conviction_by_ticker(rows: Iterable[Dict[str, Any]], conviction_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index = {
        _ticker(row): row
        for row in conviction_rows or []
        if isinstance(row, dict) and _ticker(row)
    }
    fields = ("conviction_score", "conviction_level", "conviction_summary", "conviction_factors", "conviction_conflicts")
    output: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        conviction = index.get(_ticker(item))
        if conviction:
            for field in fields:
                item[field] = conviction.get(field)
        output.append(item)
    return output


def ensure_institutional_conviction_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    record_metrics: bool = False,
) -> List[Dict[str, Any]]:
    safe_rows = [dict(row) for row in rows or [] if isinstance(row, dict)]
    if any("conviction_score" in row for row in safe_rows):
        return safe_rows
    enriched, _metrics = enrich_institutional_conviction_rows(
        safe_rows,
        ai_tools=ai_tools,
        market_pulse=market_pulse,
        record_metrics=record_metrics,
    )
    return enriched


def conviction_items(rows: Iterable[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    items = [dict(row) for row in rows or [] if isinstance(row, dict) and "conviction_score" in row]
    items.sort(key=lambda row: _safe_float(row.get("conviction_score"), 0.0), reverse=True)
    return items[:limit]


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    scores = [_safe_float(row.get("conviction_score"), 0.0) for row in safe_rows]
    conflicts = sum(len(_listify(row.get("conviction_conflicts"))) for row in safe_rows)
    levels = Counter(str(row.get("conviction_level") or "") for row in safe_rows)
    return {
        "signals": len(safe_rows),
        "average_conviction": round(sum(scores) / max(1, len(scores)), 2),
        "high_conviction": int(levels.get(CONVICTION_VERY_HIGH, 0) + levels.get(CONVICTION_HIGH, 0)),
        "low_conviction": int(levels.get(CONVICTION_LOW, 0)),
        "conflicts_detected": conflicts,
    }
