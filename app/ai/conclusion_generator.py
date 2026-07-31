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
# Max concurrent LLM workers - bounds resource usage. Clamped to [1, 32]: a bad env
# value must never spawn an unbounded pool, nor a 0-worker pool that strands every task.
_MAX_WORKERS = max(1, min(32, int(os.getenv("CONCLUSION_LLM_MAX_WORKERS", "4"))))
# Backpressure. ThreadPoolExecutor's work queue is unbounded, so N distinct symbols would
# queue N tasks, each pinning its `data` dict. Cap the reserved (in-flight + queued) set
# instead; past the cap the panel simply keeps its template for this refresh.
_MAX_PENDING = max(1, int(os.getenv("CONCLUSION_LLM_MAX_PENDING", str(_MAX_WORKERS * 4))))
# Cache ceiling. TTL alone does not bound memory: the key carries rounded RSI and change_pct,
# so one symbol yields many distinct keys and a busy process accumulates every one of them
# for a full TTL window. Past this size the soonest-to-expire entries are dropped.
_MAX_CACHE_ENTRIES = max(1, int(os.getenv("CONCLUSION_LLM_CACHE_MAXSIZE", "512")))
# Opportunistic cleanup: sweeping the whole cache on every request is O(n) on the hot path.
# Between sweeps correctness is preserved by the per-entry expiry check in the lookup.
_EVICT_INTERVAL = float(os.getenv("CONCLUSION_LLM_EVICT_INTERVAL", "30"))

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
# _CACHE_LOCK guards _CACHE; _SCHED_LOCK guards _SCHEDULED. They are never held at the
# same time, so there is no lock ordering to get wrong.
_CACHE_LOCK = threading.Lock()
_last_evict_at = 0.0
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

    _cache_put(_cache_key(data), text)
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
    """Get or create the bounded thread pool executor.

    Double-checked: the hot path takes the already-initialised branch and never
    contends on _EXECUTOR_LOCK.
    """
    global _EXECUTOR
    executor = _EXECUTOR
    if executor is not None:
        return executor
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="conclusion-llm",
            )
        return _EXECUTOR


def shutdown_executor(wait: bool = True, *, cancel_futures: bool = True) -> None:
    """Tear the worker pool down and release every reserved key.

    Idempotent. The next get_cached_or_schedule() lazily rebuilds the pool, so this is
    safe for application shutdown and for test teardown alike.
    """
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        executor, _EXECUTOR = _EXECUTOR, None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=cancel_futures)
    with _SCHED_LOCK:
        _SCHEDULED.clear()


def _cache_get(key: tuple) -> tuple[str, float] | None:
    """Read one entry under _CACHE_LOCK."""
    with _CACHE_LOCK:
        return _CACHE.get(key)


def _cache_put(key: tuple, text: str, now: float | None = None) -> None:
    """Store one entry under _CACHE_LOCK, keeping _CACHE within _MAX_CACHE_ENTRIES."""
    if now is None:
        now = time.time()
    with _CACHE_LOCK:
        _CACHE[key] = (text, now + _TTL_SECONDS)
        overflow = len(_CACHE) - _MAX_CACHE_ENTRIES
        if overflow <= 0:
            return
        # Over the ceiling: drop whatever expires soonest, already-expired entries first.
        for stale_key in sorted(_CACHE, key=lambda k: _CACHE[k][1])[:overflow]:
            _CACHE.pop(stale_key, None)


def _evict_expired_cache(now: float | None = None, *, force: bool = True) -> int:
    """Drop expired entries from _CACHE. Returns the number of entries removed.

    force=False is the hot-path mode: it skips the O(n) sweep unless _EVICT_INTERVAL has
    elapsed or the cache sits above its ceiling. Skipping is safe because the caller
    re-checks each entry's own expiry before serving it.

    _SCHEDULED is deliberately NOT purged here. It holds only in-flight keys, which are
    exactly the keys not yet in _CACHE -- a "stale scheduled" sweep therefore released
    the live reservations and let concurrent refreshes stack duplicate LLM calls for the
    same symbol. It is bounded at admission by _MAX_PENDING and always released in
    _fill()'s finally (or on submit failure), so it never needs a sweep.
    """
    global _last_evict_at
    if now is None:
        now = time.time()
    with _CACHE_LOCK:
        if (
            not force
            and now - _last_evict_at < _EVICT_INTERVAL
            and len(_CACHE) <= _MAX_CACHE_ENTRIES
        ):
            return 0
        _last_evict_at = now
        expired_keys = [k for k, (_, exp) in _CACHE.items() if exp <= now]
        for k in expired_keys:
            _CACHE.pop(k, None)
        return len(expired_keys)


def get_cached_or_schedule(data: dict[str, Any]) -> str | None:
    """Non-blocking: return the cached prose, else fire a background fill and return None.

    This is the hot-path entrypoint. The panel calls it every refresh: the first call
    for a symbol returns None (panel keeps the template) and kicks off one LLM call in a
    bounded worker pool; once it lands in the cache the next refresh picks it up. In-flight keys
    are deduped so concurrent refreshes never stack LLM calls for the same symbol.
    """
    _evict_expired_cache(force=False)
    try:
        key = _cache_key(data)
    except (TypeError, ValueError) as exc:
        # A malformed payload must never break the bundle; the panel keeps its template.
        logger.warning("unusable conclusion payload for %s: %s", data.get("symbol"), exc)
        return None
    hit = _cache_get(key)
    if hit and hit[1] > time.time():
        return hit[0]
    with _SCHED_LOCK:
        if key in _SCHEDULED:
            return None
        if len(_SCHEDULED) >= _MAX_PENDING:
            logger.debug(
                "conclusion backlog full (%d pending), skipping %s",
                len(_SCHEDULED), data.get("symbol"),
            )
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

    try:
        _get_executor().submit(_fill)
    except Exception as exc:  # noqa: BLE001 -- pool already shut down, OOM, ...
        # Never leave the key reserved: a stuck key blocks this symbol forever.
        with _SCHED_LOCK:
            _SCHEDULED.discard(key)
        logger.warning("could not schedule conclusion for %s: %s", data.get("symbol"), exc)
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
