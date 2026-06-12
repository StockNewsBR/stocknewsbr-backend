from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_common import build_payload, clamp, safe_float, top_n
from app.services.snapshot_contract import coerce_data_quality


OFFICIAL_AI_TOOL_KEYS = (
    "flow",
    "liquidity",
    "trend",
    "momentum",
    "smart_money",
    "risk",
    "news",
    "macro",
    "regime",
)

INTERNAL_AI_ENGINE_KEYS = (
    "heat_map",
    "radar",
    "breakout_probability",
    "institutional_flow",
    "smart_money",
    "accumulation",
    "volatility_squeeze",
    "liquidity_sweep",
    "liquidity_map",
    "market_regime",
    "master_score",
)


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _rows_by_ticker(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row)
        if ticker and ticker not in output:
            output[ticker] = row
    return output


def _row_list(internal_outputs: Dict[str, List[Dict[str, Any]]], key: str) -> List[Dict[str, Any]]:
    value = internal_outputs.get(key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _quality_blocks(row: Dict[str, Any]) -> List[str]:
    quality = coerce_data_quality(row)
    blocks: List[str] = []
    if quality in {"score_only", "stale", "empty", "invalid", "missing", "provider_failed"}:
        blocks.append(f"data_quality:{quality}")
    if row.get("stale") is True or row.get("is_stale") is True:
        blocks.append("stale")
    if row.get("provider_error") or row.get("provider_failed") is True:
        blocks.append("provider_failed")
    return blocks


def _listify(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, tuple):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _governance_metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    blocked = (
        _listify(row.get("blocked_signals"))
        + _listify(row.get("blocked_reasons"))
        + _listify(row.get("no_trade_reasons"))
        + _quality_blocks(row)
    )
    auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
    blocked_by_auditor = bool(
        row.get("blocked_by_auditor")
        or row.get("auditor_blocked")
        or auditor.get("blocked_by_auditor")
        or str(row.get("audit_status") or auditor.get("audit_status") or "").upper() == "BLOCKED"
    )
    if blocked_by_auditor:
        blocked.append("auditor_blocked")
    return {
        "input_data_quality": coerce_data_quality(row),
        "input_decision_state": row.get("decision_state") or row.get("decision") or "UNKNOWN",
        "input_decision_ready": bool(row.get("decision_ready") is True),
        "input_can_trade": bool(row.get("can_trade") is True),
        "market_pulse": row.get("market_pulse") or row.get("market_pulse_state") or row.get("market_context"),
        "blocked_signals": sorted(set(blocked)),
        "blocked_by_auditor": blocked_by_auditor,
        "auditor_status": auditor.get("audit_status") or auditor.get("status") or row.get("audit_status") or row.get("auditor_status") or "not_available",
        "audit_score": row.get("audit_score") or auditor.get("audit_score"),
        "audit_blocks": row.get("audit_blocks") or auditor.get("audit_blocks") or [],
        "audit_warnings": row.get("audit_warnings") or auditor.get("audit_warnings") or [],
    }


def _attach_governance(payload: Dict[str, Any], row: Dict[str, Any], internal_engines: List[str]) -> Dict[str, Any]:
    metrics = payload.setdefault("metrics", {})
    if isinstance(metrics, dict):
        metrics.setdefault("governance", _governance_metrics(row))
        metrics.setdefault("internal_engines", list(internal_engines))
    payload["official_ai"] = True
    payload["internal_engines"] = list(internal_engines)
    payload["input_decision_state"] = row.get("decision_state") or row.get("decision") or "UNKNOWN"
    payload["input_decision_ready"] = bool(row.get("decision_ready") is True)
    payload["blocked_signals"] = metrics.get("governance", {}).get("blocked_signals", []) if isinstance(metrics, dict) else []
    payload["blocked_by_auditor"] = bool(metrics.get("governance", {}).get("blocked_by_auditor")) if isinstance(metrics, dict) else False
    if payload.get("input_decision_ready") is not True:
        payload["decision_ready"] = False
        payload["can_trade"] = False
        payload["operational_message"] = "NAO OPERAR AGORA"
    return payload


def _officialize_internal_row(
    row: Dict[str, Any],
    *,
    tool: str,
    internal_engines: List[str],
    metrics_extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = dict(row)
    payload["tool"] = tool
    metrics = dict(payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {})
    metrics.update(metrics_extra or {})
    payload["metrics"] = metrics
    return _attach_governance(payload, row, internal_engines)


def _compose_trend(feature_rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in feature_rows:
        trend_strength = safe_float(row.get("trend_strength"))
        momentum = safe_float(row.get("momentum"))
        rel_volume = safe_float(row.get("rel_volume"))
        above_vwap = bool(row.get("above_vwap"))
        price = safe_float(row.get("price"))
        data_quality = coerce_data_quality(row)
        directional_score = clamp(
            trend_strength * 0.68
            + abs(momentum) * 8.0
            + max(rel_volume - 1.0, 0.0) * 8.0
            + (8.0 if above_vwap else 0.0)
        )

        if price <= 0 or data_quality == "score_only":
            score = min(55.0, directional_score)
            state = "trend_pending"
            comment = f"{row['ticker']} tem tendencia pendente: sem preco real suficiente para confirmar estrutura."
            trigger = "Classificar tendencia somente com preco, VWAP/media e volume validos."
            invalidation = "Sem dados validos, a Trend IA permanece contexto e nao vira leitura acionavel."
        elif trend_strength >= 62 and momentum >= 0 and above_vwap:
            score = directional_score
            state = "uptrend_structure"
            comment = f"{row['ticker']} mostra estrutura de alta: tendencia {trend_strength:.1f}, momentum {momentum:.2f} e preco acima da VWAP."
            trigger = "Manter estrutura acima da VWAP com topos e fundos ascendentes."
            invalidation = "Perda da VWAP, quebra de fundo ou queda da forca de tendencia."
        elif trend_strength >= 62 and momentum < 0 and not above_vwap:
            score = directional_score
            state = "downtrend_structure"
            comment = f"{row['ticker']} mostra estrutura de baixa: tendencia {trend_strength:.1f}, momentum {momentum:.2f} e preco abaixo da VWAP."
            trigger = "Manter estrutura abaixo da VWAP com perda de suportes."
            invalidation = "Recuperacao da VWAP, rompimento de topo ou reducao da pressao vendedora."
        else:
            score = min(68.0, directional_score)
            state = "structure_mixed"
            comment = f"{row['ticker']} tem estrutura indefinida: tendencia {trend_strength:.1f}, momentum {momentum:.2f}, RVOL {rel_volume:.2f}."
            trigger = "Esperar direcao predominante, volume e defesa de estrutura."
            invalidation = "Lateralidade persistente ou sinais conflitantes entre preco e fluxo."

        payload = build_payload(
            row=row,
            tool="trend",
            score=score,
            state=state,
            ai_comment=comment,
            trigger=trigger,
            invalidation=invalidation,
            metrics={
                "trend_score": round(score, 1),
                "trend_strength": round(trend_strength, 1),
                "momentum": round(momentum, 2),
                "rel_volume": round(rel_volume, 2),
                "above_vwap": above_vwap,
                "decision": "Trend IA dedicated",
            },
        )
        rows.append(_attach_governance(payload, row, ["trend_features"]))
    return top_n(rows, limit=limit)


def _compose_liquidity(
    feature_rows: List[Dict[str, Any]],
    internal_outputs: Dict[str, List[Dict[str, Any]]],
    limit: int,
) -> List[Dict[str, Any]]:
    sweep_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "liquidity_sweep"))
    map_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "liquidity_map"))
    rows: List[Dict[str, Any]] = []
    for row in feature_rows:
        ticker = _ticker(row)
        sweep = sweep_by_ticker.get(ticker, {})
        liq_map = map_by_ticker.get(ticker, {})
        sweep_score = safe_float(sweep.get("score"))
        map_score = safe_float(liq_map.get("score"))
        false_breakout_risk = safe_float(row.get("false_breakout_risk"))
        score = clamp(max(sweep_score, map_score) * 0.55 + min(sweep_score, map_score) * 0.25 + false_breakout_risk * 0.20)

        map_metrics = liq_map.get("metrics") if isinstance(liq_map.get("metrics"), dict) else {}
        sweep_state = str(sweep.get("state") or "")
        map_state = str(liq_map.get("state") or "")
        upper = map_metrics.get("upper_liquidity")
        lower = map_metrics.get("lower_liquidity")

        if "liquidity_sweep_detected" in sweep_state:
            state = "liquidity_trap"
            comment = f"{row['ticker']} tem risco de armadilha de liquidez: sweep {sweep_score:.1f}, mapa {map_score:.1f}."
        elif "liquidity_hotspot" in map_state or "liquidity_zone" in map_state:
            state = "liquidity_zone"
            comment = f"{row['ticker']} tem zona de liquidez relevante entre {lower or 'n/a'} e {upper or 'n/a'}."
        elif "thin_liquidity" in map_state:
            state = "thin_liquidity"
            comment = f"{row['ticker']} tem liquidez fraca ou pouco confiavel para leitura operacional."
        else:
            state = "liquidity_monitoring"
            comment = f"{row['ticker']} segue em monitoramento de liquidez: sweep {sweep_score:.1f}, mapa {map_score:.1f}."

        payload = build_payload(
            row=row,
            tool="liquidity",
            score=score,
            state=state,
            ai_comment=comment,
            trigger="Validar zona somente com preco real, volume e reacao clara na faixa de liquidez.",
            invalidation="A leitura invalida se o preco atravessar a zona sem reacao ou se os dados de liquidez forem fracos.",
            metrics={
                "liquidity_score": round(score, 1),
                "liquidity_sweep_score": round(sweep_score, 1),
                "liquidity_sweep_state": sweep_state or None,
                "liquidity_map_score": round(map_score, 1),
                "liquidity_map_state": map_state or None,
                "upper_liquidity": upper,
                "lower_liquidity": lower,
                "false_breakout_risk": round(false_breakout_risk, 1),
            },
        )
        rows.append(_attach_governance(payload, row, ["liquidity_sweep", "liquidity_map"]))
    return top_n(rows, limit=limit)


