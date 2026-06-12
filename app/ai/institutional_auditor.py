from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.snapshot_contract import coerce_data_quality, snapshot_row_orientation


AUDIT_APPROVED = "APPROVED"
AUDIT_CAUTION = "CAUTION"
AUDIT_BLOCKED = "BLOCKED"
AUDIT_STATUSES = {AUDIT_APPROVED, AUDIT_CAUTION, AUDIT_BLOCKED}

_BLOCKED_QUALITIES = {"score_only", "stale", "empty", "invalid", "missing", "provider_failed"}
_BLOCKED_DECISION_STATES = {"NO_TRADE", "DO_NOT_TRADE"}
_NO_TRADE_SIGNALS = {"NO_TRADE", "DO_NOT_TRADE"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _state(value: Any) -> str:
    return str(value or "").strip().lower()


def _listify(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _positive(row: Dict[str, Any], *keys: str) -> bool:
    return any(_safe_float(row.get(key)) > 0 for key in keys)


def _row_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row)
        if ticker and ticker not in output:
            output[ticker] = row
    return output


def _tool_map(ai_tools: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not isinstance(ai_tools, dict):
        return {}
    return {
        tool: _row_index(rows)
        for tool, rows in ai_tools.items()
        if isinstance(rows, list)
    }


def _tool_row(index: Dict[str, Dict[str, Dict[str, Any]]], tool: str, ticker: str) -> Dict[str, Any]:
    return dict(index.get(tool, {}).get(ticker, {}))


def _metric(row: Dict[str, Any], key: str, default: Any = None) -> Any:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return metrics.get(key, row.get(key, default))


def _direction_from_state(tool: str, row: Dict[str, Any], base_row: Dict[str, Any]) -> str:
    if not row:
        return "neutral"
    state = _state(row.get("state") or _metric(row, f"{tool}_state"))
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("signal"),
            row.get("trade_action"),
            row.get("ai_comment"),
            state,
        )
    )
    score = _safe_float(row.get("score"), 50.0)

    bearish_terms = (
        "bear",
        "baixa",
        "downtrend",
        "selling",
        "sell",
        "short",
        "distribution",
        "vendedor",
        "strong_selling",
        "downtrend_structure",
        "institutional_distribution",
    )
    bullish_terms = (
        "bull",
        "alta",
        "uptrend",
        "buying",
        "buy",
        "long",
        "accumulation",
        "comprador",
        "strong_buying",
        "uptrend_structure",
        "institutional_accumulation",
        "institutional_buying",
    )
    risk_terms = (
        "thin_liquidity",
        "critical_risk",
        "high_risk",
        "provider_failed",
        "invalid",
        "blocked",
        "liquidity_trap",
    )

    if tool == "risk":
        risk_score = _safe_float(_metric(row, "risk_score", score))
        if "critical_risk" in text or risk_score >= 85:
            return "critical_risk"
        if "high_risk" in text or risk_score >= 70:
            return "high_risk"
        if "medium_risk" in text or risk_score >= 45:
            return "medium_risk"
        return "low_risk"

    if any(term in text for term in risk_terms):
        return "risk"
    if any(term in text for term in bearish_terms) and not any(term in text for term in bullish_terms):
        return "bearish"
    if any(term in text for term in bullish_terms) and not any(term in text for term in bearish_terms):
        return "bullish"

    orientation = snapshot_row_orientation(base_row)
    if score >= 70 and orientation in {"bullish", "bearish"}:
        return orientation
    return "neutral"


def _market_pulse_block(row: Dict[str, Any], market_pulse: Dict[str, Any] | None) -> str | None:
    if not isinstance(market_pulse, dict):
        return None
    sentiment = _state(market_pulse.get("sentiment"))
    if sentiment not in {"bullish", "bearish"}:
        return None
    orientation = snapshot_row_orientation(row)
    if orientation not in {"bullish", "bearish"} or orientation == sentiment:
        return None
    ratio_key = "bullish_ratio" if sentiment == "bullish" else "bearish_ratio"
    if _safe_float(market_pulse.get(ratio_key)) >= 0.55:
        return "Market Pulse Inconsistente"
    return None


