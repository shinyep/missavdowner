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
        """解析视频页面，提取视频信息。复用浏览器实例 + 并行提取元数据。"""
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
            m3u8_url = await self._capture_m3u8(page, url)

            return {
                'title': title,
                'cover': cover,
                'm3u8_url': m3u8_url,
                **metadata
            }

        finally:
            await context.close()

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

    async def _capture_m3u8(self, page: Page, referer: str) -> str | None:
        """捕获页面发起的 m3u8 请求。缩短超时 + 重试一次。"""
        for attempt in range(2):
            m3u8_url = None
            m3u8_future = asyncio.Future()

            def handle_request(request):
                nonlocal m3u8_url
                if ".m3u8" in request.url and not m3u8_future.done():
                    print(f"捕获到 m3u8 请求: {request.url}")
                    m3u8_url = request.url
                    m3u8_future.set_result(request.url)

            page.on("request", handle_request)

            # 点击播放按钮触发请求
            try:
                play_btn = await page.query_selector('.plyr__control--overlaid')
                if play_btn:
                    print("点击播放按钮...")
                    await play_btn.click(timeout=5000, force=True)
            except Exception as e:
                print(f"点击播放按钮失败: {e}")

            # 等待 m3u8（超时从 20s 缩短到 10s）
            try:
                await asyncio.wait_for(m3u8_future, timeout=10)
            except asyncio.TimeoutError:
                if attempt == 0:
                    print("m3u8 捕获超时，刷新页面重试...")
                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2000)
                else:
                    print("m3u8 捕获失败（重试耗尽）")
            finally:
                page.remove_listener("request", handle_request)

            if m3u8_url:
                return m3u8_url

        return None


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
        keep_temp_files: bool = False
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

            async with httpx.AsyncClient(**client_kwargs) as client:
                m3u8_resp = None
                last_m3u8_exc = None
                for _ in range(3):
                    try:
                        m3u8_resp = await client.get(m3u8_url)
                        m3u8_resp.raise_for_status()
                        break
                    except Exception as exc:
                        last_m3u8_exc = exc
                        await asyncio.sleep(1.0)
                if m3u8_resp is None:
                    raise last_m3u8_exc
                playlist_content = m3u8_resp.text

                # 2. 解析所有片段 URL
                segment_urls = [
                    urljoin(m3u8_url, line.strip())
                    for line in playlist_content.splitlines()
                    if line.strip() and not line.startswith('#')
                ]
                total_segments = len(segment_urls)
                print(f"发现 {total_segments} 个视频片段")

                # 生成指向本地分片文件的 m3u8，供 ffmpeg 离线合并。
                local_playlist_lines: list[str] = []
                for line in playlist_content.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'):
                        local_playlist_lines.append(line)
                        continue
                    filename = Path(urlparse(urljoin(m3u8_url, stripped)).path).name.replace('.jpeg', '.ts')
                    local_playlist_lines.append(filename)
                local_m3u8 = temp_dir / "playlist.m3u8"
                local_m3u8.write_text("\n".join(local_playlist_lines), encoding='utf-8')

                # 3. 并发下载所有片段
                downloaded = 0
                sem = asyncio.Semaphore(self._max_concurrent)

                async def download_segment(seg_url: str):
                    nonlocal downloaded
                    async with sem:
                        last_seg_exc = None
                        for _ in range(3):
                            try:
                                resp = await client.get(seg_url, headers={**self.headers, 'Referer': referer}, timeout=30)
                                if resp.status_code == 200:
                                    filename = Path(urlparse(seg_url).path).name.replace('.jpeg', '.ts')
                                    (temp_dir / filename).write_bytes(resp.content)
                                    downloaded += 1
                                    if progress_callback:
                                        try:
                                            progress_callback(downloaded / total_segments * 50, f"{downloaded}/{total_segments}", 'download_segments')
                                        except TypeError:
                                            progress_callback(downloaded / total_segments * 50, f"{downloaded}/{total_segments}")
                                    return
                            except Exception as exc:
                                last_seg_exc = exc
                                await asyncio.sleep(0.5)
                        print(f"下载片段失败: {last_seg_exc}")

                tasks = [download_segment(url) for url in segment_urls]
                await asyncio.gather(*tasks)
                print("所有片段下载完成")

            if auto_merge:
                # 4. 使用 ffmpeg 合并
                print(f"合并视频到: {output}")
                if progress_callback:
                    try:
                        progress_callback(50, '合并中...', 'merging', str(temp_dir))
                    except TypeError:
                        progress_callback(50, '合并中...')
                ffmpeg_cmd = [
                    'ffmpeg', '-hide_banner', '-loglevel', 'error',
                    '-protocol_whitelist', 'file,pipe',
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

                _, stderr = await process.communicate()

                if process.returncode != 0:
                    raise RuntimeError(f"ffmpeg 合并失败: {stderr.decode()}")

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
            # 清理临时目录
            import shutil
            if not keep_temp_files:
                shutil.rmtree(temp_dir, ignore_errors=True)
            else:
                print(f"保留临时文件: {temp_dir}")

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
