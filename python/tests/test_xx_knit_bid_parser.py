# -*- coding: utf-8 -*-
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.image_crawler import ImageGalleryCrawler
from python.novel_import import import_images_to_novel


PAGE_1_HTML = """
<html>
  <head>
    <title>JVID Yanyan Catching Bugs Photo Set 147P - JVID - Page 1 - Love the girl</title>
    <meta property="og:title" content="JVID Yanyan Catching Bugs Photo Set 147P - JVID - Love the girl" />
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "ImageGallery", "name": "JVID Yanyan Catching Bugs Photo Set 147P", "contentUrl": "https://media.knit.bid/play/test-gallery-video.m3u8", "numberOfItems": 3, "pagination": {"@type": "Pagination", "currentPage": 1, "totalPages": 2}, "itemListElement": [
      {"@type": "ImageObject", "position": 1, "contentUrl": "https://xx.knit.bid/static/images/2022/04/07/img-001.jpg"},
      {"@type": "ImageObject", "position": 2, "contentUrl": "https://xx.knit.bid/static/images/2022/04/07/img-002.jpg"}
    ]}
    </script>
  </head>
  <body>
    <article>
      <div class="article-content">
        <div class="article-video-block">
          <video id="player-1" controls>
            <source src="https://media.knit.bid/play/test-gallery-video.m3u8" type="application/vnd.apple.mpegurl" />
          </video>
        </div>
        <img data-src="https://xx.knit.bid/static/images/2022/04/07/img-001.jpg" src="https://xx.knit.bid/static/images/2022/04/07/img-001.jpg" />
        <img data-src="https://xx.knit.bid/static/images/2022/04/07/img-002.jpg" src="https://xx.knit.bid/static/images/2022/04/07/img-002.jpg" />
      </div>
    </article>
  </body>
</html>
"""

PAGE_2_HTML = """
<html>
  <head>
    <title>JVID Yanyan Catching Bugs Photo Set 147P - JVID - Page 2 - Love the girl</title>
  </head>
  <body>
    <article>
      <div class="article-content">
        <img data-src="https://xx.knit.bid/static/images/2022/04/07/img-003.jpg" src="https://xx.knit.bid/static/images/2022/04/07/img-003.jpg" />
      </div>
    </article>
  </body>
</html>
"""


def _make_fake_response(url: str):
    """构造模拟的 httpx.Response 对象。"""
    text = PAGE_2_HTML if '/page/2/' in url else PAGE_1_HTML
    response = MagicMock()
    response.text = text
    response.raise_for_status = MagicMock()
    return response


class XxKnitBidParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_gallery_collects_images_from_jsonld_and_pagination(self):
        crawler = ImageGalleryCrawler()

        fake_get = AsyncMock(side_effect=_make_fake_response)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = fake_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await crawler.parse_gallery("https://xx.knit.bid/en/article/19586/")

        self.assertEqual(result.title, "JVID Yanyan Catching Bugs Photo Set 147P")
        self.assertEqual(
            result.image_urls,
            [
                "https://xx.knit.bid/static/images/2022/04/07/img-001.jpg",
                "https://xx.knit.bid/static/images/2022/04/07/img-002.jpg",
                "https://xx.knit.bid/static/images/2022/04/07/img-003.jpg",
            ],
        )
        self.assertEqual(result.video_url, "https://media.knit.bid/play/test-gallery-video.m3u8")


class NovelImportHelpersTests(unittest.TestCase):
    def test_import_images_script_deduplicates_normalized_source_names(self):
        """回归测试：同一张图被重复导入时，应按源文件名归一化去重。"""
        image_paths = [
            r"F:\novel\img\gallery_images\1900\1900_001.jpg",
            r"F:\novel\img\gallery_images\1900\1900_002.jpg",
            r"F:\novel\img\gallery_images\1900\1900_003.jpg",
        ]

        with patch("python.novel_import.os.path.exists", return_value=True), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="GALLERY_ID:1900\nIMAGES_CREATED:0\n",
                stderr="",
            )

            result = import_images_to_novel(
                r"F:\novel",
                "阿薰 - 天台 82P1V - 阿薰 - 爱妹子",
                image_paths,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["gallery_id"], 1900)
        self.assertEqual(result["image_count"], 0)
        script = mock_run.call_args.args[0][2]
        self.assertIn("def normalize_source_name(name: str) -> str:", script)
        self.assertIn("source_name = normalize_source_name(path.name)", script)
        self.assertIn("existing_source_names.add(normalized.lower())", script)


if __name__ == "__main__":
    unittest.main()
