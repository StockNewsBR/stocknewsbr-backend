from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, Iterable, List

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.services.snapshot_contract import (
    ACTIONABLE_SIGNALS,
    BEARISH_ACTIONS,
    BULLISH_ACTIONS,
    CANONICAL_DECISION_STATUSES,
    DECISION_BLOCKED,
    DECISION_CONFLICT,
    DECISION_ERROR,
    DECISION_INSUFFICIENT_DATA,
    DECISION_NO_TRADE,
    DECISION_READY,
    DECISION_STALE_DATA,
    QUALITY_EMPTY,
    QUALITY_INVALID,
    QUALITY_SCORE_ONLY,
    QUALITY_STALE,
)


STRATEGIC_PANEL_VERSION = "v4_mission_13"
CANONICAL_ANALYSIS_VERSION = "1.0"
ACTION_OBSERVE = "OBSERVAR"
ACTION_WAIT = "AGUARDAR"
ACTION_FORMING = "OPORTUNIDADE EM FORMAÇÃO"
ACTION_CONFIRMED = "OPORTUNIDADE CONFIRMADA"
ACTION_NO_TRADE = "NÃO OPERAR AGORA"

TRADE_NO_TRADE = "NO_TRADE"
REGIME_BULL_TREND = "BULL_TREND"
REGIME_BEAR_TREND = "BEAR_TREND"
REGIME_RANGE = "RANGE"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"
REGIME_UNKNOWN = "UNKNOWN"
CONCLUSION_OPPORTUNITY_CONFIRMED = "OPPORTUNITY_CONFIRMED"
CONCLUSION_OPPORTUNITY_FORMING = "OPPORTUNITY_FORMING"
CONCLUSION_OBSERVE = "OBSERVE"
CONCLUSION_WAIT = "WAIT"
CONCLUSION_NO_TRADE = "NO_TRADE"
CONCLUSION_CONFLICT = "CONFLICT"
VALIDATION_VALID = "VALID"
VALIDATION_NORMALIZED = "NORMALIZED"
VALIDATION_REJECTED = "REJECTED"

CANONICAL_ANALYSIS_DIRECTIONS = frozenset({"BULLISH", "BEARISH", "NEUTRAL"})
CANONICAL_ANALYSIS_DECISIONS = frozenset(CANONICAL_DECISION_STATUSES)
CANONICAL_ANALYSIS_TRADES = frozenset({*ACTIONABLE_SIGNALS, TRADE_NO_TRADE})
CANONICAL_ANALYSIS_REGIMES = frozenset(
    {REGIME_BULL_TREND, REGIME_BEAR_TREND, REGIME_RANGE, REGIME_HIGH_VOLATILITY, REGIME_UNKNOWN}
)
CANONICAL_ANALYSIS_BIASES = CANONICAL_ANALYSIS_DIRECTIONS
CANONICAL_ANALYSIS_CONCLUSIONS = frozenset(
    {
        CONCLUSION_OPPORTUNITY_CONFIRMED,
        CONCLUSION_OPPORTUNITY_FORMING,
        CONCLUSION_OBSERVE,
        CONCLUSION_WAIT,
        CONCLUSION_NO_TRADE,
        CONCLUSION_CONFLICT,
    }
)

_VALID_ACTIONS = {
    ACTION_OBSERVE,
    ACTION_WAIT,
    ACTION_FORMING,
    ACTION_CONFIRMED,
    ACTION_NO_TRADE,
}
_MASTER_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
_AUDIT_STATUSES = {AUDIT_APPROVED, AUDIT_CAUTION, AUDIT_BLOCKED}
_REASON_ORDER = (
    ("flow_reason", "flow"),
    ("smart_money_reason", "smart_money"),
    ("liquidity_reason", "liquidity"),
    ("trend_reason", "trend"),
    ("momentum_reason", "momentum"),
    ("regime_reason", "regime"),
    ("news_reason", "news"),
    ("macro_reason", "macro"),
    ("risk_reason", "risk"),
)


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
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


def _normalize_status(value: Any, fallback: str = AUDIT_APPROVED) -> str:
    status = str(value or fallback).upper().strip()
    return status if status in _AUDIT_STATUSES else fallback


def _normalize_direction(value: Any) -> str:
    direction = str(value or "NEUTRAL").upper().strip()
    return direction if direction in _MASTER_DIRECTIONS else "NEUTRAL"


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


