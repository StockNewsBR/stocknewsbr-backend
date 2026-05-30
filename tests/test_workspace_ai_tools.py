import unittest
from unittest.mock import patch

from app.services import workspace_service


class WorkspaceAiToolsTests(unittest.TestCase):
    def test_workspace_data_uses_snapshot_ai_tools_when_available(self):
        snapshot_rows = [
            {
                "ticker": "PETR4",
                "price": 37.5,
                "prev_close": 36.9,
                "open": 37.0,
                "high": 38.1,
                "low": 36.8,
                "vwap": 37.2,
                "volume": 1_250_000,
                "avg_volume": 800_000,
                "rsi": 58.0,
                "adx": 24.0,
                "atr_pct": 1.9,
                "bb_width": 0.03,
                "kc_width": 0.05,
                "momentum": 1.2,
                "change_pct": 1.6,
            }
        ]
        snapshot_ai_tools = {
            "heat_map": [],
            "radar": [],
            "breakout_probability": [],
            "institutional_flow": [
                {
                    "ticker": "PETR4",
                    "name": "Petrobras",
                    "tool": "institutional_flow",
                    "score": 84.0,
                    "signal": "BUY",
                    "state": "institutional_buying",
                    "confidence": 92,
                    "price": 37.5,
                    "change_pct": 1.6,
                    "volume": 1250000,
                    "rel_volume": 1.56,
                    "vwap": 37.2,
                    "rsi": 58.0,
                    "adx": 24.0,
                    "atr_pct": 1.9,
                    "metrics": {"institutional_bias": 84.0},
                    "ai_comment": "Fluxo institucional forte.",
                    "trigger": "Continuação acima da VWAP.",
                    "invalidation": "Perda da VWAP.",
                    "updated_at": "2026-04-06T10:00:00+00:00",
                }
            ],
            "smart_money": [],
            "accumulation": [],
            "volatility_squeeze": [],
            "liquidity_sweep": [],
            "liquidity_map": [],
            "market_regime": [],
            "master_score": [],
        }
        ranking_rows = [
            {
                "symbol": "PETR4",
                "score": 88.0,
                "trend": "Alta",
                "price": 37.5,
            }
        ]
        bootstrap = {
            "brand": "StockNewsBR",
            "pricing": {"trial_days": 90, "premium_monthly": {"price_brl": 49}},
            "launch_roadmap": {"current": "web", "next": "app"},
            "ai_modules": ["IA Institutional Flow", "IA Master Score"],
            "social_features": {"feed": True},
        }
        metrics = {
            "engine_cycles": 10,
            "signals_generated": 5,
            "assets_scanned": 80,
            "cache_age": 3,
            "http_requests": 100,
            "ws_connections": 2,
            "chat_messages": 8,
        }

        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service,
            "get_metrics_snapshot",
            return_value=metrics,
        ), patch.object(
            workspace_service,
            "get_snapshot",
            return_value={"signals": snapshot_rows, "ai_tools": snapshot_ai_tools},
        ), patch.object(
            workspace_service,
            "get_ranking",
            return_value=ranking_rows,
        ), patch.object(
            workspace_service,
            "get_posts",
            return_value=[],
        ), patch.object(
            workspace_service,
            "get_help_center_blueprint",
            return_value={"guides": []},
        ), patch.object(
            workspace_service,
            "get_media_status",
            return_value={"provider": "local", "cdn_ready": False},
        ), patch.object(
            workspace_service,
            "get_push_status",
            return_value={"android_ready": False, "apple_ready": False},
        ), patch.object(
            workspace_service,
            "get_user_workspace_layout",
            return_value={"tabs": ["home", "institutional-flow", "master-score"], "pinned_ticker": "PETR4", "opened_popouts": []},
        ), patch.object(
            workspace_service,
            "get_layout",
            return_value={
                "tabs": [
                    {"id": "home", "title": "Home"},
                    {"id": "institutional-flow", "title": "Institutional Flow"},
                    {"id": "volatility-squeeze", "title": "Squeeze"},
                    {"id": "accumulation", "title": "Accumulation"},
                    {"id": "liquidity-map", "title": "Liquidity Map"},
                    {"id": "master-score", "title": "Master Score"},
                ]
            },
        ), patch.object(
            workspace_service,
            "list_room_messages",
            return_value=[],
        ), patch.object(
            workspace_service,
            "persist_ai_alert_history",
            side_effect=lambda value: value,
        ), patch.object(
            workspace_service,
            "build_ai_tool_payload",
            side_effect=AssertionError("workspace should reuse ai_tools from snapshot"),
            create=True,
        ):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertIn("ai_tools", payload)
        self.assertEqual(payload["ai_tools"], snapshot_ai_tools)
        self.assertEqual(payload["status"]["snapshot_signals"], 1)
        self.assertIn("market_decision", payload)

    def test_workspace_data_uses_ai_history_when_snapshot_ai_tools_missing(self):
        snapshot_rows = [
            {
                "ticker": "PETR4",
                "price": 37.5,
                "prev_close": 36.9,
                "open": 37.0,
                "high": 38.1,
                "low": 36.8,
                "vwap": 37.2,
                "volume": 1_250_000,
                "avg_volume": 800_000,
                "rsi": 58.0,
                "adx": 24.0,
                "atr_pct": 1.9,
                "bb_width": 0.03,
                "kc_width": 0.05,
                "momentum": 1.2,
                "change_pct": 1.6,
            }
        ]
        ranking_rows = [
            {
                "symbol": "PETR4",
                "score": 88.0,
                "trend": "Alta",
                "price": 37.5,
            }
        ]
        bootstrap = {
            "brand": "StockNewsBR",
            "pricing": {"trial_days": 90, "premium_monthly": {"price_brl": 49}},
            "launch_roadmap": {"current": "web", "next": "app"},
            "ai_modules": ["IA Institutional Flow", "IA Master Score"],
            "social_features": {"feed": True},
        }
        metrics = {
            "engine_cycles": 10,
            "signals_generated": 5,
            "assets_scanned": 80,
            "cache_age": 3,
            "http_requests": 100,
            "ws_connections": 2,
            "chat_messages": 8,
        }

        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service,
            "get_metrics_snapshot",
            return_value=metrics,
        ), patch.object(
            workspace_service,
            "get_snapshot",
            return_value={"signals": snapshot_rows},
        ), patch.object(
            workspace_service,
            "get_ranking",
            return_value=ranking_rows,
        ), patch.object(
            workspace_service,
            "get_posts",
            return_value=[],
        ), patch.object(
            workspace_service,
            "get_help_center_blueprint",
            return_value={"guides": []},
        ), patch.object(
            workspace_service,
            "get_media_status",
            return_value={"provider": "local", "cdn_ready": False},
        ), patch.object(
            workspace_service,
            "get_push_status",
            return_value={"android_ready": False, "apple_ready": False},
        ), patch.object(
            workspace_service,
            "get_user_workspace_layout",
            return_value={"tabs": ["home", "institutional-flow", "master-score"], "pinned_ticker": "PETR4", "opened_popouts": []},
        ), patch.object(
            workspace_service,
            "get_layout",
            return_value={
                "tabs": [
                    {"id": "home", "title": "Home"},
                    {"id": "institutional-flow", "title": "Institutional Flow"},
                    {"id": "volatility-squeeze", "title": "Squeeze"},
                    {"id": "accumulation", "title": "Accumulation"},
                    {"id": "liquidity-map", "title": "Liquidity Map"},
                    {"id": "master-score", "title": "Master Score"},
                ]
            },
        ), patch.object(
            workspace_service,
            "list_room_messages",
            return_value=[],
        ), patch.object(
            workspace_service,
            "get_ai_alert_history_snapshot",
            return_value={
                "tools": {
                    "heat_map": [],
                    "radar": [],
                    "breakout_probability": [],
                    "institutional_flow": [
                        {
                            "ticker": "PETR4",
                            "tool": "institutional_flow",
                            "score": 84.0,
                            "signal": "BUY",
                            "price": 37.5,
                            "volume": 1250000,
                            "data_quality": "priced",
                        }
                    ],
                    "smart_money": [],
                    "accumulation": [],
                    "volatility_squeeze": [],
                    "liquidity_sweep": [],
                    "liquidity_map": [],
                    "market_regime": [],
                    "master_score": [
                        {
                            "ticker": "PETR4",
                            "tool": "master_score",
                            "score": 88.0,
                            "signal": "BUY",
                            "price": 37.5,
                            "volume": 1250000,
                            "data_quality": "priced",
                        }
                    ],
                }
            },
        ), patch.object(
            workspace_service,
            "persist_ai_alert_history",
            side_effect=lambda value: value,
        ), patch.object(
            workspace_service,
            "build_ai_tool_payload",
            side_effect=AssertionError("workspace should not rebuild AI tools in HTTP request"),
            create=True,
        ):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertIn("ai_tools", payload)
        self.assertEqual(
            sorted(payload["ai_tools"].keys()),
            [
                "accumulation",
                "breakout_probability",
                "heat_map",
                "institutional_flow",
                "liquidity_map",
                "liquidity_sweep",
                "market_regime",
                "master_score",
                "radar",
                "smart_money",
                "volatility_squeeze",
            ],
        )
        self.assertTrue(payload["ai_tools"]["institutional_flow"])
        self.assertTrue(payload["ai_tools"]["master_score"])
        self.assertIn("market_decision", payload)
        self.assertFalse(payload["market_decision"].get("decision_ready"))

        flow_row = payload["ai_tools"]["institutional_flow"][0]
        master_row = payload["ai_tools"]["master_score"][0]

        self.assertEqual(flow_row["ticker"], "PETR4")
        self.assertEqual(flow_row["tool"], "institutional_flow")

        self.assertEqual(master_row["ticker"], "PETR4")
        self.assertEqual(master_row["tool"], "master_score")


if __name__ == "__main__":
    unittest.main()
