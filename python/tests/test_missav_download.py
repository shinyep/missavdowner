# -*- coding: utf-8 -*-
import shutil
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "python"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PYTHON_ROOT))

import server as missav_server
from python.crawler import VideoDownloader


class _ImmediateThread:
    """测试用同步线程桩，避免后台线程影响断言。"""

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


class MissavDownloadValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_video_rejects_non_m3u8_response_before_ffmpeg(self):
        downloader = VideoDownloader()

        class FakeResponse:
            status_code = 200
            text = "<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare</title></head><body>blocked</body></html>"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs
                self.get_calls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, **kwargs):
                self.get_calls.append((url, kwargs))
                return FakeResponse()

        async def fail_create_subprocess_exec(*args, **kwargs):
            raise AssertionError("ffmpeg should not be called for invalid m3u8 content")

        with patch("python.crawler.httpx.AsyncClient", FakeClient), \
             patch("python.crawler.asyncio.create_subprocess_exec", fail_create_subprocess_exec):
            with self.assertRaisesRegex(RuntimeError, "m3u8"):
                await downloader.download_video(
                    "https://surrit.com/test/video.m3u8",
                    "https://missav.ws/sdmt-015",
                    str(Path("G:/videodown/tmp-test/output.mp4")),
                    auto_merge=True,
                    keep_temp_files=True,
                )

    async def test_download_video_forwards_browser_cookies_to_http_client(self):
        downloader = VideoDownloader()
        captured_kwargs = {}

        class FakeResponse:
            status_code = 200
            content = b"segment-bytes"
            text = "#EXTM3U\n#EXT-X-VERSION:3\nsegment-001.ts\n"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                captured_kwargs.update(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, **kwargs):
                return FakeResponse()

        async def fake_create_subprocess_exec(*args, **kwargs):
            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"", b""

            return FakeProcess()

        cookies = [
            {"name": "cf_clearance", "value": "token", "domain": ".surrit.com", "path": "/"},
            {"name": "session", "value": "abc123", "domain": ".surrit.com", "path": "/"},
        ]

        with patch("python.crawler.httpx.AsyncClient", FakeClient), \
             patch("python.crawler.asyncio.create_subprocess_exec", fake_create_subprocess_exec):
            await downloader.download_video(
                "https://surrit.com/test/video.m3u8",
                "https://missav.ws/sdmt-015",
                str(Path("G:/videodown/tmp-test/output.mp4")),
                auto_merge=True,
                keep_temp_files=True,
                session_cookies=cookies,
            )

        self.assertIn("cookies", captured_kwargs)
        self.assertEqual(captured_kwargs["cookies"], {"cf_clearance": "token", "session": "abc123"})

    async def test_download_video_downloads_original_jpeg_segments_but_merges_local_ts_files(self):
        downloader = VideoDownloader()
        captured_playlist = {}
        requested_urls = []
        written_segments = []

        class FakeResponse:
            status_code = 200
            content = b"segment-bytes"

            def raise_for_status(self):
                return None

            @property
            def text(self):
                return "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:5,\nvideo0.jpeg\n"

        class FakeClient:
            def __init__(self, *args, **kwargs):
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, **kwargs):
                requested_urls.append(url)
                return FakeResponse()

        async def fake_create_subprocess_exec(*args, **kwargs):
            playlist_path = Path(args[args.index("-i") + 1])
            captured_playlist["content"] = playlist_path.read_text(encoding="utf-8")
            written_segments.extend(path.name for path in playlist_path.parent.glob("*") if path.is_file())

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"", b""

            return FakeProcess()

        with patch("python.crawler.httpx.AsyncClient", FakeClient), \
             patch("python.crawler.asyncio.create_subprocess_exec", fake_create_subprocess_exec):
            await downloader.download_video(
                "https://surrit.com/test/video.m3u8",
                "https://missav.ws/dm105/kawd-931",
                str(Path("G:/videodown/tmp-test/output.mp4")),
                auto_merge=True,
                keep_temp_files=True,
            )

        self.assertIn("https://surrit.com/test/video0.jpeg", requested_urls)
        self.assertIn("video0.ts", captured_playlist["content"])
        self.assertNotIn("video0.jpeg", captured_playlist["content"])
        self.assertIn("video0.ts", written_segments)

    async def test_download_video_uses_segment_fetcher_when_http_client_gets_403(self):
        downloader = VideoDownloader()
        fetched_urls = []
        segment_fetcher_calls = []
        captured_playlist = {}

        class FakeResponse:
            def __init__(self, url):
                self.url = url
                self.status_code = 403 if url.endswith("video0.jpeg") else 200
                self.content = b""
                self.text = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:5,\nvideo0.jpeg\n"

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"{self.status_code} forbidden")

        class FakeClient:
            def __init__(self, *args, **kwargs):
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, **kwargs):
                fetched_urls.append(url)
                return FakeResponse(url)

        async def fake_segment_fetcher(url):
            segment_fetcher_calls.append(url)
            return b"browser-segment-bytes"

        async def fake_create_subprocess_exec(*args, **kwargs):
            playlist_path = Path(args[args.index("-i") + 1])
            captured_playlist["content"] = playlist_path.read_text(encoding="utf-8")
            captured_playlist["segment_bytes"] = (playlist_path.parent / "video0.ts").read_bytes()

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"", b""

            return FakeProcess()

        with patch("python.crawler.httpx.AsyncClient", FakeClient), \
             patch("python.crawler.asyncio.create_subprocess_exec", fake_create_subprocess_exec):
            await downloader.download_video(
                "https://surrit.com/test/video.m3u8",
                "https://missav.ws/dm105/kawd-931",
                str(Path("G:/videodown/tmp-test/output.mp4")),
                auto_merge=True,
                keep_temp_files=True,
                segment_fetcher=fake_segment_fetcher,
            )

        self.assertIn("https://surrit.com/test/video0.jpeg", fetched_urls)
        self.assertEqual(segment_fetcher_calls, ["https://surrit.com/test/video0.jpeg"])
        self.assertIn("video0.ts", captured_playlist["content"])
        self.assertEqual(captured_playlist["segment_bytes"], b"browser-segment-bytes")

    async def test_download_video_creates_browser_fetcher_when_segment_gets_403(self):
        downloader = VideoDownloader()
        fetched_urls = []
        browser_fetcher_urls = []
        browser_cleanup_called = False
        captured_playlist = {}

        class FakeResponse:
            def __init__(self, url):
                self.url = url
                self.status_code = 403 if url.endswith("video0.jpeg") else 200
                self.content = b""
                self.text = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:5,\nvideo0.jpeg\n"

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"{self.status_code} forbidden")

        class FakeClient:
            def __init__(self, *args, **kwargs):
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, **kwargs):
                fetched_urls.append(url)
                return FakeResponse(url)

        async def fake_create_browser_fetcher(referer_url):
            self.assertEqual(referer_url, "https://missav.ws/dm31/iene-552")

            async def fake_fetch(url):
                browser_fetcher_urls.append(url)
                return b"new-browser-segment-bytes"

            async def fake_cleanup():
                nonlocal browser_cleanup_called
                browser_cleanup_called = True

            return fake_fetch, fake_cleanup

        async def fake_create_subprocess_exec(*args, **kwargs):
            playlist_path = Path(args[args.index("-i") + 1])
            captured_playlist["content"] = playlist_path.read_text(encoding="utf-8")
            captured_playlist["segment_bytes"] = (playlist_path.parent / "video0.ts").read_bytes()

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"", b""

            return FakeProcess()

        with patch("python.crawler.httpx.AsyncClient", FakeClient), \
             patch("python.crawler.create_playwright_segment_fetcher", fake_create_browser_fetcher), \
             patch("python.crawler.asyncio.create_subprocess_exec", fake_create_subprocess_exec):
            await downloader.download_video(
                "https://surrit.com/test/video.m3u8",
                "https://missav.ws/dm31/iene-552",
                str(Path("G:/videodown/tmp-test/output.mp4")),
                auto_merge=True,
                keep_temp_files=True,
            )

        self.assertIn("https://surrit.com/test/video0.jpeg", fetched_urls)
        self.assertEqual(browser_fetcher_urls, ["https://surrit.com/test/video0.jpeg"])
        self.assertTrue(browser_cleanup_called)
        self.assertIn("video0.ts", captured_playlist["content"])
        self.assertEqual(captured_playlist["segment_bytes"], b"new-browser-segment-bytes")

    async def test_download_video_times_out_stuck_ffmpeg_merge(self):
        downloader = VideoDownloader()

        class FakeResponse:
            status_code = 200
            content = b"segment-bytes"
            text = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:5,\nvideo0.jpeg\n"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, **kwargs):
                return FakeResponse()

        class HangingProcess:
            returncode = None
            killed = False

            async def communicate(self):
                await asyncio.sleep(60)
                return b"", b""

            def kill(self):
                self.killed = True

            async def wait(self):
                self.returncode = -9
                return self.returncode

        process = HangingProcess()

        async def fake_create_subprocess_exec(*args, **kwargs):
            return process

        with patch("python.crawler.httpx.AsyncClient", FakeClient), \
             patch("python.crawler.asyncio.create_subprocess_exec", fake_create_subprocess_exec):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg 合并超时"):
                await downloader.download_video(
                    "https://surrit.com/test/video.m3u8",
                    "https://missav.ws/dm105/kawd-931",
                    str(Path("G:/videodown/tmp-test/output.mp4")),
                    auto_merge=True,
                    keep_temp_files=True,
                    merge_timeout_seconds=0.01,
                )

        self.assertTrue(process.killed)