def _risk_from_risk_ia(master_row: Dict[str, Any], risk_row: Dict[str, Any] | None) -> Dict[str, Any]:
    row = risk_row if isinstance(risk_row, dict) else {}
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("state"),
            row.get("ai_comment"),
            row.get("reason"),
            row.get("risk_summary"),
            row.get("risk_level"),
            metrics.get("risk_summary"),
            metrics.get("risk_state"),
            master_row.get("master_risk"),
        )
    )
    risk_score = _safe_float(metrics.get("risk_score") or row.get("risk_score") or row.get("score"), -1.0)

    if any(term in text for term in ("critical", "critico", "crítico", "high", "alto", "alta", "elevado", "elevada")) or risk_score >= 70:
        level = "Alto"
    elif any(term in text for term in ("medium", "medio", "médio", "moderado", "moderada")) or risk_score >= 45:
        level = "Moderado"
    elif any(term in text for term in ("low", "baixo", "baixa", "reduzido", "reduzida")) or risk_score >= 0:
        level = "Baixo"
    else:
        level = str(master_row.get("master_risk") or "Moderado").strip() or "Moderado"

    return {
        "level": level,
        "visual_level": {"Baixo": "🟢 Baixo", "Moderado": "🟡 Moderado", "Alto": "🔴 Alto"}.get(level, "🟡 Moderado"),
        "source": "risk_ia" if row else "master_score",
        "score": risk_score if risk_score >= 0 else None,
        "summary": row.get("ai_comment") or row.get("reason") or master_row.get("master_risk") or level,
    }


def _direction_label(direction: str) -> str:
    return {
        "BULLISH": "Compradora",
        "BEARISH": "Vendedora",
        "NEUTRAL": "Neutra",
    }.get(direction, "Neutra")


def _direction_visual(direction: str) -> str:
    return {
        "BULLISH": "🐂 Compradora",
        "BEARISH": "🐻 Vendedora",
        "NEUTRAL": "⚪ Neutra",
    }.get(direction, "⚪ Neutra")


def _audit_visual(status: str) -> str:
    return {
        AUDIT_APPROVED: "🟢 APROVADO",
        AUDIT_CAUTION: "🟡 ATENÇÃO",
        AUDIT_BLOCKED: "🔴 BLOQUEADO",
    }.get(status, "🟡 ATENÇÃO")


def _conviction_visual(value: Any) -> str:
    text = str(value or "Baixa").strip() or "Baixa"
    normalized = text.lower()
    if normalized.startswith("alta"):
        return "🔥 Convicção Alta"
    if normalized.startswith(("média", "media")):
        return "🟡 Convicção Média"
    return "⚪ Convicção Baixa"


def _confidence_visual(value: Any) -> str:
    text = str(value or "Baixa").strip() or "Baixa"
    normalized = text.lower()
    if normalized.startswith("alta"):
        return "🟢 Confiança Alta"
    if normalized.startswith(("média", "media")):
        return "🟡 Confiança Média"
    return "🔴 Confiança Baixa"


def _recommended_action(
    *,
    score: float,
    direction: str,
    master_status: str,
    audit_status: str,
    conviction: str,
    confidence: str,
    risk_level: str,
) -> str:
    if master_status == AUDIT_BLOCKED or audit_status == AUDIT_BLOCKED:
        return ACTION_NO_TRADE
    if risk_level == "Alto":
        return ACTION_WAIT
    if direction == "NEUTRAL":
        return ACTION_OBSERVE if master_status == AUDIT_APPROVED and risk_level == "Baixo" else ACTION_WAIT
    if master_status == AUDIT_CAUTION or audit_status == AUDIT_CAUTION:
        return ACTION_FORMING if score >= 65 and risk_level != "Alto" else ACTION_WAIT
    if score >= 80 and conviction == "Alta" and confidence in {"Alta", "Média"} and risk_level in {"Baixo", "Moderado"}:
        return ACTION_CONFIRMED
    if score >= 60:
        return ACTION_FORMING
    return ACTION_OBSERVE


