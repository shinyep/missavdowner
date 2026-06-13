import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from python.image_crawler import GalleryParseResult, ImageGalleryCrawler


class GalleryDownloadRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="gallery_retry_test_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("python.image_crawler.asyncio.sleep", new=AsyncMock())
    async def test_download_gallery_retries_single_failed_image_until_success(self):
        crawler = ImageGalleryCrawler()
        crawler.parse_gallery = AsyncMock(
            return_value=GalleryParseResult(
                title="retry-success",
                page_url="https://example.com/gallery/1",
                image_urls=["https://cdn.example.com/001.jpg"],
            )
        )

        attempts = {"count": 0}

        async def fake_download_image(_client, _image_url, _referer):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary network error")
            return b"fake-image-bytes"

        crawler._download_image = fake_download_image
        crawler._detect_extension = lambda _url, _bytes: ".jpg"

        progress_events = []

        result = await crawler.download_gallery(
            "https://example.com/gallery/1",
            str(self.temp_dir),
            lambda progress, speed, phase, detail, extra: progress_events.append(
                {
                    "progress": progress,
                    "speed": speed,
                    "phase": phase,
                    "detail": detail,
                    "extra": extra,
                }
            ),
        )

        self.assertEqual(attempts["count"], 3)
        self.assertEqual(result["image_count"], 1)
        self.assertEqual(len(result["image_paths"]), 1)
        self.assertTrue(Path(result["image_paths"][0]).exists())
        self.assertEqual(progress_events[-1]["extra"]["success_count"], 1)
        self.assertEqual(progress_events[-1]["extra"]["failed_count"], 0)

    @patch("python.image_crawler.asyncio.sleep", new=AsyncMock())
    async def test_download_gallery_marks_image_failed_after_retry_limit(self):
        crawler = ImageGalleryCrawler()
        crawler.parse_gallery = AsyncMock(
            return_value=GalleryParseResult(
                title="retry-failed",
                page_url="https://example.com/gallery/2",
                image_urls=["https://cdn.example.com/002.jpg"],
            )
        )

        attempts = {"count": 0}
        progress_events = []

        async def fake_download_image(_client, _image_url, _referer):
            attempts["count"] += 1
            raise RuntimeError("permanent failure")

        crawler._download_image = fake_download_image

        with self.assertRaises(RuntimeError) as context:
            await crawler.download_gallery(
                "https://example.com/gallery/2",
                str(self.temp_dir),
                lambda progress, speed, phase, detail, extra: progress_events.append(
                    {
                        "progress": progress,
                        "speed": speed,
                        "phase": phase,
                        "detail": detail,
                        "extra": extra,
                    }
                ),
            )

        self.assertEqual(str(context.exception), "\u56fe\u7247\u4e0b\u8f7d\u5168\u90e8\u5931\u8d25")
        self.assertEqual(attempts["count"], 3)
        self.assertGreaterEqual(len(progress_events), 2)
        final_event = progress_events[-1]
        self.assertEqual(final_event["phase"], "downloading")
        self.assertIn("下载失败", final_event["detail"])
        self.assertNotIn("?", final_event["detail"])
        self.assertEqual(final_event["speed"], "0.00 张/秒")


if __name__ == "__main__":
    unittest.main()
