"""The conclusion layer must not start calls that can only time out.

The H2 backend runs controlled-offline. Ollama accepts the connection but never answers
within CONCLUSION_LLM_TIMEOUT, so every scheduled fill burned a worker for 20 s and logged
a warning -- 71 of them in one session. Those daemon threads are what produced the
post-gate latency transient. Offline means: no call, honest absence, cached prose still
served, and never invented text.
"""

import threading
import time
from unittest.mock import patch

import pytest

from app.ai import conclusion_generator


PAYLOAD = {
    "symbol": "PETR4",
    "trend_bias": "ALTA",
    "signal": "alta",
    "rsi": 55.0,
    "change_pct": 1.1,
    "master_verdict": "AGUARDAR",
    "support": 40.0,
    "resistance": 45.0,
}


@pytest.fixture(autouse=True)
def clean_llm_state():
    conclusion_generator.shutdown_executor(wait=True)
    with conclusion_generator._CACHE_LOCK:
        conclusion_generator._CACHE.clear()
    yield
    conclusion_generator.shutdown_executor(wait=True)
    with conclusion_generator._CACHE_LOCK:
        conclusion_generator._CACHE.clear()


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setenv("CONCLUSION_LLM_DISABLED", "1")


@pytest.fixture
def online(monkeypatch):
    monkeypatch.delenv("CONCLUSION_LLM_DISABLED", raising=False)
    monkeypatch.delenv("CODEX_SANDBOX_NETWORK_DISABLED", raising=False)


def test_offline_makes_zero_provider_calls(offline):
    with patch.object(conclusion_generator, "requests") as requests_module:
        assert conclusion_generator.generate_conclusion(PAYLOAD) is None
        assert requests_module.post.call_count == 0


def test_offline_schedules_no_background_work(offline):
    before = threading.active_count()
    with patch.object(conclusion_generator, "requests") as requests_module:
        for _ in range(20):
            assert conclusion_generator.get_cached_or_schedule(PAYLOAD) is None
        assert requests_module.post.call_count == 0
    # No worker pool should have been created at all.
    assert conclusion_generator._EXECUTOR is None
    assert threading.active_count() <= before + 1


def test_offline_still_serves_cached_prose(offline):
    key = conclusion_generator._cache_key(PAYLOAD)
    conclusion_generator._cache_put(key, "conclusão em cache")

    assert conclusion_generator.get_cached_or_schedule(PAYLOAD) == "conclusão em cache"


def test_offline_never_invents_text(offline):
    with patch.object(conclusion_generator, "requests"):
        assert conclusion_generator.conclusion_or_template(PAYLOAD, "TEMPLATE") == "TEMPLATE"


def test_online_healthy_provider_is_called(online):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "  prosa gerada  "}

    with patch.object(conclusion_generator, "requests") as requests_module:
        requests_module.post.return_value = _Response()
        assert conclusion_generator.generate_conclusion(PAYLOAD) == "prosa gerada"
        assert requests_module.post.call_count == 1


def test_online_failing_provider_fails_closed_to_template(online):
    with patch.object(conclusion_generator, "requests") as requests_module:
        requests_module.post.side_effect = RuntimeError("connection refused")
        assert conclusion_generator.generate_conclusion(PAYLOAD) is None
        assert conclusion_generator.conclusion_or_template(PAYLOAD, "TEMPLATE") == "TEMPLATE"


def test_online_concurrent_refreshes_make_at_most_one_call_per_key(online):
    calls: list[float] = []
    barrier = threading.Event()

    class _SlowResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "prosa"}

    def _post(*args, **kwargs):
        calls.append(time.time())
        barrier.wait(timeout=2)
        return _SlowResponse()

    with patch.object(conclusion_generator, "requests") as requests_module:
        requests_module.post.side_effect = _post
        threads = [
            threading.Thread(target=conclusion_generator.get_cached_or_schedule, args=(PAYLOAD,))
            for _ in range(12)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        barrier.set()
        conclusion_generator.shutdown_executor(wait=True, cancel_futures=False)

    assert len(calls) <= 1, f"single-flight broken: {len(calls)} concurrent provider calls"


def test_sandbox_flag_alone_disables_the_provider(monkeypatch):
    monkeypatch.delenv("CONCLUSION_LLM_DISABLED", raising=False)
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    with patch.object(conclusion_generator, "requests") as requests_module:
        assert conclusion_generator.generate_conclusion(PAYLOAD) is None
        assert requests_module.post.call_count == 0