def _reason_label(tool: str, text: str, direction: str, risk_level: str) -> str:
    normalized = text.lower()
    bearish = any(term in normalized for term in ("bear", "baixa", "vendedor", "selling", "sell", "short", "distribution", "distribui"))
    bullish = any(term in normalized for term in ("bull", "alta", "comprador", "buying", "buy", "accumulation", "acumul"))
    positive = (direction == "BULLISH" and bullish and not bearish) or (direction == "BEARISH" and bearish and not bullish)

    if tool == "flow":
        label = "Fluxo comprador" if bullish and not bearish else "Fluxo vendedor" if bearish and not bullish else "Fluxo neutro"
    elif tool == "smart_money":
        label = "Smart Money positivo" if positive else "Smart Money em conflito" if bullish != bearish else "Smart Money neutro"
    elif tool == "liquidity":
        label = "Liquidez adequada" if positive or "liquidez" in normalized else "Liquidez indefinida"
    elif tool == "trend":
        label = "Tendência favorável" if positive else "Tendência sem confirmação"
    elif tool == "momentum":
        label = "Momentum alinhado" if positive else "Momentum sem confirmação"
    elif tool == "regime":
        label = "Regime favorável" if positive else "Regime neutro"
    elif tool == "news":
        label = "Notícias favoráveis" if positive else "Notícias neutras"
    elif tool == "macro":
        label = "Macro favorável" if positive else "Macro neutro"
    else:
        label = f"Risco {risk_level.lower()}"

    tone = "warning" if tool == "risk" and risk_level == "Alto" else "positive" if positive or (tool == "risk" and risk_level == "Baixo") else "neutral"
    icon = "✅" if tone == "positive" else "⚠️" if tone == "warning" else "•"
    return f"{icon} {label}"


def _why_items(master_row: Dict[str, Any], direction: str, risk_level: str) -> List[Dict[str, str]]:
    reasoning = master_row.get("master_reasoning") if isinstance(master_row.get("master_reasoning"), dict) else {}
    items: List[Dict[str, str]] = []
    seen = set()
    for field, tool in _REASON_ORDER:
        text = str(reasoning.get(field) or "").strip()
        if not text:
            continue
        label = _reason_label(tool, text, direction, risk_level)
        if label in seen:
            continue
        seen.add(label)
        items.append(
            {
                "tool": tool,
                "label": label,
                "source": field,
                "reason": text[:220],
            }
        )
        if len(items) >= 6:
            break
    if not items and master_row.get("master_summary"):
        items.append({"tool": "master_score", "label": "• Score Mestre consolidado", "source": "master_summary", "reason": str(master_row.get("master_summary"))[:220]})
    return items


def _summary_from_items(master_row: Dict[str, Any], why: List[Dict[str, str]], audit_status: str, risk_level: str) -> str:
    clean = [str(item.get("label", "")).replace("✅ ", "").replace("⚠️ ", "").replace("• ", "") for item in why]
    useful = [item for item in clean if item and "sem confirmação" not in item.lower() and "neutro" not in item.lower()]
    parts = useful[:3] or clean[:2]
    audit_text = "Auditor aprovado" if audit_status == AUDIT_APPROVED else "Auditor em atenção" if audit_status == AUDIT_CAUTION else "Auditor bloqueado"
    summary = ". ".join(filter(None, [", ".join(parts), audit_text, f"Risco {risk_level.lower()}"]))
    if len(summary) > 220:
        summary = summary[:217].rstrip(" ,.;") + "..."
    if not summary:
        summary = str(master_row.get("master_summary") or "Leitura estratégica ainda sem contexto suficiente.")[:220]
    return summary


def _no_trade_reasons(master_row: Dict[str, Any]) -> List[str]:
    reasons = []
    for key in ("audit_blocks", "blocked_reasons", "no_trade_reasons", "audit_warnings", "warnings"):
        reasons.extend(_listify(master_row.get(key)))
    if not reasons and str(master_row.get("master_status") or "").upper() == AUDIT_BLOCKED:
        reasons.append("bloqueio institucional")
    return list(dict.fromkeys(reason for reason in reasons if reason))[:8]


_MIN_REWARD_RISK = 1.5
_MIN_UPSIDE_PCT = 0.003
_MIN_TICKS = 2
_TICK_SIZE = 0.01
_GEOMETRY_CONFIDENCE_CAP = 60.0


def _first_positive(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value, default=math.nan)
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    return None


def _level_prices(master_row: Dict[str, Any]) -> List[float]:
    prices: List[float] = []
    for key in ("levels", "zones", "liquidity_levels"):
        rows = master_row.get(key)
        if not isinstance(rows, (list, tuple)):
            continue
        for item in rows:
            price = _first_positive(item.get("price") if isinstance(item, dict) else item)
            if price is not None:
                prices.append(price)
    return sorted(set(prices))


