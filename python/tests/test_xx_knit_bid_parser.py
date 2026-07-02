# -*- coding: utf-8 -*-
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "python"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PYTHON_ROOT))

from python.image_crawler import ImageGalleryCrawler
from python.novel_import import import_images_to_novel
import server as gallery_server


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

PAGE_31514_HTML = """
<html>
  <head>
    <title>[??] Buckwheat777 - ???????? ???? #01????????? 118P - Buckwheat777 - ???</title>
    <meta property="og:title" content="[??] Buckwheat777 - ???????? ???? #01????????? 118P - Buckwheat777 - ???" />
  </head>
  <body>
    <article>
      <div class="article-content">
        <img class="item-image__img alignnone size-medium wp-image-42" data-src="/static/images/2026/05/07/%5B%E7%A7%81%E6%88%BF%5D%20Buckwheat777%20-%20%E4%BA%BA%E9%97%B4%E5%B0%A4%E7%89%A9%E6%9E%81%E5%93%81%E5%BE%A1%E5%A7%90%20%E7%A6%8F%E5%88%A9%E7%A7%81%E6%8B%8D%20%2301%EF%BC%9A%E5%BE%A1%E5%A7%90%E7%A7%81%E6%8B%8D%E7%BE%8E%E8%85%BF%E7%BE%8E%E8%83%B8%20118P/OtherXXX-Buckwheat777-The-most-beautiful-lady-in-the-world-Welfare-private-shooting-01-lovecutes.com-001.jpg" src="https://xx.knit.bid/static/zde/timg.gif?v=1732843218" alt="[??] Buckwheat777 - ???????? ???? #01????????? 118P" />
        <img class="item-image__img alignnone size-medium wp-image-42" data-src="/static/images/2026/05/07/%5B%E7%A7%81%E6%88%BF%5D%20Buckwheat777%20-%20%E4%BA%BA%E9%97%B4%E5%B0%A4%E7%89%A9%E6%9E%81%E5%93%81%E5%BE%A1%E5%A7%90%20%E7%A6%8F%E5%88%A9%E7%A7%81%E6%8B%8D%20%2301%EF%BC%9A%E5%BE%A1%E5%A7%90%E7%A7%81%E6%8B%8D%E7%BE%8E%E8%85%BF%E7%BE%8E%E8%83%B8%20118P/OtherXXX-Buckwheat777-The-most-beautiful-lady-in-the-world-Welfare-private-shooting-01-lovecutes.com-002.jpg" src="https://xx.knit.bid/static/zde/timg.gif?v=1732843218" alt="[??] Buckwheat777 - ???????? ???? #01?????????? 120P" />
      </div>
    </article>
  </body>
</html>
"""



def _make_fake_response(url: str):
    """构造模拟的 httpx.Response 对象。"""
    text = PAGE_2_HTML if "/page/2/" in url else PAGE_1_HTML
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

    async def test_parse_gallery_ignores_recommendation_images_and_keeps_real_title(self):
        crawler = ImageGalleryCrawler()

        response = MagicMock()
        response.text = PAGE_31514_HTML
        response.raise_for_status = MagicMock()

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=response)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=fake_client):
            result = await crawler.parse_gallery("https://xx.knit.bid/article/31514/")

        self.assertEqual(result.title, "[??] Buckwheat777 - ???????? ???? #01????????? 118P")
        self.assertEqual(len(result.image_urls), 2)
        self.assertTrue(all(url.startswith("https://xx.knit.bid/static/images/2026/05/07/") for url in result.image_urls))
        self.assertEqual(result.video_url, "")


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


class _ImmediateThread:
    """测试用同步线程桩，避免真实后台线程影响断言。"""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)

    def join(self):
        return None


