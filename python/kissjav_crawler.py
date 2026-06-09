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
        解析视频页面，提取视频信息

        Args:
            url: kissjav 视频页面 URL

        Returns:
            包含视频信息的字典
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                user_agent=self.headers['User-Agent'],
                viewport={'width': 1920, 'height': 1080}
            )
            # 隐藏自动化标记
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            """)
            page = await context.new_page()

            try:
                # 导航到页面
                print(f"[Kissjav] 正在访问: {url}")
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)

                # 处理 Cloudflare 质询
                await self._handle_cloudflare(page)

                # 等待页面加载完成
                await page.wait_for_timeout(3000)

                # 从 HTML 源码中提取 flashvars 数据（最可靠的方式）
                html_content = await page.content()
                flashvars = self._extract_flashvars_from_html(html_content)

                # 提取标题
                title = self._extract_title_from_html(html_content) or await self._extract_title(page)

                # 提取封面
                cover = flashvars.get('preview_url', '')
                if cover and cover.startswith('//'):
                    cover = 'https:' + cover

                # 提取视频 URL
                video_url = flashvars.get('video_url', '')

                # 提取元数据
                metadata = self._extract_metadata_from_flashvars(flashvars)

                print(f"[Kissjav] 标题: {title}")
                print(f"[Kissjav] 封面: {cover[:80]}...")
                print(f"[Kissjav] 视频: {video_url[:80]}...")
                print(f"[Kissjav] 演员: {metadata.get('actresses', [])}")
                print(f"[Kissjav] 标签: {metadata.get('tags', [])}")

                return {
                    'title': title,
                    'cover': cover,
                    'm3u8_url': None,
                    'video_url': video_url,
                    **metadata
                }

            finally:
                await browser.close()

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
    """KissJAV 视频下载器 - 使用 Playwright 下载（携带浏览器 cookies 绕过 CDN 校验）"""

    def __init__(self):
        self._proxy = None
        self._paused_tasks: set[str] = set()

    def set_proxy(self, proxy: str | None):
        self._proxy = proxy

    def set_concurrent(self, max_concurrent: int):
        pass

    async def download_video(
        self,
        video_url: str,
        referer: str,
        output: str | Path,
        progress_callback=None
    ) -> str:
        """使用 Playwright 响应拦截下载视频（走浏览器网络栈，携带 cookies）。"""
        from crawler import BrowserManager
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

        print(f"[Kissjav] Playwright 下载: {video_url[:80]}...")

        context = await BrowserManager.new_context()
        page = await context.new_page()

        try:
            # 访问 kissjav 页面获取 cookies
            await page.goto(referer, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)

            # 拦截所有响应，捕获视频数据（过滤广告追踪 URL）
            video_data = {}
            ad_domains = {'coosync.com', 'alfalfaemployeeresource.com', 'magsrv.com', 'exdynsrv.com'}

            async def on_response(response):
                url = response.url
                status = response.status
                # 跳过广告追踪响应
                if any(ad in url for ad in ad_domains):
                    return
                # 匹配视频 CDN 响应（200 + 大文件）
                if status == 200:
                    try:
                        content_length = int(response.headers.get('content-length', '0'))
                        if content_length > 100000 or '.mp4' in url:  # >100KB 或 mp4
                            body = await response.body()
                            if len(body) > 100000:
                                video_data['bytes'] = body
                                video_data['url'] = url
                                print(f"[Kissjav] 捕获: {url[:60]}... {len(body)/1024/1024:.1f}MB")
                    except Exception:
                        pass

            page.on('response', on_response)

            # 导航到视频 URL（浏览器自动跟随所有重定向）
            try:
                await page.goto(video_url, wait_until='commit', timeout=120000)
            except Exception:
                pass

            # 等待视频响应到达（最多 5 分钟）
            for i in range(300):
                if 'bytes' in video_data:
                    break
                if i % 30 == 29:
                    print(f"[Kissjav] 等待中... {i+1}s")
                await page.wait_for_timeout(1000)

            if 'bytes' not in video_data:
                raise RuntimeError("下载失败: 未捕获到视频数据（CDN 可能拒绝了请求）")

            data = video_data['bytes']
            output.write_bytes(data)

            size_mb = len(data) / 1024 / 1024
            if progress_callback:
                progress_callback(100, f"{size_mb:.1f} MB")

            print(f"[Kissjav] 下载完成: {output} ({size_mb:.1f} MB)")
            return str(output)
        finally:
            await context.close()

    def pause_task(self, task_id: str):
        self._paused_tasks.add(task_id)

    def resume_task(self, task_id: str):
        self._paused_tasks.discard(task_id)

    def is_paused(self, task_id: str) -> bool:
        return task_id in self._paused_tasks


# 单例实例
kissjav_crawler = KissjavCrawler()
kissjav_downloader = KissjavVideoDownloader()
