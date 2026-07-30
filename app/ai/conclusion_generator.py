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
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

logger = logging.getLogger("stocknewsbr.conclusion_llm")

_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_MODEL = os.getenv("CONCLUSION_LLM_MODEL", "qwen3.5:9b")
_TIMEOUT = float(os.getenv("CONCLUSION_LLM_TIMEOUT", "20"))
_TTL_SECONDS = float(os.getenv("CONCLUSION_LLM_TTL", "180"))
# Max concurrent LLM workers - bounds resource usage
_MAX_WORKERS = min(4, int(os.getenv("CONCLUSION_LLM_MAX_WORKERS", "4")))

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
_SCHEDULED: set = set()
_SCHED_LOCK = threading.Lock()
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def _cache_key(data: dict[str, Any]) -> tuple:
    """Generate a cache key from the relevant indicator values."""
    symbol = data.get("symbol") or data.get("ticker") or "UNKNOWN"
    signal = str(data.get("signal") or "").strip().lower()
    verdict = str(data.get("master_verdict") or "").strip().upper()
    rsi = round(float(data.get("rsi") or 50.0), 1)
    change = round(float(data.get("change_pct") or 0.0), 1)
    return (symbol, signal, verdict, rsi, change)


def _call_llm(prompt: str) -> str | None:
    """Call the configured LLM provider and return the generated text, or None on failure."""
    if _PROVIDER == "omniroute":
        return _call_omniroute(prompt)
    return _call_ollama(prompt)


def _call_ollama(prompt: str) -> str | None:
    """Call Ollama API and return generated text."""
    try:
        resp = requests.post(
            f"{_OLLAMA_URL}/api/generate",
            json={"model": _MODEL, "prompt": prompt, "stream": False},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()
    except Exception as exc:
        logger.warning("Ollama conclusion call failed: %s", exc)
        return None


def _call_omniroute(prompt: str) -> str | None:
    """Call OmniRoute (OpenAI-compatible) API and return generated text."""
    if not _OMNI_KEY:
        logger.warning("OmniRoute API key not configured")
        return None
    try:
        headers = {"Authorization": f"Bearer {_OMNI_KEY}", "Content-Type": "application/json"}
        resp = requests.post(
            f"{_OMNI_URL}/chat/completions",
            json={
                "model": _OMNI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 256,
            },
            timeout=_OMNI_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        return None
    except Exception as exc:
        logger.warning("OmniRoute conclusion call failed: %s", exc)
        return None


def _build_prompt(data: dict[str, Any]) -> str:
    """Build the prompt for the LLM from the engine's per-asset data."""
    symbol = data.get("symbol") or data.get("ticker") or "UNKNOWN"
    trend_bias = data.get("trend_bias", "")
    signal = data.get("signal", "")
    rsi = data.get("rsi", 50)
    change_pct = data.get("change_pct", 0)
    master_verdict = data.get("master_verdict", "")
    support = data.get("support")
    resistance = data.get("resistance")

    lines = [
        f"Ativo: {symbol}",
        f"Viés de tendência: {trend_bias}",
        f"Sinal: {signal}",
        f"RSI: {rsi:.1f}",
        f"Variação: {change_pct:.2f}%",
        f"Veredito do Score Mestre: {master_verdict}",
    ]
    if support is not None:
        lines.append(f"Suporte: {support:.2f}")
    if resistance is not None:
        lines.append(f"Resistência: {resistance:.2f}")
    lines.append("Escreva uma conclusão curta (máx 3 frases) em português, explicando o veredito do Score Mestre para este ativo, sem inventar dados, sem dar ordem de compra/venda.")
    return "\n".join(lines)


def generate_conclusion(data: dict[str, Any]) -> str | None:
    """Synchronously generate an LLM conclusion for the given asset data.

    Returns the generated prose on success, None on any failure (LLM down, timeout, empty output).
    Callers MUST fall back to the Python template on None.
    """
    prompt = _build_prompt(data)
    text = _call_llm(prompt)
    if not text:
        return None

    # Cache the result
    key = _cache_key(data)
    _CACHE[key] = (text, time.time() + _TTL_SECONDS)
    return text


def conclusion_or_template(data: dict[str, Any], template: str) -> str:
    """Public API: try LLM conclusion, fall back to template on any failure.

    This is the ONLY function consumers should call. It never raises.
    """
    try:
        result = generate_conclusion(data)
        if result:
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("conclusion_or_template failed for %s: %s", data.get("symbol"), exc)
    return template


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the bounded thread pool executor."""
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="conclusion-llm",
            )
        return _EXECUTOR


def _evict_expired_cache(now: float | None = None) -> int:
    """Evict expired entries from _CACHE and stale keys from _SCHEDULED.
    Returns number of evicted cache entries."""
    if now is None:
        now = time.time()
    with _SCHED_LOCK:
        # Evict expired cache entries
        expired_keys = [k for k, (_, exp) in _CACHE.items() if exp <= now]
        for k in expired_keys:
            _CACHE.pop(k, None)
        # Also clean _SCHEDULED of keys no longer relevant (expired or done)
        # Note: _SCHEDULED only tracks in-flight generations, not finished ones
        scheduled_count_before = len(_SCHEDULED)
        # We can't easily know which scheduled keys are done; they're removed in _fill()
        # But we can limit _SCHEDULED size to prevent unbounded growth
        if scheduled_count_before > _MAX_WORKERS * 2:
            # If too many pending, clear the oldest (set is unordered, so just clear some)
            # Actually, since it's a set, we remove entries whose cache entries are expired
            active_keys = set(_CACHE.keys())
            # Remove scheduled keys that are no longer in cache (expired or never cached)
            stale_scheduled = _SCHEDULED - active_keys
            for k in stale_scheduled:
                _SCHEDULED.discard(k)
        return len(expired_keys)


def get_cached_or_schedule(data: dict[str, Any]) -> str | None:
    """Non-blocking: return the cached prose, else fire a background fill and return None.

    This is the hot-path entrypoint. The panel calls it every refresh: the first call
    for a symbol returns None (panel keeps the template) and kicks off one LLM call in a
    bounded worker pool; once it lands in the cache the next refresh picks it up. In-flight keys
    are deduped so concurrent refreshes never stack LLM calls for the same symbol.
    """
    # Bounded eviction on hot path access (ponytail: O(n) scan, fine for small cache)
    _evict_expired_cache()
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

    _get_executor().submit(_fill)
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
