"""
KissJAV 视频爬虫模块
从 kissjav.com 提取视频信息和下载链接
使用 Playwright + stealth 注入，复用 MissAV 技术栈

页面结构关键信息：
- flashvars 是局部变量（var flashvars = {...}），不是 window.flashvars
- 页面已执行 atob 解码 video_url，提取时已是明文 URL
- kt_player() 初始化播放器后 flashvars 可能被回收
- 需要在页面脚本执行前拦截，或直接从 HTML 正则提取原始数据
"""
import asyncio
import re
import base64
import time
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import async_playwright, Page

# 强制 stdout UTF-8 编码，避免 Windows GBK 环境韩文崩溃
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


class KissjavCrawler:
    """KissJAV 视频爬虫"""

    BASE_URL = "https://kissjav.com/"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.BASE_URL,
        }

    async def parse_video(self, url: str) -> dict:
        """
        解析视频页面，提取视频信息。
        优先 httpx 直抓（快），Cloudflare 拦截时回退 Playwright（慢但能过 CF）。
        """
        html_content = None

        # 快速路径：httpx 直抓静态 HTML
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(15),
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and 'flashvars' in resp.text:
                    html_content = resp.text
                    print(f"[Kissjav] httpx 直抓成功 ({len(html_content)} bytes)")
        except Exception as e:
            print(f"[Kissjav] httpx 失败: {e}，回退 Playwright")

        # 慢速路径：Playwright（Cloudflare 保护时）
        if html_content is None:
            html_content = await self._fetch_with_playwright(url)

        # 从 HTML 提取数据（两种路径共用）
        flashvars = self._extract_flashvars_from_html(html_content)
        title = self._extract_title_from_html(html_content)

        cover = flashvars.get('preview_url', '')
        if cover and cover.startswith('//'):
            cover = 'https:' + cover

        video_url = flashvars.get('video_url', '')
        metadata = self._extract_metadata_from_flashvars(flashvars)

        print(f"[Kissjav] 标题: {title}")
        print(f"[Kissjav] 视频: {video_url[:80]}...")

        return {
            'title': title,
            'cover': cover,
            'm3u8_url': None,
            'video_url': video_url,
            **metadata
        }

    async def _fetch_with_playwright(self, url: str) -> str:
        """Playwright 兜底：处理 Cloudflare 质询。复用 BrowserManager 浏览器实例。"""
        from crawler import BrowserManager
        context = await BrowserManager.new_context()
        page = await context.new_page()
        try:
            print(f"[Kissjav] Playwright 访问: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await self._handle_cloudflare(page)
            await page.wait_for_timeout(1000)
            return await page.content()
        finally:
            await context.close()

    def _extract_flashvars_from_html(self, html: str) -> dict:
        """
        从 HTML 源码中正则提取 flashvars 变量内容。
        最可靠的方式，不依赖 JS 执行上下文。
        """
        result = {}

        # 匹配 var flashvars = { ... }; 块
        # flashvars 内容跨多行，需要非贪婪匹配
        pattern = r'var\s+flashvars\s*=\s*\{([\s\S]*?)\};'
        match = re.search(pattern, html)
        if not match:
            print("[Kissjav] 警告: 未找到 flashvars 定义")
            return result

        flashvars_body = match.group(1)

        # 提取各个键值对
        # 格式: key: 'value' 或 key: "value"
        kv_pattern = r"(\w+)\s*:\s*['\"]([^'\"]*?)['\"]"
        for kv_match in re.finditer(kv_pattern, flashvars_body):
            key = kv_match.group(1)
            value = kv_match.group(2)
            result[key] = value

        # 对 video_url 做 Base64 解码（页面脚本执行 atob 前是编码的）
        if 'video_url' in result:
            raw = result['video_url']
            try:
                decoded = base64.b64decode(raw).decode('utf-8')
                if decoded.startswith('http'):
                    result['video_url'] = decoded
                    print(f"[Kissjav] video_url Base64 解码成功")
                else:
                    print(f"[Kissjav] video_url 解码后不是 URL: {decoded[:50]}")
            except Exception:
                # 如果解码失败，可能已经是明文 URL（页面已执行 atob）
                if raw.startswith('http'):
                    print(f"[Kissjav] video_url 已是明文 URL")

        # video_url_hd 同理
        if 'video_url_hd' in result:
            raw_hd = result['video_url_hd']
            try:
                decoded_hd = base64.b64decode(raw_hd).decode('utf-8')
                if decoded_hd.startswith('http'):
                    result['video_url_hd'] = decoded_hd
                else:
                    # 'MQ==' 解码为 '1' 表示 HD 不可用
                    del result['video_url_hd']
            except Exception:
                pass

        return result

    def _extract_title_from_html(self, html: str) -> str:
        """从 HTML 的 og:title 或 <title> 提取标题"""
        # 优先 og:title
        og_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if og_match:
            return og_match.group(1).strip()

        # <title> 标签
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            title = title_match.group(1).strip()
            # 移除网站后缀
            for suffix in [' - KissJAV', ' korean porn vip', ' japanese porn vip']:
                if title.endswith(suffix):
                    title = title[:-len(suffix)].strip()
            return title

        return ""

    def _extract_metadata_from_flashvars(self, flashvars: dict) -> dict:
        """从 flashvars 中提取元数据"""
        metadata = {
            'actresses': [],
            'tags': [],
            'code': '',
            'release_date': '',
            'duration': '',
        }

        # 演员
        if flashvars.get('video_models'):
            models = flashvars['video_models']
            metadata['actresses'] = [m.strip() for m in models.split(',') if m.strip()]

        # 标签（来自 video_categories 和 video_tags）
        tags = []
        if flashvars.get('video_categories'):
            tags.extend([t.strip() for t in flashvars['video_categories'].split(',') if t.strip()])
        if flashvars.get('video_tags'):
            tags.extend([t.strip() for t in flashvars['video_tags'].split(',') if t.strip()])
        metadata['tags'] = list(set(tags))

        # 番号
        if flashvars.get('video_id'):
            metadata['code'] = f"KJ-{flashvars['video_id']}"

        return metadata

    async def _handle_cloudflare(self, page: Page):
        """处理 Cloudflare 质询 - 统一策略：先尝试点击，再等待标题变化"""
        cf_titles = ("Just a moment...", "Attention Required", "Checking your browser", "Please wait...")

        await page.wait_for_timeout(2000)

        title = await page.title()
        if title in cf_titles:
            print(f"[Kissjav] 检测到 Cloudflare 质询 ({title})，尝试处理...")

            # 尝试点击 challenge-stage
            try:
                challenge_stage = await page.query_selector('#challenge-stage')
                if challenge_stage:
                    print("[Kissjav] 找到 challenge-stage，尝试点击...")
                    await challenge_stage.click()
                    await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"[Kissjav] 点击 challenge-stage 失败: {e}")

            # 等待标题变化
            try:
                await page.wait_for_function(
                    "document.title !== 'Just a moment...' && document.title !== 'Please wait...'",
                    timeout=30000
                )
                print("[Kissjav] Cloudflare 已通过")
                await page.wait_for_timeout(3000)
            except Exception:
                print("[Kissjav] Cloudflare 等待超时，尝试刷新...")
                try:
                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(5000)
                except Exception:
                    pass

    async def _extract_title(self, page: Page) -> str:
        """备用标题提取"""
        title_el = await page.query_selector('h1')
        if title_el:
            title = await title_el.text_content()
            if title:
                return title.strip()
        return "未知标题"


