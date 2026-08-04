from __future__ import annotations


from typing import Any

from app.services.score_display import attach_master_score_display_contract, normalize_master_score_display
from app.services.symbol_registry import canonical_symbol


def _strip_visual(value: Any) -> str:
    text = str(value or "").strip()
    for marker in ("🚨", "🔥", "🟡", "🟢", "🔴", "⚪"):
        text = text.replace(marker, "")
    return " ".join(text.split()).strip()


def _score(value: Any, *, source_scale: str = "0_10") -> str:
    number, _warning = normalize_master_score_display(value, source_scale=source_scale)
    if value in (None, "") or _warning == "master_score_display_invalid":
        return "N/A"
    if number.is_integer():
        return str(int(number))
    return str(round(number, 2))


def _confidence(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return f"{round(number, 1)}%"


def _audit_label(value: Any) -> str:
    normalized = _strip_visual(value).upper()
    return {
        "APPROVED": "APROVADO",
        "CAUTION": "ATENÇÃO",
        "BLOCKED": "BLOQUEADO",
    }.get(normalized, normalized or "N/A")


def telegram_summary(signal: dict[str, Any] | None) -> str:
    if not isinstance(signal, dict):
        return ""

    candidates = [
        signal.get("telegram_summary"),
        signal.get("final_decision_summary"),
        signal.get("final_decision_reason"),
        signal.get("priority_summary"),
        signal.get("conviction_summary"),
        signal.get("master_summary"),
        signal.get("strategic_panel_summary"),
        signal.get("operational_summary"),
    ]
    lines: list[str] = []
    for candidate in candidates:
        if len(lines) >= 3:
            break
        if not candidate:
            continue
        for raw_line in str(candidate).replace("\r", "\n").split("\n"):
            line = " ".join(raw_line.split()).strip()
            if line and line not in lines:
                lines.append(line[:180])
            if len(lines) >= 3:
                break
    return "\n".join(lines[:3])


def format_signal_alert(signal, regime=None):
    if not isinstance(signal, dict):
        return ""

    ticker = canonical_symbol(signal.get("canonical_symbol") or signal.get("ticker") or signal.get("symbol")) or "N/A"
    final_decision = _strip_visual(signal.get("final_decision")) or "ALERTA INSTITUCIONAL"
    display_contract = attach_master_score_display_contract(signal)
    score_value = display_contract.get("master_score_raw")
    score_scale = display_contract.get("master_score_source_scale") or "0_10"
    if score_value in (None, ""):
        score_value = display_contract.get("master_score")
        score_scale = "0_10"
    master_score = (
        "N/A"
        if display_contract.get("master_score_display_warning") == "master_score_display_invalid"
        else _score(score_value, source_scale=score_scale)
    )
    audit_status = _audit_label(signal.get("audit_status") or signal.get("auditor_status") or "N/A")
    conviction = _strip_visual(signal.get("conviction_level") or "N/A")
    priority = _strip_visual(signal.get("priority_level") or "N/A")
    historical_confidence = _confidence(signal.get("historical_confidence_score"))
    summary = telegram_summary(signal) or "Contexto institucional final favoravel para acompanhamento imediato."

    message = (
        f"{final_decision}\n\n"
        f"{ticker}\n\n"
        f"🎯 Score Mestre: {master_score}\n\n"
        f"🛡️ Auditor: {audit_status}\n\n"
        f"🔥 Convicção: {conviction}\n\n"
        f"🚨 Prioridade: {priority}\n\n"
        f"📊 Confiança Histórica: {historical_confidence or 'N/A'}\n\n"
        f"Resumo:\n\n{summary}"
    )

    return message
