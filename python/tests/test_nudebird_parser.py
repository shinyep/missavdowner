# -*- coding: utf-8 -*-
"""nudebird.biz 专用解析回归测试。

验证 nudebird.biz 走独立解析路径，只从 .entry-content 提取正文图片，
不抓取 header logo（Screenshot-8-1-1.png）。
"""

import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from python.image_crawler import ImageGalleryCrawler

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_HTML = (FIXTURE_DIR / "nudebird_sample.html").read_text(encoding="utf-8")


class NudebirdParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_nudebird_collects_content_images(self):
        """正文图片应从 .entry-content 的 src 提取，跳过 base64 占位图"""
        crawler = ImageGalleryCrawler()
        crawler._nudebird_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://nudebird.biz/sample/")

        self.assertEqual(
            result.image_urls,
            [
                "https://nudebird.biz/wp-content/uploads/2026/06/17-1781612108.webp",
                "https://nudebird.biz/wp-content/uploads/2026/06/1-1781612111.webp",
                "https://nudebird.biz/wp-content/uploads/2026/06/2-1781612112.webp",
            ],
        )

    async def test_parse_nudebird_excludes_header_logo(self):
        """header 中的 logo（Screenshot-8-1-1.png）不应被收入结果"""
        crawler = ImageGalleryCrawler()
        crawler._nudebird_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://nudebird.biz/sample/")

        self.assertTrue(all("Screenshot-8-1-1" not in url for url in result.image_urls))
        self.assertTrue(all("2021/02" not in url for url in result.image_urls))

    async def test_parse_nudebird_title_from_h1(self):
        """标题应从 h1 提取，不带站点后缀"""
        crawler = ImageGalleryCrawler()
        crawler._nudebird_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://nudebird.biz/sample/")

        self.assertEqual(result.title, "[AI Enhanced] DJAWA Photo: HENDOONG")

    async def test_is_nudebird_url(self):
        """nudebird.biz 应走独立解析路径"""
        self.assertTrue(ImageGalleryCrawler._is_nudebird_url("https://nudebird.biz/sample/"))
        self.assertFalse(ImageGalleryCrawler._is_nudebird_url("https://hotgirl.biz/sample/"))
        self.assertFalse(ImageGalleryCrawler._is_nudebird_url("https://hotgirl.asia/sample/"))
