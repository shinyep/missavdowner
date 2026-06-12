import unittest
from unittest.mock import AsyncMock

from python.image_crawler import ImageGalleryCrawler


ARTICLE_IMAGES = "\n".join(
    f'        <img src="https://goddess247.com/wp-content/uploads/2026/03/ROSI-{index:04d}.jpg" />'
    for index in range(68)
)

EXPECTED_IMAGE_URLS = [
    f"https://goddess247.com/wp-content/uploads/2026/03/ROSI-{index:04d}.jpg"
    for index in range(68)
]

SAMPLE_HTML = f"""
<html>
  <head>
    <meta property="og:title" content="ROSI写真 2025.10.31 No.5079 (68P)" />
    <title>ROSI写真 2025.10.31 No.5079 (68P) - Goddess247</title>
  </head>
  <body>
    <header>
      <h1>Goddess247</h1>
      <span class="elementor-heading-title">Goddess247</span>
    </header>
    <article>
      <h1>ROSI写真 2025.10.31 No.5079 (68P)</h1>
      <div class="elementor-widget-theme-post-content">
{ARTICLE_IMAGES}
      </div>
      <section class="related-posts">
        <img src="https://i1.wp.com/goddess247.com/wp-content/uploads/2026/03/OTHER-0000.jpg?w=1920&ssl=1" />
      </section>
    </article>
  </body>
</html>
"""


class Goddess247ParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_gallery_only_collects_article_images(self):
        crawler = ImageGalleryCrawler()
        crawler._load_page_html = AsyncMock(return_value=SAMPLE_HTML)

        result = await crawler.parse_gallery(
            "https://goddess247.com/rosi%e5%86%99%e7%9c%9f-2025-10-31-no-5079-68p/"
        )

        self.assertEqual(result.title, "ROSI写真 2025.10.31 No.5079 (68P)")
        self.assertEqual(len(result.image_urls), 68)
        self.assertEqual(result.image_urls, EXPECTED_IMAGE_URLS)
        self.assertEqual(result.image_urls[0], EXPECTED_IMAGE_URLS[0])
        self.assertNotIn("OTHER-0000.jpg", "".join(result.image_urls))

    async def test_parse_gallery_prefers_article_title_over_site_heading(self):
        crawler = ImageGalleryCrawler()
        crawler._load_page_html = AsyncMock(return_value=SAMPLE_HTML)

        result = await crawler.parse_gallery(
            "https://goddess247.com/rosi%e5%86%99%e7%9c%9f-2025-10-31-no-5079-68p/"
        )

        self.assertEqual(result.title, "ROSI写真 2025.10.31 No.5079 (68P)")

    async def test_parse_gallery_prefers_og_title_when_global_h1_is_site_name(self):
        crawler = ImageGalleryCrawler()
        crawler._load_page_html = AsyncMock(
            return_value=SAMPLE_HTML.replace(
                "<article>\n      <h1>ROSI写真 2025.10.31 No.5079 (68P)</h1>",
                "<article>",
            )
        )

        result = await crawler.parse_gallery(
            "https://goddess247.com/rosi%e5%86%99%e7%9c%9f-2025-10-31-no-5079-68p/"
        )

        self.assertEqual(result.title, "ROSI写真 2025.10.31 No.5079 (68P)")


if __name__ == "__main__":
    unittest.main()
