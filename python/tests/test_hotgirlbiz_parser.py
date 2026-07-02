# -*- coding: utf-8 -*-
"""hotgirl.biz 专用解析回归测试。

验证 hotgirl.biz 走独立解析路径，只从 .entry-content 提取正文图片，
不抓取 header logo（wp-content/uploads/2017/10/Untitled-1.png）。
"""

import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from python.image_crawler import ImageGalleryCrawler

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_HTML = (FIXTURE_DIR / "hotgirl_biz_sample.html").read_text(encoding="utf-8")


class HotgirlBizParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_hotgirlbiz_collects_content_images(self):
        """正文图片应从 .entry-content 的 data-src 提取"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirlbiz_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.biz/sample/")

        self.assertEqual(
            result.image_urls,
            [
                "https://hotgirl.biz/wp-content/uploads/2026/06/19087-11145353-11145353.jpg",
                "https://hotgirl.biz/wp-content/uploads/2026/06/B39157744-11145356-11145356.jpg",
                "https://hotgirl.biz/wp-content/uploads/2026/06/779157498-11145400-11145400.jpg",
            ],
        )

    async def test_parse_hotgirlbiz_excludes_header_logo(self):
        """header 中的 logo（Untitled-1.png）不应被收入结果"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirlbiz_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.biz/sample/")

        self.assertTrue(all("Untitled-1" not in url for url in result.image_urls))
        self.assertTrue(all("2017/10" not in url for url in result.image_urls))

    async def test_parse_hotgirlbiz_title_from_h1(self):
        """标题应从 h1 提取，不带站点后缀"""
        crawler = ImageGalleryCrawler()
        crawler._hotgirlbiz_fetch = AsyncMock(side_effect=[SAMPLE_HTML])

        result = await crawler.parse_gallery("https://hotgirl.biz/sample/")

        self.assertEqual(result.title, "XiuRen Extra FW0217 谢小蒽")

    async def test_is_hotgirlbiz_url(self):
        """hotgirl.biz 应走独立解析路径"""
        self.assertTrue(ImageGalleryCrawler._is_hotgirlbiz_url("https://hotgirl.biz/sample/"))
        self.assertFalse(ImageGalleryCrawler._is_hotgirlbiz_url("https://hotgirl.asia/sample/"))
        self.assertFalse(ImageGalleryCrawler._is_hotgirlbiz_url("https://nudebird.biz/sample/"))
