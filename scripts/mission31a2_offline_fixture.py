"""Deterministic OFFLINE candle/quote fixture for the mission31a2 audit gate.

Why this exists
---------------
The AI panel hydrates from cached candles: `symbol_hydration._analysis_input`
requires >= 15 daily rows with a close and >= 15 intraday rows whose last bar has
volume. Provider access belongs to `worker.py` (`warm_charts_once`), so with no
worker running the chart cache stays empty, every symbol resolves to
INSUFFICIENT_DATA / `hydration_timeout_missing_dependencies`, and the UI never
publishes a reading.

Warming that cache from a real provider (Yahoo) makes the suite depend on the
network, on provider availability and on live data — a green that can rot
overnight without a single code change. This fixture writes the same cache
through the product's own contract (`_cache_chart_data` / `_cache_price_payload`)
using values derived from a fixed seed, so the gate is reproducible and offline.

The Playwright gate owns this fixture through ``start``/``refresh``/``stop``.
The older seed/clear/verify actions remain only as local diagnostics.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import ProxyHandler, build_opener

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.market.market_data_loader import (  # noqa: E402
    _cache_chart_data,
    _cache_price_payload,
)
from app.services.symbol_registry import canonical_symbol_aliases  # noqa: E402


def _invalidate_snapshot_memory_cache() -> None:
    """Force the in-memory SnapshotCache singleton to reload from disk on next access.

    The singleton guards reloads with `file_mtime > self._disk_mtime`. When
    consecutive fixture rounds write snapshot.json within the same mtime
    granularity window, the singleton skips the reload and serves stale RAM
    data. Resetting _disk_mtime and _timestamp to 0 makes the next
    _load_from_disk_if_needed unconditionally re-read from disk.
    """
    from app.cache.snapshot_cache import snapshot_cache  # noqa: E402

    with snapshot_cache._lock:
        snapshot_cache._disk_mtime = 0.0
        snapshot_cache._timestamp = 0.0
        snapshot_cache._last_good_timestamp = 0.0
        snapshot_cache._last_disk_write_at = 0.0
        snapshot_cache._last_disk_signature = ""
        snapshot_cache._last_good_signature = ""


def _fixture_aliases(symbol: str) -> list[str]:
    """Every alias the application will look the symbol up under.

    The bundle resolves a quote through cached_price_payloads(_symbol_aliases(ticker)),
    so seeding only the base key left the B3 aliases (PETR4.SA, BMFBOVESPA:PETR4, ...)
    holding whatever real or snapshot-sourced value was already on disk. The overlay then
    drew support/resistance from the fixture's synthetic candles while the price card
    showed that unrelated cached quote -- PETR4 at 43.42 against levels near 200, and
    VALE3/ITUB4 with a resistance below spot. The fixture must own every alias it can be
    read through, or it is not the single authority it claims to be.
    """
    return list(dict.fromkeys([symbol, *canonical_symbol_aliases(symbol)]))

POPULATION_CONTRACTS = {
    "canonical": ("PETR4", "BNY", "AMZN", "BTCUSD", "VALE3", "ITUB4", "AAPL", "TSLA", "NVDA"),
    "supplemental-avgo": ("AVGO", "AXP", "CMG", "CRWD", "GE", "GM", "LI", "ROKU", "SAP"),
    "extra-nine": ("DE", "DG", "DTC", "CAR", "CHPT", "GS", "HD", "LULU", "MARA"),
}
POPULATION_SIGNATURES = {
    "canonical": "PETR4,BNY,AMZN,BTCUSD,VALE3,ITUB4,AAPL,TSLA,NVDA",
    "supplemental-avgo": "AVGO,AXP,CMG,CRWD,GE,GM,LI,ROKU,SAP",
    "extra-nine": "DE,DG,DTC,CAR,CHPT,GS,HD,LULU,MARA",
}
POPULATION = os.getenv("MISSION31A2_POPULATION", "canonical")
if os.getenv("MISSION31A2_SYMBOLS"):
    raise ValueError("MISSION31A2_SYMBOLS is forbidden; select a named fixed population")
if POPULATION not in POPULATION_CONTRACTS:
    raise ValueError(f"unknown MISSION31A2_POPULATION: {POPULATION}")
SYMBOLS = list(POPULATION_CONTRACTS[POPULATION])
if len(SYMBOLS) != 9 or len(set(SYMBOLS)) != 9 or ",".join(SYMBOLS) != POPULATION_SIGNATURES[POPULATION]:
    raise ValueError(f"mission31a2 population contract changed: {POPULATION}")

DAILY_ROWS = 40
INTRADAY_ROWS = 60
INTERVALS_INTRADAY = ("1D", "@5M")
INTERVAL_DAILY = "3M"
LOCK_PATH = REPO_ROOT / "runtime" / "mission31a2_fixture.lock"
QUOTE_BACKUP_PATH = REPO_ROOT / "runtime" / "mission31a2_quote_backup.json"
SNAPSHOT_BACKUP_PATH = REPO_ROOT / "runtime" / "mission31a2_snapshot_backup.json"
ANALYSIS_PATH = Path(
    os.getenv("SYMBOL_ANALYSIS_CACHE_FILE")
    or REPO_ROOT / "runtime" / "cache" / "symbol_analysis.json"
)
API_BASE = (os.getenv("MISSION31A2_API_BASE") or "http://127.0.0.1:8000").rstrip("/")
_LOCAL_OPENER = build_opener(ProxyHandler({}))


def _seed_value(symbol: str, index: int) -> float:
    """Deterministic pseudo-noise in [0, 1) derived from symbol + index."""
    digest = hashlib.sha256(f"{symbol}:{index}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _base_price(symbol: str) -> float:
    return 20.0 + (int(hashlib.sha256(symbol.encode()).hexdigest()[:6], 16) % 18000) / 100.0


def _candles(symbol: str, count: int, step: timedelta, anchor: datetime) -> list[dict]:
    """Monotonic-time OHLCV rows with a non-zero close and volume on every bar."""
    base = _base_price(symbol)
    cycle = (0.0, 0.04, 0.0, -0.04, 0.0)
    rows: list[dict] = []
    for index in range(count):
        # Repeated extrema plus a central final close exercise real, operational
        # support/resistance at every price scale instead of a random micro-range.
        close = round(base * (1 + cycle[index % len(cycle)]), 4)
        spread = round(max(0.01, close * 0.004), 4)
        stamp = anchor - step * (count - 1 - index)
        rows.append({
            "time": str(stamp),
            "open": round(close - spread / 2, 4),
            "high": round(close + spread, 4),
            "low": round(close - spread, 4),
            "close": close,
            # Last bar volume must be > 0 or _analysis_input rejects the frame.
            "volume": float(1_000_000 + int(_seed_value(symbol, index + 500) * 9_000_000)),
        })
    return rows


def _seed() -> dict:
    anchor = datetime.now(timezone.utc).replace(microsecond=0)
    for symbol in SYMBOLS:
        daily = _candles(symbol, DAILY_ROWS, timedelta(days=1), anchor)
        intraday = _candles(symbol, INTRADAY_ROWS, timedelta(minutes=5), anchor)
        _cache_chart_data(symbol, INTERVAL_DAILY, daily)
        for interval in INTERVALS_INTRADAY:
            _cache_chart_data(symbol, interval, intraday)
        last = intraday[-1]
        # Written to every alias, not just the base key: whichever alias the bundle
        # resolves through must carry the same price these candles imply.
        for alias in _fixture_aliases(symbol):
            _cache_price_payload(alias, {
                "symbol": symbol,
                "price": last["close"],
                "change_pct": 0.75,
                "volume": last["volume"],
                "source": "mission31a2_offline_fixture",
                "price_semantics": "direct_market_price",
                "timestamp": str(anchor),
            })
    return {
        "population": POPULATION,
        "symbols": SYMBOLS,
        "seeded_symbols": len(SYMBOLS),
        "daily_rows": DAILY_ROWS,
        "intraday_rows": INTRADAY_ROWS,
        "anchor": anchor.isoformat(),
        "external_provider_calls": 0,
    }


def seed() -> int:
    print(json.dumps(_seed(), indent=2))
    return 0


def _clear_hydration_states() -> int:
    try:
        payload = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return 0
    items = payload.get("items", payload) if isinstance(payload, dict) else {}
    if not isinstance(items, dict):
        return 0
    removed = 0
    for symbol in SYMBOLS:
        if items.pop(f"{symbol}:1D", None) is not None:
            removed += 1
    ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ANALYSIS_PATH.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, ANALYSIS_PATH)
    return removed


def _local_get(path: str) -> None:
    target = f"{API_BASE}{path}"
    parsed = urlparse(target)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("mission31a2 fixture only permits loopback HTTP")
    with _LOCAL_OPENER.open(target, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"local fixture request failed with HTTP {response.status}")
        response.read()


def _sync_backend_hydration_cache() -> bool:
    try:
        _local_get(f"/public/market/insight/{quote(SYMBOLS[0])}?interval=1D")
        return True
    except (OSError, RuntimeError):
        return False


def _seed_hydration_states() -> dict:
    failures: list[str] = []
    for symbol in SYMBOLS:
        try:
            _local_get(f"/public/market/bundle/{quote(symbol)}?interval=1D&limit=6&locale=pt-BR")
        except (OSError, RuntimeError) as exc:
            failures.append(f"{symbol}: hydration request failed: {exc}")

    deadline = time.monotonic() + 15
    statuses: dict[str, str] = {}
    while time.monotonic() < deadline and not failures:
        try:
            payload = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
            items = payload.get("items", payload) if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            items = {}
        statuses = {symbol: str((items.get(f"{symbol}:1D") or {}).get("status") or "PENDING") for symbol in SYMBOLS}
        if all(status == "READY" for status in statuses.values()):
            break
        time.sleep(0.25)
    for symbol, status in statuses.items():
        if status != "READY":
            failures.append(f"{symbol}: hydration status {status}")
    return {"statuses": statuses, "failures": failures, "external_provider_calls": 0}


def _remove_cache_keys(path: Path, container: str | None, keys: set[str]) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return 0
    values = payload.get(container, {}) if container and isinstance(payload, dict) else payload
    if not isinstance(values, dict):
        return 0
    removed = sum(values.pop(key, None) is not None for key in keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)
    return removed


def _clear() -> dict:
    """Remove every quote, candle and persisted hydration state owned here."""
    from app.market.market_data_loader import (
        _CHART_DATA_CACHE,
        _CHART_CACHE_FILE,
        _PRICE_SNAPSHOT_CACHE,
        _PRICE_CACHE_FILE,
        _cache_key,
        _chart_cache_key,
    )

    quote_keys = {
        _cache_key(alias)
        for symbol in SYMBOLS
        for alias in _fixture_aliases(symbol)
    }
    candle_keys = {
        _chart_cache_key(symbol, interval)
        for symbol in SYMBOLS
        for interval in (INTERVAL_DAILY, *INTERVALS_INTRADAY)
    }
    removed_quotes = _remove_cache_keys(_PRICE_CACHE_FILE, None, quote_keys)
    removed_candles = _remove_cache_keys(_CHART_CACHE_FILE, "charts", candle_keys)
    
    # Also remove from snapshot.json
    snapshot_path = REPO_ROOT / "runtime" / "cache" / "snapshot.json"
    snapshot_removed = 0
    try:
        snap_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        for container in ("payload", "last_good_payload"):
            if container in snap_data and isinstance(snap_data[container], dict):
                by_ticker = snap_data[container].get("by_ticker")
                if isinstance(by_ticker, dict):
                    for symbol in SYMBOLS:
                        for alias in _fixture_aliases(symbol):
                            if by_ticker.pop(alias, None) is not None:
                                snapshot_removed += 1
                        if by_ticker.pop(symbol, None) is not None:
                            snapshot_removed += 1
                signals = snap_data[container].get("signals")
                if isinstance(signals, list):
                    new_signals = []
                    for sig in signals:
                        if isinstance(sig, dict):
                            sig_sym = sig.get("ticker") or sig.get("symbol")
                            if sig_sym in SYMBOLS or any(sig_sym in _fixture_aliases(s) for s in SYMBOLS):
                                snapshot_removed += 1
                                continue
                        new_signals.append(sig)
                    snap_data[container]["signals"] = new_signals
        if snapshot_removed > 0:
            now = time.time()
            if "timestamp" in snap_data:
                snap_data["timestamp"] = now
            if "last_good_timestamp" in snap_data:
                snap_data["last_good_timestamp"] = now
            tmp = snapshot_path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(snap_data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, snapshot_path)
            _invalidate_snapshot_memory_cache()
    except Exception:
        pass

    for key in quote_keys:
        _PRICE_SNAPSHOT_CACHE.pop(key, None)
    for key in candle_keys:
        _CHART_DATA_CACHE.pop(key, None)
    removed_hydration = _clear_hydration_states()
    return {
        "cleared_quotes": removed_quotes,
        "cleared_candles": removed_candles,
        "cleared_hydration_states": removed_hydration,
        "cleared_snapshots": snapshot_removed,
        "external_provider_calls": 0,
    }


def clear() -> int:
    print(json.dumps(_clear(), indent=2))
    return 0


def _verify() -> dict:
    """Prove the state machine both ways, entirely from local cache."""
    from app.system.symbol_hydration import _analysis_input, _chart, _quote

    failures: list[str] = []
    rows = []
    for symbol in SYMBOLS:
        intraday = _chart(symbol, "1D")
        daily = _chart(symbol, "3M")
        seed_ok = bool(intraday and daily) and _analysis_input(symbol, intraday, daily, _quote(symbol)) is not None
        rows.append({
            "symbol": symbol,
            "daily_rows": len(daily),
            "intraday_rows": len(intraday),
            "analysis_input_ready": seed_ok,
        })
        if not seed_ok:
            failures.append(f"{symbol}: analysis seed not buildable from local cache")

    return {
        "symbols": rows,
        "failures": failures,
        "external_provider_calls": 0,
    }


def verify() -> int:
    result = _verify()
    print(json.dumps(result, indent=2))
    return 1 if result["failures"] else 0


def _lock_payload() -> dict:
    try:
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _pid_alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, TypeError, ValueError):
        return False
    except PermissionError:
        return True
    return True


def _write_lock(generation: str, owner_pid: int) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"generation": generation, "owner_pid": owner_pid})
    try:
        descriptor = os.open(LOCK_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        previous = _lock_payload()
        if previous.get("generation") != generation and _pid_alive(previous.get("owner_pid")):
            raise RuntimeError("mission31a2 fixture is owned by a live generation")
        _clear()
        LOCK_PATH.unlink(missing_ok=True)
        descriptor = os.open(LOCK_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)


def _require_generation(generation: str) -> None:
    if _lock_payload().get("generation") != generation:
        raise RuntimeError("mission31a2 fixture generation mismatch")


def refresh(generation: str) -> int:
    _require_generation(generation)
    from app.market.market_data_loader import (
        _CHART_DATA_CACHE,
        _PRICE_SNAPSHOT_CACHE,
        _cache_chart_data,
        _cache_key,
        _cache_price_payload,
        _chart_cache_key,
        _load_chart_cache_once,
        _load_price_cache_once,
        _persist_chart_cache,
        _persist_price_cache,
    )

    now = time.time()
    anchor = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = anchor.isoformat()
    _load_chart_cache_once(force=True)
    _load_price_cache_once(include_stale=True, force=True)
    refreshed = 0
    for symbol in SYMBOLS:
        daily = _candles(symbol, DAILY_ROWS, timedelta(days=1), anchor)
        intraday = _candles(symbol, INTRADAY_ROWS, timedelta(minutes=5), anchor)
        for interval, rows in ((INTERVAL_DAILY, daily), *((value, intraday) for value in INTERVALS_INTRADAY)):
            if _chart_cache_key(symbol, interval) not in _CHART_DATA_CACHE:
                _cache_chart_data(symbol, interval, rows, persist=False)
        last = intraday[-1]
        owned = 0
        for alias in _fixture_aliases(symbol):
            quote = _PRICE_SNAPSHOT_CACHE.get(_cache_key(alias))
            if not isinstance(quote, dict) or (quote.get("payload") or {}).get("source") != "mission31a2_offline_fixture":
                _cache_price_payload(alias, {
                    "symbol": symbol,
                    "price": last["close"],
                    "change_pct": 0.75,
                    "volume": last["volume"],
                    "source": "mission31a2_offline_fixture",
                    "price_semantics": "direct_market_price",
                    "timestamp": stamp,
                }, persist=False)
                quote = _PRICE_SNAPSHOT_CACHE.get(_cache_key(alias))
            if isinstance(quote, dict) and (quote.get("payload") or {}).get("source") == "mission31a2_offline_fixture":
                quote["timestamp"] = now
                quote["payload"]["timestamp"] = stamp
                owned += 1
        # A symbol counts as refreshed only when every alias it can be read through is
        # fixture-owned; one stale alias is enough to desynchronise price from levels.
        if owned == len(_fixture_aliases(symbol)):
            refreshed += 1
        for interval in (INTERVAL_DAILY, *INTERVALS_INTRADAY):
            chart = _CHART_DATA_CACHE.get(_chart_cache_key(symbol, interval))
            if isinstance(chart, dict):
                chart["timestamp"] = now
    _persist_chart_cache()
    _persist_price_cache()
    print(json.dumps({"population": POPULATION, "symbols": SYMBOLS, "refreshed_quotes": refreshed, "external_provider_calls": 0}))
    return 0 if refreshed == len(SYMBOLS) else 1


def residual_entries() -> int:
    from app.market.market_data_loader import (
        _CHART_CACHE_FILE,
        _PRICE_CACHE_FILE,
        _cache_key,
        _chart_cache_key,
    )

    try:
        quotes = json.loads(_PRICE_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        quotes = {}
    try:
        chart_payload = json.loads(_CHART_CACHE_FILE.read_text(encoding="utf-8"))
        charts = chart_payload.get("charts", {}) if isinstance(chart_payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        charts = {}
    total = sum(
        1 for symbol in SYMBOLS
        if _cache_key(symbol) in quotes
        and isinstance(quotes.get(_cache_key(symbol)), dict)
        and (quotes[_cache_key(symbol)].get("payload") or {}).get("source") == "mission31a2_offline_fixture"
    )
    total += sum(
        _chart_cache_key(symbol, interval) in charts
        for symbol in SYMBOLS
        for interval in (INTERVAL_DAILY, *INTERVALS_INTRADAY)
    )
    try:
        payload = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
        items = payload.get("items", payload) if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        items = {}
    total += sum(f"{symbol}:1D" in items for symbol in SYMBOLS)
    return int(total)


def _backup_preexisting_quotes(generation: str) -> int:
    """Save any non-fixture quote entries this run is about to overwrite.

    The fixture now owns every alias, which means it displaces real cached quotes rather
    than sitting beside them. Those bytes are recorded here and put back by stop(), so a
    run leaves the working tree's cache exactly as it found it.
    """
    from app.market.market_data_loader import _PRICE_CACHE_FILE, _cache_key

    try:
        disk = json.loads(_PRICE_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        disk = {}
    if not isinstance(disk, dict):
        disk = {}
    owned_keys = {
        _cache_key(alias) for symbol in SYMBOLS for alias in _fixture_aliases(symbol)
    }
    saved = {
        key: value
        for key, value in disk.items()
        if key in owned_keys
        and isinstance(value, dict)
        and (value.get("payload") or {}).get("source") != "mission31a2_offline_fixture"
    }
    QUOTE_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUOTE_BACKUP_PATH.write_text(
        json.dumps({"generation": generation, "entries": saved}, ensure_ascii=False),
        encoding="utf-8",
    )
    
    # Backup snapshot entries
    snapshot_path = REPO_ROOT / "runtime" / "cache" / "snapshot.json"
    snapshot_saved = {"payload": {"by_ticker": {}, "signals": []}, "last_good_payload": {"by_ticker": {}, "signals": []}}
    try:
        snap_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        for container in ("payload", "last_good_payload"):
            if container in snap_data and isinstance(snap_data[container], dict):
                by_ticker = snap_data[container].get("by_ticker")
                if isinstance(by_ticker, dict):
                    for symbol in SYMBOLS:
                        for alias in _fixture_aliases(symbol) + [symbol]:
                            if alias in by_ticker:
                                snapshot_saved[container]["by_ticker"][alias] = by_ticker[alias]
                signals = snap_data[container].get("signals")
                if isinstance(signals, list):
                    for sig in signals:
                        if isinstance(sig, dict):
                            sig_sym = sig.get("ticker") or sig.get("symbol")
                            if sig_sym in SYMBOLS or any(sig_sym in _fixture_aliases(s) for s in SYMBOLS):
                                snapshot_saved[container]["signals"].append(sig)
    except Exception:
        pass
    SNAPSHOT_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_BACKUP_PATH.write_text(
        json.dumps({"generation": generation, "entries": snapshot_saved}, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(saved)

def _restore_preexisting_quotes(generation: str) -> int:
    """Put back exactly what _backup_preexisting_quotes saved for this generation."""
    from app.market.market_data_loader import _PRICE_CACHE_FILE

    try:
        backup = json.loads(QUOTE_BACKUP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return 0
    if not isinstance(backup, dict) or backup.get("generation") != generation:
        return 0
    entries = backup.get("entries") or {}
    if not isinstance(entries, dict) or not entries:
        QUOTE_BACKUP_PATH.unlink(missing_ok=True)
        return 0
    try:
        disk = json.loads(_PRICE_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        disk = {}
    if not isinstance(disk, dict):
        disk = {}
    disk.update(entries)
    _PRICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _PRICE_CACHE_FILE.with_suffix(f".{os.getpid()}.restore.tmp")
    temporary.write_text(json.dumps(disk, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, _PRICE_CACHE_FILE)
    QUOTE_BACKUP_PATH.unlink(missing_ok=True)
    
    # Restore snapshot entries
    try:
        snap_backup = json.loads(SNAPSHOT_BACKUP_PATH.read_text(encoding="utf-8"))
        if isinstance(snap_backup, dict) and snap_backup.get("generation") == generation:
            snap_entries = snap_backup.get("entries") or {}
            if snap_entries:
                snapshot_path = REPO_ROOT / "runtime" / "cache" / "snapshot.json"
                snap_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
                for container in ("payload", "last_good_payload"):
                    if container in snap_entries and snap_entries[container]:
                        if container not in snap_data or not isinstance(snap_data[container], dict):
                            snap_data[container] = {"by_ticker": {}, "signals": []}
                        if "by_ticker" not in snap_data[container] or not isinstance(snap_data[container]["by_ticker"], dict):
                            snap_data[container]["by_ticker"] = {}
                        if "by_ticker" in snap_entries[container]:
                            snap_data[container]["by_ticker"].update(snap_entries[container]["by_ticker"])
                        if "signals" not in snap_data[container] or not isinstance(snap_data[container]["signals"], list):
                            snap_data[container]["signals"] = []
                        if "signals" in snap_entries[container]:
                            snap_data[container]["signals"].extend(snap_entries[container]["signals"])
                now = time.time()
                if "timestamp" in snap_data:
                    snap_data["timestamp"] = now
                if "last_good_timestamp" in snap_data:
                    snap_data["last_good_timestamp"] = now
                tmp = snapshot_path.with_suffix(f".{os.getpid()}.restore.tmp")
                tmp.write_text(json.dumps(snap_data, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, snapshot_path)
                _invalidate_snapshot_memory_cache()
    except Exception:
        pass
    finally:
        SNAPSHOT_BACKUP_PATH.unlink(missing_ok=True)
    return len(entries)


def start(generation: str, owner_pid: int) -> int:
    _write_lock(generation, owner_pid)
    preserved_quotes = _backup_preexisting_quotes(generation)
    cleaned = _clear()
    backend_cache_synced = _sync_backend_hydration_cache()
    seeded = _seed()
    checked = _verify()
    hydration = _seed_hydration_states()
    failures = [*checked["failures"], *hydration["failures"]]
    if not backend_cache_synced:
        failures.append("backend hydration cache did not acknowledge persisted cleanup")
    result = {
        "generation": generation,
        "population": POPULATION,
        "symbols": SYMBOLS,
        "cleanup": cleaned,
        "preexisting_quotes_preserved": preserved_quotes,
        "backend_cache_synced": backend_cache_synced,
        "seed": seeded,
        "hydration": hydration,
        "failures": failures,
        "external_provider_calls": 0,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


def _stable_clear() -> tuple[dict, int]:
    totals = {"cleared_quotes": 0, "cleared_candles": 0, "cleared_hydration_states": 0, "external_provider_calls": 0}
    residual = -1
    stable_zero = 0
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        cleaned = _clear()
        for key in ("cleared_quotes", "cleared_candles", "cleared_hydration_states"):
            totals[key] += int(cleaned[key])
        time.sleep(0.75)
        residual = residual_entries()
        stable_zero = stable_zero + 1 if residual == 0 else 0
        if stable_zero >= 2:
            break
    return totals, residual


def stop(generation: str) -> int:
    _require_generation(generation)
    totals, residual = _stable_clear()
    restored_quotes = _restore_preexisting_quotes(generation)
    backend_cache_synced = _sync_backend_hydration_cache()
    residual = residual_entries()
    LOCK_PATH.unlink(missing_ok=True)
    print(json.dumps({
        "generation": generation,
        "population": POPULATION,
        "symbols": SYMBOLS,
        "cleanup": totals,
        "preexisting_quotes_restored": restored_quotes,
        "backend_cache_synced": backend_cache_synced,
        "residual_entries": residual,
        "external_provider_calls": 0,
    }, indent=2))
    return 0 if residual == 0 and backend_cache_synced else 1


def main() -> int:
    action = (sys.argv[1] if len(sys.argv) > 1 else "seed").lower()
    generation = sys.argv[2] if len(sys.argv) > 2 else ""
    if action == "seed":
        return seed()
    if action == "clear":
        return clear()
    if action == "verify":
        return verify()
    if action == "start" and generation and len(sys.argv) > 3:
        return start(generation, int(sys.argv[3]))
    if action == "refresh" and generation:
        return refresh(generation)
    if action == "stop" and generation:
        return stop(generation)
    print(f"unknown action: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
