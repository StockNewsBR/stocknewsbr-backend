import tempfile
import unittest
from pathlib import Path

from app.services import video_library_service


class VideoLibraryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_manifest = video_library_service.VIDEO_MANIFEST_PATH
        self.original_output_dir = video_library_service.VIDEO_OUTPUT_DIR
        video_library_service.VIDEO_MANIFEST_PATH = Path(self.tempdir.name) / "help_videos.json"
        video_library_service.VIDEO_OUTPUT_DIR = Path(self.tempdir.name) / "help-videos"
        video_library_service.VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        video_library_service.VIDEO_MANIFEST_PATH = self.original_manifest
        video_library_service.VIDEO_OUTPUT_DIR = self.original_output_dir
        self.tempdir.cleanup()

    def test_marks_video_as_available_when_file_exists(self):
        target = video_library_service.VIDEO_OUTPUT_DIR / "heat-map.mp4"
        target.write_bytes(b"")

        entry = video_library_service.get_help_video_entry("heat-map")

        self.assertTrue(entry["video_ready"])
        self.assertEqual(entry["status"], "available")
        self.assertEqual(entry["public_url"], "/media/help-videos/heat-map.mp4")

    def test_library_reports_planned_when_files_are_missing(self):
        payload = video_library_service.get_help_video_library()

        self.assertGreaterEqual(payload["status"]["planned_videos"], 1)
        self.assertFalse(payload["status"]["mp4_recordings_ready"])


if __name__ == "__main__":
    unittest.main()
