import unittest
from unittest.mock import patch

from app.services import workspace_service
from app.ai.ai_specialists import OFFICIAL_AI_TOOL_KEYS


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
            "flow": [
                {
                    "ticker": "PETR4",
                    "name": "Petrobras",
                    "tool": "flow",
                    "score": 84.0,
                    "signal": "WATCH",
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
            "liquidity": [],
            "trend": [],
            "momentum": [],
            "smart_money": [],
            "risk": [],
            "news": [],
            "macro": [],
            "regime": [],
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
            "ai_modules": ["Flow IA", "Risk IA"],
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
            return_value={"tabs": ["home", "flow", "risk"], "pinned_ticker": "PETR4", "opened_popouts": []},
        ), patch.object(
            workspace_service,
            "get_layout",
            return_value={
                "tabs": [
                    {"id": "home", "title": "Home"},
                    {"id": "flow", "title": "Flow IA"},
                    {"id": "risk", "title": "Risk IA"},
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

    def test_workspace_data_does_not_restore_ai_history_when_snapshot_ai_tools_missing(self):
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
            "ai_modules": ["Flow IA", "Risk IA"],
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
            return_value={"tabs": ["home", "flow", "risk"], "pinned_ticker": "PETR4", "opened_popouts": []},
        ), patch.object(
            workspace_service,
            "get_layout",
            return_value={
                "tabs": [
                    {"id": "home", "title": "Home"},
                    {"id": "flow", "title": "Flow IA"},
                    {"id": "risk", "title": "Risk IA"},
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
                    "flow": [
                        {
                            "ticker": "PETR4",
                            "tool": "flow",
                            "score": 84.0,
                            "signal": "WATCH",
                            "price": 37.5,
                            "volume": 1250000,
                            "data_quality": "priced",
                        }
                    ],
                    "liquidity": [],
                    "trend": [],
                    "momentum": [],
                    "smart_money": [],
                    "risk": [],
                    "news": [],
                    "macro": [],
                    "regime": [],
                }
            },
            create=True,
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
            sorted(OFFICIAL_AI_TOOL_KEYS),
        )
        self.assertFalse(payload["ai_tools"]["flow"])
        self.assertFalse(payload["ai_tools"]["risk"])
        self.assertIn("market_decision", payload)
        self.assertFalse(payload["market_decision"].get("decision_ready"))

    def test_workspace_data_does_not_restore_non_operational_ai_history(self):
        bootstrap = {
            "brand": "StockNewsBR",
            "pricing": {"trial_days": 90, "premium_monthly": {"price_brl": 49}},
            "launch_roadmap": {"current": "web", "next": "app"},
            "ai_modules": ["Risk IA"],
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
            return_value={"signals": [], "ai_tools": workspace_service._empty_ai_outputs()},
        ), patch.object(
            workspace_service,
            "get_ranking",
            return_value=[],
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
            return_value={},
        ), patch.object(
            workspace_service,
            "get_push_status",
            return_value={},
        ), patch.object(
            workspace_service,
            "get_user_workspace_layout",
            return_value={"tabs": ["home"], "pinned_ticker": "PETR4", "opened_popouts": []},
        ), patch.object(
            workspace_service,
            "get_layout",
            return_value={"tabs": [{"id": "home", "title": "Home"}]},
        ), patch.object(
            workspace_service,
            "list_room_messages",
            return_value=[],
        ), patch.object(
            workspace_service,
            "get_ai_alert_history_snapshot",
            return_value={
                "tools": {
                    "flow": [],
                    "liquidity": [],
                    "trend": [],
                    "momentum": [],
                    "smart_money": [],
                    "risk": [
                        {
                            "ticker": "PETR4",
                            "tool": "risk",
                            "score": 91.0,
                            "signal": "WATCH",
                            "price": 0,
                            "volume": 0,
                            "data_quality": "score_only",
                            "decision_ready": False,
                        }
                    ],
                    "news": [],
                    "macro": [],
                    "regime": [],
                }
            },
            create=True,
        ), patch.object(
            workspace_service,
            "persist_ai_alert_history",
            side_effect=lambda value: value,
        ):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertFalse(payload["ai_tools"]["risk"])

    def test_workspace_cards_and_ranking_prefer_snapshot_rows(self):
        snapshot_rows = [
            {
                "ticker": "PETR4",
                "symbol": "PETR4",
                "score": 88.0,
                "price": 37.5,
                "change_pct": 1.6,
                "volume": 1_250_000,
                "avg_volume": 800_000,
                "rel_volume": 1.56,
                "vwap": 37.2,
                "rsi": 58.0,
                "macd": 0.12,
                "data_quality": "priced",
            }
        ]
        stale_ranking = [
            {
                "symbol": "PETR4",
                "score": 12.0,
                "price": 1.11,
                "change_pct": -9.0,
                "volume": 1,
                "rsi": 1.0,
            }
        ]
        snapshot_ai_tools = {
            "flow": [],
            "liquidity": [],
            "trend": [],
            "momentum": [],
            "smart_money": [],
            "risk": [
                {
                    "ticker": "PETR4",
                    "tool": "risk",
                    "score": 88.0,
                    "signal": "WATCH",
                    "price": 37.5,
                    "volume": 1_250_000,
                    "rsi": 58.0,
                    "data_quality": "priced",
                }
            ],
        }

        bootstrap = {
            "brand": "StockNewsBR",
            "pricing": {"trial_days": 90, "premium_monthly": {"price_brl": 49}},
            "launch_roadmap": {"current": "web", "next": "app"},
            "ai_modules": ["Risk IA"],
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
            return_value=stale_ranking,
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
            return_value={},
        ), patch.object(
            workspace_service,
            "get_push_status",
            return_value={},
        ), patch.object(
            workspace_service,
            "get_user_workspace_layout",
            return_value={"tabs": ["home"], "pinned_ticker": "PETR4", "opened_popouts": []},
        ), patch.object(
            workspace_service,
            "get_layout",
            return_value={"tabs": [{"id": "home", "title": "Home"}]},
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
            side_effect=AssertionError("workspace should not rebuild AI tools in HTTP request"),
            create=True,
        ):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertEqual(payload["top_signals"][0]["price"], 37.5)
        self.assertEqual(payload["ranking"][0]["price"], 37.5)
        self.assertEqual(payload["ranking"][0]["rsi"], 58.0)
        self.assertNotEqual(payload["ranking"][0]["price"], 1.11)


if __name__ == "__main__":
    unittest.main()
