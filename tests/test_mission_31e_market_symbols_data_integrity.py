import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.api import routes_public_market, routes_public_market_live
from app.market import market_data_loader
from app.services import public_market_data_service
from app.services.quote_service import classify_quote_payload, empty_quote_payload
from app.services.symbol_registry import canonical_symbol, is_ambiguous_crypto_symbol, is_bdr_symbol, symbol_category
from app.services.symbol_sanitizer import sanitize_market_symbol


class Mission31EMarketSymbolsDataIntegrityTests(unittest.TestCase):
    def setUp(self):
        market_data_loader._SYMBOL_FAILURES.clear()
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._PRICE_SNAPSHOT_CACHE.clear()

    def test_crypto_without_quote_is_ambiguous_not_silently_defaulted(self):
        for base_symbol in ("BTC", "ETH", "SOL", "btc", " BTC "):
            with self.subTest(base_symbol=base_symbol):
                market_data_loader._SYMBOL_FAILURES.clear()
                self.assertTrue(is_ambiguous_crypto_symbol(base_symbol))
                self.assertEqual(canonical_symbol(base_symbol), "")
                self.assertIsNone(sanitize_market_symbol(base_symbol, allow_provider_symbols=True))

                with patch.object(
                    market_data_loader,
                    "get_ticker_frame",
                    side_effect=AssertionError("ambiguous crypto must not call provider"),
                ):
                    self.assertIsNone(market_data_loader.get_price_snapshot(base_symbol))

                self.assertTrue(market_data_loader._is_symbol_cooling_down(base_symbol))

        self.assertEqual(canonical_symbol("BTCUSDT"), "BTCUSD")
        self.assertEqual(sanitize_market_symbol("BTCUSDT", allow_provider_symbols=True), "BTCUSD")

    def test_cached_crypto_pair_does_not_satisfy_ambiguous_base_symbol(self):
        now = time.time()
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._PRICE_SNAPSHOT_CACHE["BTCUSD"] = {
                "timestamp": now,
                "payload": {
                    "symbol": "BTCUSD",
                    "display_symbol": "BTCUSD",
                    "requested_symbol": "BTCUSDT",
                    "canonical_symbol": "BTCUSD",
                    "provider_symbol": "BTC-USD",
                    "asset_type": "CRYPTO",
                    "market": "CRYPTO",
                    "currency": "USD",
                    "timezone": "UTC",
                    "identity_preserved": True,
                    "price_semantics": "direct_market_price",
                    "freshness_semantics": "provider_observation_or_cache_ttl",
                    "price": 65000.0,
                    "source": "market_cache",
                },
            }

        with patch.object(market_data_loader, "_load_price_cache_once", return_value=None):
            self.assertEqual(market_data_loader.get_cached_price_snapshots(["BTC"]), {})
            payloads = market_data_loader.get_cached_price_snapshots(["BTCUSDT"])
        self.assertEqual(payloads["BTCUSD"]["provider_symbol"], "BTC-USD")

    def test_legacy_cache_without_identity_contract_is_migrated_before_use(self):
        now = time.time()
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._PRICE_SNAPSHOT_CACHE["PETR4"] = {
                "timestamp": now,
                "payload": {
                    "symbol": "PETR4",
                    "price": 38.8,
                    "volume": 10_000,
                    "source": "legacy_market_cache",
                },
            }

        with patch.object(market_data_loader, "_load_price_cache_once", return_value=None):
            payloads = market_data_loader.get_cached_price_snapshots(["PETR4"], allow_stale=True)
            cached = market_data_loader._get_cached_price_payload("PETR4", allow_stale=True)

        self.assertEqual(payloads["PETR4"]["canonical_symbol"], "PETR4")
        self.assertEqual(payloads["PETR4"]["provider_symbol"], "PETR4.SA")
        self.assertTrue(payloads["PETR4"]["identity_preserved"])
        self.assertEqual(cached["canonical_symbol"], "PETR4")

    def test_disk_cache_migration_reindexes_bdr_alias_to_canonical_cache_key(self):
        payload = {
            "M1TA34.SA": {
                "timestamp": time.time(),
                "payload": {
                    "symbol": "M1TA34.SA",
                    "price": 18.4,
                    "volume": 10_000,
                    "source": "legacy_market_cache",
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "market_quotes.json"
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(market_data_loader, "_PRICE_CACHE_FILE", cache_path), patch.object(
                market_data_loader, "_PRICE_CACHE_LOADED", False
            ), patch.object(market_data_loader, "_PRICE_CACHE_MTIME", 0), patch.object(
                market_data_loader, "_PRICE_CACHE_INCLUDE_STALE", False
            ):
                market_data_loader._load_price_cache_once(include_stale=True, force=True)

        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            migrated = market_data_loader._PRICE_SNAPSHOT_CACHE.get("M1TA34")

        self.assertIsNotNone(migrated)
        self.assertEqual(migrated["payload"]["symbol"], "M1TA34")
        self.assertEqual(migrated["payload"]["display_symbol"], "M1TA34")
        self.assertEqual(migrated["payload"]["canonical_symbol"], "M1TA34")
        self.assertEqual(migrated["payload"]["provider_symbol"], "M1TA34.SA")

    def test_unknown_symbol_ending_34_is_not_classified_as_bdr(self):
        self.assertEqual(canonical_symbol("ZZZZ34"), "")
        self.assertIsNone(sanitize_market_symbol("ZZZZ34", allow_provider_symbols=True))
        self.assertFalse(is_bdr_symbol("ZZZZ34"))
        self.assertFalse(market_data_loader._is_bdr_symbol("ZZZZ34"))
        for renamed_b3_symbol in ("CCRO3", "ELET3", "ELET6", "NTCO3", "VIIA3"):
            with self.subTest(renamed_b3_symbol=renamed_b3_symbol):
                self.assertFalse(market_data_loader._is_bdr_symbol(renamed_b3_symbol))
        self.assertEqual(canonical_symbol("IVVB11"), "IVVB11")
        self.assertFalse(is_bdr_symbol("IVVB11"))
        self.assertEqual(symbol_category("IVVB11"), "B3")
        self.assertEqual(canonical_symbol("A1MD34"), "A1MD34")
        self.assertTrue(is_bdr_symbol("A1MD34"))

    def test_renamed_b3_symbol_pairs_share_one_canonical_identity(self):
        # market_data_loader already collapses old/new tickers to the same cache
        # key for these corporate-action renames; canonical_symbol must agree,
        # otherwise routes using canonical_symbol() as identity (search, radar,
        # feed) treat the old and new ticker as two different assets while price
        # data is cached under a single key.
        renamed_pairs = (
            ("CCRO3", "MOTV3"),
            ("NTCO3", "NATU3"),
            ("VIIA3", "BHIA3"),
        )
        for old_symbol, new_symbol in renamed_pairs:
            with self.subTest(old_symbol=old_symbol, new_symbol=new_symbol):
                self.assertEqual(canonical_symbol(old_symbol), canonical_symbol(new_symbol))
                self.assertEqual(canonical_symbol(new_symbol), old_symbol)
                self.assertEqual(
                    market_data_loader._cache_key(old_symbol),
                    market_data_loader._cache_key(new_symbol),
                )
                self.assertEqual(symbol_category(old_symbol), "B3")
                self.assertEqual(symbol_category(new_symbol), "B3")

        with patch.object(
            market_data_loader,
            "get_ticker_frame",
            side_effect=AssertionError("unknown BDR-like symbol must not call provider"),
        ):
            self.assertIsNone(market_data_loader.get_price_snapshot("ZZZZ34"))

    def test_us_qualified_bdr_alias_is_rejected_before_suffix_stripping(self):
        for symbol in ("AAPL34.US", "NASDAQ:AAPL34", "NYSE:AAPL34"):
            with self.subTest(symbol=symbol):
                self.assertFalse(is_bdr_symbol(symbol))
                self.assertEqual(canonical_symbol(symbol), "")
                self.assertIsNone(sanitize_market_symbol(symbol, allow_provider_symbols=True))

    def test_us_qualified_b3_symbol_is_rejected_before_alias_mapping(self):
        for symbol in ("NASDAQ:PETR4", "PETR4.US", "NYSE:WING26"):
            with self.subTest(symbol=symbol):
                self.assertEqual(canonical_symbol(symbol), "")
                self.assertIsNone(sanitize_market_symbol(symbol, allow_provider_symbols=True))

    def test_market_qualified_crypto_pair_is_rejected_not_collapsed_to_crypto(self):
        for symbol in ("NASDAQ:BTCUSD", "BTCUSD.US", "NYSE:ETHUSDT"):
            with self.subTest(symbol=symbol):
                self.assertFalse(is_ambiguous_crypto_symbol(symbol))
                self.assertEqual(canonical_symbol(symbol), "")
                self.assertIsNone(sanitize_market_symbol(symbol, allow_provider_symbols=True))

    def test_qualified_symbols_do_not_become_ambiguous_crypto(self):
        self.assertFalse(is_ambiguous_crypto_symbol("SOL.US"))
        self.assertFalse(is_ambiguous_crypto_symbol("NYSE:LINK"))
        self.assertEqual(canonical_symbol("SOL.US"), "")
        self.assertEqual(canonical_symbol("NYSE:LINK"), "")
        self.assertIsNone(sanitize_market_symbol("SOL.US", allow_provider_symbols=True))
        self.assertIsNone(sanitize_market_symbol("NYSE:LINK", allow_provider_symbols=True))

        aapl_contract = market_data_loader._identity_contract_for_symbol("AAPL.US", "AAPL")
        bny_contract = market_data_loader._identity_contract_for_symbol("NYSE:BNY", "BNY")
        self.assertEqual(aapl_contract["canonical_symbol"], "AAPL")
        self.assertEqual(aapl_contract["market"], "USA")
        self.assertEqual(bny_contract["canonical_symbol"], "BNY")
        self.assertEqual(bny_contract["market"], "USA")

    def test_exchange_prefixed_crypto_base_requires_explicit_pair(self):
        for symbol in ("BINANCE:BTC", "COINBASE:ETH"):
            with self.subTest(symbol=symbol):
                self.assertTrue(is_ambiguous_crypto_symbol(symbol))
                self.assertEqual(canonical_symbol(symbol), "")
                self.assertIsNone(sanitize_market_symbol(symbol, allow_provider_symbols=True))

        self.assertEqual(canonical_symbol("BINANCE:BTCUSDT"), "BTCUSD")
        self.assertEqual(sanitize_market_symbol("BINANCE:BTCUSDT", allow_provider_symbols=True), "BTCUSD")
        self.assertEqual(canonical_symbol("NYSE:LINK"), "")
        self.assertIsNone(sanitize_market_symbol("NYSE:LINK", allow_provider_symbols=True))

    def test_client_symbol_registry_fixtures_match_backend_contract(self):
        cases = [
            ("AXIA6", "AXIA3", False, False),
            ("ELET6", "AXIA3", False, False),
            ("AXIA7", "AXIA7", False, False),
            ("A1MD34", "A1MD34", True, False),
            ("AMD34", "A1MD34", True, False),
            ("IVVB11", "IVVB11", False, False),
            ("BTC", "", False, True),
            ("BTCUSDT", "BTCUSD", False, False),
            ("NASDAQ:BTCUSD", "", False, False),
            ("AAPL34.US", "", False, False),
            ("NASDAQ:PETR4", "", False, False),
            ("PETR4.US", "", False, False),
            ("NYSE:LINK", "", False, False),
        ]
        for raw, expected_canonical, expected_bdr, expected_ambiguous in cases:
            with self.subTest(raw=raw):
                self.assertEqual(canonical_symbol(raw), expected_canonical)
                self.assertEqual(is_bdr_symbol(raw), expected_bdr)
                self.assertEqual(is_ambiguous_crypto_symbol(raw), expected_ambiguous)

        repo_root = Path(__file__).resolve().parents[1]
        client_cases = [
            {
                "raw": raw,
                "canonical": expected_canonical,
                "bdr": expected_bdr,
                "ambiguous": expected_ambiguous,
            }
            for raw, expected_canonical, expected_bdr, expected_ambiguous in cases
        ]
        script = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = process.argv[1];
const cases = JSON.parse(process.argv[2]);
let ts;
for (const candidate of [
  path.join(root, "apps/web/node_modules/typescript"),
  path.join(root, "node_modules/typescript"),
]) {
  try {
    ts = require(candidate);
    break;
  } catch (err) {
  }
}
if (!ts) {
  throw new Error("typescript module not found in known locations");
}

function loadRegistry(file) {
  const source = fs.readFileSync(file, "utf8");
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(js, { module, exports: module.exports, require, console }, { filename: file });
  return module.exports;
}

const registries = {
  web: loadRegistry(path.join(root, "apps/web/lib/symbol-registry.ts")),
  mobile: loadRegistry(path.join(root, "apps/mobile/lib/symbolRegistry.ts")),
};
const results = [];
for (const [registryName, registry] of Object.entries(registries)) {
  for (const item of cases) {
    results.push({
      registry: registryName,
      raw: item.raw,
      canonical: registry.canonicalSymbol(item.raw),
      bdr: registry.isBdrSymbol(item.raw),
      ambiguous: registry.isAmbiguousCryptoSymbol(item.raw),
    });
  }
}
process.stdout.write(JSON.stringify(results));
"""
        try:
            completed = subprocess.run(
                ["node", "-e", script, str(repo_root), json.dumps(client_cases)],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            self.skipTest("Node.js is required for client registry parity checks")
        if completed.returncode != 0:
            if "typescript module not found in known locations" in (completed.stderr or completed.stdout):
                self.skipTest("TypeScript dependency is required for client registry parity checks")
            self.fail(completed.stderr or completed.stdout)
        client_results = json.loads(completed.stdout)
        expected_by_raw = {item["raw"]: item for item in client_cases}
        for result in client_results:
            expected = expected_by_raw[result["raw"]]
            with self.subTest(registry=result["registry"], raw=result["raw"]):
                self.assertEqual(result["canonical"], expected["canonical"])
                self.assertEqual(result["bdr"], expected["bdr"])
                self.assertEqual(result["ambiguous"], expected["ambiguous"])

    def test_cached_identity_contract_rejects_wrong_symbol_aliases(self):
        now = time.time()
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._PRICE_SNAPSHOT_CACHE["PETR4"] = {
                "timestamp": now,
                "payload": {
                    "symbol": "PETR4",
                    "display_symbol": "VALE3",
                    "requested_symbol": "VALE3",
                    "canonical_symbol": "VALE3",
                    "provider_symbol": "PETR4.SA",
                    "asset_type": "B3",
                    "market": "B3",
                    "currency": "BRL",
                    "timezone": "America/Sao_Paulo",
                    "identity_preserved": True,
                    "price_semantics": "direct_market_price",
                    "freshness_semantics": "provider_observation_or_cache_ttl",
                    "price": 38.8,
                    "source": "market_cache",
                },
            }

        with patch.object(market_data_loader, "_load_price_cache_once", return_value=None):
            self.assertEqual(market_data_loader.get_cached_price_snapshots(["PETR4"], allow_stale=True), {})
            self.assertIsNone(market_data_loader._get_cached_price_payload("PETR4", allow_stale=True))

    def test_legacy_payload_without_any_identity_is_not_migrated(self):
        payload = {"price": 38.8, "volume": 10_000, "source": "legacy_market_cache"}

        self.assertFalse(market_data_loader._legacy_payload_matches_symbol("PETR4", payload))
        self.assertIsNone(market_data_loader._attach_identity_contract("PETR4", payload))

    def test_identity_contract_rejects_incoherent_proxy_semantics(self):
        payload = {
            "symbol": "AAPL34",
            "requested_symbol": "AAPL34",
            "canonical_symbol": "AAPL34",
            "display_symbol": "AAPL34",
            "provider_symbol": "AAPL34.SA",
            "asset_type": "BDR",
            "market": "B3",
            "currency": "BRL",
            "timezone": "America/Sao_Paulo",
            "identity_preserved": True,
            "price_semantics": "direct_market_price",
            "freshness_semantics": "provider_observation_or_cache_ttl",
            "price": 76.48,
            "source": "proxy_market",
            "fallback": False,
        }

        self.assertFalse(market_data_loader._has_identity_contract("AAPL34", payload))

    def test_bdr_proxy_payload_is_context_only_not_negotiable_bdr_price(self):
        proxy_payload = {
            "symbol": "AAPL34",
            "display_symbol": "AAPL34",
            "provider_symbol": "AAPL",
            "price": 210.0,
            "source": "proxy_market",
            "fallback_type": "foreign_underlying_context_only",
        }

        self.assertTrue(is_bdr_symbol("AAPL34"))
        self.assertFalse(market_data_loader._payload_matches_requested_symbol("AAPL34", proxy_payload))
        self.assertFalse(public_market_data_service._payload_matches_symbol(proxy_payload, "AAPL34"))
        self.assertFalse(routes_public_market_live._payload_matches_requested_symbol(proxy_payload, "AAPL34"))

    def test_proxy_market_payload_requires_expected_proxy_identity(self):
        proxy_payload = {
            "symbol": "AAPL",
            "display_symbol": "AAPL",
            "provider_symbol": "MSFT",
            "price": 210.0,
            "source": "proxy_market",
            "fallback_type": "foreign_underlying_context_only",
        }

        self.assertFalse(market_data_loader._payload_matches_requested_symbol("AAPL", proxy_payload))

    def test_invalid_cache_key_does_not_return_cacheable_payload(self):
        direct_payload = {
            "symbol": "PETR4",
            "display_symbol": "PETR4",
            "provider_symbol": "PETR4.SA",
            "price": 38.8,
            "source": "market_cache",
        }

        with patch.object(market_data_loader, "_cache_key", return_value=""):
            payload = market_data_loader._cache_price_payload("PETR4", direct_payload, persist=False)

        self.assertIsNone(payload)
        self.assertTrue(market_data_loader._is_symbol_cooling_down("PETR4"))
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            self.assertEqual(market_data_loader._PRICE_SNAPSHOT_CACHE, {})

    def test_public_market_data_service_filters_ambiguous_and_proxy_snapshot_cache(self):
        proxy_payload = {
            "symbol": "AAPL34",
            "display_symbol": "AAPL34",
            "provider_symbol": "AAPL",
            "price": 210.0,
            "source": "reference_proxy",
            "fallback_type": "reference_proxy",
        }
        with patch.object(
            public_market_data_service,
            "_direct_cached_price_payloads",
            return_value={"AAPL34": proxy_payload},
        ), patch.object(
            public_market_data_service,
            "get_cached_price_snapshots",
            return_value={"AAPL34": proxy_payload},
        ) as cached:
            self.assertEqual(public_market_data_service.cached_price_payloads(["BTC", "AAPL34"], allow_stale=True), {})

        cached.assert_called_once_with(["AAPL34"], allow_stale=True)

    def test_public_market_data_service_rejects_payload_cached_under_wrong_key(self):
        petr_payload = {
            "symbol": "PETR4",
            "display_symbol": "PETR4",
            "provider_symbol": "PETR4.SA",
            "price": 38.8,
            "source": "market_cache",
        }
        with patch.object(
            public_market_data_service,
            "_direct_cached_price_payloads",
            return_value={},
        ), patch.object(
            public_market_data_service,
            "get_cached_price_snapshots",
            return_value={"VALE3": petr_payload},
        ):
            self.assertEqual(public_market_data_service.cached_price_payloads(["VALE3"], allow_stale=True), {})

    def test_public_market_data_service_rejects_provider_only_proxy_cache_identity(self):
        proxy_payload = {
            "provider_symbol": "PETR4.SA",
            "price": 38.8,
            "source": "proxy_market",
            "fallback_type": "foreign_underlying_context_only",
        }

        self.assertFalse(public_market_data_service._payload_matches_cache_key(proxy_payload, "PETR4", ["PETR4"]))

    def test_bdr_direct_payload_preserves_b3_brl_identity(self):
        frame = pd.DataFrame(
            [
                {"Open": 41.0, "High": 42.5, "Low": 40.5, "Close": 41.5, "Volume": 1000},
                {"Open": 41.5, "High": 43.0, "Low": 41.2, "Close": 42.0, "Volume": 1500},
            ],
            index=pd.date_range("2026-01-01", periods=2, freq="h"),
        )

        payload = market_data_loader._price_payload_from_frame("AAPL34", frame)

        self.assertEqual(payload["symbol"], "AAPL34")
        self.assertEqual(payload["display_symbol"], "AAPL34")
        self.assertEqual(payload["provider_symbol"], "AAPL34.SA")
        self.assertEqual(payload["canonical_symbol"], "AAPL34")
        self.assertEqual(payload["asset_type"], "BDR")
        self.assertEqual(payload["market"], "B3")
        self.assertEqual(payload["currency"], "BRL")
        self.assertFalse(payload["fallback"])
        self.assertEqual(payload["price_semantics"], "direct_market_price")
        self.assertEqual(payload["price"], 42.0)

    def test_public_bundle_prefers_identity_contract_over_legacy_alias_payload(self):
        crypto_identity = {
            "symbol": "BTCUSD",
            "requested_symbol": "BTCUSD",
            "canonical_symbol": "BTCUSD",
            "display_symbol": "BTCUSD",
            "provider_symbol": "BTC-USD",
            "asset_type": "CRYPTO",
            "market": "CRYPTO",
            "currency": "USD",
            "timezone": "UTC",
            "identity_preserved": True,
            "price_semantics": "direct_market_price",
            "freshness_semantics": "provider_observation_or_cache_ttl",
            "price": 100.0,
            "source": "market_cache",
        }
        crypto_legacy_alias = {
            "symbol": "BTCUSD",
            "display_symbol": "BTCUSD",
            "provider_symbol": "BTC-USD",
            "price": 100.0,
            "source": "market_cache",
        }
        bdr_identity = {
            "symbol": "AAPL34",
            "requested_symbol": "AAPL34",
            "canonical_symbol": "AAPL34",
            "display_symbol": "AAPL34",
            "provider_symbol": "AAPL34.SA",
            "asset_type": "BDR",
            "market": "B3",
            "currency": "BRL",
            "timezone": "America/Sao_Paulo",
            "identity_preserved": True,
            "price_semantics": "direct_market_price",
            "freshness_semantics": "provider_observation_or_cache_ttl",
            "price": 76.48,
            "source": "market_cache",
        }
        bdr_legacy_alias = {
            "symbol": "AAPL34",
            "display_symbol": "AAPL34",
            "provider_symbol": "AAPL34.SA",
            "price": 76.48,
            "source": "market_cache",
        }

        crypto_quote = routes_public_market_live._resolve_cached_quote(
            {"BTCUSDT": crypto_legacy_alias, "BTCUSD": crypto_identity},
            "BTCUSD",
        )
        crypto_legacy_candidates = routes_public_market_live._matching_quote_candidates(
            {"BTCUSD": crypto_legacy_alias},
            "BTCUSD",
        )
        bdr_quote = routes_public_market_live._resolve_cached_quote(
            {"AAPL34.SA": bdr_legacy_alias, "AAPL34": bdr_identity},
            "AAPL34",
        )

        self.assertEqual(crypto_legacy_candidates, [])
        self.assertEqual(crypto_quote["asset_type"], "CRYPTO")
        self.assertEqual(crypto_quote["market"], "CRYPTO")
        self.assertTrue(crypto_quote["identity_preserved"])
        self.assertEqual(bdr_quote["asset_type"], "BDR")
        self.assertEqual(bdr_quote["market"], "B3")
        self.assertTrue(bdr_quote["identity_preserved"])

    def test_b3_future_reference_proxy_is_explicitly_not_exact_contract(self):
        reference = {
            "symbol": "^BVSP",
            "provider_symbol": "^BVSP",
            "price": 179000.0,
            "change": 120.0,
            "change_pct": 0.07,
        }

        with patch.object(market_data_loader, "_get_cached_price_payload", return_value=reference):
            payload = market_data_loader._reference_payload_for_b3_future("WINM26")

        self.assertEqual(payload["symbol"], "WINM26")
        self.assertEqual(payload["provider_symbol"], "^BVSP")
        self.assertEqual(payload["source"], "reference_proxy")
        self.assertEqual(payload["quote_status"], "reference")
        self.assertEqual(payload["reference_proxy_for"], "WINM26")
        self.assertFalse(payload["exact_contract"])
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["fallback_type"], "reference_proxy")
        self.assertEqual(payload["price_semantics"], "reference_proxy_not_exact_contract")
        self.assertTrue(market_data_loader._payload_matches_requested_symbol("WINM26", payload))

        wrong_reference = {**payload, "provider_symbol": "BRL=X", "reference_symbol": "BRL=X"}
        self.assertFalse(market_data_loader._payload_matches_requested_symbol("WINM26", wrong_reference))

    def test_public_batch_preserves_requested_items_invalid_ambiguous_and_duplicates(self):
        cached = {
            "PETR4": {
                "symbol": "PETR4",
                "requested_symbol": "PETR4",
                "canonical_symbol": "PETR4",
                "display_symbol": "PETR4",
                "provider_symbol": "PETR4.SA",
                "asset_type": "B3",
                "market": "B3",
                "currency": "BRL",
                "timezone": "America/Sao_Paulo",
                "identity_preserved": True,
                "price_semantics": "direct_market_price",
                "freshness_semantics": "provider_observation_or_cache_ttl",
                "price": 38.8,
                "volume": 10_000,
                "source": "market_cache",
            },
            "AAPL34": {
                "symbol": "AAPL34",
                "display_symbol": "AAPL34",
                "provider_symbol": "AAPL",
                "price": 210.0,
                "source": "proxy_market",
            },
        }

        with patch.object(routes_public_market_live, "cached_price_payloads", return_value=cached), patch.object(
            routes_public_market_live,
            "get_cached_quote_payload",
            return_value=None,
        ):
            payload = routes_public_market_live.public_quotes("PETR4,BTC,???,$$$,AAPL34,PETR4")

        self.assertEqual(payload["count"], 6)
        self.assertEqual([item["symbol"] for item in payload["items"]], ["PETR4", "BTC", "INVALID_SYMBOL", "INVALID_SYMBOL", "AAPL34", "PETR4"])
        self.assertEqual(payload["items"][0]["quote_status"], "valid")
        self.assertEqual(payload["items"][1]["quote_status"], "ambiguous_symbol")
        self.assertEqual(payload["items"][2]["quote_status"], "invalid_symbol")
        self.assertEqual(payload["items"][2]["requested_symbol"], "INVALID_SYMBOL")
        self.assertEqual(payload["items"][3]["quote_status"], "invalid_symbol")
        self.assertEqual(payload["items"][3]["requested_symbol"], "INVALID_SYMBOL")
        self.assertEqual(payload["items"][4]["quote_status"], "empty")
        self.assertIsNone(payload["items"][4]["price"])
        self.assertEqual(payload["items"][5]["price"], 38.8)

    def test_public_single_quote_marks_ambiguous_symbol_explicitly(self):
        payload = routes_public_market.public_quote("BTC")

        self.assertEqual(payload["symbol"], "BTC")
        self.assertEqual(payload["quote_status"], "ambiguous_symbol")
        self.assertEqual(classify_quote_payload(payload), "ambiguous_symbol")
        self.assertIsNone(payload["price"])

    def test_public_single_quote_rejects_bdr_proxy_cache_payload(self):
        proxy_payload = {
            "symbol": "AAPL34",
            "display_symbol": "AAPL34",
            "provider_symbol": "AAPL",
            "price": 210.0,
            "source": "proxy_market",
            "fallback_type": "foreign_underlying_context_only",
        }

        with patch.object(routes_public_market, "get_cached_quote_payload", return_value=proxy_payload):
            payload = routes_public_market.public_quote("AAPL34")

        self.assertEqual(payload["symbol"], "AAPL34")
        self.assertEqual(payload["source"], "empty")
        self.assertIsNone(payload["price"])

    def test_public_single_quote_blocks_configured_symbol_before_cache_lookup(self):
        # ENBR3 remains deliberately blocked; BRFS3/JBSS3 now alias to live
        # successors (MBRF3/JBSS32) and left the blocklist.
        cached_payload = {
            "symbol": "ENBR3",
            "display_symbol": "ENBR3",
            "provider_symbol": "ENBR3.SA",
            "price": 21.0,
            "source": "market_cache",
        }

        with patch.object(routes_public_market, "get_cached_quote_payload", return_value=cached_payload) as cached:
            payload = routes_public_market.public_quote("ENBR3")

        cached.assert_not_called()
        self.assertEqual(payload["symbol"], "ENBR3")
        self.assertEqual(payload["quote_status"], "blocked_symbol")
        self.assertIsNone(payload["price"])

    def test_public_single_quote_resolves_legacy_bdr_alias_before_cache_lookup(self):
        a1md_payload = {
            "symbol": "A1MD34",
            "requested_symbol": "A1MD34",
            "canonical_symbol": "A1MD34",
            "display_symbol": "A1MD34",
            "provider_symbol": "A1MD34.SA",
            "asset_type": "BDR",
            "market": "B3",
            "currency": "BRL",
            "timezone": "America/Sao_Paulo",
            "identity_preserved": True,
            "price_semantics": "direct_market_price",
            "freshness_semantics": "provider_observation_or_cache_ttl",
            "price": 52.3,
            "volume": 10_000,
            "source": "market_cache",
            "fallback": False,
            "fallback_type": None,
        }

        def cached_payload(alias):
            return a1md_payload if alias in {"A1MD34.SA", "A1MD34"} else None

        with patch.object(routes_public_market, "get_cached_quote_payload", side_effect=cached_payload) as cached:
            payload = routes_public_market.public_quote("AMD34")

        self.assertEqual(cached.call_args_list[0].args[0], "A1MD34")
        self.assertEqual(payload["symbol"], "A1MD34")
        self.assertEqual(payload["price"], 52.3)

    def test_public_quotes_metrics_do_not_count_invalid_items_as_cache_hits(self):
        with patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live,
            "record_cache_access",
        ) as record_cache:
            payload = routes_public_market_live.public_quotes("BTC,???")

        self.assertEqual([item["quote_status"] for item in payload["items"]], ["ambiguous_symbol", "invalid_symbol"])
        self.assertEqual([call.args[1] for call in record_cache.call_args_list], [False, False])

    def test_public_chart_preserves_invalid_and_ambiguous_status(self):
        ambiguous = routes_public_market_live.public_market_chart("BTC")
        invalid = routes_public_market_live.public_market_chart("???")

        self.assertEqual(ambiguous["status"], "ambiguous_symbol")
        self.assertEqual(ambiguous["summary"]["status"], "ambiguous_symbol")
        self.assertEqual(invalid["status"], "invalid_symbol")
        self.assertEqual(invalid["summary"]["status"], "invalid_symbol")

    def test_empty_quote_status_is_normalized_before_classification(self):
        payload = empty_quote_payload("BTC", quote_status=" ambiguous_symbol ", reason="missing_quote_asset")

        self.assertEqual(payload["quote_status"], "ambiguous_symbol")
        self.assertEqual(payload["source"], "ambiguous_symbol")
        self.assertEqual(classify_quote_payload(payload), "ambiguous_symbol")

    def test_invalid_bundle_does_not_call_news_or_ai_tools(self):
        with patch.object(
            routes_public_market_live,
            "build_public_news_payload",
            side_effect=AssertionError("invalid bundle must not call news"),
        ), patch.object(
            routes_public_market_live,
            "build_public_ai_tools_payload",
            side_effect=AssertionError("invalid bundle must not call ai tools"),
        ):
            payload = routes_public_market_live.public_market_bundle("???", interval="1D")

        self.assertEqual(payload["symbol"], "INVALID_SYMBOL")
        self.assertEqual(payload["quote"]["quote_status"], "invalid_symbol")
        self.assertEqual(payload["chart"]["status"], "invalid_symbol")
        self.assertEqual(payload["chart"]["summary"]["status"], "invalid_symbol")
        self.assertEqual(payload["news"]["items"], [])
        self.assertEqual(payload["ai_tools"]["tools"], {})
        self.assertIn("master_score", payload["insight"])
        self.assertIn("decision_envelope", payload["insight"])

    def test_stale_cache_is_never_reclassified_as_fresh(self):
        old_timestamp = time.time() - market_data_loader._PRICE_CACHE_TTL_SECONDS - 30
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._PRICE_SNAPSHOT_CACHE["AAPL"] = {
                "timestamp": old_timestamp,
                "payload": {
                    "symbol": "AAPL",
                    "display_symbol": "AAPL",
                    "requested_symbol": "AAPL",
                    "canonical_symbol": "AAPL",
                    "provider_symbol": "AAPL",
                    "asset_type": "USA",
                    "market": "USA",
                    "currency": "USD",
                    "timezone": "America/New_York",
                    "identity_preserved": True,
                    "price_semantics": "direct_market_price",
                    "freshness_semantics": "provider_observation_or_cache_ttl",
                    "price": 195.0,
                    "source": "market_cache",
                },
            }

        with patch.object(market_data_loader, "_load_price_cache_once", return_value=None):
            self.assertEqual(market_data_loader.get_cached_price_snapshots(["AAPL"]), {})
            stale = market_data_loader.get_cached_price_snapshots(["AAPL"], allow_stale=True)
        self.assertTrue(stale["AAPL"]["stale"])
        self.assertEqual(stale["AAPL"]["source"], "market_cache")
        self.assertEqual(stale["AAPL"]["cache_source"], "stale_market_cache")
        self.assertEqual(stale["AAPL"]["original_source"], "market_cache")
        self.assertGreater(stale["AAPL"]["cache_age_seconds"], market_data_loader._PRICE_CACHE_TTL_SECONDS)

    def test_fast_info_fails_closed_when_identity_contract_cannot_attach(self):
        class FakeYFinance:
            class Ticker:
                fast_info = {
                    "last_price": 195.0,
                    "previous_close": 190.0,
                    "last_volume": 1000,
                    "ten_day_average_volume": 2000,
                    "day_high": 196.0,
                    "day_low": 189.0,
                }
                info = {}

                def __init__(self, symbol):
                    self.symbol = symbol

        with patch.object(market_data_loader, "_network_provider_allowed", return_value=True), patch.object(
            market_data_loader, "_get_yfinance", return_value=FakeYFinance
        ), patch.object(market_data_loader, "_attach_identity_contract", return_value=None), patch.object(
            market_data_loader, "record_external_provider_call"
        ) as record_call:
            payload = market_data_loader._price_payload_from_fast_info("AAPL")

        self.assertIsNone(payload)
        self.assertTrue(market_data_loader._is_symbol_cooling_down("AAPL"))
        self.assertFalse(record_call.call_args.kwargs["success"])
        self.assertEqual(record_call.call_args.kwargs["error"], "identity_mismatch")

    def test_quote_warmup_covers_entire_public_watchlist(self):
        """Every watchlist (public universe) symbol must fit inside the warmup limit."""
        from app.market.universe_registry import PUBLIC_UNIVERSES
        from app.system.quote_warmup import DEFAULT_QUOTE_WARMUP_LIMIT, public_quote_symbols

        warmed = set(public_quote_symbols(DEFAULT_QUOTE_WARMUP_LIMIT))
        watchlist = {
            sanitize_market_symbol(symbol) or symbol
            for symbols in PUBLIC_UNIVERSES.values()
            for symbol in symbols
        }
        missing = sorted(watchlist - warmed)
        self.assertEqual(missing, [], f"watchlist symbols never warmed (always 'sem snapshot'): {missing}")


if __name__ == "__main__":
    unittest.main()