class MissavParseApiTests(unittest.TestCase):
    @patch.object(missav_server, "get_crawler_for_url")
    def test_parse_api_returns_json_serializable_payload(self, mock_get_crawler):
        mock_crawler = SimpleNamespace()
        mock_crawler.parse_video = AsyncMock(return_value={
            "title": "SDMT-015",
            "m3u8_url": "https://surrit.com/video.m3u8",
            "m3u8_text": "#EXTM3U\n#EXT-X-VERSION:3\nsegment-001.ts\n",
            "cookies": [{"name": "cf_clearance", "value": "token"}],
        })
        mock_get_crawler.return_value = (mock_crawler, None, "missav")

        client = missav_server.app.test_client()
        response = client.post("/api/parse", json={"url": "https://missav.ws/sdmt-015"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["source"], "missav")
        self.assertEqual(payload["m3u8_url"], "https://surrit.com/video.m3u8")
        self.assertEqual(payload["cookies"][0]["name"], "cf_clearance")


class MissavDownloadToNovelApiTests(unittest.TestCase):
    def setUp(self):
        missav_server.download_tasks.clear()
        self.temp_novel_root = PROJECT_ROOT / "tmp_video_to_novel_test"
        shutil.rmtree(self.temp_novel_root, ignore_errors=True)

    def tearDown(self):
        missav_server.download_tasks.clear()
        shutil.rmtree(self.temp_novel_root, ignore_errors=True)

    @patch.object(missav_server, "_save_to_history")
    @patch.object(missav_server, "import_video_to_novel")
    @patch.object(missav_server.threading, "Thread", _ImmediateThread)
    @patch.object(missav_server, "get_crawler_for_url")
    def test_download_to_novel_uses_temp_videos_for_video_and_hls_temp_files(
        self,
        mock_get_crawler,
        mock_import_video,
        _mock_save_history,
    ):
        """回归测试：普通视频入库前应下载到 Novel 的 temp_videos 目录。"""
        mock_crawler = SimpleNamespace()
        mock_crawler.parse_video = AsyncMock(return_value={
            "title": "TLS-017",
            "code": "TLS-017",
            "m3u8_url": "https://surrit.com/test/video.m3u8",
            "m3u8_text": "#EXTM3U\n#EXTINF:5,\nsegment.ts\n",
            "cookies": [{"name": "cf_clearance", "value": "token"}],
        })

        captured_output_paths = []

        class FakeDownloader:
            def set_proxy(self, _proxy):
                return None

            def set_concurrent(self, _max_concurrent):
                return None

            async def download_video(self, _m3u8_url, _referer, output_path, *args, **kwargs):
                captured_output_paths.append(Path(output_path))
                return output_path

        mock_get_crawler.return_value = (mock_crawler, FakeDownloader(), "missav")
        mock_import_video.return_value = {
            "success": True,
            "message": "Import OK",
        }

        client = missav_server.app.test_client()
        response = client.post(
            "/api/download-to-novel",
            json={
                "url": "https://missav.ws/dm27/tls-017",
                "outputDir": "",
                "novelProjectPath": str(self.temp_novel_root),
                "autoMerge": True,
                "keepTempFiles": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_output_paths[0].parent, self.temp_novel_root / "img" / "temp_videos")
        self.assertEqual(Path(mock_import_video.call_args.args[1]).parent, self.temp_novel_root / "img" / "temp_videos")


class MissavDownloadStatusApiTests(unittest.TestCase):
    def tearDown(self):
        missav_server.download_tasks.pop("task-status", None)

    def test_download_status_hides_internal_video_info(self):
        missav_server.download_tasks["task-status"] = {
            "id": "task-status",
            "url": "https://missav.ws/dm27/tls-017",
            "filename": "TLS-017.mp4",
            "output_path": "G:/videodown/tmp_live_tls017/TLS-017.mp4",
            "status": "downloading",
            "progress": 50,
            "speed": "合并中...",
            "phase": "merging",
            "phaseTitle": "合并视频",
            "detail": "G:/videodown/tmp_live_tls017/.temp_1782753120",
            "source": "missav",
            "video_info": {
                "title": "TLS-017",
                "m3u8_text": "#EXTM3U\n#EXTINF:5,\nsegment.ts\n",
            },
        }

        client = missav_server.app.test_client()
        response = client.get("/api/download-status/task-status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["detail"], "G:/videodown/tmp_live_tls017/.temp_1782753120")
        self.assertEqual(payload["source"], "missav")
        self.assertNotIn("video_info", payload)
        self.assertNotIn("m3u8_text", payload)


if __name__ == "__main__":
    unittest.main()
