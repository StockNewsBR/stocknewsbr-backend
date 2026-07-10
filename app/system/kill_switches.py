# =====================================================
# STOCKNEWSBR KILL SWITCHES (Mission 32)
# =====================================================
# Controles operacionais simples, auditáveis e reversíveis para desligar
# partes do pipeline de alertas sem derrubar a aplicação.
#
# Implementação por environment variable (sem plataforma externa de flags):
#   DISABLE_PUSH_ALERTS      -> bloqueia dispatch de Push
#   DISABLE_TELEGRAM_ALERTS  -> bloqueia dispatch de Telegram
#   DISABLE_AI_DECISIONS     -> sinaliza bloqueio de decisões de IA (consumo
#                               em componentes financeiros pertence a missões
#                               futuras; alertas respeitam via envelope)
#   DISABLE_PROVIDER_<NAME>  -> sinaliza provider desativado (ex.: ALPACA)
#   DISABLE_SYMBOL_<SYMBOL>  -> bloqueia alertas de um símbolo específico
#   READ_ONLY_MODE           -> bloqueia qualquer envio externo de alerta
#
# Valores padrão: todos DESLIGADOS (pipeline habilitado). Qualquer valor em
# {1, true, yes, on, enabled} liga o kill switch. Rollback = remover/zerar a
# variável (leitura é dinâmica, sem cache).
#
# Fail-safe: erro de leitura nunca derruba o chamador; em caso de falha o
# helper de bloqueio reporta bloqueio explícito (nega envio) em vez de
# silenciosamente liberar.

import os
import re
from typing import Any, Dict, Optional

_TRUTHY = {"1", "true", "yes", "on", "enabled"}

PROVIDER_KILL_SWITCH_PREFIX = "DISABLE_PROVIDER_"
SYMBOL_KILL_SWITCH_PREFIX = "DISABLE_SYMBOL_"

CORE_KILL_SWITCHES = (
    "DISABLE_PUSH_ALERTS",
    "DISABLE_TELEGRAM_ALERTS",
    "DISABLE_AI_DECISIONS",
    "READ_ONLY_MODE",
)

# Modo institucional imutável do paper trading (Mission 25/31G).
PAPER_ONLY_MODE = "PAPER_ONLY"


def _flag_enabled(name: str, *, fail_closed: bool = False) -> bool:
    try:
        return str(os.getenv(name, "") or "").strip().lower() in _TRUTHY
    except Exception:  # pragma: no cover - defensivo
        if fail_closed:
            raise
        return False


def _normalize_suffix(value: Any) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"[^A-Z0-9]+", "_", text).strip("_")


def is_push_alerts_disabled() -> bool:
    return _flag_enabled("DISABLE_PUSH_ALERTS")


def is_telegram_alerts_disabled() -> bool:
    return _flag_enabled("DISABLE_TELEGRAM_ALERTS")


def is_ai_decisions_disabled() -> bool:
    return _flag_enabled("DISABLE_AI_DECISIONS")


def is_read_only_mode() -> bool:
    return _flag_enabled("READ_ONLY_MODE")


def is_provider_disabled(provider: Any) -> bool:
    suffix = _normalize_suffix(provider)
    if not suffix:
        return False
    return _flag_enabled(f"{PROVIDER_KILL_SWITCH_PREFIX}{suffix}")


def is_symbol_disabled(symbol: Any) -> bool:
    suffix = _normalize_suffix(symbol)
    if not suffix:
        return False
    return _flag_enabled(f"{SYMBOL_KILL_SWITCH_PREFIX}{suffix}")


def alert_channel_block_reason(channel: str) -> Optional[str]:
    """Retorna o motivo de bloqueio do canal de alerta, ou None se liberado.

    Fail-safe: qualquer erro interno resulta em bloqueio explícito e
    auditável, nunca em envio silencioso.
    """
    try:
        if _flag_enabled("READ_ONLY_MODE", fail_closed=True):
            return "kill_switch=READ_ONLY_MODE"
        normalized = str(channel or "").strip().lower()
        if normalized == "push" and _flag_enabled("DISABLE_PUSH_ALERTS", fail_closed=True):
            return "kill_switch=DISABLE_PUSH_ALERTS"
        if normalized == "telegram" and _flag_enabled("DISABLE_TELEGRAM_ALERTS", fail_closed=True):
            return "kill_switch=DISABLE_TELEGRAM_ALERTS"
        return None
    except Exception:  # pragma: no cover - defensivo
        return "kill_switch=EVALUATION_ERROR_FAIL_SAFE"


def symbol_block_reason(symbol: Any) -> Optional[str]:
    try:
        suffix = _normalize_suffix(symbol)
        if suffix and _flag_enabled(f"{SYMBOL_KILL_SWITCH_PREFIX}{suffix}", fail_closed=True):
            return f"kill_switch={SYMBOL_KILL_SWITCH_PREFIX}{suffix}"
        return None
    except Exception:  # pragma: no cover - defensivo
        return "kill_switch=EVALUATION_ERROR_FAIL_SAFE"


def _active_prefixed_switches(prefix: str) -> Dict[str, bool]:
    active: Dict[str, bool] = {}
    try:
        for name in os.environ:
            if name.startswith(prefix) and _flag_enabled(name):
                active[name] = True
    except Exception:  # pragma: no cover - defensivo
        pass
    return active


def get_kill_switch_status() -> Dict[str, Any]:
    """Snapshot auditável para health/status. Nunca expõe segredos."""
    return {
        "DISABLE_PUSH_ALERTS": is_push_alerts_disabled(),
        "DISABLE_TELEGRAM_ALERTS": is_telegram_alerts_disabled(),
        "DISABLE_AI_DECISIONS": is_ai_decisions_disabled(),
        "READ_ONLY_MODE": is_read_only_mode(),
        "providers_disabled": sorted(_active_prefixed_switches(PROVIDER_KILL_SWITCH_PREFIX)),
        "symbols_disabled": sorted(_active_prefixed_switches(SYMBOL_KILL_SWITCH_PREFIX)),
        "PAPER_ONLY": PAPER_ONLY_MODE,
        "defaults": "all switches OFF (pipeline enabled); PAPER_ONLY is immutable",
    }
