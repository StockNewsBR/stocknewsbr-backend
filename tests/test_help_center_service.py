import unittest

try:
    from app.services.help_center_service import get_help_center_blueprint, get_help_guide
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class HelpCenterServiceTests(unittest.TestCase):
    def test_help_guides_have_demo_urls(self):
        blueprint = get_help_center_blueprint()

        self.assertTrue(blueprint["guides"])
        self.assertTrue(blueprint["guides"][0]["demo_video_url"])

    def test_can_find_known_guide(self):
        guide = get_help_guide("grafico")

        self.assertIsNotNone(guide)
        self.assertEqual(guide["slug"], "grafico")


if __name__ == "__main__":
    unittest.main()
