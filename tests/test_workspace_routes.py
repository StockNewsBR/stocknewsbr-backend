import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.web import routes_workspace


class WorkspaceRoutesTests(unittest.TestCase):
    def test_workspace_ticker_bundle_degrades_sections_independently(self):
        user = SimpleNamespace(id=7, plan="premium")

        with patch.object(
            routes_workspace,
            "get_cached_quote_payload",
            return_value={"symbol": "PETR4", "price": 37.5, "volume": 1000},
        ), patch.object(
            routes_workspace,
            "build_workspace_chart_payload",
            side_effect=RuntimeError("chart failed"),
        ), patch.object(
            routes_workspace,
            "ticker_feed",
            side_effect=RuntimeError("feed failed"),
        ), patch.object(
            routes_workspace,
            "build_public_news_payload",
            side_effect=RuntimeError("news failed"),
        ), patch.object(
            routes_workspace,
            "list_room_messages",
            side_effect=RuntimeError("room failed"),
        ), patch.object(
            routes_workspace.logger,
            "warning",
        ):
            payload = routes_workspace.workspace_ticker_bundle("PETR4", current_user=user)

        self.assertEqual(payload["symbol"], "PETR4")
        self.assertEqual(payload["chart"], {})
        self.assertEqual(payload["feed"]["items"], [])
        self.assertEqual(payload["news"]["count"], 0)
        self.assertEqual(payload["room"]["items"], [])
        self.assertEqual(payload["quote"]["price"], 37.5)


if __name__ == "__main__":
    unittest.main()
