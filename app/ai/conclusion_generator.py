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
