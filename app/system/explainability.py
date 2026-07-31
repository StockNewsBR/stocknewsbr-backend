from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from app.cache.snapshot_cache import get_snapshot
from app.services.score_display import attach_master_score_display_contract
from app.services.snapshot_contract import resolve_decision_envelope
from app.system.system_metrics import record_explainability_metrics

BREAKDOWN_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "flow": ("flow", "smart_money"),
    "liquidity": ("liquidity",),
    "regime": ("regime",),
    "structure": ("trend", "momentum"),
    "news": ("news", "macro"),
    "risk": ("risk",),
}

BREAKDOWN_LABELS = {
    "flow": "Fluxo",
    "liquidity": "Liquidez",
    "regime": "Regime",
    "structure": "Estrutura",
    "news": "Noticias",
    "risk": "Risco",
}

NEGATIVE_TOKENS = (
    "bloque",
    "blocked",
    "stale",
    "risco",
    "fraco",
    "baixa",
    "baixo",
    "insuficiente",
    "no_trade",
    "nao operar",
    "não operar",
    "conflito",
    "perda",
    "vendedor",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric


def _normalize_score(value: Any) -> float:
    score = _safe_float(value, 0.0)
    if score < 0:
        return 0.0
    if score <= 10:
        score *= 10.0
    return max(0.0, min(score, 100.0))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _listify(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    elif value:
        items = [value]
    else:
        items = []
    return [_text(item) for item in items if _text(item)]


def _dedupe(values: Iterable[str], limit: int = 8) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _text(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _symbol(row: Dict[str, Any]) -> str:
    return _text(row.get("ticker") or row.get("symbol") or "UNKNOWN").upper() or "UNKNOWN"


def _component_reason_key(component: str) -> str:
    return f"{component}_reason"


def _component_direction(row: Dict[str, Any], component: str) -> str:
    consensus = row.get("master_consensus") if isinstance(row.get("master_consensus"), dict) else {}
    directions = consensus.get("directions") if isinstance(consensus.get("directions"), dict) else {}
    return _text(directions.get(component)).upper()


def _is_opposing(component_direction: str, master_direction: str) -> bool:
    if component_direction in {"", "NEUTRAL"} or master_direction in {"", "NEUTRAL"}:
        return False
    return component_direction != master_direction


def _risk_category(row: Dict[str, Any]) -> str:
    risk = _text(row.get("master_risk") or row.get("risk_level") or row.get("risk")).lower()
    if any(token in risk for token in ("baixo", "low")):
        return "positive"
    if any(token in risk for token in ("alto", "high", "critico", "crítico")):
        return "negative"
    if risk:
        return "neutral"
    return ""


def _component_category(row: Dict[str, Any], component: str, value: float) -> str:
    if component == "risk":
        category = _risk_category(row)
        if category:
            return category

    master_direction = _text(row.get("master_direction")).upper()
    direction = _component_direction(row, component)
    if direction and direction != "NEUTRAL":
        return "negative" if _is_opposing(direction, master_direction) else "positive"
    if value >= 60:
        return "positive"
    if value <= 35:
        return "negative"
    return "neutral"


def _looks_negative(value: str) -> bool:
    normalized = value.lower()
    return any(token in normalized for token in NEGATIVE_TOKENS)


def score_breakdown(row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    components = row.get("master_components") if isinstance(row.get("master_components"), dict) else {}
    raw_values: Dict[str, float] = {}
    for category, component_names in BREAKDOWN_CATEGORIES.items():
        values = [
            _normalize_score(components.get(component))
            for component in component_names
            if component in components
        ]
        raw_values[category] = round(sum(values) / len(values), 2) if values else 0.0

    total = sum(raw_values.values())
    breakdown: Dict[str, Dict[str, Any]] = {}
    running = 0.0
    non_zero = [key for key, value in raw_values.items() if value > 0]
    for index, (category, value) in enumerate(raw_values.items()):
        if total <= 0:
            percent = 0.0
        elif index == len(raw_values) - 1:
            percent = round(max(0.0, 100.0 - running), 2)
        else:
            percent = round((value / total) * 100.0, 2)
            running += percent
        breakdown[category] = {
            "label": BREAKDOWN_LABELS[category],
            "components": list(BREAKDOWN_CATEGORIES[category]),
            "raw_score": value,
            "contribution_pct": percent if non_zero else 0.0,
        }
    return breakdown


def why_this_score(row: Dict[str, Any]) -> Dict[str, List[str]]:
    reasoning = row.get("master_reasoning") if isinstance(row.get("master_reasoning"), dict) else {}
    components = row.get("master_components") if isinstance(row.get("master_components"), dict) else {}
    positive: List[str] = []
    negative: List[str] = []
    neutral: List[str] = []

    for component, raw_value in components.items():
        reason = _text(reasoning.get(_component_reason_key(str(component))))
        if not reason:
            continue
        category = _component_category(row, str(component), _normalize_score(raw_value))
        if category == "positive":
            positive.append(reason)
        elif category == "negative":
            negative.append(reason)
        else:
            neutral.append(reason)

    for value in _listify(row.get("conviction_factors")) + _listify(row.get("priority_factors")):
        if _looks_negative(value):
            negative.append(value)
        else:
            positive.append(value)

    for field in ("operational_blocks", "audit_blocks", "final_decision_blocks", "conviction_conflicts"):
        negative.extend(_listify(row.get(field)))

    for field in ("operational_warnings", "audit_warnings"):
        neutral.extend(_listify(row.get(field)))

    envelope = resolve_decision_envelope(row)
    negative.extend(_listify(envelope.get("blockers")))
    neutral.extend(_listify(envelope.get("warnings")))

    summary = _text(row.get("master_summary") or row.get("final_decision_reason") or row.get("strategic_panel_summary"))
    if summary and not positive and not negative and not neutral:
        neutral.append(summary)

    return {
        "positive_factors": _dedupe(positive),
        "negative_factors": _dedupe(negative),
        "neutral_factors": _dedupe(neutral),
    }


def _level_value(row: Dict[str, Any], names: Tuple[str, ...]) -> float | None:
    for name in names:
        if row.get(name) is None:
            continue
        value = _safe_float(row.get(name), 0.0)
        if value:
            return value
    levels = row.get("levels") if isinstance(row.get("levels"), dict) else {}
    for name in names:
        if levels.get(name) is None:
            continue
        value = _safe_float(levels.get(name), 0.0)
        if value:
            return value
    return None


def what_would_change_my_mind(row: Dict[str, Any]) -> List[str]:
    conditions: List[str] = []
    conditions.extend(_listify(row.get("opinion_change_conditions")))
    conditions.extend(_listify(row.get("invalidation") or row.get("invalidacao")))

    direction = _text(row.get("master_direction")).upper()
    support = _level_value(row, ("support", "support_level", "supportLevel"))
    resistance = _level_value(row, ("resistance", "resistance_level", "resistanceLevel"))
    if support is not None and direction in {"BULLISH", "BUY", "LONG"}:
        conditions.append(f"Perda do suporte {support:g}")
    if resistance is not None and direction in {"BEARISH", "SELL", "SHORT"}:
        conditions.append(f"Rompimento da resistencia {resistance:g}")

    if not conditions:
        conditions.extend(_listify(row.get("operational_blocks")))
    return _dedupe(conditions, limit=6)


def decision_explainability_score(row: Dict[str, Any], why: Dict[str, List[str]], change_mind: List[str], breakdown: Dict[str, Dict[str, Any]]) -> float:
    score = 0.0
    if any(why.values()):
        score += 25.0
    if why.get("positive_factors") and (why.get("negative_factors") or why.get("neutral_factors")):
        score += 15.0
    if change_mind:
        score += 20.0
    if any(item.get("raw_score", 0) > 0 for item in breakdown.values()):
        score += 20.0
    if _text(row.get("master_summary") or row.get("final_decision_reason") or row.get("strategic_panel_summary")):
        score += 10.0
    if _text(row.get("audit_status") or row.get("auditor_status")) and _text(row.get("operational_status")):
        score += 10.0
    return round(min(score, 100.0), 2)


def explain_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    display_row = attach_master_score_display_contract(row)
    envelope = resolve_decision_envelope(display_row)
    why = why_this_score(row)
    change_mind = what_would_change_my_mind(row)
    breakdown = score_breakdown(row)
    explainability_score = decision_explainability_score(row, why, change_mind, breakdown)
    return {
        "ticker": _symbol(row),
        "master_score": display_row.get("master_score"),
        "master_score_raw": display_row.get("master_score_raw"),
        "master_score_display": display_row.get("master_score_display"),
        "master_score_display_warning": display_row.get("master_score_display_warning"),
        "master_direction": row.get("master_direction"),
        "final_decision": row.get("final_decision"),
        "decision_status": envelope.get("decision_status"),
        "decision_envelope": envelope,
        "human_message": envelope.get("human_message"),
        "blockers": envelope.get("blockers") or [],
        "warnings": envelope.get("warnings") or [],
        "conviction_level": row.get("conviction_level"),
        "priority_level": row.get("priority_level"),
        "operational_status": row.get("operational_status"),
        "audit_status": row.get("audit_status") or row.get("auditor_status"),
        "why_this_score": why,
        "what_would_change_my_mind": change_mind,
        "score_breakdown": breakdown,
        "decision_explainability_score": explainability_score,
        "diagnostic_only": True,
    }


def calculate_explainability(snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else get_snapshot()
    signals = [row for row in safe_snapshot.get("signals", []) if isinstance(row, dict)]
    explanations = [explain_signal(row) for row in signals]
    scores = [_safe_float(item.get("decision_explainability_score"), 0.0) for item in explanations]
    average_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    metrics = {
        "status": "READY" if explanations else "EMPTY",
        "explanations": len(explanations),
        "average_decision_explainability_score": average_score,
        "high_explainability": len([score for score in scores if score >= 75]),
        "low_explainability": len([score for score in scores if score < 50]),
        "missing_change_conditions": len([item for item in explanations if not item.get("what_would_change_my_mind")]),
    }
    return {
        "status": metrics["status"],
        "source": "snapshot_cache",
        "diagnostic_only": True,
        "metrics": metrics,
        "explanations": explanations,
        "limitations": [
            "Usa somente campos ja presentes no snapshot institucional.",
            "Nao altera Score Mestre, Auditor, Ranking, Decision Engine, Paper Trading ou Performance Intelligence.",
            "Quando o snapshot nao traz fatores ou condicoes, a explicabilidade fica limitada em vez de inventar dado.",
        ],
    }


def get_explainability_status() -> Dict[str, Any]:
    payload = calculate_explainability(get_snapshot())
    record_explainability_metrics(payload.get("metrics", {}))
    return payload
