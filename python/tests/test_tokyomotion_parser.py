# -*- coding: utf-8 -*-
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from python.image_crawler import TokyoMotionCrawler


SAMPLE_HTML = """
<html>
  <head>
    <meta property="og:title" content="配達ファック" />
    <meta property="og:image" content="https://cdn.tokyo-motion.net/media/videos/tmb205/6578364/default.jpg" />
    <meta property="video:tag" content="露出" />
    <meta property="video:tag" content="delivery" />
    <title>配達ファック - TOKYO Motion</title>
  </head>
  <body>
    <video id="vjsplayer" poster="https://cdn.tokyo-motion.net/media/videos/tmb205/6578364/default.jpg" controls>
      <source src="https://www.tokyomotion.net/vsrc/sd/test-token" default title="SD" type="video/mp4" />
      <source src="https://www.tokyomotion.net/vsrc/hd/test-token" title="HD" type="video/mp4" />
    </video>
  </body>
</html>
"""

FALLBACK_HTML = """
<html>
  <head>
    <title>サンプル動画 - TOKYO Motion</title>
  </head>
  <body>
    <video poster="https://cdn.tokyo-motion.net/media/videos/tmb205/7000000/default.jpg" controls>
      <source src="https://www.tokyomotion.net/vsrc/sd/fallback-token" type="video/mp4" />
    </video>
  </body>
</html>
"""


class TokyoMotionCrawlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_video_prefers_hd_source_and_og_title(self):
        crawler = TokyoMotionCrawler()
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await crawler.parse_video("https://www.tokyomotion.net/video/6578364/sample")

        self.assertEqual(result["title"], "配達ファック")
        self.assertEqual(result["video_url"], "https://www.tokyomotion.net/vsrc/hd/test-token")
        self.assertEqual(result["cover"], "https://cdn.tokyo-motion.net/media/videos/tmb205/6578364/default.jpg")
        self.assertIn("露出", result["tags"])
        self.assertIsNone(result["m3u8_url"])
        self.assertEqual(result["actresses"], [])

    async def test_parse_video_falls_back_to_title_tag_and_first_source(self):
        crawler = TokyoMotionCrawler()
        mock_resp = MagicMock()
        mock_resp.text = FALLBACK_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await crawler.parse_video("https://www.tokyomotion.net/video/7000000/sample")

        self.assertEqual(result["title"], "サンプル動画")
        self.assertEqual(result["video_url"], "https://www.tokyomotion.net/vsrc/sd/fallback-token")
        self.assertEqual(result["cover"], "https://cdn.tokyo-motion.net/media/videos/tmb205/7000000/default.jpg")


if __name__ == "__main__":
    unittest.main()