def _compose_momentum(
    feature_rows: List[Dict[str, Any]],
    internal_outputs: Dict[str, List[Dict[str, Any]]],
    limit: int,
) -> List[Dict[str, Any]]:
    radar_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "radar"))
    breakout_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "breakout_probability"))
    heat_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "heat_map"))
    rows: List[Dict[str, Any]] = []
    for row in feature_rows:
        ticker = _ticker(row)
        radar = radar_by_ticker.get(ticker, {})
        breakout = breakout_by_ticker.get(ticker, {})
        heat = heat_by_ticker.get(ticker, {})
        radar_score = safe_float(radar.get("score"))
        breakout_score = safe_float(breakout.get("score"))
        heat_score = safe_float(heat.get("score"))
        score = clamp(radar_score * 0.45 + breakout_score * 0.30 + heat_score * 0.25)
        radar_state = str(radar.get("state") or "")
        breakout_state = str(breakout.get("state") or "")
        heat_state = str(heat.get("state") or "")

        if radar_state in {"momentum_ignition", "fast_move"} and breakout_state in {"ready_to_break", "building_pressure"}:
            state = "momentum_expansion"
            comment = f"{row['ticker']} combina aceleracao e pressao de rompimento: radar {radar_score:.1f}, breakout {breakout_score:.1f}."
        elif heat_state == "strong_selling":
            state = "bearish_momentum"
            comment = f"{row['ticker']} mostra momentum vendedor relativo: heat {heat_score:.1f}, radar {radar_score:.1f}."
        elif score >= 55:
            state = "momentum_watch"
            comment = f"{row['ticker']} tem momentum em formacao: radar {radar_score:.1f}, breakout {breakout_score:.1f}, heat {heat_score:.1f}."
        else:
            state = "momentum_quiet"
            comment = f"{row['ticker']} ainda nao tem aceleracao suficiente para momentum oficial."

        payload = build_payload(
            row=row,
            tool="momentum",
            score=score,
            state=state,
            ai_comment=comment,
            trigger="Exigir continuidade de aceleracao, volume incomum e confirmacao da estrutura.",
            invalidation="Perde leitura se velocidade cair, volume secar ou rompimento falhar.",
            metrics={
                "momentum_score": round(score, 1),
                "radar_score": round(radar_score, 1),
                "radar_state": radar_state or None,
                "breakout_probability_score": round(breakout_score, 1),
                "breakout_probability_state": breakout_state or None,
                "heat_map_score": round(heat_score, 1),
                "heat_map_state": heat_state or None,
            },
        )
        rows.append(_attach_governance(payload, row, ["radar", "breakout_probability", "heat_map"]))
    return top_n(rows, limit=limit)


