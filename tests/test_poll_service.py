import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from app.services import poll_service
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class PollServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_path = poll_service.POLL_STORE_PATH
        poll_service.POLL_STORE_PATH = Path(self.temp_dir) / "weekly_polls.json"

    def tearDown(self):
        poll_service.POLL_STORE_PATH = self.original_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_stock_poll(self):
        poll = poll_service.ensure_weekly_poll("PETR4")

        self.assertEqual(poll["symbol"], "PETR4")
        self.assertEqual(len(poll["options"]), 2)
        self.assertTrue(poll["question"])

    def test_vote_replaces_previous_vote(self):
        poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")
        poll = poll_service.vote_poll("BTCUSDT", "A", user_id=10)
        poll = poll_service.vote_poll("BTCUSDT", "B", user_id=10)

        option_a = next(item for item in poll["options"] if item["key"] == "A")
        option_b = next(item for item in poll["options"] if item["key"] == "B")

        self.assertEqual(option_a["votes"], 0)
        self.assertEqual(option_b["votes"], 1)


if __name__ == "__main__":
    unittest.main()
