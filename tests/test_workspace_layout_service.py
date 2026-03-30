import tempfile
import unittest
from pathlib import Path

from app.services import workspace_layout_service


class WorkspaceLayoutServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_path = workspace_layout_service.LAYOUT_STORE_PATH
        workspace_layout_service.LAYOUT_STORE_PATH = Path(self.tempdir.name) / "workspace_layouts.json"

    def tearDown(self):
        workspace_layout_service.LAYOUT_STORE_PATH = self.original_path
        self.tempdir.cleanup()

    def test_saves_valid_tab_order_and_filters_invalid_values(self):
        layout = workspace_layout_service.save_user_workspace_layout(
            7,
            {
                "tabs": ["grafico", "home", "grafico", "nao-existe"],
                "pinned_ticker": "vale3",
                "opened_popouts": ["grafico", "nao-existe"],
            },
        )

        self.assertEqual(layout["tabs"], ["grafico", "home"])
        self.assertEqual(layout["pinned_ticker"], "VALE3")
        self.assertEqual(layout["opened_popouts"], ["grafico"])

    def test_returns_default_layout_when_user_has_no_saved_state(self):
        layout = workspace_layout_service.get_user_workspace_layout(999)

        self.assertIn("home", layout["tabs"])
        self.assertEqual(layout["pinned_ticker"], "PETR4")


if __name__ == "__main__":
    unittest.main()