def _flow_without_reading(master_row: Dict[str, Any]) -> bool:
    reasoning = master_row.get("master_reasoning") if isinstance(master_row.get("master_reasoning"), dict) else {}
    flow_text = _analysis_token(reasoning.get("flow_reason") or master_row.get("flow_state") or "")
    if "SEM_LEITURA" in flow_text or "NO_READ" in flow_text:
        return True
    # Empty flow inside an otherwise populated reasoning dict = flow has no reading.
    return not flow_text and any(str(value or "").strip() for value in reasoning.values())


def _has_other_confirmations(master_row: Dict[str, Any]) -> bool:
    reasoning = master_row.get("master_reasoning") if isinstance(master_row.get("master_reasoning"), dict) else {}
    return any(
        str(reasoning.get(field) or "").strip()
        for field, tool in _REASON_ORDER
        if tool not in {"flow", "risk"}
    )


def resolve_trade_geometry(master_row: Dict[str, Any], suggested_trade: str) -> Dict[str, Any]:
    """Fail-closed entry/target/invalidation geometry for actionable trades."""
    entry = _first_positive(master_row.get("price"), master_row.get("last_price"), master_row.get("close"))
    target = _first_positive(
        master_row.get("target"), master_row.get("alvo"), master_row.get("target_price"),
        master_row.get("resistance") if suggested_trade in BULLISH_ACTIONS else master_row.get("support"),
        master_row.get("liquidity_target"),
    )
    invalidation = _first_positive(
        master_row.get("invalidation_price"), master_row.get("invalidacao"),
        master_row.get("stop"), master_row.get("stop_loss"),
        master_row.get("support") if suggested_trade in BULLISH_ACTIONS else master_row.get("resistance"),
    )
    geometry: Dict[str, Any] = {
        "entrada_referencia": round(entry, 2) if entry is not None else None,
        "alvo": round(target, 2) if target is not None else None,
        "invalidacao": round(invalidation, 2) if invalidation is not None else None,
        "potencial_pct": None,
        "risco_pct": None,
        "reward_risk": None,
        "liquidez_alvo": None,
        "evaluated": False,
        "blocked": False,
        "block_reasons": [],
    }
    side = "BUY" if suggested_trade in BULLISH_ACTIONS else "SELL" if suggested_trade in BEARISH_ACTIONS else None
    if side is None or entry is None or target is None:
        return geometry

    geometry["evaluated"] = True
    sign = 1.0 if side == "BUY" else -1.0
    upside = (target - entry) * sign
    downside = (entry - invalidation) * sign if invalidation is not None else None
    min_upside = max(entry * _MIN_UPSIDE_PCT, _MIN_TICKS * _TICK_SIZE)
    reasons: List[str] = []
    if upside <= 0:
        reasons.append("alvo_nao_favoravel_a_entrada")
    elif upside < min_upside:
        reasons.append("potencial_insignificante")
    if downside is None or downside <= 0:
        reasons.append("invalidacao_indefinida")
        reward_risk = None
    else:
        reward_risk = upside / downside
        if reward_risk < _MIN_REWARD_RISK:
            reasons.append("reward_risk_insuficiente")
    geometry["potencial_pct"] = round(upside / entry * 100, 2)
    geometry["risco_pct"] = round(downside / entry * 100, 2) if downside is not None and downside > 0 else None
    geometry["reward_risk"] = round(reward_risk, 2) if reward_risk is not None else None
    geometry["blocked"] = bool(reasons)
    geometry["block_reasons"] = reasons

    levels = _level_prices(master_row)
    next_levels = [price for price in levels if (price > target if side == "BUY" else price < target)]
    if next_levels:
        geometry["liquidez_alvo"] = round(next_levels[0] if side == "BUY" else next_levels[-1], 2)
    return geometry


def _format_brl(value: float) -> str:
    return f"R${value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _analysis_token(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "_".join(text.upper().strip().replace("-", " ").split())


def _analysis_value(value: Any, aliases: Dict[str, str], fallback: str) -> str:
    return aliases.get(_analysis_token(value), fallback)


