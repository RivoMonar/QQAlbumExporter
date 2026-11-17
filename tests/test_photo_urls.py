import unittest
from unittest.mock import patch

import qqzone_downloader as downloader


class PhotoUrlTests(unittest.TestCase):
    def test_photo_url_fallback(self):
        cases = [
            ({"origin_url": 1, "raw": 1, "origin": 1,
              "url": "https://example.com/photo.jpg"},
             "https://example.com/photo.jpg"),
            ({"origin_url": True, "raw": {"flag": 1}, "origin": [1],
              "url": 2, "picUrl": "https://example.com/fallback.jpg"},
             "https://example.com/fallback.jpg"),
            ({"origin_url": "https://example.com/original.jpg",
              "url": "https://example.com/preview.jpg"},
             "https://example.com/original.jpg"),
            ({"origin_url": "  ", "url": " example.com/photo.jpg "},
             "https://example.com/photo.jpg"),
            ({"url": "//example.com/photo.jpg"}, "https://example.com/photo.jpg"),
            ({"url": "http://example.com/photo.jpg"}, "http://example.com/photo.jpg"),
            ({"origin_url": 1, "raw": True, "origin": None}, ""),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                response = {"data": {"photoList": [{"id": "photo1", **fields}]}}
                with patch.object(downloader, "api_get", return_value=response), \
                     patch.object(downloader.time, "sleep"):
                    photos = downloader.list_photos("user", "user", "album", 0, "", silent=True)
                self.assertEqual(len(photos), 1)
                self.assertEqual(photos[0]["url"], expected)


if __name__ == "__main__":
    unittest.main()
