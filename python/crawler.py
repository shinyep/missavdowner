"""
MissAV 视频爬虫核心模块
从 missav.ws 提取视频信息和下载链接
"""
import asyncio
import atexit
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BrowserManager:
    """Playwright 浏览器实例单例，避免每次解析都启动/关闭浏览器"""

    _instance = None
    _browser: Browser | None = None
    _playwright = None

    @classmethod
    async def get_browser(cls) -> Browser:
        if cls._browser is not None and cls._browser.is_connected():
            return cls._browser

        # 浏览器不存在或已断开，重建整个链路
        try:
            if cls._playwright:
                await cls._playwright.stop()
        except Exception:
            pass
        cls._playwright = None
        cls._browser = None

        cls._playwright = await async_playwright().start()
        cls._browser = await cls._playwright.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled'],
        )
        print("[BrowserManager] 新建浏览器实例")
        return cls._browser

    @classmethod
    async def new_context(cls, accept_downloads: bool = False) -> BrowserContext:
        for attempt in range(2):
            try:
                browser = await cls.get_browser()
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    accept_downloads=accept_downloads,
                )
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    window.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                """)
                return context
            except Exception as e:
                # 整个 Playwright 链路断开，强制完全重建
                print(f"[BrowserManager] 实例失效({e})，完全重建中...")
                try:
                    if cls._browser:
                        await cls._browser.close()
                except Exception:
                    pass
                try:
                    if cls._playwright:
                        await cls._playwright.stop()
                except Exception:
                    pass
                cls._browser = None
                cls._playwright = None
                if attempt == 1:
                    raise
        raise RuntimeError("无法创建浏览器 context")

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None


def _cleanup_browser():
    """进程退出时清理浏览器实例"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(BrowserManager.close())
        else:
            loop.run_until_complete(BrowserManager.close())
    except Exception:
        pass


atexit.register(_cleanup_browser)