def _compose_smart_money(
    feature_rows: List[Dict[str, Any]],
    internal_outputs: Dict[str, List[Dict[str, Any]]],
    limit: int,
) -> List[Dict[str, Any]]:
    flow_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "institutional_flow"))
    accumulation_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "accumulation"))
    smart_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "smart_money"))
    liquidity_by_ticker = _rows_by_ticker(_row_list(internal_outputs, "liquidity_sweep"))
    rows: List[Dict[str, Any]] = []
    for row in feature_rows:
        ticker = _ticker(row)
        flow_score = safe_float(flow_by_ticker.get(ticker, {}).get("score"))
        accumulation_score = safe_float(accumulation_by_ticker.get(ticker, {}).get("score"))
        absorption_score = safe_float(row.get("absorption_score"))
        base_smart_score = safe_float(smart_by_ticker.get(ticker, {}).get("score"))
        sweep_score = safe_float(liquidity_by_ticker.get(ticker, {}).get("score"))
        score = clamp(flow_score * 0.34 + accumulation_score * 0.28 + absorption_score * 0.26 + base_smart_score * 0.12)

        if sweep_score >= 70 and absorption_score >= 55:
            state = "possible_manipulation"
            comment = f"{row['ticker']} pode ter manipulacao/stop hunt com absorcao: sweep {sweep_score:.1f}, absorcao {absorption_score:.1f}."
        elif flow_score >= 70 and accumulation_score >= 60:
            state = "institutional_accumulation"
            comment = f"{row['ticker']} mostra atuacao institucional: flow {flow_score:.1f}, acumulacao {accumulation_score:.1f}, absorcao {absorption_score:.1f}."
        elif flow_score <= 30 and accumulation_score <= 35:
            state = "institutional_distribution"
            comment = f"{row['ticker']} sugere distribuicao ou ausencia de defesa institucional."
        elif absorption_score >= 55:
            state = "institutional_defense"
            comment = f"{row['ticker']} tem defesa institucional parcial em absorcao {absorption_score:.1f}."
        else:
            state = "smart_money_neutral"
            comment = f"{row['ticker']} nao mostra atuacao institucional dominante neste ciclo."

        payload = build_payload(
            row=row,
            tool="smart_money",
            score=score,
            state=state,
            ai_comment=comment,
            trigger="Confirmar com defesa objetiva de nivel, volume persistente e continuidade do fluxo.",
            invalidation="Perde leitura se o fluxo sumir, a zona defendida falhar ou surgir distribuicao clara.",
            metrics={
                "smart_money_score": round(score, 1),
                "flow_score": round(flow_score, 1),
                "accumulation_score": round(accumulation_score, 1),
                "absorption_score": round(absorption_score, 1),
                "base_smart_money_score": round(base_smart_score, 1),
                "liquidity_sweep_score": round(sweep_score, 1),
            },
        )
        rows.append(_attach_governance(payload, row, ["institutional_flow", "accumulation", "absorption"]))
    return top_n(rows, limit=limit)


