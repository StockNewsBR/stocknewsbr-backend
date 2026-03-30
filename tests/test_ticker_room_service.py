import tempfile
import unittest
from pathlib import Path

from app.services import ticker_room_service


class TickerRoomServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_path = ticker_room_service.ROOM_STORE_PATH
        ticker_room_service.ROOM_STORE_PATH = Path(self.tempdir.name) / "ticker_rooms.json"

    def tearDown(self):
        ticker_room_service.ROOM_STORE_PATH = self.original_path
        self.tempdir.cleanup()

    def test_appends_and_lists_messages_with_image(self):
        message = ticker_room_service.append_room_message(
            "petr4",
            user_id=10,
            user_name="Trader 10",
            text="Compra interessante com suporte.",
            image_url="/media/posts/teste.png",
        )
        items = ticker_room_service.list_room_messages("PETR4", limit=10)

        self.assertIsNotNone(message)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["image_url"], "/media/posts/teste.png")
        self.assertEqual(items[0]["symbol"], "PETR4")


if __name__ == "__main__":
    unittest.main()
