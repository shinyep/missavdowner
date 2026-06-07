"""
MissAV 视频爬虫核心模块
从 missav.ws 提取视频信息和下载链接
"""
import asyncio`nimport traceback
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page


class MissavCrawler:
    """MissAV 视频爬虫"""

    BASE_URL = "https://missav.ws/"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.BASE_URL,
        }

    async def parse_video(self, url: str) -> dict:
        """
        解析视频页面，提取视频信息

        Args:
            url: missav 视频页面 URL

        Returns:
            包含视频信息的字典
        """
        print(f"[LOG][parse_video] START parsing: {url}")
        print(f"[LOG][parse_video] Launching browser...")
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
                print(f"[LOG][parse_video] Browser launched successfully")
            except Exception as e:
                print(f"[LOG][parse_video] Browser launch FAILED: {e}")
                raise

            context = await browser.new_context(
                user_agent=self.headers['User-Agent'],
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            print(f"[LOG][parse_video] Page created")

            try:
                # 导航到页面
                print(f"[LOG][parse_video] Navigating to: {url}")
                try:
                    resp = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                    print(f"[LOG][parse_video] Navigation response status: {resp.status if resp else 'None'}")
                    print(f"[LOG][parse_video] Current URL after nav: {await page.url()}")
                except Exception as e:
                    print(f"[LOG][parse_video] Navigation FAILED: {e}")
                    # Try to get page content anyway
                    try:
                        print(f"[LOG][parse_video] Page title after nav error: {await page.title()}")
                    except:
                        pass
                    raise

                # 检查 Cloudflare 质询
                cf_challenge = await page.query_selector("#challenge-running")
                if cf_challenge:
                    print("[LOG][parse_video] Cloudflare challenge detected, waiting...")
                    try:
                        await page.wait_for_selector('body:not(#challenge-running)', timeout=30000)
                        print("[LOG][parse_video] Cloudflare challenge passed")
                    except Exception as e:
                        print(f"[LOG][parse_video] Cloudflare wait FAILED: {e}")

                # 提取标题
                print("[LOG][parse_video] Extracting title...")
                title = await self._extract_title(page)
                print(f"[LOG][parse_video] Title result: {title}")

                # 提取封面图
                print("[LOG][parse_video] Extracting cover...")
                cover = await self._extract_cover(page)
                print(f"[LOG][parse_video] Cover result: {cover[:100] if cover else 'EMPTY'}")

                # 提取元数据
                print("[LOG][parse_video] Extracting metadata...")
                metadata = await self._extract_metadata(page)
                print(f"[LOG][parse_video] Metadata result: {metadata}")

                # 监听 m3u8 请求
                print("[LOG][parse_video] Capturing m3u8...")
                m3u8_url = await self._capture_m3u8(page, url)
                print(f"[LOG][parse_video] m3u8_url result: {m3u8_url}")

                result = {
                    'title': title,
                    'cover': cover,
                    'm3u8_url': m3u8_url,
                    **metadata
                }
                print(f"[LOG][parse_video] DONE - returning result")
                return result

            except Exception as e:
                print(f"[LOG][parse_video] UNHANDLED ERROR in parse_video: {e}")
                import traceback
                traceback.print_exc()
                raise

            finally:
                await browser.close()

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
        """捕获页面发起的 m3u8 请求"""
        print(f"[LOG][capture_m3u8] START - setting up request listener")
        m3u8_url = None
        m3u8_future = asyncio.Future()

        # Also log ALL requests for debugging
        all_requests = []
        def log_all_requests(request):
            all_requests.append(request.url)

        def handle_request(request):
            nonlocal m3u8_url
            log_all_requests(request)
            if ".m3u8" in request.url and not m3u8_future.done():
                print(f"[LOG][capture_m3u8] M3U8 FOUND: {request.url}")
                m3u8_url = request.url
                m3u8_future.set_result(request.url)

        page.on("request", handle_request)
        print(f"[LOG][capture_m3u8] Request listener registered")

        # Dump page info
        try:
            page_title = await page.title()
            page_url = page.url
            print(f"[LOG][capture_m3u8] Page title: {page_title}")
            print(f"[LOG][capture_m3u8] Page url: {page_url}")

            # Check available video/play selectors
            selectors_to_check = [
                '.plyr__control--overlaid',
                'video',
                'video source',
                '.plyr',
                '.video-js',
                '[data-plyr]',
                'button[aria-label="Play"]',
                '.play-button',
            ]
            for sel in selectors_to_check:
                el = await page.query_selector(sel)
                if el:
                    attrs = {}
                    try:
                        for attr in ['src', 'data-plyr-embed-id', 'data-video-id', 'poster', 'class']:
                            val = await el.get_attribute(attr)
                            if val:
                                attrs[attr] = val
                    except:
                        pass
                    print(f"[LOG][capture_m3u8] Found element: {sel} attrs={attrs}")
        except Exception as e:
            print(f"[LOG][capture_m3u8] Error checking page state: {e}")

        # 尝试点击播放按钮
        print(f"[LOG][capture_m3u8] Looking for play button...")
        try:
            play_btn = await page.query_selector('.plyr__control--overlaid')
            if play_btn:
                print(f"[LOG][capture_m3u8] Play button found, clicking...")
                await play_btn.click(timeout=5000, force=True)
                print(f"[LOG][capture_m3u8] Play button clicked")
                # Wait a bit for requests to fire
                await asyncio.sleep(2)
            else:
                print(f"[LOG][capture_m3u8] Play button NOT found (.plyr__control--overlaid)")
                # Try clicking the video element directly
                video_el = await page.query_selector('video')
                if video_el:
                    print(f"[LOG][capture_m3u8] Trying to click video element...")
                    await video_el.click(timeout=5000, force=True)
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"[LOG][capture_m3u8] Play button click FAILED: {e}")

        # Log all requests seen so far
        print(f"[LOG][capture_m3u8] Total requests captured: {len(all_requests)}")
        m3u8_requests = [r for r in all_requests if '.m3u8' in r]
        video_requests = [r for r in all_requests if any(x in r.lower() for x in ['.mp4', '.m3u8', '.ts', 'video', 'hls'])]
        print(f"[LOG][capture_m3u8] m3u8 requests: {m3u8_requests}")
        print(f"[LOG][capture_m3u8] Video-related requests: {video_requests}")

        # 等待 m3u8 请求
        try:
            print(f"[LOG][capture_m3u8] Waiting for m3u8 request (timeout=20s)...")
            await asyncio.wait_for(m3u8_future, timeout=20)
            print(f"[LOG][capture_m3u8] M3U8 captured successfully")
        except asyncio.TimeoutError:
            print(f"[LOG][capture_m3u8] TIMEOUT: No m3u8 request detected within 20s")
            # Dump final request list
            new_requests = [r for r in all_requests if '.m3u8' in r]
            print(f"[LOG][capture_m3u8] Final m3u8 requests: {new_requests}")
            print(f"[LOG][capture_m3u8] Total requests: {len(all_requests)}")
        finally:
            page.remove_listener("request", handle_request)

        print(f"[LOG][capture_m3u8] RETURNING: {m3u8_url}")
        return m3u8_url


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
            progress_callback: 进度回调函数 (progress: float, speed: str) -> None

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
                m3u8_resp = await client.get(m3u8_url)
                m3u8_resp.raise_for_status()
                playlist_content = m3u8_resp.text

                # 修复 m3u8 内容（.jpeg -> .ts）
                fixed_content = playlist_content.replace('.jpeg', '.ts')
                local_m3u8 = temp_dir / "playlist.m3u8"
                local_m3u8.write_text(fixed_content)

                # 2. 解析所有片段 URL
                segment_urls = [
                    urljoin(m3u8_url, line.strip())
                    for line in playlist_content.splitlines()
                    if line.strip() and not line.startswith('#')
                ]
                total_segments = len(segment_urls)
                print(f"发现 {total_segments} 个视频片段")

                # 3. 并发下载所有片段
                downloaded = 0
                sem = asyncio.Semaphore(self._max_concurrent)

                async def download_segment(seg_url: str):
                    nonlocal downloaded
                    async with sem:
                        try:
                            resp = await client.get(seg_url, headers={**self.headers, 'Referer': referer}, timeout=30)
                            if resp.status_code == 200:
                                filename = Path(urlparse(seg_url).path).name.replace('.jpeg', '.ts')
                                (temp_dir / filename).write_bytes(resp.content)
                                downloaded += 1
                                if progress_callback:
                                    progress_callback(downloaded / total_segments * 50, f"{downloaded}/{total_segments}")
                        except Exception as e:
                            print(f"下载片段失败: {e}")

                tasks = [download_segment(url) for url in segment_urls]
                await asyncio.gather(*tasks)
                print("所有片段下载完成")

            if auto_merge:
                # 4. 使用 ffmpeg 合并
                print(f"合并视频到: {output}")
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
                progress_callback(100, "完成")

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