class MissavCrawler:
    """MissAV 视频爬虫"""

    BASE_URL = "https://missav.ws/"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.BASE_URL,
        }

    async def parse_video(self, url: str) -> dict:
        """解析视频页面，提取视频信息。复用浏览器实例 + 并行提取元数据。

        返回的 dict 中包含 browser_page/browser_context，调用方负责在使用后关闭。
        """
        context = await BrowserManager.new_context()
        page = await context.new_page()

        try:
            print(f"正在访问: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)

            # 处理 Cloudflare 质询
            await self._handle_cloudflare(page)

            # 并行提取标题、封面、元数据（省 ~1-2s）
            title_task = asyncio.create_task(self._extract_title(page))
            cover_task = asyncio.create_task(self._extract_cover(page))
            metadata_task = asyncio.create_task(self._extract_metadata(page))

            title = await title_task
            cover = await cover_task
            metadata = await metadata_task

            # m3u8 捕获（依赖页面交互，不能并行）
            m3u8_info = await self._capture_m3u8(page, url)
            cookies = await context.cookies()

            return {
                'title': title,
                'cover': cover,
                'm3u8_url': m3u8_info.get('url'),
                'm3u8_text': m3u8_info.get('text'),
                'cookies': cookies,
                'browser_context': context,  # 调用方负责关闭
                'browser_page': page,        # 可用于浏览器端下载分片
                **metadata
            }

        except Exception:
            # 解析失败时确保清理
            await context.close()
            raise

    async def _handle_cloudflare(self, page: Page):
        """处理 Cloudflare 质询 - stealth 模式下自动通过"""
        cf_titles = ("Just a moment...", "Attention Required", "Checking your browser")

        await page.wait_for_timeout(2000)

        title = await page.title()
        if title in cf_titles:
            print(f"检测到 Cloudflare 质询 ({title})，等待自动验证...")
            try:
                await page.wait_for_function(
                    f"document.title !== '{title}'",
                    timeout=30000
                )
                print("Cloudflare 已通过")
                await page.wait_for_timeout(3000)
            except Exception:
                print("Cloudflare 等待超时，尝试刷新...")
                try:
                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(5000)
                except Exception:
                    pass
            return

        # 旧版 CF 选择器兜底
        if await page.query_selector("#challenge-running"):
            print("检测到旧版 Cloudflare 质询，等待...")
            try:
                await page.wait_for_selector('body:not(#challenge-running)', timeout=30000)
                await page.wait_for_timeout(2000)
            except Exception:
                pass

    async def _extract_title(self, page: Page) -> str:
        """提取视频标题"""
        # 尝试从 h1 标签提取
        title_el = await page.query_selector('h1')
        if title_el:
            title = await title_el.text_content()
            if title:
                return title.strip()

        # 备用方案：从 meta 标签提取
        og_title = await page.query_selector('meta[property="og:title"]')
        if og_title:
            content = await og_title.get_attribute('content')
            if content:
                # missav 标题格式: XXX - Actress - MISSAV
                parts = content.split(' - ')
                if len(parts) > 1:
                    return ' - '.join(parts[:-1]).strip()

        return "未知标题"

    async def _extract_cover(self, page: Page) -> str:
        """提取封面图 URL"""
        # 方法1: 从 og:image meta 标签提取
        og_image = await page.query_selector('meta[property="og:image"]')
        if og_image:
            content = await og_image.get_attribute('content')
            if content:
                print(f"Found og:image: {content}")
                return urljoin(self.BASE_URL, content)

        # 方法2: 从视频元素的 poster 属性提取
        video = await page.query_selector('video[poster]')
        if video:
            poster = await video.get_attribute('poster')
            if poster:
                print(f"Found video poster: {poster}")
                return urljoin(self.BASE_URL, poster)

        # 方法3: 从页面中的图片提取
        img_selectors = [
            'img.video-cover',
            'img.thumbnail',
            '.video-player img',
            'article img',
        ]
        for selector in img_selectors:
            img = await page.query_selector(selector)
            if img:
                src = await img.get_attribute('src')
                if src and not src.startswith('data:'):
                    print(f"Found image from selector {selector}: {src}")
                    return urljoin(self.BASE_URL, src)

        print("No cover image found")
        return ""

    async def _extract_metadata(self, page: Page) -> dict:
        """提取视频元数据（演员、标签、番号等）"""
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')

        metadata = {
            'actresses': [],
            'tags': [],
            'code': '',
            'release_date': '',
            'duration': ''
        }

        # 提取演员
        actress_link = soup.find('a', href=re.compile(r'/actresses/'))
        if actress_link:
            name_tag = actress_link.find('span', itemprop='name')
            if name_tag:
                metadata['actresses'] = [name_tag.get_text(strip=True)]

        # 提取标签
        tag_container = soup.find('div', class_=re.compile(r'flex flex-wrap gap-2'))
        if tag_container:
            tag_links = tag_container.find_all('a', href=re.compile(r'/tags/'))
            metadata['tags'] = [
                tag.find('span').get_text(strip=True)
                for tag in tag_links
                if tag.find('span')
            ]

        # 提取番号
        code_link = soup.find('a', href=re.compile(r'/search/'))
        if code_link and code_link.find('span'):
            metadata['code'] = code_link.find('span').get_text(strip=True)

        # 提取发布日期和时长
        info_container = soup.find('div', class_=re.compile(r'flex items-center space-x-2'))
        if info_container:
            all_text = info_container.get_text(sep=' ', strip=True)

            # 日期
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', all_text)
            if date_match:
                metadata['release_date'] = date_match.group(0)

            # 时长
            duration_match = re.search(r'(\d+)\s*min', all_text)
            if duration_match:
                metadata['duration'] = f"{duration_match.group(1)} min"

        return metadata

    async def _capture_m3u8(self, page: Page, referer: str) -> dict:
        """捕获页面发起的 m3u8 请求及其响应正文。

        通过 response 事件捕获（而不是 request），确保响应体已就绪可直接读取。
        同时监听 request 以快速发现 URL 用于日志输出。
        """
        for attempt in range(2):
            m3u8_url = None
            m3u8_text = None
            m3u8_responses: list = []  # 存储匹配的 response 对象
            m3u8_future = asyncio.Future()

            def handle_response(response):
                nonlocal m3u8_url
                if ".m3u8" in response.url and not m3u8_future.done():
                    print(f"捕获到 m3u8 响应: {response.url} (status={response.status})")
                    m3u8_url = response.url
                    m3u8_responses.append(response)
                    if response.status == 200:
                        m3u8_future.set_result(response.url)

            page.on("response", handle_response)

            # 点击播放按钮触发请求
            try:
                play_btn = await page.query_selector('.plyr__control--overlaid')
                if play_btn:
                    print("点击播放按钮...")
                    await play_btn.click(timeout=5000, force=True)
            except Exception as e:
                print(f"点击播放按钮失败: {e}")

            # 等待 m3u8 200 响应（超时 10s）
            try:
                await asyncio.wait_for(m3u8_future, timeout=10)
            except asyncio.TimeoutError:
                if m3u8_responses:
                    # 有响应但不是 200（如 403），也算捕获到了 URL
                    print(f"m3u8 响应非 200，但仍获取到 URL")
                elif attempt == 0:
                    print("m3u8 捕获超时，刷新页面重试...")
                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2000)
                else:
                    print("m3u8 捕获失败（重试耗尽）")
            finally:
                page.remove_listener("response", handle_response)

            if m3u8_url:
                # 从已捕获的 response 中读取正文
                for resp in m3u8_responses:
                    try:
                        body = await resp.text()
                        if body and body.lstrip('﻿').strip().startswith('#EXTM3U'):
                            m3u8_text = body
                            print(f"m3u8 响应正文已缓存 ({len(m3u8_text)} 字符)")
                            break
                    except Exception:
                        continue
                return {
                    'url': m3u8_url,
                    'text': m3u8_text,
                }

        return {
            'url': None,
            'text': None,
        }


