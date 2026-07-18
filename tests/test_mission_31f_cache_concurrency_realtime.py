import asyncio
import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from app.ai.final_decision import FINAL_CONFIRMED
from app.ai.institutional_auditor import AUDIT_APPROVED
from app.ai.institutional_conviction import CONVICTION_VERY_HIGH
from app.ai.institutional_priority import PRIORITY_CRITICAL
from app.ai.operational_rules import OPERATIONAL_READY
from app.core import atomic_io
from app.core.atomic_io import mutate_json_file, read_json_file, write_json_file_atomic_locked
from app.cache.signal_cache_layer import SignalCacheLayer
from app.cache.signal_outcome_cache import SignalOutcomeCache
from app.cache.paper_trading_cache import PaperTradingCache
from app.cache.snapshot_cache import SnapshotCache
from app.data import warm_data_pool
from app.services import poll_service, push_service, ticker_room_service
from app.social import moderation
from app.system.room_websocket_manager import RoomWebSocketManager
from app.system.websocket_manager import ConnectionManager
from app.telegram.telegram_alert_engine import reset_telegram_alert_state, send_signal_alert

market_data_cache = import_module("app.cache.market_data_cache")


class FakeWebSocket:
    def __init__(self, fail_send: bool = False, accept_delay: float = 0.0):
        self.accepted = False
        self.closed = None
        self.sent = []
        self.fail_send = fail_send
        self.accept_delay = accept_delay

    async def accept(self):
        await asyncio.sleep(self.accept_delay)
        self.accepted = True

    async def close(self, code=None, reason=None):
        self.closed = {"code": code, "reason": reason}

    async def send_json(self, payload):
        await asyncio.sleep(0)
        if self.fail_send:
            raise RuntimeError("dead_client")
        self.sent.append(payload)


def _telegram_row():
    return {
        "ticker": "PETR4",
        "symbol": "PETR4",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "price": 37.5,
        "volume": 1_000_000,
        "data_quality": "priced",
        "final_decision": FINAL_CONFIRMED,
        "final_decision_score": 92.0,
        "final_decision_confidence": "Alta",
        "final_decision_summary": "Fluxo comprador e contexto institucional forte.",
        "priority_level": PRIORITY_CRITICAL,
        "conviction_level": CONVICTION_VERY_HIGH,
        "operational_status": OPERATIONAL_READY,
        "audit_status": AUDIT_APPROVED,
        "master_score": 88.0,
        "master_score_raw": 88.0,
        "master_score_source_scale": "0_100",
        "master_direction": "BULLISH",
        "telegram_access": {"linked": True, "allowed": True, "reason": None},
    }


