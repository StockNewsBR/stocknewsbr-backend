from __future__ import annotations

import csv
import json
import threading
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

from app.ai.ai_common import signal_from_score
from app.ai.feature_hub import build_ai_tool_payload
from app.cache.snapshot_cache import get_snapshot

AI_TAB_AUDIT_DIR = Path("runtime/ai_tabs")
AI_TAB_AUDIT_EXPORT_DIR = AI_TAB_AUDIT_DIR / "exports"
AI_TAB_AUDIT_DATASET_DIR = AI_TAB_AUDIT_DIR / "datasets"
AI_TAB_AUDIT_HISTORY_DIR = AI_TAB_AUDIT_DIR / "history"
AI_TAB_AUDIT_HISTORY_LIMIT = 48
EXPECTED_TOOLS = [
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
]
REQUIRED_FIELDS = [
    "ticker",
    "detected_at",
    "score",
    "signal",
    "state",
    "ai_comment",
    "trigger",
    "invalidation",
    "invalidacao",
    "metrics",
    "reason",
    "news_context",
]
BENCHMARK_WEIGHTS = {
    "consistency": 0.30,
    "product_quality": 0.22,
    "confidence": 0.18,
    "explanation_quality": 0.15,
    "coverage": 0.10,
    "state_diversity": 0.05,
}
SCENARIO_EXPECTED_ROWS = {
    "quiet": 1,
    "balanced": 2,
    "active": 4,
    "eventful": 6,
}
QUALITY_DIMENSIONS = [
    "coverage",
    "consistency",
    "confidence",
    "state_diversity",
    "explanation_quality",
    "product_quality",
]
GENERIC_EXPLANATION_HINTS = {
    "acompanhar",
    "monitorar",
    "sem leitura",
    "n/a",
    "na",
    "aguarde",
    "watch",
    "monitoring",
    "setup neutro",
}
EXPLANATION_MIN_LENGTH = 18
BDR_SUFFIXES = ("34",)
B3_SUFFIXES = ("3", "4", "5", "6", "11")
APPROVAL_RULES = {
    "approved": {
        "consistency_score": 80,
        "avg_confidence": 55,
        "benchmark_score": 80,
        "product_quality": 75,
    },
    "watch": {
        "consistency_score": 65,
        "avg_confidence": 40,
        "benchmark_score": 62,
    },
}

_lock = threading.RLock()
_last_report: Dict[str, Any] = {}
_history: List[Dict[str, Any]] = []


def _ensure_report_dir() -> None:
    AI_TAB_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AI_TAB_AUDIT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    AI_TAB_AUDIT_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    AI_TAB_AUDIT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _safe_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_ticker(value: Any) -> str:
    return str(value or "").upper().strip()


def _asset_class_for_ticker(ticker: str) -> str:
    normalized = _normalize_ticker(ticker)
    if not normalized:
        return "unknown"
    if "-USD" in normalized or normalized.endswith("USDT") or normalized.endswith("BTC"):
        return "crypto"
    if normalized.endswith(".SA"):
        base = normalized[:-3]
        if base.endswith(BDR_SUFFIXES):
            return "bdr"
        if base.endswith(B3_SUFFIXES):
            return "b3"
    if normalized.endswith(BDR_SUFFIXES):
        return "bdr"
    if normalized.endswith(B3_SUFFIXES):
        return "b3"
    if normalized.isalpha() and len(normalized) <= 6:
        return "usa"
    return "other"


def _dominant_asset_class(rows: Iterable[Dict[str, Any]]) -> str:
    counts = Counter(_asset_class_for_ticker(row.get("ticker") or row.get("symbol")) for row in rows)
    counts.pop("unknown", None)
    if not counts:
        return "unknown"
    return counts.most_common(1)[0][0]


def _infer_period(snapshot: Dict[str, Any]) -> str:
    for key in ("period", "timeframe", "window", "interval"):
        value = str(snapshot.get(key) or "").strip().lower()
        if value:
            return value
    return "current"


def _infer_scenario(snapshot: Dict[str, Any], rows: Iterable[Dict[str, Any]]) -> str:
    snapshot_rows = _safe_rows(snapshot.get("signals"))
    total_signals = len(snapshot_rows)
    if snapshot.get("stale"):
        return "stale"
    if total_signals <= 3:
        return "quiet"
    if total_signals <= 8:
        return "balanced"
    if total_signals <= 18:
        return "active"
    return "eventful"


def _expected_rows_for_context(tool: str, asset_class: str, scenario: str) -> int:
    base = SCENARIO_EXPECTED_ROWS.get(scenario, 2)
    tool_weight = {
        "heat_map": 1,
        "radar": 2,
        "breakout_probability": 2,
        "institutional_flow": 2,
        "smart_money": 2,
        "accumulation": 2,
        "volatility_squeeze": 2,
        "liquidity_sweep": 2,
        "liquidity_map": 2,
        "market_regime": 1,
        "master_score": 1,
    }.get(tool, 1)
    asset_adjustment = {
        "crypto": 0,
        "b3": 0,
        "bdr": 1,
        "usa": 1,
        "other": 0,
        "unknown": 0,
    }.get(asset_class, 0)
    return max(1, min(8, base * tool_weight + asset_adjustment))


def _coverage_score(actual_rows: int, expected_rows: int) -> float:
    if expected_rows <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (actual_rows / expected_rows) * 100.0)), 2)


