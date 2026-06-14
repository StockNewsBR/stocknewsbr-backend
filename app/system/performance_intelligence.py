from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

from app.cache.signal_outcome_cache import get_signal_outcome_state
from app.system.system_metrics import record_performance_intelligence_metrics

MIN_SAMPLE_SIZE = 3
VALID_RESULTS = {"winner", "loser", "neutral"}
SCORE_BUCKETS = ("0-4", "4-5", "5-6", "6-7", "7-8", "8-10")
REGIME_BUCKETS = ("bullish", "bearish", "sideways", "volatile", "low_liquidity")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric


def _safe_symbol(record: Dict[str, Any]) -> str:
    return str(record.get("ticker") or record.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"


def _result(record: Dict[str, Any]) -> str:
    return str(record.get("simulated_result") or "").strip().lower()


def _is_evaluable(record: Dict[str, Any]) -> bool:
    return _result(record) in VALID_RESULTS


def _is_released(record: Dict[str, Any]) -> bool:
    return bool(record.get("actionability") is True)


def _is_blocked(record: Dict[str, Any]) -> bool:
    return str(record.get("status") or "").strip().lower() == "blocked"


def _score_value(record: Dict[str, Any]) -> float | None:
    raw = record.get("master_score")
    if raw is None:
        raw = record.get("score")
    score = _safe_float(raw, -1.0)
    if score < 0:
        return None
    return score / 10.0 if score > 10 else score


def score_bucket(record: Dict[str, Any]) -> str:
    score = _score_value(record)
    if score is None:
        return "unknown"
    if score <= 4:
        return "0-4"
    if score <= 5:
        return "4-5"
    if score <= 6:
        return "5-6"
    if score <= 7:
        return "6-7"
    if score <= 8:
        return "7-8"
    return "8-10"


def regime_bucket(record: Dict[str, Any]) -> str:
    raw = str(record.get("market_regime") or record.get("regime") or "unknown").strip().lower()
    normalized = raw.replace("-", "_").replace(" ", "_")
    if normalized in REGIME_BUCKETS:
        return normalized
    if any(token in normalized for token in ("bull", "alta", "uptrend", "comprador")):
        return "bullish"
    if any(token in normalized for token in ("bear", "baixa", "downtrend", "vendedor")):
        return "bearish"
    if any(token in normalized for token in ("sideways", "lateral", "range", "chop")):
        return "sideways"
    if any(token in normalized for token in ("volatile", "volatility", "squeeze")):
        return "volatile"
    if any(token in normalized for token in ("low_liquidity", "illiquid", "baixa_liquidez")):
        return "low_liquidity"
    return "unknown"


def _drawdown(returns: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return round(max_drawdown, 4)


def _empty_group() -> Dict[str, Any]:
    return {
        "sample_size": 0,
        "evaluated_executable": 0,
        "wins": 0,
        "losses": 0,
        "neutral": 0,
        "win_rate": 0.0,
        "average_payoff": 0.0,
        "average_mfe_pct": 0.0,
        "average_mae_pct": 0.0,
        "drawdown_pct": 0.0,
        "false_positive_rate": 0.0,
        "false_negative_rate": 0.0,
        "blocked_correctly": 0,
        "blocked_would_have_won": 0,
        "released_failed": 0,
        "released_won": 0,
    }


def _build_group(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluable = [record for record in records if _is_evaluable(record)]
    released = [record for record in evaluable if _is_released(record)]
    blocked = [record for record in evaluable if _is_blocked(record)]
    winners = [record for record in released if _result(record) == "winner"]
    losers = [record for record in released if _result(record) == "loser"]
    neutrals = [record for record in released if _result(record) == "neutral"]
    blocked_winners = [record for record in blocked if _result(record) == "winner"]
    blocked_correctly = [record for record in blocked if _result(record) != "winner"]
    returns = [_safe_float(record.get("outcome_return_pct"), 0.0) for record in released]
    win_returns = [_safe_float(record.get("outcome_return_pct"), 0.0) for record in winners]
    loss_returns = [abs(_safe_float(record.get("outcome_return_pct"), 0.0)) for record in losers]
    mfe_values = [_safe_float(record.get("mfe_pct"), 0.0) for record in released if record.get("mfe_pct") is not None]
    mae_values = [_safe_float(record.get("mae_pct"), 0.0) for record in released if record.get("mae_pct") is not None]

    group = _empty_group()
    group.update(
        {
            "sample_size": len(evaluable),
            "evaluated_executable": len(released),
            "wins": len(winners),
            "losses": len(losers),
            "neutral": len(neutrals),
            "win_rate": round((len(winners) / max(1, len(released))) * 100.0, 2) if released else 0.0,
            "average_payoff": round((sum(win_returns) / len(win_returns)) / max(0.0001, (sum(loss_returns) / len(loss_returns))), 4) if win_returns and loss_returns else 0.0,
            "average_mfe_pct": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else 0.0,
            "average_mae_pct": round(sum(mae_values) / len(mae_values), 4) if mae_values else 0.0,
            "drawdown_pct": _drawdown(returns),
            "false_positive_rate": round((len(losers) / max(1, len(released))) * 100.0, 2) if released else 0.0,
            "false_negative_rate": round((len(blocked_winners) / max(1, len(blocked))) * 100.0, 2) if blocked else 0.0,
            "blocked_correctly": len(blocked_correctly),
            "blocked_would_have_won": len(blocked_winners),
            "released_failed": len(losers),
            "released_won": len(winners),
        }
    )
    return group


def _group_by(records: List[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(key_fn(record) or "unknown")].append(record)
    return {key: _build_group(value) for key, value in sorted(grouped.items())}


def _ensure_score_buckets(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {bucket: groups.get(bucket, _empty_group()) for bucket in SCORE_BUCKETS}


def _ensure_regime_buckets(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {bucket: groups.get(bucket, _empty_group()) for bucket in REGIME_BUCKETS}
    for key, value in groups.items():
        if key not in result:
            result[key] = value
    return result


def _auditor_efficiency(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    blocked = [record for record in records if _is_blocked(record) and _is_evaluable(record)]
    blocked_would_have_won = [record for record in blocked if _result(record) == "winner"]
    blocked_correctly = [record for record in blocked if _result(record) != "winner"]
    denominator = len(blocked_correctly) + len(blocked_would_have_won)
    if denominator < MIN_SAMPLE_SIZE:
        return {
            "status": "insufficient_sample",
            "sample_size": denominator,
            "blocked_correctly": len(blocked_correctly),
            "blocked_would_have_won": len(blocked_would_have_won),
            "institutional_auditor_efficiency": None,
        }
    return {
        "status": "ready",
        "sample_size": denominator,
        "blocked_correctly": len(blocked_correctly),
        "blocked_would_have_won": len(blocked_would_have_won),
        "institutional_auditor_efficiency": round((len(blocked_correctly) / denominator) * 100.0, 2),
    }


def _recommendations(payload: Dict[str, Any]) -> List[str]:
    recommendations: List[str] = []
    if payload["sample_size"] < MIN_SAMPLE_SIZE:
        return [
            "Amostra insuficiente para calibracao institucional; manter regras atuais e continuar acumulando outcomes.",
        ]

    for bucket, metrics in payload["by_score_bucket"].items():
        if metrics["sample_size"] >= MIN_SAMPLE_SIZE and metrics["win_rate"] < 45:
            recommendations.append(f"Score {bucket} apresentou win rate abaixo do esperado; revisar evidencias antes de qualquer calibracao.")

    for regime, metrics in payload["by_regime"].items():
        if metrics["sample_size"] >= MIN_SAMPLE_SIZE and metrics["false_positive_rate"] >= 50:
            recommendations.append(f"Regime {regime} concentra falsos positivos; manter diagnostico separado sem alterar thresholds automaticamente.")

    for symbol, metrics in payload["by_asset"].items():
        if metrics["sample_size"] >= MIN_SAMPLE_SIZE and metrics["average_payoff"] == 0 and metrics["released_failed"] > metrics["released_won"]:
            recommendations.append(f"Ativo {symbol} tem payoff fraco na amostra atual apesar de sinais liberados; acompanhar antes de calibrar.")

    auditor = payload["auditor_efficiency"]
    if auditor.get("status") == "ready":
        recommendations.append(
            f"Auditor bloqueou corretamente {auditor['institutional_auditor_efficiency']}% dos sinais avaliaveis bloqueados."
        )

    return recommendations or ["Nenhum ajuste automatico recomendado; diagnostico permanece observacional."]


def calculate_performance_intelligence(state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    safe_state = state if isinstance(state, dict) else get_signal_outcome_state()
    records = [record for record in safe_state.get("records", []) if isinstance(record, dict)]
    evaluable_records = [record for record in records if _is_evaluable(record)]
    released = [record for record in evaluable_records if _is_released(record)]
    blocked = [record for record in evaluable_records if _is_blocked(record)]

    payload = {
        "status": "INSUFFICIENT_SAMPLE" if len(evaluable_records) < MIN_SAMPLE_SIZE else "READY",
        "sample_size": len(evaluable_records),
        "mode": "PAPER_ONLY",
        "simulation": "SIMULATED",
        "diagnostic_only": True,
        "by_asset": _group_by(evaluable_records, _safe_symbol),
        "by_regime": _ensure_regime_buckets(_group_by(evaluable_records, regime_bucket)),
        "by_score_bucket": _ensure_score_buckets(_group_by(evaluable_records, score_bucket)),
        "auditor_efficiency": _auditor_efficiency(evaluable_records),
        "released_failed": len([record for record in released if _result(record) == "loser"]),
        "released_won": len([record for record in released if _result(record) == "winner"]),
        "blocked_correctly": len([record for record in blocked if _result(record) != "winner"]),
        "blocked_would_have_won": len([record for record in blocked if _result(record) == "winner"]),
        "limitations": [
            "Usa somente registros de signal_outcome_cache gerados pela Missao 26.",
            "Nao altera thresholds, regras, Score Mestre, Auditor, Final Decision ou Paper Trading.",
            "Resultados com amostra pequena devem ser tratados como diagnostico, nao calibracao.",
        ],
    }
    payload["recommendations"] = _recommendations(payload)
    return payload


def get_performance_intelligence_status() -> Dict[str, Any]:
    payload = calculate_performance_intelligence(get_signal_outcome_state())
    record_performance_intelligence_metrics(payload)
    return payload