def _conflicts(
    row: Dict[str, Any],
    tool_rows: Dict[str, Dict[str, Any]],
    directions: Dict[str, str],
) -> tuple[str, List[str], List[str]]:
    blocks: List[str] = []
    warnings: List[str] = []
    level = "none"

    trend = directions.get("trend")
    smart = directions.get("smart_money")
    liquidity = directions.get("liquidity")
    risk = directions.get("risk")
    news = directions.get("news")
    macro = directions.get("macro")
    regime = directions.get("regime")
    momentum = directions.get("momentum")

    if trend == "bullish" and smart == "bearish" and liquidity in {"bearish", "risk"}:
        blocks.append("Conflito de Tendencia")
        level = "high"
    elif trend == "bearish" and smart == "bullish" and liquidity in {"bullish", "risk"}:
        blocks.append("Conflito de Tendencia")
        level = "high"
    elif trend in {"bullish", "bearish"} and smart in {"bullish", "bearish"} and trend != smart:
        warnings.append("Conflito entre Trend IA e Smart Money IA")
        level = "medium"

    data_quality = coerce_data_quality(row)
    if momentum in {"bullish", "bearish"} and risk in {"high_risk", "critical_risk"}:
        if data_quality in {* _BLOCKED_QUALITIES, "score_only"} or risk == "critical_risk":
            blocks.append("Risk IA Bloqueando")
            level = "critical"
        else:
            warnings.append("Momentum forte com risco elevado")
            level = max(level, "medium", key=("none", "low", "medium", "high", "critical").index)

    if news == "bullish" and macro == "bearish" and regime in {"neutral", "risk"}:
        warnings.append("News positiva com macro/regime desfavoravel")
        level = max(level, "medium", key=("none", "low", "medium", "high", "critical").index)

    if _state(_metric(tool_rows.get("regime", {}), "regime_state")) in {"range", "sideways"}:
        warnings.append("Mercado Lateral")
        if level == "none":
            level = "low"

    return level, blocks, warnings


