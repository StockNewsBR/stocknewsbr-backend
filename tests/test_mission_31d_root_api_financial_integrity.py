import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import UniqueConstraint, create_engine, inspect, text

from app import dependencies
from app.api import routes_public_market_live
from app.cache import paper_trading_cache as paper_cache_module
from app.cache.paper_trading_cache import PaperTradingCache
from app.database_schema import ensure_runtime_schema
from app.models import SubscriptionAuditLog
from app.services.access_service import log_subscription_event
from app.services.score_display import attach_master_score_display_contract, normalize_master_score_display
from app.system.paper_trading import update_paper_trading_from_snapshot


def _paper_row(**overrides):
    row = {
        "symbol": "PETR4",
        "trade_action": "BUY",
        "decision_ready": True,
        "operational_status": "READY",
        "data_quality": "cached",
        "price": 37.5,
        "volume": 1_000_000,
    }
    row.update(overrides)
    return row


class Mission31DRootApiFinancialIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.original_internal_token = dependencies.INTERNAL_API_TOKEN
        self.tmp = tempfile.TemporaryDirectory()
        self.original_paper_cache = paper_cache_module.paper_trading_cache
        paper_cache_module.paper_trading_cache = PaperTradingCache(Path(self.tmp.name) / "paper_trading.json")

    def tearDown(self):
        dependencies.INTERNAL_API_TOKEN = self.original_internal_token
        paper_cache_module.paper_trading_cache = self.original_paper_cache
        self.tmp.cleanup()

    def test_internal_api_token_fails_closed_when_absent_empty_or_placeholder(self):
        for token in (
            "",
            "   ",
            "short-valid-looking-token",
            "token-com-caractere-ç-que-deveria-falhar",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            dependencies._normalize_internal_api_token("change_this_internal_token"),
            dependencies._normalize_internal_api_token("<defina-um-token-interno-forte-fora-do-repositorio>"),
        ):
            with self.subTest(token=repr(token)):
                dependencies.INTERNAL_API_TOKEN = token
                with self.assertRaises(HTTPException) as context:
                    dependencies.require_internal_token()

                self.assertEqual(context.exception.status_code, 503)
                self.assertEqual(context.exception.detail, "internal_token_not_configured")

    def test_internal_api_token_rejects_missing_or_bad_header_and_accepts_exact_match(self):
        dependencies.INTERNAL_API_TOKEN = "mission31d-internal-token-valid-20260630"

        for supplied in (None, "", "wrong-token", "token-invalido-ç"):
            with self.subTest(supplied=repr(supplied)):
                with self.assertRaises(HTTPException) as context:
                    dependencies.require_internal_token(supplied)

                self.assertEqual(context.exception.status_code, 403)
                self.assertEqual(context.exception.detail, "internal_access_required")

        self.assertTrue(dependencies.require_internal_token("mission31d-internal-token-valid-20260630"))

    def test_internal_api_token_header_contract_uses_x_internal_token(self):
        dependencies.INTERNAL_API_TOKEN = "mission31d-internal-token-valid-20260630"
        app = FastAPI()

        @app.get("/internal/probe", dependencies=[Depends(dependencies.require_internal_token)])
        def probe():
            return {"ok": True}

        client = TestClient(app)

        self.assertEqual(
            client.get(
                "/internal/probe",
                headers={"X-Internal-Token": "mission31d-internal-token-valid-20260630"},
            ).status_code,
            200,
        )
        self.assertEqual(client.get("/internal/probe").status_code, 403)
        self.assertEqual(
            client.get(
                "/internal/probe",
                headers={"Authorization": "mission31d-internal-token-valid-20260630"},
            ).status_code,
            403,
        )

    def test_log_subscription_event_preserves_positional_signature_compatibility(self):
        class _Db:
            def __init__(self):
                self.event = None

            def add(self, event):
                self.event = event

        db = _Db()
        event = log_subscription_event(
            db,
            None,
            "stripe",
            "invoice.payment_succeeded",
            "premium_br_monthly",
            "website",
            "sub_31d",
            "active",
            '{"safe":true}',
        )

        self.assertIs(db.event, event)
        self.assertEqual(event.product_id, "premium_br_monthly")
        self.assertEqual(event.origin, "website")
        self.assertEqual(event.external_subscription_id, "sub_31d")
        self.assertEqual(event.status, "active")
        self.assertEqual(event.payload_excerpt, '{"safe":true}')
        self.assertIsNone(event.provider_event_id)

    def test_public_master_score_contract_preserves_raw_0_100_and_display_0_10(self):
        expected = {
            0.0: 0.0,
            50.0: 5.0,
            85.0: 8.5,
            99.9: 10.0,
            100.0: 10.0,
        }

        for raw, display in expected.items():
            with self.subTest(raw=raw):
                payload = attach_master_score_display_contract({"master_score_raw": raw})

                self.assertEqual(payload["master_score_raw"], raw)
                self.assertEqual(payload["master_score"], display)
                self.assertEqual(payload["master_score_display"], display)
                self.assertEqual(payload["master_score_source_scale"], "0_100")

        self.assertEqual(normalize_master_score_display(None, source_scale="0_100"), (0.0, "master_score_display_invalid"))

    def test_public_master_score_contract_preserves_explicit_0_10_source_scale(self):
        payload = attach_master_score_display_contract(
            {"master_score": 8.5, "master_score_source_scale": "0_10"}
        )

        self.assertEqual(payload["master_score"], 8.5)
        self.assertEqual(payload["master_score_display"], 8.5)
        self.assertNotIn("master_score_raw", payload)
        self.assertEqual(payload["master_score_source_scale"], "0_10")

    def test_paper_trading_uses_utc_epoch_for_aware_and_naive_snapshot_timestamps(self):
        cases = (
            ("aware", "2026-06-30T12:00:00+00:00"),
            ("zulu", "2026-06-30T12:00:00Z"),
            ("naive", "2026-06-30T12:00:00"),
        )
        expected_timestamp = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc).timestamp()

        for label, generated_at in cases:
            with self.subTest(label=label):
                paper_cache_module.paper_trading_cache.reset()
                state = update_paper_trading_from_snapshot(
                    {"generated_at": generated_at, "signals": [_paper_row(symbol=label.upper())]},
                    now=1_000.0,
                )

                self.assertEqual(state["positions"][0]["source_snapshot_timestamp"], expected_timestamp)
                self.assertEqual(state["last_update_timestamp"], 1_000.0)

    def test_paper_trading_keeps_conservative_now_fallback_for_invalid_timestamp(self):
        state = update_paper_trading_from_snapshot(
            {"generated_at": "not-a-timestamp", "signals": [_paper_row()]},
            now=1_234.0,
        )

        self.assertEqual(state["positions"][0]["source_snapshot_timestamp"], 1_234.0)

    def test_paper_trading_checks_next_timestamp_field_after_invalid_generated_at(self):
        state = update_paper_trading_from_snapshot(
            {
                "generated_at": "not-a-timestamp",
                "updated_at": "2026-06-30T12:00:00Z",
                "signals": [_paper_row()],
            },
            now=1_234.0,
        )

        self.assertEqual(
            state["positions"][0]["source_snapshot_timestamp"],
            datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc).timestamp(),
        )

    def test_public_quotes_sanitize_non_finite_numbers_before_json_response(self):
        unsafe_quotes = [
            {
                "symbol": "PETR4",
                "price": float("nan"),
                "change": float("inf"),
                "nested": {"low": float("-inf"), "high": 37.9},
            },
            {
                "symbol": "VALE3",
                "price": 62.1,
                "change": -0.2,
                "nested": {"low": 61.9, "high": float("inf")},
            },
        ]
        quote_iter = iter(unsafe_quotes)

        with patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live,
            "_resolve_cached_quote",
            side_effect=lambda *_args, **_kwargs: next(quote_iter),
        ):
            payload = routes_public_market_live.public_quotes("PETR4,VALE3")

        self.assertEqual(payload["count"], 2)
        self.assertIsNone(payload["items"][0]["price"])
        self.assertIsNone(payload["items"][0]["change"])
        self.assertIsNone(payload["items"][0]["nested"]["low"])
        self.assertEqual(payload["items"][0]["nested"]["high"], 37.9)
        self.assertEqual(payload["items"][1]["price"], 62.1)
        self.assertEqual(payload["items"][1]["change"], -0.2)
        self.assertEqual(payload["items"][1]["nested"]["low"], 61.9)
        self.assertIsNone(payload["items"][1]["nested"]["high"])

    def test_snapshot_master_context_sanitizes_non_finite_numbers(self):
        snapshot_row = {
            "symbol": "PETR4",
            "master_score": 8.0,
            "master_score_source_scale": "0_10",
            "radar_priority_score": float("nan"),
            "ranking_opportunity_score": float("inf"),
            "final_decision_score": float("-inf"),
            "strategic_panel": {"risk": float("inf"), "support": 36.5},
        }

        with patch.object(routes_public_market_live, "get_snapshot_ticker", return_value=snapshot_row):
            payload = routes_public_market_live._snapshot_master_context("PETR4")

        self.assertIsNone(payload["radar_priority_score"])
        self.assertIsNone(payload["ranking_opportunity_score"])
        self.assertIsNone(payload["final_decision_score"])
        self.assertIsNone(payload["strategic_panel"]["risk"])
        self.assertEqual(payload["strategic_panel"]["support"], 36.5)

    def test_snapshot_master_context_falls_back_to_full_strategic_panel_index(self):
        panel = {
            "ticker": "PETR4",
            "master_score": 78.0,
            "why": [{"tool": "flow", "label": "Comprador"}],
        }

        with patch.object(
            routes_public_market_live,
            "get_snapshot_ticker",
            return_value={"ticker": "PETR4", "strategic_panel": {}},
        ), patch.object(
            routes_public_market_live,
            "get_snapshot",
            return_value={"strategic_panels": [panel]},
        ):
            payload = routes_public_market_live._snapshot_master_context("PETR4.SA")

        self.assertEqual(payload["master_score"], 7.8)
        self.assertEqual(payload["strategic_panel"]["why"][0]["tool"], "flow")

    def test_public_insight_chart_and_bundle_sanitize_non_finite_numbers(self):
        chart_rows = [
            {
                "time": "2026-06-30T12:00:00Z",
                "open": 37.0,
                "high": 38.0,
                "low": 36.5,
                "close": float("inf"),
            }
        ]
        chart_signal = {
            "score": float("nan"),
            "rsi": float("inf"),
            "trend_bias": "alta",
            "signal": "BUY",
            "summary": {"confidence": float("-inf")},
        }
        overlays = {
            "series": [{"value": float("inf")}],
            "markers": [{"price": float("nan")}],
            "zones": [{"low": float("-inf"), "high": 38.0}],
            "summary": {"score": float("nan")},
        }

        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=chart_rows), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value=chart_signal,
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value=overlays,
        ), patch.object(
            routes_public_market_live,
            "_snapshot_master_context",
            return_value={"radar_priority_score": float("inf")},
        ), patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live,
            "_resolve_cached_quote",
            return_value={"symbol": "PETR4", "price": float("nan")},
        ), patch.object(routes_public_market_live, "record_cache_access"), patch.object(
            routes_public_market_live,
            "build_public_news_payload",
            return_value={"items": [{"score": float("inf")}]},
        ), patch.object(
            routes_public_market_live,
            "build_public_ai_tools_payload",
            return_value={"tools": [{"confidence": float("-inf")}]},
        ):
            insight = routes_public_market_live.public_market_insight("PETR4")
            chart = routes_public_market_live.public_market_chart("PETR4")
            bundle = routes_public_market_live.public_market_bundle("PETR4")

        self.assertIsNone(insight["score"])
        self.assertIsNone(insight["rsi"])
        self.assertIsNone(insight["summary"]["confidence"])
        self.assertIsNone(insight["radar_priority_score"])
        self.assertIsNone(chart["ohlc"][0]["close"])
        self.assertIsNone(chart["series"][0]["value"])
        self.assertIsNone(chart["markers"][0]["price"])
        self.assertIsNone(chart["zones"][0]["low"])
        self.assertIsNone(chart["summary"]["score"])
        self.assertIsNone(bundle["quote"]["price"])
        self.assertIsNone(bundle["news"]["items"][0]["score"])
        self.assertIsNone(bundle["ai_tools"]["tools"][0]["confidence"])

    def test_runtime_schema_guarantees_stripe_provider_event_id_unique_index(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        provider VARCHAR NOT NULL,
                        provider_event_id VARCHAR,
                        event_type VARCHAR NOT NULL,
                        payload_excerpt TEXT
                    )
                    """
                )
            )

        ensure_runtime_schema(engine)
        columns = {column["name"] for column in inspect(engine).get_columns("subscription_audit_logs")}
        indexes = {index["name"] for index in inspect(engine).get_indexes("subscription_audit_logs")}

        self.assertIn("provider_event_id", columns)
        self.assertIn("uq_subscription_audit_provider_event", indexes)

    def test_subscription_audit_model_enforces_unique_constraint(self):
        table = SubscriptionAuditLog.__table__

        self.assertIn("provider_event_id", table.c)
        self.assertTrue(table.c.provider_event_id.nullable)
        self.assertTrue(
            any(
                isinstance(constraint, UniqueConstraint)
                and set(constraint.columns.keys()) == {"provider", "provider_event_id"}
                for constraint in table.constraints
            )
        )


if __name__ == "__main__":
    unittest.main()