def validate_canonical_analysis(raw: Dict[str, Any]) -> Dict[str, Any]:
    direction = _analysis_value(raw.get("direction"), {
        "BULLISH": "BULLISH", "BUY": "BULLISH", "LONG": "BULLISH", "COMPRADORA": "BULLISH", "ALTA": "BULLISH",
        "BEARISH": "BEARISH", "SELL": "BEARISH", "SHORT": "BEARISH", "VENDEDORA": "BEARISH", "BAIXA": "BEARISH",
        "NEUTRAL": "NEUTRAL", "NEUTRA": "NEUTRAL", "FLAT": "NEUTRAL",
    }, "NEUTRAL")
    decision = _analysis_value(raw.get("decision"), {
        "READY": DECISION_READY, "PRONTA": DECISION_READY, "PRONTO": DECISION_READY,
        "BLOCKED": DECISION_BLOCKED, "BLOQUEADA": DECISION_BLOCKED, "BLOQUEADO": DECISION_BLOCKED,
        "NO_TRADE": DECISION_NO_TRADE, "DO_NOT_TRADE": DECISION_NO_TRADE, "AGUARDAR": DECISION_NO_TRADE,
        "STALE_DATA": DECISION_STALE_DATA, "INSUFFICIENT_DATA": DECISION_INSUFFICIENT_DATA,
        "CONFLICT": DECISION_CONFLICT, "ERROR": DECISION_ERROR,
    }, DECISION_NO_TRADE)
    trade = _analysis_value(raw.get("suggested_trade"), {
        "BUY": "BUY", "COMPRA": "BUY", "LONG": "BUY",
        "SELL": "SELL", "VENDA": "SELL", "SHORT": "SHORT", "VENDA_A_DESCOBERTO": "SHORT",
        "COVER": "COVER", "COBRIR": "COVER", "NO_TRADE": TRADE_NO_TRADE,
        "NO_DECISION": TRADE_NO_TRADE, "NONE": TRADE_NO_TRADE, "WAIT": TRADE_NO_TRADE,
    }, TRADE_NO_TRADE)
    regime = _analysis_value(raw.get("regime"), {
        "BULL_TREND": REGIME_BULL_TREND, "BULLISH": REGIME_BULL_TREND, "TENDENCIA_DE_ALTA": REGIME_BULL_TREND,
        "BEAR_TREND": REGIME_BEAR_TREND, "BEARISH": REGIME_BEAR_TREND, "TENDENCIA_DE_BAIXA": REGIME_BEAR_TREND,
        "RANGE": REGIME_RANGE, "LATERAL": REGIME_RANGE, "NEUTRAL": REGIME_RANGE,
        "HIGH_VOLATILITY": REGIME_HIGH_VOLATILITY, "ALTA_VOLATILIDADE": REGIME_HIGH_VOLATILITY,
    }, REGIME_UNKNOWN)
    bias = _analysis_value(raw.get("bias"), {
        "BULLISH": "BULLISH", "BUY": "BULLISH", "LONG": "BULLISH", "COMPRADORA": "BULLISH", "ALTA": "BULLISH",
        "BEARISH": "BEARISH", "SELL": "BEARISH", "SHORT": "BEARISH", "VENDEDORA": "BEARISH", "BAIXA": "BEARISH",
        "NEUTRAL": "NEUTRAL", "NEUTRA": "NEUTRAL", "FLAT": "NEUTRAL",
    }, direction)

    reasons: List[str] = []
    if trade in BULLISH_ACTIONS and direction != "BULLISH":
        reasons.append("direction_vs_suggested_trade")
    if trade in BEARISH_ACTIONS and direction != "BEARISH":
        reasons.append("direction_vs_suggested_trade")
    if regime == REGIME_BULL_TREND and bias == "BEARISH" or regime == REGIME_BEAR_TREND and bias == "BULLISH":
        reasons.append("regime_vs_bias")
    if bias != "NEUTRAL" and direction != "NEUTRAL" and bias != direction:
        reasons.append("direction_vs_bias")

    if reasons:
        decision = DECISION_CONFLICT
        trade = TRADE_NO_TRADE
        conclusion = CONCLUSION_CONFLICT
        validation_status = VALIDATION_REJECTED
    elif decision == DECISION_READY and trade in ACTIONABLE_SIGNALS:
        conclusion = CONCLUSION_OPPORTUNITY_CONFIRMED
        validation_status = VALIDATION_NORMALIZED
    elif decision == DECISION_BLOCKED:
        conclusion = CONCLUSION_NO_TRADE
        validation_status = VALIDATION_NORMALIZED
    elif decision == DECISION_NO_TRADE and direction == "NEUTRAL":
        conclusion = CONCLUSION_OBSERVE
        validation_status = VALIDATION_NORMALIZED
    elif decision in {DECISION_NO_TRADE, DECISION_STALE_DATA, DECISION_INSUFFICIENT_DATA, DECISION_ERROR}:
        conclusion = CONCLUSION_NO_TRADE
        validation_status = VALIDATION_NORMALIZED
    else:
        conclusion = CONCLUSION_WAIT
        validation_status = VALIDATION_NORMALIZED

    return {
        "version": CANONICAL_ANALYSIS_VERSION,
        "direction": direction,
        "decision": decision,
        "suggested_trade": trade,
        "regime": regime,
        "bias": bias,
        "conclusion": conclusion,
        "validation_status": validation_status,
        "validation_reasons": list(dict.fromkeys(reasons)),
    }