def build_institutional_audit(
    row: Dict[str, Any],
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    snapshot_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    item = dict(row or {})
    ticker = _ticker(item) or "UNKNOWN"
    snapshot_context = snapshot_context if isinstance(snapshot_context, dict) else {}
    index = _tool_map(ai_tools or {})
    tool_rows = {tool: _tool_row(index, tool, ticker) for tool in ("trend", "momentum", "smart_money", "liquidity", "regime", "risk", "news", "macro")}
    directions = {tool: _direction_from_state(tool, tool_row, item) for tool, tool_row in tool_rows.items()}

    blocks = _listify(item.get("audit_blocks"))
    warnings = _listify(item.get("audit_warnings"))
    quality = coerce_data_quality(item)

    if quality in _BLOCKED_QUALITIES:
        blocks.append("Data Quality Ruim")
    elif quality == "score_only":
        blocks.append("Data Quality Ruim")

    if snapshot_context.get("stale") is True or item.get("snapshot_valid") is False or _state(snapshot_context.get("source")) in {"empty", "exception_fallback", "snapshot_fallback"}:
        blocks.append("Snapshot Invalido")

    if not _positive(item, "price", "close", "last_price"):
        blocks.append("Preco Ausente")
    if not _positive(item, "volume", "last_volume"):
        blocks.append("Volume Ausente")
    if item.get("provider_error") or item.get("provider_failed") is True or _state(item.get("provider_status")) in {"provider_failed", "failed", "error", "timeout"}:
        blocks.append("Provider Error")

    if "decision_ready" in item and item.get("decision_ready") is False:
        blocks.append("Decision Ready False")
    if str(item.get("decision_state") or "").upper().strip() in _BLOCKED_DECISION_STATES:
        blocks.append("NO_TRADE")
    if any(
        str(item.get(key) or "").upper().strip() in _NO_TRADE_SIGNALS
        for key in ("trade_action", "signal", "action")
    ):
        blocks.append("NO_TRADE")

    risk_row = tool_rows.get("risk", {})
    risk_state = directions.get("risk")
    risk_blocks = _listify(_metric(risk_row, "risk_blocks")) + _listify(risk_row.get("no_trade_reasons"))
    if risk_state in {"critical_risk", "high_risk"} or risk_blocks:
        blocks.append("Risk IA Bloqueando")
    elif risk_state == "medium_risk":
        warnings.append("Risk IA em atencao")

    liquidity_state = _state(tool_rows.get("liquidity", {}).get("state") or _metric(tool_rows.get("liquidity", {}), "liquidity_map_state"))
    if liquidity_state in {"thin_liquidity", "low_liquidity", "illiquid"}:
        blocks.append("Baixa Liquidez")
    elif liquidity_state in {"liquidity_trap", "liquidity_monitoring"}:
        warnings.append("Liquidez Insuficiente")

    momentum_state = _state(tool_rows.get("momentum", {}).get("state") or _metric(tool_rows.get("momentum", {}), "radar_state"))
    if momentum_state in {"invalid", "invalidated", "radar_invalid"} or _state(item.get("radar_state")) in {"invalid", "invalidated", "blocked"}:
        blocks.append("Radar Invalido")
    elif momentum_state in {"momentum_watch", "momentum_quiet"}:
        warnings.append("Momentum sem Confirmacao")

    pulse_block = _market_pulse_block(item, market_pulse)
    if pulse_block:
        blocks.append(pulse_block)

    conflict_level, conflict_blocks, conflict_warnings = _conflicts(item, tool_rows, directions)
    blocks.extend(conflict_blocks)
    warnings.extend(conflict_warnings)

    macro_state = _state(tool_rows.get("macro", {}).get("state") or _metric(tool_rows.get("macro", {}), "macro_state"))
    news_state = _state(tool_rows.get("news", {}).get("state") or _metric(tool_rows.get("news", {}), "news_state"))
    if macro_state in {"macro_unavailable", "macro_news_only", "not_available"}:
        warnings.append("Macro Indisponivel")
    if news_state in {"news_not_linked", "news_empty", "news_provider_failed"}:
        warnings.append("Noticiario Limitado")

    blocks = list(dict.fromkeys(blocks))
    warnings = [warning for warning in dict.fromkeys(warnings) if warning not in blocks]

    if blocks:
        status = AUDIT_BLOCKED
    elif warnings:
        status = AUDIT_CAUTION
    else:
        status = AUDIT_APPROVED

    if conflict_level == "none" and blocks:
        conflict_level = "critical" if "Conflito de Tendencia" in blocks else "low"
    if status == AUDIT_BLOCKED and conflict_level in {"none", "low"} and any("Conflito" in block for block in blocks):
        conflict_level = "high"

    penalty = len(blocks) * 16 + len(warnings) * 6
    if "Risk IA Bloqueando" in blocks:
        penalty += 14
    if conflict_level in {"high", "critical"}:
        penalty += 18
    score = max(0.0, min(100.0, 92.0 - penalty))
    if status == AUDIT_BLOCKED:
        score = min(score, 39.0)
    elif status == AUDIT_CAUTION:
        score = min(score, 79.0)

    if status == AUDIT_APPROVED and score >= 80:
        confidence = "Alta"
    elif status == AUDIT_BLOCKED or score < 50:
        confidence = "Baixa"
    else:
        confidence = "Media"

    if status == AUDIT_APPROVED:
        reason = "Contexto institucional validado pelo Auditor."
    elif status == AUDIT_CAUTION:
        reason = "Contexto exige atencao antes de promover oportunidade."
    else:
        reason = "Oportunidade bloqueada pelo Auditor Institucional."

    summary_parts = blocks or warnings or ["Sem bloqueios institucionais relevantes"]
    summary = f"{ticker}: {status} | " + "; ".join(summary_parts[:6])

    return {
        "audit_status": status,
        "auditor_status": status,
        "audit_score": round(score, 1),
        "auditor_score": round(score, 1),
        "audit_confidence": confidence,
        "audit_reason": reason,
        "audit_blocks": blocks,
        "audit_warnings": warnings,
        "audit_summary": summary,
        "auditor_summary": summary,
        "auditor_approved": status != AUDIT_BLOCKED,
        "blocked_by_auditor": status == AUDIT_BLOCKED,
        "conflict_detected": conflict_level not in {"none", "low"} or any("Conflito" in value for value in blocks + warnings),
        "conflict_level": conflict_level,
        "audit_components": directions,
    }


def attach_audit_contract(row: Dict[str, Any], audit: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(row or {})
    audit_payload = dict(audit or {})
    output.update(
        {
            "audit_status": audit_payload.get("audit_status", AUDIT_BLOCKED),
            "auditor_status": audit_payload.get("auditor_status", audit_payload.get("audit_status", AUDIT_BLOCKED)),
            "audit_score": audit_payload.get("audit_score", 0.0),
            "auditor_score": audit_payload.get("auditor_score", audit_payload.get("audit_score", 0.0)),
            "audit_confidence": audit_payload.get("audit_confidence", "Baixa"),
            "audit_reason": audit_payload.get("audit_reason", ""),
            "audit_blocks": list(audit_payload.get("audit_blocks") or []),
            "audit_warnings": list(audit_payload.get("audit_warnings") or []),
            "audit_summary": audit_payload.get("audit_summary", ""),
            "auditor_summary": audit_payload.get("auditor_summary", audit_payload.get("audit_summary", "")),
            "auditor_approved": bool(audit_payload.get("auditor_approved") is True),
            "blocked_by_auditor": bool(audit_payload.get("blocked_by_auditor") is True),
            "conflict_detected": bool(audit_payload.get("conflict_detected") or output.get("conflict_detected")),
            "conflict_level": audit_payload.get("conflict_level", output.get("conflict_level", "none")),
            "auditor": audit_payload,
            "institutional_auditor": audit_payload,
        }
    )
    if output["blocked_by_auditor"]:
        blocked = _listify(output.get("blocked_reasons"))
        blocked.append("auditor_blocked")
        blocked.extend(output["audit_blocks"])
        output["blocked_reasons"] = list(dict.fromkeys(blocked))
        output["decision_ready"] = False
        output["can_trade"] = False
        output["decision_state"] = "DO_NOT_TRADE"
        output["operational_message"] = "NAO OPERAR AGORA"
        reasons = _listify(output.get("no_trade_reasons"))
        reasons.append("auditor bloqueou")
        output["no_trade_reasons"] = list(dict.fromkeys(reasons))
    return output


def audit_market_rows(
    rows: Iterable[Dict[str, Any]],
    ai_tools: Dict[str, Any] | None = None,
    market_pulse: Dict[str, Any] | None = None,
    snapshot_context: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    audited: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        audit = build_institutional_audit(row, ai_tools=ai_tools, market_pulse=market_pulse, snapshot_context=snapshot_context)
        audited.append(attach_audit_contract(row, audit))
    return audited


def audit_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row)
        auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
        if ticker and auditor:
            output[ticker] = dict(auditor)
    return output


def apply_audits_by_ticker(rows: Iterable[Dict[str, Any]], audits: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        audit = audits.get(_ticker(row))
        output.append(attach_audit_contract(row, audit) if audit else dict(row))
    return output


def apply_audit_to_ai_tools(ai_tools: Dict[str, Any], audits: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    output: Dict[str, List[Dict[str, Any]]] = {}
    for tool, rows in (ai_tools or {}).items():
        safe_rows = rows if isinstance(rows, list) else []
        output[tool] = apply_audits_by_ticker(safe_rows, audits)
    return output


def summarize_audits(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    statuses = {AUDIT_APPROVED: 0, AUDIT_CAUTION: 0, AUDIT_BLOCKED: 0}
    blocked: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    scores: List[float] = []
    for row in safe_rows:
        status = str(row.get("audit_status") or AUDIT_BLOCKED).upper()
        if status in statuses:
            statuses[status] += 1
        score = _safe_float(row.get("audit_score"), -1.0)
        if score >= 0:
            scores.append(score)
        if status == AUDIT_BLOCKED:
            blocked.append({"ticker": row.get("ticker") or row.get("symbol"), "blocks": row.get("audit_blocks") or []})
        elif status == AUDIT_CAUTION:
            warnings.append({"ticker": row.get("ticker") or row.get("symbol"), "warnings": row.get("audit_warnings") or []})
    return {
        "status": AUDIT_BLOCKED if statuses[AUDIT_BLOCKED] else AUDIT_CAUTION if statuses[AUDIT_CAUTION] else AUDIT_APPROVED,
        "approved": statuses[AUDIT_APPROVED],
        "caution": statuses[AUDIT_CAUTION],
        "blocked": statuses[AUDIT_BLOCKED],
        "avg_audit_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "blocked_signals": blocked[:25],
        "caution_signals": warnings[:25],
    }