class GalleryDownloadStatusTests(unittest.TestCase):
    def setUp(self):
        gallery_server.download_tasks.clear()
        self.temp_novel_root = PROJECT_ROOT / "tmp_gallery_status_test"
        shutil.rmtree(self.temp_novel_root, ignore_errors=True)

    def tearDown(self):
        gallery_server.download_tasks.clear()
        shutil.rmtree(self.temp_novel_root, ignore_errors=True)

    @patch.object(gallery_server, "_save_gallery_to_history")
    @patch.object(gallery_server, "import_images_to_novel")
    @patch.object(gallery_server.threading, "Thread", _ImmediateThread)
    @patch.object(gallery_server, "ImageGalleryCrawler")
    def test_gallery_download_to_novel_returns_image_stats_after_import(
        self,
        mock_crawler_cls,
        mock_import_images,
        _mock_save_history,
    ):
        """回归测试：图集入库完成后，状态接口应返回前端统计所需字段。"""

        async def fake_download_gallery(_gallery_url, _output_dir, progress_callback=None):
            if progress_callback:
                progress_callback(
                    50,
                    "1.25 张/秒",
                    "downloading",
                    "正在下载第 5/12 张图片",
                    {
                        "total_images": 12,
                        "current_index": 5,
                        "success_count": 4,
                        "failed_count": 1,
                        "title": "回归测试图集",
                    },
                )
            return {
                "title": "回归测试图集",
                "filename": "回归测试图集",
                "output_path": str(self.temp_novel_root / "img" / "gallery-cache" / "回归测试图集"),
                "image_count": 12,
                "image_paths": [
                    str(self.temp_novel_root / "001.jpg"),
                    str(self.temp_novel_root / "002.jpg"),
                ],
                "video_url": "",
                "source_url": "https://example.com/gallery/1",
            }

        mock_crawler = MagicMock()
        mock_crawler.download_gallery = fake_download_gallery
        mock_crawler_cls.return_value = mock_crawler
        mock_import_images.return_value = {
            "success": True,
            "gallery_id": 1908,
            "image_count": 160,
            "message": "Import OK (gallery_id=1908, images=160)",
        }

        client = gallery_server.app.test_client()
        response = client.post(
            "/api/gallery/download",
            json={
                "galleryUrl": "https://example.com/gallery/1",
                "downloadMode": "novel",
                "novelProjectPath": str(self.temp_novel_root),
                "proxy": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        task_id = response.get_json()["task_id"]

        status_response = client.get(f"/api/download-status/{task_id}")
        self.assertEqual(status_response.status_code, 200)
        task = status_response.get_json()

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["gallery_id"], 1908)
        self.assertEqual(task["totalImages"], 12)
        self.assertEqual(task["successCount"], 160)
        self.assertEqual(task["currentIndex"], 5)
        self.assertEqual(task["failedCount"], 1)
        self.assertEqual(task["detail"], "Import OK (gallery_id=1908, images=160)")

    @patch.object(gallery_server, "_save_gallery_to_history")
    @patch.object(gallery_server, "import_images_to_novel")
    @patch.object(gallery_server, "import_video_to_novel")
    @patch.object(gallery_server.missav_downloader, "download_video")
    @patch.object(gallery_server.threading, "Thread", _ImmediateThread)
    @patch.object(gallery_server, "ImageGalleryCrawler")
    def test_gallery_video_cache_uses_temp_videos_directory(
        self,
        mock_crawler_cls,
        mock_download_video,
        mock_import_video,
        mock_import_images,
        _mock_save_history,
    ):
        """回归测试：图集附带视频在入库前应缓存到 Novel 的 temp_videos 目录。"""

        temp_root = self.temp_novel_root
        expected_dir = temp_root / "img" / "temp_videos"

        async def fake_download_gallery(_gallery_url, _output_dir, progress_callback=None):
            return {
                "title": "测试图集视频缓存",
                "filename": "测试图集视频缓存",
                "output_path": str(temp_root / "img" / "gallery-images" / "1908"),
                "image_count": 12,
                "image_paths": [
                    str(temp_root / "001.jpg"),
                    str(temp_root / "002.jpg"),
                ],
                "video_url": "https://media.knit.bid/play/test-gallery-video.m3u8",
                "source_url": "https://xx.knit.bid/en/article/19586/",
            }

        mock_crawler = MagicMock()
        mock_crawler.download_gallery = fake_download_gallery
        mock_crawler_cls.return_value = mock_crawler
        mock_import_images.return_value = {
            "success": True,
            "gallery_id": 1908,
            "image_count": 12,
            "message": "Import OK (gallery_id=1908, images=12)",
        }
        mock_download_video.side_effect = AsyncMock(return_value=str(expected_dir / "测试图集视频缓存.mp4"))
        mock_import_video.return_value = {
            "success": True,
            "video_id": 42,
            "message": "Import OK (video_id=42), transcode triggered",
        }

        client = gallery_server.app.test_client()
        response = client.post(
            "/api/gallery/download",
            json={
                "galleryUrl": "https://xx.knit.bid/en/article/19586/",
                "downloadMode": "novel",
                "novelProjectPath": str(temp_root),
                "proxy": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        task_id = response.get_json()["task_id"]

        status_response = client.get(f"/api/download-status/{task_id}")
        self.assertEqual(status_response.status_code, 200)
        task = status_response.get_json()

        self.assertEqual(task["status"], "completed")
        self.assertEqual(Path(mock_import_video.call_args.args[1]), expected_dir / "测试图集视频缓存.mp4")

    @patch.object(gallery_server, "_save_gallery_to_history")
    @patch.object(gallery_server, "import_images_to_novel")
    @patch.object(gallery_server.threading, "Thread", _ImmediateThread)
    @patch.object(gallery_server, "ImageGalleryCrawler")
    def test_gallery_download_status_returns_failed_images(
        self,
        mock_crawler_cls,
        mock_import_images,
        _mock_save_history,
    ):
        """回归测试：图集任务状态应返回失败图片明细，供前端逐张重试。"""

        async def fake_download_gallery(_gallery_url, _output_dir, progress_callback=None):
            if progress_callback:
                progress_callback(
                    50,
                    "1.25 张/秒",
                    "downloading",
                    "第 5/12 张下载失败：HTTP 403",
                    {
                        "total_images": 12,
                        "current_index": 5,
                        "success_count": 4,
                        "failed_count": 1,
                        "failed_images": [
                            {
                                "index": 5,
                                "image_url": "https://example.com/image-005.jpg",
                                "reason": "HTTP 403",
                            }
                        ],
                        "title": "回归测试图集",
                    },
                )
            return {
                "title": "回归测试图集",
                "filename": "回归测试图集",
                "output_path": str(self.temp_novel_root / "img" / "gallery-cache" / "回归测试图集"),
                "image_count": 11,
                "image_paths": [
                    str(self.temp_novel_root / "001.jpg"),
                    str(self.temp_novel_root / "002.jpg"),
                ],
                "video_url": "",
                "source_url": "https://example.com/gallery/1",
            }

        mock_crawler = MagicMock()
        mock_crawler.download_gallery = fake_download_gallery
        mock_crawler_cls.return_value = mock_crawler
        mock_import_images.return_value = {
            "success": True,
            "gallery_id": 1908,
            "image_count": 11,
            "message": "Import OK (gallery_id=1908, images=11)",
        }

        client = gallery_server.app.test_client()
        response = client.post(
            "/api/gallery/download",
            json={
                "galleryUrl": "https://example.com/gallery/1",
                "downloadMode": "novel",
                "novelProjectPath": str(self.temp_novel_root),
                "proxy": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        task_id = response.get_json()["task_id"]

        status_response = client.get(f"/api/download-status/{task_id}")
        self.assertEqual(status_response.status_code, 200)
        task = status_response.get_json()

        self.assertEqual(task["failedCount"], 1)
        self.assertEqual(task["failedImages"][0]["index"], 5)
        self.assertEqual(task["failedImages"][0]["image_url"], "https://example.com/image-005.jpg")
        self.assertEqual(task["failedImages"][0]["reason"], "HTTP 403")

    @patch.object(gallery_server.threading, "Thread", _ImmediateThread)
    @patch.object(gallery_server, "_download_single_gallery_image")
    def test_retry_gallery_image_updates_failed_images_and_counts(
        self,
        mock_retry_download,
    ):
        """回归测试：单张重试成功后，应移除失败项并更新统计。"""

        retry_file = self.temp_novel_root / "img" / "gallery_images" / "1909" / "1909_005.jpg"
        retry_file.parent.mkdir(parents=True, exist_ok=True)
        mock_retry_download.return_value = {
            "saved_path": str(retry_file),
            "image_count": 1,
        }

        gallery_server.download_tasks["task-retry"] = {
            "id": "task-retry",
            "url": "https://example.com/gallery/1",
            "downloadMode": "novel",
            "gallery_id": 1909,
            "output_path": str(retry_file.parent),
            "successCount": 83,
            "failedCount": 1,
            "totalImages": 84,
            "failedImages": [
                {
                    "index": 5,
                    "image_url": "https://example.com/image-005.jpg",
                    "reason": "HTTP 403",
                }
            ],
            "retryingImages": [],
        }

        client = gallery_server.app.test_client()
        response = client.post(
            "/api/gallery/retry-image",
            json={"taskId": "task-retry", "index": 5},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["task"]["successCount"], 84)
        self.assertEqual(payload["task"]["failedCount"], 0)
        self.assertEqual(payload["task"]["failedImages"], [])
        self.assertEqual(payload["task"]["detail"], "已补下第 5 张图片")

    @patch.object(gallery_server.threading, "Thread", _ImmediateThread)
    @patch.object(gallery_server, "_infer_missing_failed_images")
    @patch.object(gallery_server, "_download_single_gallery_image")
    def test_retry_gallery_image_uses_fallback_when_failed_images_missing(
        self,
        mock_retry_download,
        mock_infer_missing,
    ):
        """回归测试：旧任务缺少失败明细时，应使用兜底推断结果完成单张重试。"""

        retry_file = self.temp_novel_root / "img" / "gallery_images" / "1909" / "1909_084.jpg"
        retry_file.parent.mkdir(parents=True, exist_ok=True)
        mock_infer_missing.return_value = [
            {
                "index": 84,
                "image_url": "https://example.com/image-084.jpg",
                "reason": "旧任务未保留失败明细，按目录缺口推断",
            }
        ]
        mock_retry_download.return_value = {
            "saved_path": str(retry_file),
            "image_count": 1,
        }

        gallery_server.download_tasks["task-fallback"] = {
            "id": "task-fallback",
            "url": "https://example.com/gallery/1",
            "downloadMode": "novel",
            "gallery_id": 1909,
            "output_path": str(retry_file.parent),
            "successCount": 83,
            "failedCount": 1,
            "totalImages": 84,
            "failedImages": [],
            "retryingImages": [],
        }

        client = gallery_server.app.test_client()
        response = client.post(
            "/api/gallery/retry-image",
            json={"taskId": "task-fallback", "index": 84},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["task"]["successCount"], 84)
        self.assertEqual(payload["task"]["failedCount"], 0)
        mock_infer_missing.assert_called_once()


if __name__ == "__main__":
    unittest.main()