def _risk_score(row: Dict[str, Any]) -> float:
    level = str(row.get("risk_level") or row.get("risk") or "").lower()
    base = {
        "baixo": 25.0,
        "low": 25.0,
        "medio": 55.0,
        "medium": 55.0,
        "moderado": 55.0,
        "alto": 78.0,
        "high": 78.0,
        "critico": 92.0,
        "critical": 92.0,
    }.get(level, 45.0)
    blocks = _listify(row.get("blocked_reasons")) + _listify(row.get("no_trade_reasons"))
    if row.get("decision_ready") is not True:
        base += 10.0
    if row.get("can_trade") is not True:
        base += 7.0
    base += min(15.0, len(blocks) * 3.0)
    base += len(_quality_blocks(row)) * 6.0
    if row.get("conflict_detected") is True:
        base += 10.0
    return clamp(base)


def _compose_risk(master_rows: List[Dict[str, Any]], feature_rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    feature_by_ticker = _rows_by_ticker(feature_rows)
    rows: List[Dict[str, Any]] = []
    for master in master_rows:
        ticker = _ticker(master)
        source = {**feature_by_ticker.get(ticker, {}), **master}
        risk_score = _risk_score(source)
        risk_blocks = (
            _listify(source.get("blocked_reasons"))
            + _listify(source.get("no_trade_reasons"))
            + _quality_blocks(source)
        )
        can_trade = bool(source.get("can_trade") is True and source.get("decision_ready") is True and not risk_blocks)
        if risk_score >= 85:
            state = "critical_risk"
            level = "Critico"
        elif risk_score >= 70:
            state = "high_risk"
            level = "Alto"
        elif risk_score >= 45:
            state = "medium_risk"
            level = "Medio"
        else:
            state = "low_risk"
            level = "Baixo"
        no_trade_reason = "; ".join(risk_blocks) if risk_blocks else ("Trade permitido pelo guard atual." if can_trade else "Sem liberacao operacional.")
        summary = f"Risco {level}: {no_trade_reason}"
        payload = build_payload(
            row=source,
            tool="risk",
            score=risk_score,
            state=state,
            ai_comment=summary,
            trigger="Liberar trade somente quando risco, dados e decisao operacional estiverem alinhados.",
            invalidation="Qualquer bloqueio de liquidez, dados, conflito ou auditor impede leitura acionavel.",
            metrics={
                "risk_score": round(risk_score, 1),
                "risk_summary": summary,
                "risk_blocks": sorted(set(risk_blocks)),
                "can_trade": can_trade,
                "no_trade_reason": no_trade_reason,
                "decision_ready": bool(source.get("decision_ready") is True),
                "decision_state": source.get("decision_state"),
                "trade_action": source.get("trade_action"),
                "conflict_detected": bool(source.get("conflict_detected")),
            },
        )
        payload["decision_ready"] = bool(source.get("decision_ready") is True and can_trade)
        payload["can_trade"] = can_trade
        payload["operational_message"] = "PODE OPERAR" if can_trade else "NAO OPERAR AGORA"
        payload["no_trade_reasons"] = sorted(set(risk_blocks)) if risk_blocks else ([] if can_trade else ["sem liberacao operacional"])
        payload["risk_score"] = round(risk_score, 1)
        payload["risk_summary"] = summary
        payload["risk_blocks"] = payload["no_trade_reasons"]
        payload["no_trade_reason"] = no_trade_reason
        rows.append(_attach_governance(payload, source, ["trade_decision_guard", "master_score"]))
    if not rows:
        for row in feature_rows:
            payload = build_payload(
                row=row,
                tool="risk",
                score=85.0,
                state="high_risk",
                ai_comment=f"{row['ticker']} sem decisao consolidada; risco operacional alto.",
                trigger="Aguardar Score Mestre/guard interno consolidar decisao.",
                invalidation="Sem decisao consolidada, nao ha trade acionavel.",
                metrics={
                    "risk_score": 85.0,
                    "risk_summary": "Risco alto: sem decisao consolidada.",
                    "risk_blocks": ["sem decisao consolidada"],
                    "can_trade": False,
                    "no_trade_reason": "sem decisao consolidada",
                },
            )
            rows.append(_attach_governance(payload, row, ["trade_decision_guard"]))
    return top_n(rows, limit=limit)


def _news_context(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("news_context") or row.get("news") or row.get("news_report")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list):
        return {"status": "available" if raw else "empty", "items": raw[:3], "count": len(raw)}
    return {"status": "not_linked"}


def _news_attention_score(row: Dict[str, Any]) -> float:
    change = abs(safe_float(row.get("change_pct")))
    rel_volume = safe_float(row.get("rel_volume"))
    abnormal_move = safe_float(row.get("abnormal_move_score"))
    return clamp(change * 3.0 + max(rel_volume - 1.0, 0.0) * 8.0 + abnormal_move * 0.08, 0.0, 15.0)


def _macro_sensitivity_score(row: Dict[str, Any]) -> float:
    ticker = _ticker(row)
    if ticker.endswith("USD"):
        asset_bias = 14.0
    elif ticker.isalpha() and len(ticker) <= 5:
        asset_bias = 11.0
    elif ticker.endswith("34"):
        asset_bias = 8.0
    else:
        asset_bias = 4.0
    return clamp(asset_bias + safe_float(row.get("atr_pct")) * 1.4 + abs(safe_float(row.get("market_relative_change"))) * 0.8, 0.0, 20.0)


def _compose_news(feature_rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in feature_rows:
        context = _news_context(row)
        status = str(context.get("status") or context.get("state") or "not_linked").lower()
        relevance = safe_float(context.get("relevance_score") or context.get("relevance") or context.get("ranking_score"))
        confidence = safe_float(context.get("confidence_score") or context.get("confidence"))
        impact = str(context.get("impact") or context.get("impact_label") or "unknown")
        provider_status = str(context.get("provider_status") or context.get("cache_status") or status)
        fallback_attention = _news_attention_score(row)
        score = (
            clamp(relevance * 0.60 + confidence * 0.40)
            if relevance or confidence
            else (25.0 + fallback_attention if status == "available" else 10.0 + fallback_attention)
        )
        if status in {"provider_failed", "error", "failed"}:
            state = "news_provider_failed"
            comment = f"{row['ticker']} sem leitura confiavel de noticias por falha de provider."
        elif status == "available":
            state = "news_available"
            comment = f"{row['ticker']} tem noticias acopladas: impacto {impact}, relevancia {relevance:.1f}, confianca {confidence:.1f}."
        elif status == "empty":
            state = "news_empty"
            comment = f"{row['ticker']} sem noticia relevante no ciclo atual."
        else:
            state = "news_not_linked"
            comment = f"{row['ticker']} ainda nao tem contexto de noticia ligado a este snapshot."
        payload = build_payload(
            row=row,
            tool="news",
            score=score,
            state=state,
            ai_comment=comment,
            trigger="Usar noticia apenas como contexto, nunca como gatilho isolado.",
            invalidation="Falha de provider, noticia desatualizada ou baixa relevancia removem peso operacional.",
            metrics={
                "news_state": state,
                "relevance": round(relevance, 1),
                "confidence": round(confidence, 1),
                "impact": impact,
                "provider_status": provider_status,
                "data_quality": coerce_data_quality(row),
            },
            news_context=context,
        )
        rows.append(_attach_governance(payload, row, ["news_service"]))
    return top_n(rows, limit=limit)


def _compose_macro(feature_rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in feature_rows:
        context = _news_context(row)
        labels = context.get("labels") or context.get("tags") or []
        labels = labels if isinstance(labels, list) else [labels]
        has_macro_news = any("macro" in str(label).lower() for label in labels)
        real_macro = row.get("macro_context") if isinstance(row.get("macro_context"), dict) else {}
        has_real_macro = bool(real_macro)
        if has_real_macro:
            state = "macro_context_available"
            score = clamp(safe_float(real_macro.get("score") or real_macro.get("confidence") or 55.0))
            comment = f"{row['ticker']} tem contexto macro real acoplado ao ciclo."
            context_type = "real_macro"
        elif has_macro_news:
            state = "macro_news_only"
            score = 35.0 + _macro_sensitivity_score(row) * 0.25
            comment = f"{row['ticker']} tem apenas contexto macro derivado de noticias; nao e macro quantitativo."
            context_type = "macro_from_news"
        else:
            state = "macro_unavailable"
            score = 12.0 + _macro_sensitivity_score(row)
            comment = f"{row['ticker']} sem contexto macro real neste snapshot."
            context_type = "not_available"
        payload = build_payload(
            row=row,
            tool="macro",
            score=score,
            state=state,
            ai_comment=comment,
            trigger="Usar macro como filtro de contexto quando houver fonte real ou evento macro claramente identificado.",
            invalidation="Nao tratar macro-news como macro quantitativo; sem fonte real, manter peso baixo.",
            metrics={
                "macro_state": state,
                "macro_context_type": context_type,
                "macro_real_available": has_real_macro,
                "macro_news_only": has_macro_news and not has_real_macro,
                "provider_status": real_macro.get("provider_status") or context.get("provider_status") or "not_available",
                "data_quality": coerce_data_quality(row),
            },
        )
        rows.append(_attach_governance(payload, row, ["macro_context", "news_service"]))
    return top_n(rows, limit=limit)


def build_official_ai_outputs(
    feature_rows: Iterable[Dict[str, Any]],
    internal_outputs: Dict[str, List[Dict[str, Any]]],
    *,
    limit: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    rows = [row for row in feature_rows or [] if isinstance(row, dict) and row.get("ticker")]
    flow_rows = [
        _officialize_internal_row(
            row,
            tool="flow",
            internal_engines=["institutional_flow"],
            metrics_extra={"flow_score": row.get("score"), "flow_state": row.get("state")},
        )
        for row in _row_list(internal_outputs, "institutional_flow")
    ]
    regime_rows = [
        _officialize_internal_row(
            row,
            tool="regime",
            internal_engines=["market_regime"],
            metrics_extra={"regime_score": row.get("score"), "regime_state": row.get("state")},
        )
        for row in _row_list(internal_outputs, "market_regime")
    ]
    master_rows = _row_list(internal_outputs, "master_score")
    return {
        "flow": top_n(flow_rows, limit=limit),
        "liquidity": _compose_liquidity(rows, internal_outputs, limit),
        "trend": _compose_trend(rows, limit),
        "momentum": _compose_momentum(rows, internal_outputs, limit),
        "smart_money": _compose_smart_money(rows, internal_outputs, limit),
        "risk": _compose_risk(master_rows, rows, limit),
        "news": _compose_news(rows, limit),
        "macro": _compose_macro(rows, limit),
        "regime": top_n(regime_rows, limit=limit),
    }