def _score_state_diversity(
    state_distribution: Dict[str, int],
    rows_count: int,
    expected_unique_states: int,
) -> float:
    if rows_count <= 0 or not state_distribution:
        return 0.0
    if rows_count <= 2:
        return 100.0 if len(state_distribution) <= max(1, expected_unique_states) else 75.0
    dominant_ratio = max(state_distribution.values()) / max(1, rows_count)
    unique_ratio = len(state_distribution) / max(1, expected_unique_states)
    diversity = (1.0 - dominant_ratio) * 55.0 + min(unique_ratio, 1.0) * 45.0
    return round(max(0.0, min(100.0, diversity)), 2)


def _is_generic_explanation(value: Any) -> bool:
    text = _normalize_text(value)
    if len(text) < EXPLANATION_MIN_LENGTH:
        return True
    if len(text) >= 30 and any(token in text for token in {"vwap", "volume", "range", "faixa", "liquidez", "fluxo", "reacao", "reação", "lateral", "expans", "rompimento", "preço", "preco"}):
        return False
    if len(text) >= 48:
        return False
    return any(hint in text for hint in GENERIC_EXPLANATION_HINTS)


def _score_explanations(rows: Iterable[Dict[str, Any]]) -> tuple[float, List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    safe_rows = _safe_rows(list(rows))
    if not safe_rows:
        return 0.0, findings

    weak_comment = []
    weak_trigger = []
    weak_invalidation = []

    for row in safe_rows:
        ticker = str(row.get("ticker") or "?")
        if _is_generic_explanation(row.get("ai_comment")):
            weak_comment.append(ticker)
        if _is_generic_explanation(row.get("trigger")):
            weak_trigger.append(ticker)
        if _is_generic_explanation(row.get("invalidation")):
            weak_invalidation.append(ticker)

    if weak_comment:
        findings.append(
            {
                "severity": "warning",
                "code": "weak_ai_comment",
                "detail": "Explicacao final da IA esta curta ou generica demais para o trader",
                "tickers": weak_comment[:10],
            }
        )
    if weak_trigger:
        findings.append(
            {
                "severity": "warning",
                "code": "weak_trigger",
                "detail": "Trigger da IA esta curto ou generico demais",
                "tickers": weak_trigger[:10],
            }
        )
    if weak_invalidation:
        findings.append(
            {
                "severity": "warning",
                "code": "weak_invalidation",
                "detail": "Invalidação da IA esta curta ou generica demais",
                "tickers": weak_invalidation[:10],
            }
        )

    total_slots = max(1, len(safe_rows) * 3)
    weak_total = len(weak_comment) + len(weak_trigger) + len(weak_invalidation)
    return max(0.0, round(100.0 - ((weak_total / total_slots) * 100.0), 2)), findings


def _score_product_quality(
    tool: str,
    rows: Iterable[Dict[str, Any]],
    avg_score: float,
    avg_confidence: float,
) -> tuple[float, List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    safe_rows = _safe_rows(list(rows))
    if not safe_rows:
        return 0.0, findings

    low_context = []
    ticker_only = []
    stale_or_flat = []

    for row in safe_rows:
        ticker = str(row.get("ticker") or "?")
        metrics = row.get("metrics") or {}
        name = str(row.get("name") or "").strip()
        comment = _normalize_text(row.get("ai_comment"))
        trigger = _normalize_text(row.get("trigger"))
        if name in {"", ticker} and _asset_class_for_ticker(ticker) != "crypto":
            ticker_only.append(ticker)
        if not metrics:
            low_context.append(ticker)
        if comment == trigger or comment.endswith("monitorar") or comment.endswith("monitoring"):
            stale_or_flat.append(ticker)

    if low_context:
        findings.append(
            {
                "severity": "warning",
                "code": "thin_context",
                "detail": f"{tool} esta tecnicamente preenchido, mas com pouco contexto util de mercado",
                "tickers": low_context[:10],
            }
        )
    if ticker_only:
        findings.append(
            {
                "severity": "warning",
                "code": "generic_name",
                "detail": f"{tool} ainda mostra linhas sem nome amigavel do ativo",
                "tickers": ticker_only[:10],
            }
        )
    if stale_or_flat and avg_score >= 60:
        findings.append(
            {
                "severity": "warning",
                "code": "flat_editorial",
                "detail": f"{tool} esta correto tecnicamente, mas a explicacao ainda esta fraca como produto",
                "tickers": stale_or_flat[:10],
            }
        )

    penalty = (
        (len(low_context) / max(1, len(safe_rows))) * 22.0
        + (len(ticker_only) / max(1, len(safe_rows))) * 12.0
        + (len(stale_or_flat) / max(1, len(safe_rows))) * 20.0
    )
    bonus = 0.0
    if avg_confidence >= 65:
        bonus += 8.0
    if avg_score >= 70:
        bonus += 4.0
    return round(max(0.0, min(100.0, 100.0 - penalty + bonus)), 2), findings


def _approval_status(
    consistency_score: float,
    avg_confidence: float,
    benchmark_score: float,
    product_quality: float,
    errors_present: bool,
) -> str:
    approved = APPROVAL_RULES["approved"]
    watch = APPROVAL_RULES["watch"]
    if errors_present:
        return "blocked"
    if (
        consistency_score >= approved["consistency_score"]
        and avg_confidence >= approved["avg_confidence"]
        and benchmark_score >= approved["benchmark_score"]
        and product_quality >= approved["product_quality"]
    ):
        return "approved"
    if (
        consistency_score >= watch["consistency_score"]
        and avg_confidence >= watch["avg_confidence"]
        and benchmark_score >= watch["benchmark_score"]
    ):
        return "watch"
    return "blocked"


def _build_benchmark_context(snapshot: Dict[str, Any], tool: str, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    safe_rows = _safe_rows(list(rows))
    asset_class = _dominant_asset_class(safe_rows)
    if asset_class == "unknown":
        asset_class = _dominant_asset_class(_safe_rows(snapshot.get("signals")))
    scenario = _infer_scenario(snapshot, safe_rows)
    period = _infer_period(snapshot)
    expected_rows = _expected_rows_for_context(tool, asset_class, scenario)
    expected_unique_states = 1 if scenario in {"quiet", "stale"} else 2 if scenario == "balanced" else 3
    minimum_rows = 1 if scenario in {"quiet", "stale"} else 2
    return {
        "asset_class": asset_class,
        "period": period,
        "scenario": scenario,
        "expected_rows": expected_rows,
        "expected_unique_states": expected_unique_states,
        "minimum_rows": minimum_rows,
        "active_signals": len(_safe_rows(snapshot.get("signals"))),
    }


def _build_tool_qa_checklist(tool_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings = tool_report.get("findings") or []
    finding_codes = {item.get("code") for item in findings if isinstance(item, dict)}
    matrix = tool_report.get("quality_matrix") or {}
    rows = int(tool_report.get("rows") or 0)
    context = tool_report.get("benchmark_context") or {}
    minimum_rows = int(context.get("minimum_rows") or 1)
    checklist = [
        {
            "item": "Cobertura minima",
            "status": "pass" if rows >= minimum_rows else "fail",
            "detail": f"{rows} linhas auditadas",
        },
        {
            "item": "Consistencia tecnica",
            "status": "pass" if tool_report.get("consistency_score", 0) >= 85 else "warn" if tool_report.get("consistency_score", 0) >= 65 else "fail",
            "detail": f"score {tool_report.get('consistency_score', 0)}",
        },
        {
            "item": "Confianca media",
            "status": "pass" if tool_report.get("avg_confidence", 0) >= 55 else "warn" if tool_report.get("avg_confidence", 0) >= 40 else "fail",
            "detail": f"media {tool_report.get('avg_confidence', 0)}",
        },
        {
            "item": "Explicacao final ao usuario",
            "status": "pass" if not finding_codes.intersection({"weak_ai_comment", "weak_trigger", "weak_invalidation"}) else "warn",
            "detail": f"qualidade {matrix.get('explanation_quality', 0)}",
        },
        {
            "item": "Qualidade de produto",
            "status": "pass" if matrix.get("product_quality", 0) >= 80 else "warn" if matrix.get("product_quality", 0) >= 60 else "fail",
            "detail": f"qualidade {matrix.get('product_quality', 0)}",
        },
        {
            "item": "Sem drift critico",
            "status": "pass",
            "detail": "comparacao atual sem alerta critico",
        },
    ]
    return checklist


def _compare_tool_runs(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    if not previous:
        return {
            "status": "first_run",
            "detail": "Sem run anterior para comparar",
        }

    previous_states = previous.get("state_distribution") or {}
    current_states = current.get("state_distribution") or {}
    prev_dominant = max(previous_states.items(), key=lambda item: item[1])[0] if previous_states else None
    curr_dominant = max(current_states.items(), key=lambda item: item[1])[0] if current_states else None

    score_delta = round(float(current.get("avg_score", 0) or 0) - float(previous.get("avg_score", 0) or 0), 2)
    confidence_delta = round(float(current.get("avg_confidence", 0) or 0) - float(previous.get("avg_confidence", 0) or 0), 2)
    consistency_delta = round(float(current.get("consistency_score", 0) or 0) - float(previous.get("consistency_score", 0) or 0), 2)
    rows_delta = int(current.get("rows", 0) or 0) - int(previous.get("rows", 0) or 0)
    benchmark_delta = round(float(current.get("benchmark_score", 0) or 0) - float(previous.get("benchmark_score", 0) or 0), 2)

    drift_flags: List[str] = []
    if prev_dominant and curr_dominant and prev_dominant != curr_dominant:
        drift_flags.append("dominant_state_changed")
    if abs(score_delta) >= 12:
        drift_flags.append("avg_score_shift")
    if abs(confidence_delta) >= 12:
        drift_flags.append("confidence_shift")
    if abs(consistency_delta) >= 15:
        drift_flags.append("consistency_shift")
    if abs(rows_delta) >= 8:
        drift_flags.append("coverage_shift")
    if abs(benchmark_delta) >= 12:
        drift_flags.append("benchmark_shift")

    status = "stable"
    if drift_flags:
        status = "watch"
    if len(drift_flags) >= 3:
        status = "drift"

    return {
        "status": status,
        "score_delta": score_delta,
        "confidence_delta": confidence_delta,
        "consistency_delta": consistency_delta,
        "rows_delta": rows_delta,
        "benchmark_delta": benchmark_delta,
        "previous_dominant_state": prev_dominant,
        "current_dominant_state": curr_dominant,
        "flags": drift_flags,
    }


def _build_benchmark_summary(per_tool: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    approvals = Counter(item.get("approval_status", "blocked") for item in per_tool.values())
    benchmark_values = [float(item.get("benchmark_score", 0) or 0) for item in per_tool.values()]
    overall = "approved"
    if approvals.get("blocked"):
        overall = "blocked"
    elif approvals.get("watch"):
        overall = "watch"
    return {
        "overall_approval": overall,
        "approved_tools": approvals.get("approved", 0),
        "watch_tools": approvals.get("watch", 0),
        "blocked_tools": approvals.get("blocked", 0),
        "avg_benchmark_score": round(mean(benchmark_values), 2) if benchmark_values else 0.0,
    }


def _load_ai_tools_from_snapshot(snapshot: Dict[str, Any]) -> tuple[Dict[str, List[Dict[str, Any]]], str]:
    ai_tools = snapshot.get("ai_tools")

    if isinstance(ai_tools, dict) and any(_safe_rows(ai_tools.get(tool)) for tool in EXPECTED_TOOLS):
        return {tool: _safe_rows(ai_tools.get(tool)) for tool in EXPECTED_TOOLS}, "snapshot"

    signals = _safe_rows(snapshot.get("signals"))

    if signals:
        derived = build_ai_tool_payload(top_signals=signals, ranking=signals, limit=20)
        return {tool: _safe_rows(derived.get(tool)) for tool in EXPECTED_TOOLS}, "derived_from_snapshot_signals"

    return {tool: [] for tool in EXPECTED_TOOLS}, "empty"


def _is_state_consistent(tool: str, row: Dict[str, Any]) -> bool:
    score = float(row.get("score", 0) or 0)
    state = str(row.get("state") or "").strip().lower()
    metrics = row.get("metrics") or {}

    if tool == "heat_map":
        if state == "strong_buying":
            return score >= 65
        if state == "strong_selling":
            return score <= 35
        if state == "mixed":
            return 35 < score < 65
    elif tool == "radar":
        if state == "momentum_ignition":
            return score >= 78
        if state == "fast_move":
            return 58 <= score < 78
        if state == "early_radar":
            return 38 <= score < 58
        if state == "quiet":
            return score < 38
    elif tool == "breakout_probability":
        if state == "ready_to_break":
            return score >= 75
        if state == "building_pressure":
            return 55 <= score < 75
        if state == "not_ready":
            return score < 55
    elif tool in {"institutional_flow", "accumulation", "liquidity_map"}:
        if state in {"institutional_buying", "accumulation", "liquidity_hotspot"}:
            return score >= 75
        if state in {"institutional_interest", "early_accumulation", "liquidity_zone"}:
            return 55 <= score < 75
        if state in {"distribution_risk", "distribution_or_weak", "thin_liquidity"}:
            return score <= 25
        if state == "monitoring":
            return 25 < score < 55
    elif tool == "smart_money":
        if state == "smart_money_active":
            return score >= 72
        if state == "smart_money_interest":
            return 50 <= score < 72
        if state == "retail_noise":
            return score < 50
    elif tool == "volatility_squeeze":
        if state == "squeeze_ready":
            return score >= 75
        if state == "compression":
            return 55 <= score < 75
        if state == "already_expanded":
            return score <= 25
        if state == "monitoring":
            return 25 < score < 55
    elif tool == "liquidity_sweep":
        if state == "liquidity_sweep_detected":
            return score >= 70
        if state == "sweep_watch":
            return 48 <= score < 70
        if state == "no_sweep":
            return score < 48
    elif tool == "market_regime":
        trend_strength = float(metrics.get("trend_strength", 0) or 0)
        volatility_score = float(metrics.get("volatility_score", 0) or 0)
        momentum = float(metrics.get("momentum", 0) or 0)
        if state == "high_volatility":
            return volatility_score >= 72
        if state == "bull_trend":
            return trend_strength >= 60 and momentum >= 0
        if state == "bear_trend":
            return trend_strength >= 60 and momentum < 0
        if state == "range":
            return not (volatility_score >= 72 or trend_strength >= 60)
    elif tool == "master_score":
        if state == "high_conviction":
            return score >= 85
        if state == "tradable":
            return 70 <= score < 85
        if state == "neutral_setup":
            return 50 <= score < 70
        if state == "weak_setup":
            return score < 50

    return True


def _detect_cloned_tool_lists(ai_tools: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    signatures: Dict[tuple[str, ...], List[str]] = {}
    for tool in EXPECTED_TOOLS:
        rows = _safe_rows(ai_tools.get(tool))
        signature = tuple(str(row.get("ticker") or row.get("symbol") or "").upper().strip() for row in rows[:8])
        signature = tuple(item for item in signature if item)
        if len(signature) < 8:
            continue
        signatures.setdefault(signature, []).append(tool)

    findings: List[Dict[str, Any]] = []
    for signature, tools in signatures.items():
        if len(tools) < 2:
            continue
        findings.append(
            {
                "severity": "warning",
                "code": "cloned_tool_list",
                "detail": "Duas ou mais IAs exibem a mesma lista ordenada de tickers",
                "tools": tools,
                "sample_tickers": list(signature[:8]),
            }
        )
    return findings


def _audit_tool(tool: str, rows: Iterable[Dict[str, Any]], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    safe_rows = _safe_rows(list(rows))
    findings: List[Dict[str, Any]] = []
    benchmark_context = _build_benchmark_context(snapshot, tool, safe_rows)

    if not safe_rows:
        findings.append({"severity": "error", "code": "empty_tool", "detail": f"{tool} sem linhas no snapshot atual"})
        return {
            "tool": tool,
            "status": "empty",
            "rows": 0,
            "consistency_score": 0,
            "state_distribution": {},
            "sample_tickers": [],
            "avg_score": 0.0,
            "avg_confidence": 0.0,
            "benchmark_score": 0.0,
            "approval_status": "blocked",
            "quality_matrix": {dimension: 0.0 for dimension in QUALITY_DIMENSIONS},
            "benchmark_context": benchmark_context,
            "qa_checklist": [],
            "comparison": {"status": "first_run", "detail": "Sem run anterior para comparar"},
            "findings": findings,
        }

    tickers = [str(row.get("ticker") or "") for row in safe_rows]
    score_values = [float(row.get("score", 0) or 0) for row in safe_rows]
    confidence_values = [float(row.get("confidence", 0) or 0) for row in safe_rows]
    state_distribution = dict(Counter(str(row.get("state") or "unknown") for row in safe_rows))
    avg_score = round(mean(score_values), 2) if score_values else 0.0
    avg_confidence = round(mean(confidence_values), 2) if confidence_values else 0.0

    duplicate_tickers = sorted({ticker for ticker in tickers if ticker and tickers.count(ticker) > 1})
    if duplicate_tickers:
        findings.append(
            {
                "severity": "warning",
                "code": "duplicate_tickers",
                "detail": f"{tool} tem tickers duplicados",
                "tickers": duplicate_tickers[:10],
            }
        )

    invalid_scores = [str(row.get("ticker") or "?") for row in safe_rows if not 0 <= float(row.get("score", 0) or 0) <= 100]
    if invalid_scores:
        findings.append(
            {
                "severity": "error",
                "code": "invalid_score_range",
                "detail": f"{tool} gerou score fora de 0-100",
                "tickers": invalid_scores[:10],
            }
        )

    missing_required = []
    for row in safe_rows:
        missing = [field for field in REQUIRED_FIELDS if row.get(field) in (None, "", [])]
        if missing:
            missing_required.append({"ticker": row.get("ticker"), "fields": missing})
    if missing_required:
        findings.append(
            {
                "severity": "warning",
                "code": "missing_required_fields",
                "detail": f"{tool} tem linhas com campos obrigatórios faltando",
                "items": missing_required[:10],
            }
        )

    signal_mismatches = []
    if tool != "master_score":
        for row in safe_rows:
            expected_signal = signal_from_score(float(row.get("score", 0) or 0))
            actual_signal = str(row.get("signal") or "").upper().strip()
            if actual_signal != expected_signal:
                signal_mismatches.append(
                    {
                        "ticker": row.get("ticker"),
                        "expected": expected_signal,
                        "actual": actual_signal,
                    }
                )
        if signal_mismatches:
            findings.append(
                {
                    "severity": "warning",
                    "code": "signal_score_mismatch",
                    "detail": f"{tool} tem linhas com signal divergente do score",
                    "items": signal_mismatches[:10],
                }
            )

    state_mismatches = [str(row.get("ticker") or "?") for row in safe_rows if not _is_state_consistent(tool, row)]
    if state_mismatches:
        findings.append(
            {
                "severity": "warning",
                "code": "state_score_mismatch",
                "detail": f"{tool} tem state incompatível com score/métricas",
                "tickers": state_mismatches[:10],
            }
        )

    dominant_state = None
    dominant_ratio = 0.0
    if state_distribution and len(safe_rows) >= 10 and int(benchmark_context.get("active_signals") or 0) >= 10:
        dominant_state, dominant_count = max(state_distribution.items(), key=lambda item: item[1])
        dominant_ratio = dominant_count / max(1, len(safe_rows))
        if dominant_ratio >= 0.9:
            findings.append(
                {
                    "severity": "warning",
                    "code": "state_monoculture",
                    "detail": f"{tool} está concentrado demais em um único state no snapshot atual",
                    "state": dominant_state,
                    "ratio": round(dominant_ratio, 2),
                }
            )

    if avg_confidence < 45:
        findings.append(
            {
                "severity": "warning",
                "code": "low_average_confidence",
                "detail": f"{tool} está rodando com confiança média baixa no snapshot atual",
                "avg_confidence": avg_confidence,
            }
        )

    explanation_quality, explanation_findings = _score_explanations(safe_rows)
    findings.extend(explanation_findings)

    product_quality, product_findings = _score_product_quality(
        tool=tool,
        rows=safe_rows,
        avg_score=avg_score,
        avg_confidence=avg_confidence,
    )
    findings.extend(product_findings)

    severe_penalty = sum(25 for item in findings if item["severity"] == "error")
    warning_penalty = sum(10 for item in findings if item["severity"] == "warning")
    consistency_score = max(0, 100 - severe_penalty - warning_penalty)
    state_diversity = _score_state_diversity(
        state_distribution,
        len(safe_rows),
        int(benchmark_context.get("expected_unique_states") or 1),
    )
    coverage_score = _coverage_score(len(safe_rows), int(benchmark_context.get("expected_rows") or 1))
    quality_matrix = {
        "coverage": coverage_score,
        "consistency": float(consistency_score),
        "confidence": avg_confidence,
        "state_diversity": state_diversity,
        "explanation_quality": explanation_quality,
        "product_quality": product_quality,
    }
    benchmark_score = round(
        (
            quality_matrix["coverage"] * BENCHMARK_WEIGHTS["coverage"]
            + quality_matrix["consistency"] * BENCHMARK_WEIGHTS["consistency"]
            + quality_matrix["confidence"] * BENCHMARK_WEIGHTS["confidence"]
            + quality_matrix["state_diversity"] * BENCHMARK_WEIGHTS["state_diversity"]
            + quality_matrix["explanation_quality"] * BENCHMARK_WEIGHTS["explanation_quality"]
            + quality_matrix["product_quality"] * BENCHMARK_WEIGHTS["product_quality"]
        ),
        2,
    )
    approval_status = _approval_status(
        consistency_score=consistency_score,
        avg_confidence=avg_confidence,
        benchmark_score=benchmark_score,
        product_quality=product_quality,
        errors_present=any(item["severity"] == "error" for item in findings),
    )

    status = "ok"
    if any(item["severity"] == "error" for item in findings):
        status = "degraded"
    elif findings:
        status = "warning"

    return {
        "tool": tool,
        "status": status,
        "rows": len(safe_rows),
        "consistency_score": consistency_score,
        "state_distribution": state_distribution,
        "sample_tickers": tickers[:5],
        "avg_score": avg_score,
        "avg_confidence": avg_confidence,
        "benchmark_score": benchmark_score,
        "approval_status": approval_status,
        "quality_matrix": quality_matrix,
        "benchmark_context": benchmark_context,
        "findings": findings,
    }


def _load_previous_report() -> Dict[str, Any]:
    with _lock:
        if _last_report:
            return dict(_last_report)

    latest_path = AI_TAB_AUDIT_DIR / "latest_report.json"
    if latest_path.exists():
        try:
            return json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_report(report: Dict[str, Any]) -> None:
    _ensure_report_dir()
    latest_path = AI_TAB_AUDIT_DIR / "latest_report.json"
    history_path = AI_TAB_AUDIT_DIR / f"report-{int(time.time())}.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    latest_path.write_text(payload, encoding="utf-8")
    history_path.write_text(payload, encoding="utf-8")


def _record_report(report: Dict[str, Any]) -> None:
    with _lock:
        global _last_report
        _last_report = dict(report)
        _history.insert(0, dict(report))
        del _history[AI_TAB_AUDIT_HISTORY_LIMIT:]


def _resolve_snapshot(snapshot: Dict[str, Any] | None, refresh: bool) -> Dict[str, Any]:
    if isinstance(snapshot, dict):
        return dict(snapshot)

    if refresh:
        from app.engine.market_snapshot_engine import generate_market_snapshot

        generated = generate_market_snapshot()
        if isinstance(generated, dict):
            return generated

    current = get_snapshot()
    if (isinstance(current, dict) and current.get("signals")) or (isinstance(current, dict) and current.get("ai_tools")):
        return current

    if snapshot is None:
        from app.engine.market_snapshot_engine import generate_market_snapshot

        generated = generate_market_snapshot()
        if isinstance(generated, dict):
            return generated

    if isinstance(snapshot, dict):
        return dict(snapshot)
    return current if isinstance(current, dict) else {}


def _flatten_comparison_rows(tool: str, current: Dict[str, Any], comparison: Dict[str, Any]) -> Dict[str, Any]:
    context = current.get("benchmark_context") or {}
    quality = current.get("quality_matrix") or {}
    return {
        "tool": tool,
        "status": current.get("status"),
        "approval_status": current.get("approval_status"),
        "rows": current.get("rows", 0),
        "avg_score": current.get("avg_score", 0.0),
        "avg_confidence": current.get("avg_confidence", 0.0),
        "benchmark_score": current.get("benchmark_score", 0.0),
        "consistency_score": current.get("consistency_score", 0.0),
        "coverage": quality.get("coverage", 0.0),
        "state_diversity": quality.get("state_diversity", 0.0),
        "explanation_quality": quality.get("explanation_quality", 0.0),
        "product_quality": quality.get("product_quality", 0.0),
        "asset_class": context.get("asset_class"),
        "period": context.get("period"),
        "scenario": context.get("scenario"),
        "expected_rows": context.get("expected_rows"),
        "comparison_status": comparison.get("status"),
        "comparison_score_delta": comparison.get("score_delta"),
        "comparison_confidence_delta": comparison.get("confidence_delta"),
        "comparison_consistency_delta": comparison.get("consistency_delta"),
        "comparison_rows_delta": comparison.get("rows_delta"),
        "comparison_benchmark_delta": comparison.get("benchmark_delta"),
        "comparison_flags": ";".join(comparison.get("flags") or []),
    }


def _build_batch_summary(per_tool: Dict[str, Dict[str, Any]], snapshot_payload: Dict[str, Any]) -> Dict[str, Any]:
    approvals = Counter(item.get("approval_status", "blocked") for item in per_tool.values())
    statuses = Counter(item.get("status", "unknown") for item in per_tool.values())
    benchmark_values = [float(item.get("benchmark_score", 0) or 0) for item in per_tool.values()]
    confidence_values = [float(item.get("avg_confidence", 0) or 0) for item in per_tool.values()]
    consistency_values = [float(item.get("consistency_score", 0) or 0) for item in per_tool.values()]
    scenario_counts = Counter((item.get("benchmark_context") or {}).get("scenario", "unknown") for item in per_tool.values())
    return {
        "snapshot_signals": len(_safe_rows(snapshot_payload.get("signals"))),
        "tools_expected": len(EXPECTED_TOOLS),
        "tools_present": sum(1 for item in per_tool.values() if item.get("rows", 0) > 0),
        "approved_tools": approvals.get("approved", 0),
        "watch_tools": approvals.get("watch", 0),
        "blocked_tools": approvals.get("blocked", 0),
        "degraded_tools": statuses.get("degraded", 0),
        "warning_tools": statuses.get("warning", 0),
        "avg_benchmark_score": round(mean(benchmark_values), 2) if benchmark_values else 0.0,
        "avg_confidence": round(mean(confidence_values), 2) if confidence_values else 0.0,
        "avg_consistency_score": round(mean(consistency_values), 2) if consistency_values else 0.0,
        "scenario_distribution": dict(scenario_counts),
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _export_audit_artifacts(
    report: Dict[str, Any],
    snapshot_payload: Dict[str, Any],
    ai_tools: Dict[str, List[Dict[str, Any]]],
    per_tool: Dict[str, Dict[str, Any]],
    comparisons: Dict[str, Dict[str, Any]],
) -> Dict[str, str]:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    summary_rows = [_flatten_comparison_rows(tool, per_tool[tool], comparisons.get(tool, {})) for tool in EXPECTED_TOOLS]
    detail_rows: List[Dict[str, Any]] = []
    comparison_rows: List[Dict[str, Any]] = []
    for tool in EXPECTED_TOOLS:
        current = per_tool[tool]
        context = current.get("benchmark_context") or {}
        comparison = comparisons.get(tool, {})
        source_rows = _safe_rows(ai_tools.get(tool) or (snapshot_payload.get("ai_tools") or {}).get(tool))
        for row in source_rows:
            detail_rows.append(
                {
                    "tool": tool,
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "score": row.get("score"),
                    "signal": row.get("signal"),
                    "state": row.get("state"),
                    "confidence": row.get("confidence"),
                    "asset_class": context.get("asset_class"),
                    "period": context.get("period"),
                    "scenario": context.get("scenario"),
                    "rows": current.get("rows", 0),
                    "benchmark_score": current.get("benchmark_score", 0.0),
                    "approval_status": current.get("approval_status"),
                    "product_quality": (current.get("quality_matrix") or {}).get("product_quality", 0.0),
                    "consistency_score": current.get("consistency_score", 0.0),
                    "findings": ";".join(
                        sorted(
                            {
                                item.get("code")
                                for item in current.get("findings", [])
                                if isinstance(item, dict) and item.get("code")
                            }
                        )
                    ),
                }
            )
        comparison_rows.append(
            {
                "tool": tool,
                "status": comparison.get("status"),
                "score_delta": comparison.get("score_delta"),
                "confidence_delta": comparison.get("confidence_delta"),
                "consistency_delta": comparison.get("consistency_delta"),
                "rows_delta": comparison.get("rows_delta"),
                "benchmark_delta": comparison.get("benchmark_delta"),
                "previous_dominant_state": comparison.get("previous_dominant_state"),
                "current_dominant_state": comparison.get("current_dominant_state"),
                "flags": ";".join(comparison.get("flags") or []),
            }
        )

    manifest = {
        "summary_csv": str(AI_TAB_AUDIT_EXPORT_DIR / "latest_audit_summary.csv"),
        "dataset_csv": str(AI_TAB_AUDIT_DATASET_DIR / "latest_audit_dataset.csv"),
        "comparisons_csv": str(AI_TAB_AUDIT_HISTORY_DIR / "latest_audit_comparisons.csv"),
        "summary_snapshot_csv": str(AI_TAB_AUDIT_EXPORT_DIR / f"audit_summary-{timestamp}.csv"),
        "dataset_snapshot_csv": str(AI_TAB_AUDIT_DATASET_DIR / f"audit_dataset-{timestamp}.csv"),
        "comparisons_snapshot_csv": str(AI_TAB_AUDIT_HISTORY_DIR / f"audit_comparisons-{timestamp}.csv"),
    }

    summary_fields = list(summary_rows[0].keys()) if summary_rows else []
    detail_fields = list(detail_rows[0].keys()) if detail_rows else []

    if summary_rows and summary_fields:
        _write_csv(Path(manifest["summary_csv"]), summary_rows, summary_fields)
        _write_csv(Path(manifest["summary_snapshot_csv"]), summary_rows, summary_fields)
    if detail_rows and detail_fields:
        _write_csv(Path(manifest["dataset_csv"]), detail_rows, detail_fields)
        _write_csv(Path(manifest["dataset_snapshot_csv"]), detail_rows, detail_fields)
    comparison_fields = list(comparison_rows[0].keys()) if comparison_rows else []
    if comparison_rows and comparison_fields:
        _write_csv(Path(manifest["comparisons_csv"]), comparison_rows, comparison_fields)
        _write_csv(Path(manifest["comparisons_snapshot_csv"]), comparison_rows, comparison_fields)

    report["artifacts"] = manifest
    return manifest


def run_ai_tab_audit(snapshot: Dict[str, Any] | None = None, refresh: bool = False) -> Dict[str, Any]:
    snapshot_payload = _resolve_snapshot(snapshot, refresh=refresh)
    ai_tools, source = _load_ai_tools_from_snapshot(snapshot_payload)
    previous_report = _load_previous_report()
    previous_tabs = previous_report.get("tabs") if isinstance(previous_report, dict) else {}
    if not isinstance(previous_tabs, dict):
        previous_tabs = {}

    per_tool = {tool: _audit_tool(tool, ai_tools.get(tool, []), snapshot_payload) for tool in EXPECTED_TOOLS}
    clone_findings = _detect_cloned_tool_lists(ai_tools)
    for finding in clone_findings:
        for tool in finding.get("tools", []):
            if tool not in per_tool or per_tool[tool].get("status") in {"empty", "degraded"}:
                continue
            per_tool[tool].setdefault("findings", []).append(dict(finding))
            per_tool[tool]["status"] = "warning"
            per_tool[tool]["consistency_score"] = max(0, float(per_tool[tool].get("consistency_score", 100) or 100) - 10)
    for tool, current in per_tool.items():
        comparison = _compare_tool_runs(previous_tabs.get(tool) or {}, current)
        current["comparison"] = comparison
        qa_checklist = _build_tool_qa_checklist(current)
        if comparison.get("status") in {"watch", "drift"}:
            for item in qa_checklist:
                if item["item"] == "Sem drift critico":
                    item["status"] = "warn" if comparison.get("status") == "watch" else "fail"
                    item["detail"] = f"flags: {', '.join(comparison.get('flags') or []) or 'n/a'}"
                    break
        current["qa_checklist"] = qa_checklist
    status_counts = Counter(item["status"] for item in per_tool.values())
    consistency_values = [item["consistency_score"] for item in per_tool.values()]
    benchmark_summary = _build_benchmark_summary(per_tool)
    tools_present = sum(1 for tool in EXPECTED_TOOLS if ai_tools.get(tool))
    has_degraded_tabs = bool(status_counts.get("degraded"))
    has_warning_tabs = bool(status_counts.get("warning"))
    has_empty_tabs = bool(status_counts.get("empty"))
    all_tabs_ok = all(item.get("status") == "ok" for item in per_tool.values())
    overall_status = "ok"

    if tools_present == 0 or has_degraded_tabs or benchmark_summary["overall_approval"] == "blocked":
        overall_status = "degraded"
    elif (
        has_warning_tabs
        or has_empty_tabs
        or benchmark_summary["overall_approval"] == "watch"
    ):
        overall_status = "warning"
    elif benchmark_summary["overall_approval"] == "approved" and all_tabs_ok:
        overall_status = "ok"
    elif benchmark_summary["overall_approval"] == "approved":
        overall_status = "warning"

    comparisons = {
        tool: per_tool[tool].get("comparison", {"status": "first_run", "detail": "Sem run anterior para comparar"})
        for tool in EXPECTED_TOOLS
    }
    qa_checklists = {tool: per_tool[tool].get("qa_checklist", []) for tool in EXPECTED_TOOLS}
    approval_matrix = {
        tool: {
            "approval_status": per_tool[tool].get("approval_status", "blocked"),
            "benchmark_score": per_tool[tool].get("benchmark_score", 0.0),
            "quality_matrix": per_tool[tool].get("quality_matrix", {}),
        }
        for tool in EXPECTED_TOOLS
    }
    release_decision = {
        "go_live": benchmark_summary["overall_approval"] == "approved" and overall_status == "ok",
        "status": "approved" if benchmark_summary["overall_approval"] == "approved" and overall_status == "ok" else benchmark_summary["overall_approval"],
        "approved_tools": benchmark_summary["approved_tools"],
        "watch_tools": benchmark_summary["watch_tools"],
        "blocked_tools": benchmark_summary["blocked_tools"],
        "reason": "Snapshot real com tabs consistentes e benchmark institucional dentro da faixa" if benchmark_summary["overall_approval"] == "approved" and overall_status == "ok" else "Snapshot ou benchmark ainda precisa de ajuste",
    }

    report = {
        "worker": "ai_tab_audit",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "snapshot_signals": len(_safe_rows(snapshot_payload.get("signals"))),
        "overall_status": overall_status,
        "expected_tools": list(EXPECTED_TOOLS),
        "available_tools": [tool for tool, rows in ai_tools.items() if rows],
        "coverage": {
            "tools_present": tools_present,
            "tools_expected": len(EXPECTED_TOOLS),
            "avg_consistency_score": round(mean(consistency_values), 2) if consistency_values else 0.0,
        },
        "benchmark": benchmark_summary,
        "approval_matrix": approval_matrix,
        "qa_checklists": qa_checklists,
        "comparisons": comparisons,
        "batch_summary": _build_batch_summary(per_tool, snapshot_payload),
        "clone_audit": {
            "status": "warning" if clone_findings else "ok",
            "findings": clone_findings,
        },
        "release_decision": release_decision,
        "tabs": per_tool,
    }

    _export_audit_artifacts(report, snapshot_payload, ai_tools, per_tool, comparisons)
    _write_report(report)
    _record_report(report)
    return report


def get_ai_tab_audit_report() -> Dict[str, Any]:
    with _lock:
        if _last_report:
            return dict(_last_report)

    latest_path = AI_TAB_AUDIT_DIR / "latest_report.json"
    if latest_path.exists():
        try:
            return json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "worker": "ai_tab_audit",
        "overall_status": "idle",
        "detail": "No audit executed yet",
    }


def get_ai_tab_audit_history(limit: int = 10) -> List[Dict[str, Any]]:
    with _lock:
        if _history:
            return [dict(item) for item in _history[: max(1, limit)]]

    items: List[Dict[str, Any]] = []
    if AI_TAB_AUDIT_DIR.exists():
        for path in sorted(AI_TAB_AUDIT_DIR.glob("report-*.json"), reverse=True)[: max(1, limit)]:
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
    return items