class KissjavVideoDownloader:
    """KissJAV 视频下载器 - 直接下载 mp4 文件"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://kissjav.com/',
        }
        self._proxy = None
        self._paused_tasks: set[str] = set()

    def set_proxy(self, proxy: str | None):
        """设置代理"""
        self._proxy = proxy

    def set_concurrent(self, max_concurrent: int):
        """设置并发数（兼容接口，mp4 直链下载不需要并发控制）"""
        pass

    async def download_video(
        self,
        video_url: str,
        referer: str,
        output: str | Path,
        progress_callback=None
    ) -> str:
        """
        下载 mp4 视频文件

        Args:
            video_url: 视频直链 URL
            referer: Referer 头
            output: 输出文件路径
            progress_callback: 进度回调函数

        Returns:
            下载完成的文件路径
        """
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

        print(f"[Kissjav] 开始下载视频: {video_url}")
        print(f"[Kissjav] 保存到: {output}")

        client_kwargs = {
            'headers': {**self.headers, 'Referer': referer},
            'timeout': httpx.Timeout(300, connect=30),
            'follow_redirects': True,
        }
        if self._proxy:
            client_kwargs['proxy'] = self._proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            # 获取文件大小
            total_size = 0
            try:
                head_resp = await client.head(video_url)
                total_size = int(head_resp.headers.get('content-length', 0))
                print(f"[Kissjav] 文件大小: {total_size / 1024 / 1024:.2f} MB")
            except Exception as e:
                print(f"[Kissjav] 获取文件大小失败: {e}")

            # 流式下载
            downloaded = 0
            start_time = time.time()

            async with client.stream('GET', video_url) as response:
                response.raise_for_status()

                with open(output, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 计算进度和速度
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        speed_str = f"{speed / 1024 / 1024:.2f} MB/s"

                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                        else:
                            progress = -1

                        if progress_callback:
                            progress_callback(progress, speed_str)

            print(f"[Kissjav] 下载完成: {output}")
            return str(output)

    def pause_task(self, task_id: str):
        """暂停任务"""
        self._paused_tasks.add(task_id)

    def resume_task(self, task_id: str):
        """恢复任务"""
        self._paused_tasks.discard(task_id)

    def is_paused(self, task_id: str) -> bool:
        """检查任务是否暂停"""
        return task_id in self._paused_tasks


# 单例实例
kissjav_crawler = KissjavCrawler()
kissjav_downloader = KissjavVideoDownloader()
