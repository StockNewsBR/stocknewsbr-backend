import threading
import pytest
from app.system import system_metrics


@pytest.fixture(autouse=True)
def reset_provider_metrics():
    with system_metrics._lock:
        system_metrics._external_provider_calls.clear()
        system_metrics._external_provider_symbol_calls.clear()
        system_metrics._external_provider_failures.clear()
    yield
    with system_metrics._lock:
        system_metrics._external_provider_calls.clear()
        system_metrics._external_provider_symbol_calls.clear()
        system_metrics._external_provider_failures.clear()


def test_known_providers_remain_distinct():
    system_metrics.record_external_provider_call(
        "yfinance", "download", duration_seconds=0.1, success=True, symbol="PETR4"
    )
    system_metrics.record_external_provider_call(
        "brapi", "download", duration_seconds=0.2, success=True, symbol="VALE3"
    )

    calls = system_metrics._external_provider_calls
    symbol_calls = system_metrics._external_provider_symbol_calls

    assert len(calls) == 2
    assert len(symbol_calls) == 2
    assert ("unknown", "yfinance", "download", "success") in calls
    assert ("unknown", "brapi", "download", "success") in calls


def test_unknown_or_malformed_providers_converge_to_other():
    system_metrics.record_external_provider_call(
        "http://evil.com/api?q=1",
        "download?foo=bar",
        duration_seconds=0.1,
        success=True,
        symbol="PETR4?query=123",
    )
    calls = system_metrics._external_provider_calls
    symbol_calls = system_metrics._external_provider_symbol_calls

    assert ("unknown", "other", "other", "success") in calls
    assert ("unknown", "other", "other", "success", "OTHER") in symbol_calls


def test_10000_arbitrary_labels_remain_bounded():
    for i in range(10000):
        system_metrics.record_external_provider_call(
            provider=f"provider_{i}",
            operation=f"op_{i}",
            duration_seconds=0.01,
            success=True,
            symbol=f"SYM{i}",
        )

    calls = system_metrics._external_provider_calls
    symbol_calls = system_metrics._external_provider_symbol_calls

    assert len(calls) <= system_metrics._EXTERNAL_PROVIDER_CALLS_LIMIT
    assert len(symbol_calls) <= system_metrics._EXTERNAL_PROVIDER_SYMBOL_CALLS_LIMIT


def test_operation_and_status_remain_controlled():
    system_metrics.record_external_provider_call(
        "yfinance",
        "invalid/operation\nname",
        duration_seconds=0.1,
        success=False,
        error="err",
    )
    calls = system_metrics._external_provider_calls

    assert ("unknown", "yfinance", "other", "error") in calls


def test_concurrency_safe():
    def worker():
        for i in range(100):
            system_metrics.record_external_provider_call(
                provider="yfinance",
                operation="fast_info",
                duration_seconds=0.01,
                success=(i % 2 == 0),
                symbol=f"PETR{i % 5}",
            )

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert (
        len(system_metrics._external_provider_calls)
        <= system_metrics._EXTERNAL_PROVIDER_CALLS_LIMIT
    )
    assert (
        len(system_metrics._external_provider_symbol_calls)
        <= system_metrics._EXTERNAL_PROVIDER_SYMBOL_CALLS_LIMIT
    )


def test_snapshot_and_prometheus_exportation():
    system_metrics.record_external_provider_call(
        "yfinance", "download", duration_seconds=0.1, success=True, symbol="PETR4"
    )

    snapshot = system_metrics.get_performance_metrics_snapshot()
    assert "external_provider_call_total" in snapshot
    assert "external_provider_symbol_call_total" in snapshot

    prom = system_metrics.format_prometheus_metrics()
    assert "external_provider_call_total" in prom
    assert 'provider="yfinance"' in prom