def build_strategic_panel(master_row: Dict[str, Any], risk_row: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ticker = _ticker(master_row) or "UNKNOWN"
    score = round(_safe_float(master_row.get("master_score") or master_row.get("score")), 1)
    direction = _normalize_direction(master_row.get("master_direction"))
    master_status = _normalize_status(master_row.get("master_status"))
    audit_status = _normalize_status(master_row.get("audit_status") or master_row.get("auditor_status"), fallback=master_status)
    conviction = str(master_row.get("master_conviction") or "Baixa").strip() or "Baixa"
    confidence = str(master_row.get("master_confidence") or "Baixa").strip() or "Baixa"
    audit_summary = str(master_row.get("audit_summary") or master_row.get("auditor_summary") or master_row.get("master_summary") or "").strip()
    risk = _risk_from_risk_ia(master_row, risk_row)
    risk_level = str(risk.get("level") or "Moderado")
    decision = master_row.get("decision_status") or (DECISION_READY if master_row.get("decision_ready") else DECISION_NO_TRADE)
    suggested_trade = master_row.get("trade_action") or master_row.get("signal") or TRADE_NO_TRADE
    if master_status == AUDIT_BLOCKED or audit_status == AUDIT_BLOCKED:
        decision = DECISION_BLOCKED
        suggested_trade = TRADE_NO_TRADE
    canonical_analysis = validate_canonical_analysis({
        "direction": direction,
        "decision": decision,
        "suggested_trade": suggested_trade,
        "regime": master_row.get("market_regime_state") or master_row.get("regime"),
        "bias": master_row.get("bias") or direction,
    })
    action = _recommended_action(
        score=score,
        direction=direction,
        master_status=master_status,
        audit_status=audit_status,
        conviction=conviction,
        confidence=confidence,
        risk_level=risk_level,
    )
    if action not in _VALID_ACTIONS:
        action = ACTION_WAIT

    if canonical_analysis["decision"] in {DECISION_BLOCKED, DECISION_CONFLICT, DECISION_STALE_DATA, DECISION_INSUFFICIENT_DATA, DECISION_ERROR} or (
        canonical_analysis["decision"] == DECISION_NO_TRADE and canonical_analysis["direction"] != "NEUTRAL"
    ):
        action = ACTION_NO_TRADE

    # Mission 68: fail-closed entry/target geometry — single gate for every consumer.
    geometry = resolve_trade_geometry(master_row, canonical_analysis["suggested_trade"])
    flow_without_reading = _flow_without_reading(master_row)
    flow_blocks = flow_without_reading and not _has_other_confirmations(master_row)
    geometry_blocks = geometry["evaluated"] and geometry["blocked"]
    action_detail = None
    if canonical_analysis["suggested_trade"] in ACTIONABLE_SIGNALS and (geometry_blocks or flow_blocks):
        reasons = list(geometry["block_reasons"])
        if flow_blocks:
            reasons.append("fluxo_institucional_sem_leitura")
        side_is_buy = canonical_analysis["suggested_trade"] in BULLISH_ACTIONS
        canonical_analysis["suggested_trade"] = TRADE_NO_TRADE
        canonical_analysis["decision"] = DECISION_NO_TRADE
        canonical_analysis["conclusion"] = CONCLUSION_WAIT
        canonical_analysis["validation_reasons"] = list(
            dict.fromkeys([*canonical_analysis["validation_reasons"], *reasons])
        )
        action = ACTION_WAIT
        if geometry["alvo"] is not None:
            action_detail = (
                f"AGUARDAR ROMPIMENTO DE {_format_brl(geometry['alvo'])} COM CONFIRMAÇÃO"
                if side_is_buy
                else f"AGUARDAR PERDA DE {_format_brl(geometry['alvo'])} COM CONFIRMAÇÃO"
            )

    capped_confidence = geometry_blocks or flow_without_reading or (
        geometry["evaluated"] and (geometry["reward_risk"] is None or geometry["reward_risk"] < _MIN_REWARD_RISK)
    )
    confidence_pct = max(0.0, min(score, 100.0))
    if capped_confidence:
        confidence_pct = min(confidence_pct, _GEOMETRY_CONFIDENCE_CAP)
        if confidence == "Alta":
            confidence = "Média"

    no_trade_now = action == ACTION_NO_TRADE
    why = _why_items(master_row, direction, risk_level)
    summary = _summary_from_items(master_row, why, audit_status, risk_level)
    no_trade_reasons = _no_trade_reasons(master_row) if no_trade_now else []

    panel = {
        "ticker": ticker,
        "symbol": ticker,
        "strategic_panel_version": STRATEGIC_PANEL_VERSION,
        "canonical_analysis": canonical_analysis,
        "master_score_block": {
            "title": "🎯 Score Mestre",
            "score": score,
            "direction": direction,
            "direction_label": _direction_label(direction),
            "direction_visual": _direction_visual(direction),
            "conviction": conviction,
            "conviction_visual": _conviction_visual(conviction),
            "confidence": confidence,
            "confidence_visual": _confidence_visual(confidence),
        },
        "auditor_block": {
            "title": "🛡️ Auditor Institucional",
            "status": audit_status,
            "visual_status": _audit_visual(audit_status),
            "summary": audit_summary,
            "blocks": _listify(master_row.get("audit_blocks")),
            "warnings": _listify(master_row.get("audit_warnings")),
        },
        "risk_block": {
            "title": "⚠️ Risco",
            **risk,
        },
        "probable_direction_block": {
            "title": "📈 Direção Provável",
            "direction": direction,
            "label": _direction_label(direction) + (" (aguardando confirmação)" if action_detail else ""),
            "visual_label": _direction_visual(direction),
        },
        "recommended_action_block": {
            "title": "🚨 Ação Recomendada",
            "action": action,
            "action_detail": action_detail,
            "no_trade_now": no_trade_now,
            "reasons": no_trade_reasons,
        },
        "recommended_action": action,
        "recommended_action_detail": action_detail,
        "entrada_referencia": geometry["entrada_referencia"],
        "alvo": geometry["alvo"],
        "invalidacao": geometry["invalidacao"],
        "potencial_pct": geometry["potencial_pct"],
        "risco_pct": geometry["risco_pct"],
        "reward_risk": geometry["reward_risk"],
        "liquidez_alvo": geometry["liquidez_alvo"],
        "confidence_pct": round(confidence_pct, 1),
        "strategic_panel_summary": summary,
        "why": why,
        "opinion_change_conditions": _listify(master_row.get("opinion_change_conditions")),
        "no_trade_now": no_trade_now,
        "no_trade_reasons": no_trade_reasons,
        "source_contracts": ["master_score", "institutional_auditor", "risk_ia"],
    }
    panel["blocks"] = [
        panel["master_score_block"],
        panel["auditor_block"],
        panel["risk_block"],
        panel["probable_direction_block"],
        panel["recommended_action_block"],
    ]
    return panel


def strategic_panel_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row)
        if ticker and ticker not in output:
            output[ticker] = dict(row)
    return output


def apply_strategic_panels_by_ticker(rows: Iterable[Dict[str, Any]], strategic_panels: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index = strategic_panel_index(strategic_panels)
    output: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        panel = index.get(_ticker(item))
        if panel:
            item["strategic_panel"] = panel
            item["strategic_panel_summary"] = panel.get("strategic_panel_summary")
            item["recommended_action"] = panel.get("recommended_action")
        output.append(item)
    return output


def build_strategic_panels(
    master_rows: Iterable[Dict[str, Any]],
    *,
    ai_tools: Dict[str, Any] | None = None,
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    risk_rows = _risk_index(ai_tools)
    panels = [
        build_strategic_panel(row, risk_rows.get(_ticker(row)))
        for row in master_rows or []
        if isinstance(row, dict)
    ]
    return panels[:limit] if limit is not None else panels
