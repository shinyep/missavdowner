import unittest
from unittest.mock import AsyncMock

from python.image_crawler import ImageGalleryCrawler


PAGE_1_HTML = """
<html>
  <head>
    <title>JVID Yanyan Catching Bugs Photo Set 147P - JVID - Page 1 - Love the girl</title>
    <meta property="og:title" content="JVID Yanyan Catching Bugs Photo Set 147P - JVID - Love the girl" />
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "ImageGallery", "name": "JVID Yanyan Catching Bugs Photo Set 147P", "numberOfItems": 3, "pagination": {"@type": "Pagination", "currentPage": 1, "totalPages": 2}, "itemListElement": [
      {"@type": "ImageObject", "position": 1, "contentUrl": "https://xx.knit.bid/static/images/2022/04/07/img-001.jpg"},
      {"@type": "ImageObject", "position": 2, "contentUrl": "https://xx.knit.bid/static/images/2022/04/07/img-002.jpg"}
    ]}
    </script>
  </head>
  <body>
    <article>
      <div class="article-content">
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


class XxKnitBidParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_gallery_collects_images_from_jsonld_and_pagination(self):
        crawler = ImageGalleryCrawler()

        async def fake_load_page_html(gallery_url: str, page_url: str) -> str:
            if '/page/2/' in page_url:
                return PAGE_2_HTML
            return PAGE_1_HTML

        crawler._load_page_html = AsyncMock(side_effect=fake_load_page_html)

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


if __name__ == "__main__":
    unittest.main()