async def create_playwright_segment_fetcher(referer_url: str):
    """创建基于 Playwright 浏览器的视频分片下载器。

    当 CDN（如 surrit.com）受 Cloudflare 防护时，httpx 请求会被 TLS 指纹检测拦截（403）。
    此时通过真实浏览器执行 fetch() 来下载分片，利用浏览器的 TLS 指纹和已有的
    Cloudflare 通关状态绕过防护。

    该函数会导航到来源页面并点击播放按钮，以触发 CDN 的 Cloudflare 验证流程，
    确保后续 fetch() 调用能够通过 CF 防护。

    Returns:
        (fetch_func, cleanup_func)
        fetch_func(url: str) -> bytes: 下载单个分片，返回字节数据
        cleanup_func(): 关闭浏览器资源
    """
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled'],
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    """)

    page = await context.new_page()

    # 访问来源页面并点击播放按钮，以触发 CDN 的 Cloudflare 验证
    print(f"[BrowserFetcher] 正在访问来源页面以建立 Cloudflare 会话: {referer_url}")
    cdn_clearance_ready = asyncio.Future()

    def _on_cdn_response(response):
        """监听 CDN 响应：当收到 m3u8 或视频分片的 200 响应时，说明 CF 已通关。"""
        if not cdn_clearance_ready.done() and response.status == 200:
            url_lower = response.url.lower()
            if any(ext in url_lower for ext in ('.m3u8', '.jpeg', '.ts', '.mp4')):
                print(f"[BrowserFetcher] CDN Cloudflare 已通关 (响应: {response.url[:80]}...)")
                cdn_clearance_ready.set_result(True)

    page.on("response", _on_cdn_response)

    try:
        await page.goto(referer_url, wait_until='domcontentloaded', timeout=60000)

        # 处理可能的 Cloudflare 质询
        cf_titles = ("Just a moment...", "Attention Required", "Checking your browser")
        try:
            title = await page.title()
            if title in cf_titles:
                print(f"[BrowserFetcher] 检测到 CF 质询 ({title})，等待...")
                await page.wait_for_function(
                    f"document.title !== '{title}'",
                    timeout=30000
                )
                print("[BrowserFetcher] CF 质询已通过")
                await page.wait_for_timeout(3000)
        except Exception:
            pass

        # 点击播放按钮触发 m3u8 请求（进而触发 surrit.com 的 CF 验证）
        try:
            play_btn = await page.query_selector('.plyr__control--overlaid')
            if play_btn:
                print("[BrowserFetcher] 点击播放按钮以触发 CDN 请求...")
                await play_btn.click(timeout=5000, force=True)
        except Exception as e:
            print(f"[BrowserFetcher] 播放按钮点击失败: {e}")

        # 等待 CDN 请求完成（最多等 15 秒）
        try:
            await asyncio.wait_for(cdn_clearance_ready, timeout=15)
        except asyncio.TimeoutError:
            print("[BrowserFetcher] CDN 响应等待超时，继续尝试（fetch 时可能仍需 CF 验证）")

    except Exception as e:
        print(f"[BrowserFetcher] 来源页面加载异常: {e}")
    finally:
        page.remove_listener("response", _on_cdn_response)

    async def fetch_segment(url: str) -> bytes:
        """通过浏览器 fetch API 下载单个分片，返回字节数据。"""
        import base64
        js_code = """
            async (url) => {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 30000);
                try {
                    const response = await fetch(url, {
                        signal: controller.signal,
                        headers: { 'Accept-Encoding': 'identity' }
                    });
                    clearTimeout(timeout);
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    const buffer = await response.arrayBuffer();
                    const bytes = new Uint8Array(buffer);
                    // 转为 base64 以便通过 JS 桥传回 Python
                    let binary = '';
                    for (let i = 0; i < bytes.length; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return btoa(binary);
                } finally {
                    clearTimeout(timeout);
                }
            }
        """
        try:
            b64_result = await page.evaluate(js_code, url)
            return base64.b64decode(b64_result)
        except Exception as e:
            raise RuntimeError(f"浏览器下载分片失败: {url} ({e})") from e

    async def cleanup():
        try:
            await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass

    return fetch_segment, cleanup


async def _refresh_cf_clearance(page, referer_url: str) -> bool:
    """刷新页面以重新通过 Cloudflare 验证，恢复对 CDN 的访问权限。

    当长时间下载导致 cf_clearance cookie 过期后，需要重新加载来源页面
    并等待 CDN 请求通过 CF 验证。返回是否成功刷新。
    """
    try:
        print(f"  [CF Refresh] 重新加载页面以刷新 Cloudflare 会话: {referer_url}")
        await page.goto(referer_url, wait_until='domcontentloaded', timeout=30000)

        # 处理页面自身的 CF 质询
        cf_titles = ("Just a moment...", "Attention Required", "Checking your browser")
        try:
            title = await page.title()
            if title in cf_titles:
                await page.wait_for_function(
                    f"document.title !== '{title}'",
                    timeout=30000
                )
                await page.wait_for_timeout(3000)
        except Exception:
            pass

        # 点击播放按钮触发 CDN 请求以刷新 CF cookie
        try:
            play_btn = await page.query_selector('.plyr__control--overlaid')
            if play_btn:
                await play_btn.click(timeout=5000, force=True)
        except Exception:
            pass

        # 等待首次成功的 CDN 响应（m3u8 或分片）
        cf_passed = asyncio.Future()

        def _on_cf_response(response):
            if not cf_passed.done() and response.status in (200, 206):
                url_lower = response.url.lower()
                if any(ext in url_lower for ext in ('.m3u8', '.jpeg', '.ts')):
                    cf_passed.set_result(True)

        page.on("response", _on_cf_response)
        try:
            await asyncio.wait_for(cf_passed, timeout=20)
            print(f"  [CF Refresh] Cloudflare 会话已刷新")
            return True
        except asyncio.TimeoutError:
            print(f"  [CF Refresh] 等待 CDN 响应超时")
            return False
        finally:
            page.remove_listener("response", _on_cf_response)

    except Exception as e:
        print(f"  [CF Refresh] 刷新失败: {e}")
        return False


async def _browser_fetch_bytes(page, url: str, referer_url: str = "") -> bytes:
    """通过 Playwright 页面执行 fetch() 下载资源，返回字节数据。

    利用浏览器已有的 Cookie 和 TLS 指纹绕过 Cloudflare 防护，
    通过 base64 编码在 JS 桥和 Python 之间传输二进制数据。

    当 fetch 遇到 403 时，自动刷新页面以重新通过 Cloudflare 验证后重试。
    """
    import base64
    js_code = """
        async (url) => {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 30000);
            try {
                const response = await fetch(url, {
                    signal: controller.signal,
                    headers: { 'Accept-Encoding': 'identity' }
                });
                clearTimeout(timeout);
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status + ': ' + response.statusText);
                }
                const buffer = await response.arrayBuffer();
                const bytes = new Uint8Array(buffer);
                // 转为 base64 以便通过 JS 桥传回 Python
                let binary = '';
                for (let i = 0; i < bytes.length; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return btoa(binary);
            } finally {
                clearTimeout(timeout);
            }
        }
    """

    last_exc = None
    for attempt in range(2):
        try:
            b64_result = await page.evaluate(js_code, url)
            return base64.b64decode(b64_result)
        except Exception as e:
            last_exc = e
            is_403 = '403' in str(e) or 'status' in str(e).lower()
            if is_403 and referer_url and attempt == 0:
                print(f"  [BrowserPage] fetch 403，尝试刷新 Cloudflare 会话...")
                refreshed = await _refresh_cf_clearance(page, referer_url)
                if refreshed:
                    continue
            # 非 403 或刷新失败，不再重试
            break

    raise RuntimeError(f"浏览器 fetch 失败: {url} ({last_exc})") from last_exc


class VideoDownloader:
    """视频下载器"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        self._paused_tasks: set[str] = set()
        self._max_concurrent: int = 10
        self._proxy: str | None = None

    def set_concurrent(self, max_concurrent: int):
        """设置最大并发数"""
        self._max_concurrent = max(1, min(max_concurrent, 20))  # 限制在 1-20 之间
        print(f"设置最大并发数: {self._max_concurrent}")

    def set_proxy(self, proxy: str | None):
        """设置代理"""
        self._proxy = proxy if proxy else None
        if self._proxy:
            print(f"设置代理: {self._proxy}")

    async def download_video(
        self,
        m3u8_url: str,
        referer: str,
        output_path: str,
        progress_callback=None,
        auto_merge: bool = True,
        keep_temp_files: bool = False,
        session_cookies: list[dict] | None = None,
        m3u8_text: str | None = None,
        merge_timeout_seconds: float = 1800,
        segment_fetcher=None,
        browser_page=None,
    ) -> str:
        """
        下载 m3u8 视频并合并为 mp4

        Args:
            m3u8_url: m3u8 播放列表 URL
            referer: 来源页面 URL
            output_path: 输出文件路径
            progress_callback: 进度回调函数 (progress: float, speed: str, phase: str, detail: str) -> None

        Returns:
            输出文件路径
        """
        output = Path(output_path)
        temp_dir = output.parent / f".temp_{int(time.time())}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        browser_fetcher_cleanup = None

        try:
            # 1. 下载 m3u8 文件
            print(f"下载 m3u8: {m3u8_url}")
            print(f"使用并发数: {self._max_concurrent}, 代理: {self._proxy}")

            # 创建 httpx 客户端，支持代理
            client_kwargs = {
                'headers': {**self.headers, 'Referer': referer},
                'timeout': 30
            }
            if self._proxy:
                client_kwargs['proxy'] = self._proxy
            if session_cookies:
                client_kwargs['cookies'] = {
                    cookie['name']: cookie['value']
                    for cookie in session_cookies
                    if cookie.get('name') and cookie.get('value') is not None
                }

            async with httpx.AsyncClient(**client_kwargs) as client:
                if m3u8_text:
                    playlist_content = m3u8_text
                else:
                    m3u8_resp = None
                    last_m3u8_exc = None
                    # 先尝试 httpx 下载 m3u8（最多 2 次）
                    for _ in range(2):
                        try:
                            m3u8_resp = await client.get(m3u8_url)
                            m3u8_resp.raise_for_status()
                            break
                        except Exception as exc:
                            last_m3u8_exc = exc
                            # 403 时提前退出，不走无意义的 httpx 重试
                            if '403' in str(exc):
                                break
                            await asyncio.sleep(1.0)

                    if m3u8_resp is not None:
                        playlist_content = m3u8_resp.text
                    elif segment_fetcher is not None:
                        # 回退：通过浏览器下载 m3u8（绕过 Cloudflare）
                        print(f"  [BrowserFetcher] 回退浏览器下载 m3u8: {m3u8_url}")
                        try:
                            m3u8_bytes = await segment_fetcher(m3u8_url)
                            playlist_content = m3u8_bytes.decode('utf-8')
                        except Exception as fetcher_exc:
                            raise RuntimeError(f"浏览器下载 m3u8 也失败: {fetcher_exc}") from fetcher_exc
                    else:
                        raise last_m3u8_exc

                normalized_playlist = playlist_content.lstrip('\ufeff').strip()
                if not normalized_playlist.startswith('#EXTM3U'):
                    snippet = normalized_playlist[:200].replace('\n', ' ')
                    raise RuntimeError(f"m3u8 内容无效，疑似被拦截: {snippet}")

                # 下载远程分片到本地 .ts 文件，再让 ffmpeg 合并本地播放列表。
                # 部分站点把 TS 分片伪装成 .jpeg，ffmpeg HLS 会拒绝这种扩展名。
                local_m3u8 = temp_dir / "playlist.m3u8"
                local_playlist_lines: list[str] = []
                segment_urls: list[str] = []
                segment_files: list[str] = []
                for index, line in enumerate(playlist_content.splitlines()):
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'):
                        local_playlist_lines.append(line)
                        continue
                    segment_url = urljoin(m3u8_url, stripped)
                    segment_urls.append(segment_url)
                    source_name = Path(urlparse(segment_url).path).name or f"segment{index}"
                    safe_name = Path(source_name).with_suffix('.ts').name
                    segment_files.append(safe_name)
                    local_playlist_lines.append(safe_name)
                local_m3u8.write_text("\n".join(local_playlist_lines), encoding='utf-8')
                total_segments = len(segment_urls)
                print(f"发现 {total_segments} 个视频片段")

                downloaded = 0
                sem = asyncio.Semaphore(self._max_concurrent)
                fallback_segment_fetcher = segment_fetcher
                fallback_fetcher_lock = asyncio.Lock()

                async def download_segment(seg_url: str, file_name: str):
                    nonlocal downloaded, fallback_segment_fetcher, browser_fetcher_cleanup
                    async with sem:
                        # 优先使用浏览器页面下载（绕过 Cloudflare TLS 指纹检测）
                        if browser_page is not None:
                            try:
                                segment_data = await _browser_fetch_bytes(browser_page, seg_url, referer)
                                (temp_dir / file_name).write_bytes(segment_data)
                                downloaded += 1
                                if progress_callback:
                                    try:
                                        progress_callback(
                                            downloaded / total_segments * 50,
                                            f"{downloaded}/{total_segments}",
                                            'download_segments',
                                            f"正在下载分片(浏览器) {downloaded}/{total_segments}",
                                        )
                                    except TypeError:
                                        progress_callback(downloaded / total_segments * 50, f"{downloaded}/{total_segments}")
                                return
                            except Exception as exc:
                                print(f"  [BrowserPage] 浏览器下载分片失败，回退 httpx: {seg_url} ({exc})")

                        # httpx 直接下载（最多 2 次）
                        last_seg_exc = None
                        for retry in range(2):
                            try:
                                resp = await client.get(seg_url, timeout=30)
                                resp.raise_for_status()
                                (temp_dir / file_name).write_bytes(resp.content)
                                downloaded += 1
                                if progress_callback:
                                    try:
                                        progress_callback(
                                            downloaded / total_segments * 50,
                                            f"{downloaded}/{total_segments}",
                                            'download_segments',
                                            f"正在下载分片 {downloaded}/{total_segments}",
                                        )
                                    except TypeError:
                                        progress_callback(downloaded / total_segments * 50, f"{downloaded}/{total_segments}")
                                return
                            except Exception as exc:
                                last_seg_exc = exc
                                # 遇到 403（Cloudflare），不再重试 httpx
                                if '403' in str(exc):
                                    break
                                await asyncio.sleep(0.5)

                        # 回退：通过外部 segment_fetcher 回调（测试用/自定义下载器）
                        if fallback_segment_fetcher is None and last_seg_exc is not None and '403' in str(last_seg_exc):
                            async with fallback_fetcher_lock:
                                if fallback_segment_fetcher is None:
                                    try:
                                        print(f"  [BrowserFetcher] 创建浏览器分片下载器: {referer}")
                                        fallback_segment_fetcher, browser_fetcher_cleanup = await create_playwright_segment_fetcher(referer)
                                    except Exception as fetcher_create_exc:
                                        last_seg_exc = fetcher_create_exc

                        if fallback_segment_fetcher and last_seg_exc is not None:
                            try:
                                print(f"  [SegmentFetcher] 回退自定义下载器: {seg_url}")
                                segment_data = await fallback_segment_fetcher(seg_url)
                                (temp_dir / file_name).write_bytes(segment_data)
                                downloaded += 1
                                if progress_callback:
                                    try:
                                        progress_callback(
                                            downloaded / total_segments * 50,
                                            f"{downloaded}/{total_segments}",
                                            'download_segments',
                                            f"正在下载分片(回退) {downloaded}/{total_segments}",
                                        )
                                    except TypeError:
                                        progress_callback(downloaded / total_segments * 50, f"{downloaded}/{total_segments}")
                                return
                            except Exception as fetcher_exc:
                                last_seg_exc = fetcher_exc

                        raise RuntimeError(f"下载分片失败: {seg_url} ({last_seg_exc})")

                await asyncio.gather(
                    *[
                        download_segment(seg_url, file_name)
                        for seg_url, file_name in zip(segment_urls, segment_files)
                    ]
                )
                print("所有片段下载完成")

            if auto_merge:
                # 4. 使用 ffmpeg 合并
                print(f"合并视频到: {output}")
                if progress_callback:
                    try:
                        progress_callback(50, '合并中...', 'merging', str(temp_dir))
                    except TypeError:
                        progress_callback(50, '合并中...')
                # 分片已全部下载到本地 .ts 文件，本地播放列表无需 HTTP 请求头
                ffmpeg_cmd = [
                    'ffmpeg', '-hide_banner', '-loglevel', 'error',
                    '-allowed_extensions', 'ALL',
                    '-i', str(local_m3u8),
                    '-c', 'copy',
                    '-bsf:a', 'aac_adtstoasc',
                    '-y', str(output)
                ]

                process = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                try:
                    _, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=merge_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                        await process.wait()
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"ffmpeg 合并超时（{merge_timeout_seconds:g} 秒），"
                        f"可能是远程分片无法访问或被站点拦截；临时播放列表: {local_m3u8}"
                    )

                if process.returncode != 0:
                    stderr_text = stderr.decode(errors='replace')[:2000]
                    raise RuntimeError(f"ffmpeg 合并失败: {stderr_text}")

                print(f"视频合并完成: {output}")
            else:
                # 不合并，直接返回第一个片段路径
                print("跳过合并，保留原始片段")
                import shutil
                output_dir = output.parent / f"{output.stem}_segments"
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                shutil.copytree(temp_dir, output_dir)
                output = output_dir / "playlist.m3u8"

            if progress_callback:
                try:
                    progress_callback(100, '完成', None, str(temp_dir))
                except TypeError:
                    progress_callback(100, '完成')

            return str(output)

        finally:
            if browser_fetcher_cleanup:
                try:
                    await browser_fetcher_cleanup()
                except Exception as cleanup_err:
                    print(f"[BrowserFetcher] 清理异常: {cleanup_err}")
            # 清理临时目录
            import shutil
            if not keep_temp_files:
                shutil.rmtree(temp_dir, ignore_errors=True)
            else:
                print(f"保留临时文件: {temp_dir}")

    async def download_direct_mp4(
        self,
        video_url: str,
        referer: str,
        output_path: str,
        progress_callback=None,
    ) -> str:
        """直接下载 MP4 文件（支持 301/302 跳转）。"""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        client_kwargs = {
            'headers': {**self.headers, 'Referer': referer},
            "timeout": httpx.Timeout(30.0, read=300.0),
            "follow_redirects": True,
        }
        if self._proxy:
            client_kwargs['proxy'] = self._proxy

        print(f"下载直连 MP4: {video_url}")
        async with httpx.AsyncClient(**client_kwargs) as client:
            async with client.stream('GET', video_url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 1024 * 256
                with open(output, 'wb') as f:
                    async for chunk in resp.aiter_bytes(chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total > 0:
                            pct = downloaded / total * 100
                            mb = downloaded / 1024 / 1024
                            total_mb = total / 1024 / 1024
                            detail = f"正在下载视频 {mb:.1f}/{total_mb:.1f} MB"
                            try:
                                progress_callback(pct, f'{mb:.1f} MB', 'downloading', detail)
                            except TypeError:
                                progress_callback(pct, f'{mb:.1f} MB')

        print(f"视频下载完成: {output} ({downloaded / 1024 / 1024:.1f} MB)")
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
crawler = MissavCrawler()
downloader = VideoDownloader()