class Mission31FCacheConcurrencyRealtimeTests(unittest.TestCase):
    def setUp(self):
        reset_telegram_alert_state()

    def test_atomic_write_uses_restrictive_exclusive_tmp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            observed = []
            original_open = atomic_io.os.open

            def recording_open(path, flags, mode=0o777, *args, **kwargs):
                if str(path).endswith(".tmp"):
                    observed.append((flags, mode))
                return original_open(path, flags, mode, *args, **kwargs)

            with patch("app.core.atomic_io.os.open", side_effect=recording_open):
                atomic_io.write_json_file_atomic(target, {"value": "private"})

            self.assertTrue(observed)
            flags, mode = observed[0]
            self.assertTrue(flags & os.O_EXCL)
            self.assertEqual(mode, 0o600)

    def test_read_json_file_propagates_operational_io_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            target.write_text("{}", encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    read_json_file(target, lambda: {"fallback": True})

    def test_consistent_read_propagates_operational_io_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            target.write_text("{}", encoding="utf-8")
            with patch.object(Path, "open", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    atomic_io.read_json_file_consistent(target, lambda: {"fallback": True})

    def test_consistent_read_fails_closed_under_persistent_contention(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            target.write_text('{"value": 1}', encoding="utf-8")
            fstat_calls = {"count": 0}

            def flapping_fstat(_fd):
                fstat_calls["count"] += 1
                return SimpleNamespace(st_mtime=1.0, st_size=fstat_calls["count"], st_ino=1)

            with patch("app.core.atomic_io.os.fstat", side_effect=flapping_fstat):
                with self.assertRaises(TimeoutError):
                    atomic_io.read_json_file_consistent(
                        target,
                        lambda: {"fallback": True},
                        max_attempts=2,
                    )

    def test_atomic_locked_write_uses_shared_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            write_json_file_atomic_locked(target, {"value": 1})

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": 1})
            self.assertTrue(target.with_suffix(".json.lock").exists())

    def test_snapshot_cache_defensive_copy_blocks_nested_mutation(self):
        cache = SnapshotCache()
        payload = {
            "source": "test",
            "stale": False,
            "signals": [
                {
                    "ticker": "PETR4",
                    "master_score": 80,
                    "nested": {"levels": [1, 2]},
                }
            ],
        }

        cache.update(payload)
        payload["signals"][0]["nested"]["levels"].append(99)

        first = cache.get()
        first["signals"][0]["nested"]["levels"].append(100)
        second = cache.get()

        self.assertEqual(second["signals"][0]["nested"]["levels"], [1, 2])

    def test_snapshot_empty_update_moves_live_payload_to_last_good(self):
        cache = SnapshotCache()
        cache.update({"source": "test", "stale": False, "signals": [{"ticker": "PETR4", "master_score": 80}]})

        cache.update({"source": "empty", "stale": True, "signals": []})

        self.assertEqual(cache.get()["signals"], [])
        last_good = cache.get_last_good()
        self.assertEqual(last_good["signals"][0]["ticker"], "PETR4")
        self.assertEqual(cache.info()["last_good_signals"], 1)

    def test_snapshot_clear_blocks_pending_disk_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = SnapshotCache()
                write_started = threading.Event()
                original_write = cache._write_to_disk_payload

                def slow_write(payload):
                    write_started.set()
                    time.sleep(0.05)
                    return original_write(payload)

                with patch.object(cache, "_write_to_disk_payload", side_effect=slow_write):
                    worker = threading.Thread(
                        target=lambda: cache.update(
                            {
                                "source": "test",
                                "stale": False,
                                "signals": [{"ticker": "PETR4", "master_score": 80}],
                            }
                        )
                    )
                    worker.start()
                    self.assertTrue(write_started.wait(1))
                    cache.clear()
                    worker.join(1)

                self.assertFalse(worker.is_alive())
                self.assertTrue(cache._storage_path.exists())
                self.assertEqual(cache.get()["signals"], [])

    def test_snapshot_clear_write_failure_does_not_reload_stale_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = SnapshotCache()
                cache.update({"source": "test", "stale": False, "signals": [{"ticker": "PETR4", "master_score": 80}]})
                self.assertTrue(cache.get()["signals"])

                with patch.object(cache, "_ensure_storage_dir", side_effect=RuntimeError("disk")):
                    cache.clear()

                self.assertEqual(cache.get()["signals"], [])

    def test_signal_cache_returns_snapshot_not_internal_rows(self):
        cache = SignalCacheLayer()
        cache.update([{"ticker": "VALE3", "nested": {"items": [1]}}])

        first = cache.get()
        first[0]["nested"]["items"].append(2)
        second = cache.get()

        self.assertEqual(second[0]["nested"]["items"], [1])
        self.assertIsInstance(cache.age(), int)
        cache.clear()
        self.assertIsNone(cache.age())

    def test_signal_cache_clear_write_failure_does_not_reload_stale_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SIGNAL_CACHE_FILE": str(Path(tmp) / "signals.json")}):
                cache = SignalCacheLayer()
                cache.update([{"ticker": "VALE3"}])
                self.assertEqual(cache.get()[0]["ticker"], "VALE3")

                with patch("app.cache.signal_cache_layer.write_json_file_atomic", side_effect=RuntimeError("disk")):
                    cache.clear()

                self.assertEqual(cache.get(), [])

    def test_signal_outcome_corrupted_state_marks_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "signal_outcomes.json"
            state_path.write_text("{broken", encoding="utf-8")

            state = SignalOutcomeCache(state_path).get()

        self.assertEqual(state["signal_outcome_status"], "DEGRADED")
        self.assertEqual(state["state_error"], "state_file_corrupted")

    def test_signal_outcome_discards_stale_disk_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "signal_outcomes.json"
            stale = {"records": [{"ticker": "OLD"}]}
            state_path.write_text(json.dumps(stale), encoding="utf-8")
            stale_mtime = state_path.stat().st_mtime
            cache = SignalOutcomeCache(state_path)
            cache.update({"records": [{"ticker": "NEW"}]})

            with patch("app.cache.signal_outcome_cache.read_json_file_consistent", return_value=(stale, stale_mtime, 0)):
                cache._load_from_disk()

            self.assertEqual(cache.get()["records"][0]["ticker"], "NEW")

    def test_paper_trading_discards_stale_disk_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "paper_trading.json"
            stale = {"positions": [{"ticker": "OLD"}]}
            state_path.write_text(json.dumps(stale), encoding="utf-8")
            stale_mtime = state_path.stat().st_mtime
            cache = PaperTradingCache(state_path)
            cache.update({"positions": [{"ticker": "NEW"}]})

            with patch("app.cache.paper_trading_cache.read_json_file_consistent", return_value=(stale, stale_mtime, 0)):
                cache._load_from_disk()

            self.assertEqual(cache.get()["positions"][0]["ticker"], "NEW")

    def test_market_data_cache_tracks_partial_coverage_without_poisoning_missing_symbol(self):
        market_data_cache.market_data_cache.clear()
        columns = pd.MultiIndex.from_product([["PETR4.SA"], ["Close"]])
        frame = pd.DataFrame([[10.0], [10.5]], columns=columns)

        with patch.object(market_data_cache, "fetch_market_data", return_value=frame) as fetch:
            first = market_data_cache.get_market_data(["PETR4.SA", "VALE3.SA"])
            second = market_data_cache.get_market_data(["VALE3.SA"])

        self.assertIsNotNone(first)
        self.assertTrue(hasattr(first.columns, "levels"))
        self.assertIsNone(second)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(market_data_cache._cache_key, ("PETR4.SA",))

    def test_market_data_cache_returns_full_response_when_cache_storage_is_capped(self):
        market_data_cache.market_data_cache.clear()
        original_max = market_data_cache.MAX_CACHE_SYMBOLS
        market_data_cache.MAX_CACHE_SYMBOLS = 1
        columns = pd.MultiIndex.from_product([["PETR4.SA", "VALE3.SA"], ["Close"]])
        frame = pd.DataFrame([[10.0, 20.0], [10.5, 20.5]], columns=columns)

        try:
            with patch.object(market_data_cache, "fetch_market_data", return_value=frame):
                response = market_data_cache.get_market_data(["PETR4.SA", "VALE3.SA"])
        finally:
            market_data_cache.MAX_CACHE_SYMBOLS = original_max
            market_data_cache.market_data_cache.clear()

        self.assertEqual(set(response.columns.get_level_values(0)), {"PETR4.SA", "VALE3.SA"})

    def test_market_data_cache_serializes_concurrent_provider_miss(self):
        market_data_cache.market_data_cache.clear()
        columns = pd.MultiIndex.from_product([["PETR4.SA"], ["Close"]])
        frame = pd.DataFrame([[10.0], [10.5]], columns=columns)
        calls = []

        def slow_fetch(tickers):
            calls.append(tuple(tickers))
            time.sleep(0.05)
            return frame

        try:
            with patch.object(market_data_cache, "fetch_market_data", side_effect=slow_fetch):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _i: market_data_cache.get_market_data(["PETR4.SA"]), range(2)))
        finally:
            market_data_cache.market_data_cache.clear()

        self.assertEqual(calls, [("PETR4.SA",)])
        self.assertTrue(all(result is not None for result in results))

    def test_warm_data_pool_returns_snapshot_when_persistence_fails(self):
        columns = pd.MultiIndex.from_product([["PETR4.SA"], ["Close"]])
        market_frame = pd.DataFrame([[10.0] for _ in range(50)], columns=columns)
        original_pool = warm_data_pool._pool
        original_last_update = warm_data_pool._last_update
        try:
            warm_data_pool._pool = {}
            warm_data_pool._last_update = 0.0
            with patch.object(warm_data_pool, "get_all_tickers", return_value=["PETR4.SA"]):
                with patch.object(warm_data_pool, "get_market_data", return_value=market_frame):
                    with patch.object(warm_data_pool.market_store, "update", side_effect=RuntimeError("disk")):
                        result = warm_data_pool.update_pool(force_refresh=True)

            self.assertIn("PETR4.SA", result)
            self.assertEqual(len(result["PETR4.SA"]), 50)
        finally:
            warm_data_pool._pool = original_pool
            warm_data_pool._last_update = original_last_update

    def test_mutate_json_file_persists_mutated_state_and_returns_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"

            def mutate(state):
                state["value"] += 1
                return {"status": "updated"}

            result = mutate_json_file(
                state_path,
                lambda: {"value": 1},
                mutate,
            )

            persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result, {"status": "updated"})
        self.assertEqual(persisted, {"value": 2})

    def test_push_service_register_token_is_atomic_under_contention(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "push_tokens.json"
            original_path = push_service.PUSH_STORE_PATH
            original_lock = push_service._lock
            push_service.PUSH_STORE_PATH = target
            push_service._lock = threading.RLock()
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(push_service.register_push_token, 7, f"token-{i}", "android")
                        for i in range(2)
                    ]
                    for future in futures:
                        future.result()

                persisted = json.loads(target.read_text(encoding="utf-8"))
            finally:
                push_service.PUSH_STORE_PATH = original_path
                push_service._lock = original_lock

        self.assertEqual(len(persisted["7"]), 2)
        self.assertEqual({item["token"] for item in persisted["7"]}, {"token-0", "token-1"})

    def test_mutate_json_file_preserves_state_when_callback_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"value": 1}), encoding="utf-8")

            def mutate(state):
                state["value"] = 99
                raise RuntimeError("callback_failed")

            with self.assertRaises(RuntimeError):
                mutate_json_file(
                    state_path,
                    lambda: {"value": 0},
                    mutate,
                )

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            result = mutate_json_file(
                state_path,
                lambda: {"value": 0},
                lambda state: state.update({"value": 2}) or {"status": "ok"},
            )

        self.assertEqual(persisted, {"value": 1})
        self.assertEqual(result, {"status": "ok"})

    def test_websocket_capacity_reservation_and_dead_client_cleanup(self):
        async def scenario():
            manager = ConnectionManager()
            manager._max_connections = 1
            first = FakeWebSocket()
            second = FakeWebSocket()

            self.assertTrue(await manager.connect(first))
            self.assertFalse(await manager.connect(second))
            self.assertEqual(second.closed["code"], 1013)

            dead = FakeWebSocket(fail_send=True)
            manager.disconnect(first)
            self.assertTrue(await manager.connect(dead))
            await manager.broadcast({"type": "tick"})
            self.assertEqual(manager.stats()["active"], 0)

            slow = FakeWebSocket(accept_delay=0.05)
            with patch("app.system.websocket_manager.ACCEPT_TIMEOUT_SECONDS", 0.01):
                self.assertFalse(await manager.connect(slow))
            self.assertEqual(slow.closed["code"], 1013)
            self.assertEqual(manager.stats()["pending_accepts"], 0)

        asyncio.run(scenario())

    def test_websocket_capacity_reservation_stays_until_registered(self):
        async def scenario():
            manager = ConnectionManager()
            manager._max_connections = 1
            first = FakeWebSocket(accept_delay=0.02)
            second = FakeWebSocket()

            results = await asyncio.gather(manager.connect(first), manager.connect(second))

            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), 1)
            self.assertLessEqual(manager.stats()["active"], 1)
            self.assertEqual(manager.stats()["pending_accepts"], 0)

        asyncio.run(scenario())

    def test_room_websocket_capacity_is_per_room_and_idempotent_disconnect(self):
        async def scenario():
            manager = RoomWebSocketManager()
            manager._max_connections_per_room = 1
            first = FakeWebSocket()
            second = FakeWebSocket()

            self.assertTrue(await manager.connect("PETR4", first))
            self.assertFalse(await manager.connect("PETR4", second))
            self.assertEqual(second.closed["code"], 1013)
            manager.disconnect("PETR4", first)
            manager.disconnect("PETR4", first)
            self.assertEqual(manager.stats("PETR4")["active"], 0)

            slow = FakeWebSocket(accept_delay=0.05)
            with patch("app.system.room_websocket_manager.ACCEPT_TIMEOUT_SECONDS", 0.01):
                self.assertFalse(await manager.connect("ITUB4", slow))
            self.assertEqual(slow.closed["code"], 1013)
            self.assertEqual(manager.stats("ITUB4")["pending_accepts"], 0)

        asyncio.run(scenario())

    def test_room_websocket_capacity_reservation_stays_until_registered(self):
        async def scenario():
            manager = RoomWebSocketManager()
            manager._max_connections_per_room = 1
            first = FakeWebSocket(accept_delay=0.02)
            second = FakeWebSocket()

            results = await asyncio.gather(manager.connect("PETR4", first), manager.connect("PETR4", second))

            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), 1)
            self.assertLessEqual(manager.stats("PETR4")["active"], 1)
            self.assertEqual(manager.stats("PETR4")["pending_accepts"], 0)

        asyncio.run(scenario())

    def test_room_websocket_global_capacity_spans_rooms(self):
        async def scenario():
            manager = RoomWebSocketManager()
            manager._max_connections = 1
            manager._max_connections_per_room = 10
            first = FakeWebSocket()
            second = FakeWebSocket()

            self.assertTrue(await manager.connect("PETR4", first))
            self.assertFalse(await manager.connect("VALE3", second))
            self.assertEqual(second.closed["code"], 1013)
            self.assertEqual(manager.stats()["rooms"], {"PETR4": 1})

        asyncio.run(scenario())

    def test_room_websocket_duplicate_connection_is_closed(self):
        async def scenario():
            manager = RoomWebSocketManager()
            websocket = FakeWebSocket()
            manager._rooms["PETR4"].append(websocket)
            result = await manager.connect("PETR4", websocket)
            return result, websocket.closed, manager.stats("PETR4")

        result, closed, stats = asyncio.run(scenario())

        self.assertFalse(result)
        self.assertEqual(closed["code"], 1011)
        self.assertEqual(closed["reason"], "duplicate_connection")
        self.assertEqual(stats["active"], 0)

    def test_market_websocket_duplicate_connection_is_closed(self):
        async def scenario():
            manager = ConnectionManager()
            websocket = FakeWebSocket()
            manager._connections.append(websocket)
            result = await manager.connect(websocket)
            return result, websocket.closed, manager.stats()

        result, closed, stats = asyncio.run(scenario())

        self.assertFalse(result)
        self.assertEqual(closed["code"], 1011)
        self.assertEqual(closed["reason"], "duplicate_connection")
        self.assertEqual(stats["active"], 0)

    def test_room_websocket_stats_use_consistent_limit_key(self):
        manager = RoomWebSocketManager()

        self.assertIn("limit_per_room", manager.stats("PETR4"))
        self.assertIn("limit_per_room", manager.stats())

    def test_telegram_reserves_fingerprint_before_send_under_concurrency(self):
        send_calls = []

        def fake_send(_message):
            send_calls.append(time.time())
            time.sleep(0.1)
            return True

        with patch("app.telegram.telegram_alert_engine.send_alert", side_effect=fake_send):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _i: send_signal_alert(_telegram_row(), now=1000), range(2)))

        statuses = sorted(item["status"] for item in results)
        self.assertEqual(statuses, ["deduplicated", "sent"])
        self.assertEqual(len(send_calls), 1)

    def test_telegram_blocks_linked_account_without_access(self):
        row = _telegram_row()
        row["telegram_access"] = {"linked": True, "allowed": False, "reason": "telegram_access_required"}

        with patch("app.telegram.telegram_alert_engine.send_alert", side_effect=AssertionError("must_not_send")):
            result = send_signal_alert(row, now=1000)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "telegram_access_required")

    def test_telegram_blocks_when_access_was_not_validated(self):
        row = _telegram_row()
        row.pop("telegram_access", None)

        with patch("app.telegram.telegram_alert_engine.send_alert", side_effect=AssertionError("must_not_send")):
            result = send_signal_alert(row, now=1000)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "telegram_access_not_validated")

    def test_poll_votes_are_not_lost_under_thread_concurrency(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path = poll_service.POLL_STORE_PATH
            original_cache = dict(poll_service._store_cache)
            poll_service.POLL_STORE_PATH = Path(tmp) / "weekly_polls.json"
            poll_service._store_cache = {"path": "", "mtime": 0.0, "data": {"polls": {}}}
            try:
                # Event-only poll policy: pin the clock to a week with a US
                # economic event so an active poll deterministically exists.
                with patch.object(
                    poll_service,
                    "_utc_now",
                    return_value=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
                ):
                    poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")
                    with ThreadPoolExecutor(max_workers=12) as executor:
                        list(executor.map(lambda user_id: poll_service.vote_poll("BTCUSDT", "A", user_id=user_id), range(1, 101)))

                    poll = poll_service.get_weekly_poll("BTCUSDT")
                option_a = next(item for item in poll["options"] if item["key"] == "A")
                self.assertEqual(option_a["votes"], 100)
                self.assertEqual(poll["total_votes"], 100)
            finally:
                poll_service.POLL_STORE_PATH = original_path
                poll_service._store_cache = original_cache

    def test_poll_pruning_preserves_newly_stored_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path = poll_service.POLL_STORE_PATH
            original_cache = dict(poll_service._store_cache)
            original_max = poll_service.MAX_POLLS
            poll_service.POLL_STORE_PATH = Path(tmp) / "weekly_polls.json"
            poll_service._store_cache = {"path": "", "mtime": 0.0, "data": {"polls": {}}}
            poll_service.MAX_POLLS = 2
            try:
                poll_service._save_store(
                    {
                        "polls": {
                            "old-1": {"id": "old-1", "created_at": "9999-01-01T00:00:00+00:00"},
                            "old-2": {"id": "old-2", "created_at": "9999-01-02T00:00:00+00:00"},
                        }
                    }
                )
                poll_service._store_poll(
                    {
                        "id": "new-early",
                        "symbol": "PETR4",
                        "created_at": "2000-01-01T00:00:00+00:00",
                    }
                )
                stored = poll_service._load_store(use_cache=False)["polls"]
            finally:
                poll_service.POLL_STORE_PATH = original_path
                poll_service._store_cache = original_cache
                poll_service.MAX_POLLS = original_max

        self.assertLessEqual(len(stored), 2)
        self.assertIn("new-early", stored)

    def test_ticker_room_rolls_back_message_when_audit_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_room_path = ticker_room_service.ROOM_STORE_PATH
            original_moderation_path = moderation.MODERATION_STORE_PATH
            ticker_room_service.ROOM_STORE_PATH = Path(tmp) / "ticker_rooms.json"
            moderation.MODERATION_STORE_PATH = Path(tmp) / "moderation_state.json"
            try:
                ticker_room_service._save_store(
                    {
                        "PETR4": [
                            {"id": "old-1", "symbol": "PETR4", "status": "published", "created_at": 1},
                            {"id": "old-2", "symbol": "PETR4", "status": "published", "created_at": 2},
                        ]
                    }
                )
                with patch.object(ticker_room_service, "record_content_approved", side_effect=RuntimeError("audit")):
                    result = ticker_room_service.append_room_message("PETR4", 7, "Trader", "setup limpo")
                stored_ids = {item["id"] for item in ticker_room_service._load_store()["PETR4"]}

                self.assertEqual(result["error"], "chat_message_audit_failed")
                self.assertEqual(stored_ids, {"old-1", "old-2"})
            finally:
                ticker_room_service.ROOM_STORE_PATH = original_room_path
                moderation.MODERATION_STORE_PATH = original_moderation_path

    def test_ticker_room_publishes_only_after_audit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_room_path = ticker_room_service.ROOM_STORE_PATH
            original_moderation_path = moderation.MODERATION_STORE_PATH
            ticker_room_service.ROOM_STORE_PATH = Path(tmp) / "ticker_rooms.json"
            moderation.MODERATION_STORE_PATH = Path(tmp) / "moderation_state.json"
            try:
                message = ticker_room_service.append_room_message("PETR4", 7, "Trader", "setup limpo")
                items = ticker_room_service.list_room_messages("PETR4")
            finally:
                ticker_room_service.ROOM_STORE_PATH = original_room_path
                moderation.MODERATION_STORE_PATH = original_moderation_path

        self.assertEqual(message["status"], "published")
        self.assertEqual(items[0]["status"], "published")

    def test_ticker_room_trims_pending_write_before_audit_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_room_path = ticker_room_service.ROOM_STORE_PATH
            original_moderation_path = moderation.MODERATION_STORE_PATH
            original_max = ticker_room_service.MAX_ROOM_MESSAGES
            ticker_room_service.ROOM_STORE_PATH = Path(tmp) / "ticker_rooms.json"
            moderation.MODERATION_STORE_PATH = Path(tmp) / "moderation_state.json"
            ticker_room_service.MAX_ROOM_MESSAGES = 2
            try:
                ticker_room_service._save_store(
                    {
                        "PETR4": [
                            {"id": "old-1", "symbol": "PETR4", "status": "published", "created_at": 1},
                            {"id": "old-2", "symbol": "PETR4", "status": "published", "created_at": 2},
                        ]
                    }
                )
                with patch.object(ticker_room_service, "record_content_approved", return_value={"ok": True}):
                    message = ticker_room_service.append_room_message("PETR4", 7, "Trader", "setup limpo")
                items = ticker_room_service._load_store()["PETR4"]
            finally:
                ticker_room_service.ROOM_STORE_PATH = original_room_path
                moderation.MODERATION_STORE_PATH = original_moderation_path
                ticker_room_service.MAX_ROOM_MESSAGES = original_max

        self.assertLessEqual(len(items), 2)
        self.assertIn(message["id"], {item["id"] for item in items})


if __name__ == "__main__":
    unittest.main()
