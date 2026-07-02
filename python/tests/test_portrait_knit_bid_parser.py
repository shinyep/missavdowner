# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "python"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PYTHON_ROOT))

from python.image_crawler import ImageGalleryCrawler


PAGE_1_HTML = """
<html>
  <head>
    <title>[MyGirl美媛馆]Vol.634_模特糯美子写真68P</title>
    <meta name="og:title" content="[MyGirl美媛馆]Vol.634_模特糯美子写真68P" />
    <meta name="twitter:title" content="错误兜底标题" />
  </head>
  <body>
    <div class="page-content">
      <div class="container">
        <h1>[MyGirl美媛馆]第634期糯美子写真</h1>
        <p>正文说明。</p>
        <img class="img-fluid w-100 lazy mb-2" src="/static/images/loading.gif" data-src="/static/uploadfile/2022/08/10/001.jpg" />
        <img class="img-fluid w-100 lazy mb-2" src="/static/images/loading.gif" data-src="https://portrait.knit.bid/static/uploadfile/2022/08/10/002.jpg" />
        <nav aria-label="pagination">
          <ul class="pagination">
            <li class="page-item active"><a class="page-link">1</a></li>
            <li class="page-item"><a href="javascript:gotoPage(2);" class="page-link">2</a></li>
          </ul>
        </nav>
        <div class="row text-center">
          <h2 class="text-divider"><span>相关推荐</span></h2>
        </div>
        <div class="row row-cols-2 row-cols-md-5 g-4 my-3">
          <img class="card-img-top lazy" data-src="/static/uploadfile/2020/11/06/recommend.jpg" />
        </div>
      </div>
    </div>
  </body>
</html>
"""


PAGE_2_HTML = """
<html>
  <head>
    <title>[MyGirl美媛馆]Vol.634_模特糯美子写真68P</title>
  </head>
  <body>
    <div class="page-content">
      <div class="container">
        <img class="img-fluid w-100 lazy mb-2" src="/static/images/loading.gif" data-src="/static/uploadfile/2022/08/10/003.jpg" />
        <img class="img-fluid w-100 lazy mb-2" src="/static/images/loading.gif" data-src="/static/uploadfile/2022/08/10/004.jpg" />
      </div>
    </div>
  </body>
</html>
"""


NO_PAGINATION_HTML = """
<html>
  <head>
    <meta property="og:title" content="[XiuRen秀人网]No.1000_测试写真3P" />
  </head>
  <body>
    <div class="page-content">
      <div class="container">
        <img class="img-fluid w-100 lazy mb-2" data-src="/static/uploadfile/2024/01/01/a.jpg" />
        <img class="card-img-top lazy" data-src="/static/uploadfile/2024/01/01/recommend.jpg" />
      </div>
    </div>
  </body>
</html>
"""


def _make_fake_response(url: str):
    response = MagicMock()
    response.text = PAGE_2_HTML if "page=2" in url else PAGE_1_HTML
    response.raise_for_status = MagicMock()
    return response


class PortraitKnitBidParserTests(unittest.IsolatedAsyncioTestCase):
    def test_client_options_rejects_unavailable_local_proxy(self):
        crawler = ImageGalleryCrawler(proxy="http://127.0.0.1:7890")

        with patch("socket.create_connection", side_effect=OSError("refused")) as mock_connect:
            with self.assertRaisesRegex(RuntimeError, "代理不可用"):
                crawler._client_options({"User-Agent": "test"})

        parsed = urlparse("http://127.0.0.1:7890")
        mock_connect.assert_called_once_with((parsed.hostname, parsed.port), timeout=1.0)

    def test_network_connection_error_is_human_readable(self):
        crawler = ImageGalleryCrawler()

        error = crawler._format_connection_error(httpx.ConnectError("All connection attempts failed"))

        self.assertIn("连接失败", error)
        self.assertIn("代理设置", error)
        self.assertNotIn("All connection attempts failed", error)

    async def test_parse_gallery_collects_body_images_across_gotopage_pagination(self):
        crawler = ImageGalleryCrawler()
        fake_get = AsyncMock(side_effect=_make_fake_response)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = fake_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await crawler.parse_gallery("https://portrait.knit.bid/mygirl/11184")

        self.assertEqual(result.title, "[MyGirl美媛馆]Vol.634_模特糯美子写真68P")
        self.assertEqual(
            result.image_urls,
            [
                "https://portrait.knit.bid/static/uploadfile/2022/08/10/001.jpg",
                "https://portrait.knit.bid/static/uploadfile/2022/08/10/002.jpg",
                "https://portrait.knit.bid/static/uploadfile/2022/08/10/003.jpg",
                "https://portrait.knit.bid/static/uploadfile/2022/08/10/004.jpg",
            ],
        )
        self.assertEqual(result.video_url, "")
        fetched_urls = [call.args[0] for call in fake_get.call_args_list]
        self.assertIn("https://portrait.knit.bid/mygirl/11184?page=2", fetched_urls)

    async def test_parse_gallery_without_pagination_ignores_recommendation_cards(self):
        crawler = ImageGalleryCrawler()
        response = MagicMock()
        response.text = NO_PAGINATION_HTML
        response.raise_for_status = MagicMock()

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=response)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=fake_client):
            result = await crawler.parse_gallery("https://portrait.knit.bid/xiuren/1000")

        self.assertEqual(result.title, "[XiuRen秀人网]No.1000_测试写真3P")
        self.assertEqual(
            result.image_urls,
            ["https://portrait.knit.bid/static/uploadfile/2024/01/01/a.jpg"],
        )

    def test_is_portrait_knit_bid_url(self):
        self.assertTrue(ImageGalleryCrawler._is_portrait_knit_bid_url("https://portrait.knit.bid/mygirl/11184"))
        self.assertFalse(ImageGalleryCrawler._is_portrait_knit_bid_url("https://xx.knit.bid/article/11184/"))
        self.assertFalse(ImageGalleryCrawler._is_portrait_knit_bid_url("https://example.com/mygirl/11184"))


if __name__ == "__main__":
    unittest.main()
