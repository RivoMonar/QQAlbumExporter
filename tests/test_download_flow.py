import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app as gui
import qqzone_downloader as downloader


class DownloadFlowTests(unittest.TestCase):
    def test_numeric_photo_ids_and_missing_names_complete_download(self):
        response = {"data": {"photoList": [
            {"id": 123456789, "name": "", "origin": 1,
             "url": "https://example.com/a.jpg"},
            {"id": 234567890, "name": None, "lloc": 987654,
             "url": "https://example.com/b.jpg", "is_video": True},
            {"id": 345678901, "name": 42,
             "url": "https://example.com/c.jpg"},
        ]}}

        def fake_download(url, path):
            Path(path).write_bytes(b"test image")
            return True

        old_state = gui.DOWNLOAD_STATE
        try:
            with tempfile.TemporaryDirectory() as output, \
                 patch.dict(gui.app.config, {
                     "ALBUMS": [(1, {"id": "album", "name": "test", "photo_count": 3})],
                     "UIN": "test_user", "OUTPUT_DIR": output,
                 }), \
                 patch.object(gui, "COOKIE_FILE", str(Path(output) / "absent_cookie")), \
                 patch.object(downloader, "api_get", return_value=response), \
                 patch.object(downloader, "download_file", side_effect=fake_download), \
                 patch.object(downloader.time, "sleep"):
                # Capture the background entry point, then run it with real pool workers.
                with patch.object(gui.threading, "Thread") as thread:
                    result = gui.app.test_client().post("/api/download/start", json={})
                    self.assertTrue(result.get_json()["ok"])
                    run = thread.call_args.kwargs["target"]
                run()
                self.assertTrue(gui.DOWNLOAD_STATE["finished"])
                self.assertFalse(gui.DOWNLOAD_STATE["running"])
                self.assertEqual(gui.DOWNLOAD_STATE["success"], 3)
                self.assertEqual(gui.DOWNLOAD_STATE["failed"], 0)
                manifests = list(Path(output).rglob(".manifest.json"))
                self.assertEqual(len(manifests), 1)
                manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
                self.assertEqual(len(manifest), 3)
                self.assertIn("987654", manifest)
                for relative in manifest.values():
                    self.assertTrue((manifests[0].parent / relative).is_file())
                # Existing downloads must still be recognized on the next run.
                gui.DOWNLOAD_STATE.update(running=True, finished=False, success=0, done=0)
                run()
                self.assertEqual(gui.DOWNLOAD_STATE["success"], 0)
                self.assertTrue(gui.DOWNLOAD_STATE["finished"])
                self.assertEqual(downloader.download_file.call_count, 3)
        finally:
            gui.DOWNLOAD_STATE = old_state

    def test_id_fallback_and_manifest_key(self):
        for fields, expected in [
            ({"id": 123}, "123"), ({"id": 0}, "0"),
            ({"id": None, "lloc": 456}, "456"),
            ({"id": "", "lloc": "abcdefghijklmnopqr"}, "abcdefghijklmnop"),
        ]:
            with self.subTest(fields=fields), \
                 patch.object(downloader, "api_get", return_value={"data": {"photoList": [fields]}}), \
                 patch.object(downloader.time, "sleep"):
                photo = downloader.list_photos("u", "u", "a", 0, "", silent=True)[0]
                self.assertEqual(photo["id"], expected)
        self.assertEqual(gui.get_photo_key({"id": 123}), "123")
        self.assertEqual(gui.get_photo_key({"lloc": "existing-key", "id": 123}), "existing-key")


if __name__ == "__main__":
    unittest.main()
