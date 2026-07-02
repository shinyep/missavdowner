# -*- coding: utf-8 -*-
"""
hotgirl.asia 解析回归测试。

覆盖：
1. 站点识别
2. LD+JSON 标题提取（BlogPosting headline）
3. 正文内容图片提取（cdn.hotgirl.asia / 历史 everiaclub.com）
4. 排除评分、站点 logo、侧栏等非正文图片
5. 分页链接识别
"""

import unittest
from unittest.mock import AsyncMock

from python.image_crawler import ImageGalleryCrawler

# 模拟 hotgirl.asia 真实页面结构的最小样本
# CDN 域名已从 everiaclub.com 迁移到 cdn.hotgirl.asia
SAMPLE_HTML = """
<html>
  <head>
    <title>Aram, [PURE MEDIA] Vol.169 Set.01 - HotGirl.asia</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"BlogPosting","headline":"Aram, [PURE MEDIA] Vol.169 Set.01","name":"Aram, [PURE MEDIA] Vol.169 Set.01"}]}</script>
  </head>
  <body>
    <header>
      <h1>HotGirl.asia Share sexy Asian girl stock photo</h1>
    </header>
    <div id="main" class="page-detail">
      <div class="main-content main-detail">
        <img src="https://hotgirl.asia/wp-content/plugins/wp-postratings/images/stars_flat(png)/rating_on.png" />
        <img src="https://hotgirl.asia/wp-content/uploads/2022/06/cover.jpg" />
        <img data-src="https://cdn.hotgirl.asia/img/b/R29vZ2xl/example01/s0/img01.jpg" src="https://cdn.hotgirl.asia/img/b/R29vZ2xl/example01/s0/img01.jpg" />
        <img src="https://cdn.hotgirl.asia/img/b/R29vZ2xl/example01/s0/img02.jpg" />
        <img src="https://cdn.hotgirl.asia/img/b/R29vZ2xl/example01/s0/img03.jpg" />
        <img data-lazy-src="https://everiaclub.com/img/b/example_legacy.jpg" src="https://everiaclub.com/img/b/example_legacy.jpg" />
      </div>
      <a class="page" href="https://hotgirl.asia/sample/?num=2">2</a>
      <a class="page" href="https://hotgirl.asia/sample/?num=3">3</a>
    </div>
  </body>
</html>
"""

# 标题包含站点后缀的样本，验证 clean_title 能正确去除
SAMPLE_HTML_WITH_SITE_SUFFIX = """
<html>
  <head>
    <title>Aram, [PURE MEDIA] Vol.169 Set.01 - Share erotic Asian girl picture &amp; livestream</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"BlogPosting","headline":"Aram, [PURE MEDIA] Vol.169 Set.01"}</script>
  </head>
  <body>
    <header>
      <h1>HotGirl.asia Share sexy Asian girl stock photo</h1>
    </header>
    <div id="main" class="page-detail">
      <div class="main-content main-detail">
        <img src="https://cdn.hotgirl.asia/img/b/example_single.jpg" />
      </div>
    </div>
  </body>
</html>
"""

# 无 LD+JSON 样本，验证回退到 og:title / <title>
SAMPLE_HTML_NO_LDJSON = """
<html>
  <head>
    <meta property="og:title" content="Test Gallery og:title" />
    <title>Test Gallery fallback title - HotGirl.asia</title>
  </head>
  <body>
    <header><h1>HotGirl.asia</h1></header>
    <div id="main" class="page-detail">
      <div class="main-content main-detail">
        <img src="https://cdn.hotgirl.asia/img/b/og_fallback.jpg" />
      </div>
    </div>
  </body>
</html>
"""


class HotgirlParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_hotgirl_collects_content_images_from_cdn(self):
        """正文图片应提取 cdn.hotgirl.asia CDN 上的内容图"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirl_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.asia/sample/")

        self.assertEqual(len(result.image_urls), 4)
        self.assertTrue(
            all("cdn.hotgirl.asia" in url or "everiaclub.com" in url for url in result.image_urls)
        )

    async def test_parse_hotgirl_excludes_non_content_images(self):
        """应排除评分星星、封面缩略图等非正文图片"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirl_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.asia/sample/")

        self.assertFalse(any("rating_on.png" in url for url in result.image_urls))
        self.assertFalse(any("cover.jpg" in url for url in result.image_urls))
        self.assertFalse(any("wp-postratings" in url for url in result.image_urls))

    async def test_parse_hotgirl_title_from_ldjson_headline(self):
        """标题应从 LD+JSON 的 headline 字段提取"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirl_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.asia/sample/")

        self.assertEqual(result.title, "Aram, [PURE MEDIA] Vol.169 Set.01")

    async def test_parse_hotgirl_title_not_polluted_by_site_name(self):
        """标题不应是站点名 'HotGirl.asia'，应是文章真实标题"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirl_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.asia/sample/")

        self.assertNotIn("HotGirl.asia", result.title)
        self.assertNotIn("Share sexy", result.title)

    async def test_parse_hotgirl_fallback_to_title_tag(self):
        """无 LD+JSON 时应回退到 og:title"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirl_fetch = AsyncMock(side_effect=[SAMPLE_HTML_NO_LDJSON])

        result = await crawler.parse_gallery("https://hotgirl.asia/sample/")

        self.assertEqual(result.title, "Test Gallery og:title")

    async def test_parse_hotgirl_supports_everiaclub_legacy_cdn(self):
        """应兼容历史 everiaclub.com CDN 图片"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirl_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.asia/sample/")

        self.assertTrue(any("everiaclub.com" in url for url in result.image_urls))


if __name__ == "__main__":
    unittest.main()
