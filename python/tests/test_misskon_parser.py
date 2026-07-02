import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "python"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PYTHON_ROOT))

from python.image_crawler import ImageGalleryCrawler


PAGE_1_HTML = """
<html>
  <head>
    <title>[MZSOCK爱美足] No.371: 雨萌 (102 photos + 1 video) - MissKon.com</title>
    <script type="application/ld+json">
    {"@context":"http://schema.org","@type":"Article","headline":"[MZSOCK爱美足] No.371: 雨萌 (102 photos + 1 video)","name":"[MZSOCK爱美足] No.371: 雨萌 (102 photos + 1 video)"}
    </script>
  </head>
  <body>
    <article id="the-post" class="post-listing">
      <div class="post-inner">
        <h1 class="name post-title entry-title"><span itemprop="name">[MZSOCK爱美足] No.371: 雨萌 (102 photos + 1 video)</span></h1>
        <div class="entry">
          <div class="page-link">
            <span class="post-page-numbers current">1</span>
            <a href="https://misskon.com/110569-mzsock-ai-mei-zu-no371-yu-meng-102-photos-1-video/2/">2</a>
          </div>
          <img class="lazy" src="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%201%201'%3E%3C/svg%3E" data-src="https://tez.misskon.com/uploads/2026/06/12/test-001.webp" alt="test-001" />
          <img class="lazy" src="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%201%201'%3E%3C/svg%3E" data-src="https://tez.misskon.com/uploads/2026/06/12/test-002.webp" alt="test-002" />
        </div>
      </div>
    </article>
    <header class="site-header">
      <img class="lazy" src="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%201%201'%3E%3C/svg%3E" data-src="https://misskon.com/img/logo.2026.v5.png" alt="MissKon.com" />
    </header>
    <div class="yarpp-related">
      <img src="https://misskon.com/media/related-001.webp" alt="related" />
    </div>
  </body>
</html>
"""

PAGE_2_HTML = """
<html>
  <head>
    <title>[MZSOCK爱美足] No.371: 雨萌 (102 photos + 1 video) - Page 2 - MissKon.com</title>
  </head>
  <body>
    <article id="the-post" class="post-listing">
      <div class="post-inner">
        <div class="entry">
          <div class="page-link">
            <a href="https://misskon.com/110569-mzsock-ai-mei-zu-no371-yu-meng-102-photos-1-video/">1</a>
            <span class="post-page-numbers current">2</span>
          </div>
          <img class="lazy" src="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%201%201'%3E%3C/svg%3E" data-src="https://tez.misskon.com/uploads/2026/06/12/test-003.webp" alt="test-003" />
        </div>
      </div>
    </article>
  </body>
</html>
"""


def _make_fake_response(url: str):
    text = PAGE_2_HTML if url.rstrip("/").endswith("/2") else PAGE_1_HTML
    response = MagicMock()
    response.text = text
    response.raise_for_status = MagicMock()
    return response


class MissKonParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_gallery_collects_entry_images_across_post_pages(self):
        crawler = ImageGalleryCrawler()
        fake_get = AsyncMock(side_effect=_make_fake_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = fake_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await crawler.parse_gallery(
                "https://misskon.com/110569-mzsock-ai-mei-zu-no371-yu-meng-102-photos-1-video/"
            )

        self.assertEqual(result.title, "[MZSOCK爱美足] No.371: 雨萌 (102 photos + 1 video)")
        self.assertEqual(
            result.image_urls,
            [
                "https://tez.misskon.com/uploads/2026/06/12/test-001.webp",
                "https://tez.misskon.com/uploads/2026/06/12/test-002.webp",
                "https://tez.misskon.com/uploads/2026/06/12/test-003.webp",
            ],
        )
        self.assertEqual(result.video_url, "")


if __name__ == "__main__":
    unittest.main()
