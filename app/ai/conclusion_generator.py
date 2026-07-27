"""LLM conclusion layer -- turns the engine's per-asset data + verdict into prose.

The Score Mestre stays the single source of truth: this module NEVER decides a
verdict, invents data, or emits a trade order -- it only explains what the engine
already decided, per asset. On ANY failure (Ollama down/slow, empty/absurd output)
callers fall back to the existing Python template, so the panel never breaks.
Results are cached per (symbol, rounded indicators) for a few minutes.

Phase 1 = this isolated module. Wiring into the panel is deliberately NOT done here
(that touches the hot path). This runs synchronously; the eventual wiring should call
it off the event loop (run_in_executor) or pre-compute it in a worker.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger("stocknewsbr.conclusion_llm")

_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_MODEL = os.getenv("CONCLUSION_LLM_MODEL", "qwen3.5:9b")
_TIMEOUT = float(os.getenv("CONCLUSION_LLM_TIMEOUT", "20"))
_TTL_SECONDS = float(os.getenv("CONCLUSION_LLM_TTL", "180"))

# Provider selection. Default "ollama" keeps the existing behaviour untouched;
# set LLM_PROVIDER=omniroute to route the conclusion through the local OmniRoute
# gateway (OpenAI-compatible), with Ollama as automatic fallback. Reverting is a
# single env change -- no code edit. See docs/mission_73_omniroute_wiring.md.
_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
_OMNI_URL = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").rstrip("/")
# Fixed primary (NOT an auto-combo) so every conclusion is auditable to one model.
# codex/gpt-5.6-sol tested reliable (~1.8s); free alt that worked:
# openrouter/inclusionai/ling-3.0-flash:free. Free oc/*-free and groq are rate-limited.
_OMNI_MODEL = os.getenv("OMNIROUTE_MODEL", "codex/gpt-5.6-sol")
_OMNI_KEY = os.getenv("OMNIROUTE_API_KEY", "").strip()
_OMNI_TIMEOUT = float(os.getenv("OMNIROUTE_TIMEOUT", "20"))

# ponytail: process-local dict cache -- fine for a single web worker. Move to the
# shared snapshot cache if several workers each pay the first-miss LLM cost.
_CACHE: dict[tuple, tuple[str, float]] = {}


def _round(value: Any, ndigits: int = 0) -> float | None:
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def _cache_key(d: dict[str, Any]) -> tuple:
    return (
        str(d.get("symbol") or "").upper(),
        str(d.get("trend_bias") or "").lower(),
        str(d.get("signal") or "").lower(),
        str(d.get("master_verdict") or "").upper(),
        _round(d.get("rsi")),
        _round(d.get("change_pct"), 1),
    )


def _build_prompt(d: dict[str, Any]) -> str:
    return (
        "Você é um analista que EXPLICA a decisão de um motor quantitativo de trading. "
        "Regras: NÃO decida nada, NÃO recomende comprar ou vender, NÃO invente dados. "
        "Escreva 2 a 3 frases em português, explicando o cenário do ativo e por que o "
        "veredito do motor é o que é. Use SOMENTE os dados abaixo.\n\n"
        f"Ativo: {d.get('symbol')}\n"
        f"Variação no dia: {d.get('change_pct')}%\n"
        f"RSI: {d.get('rsi')}\n"
        f"Tendência (trend_bias): {d.get('trend_bias')}\n"
        f"Sinal técnico: {d.get('signal')}\n"
        f"Suporte: {d.get('support')} | Resistência: {d.get('resistance')}\n"
        f"VEREDITO DO MOTOR (imutável, não altere): {d.get('master_verdict')}\n\n"
        "Conclusão:"
    )


def _call_ollama(prompt: str) -> str:
    resp = requests.post(
        f"{_OLLAMA_URL}/api/generate",
        json={
            "model": _MODEL,
            "prompt": prompt,
            "stream": False,
            # qwen3 is a "thinking" model: without this it spends the whole token
            # budget in the `thinking` field and returns an empty `response`.
            "think": False,
            "options": {"temperature": 0.4, "num_predict": 220},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    text = (resp.json().get("response") or "").strip()
    if not text:
        raise ValueError("empty LLM response")
    return text


def _call_omniroute(prompt: str) -> str:
    """OpenAI-compatible call to the local OmniRoute gateway. Raises on any failure."""
    headers = {"Content-Type": "application/json"}
    if _OMNI_KEY:
        headers["Authorization"] = f"Bearer {_OMNI_KEY}"
    resp = requests.post(
        f"{_OMNI_URL}/chat/completions",
        json={
            "model": _OMNI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0.4,
            "max_tokens": 400,
        },
        headers=headers,
        timeout=_OMNI_TIMEOUT,
    )
    resp.raise_for_status()
    choice = (resp.json().get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    # A reasoning model can burn the whole budget into reasoning_content and return
    # empty content -> treat as failure so we fall back to Ollama instead of blanking.
    if not text:
        raise ValueError("empty OmniRoute response")
    return text


def _call_llm(prompt: str) -> str:
    """Primary provider with automatic fallback. Order set by LLM_PROVIDER env.

    omniroute -> try gateway, fall back to Ollama on any error (the '1-2 attempts,
    different provider' policy). Any other value keeps the original Ollama-only path.
    """
    if _PROVIDER == "omniroute":
        try:
            return _call_omniroute(prompt)
        except Exception as exc:  # noqa: BLE001 -- fall back to the local model
            logger.warning("OmniRoute failed (%s: %s), falling back to Ollama", _OMNI_MODEL, exc)
            return _call_ollama(prompt)
    return _call_ollama(prompt)


def generate_conclusion(data: dict[str, Any]) -> str:
    """LLM prose for one asset. Raises on ANY failure so the caller can fall back."""
    key = _cache_key(data)
    hit = _CACHE.get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    text = _call_llm(_build_prompt(data))
    # Sanity ceiling: reject absurd length or a naked trade order (the verdict is the
    # engine's job, never the LLM's). Rejection -> caller uses the template.
    lowered = text.lower()
    if len(text) > 900 or any(w in lowered for w in ("compre agora", "venda agora", "buy now", "sell now")):
        raise ValueError("LLM output failed sanity guard")
    _CACHE[key] = (text, time.time() + _TTL_SECONDS)
    return text


def conclusion_or_template(data: dict[str, Any], template_text: str) -> str:
    """Public entrypoint: LLM prose, or the Python template on ANY failure."""
    try:
        return generate_conclusion(data)
    except Exception as exc:  # noqa: BLE001 -- the fallback must catch everything
        logger.warning("conclusion LLM fallback for %s: %s", data.get("symbol"), exc)
        return template_text


_SCHEDULED: set = set()
_SCHED_LOCK = threading.Lock()


def get_cached_or_schedule(data: dict[str, Any]) -> str | None:
    """Non-blocking: return the cached prose, else fire a background fill and return None.

    This is the hot-path entrypoint. The panel calls it every refresh: the first call
    for a symbol returns None (panel keeps the template) and kicks off one LLM call in a
    daemon thread; once it lands in the cache the next refresh picks it up. In-flight keys
    are deduped so concurrent refreshes never stack LLM calls for the same symbol.
    """
    key = _cache_key(data)
    hit = _CACHE.get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    with _SCHED_LOCK:
        if key in _SCHEDULED:
            return None
        _SCHEDULED.add(key)

    def _fill() -> None:
        try:
            generate_conclusion(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduled conclusion failed for %s: %s", data.get("symbol"), exc)
        finally:
            with _SCHED_LOCK:
                _SCHEDULED.discard(key)

    threading.Thread(target=_fill, name="conclusion-llm", daemon=True).start()
    return None


if __name__ == "__main__":
    csan = {"symbol": "CSAN3", "trend_bias": "BAIXA", "signal": "baixa", "rsi": 42.7,
            "change_pct": -2.05, "master_verdict": "AGUARDAR", "support": 3.80, "resistance": 4.10}
    hype = {"symbol": "HYPE3", "trend_bias": "NEUTRO", "signal": "neutro", "rsi": 57.8,
            "change_pct": 0.99, "master_verdict": "AGUARDAR", "support": 19.9, "resistance": 20.8}

    # Test 1 (deterministic): unreachable Ollama -> must return the template, never crash.
    _saved = _OLLAMA_URL
    globals()["_OLLAMA_URL"] = "http://127.0.0.1:1"
    assert conclusion_or_template(csan, "TEMPLATE_FB") == "TEMPLATE_FB", "fallback must return template"
    globals()["_OLLAMA_URL"] = _saved
    print("OK: fallback returns the template when the LLM is down")

    # Test 2 (best-effort): if Ollama answers, rising vs falling must read differently.
    SAME = "TEMPLATE_SAME_FOR_BOTH"
    a = conclusion_or_template(csan, SAME)
    b = conclusion_or_template(hype, SAME)
    print("\nCSAN3 ->", a)
    print("\nHYPE3 ->", b)
    if a == SAME or b == SAME:
        print("\n(LLM indisponível agora; fallback ativo. A lógica está correta -- Test 1 provou o fallback.)")
    else:
        assert a != b, "rising and falling assets must get different conclusions"
        assert "AGUARDAR" in a.upper() or "aguard" in a.lower(), "must explain the engine verdict"
        print("\nOK: conclusões diferentes por ativo e coerentes com o veredito")
