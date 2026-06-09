# -*- coding: utf-8 -*-
"""
图片图集爬虫模块。

参考 F:\novel 的 image_4khd / image_kkc3 管理命令，实现 4khd/szzs/kkc3 图集 URL 转换、
分页提取、图片下载，并保留通用图片站点的基础提取能力。
"""
import asyncio
import html
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx
import inspect
from bs4 import BeautifulSoup

try:
    from PIL import Image, UnidentifiedImageError
except Exception:  # pragma: no cover - Pillow 缺失时仍允许下载原始文件
    Image = None
    UnidentifiedImageError = Exception

try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - 运行环境未安装 playwright 时使用 httpx 兜底
    async_playwright = None

ProgressCallback = Callable[[float, str, str | None, str | None, dict | None], None]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".jfif")

# 图集页面在 www.kkc3.com，实际图片 CDN 在 image.kkc3.com（data-src 已是绝对 URL）
KKC3_BASE_URL = "https://www.kkc3.com/"

BUONdua_BASE_URL = "https://buondua.com/"


@dataclass
class GalleryParseResult:
    title: str
    page_url: str
    image_urls: list[str]


class ImageGalleryCrawler:
    def __init__(self, proxy: str = ""):
        self.proxy = proxy.strip() or None

    def _client_options(self, headers: dict[str, str]) -> dict:
        options = {
            "timeout": httpx.Timeout(60.0),
            "follow_redirects": True,
            "headers": headers,
        }
        if self.proxy:
            parameters = inspect.signature(httpx.AsyncClient).parameters
            if "proxy" in parameters:
                options["proxy"] = self.proxy
            elif "proxies" in parameters:
                options["proxies"] = self.proxy
        return options

    async def parse_gallery(self, gallery_url: str) -> GalleryParseResult:
        page_url = self._normalize_gallery_url(gallery_url)

        # kkc3.com 需要 Playwright JS 执行来提取 data-src 属性，走独立解析路径
        if self._is_kkc3_url(page_url):
            return await self._parse_kkc3_gallery(page_url)

        # buondua.com 走 Playwright + BeautifulSoup 解析路径
        if self._is_buondua_url(page_url):
            return await self._parse_buondua_gallery(page_url)

        html = await self._load_page_html(gallery_url, page_url)
        soup = BeautifulSoup(html, "html.parser")
        title = self._extract_gallery_title(soup, page_url)
        image_urls = self._extract_image_urls(soup, page_url)

        for pagination_url in self._extract_pagination_links(soup, page_url):
            try:
                pagination_html = await self._load_page_html(pagination_url, pagination_url)
                pagination_soup = BeautifulSoup(pagination_html, "html.parser")
                image_urls.extend(self._extract_image_urls(pagination_soup, pagination_url))
                await asyncio.sleep(1)
            except Exception:
                continue

        deduped_urls = list(dict.fromkeys(image_urls))
        if not deduped_urls:
            raise RuntimeError("未从图集页面提取到图片链接")

        return GalleryParseResult(title=title, page_url=page_url, image_urls=deduped_urls)

    async def download_gallery(
        self,
        gallery_url: str,
        output_dir: str,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        started_at = time.time()
        self._notify(progress_callback, 0, "0 张/秒", "parsing", "正在解析图集页面")
        parsed = await self.parse_gallery(gallery_url)

        safe_title = self._safe_filename(parsed.title)
        gallery_dir = Path(output_dir).expanduser().resolve() / safe_title
        gallery_dir.mkdir(parents=True, exist_ok=True)

        saved_paths: list[str] = []
        failed_count = 0
        total = len(parsed.image_urls)
        self._notify(progress_callback, 0, "0 张/秒", "downloading", f"共发现 {total} 张图片，开始下载", {
            "total_images": total, "current_index": 0, "success_count": 0, "failed_count": 0, "title": parsed.title,
        })

        async with httpx.AsyncClient(
            **self._client_options({"User-Agent": USER_AGENT, "Referer": parsed.page_url})
        ) as client:
            for index, image_url in enumerate(parsed.image_urls, start=1):
                detail = f"正在下载第 {index}/{total} 张图片"
                try:
                    image_bytes = await self._download_image(client, image_url, parsed.page_url)
                    ext = self._detect_extension(image_url, image_bytes)
                    filename = f"{index:03d}{ext}"
                    image_path = gallery_dir / filename
                    image_path.write_bytes(image_bytes)
                    saved_paths.append(str(image_path))
                except Exception as exc:
                    failed_count += 1
                    detail = f"第 {index}/{total} 张下载失败：{str(exc)[:60]}"

                elapsed = max(time.time() - started_at, 0.1)
                speed = f"{len(saved_paths) / elapsed:.2f} 张/秒"
                self._notify(progress_callback, index / total * 100, speed, "downloading", detail, {
                    "total_images": total, "current_index": index,
                    "success_count": len(saved_paths), "failed_count": failed_count, "title": parsed.title,
                })
                await asyncio.sleep(0.3)

        if not saved_paths:
            raise RuntimeError("图片下载全部失败")

        return {
            "title": parsed.title,
            "filename": safe_title,
            "output_path": str(gallery_dir),
            "image_count": len(saved_paths),
            "image_paths": saved_paths,
            "source_url": gallery_url,
        }

    async def _load_page_html(self, original_url: str, page_url: str) -> str:
        html = ""
        if async_playwright is not None:
            try:
                html = await self._load_page_html_with_playwright(original_url, page_url)
            except Exception:
                html = ""
        if len(html) < 500:
            html = await self._load_page_html_with_httpx(page_url)
        return html

    async def _load_page_html_with_playwright(self, original_url: str, page_url: str) -> str:
        if async_playwright is None:
            raise RuntimeError("Playwright 不可用")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1365, "height": 900})
            page = await context.new_page()
            try:
                if original_url != page_url:
                    await page.goto(original_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(2500)
                await page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(5000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
                return await page.content()
            finally:
                await context.close()
                await browser.close()

    async def _load_page_html_with_httpx(self, page_url: str) -> str:
        async with httpx.AsyncClient(
            **self._client_options({"User-Agent": USER_AGENT, "Referer": page_url})
        ) as client:
            response = await client.get(page_url)
            response.raise_for_status()
            return response.text

    async def _download_image(self, client: httpx.AsyncClient, image_url: str, referer_url: str) -> bytes:
        response = await client.get(image_url, headers={"Referer": referer_url, "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"})
        response.raise_for_status()
        data = response.content
        if len(data) < 128:
            raise RuntimeError("图片内容过小")
        if Image is not None:
            from io import BytesIO

            try:
                with Image.open(BytesIO(data)) as image:
                    image.verify()
            except UnidentifiedImageError as exc:
                raise RuntimeError("下载内容不是有效图片") from exc
        return data

    def _normalize_gallery_url(self, gallery_url: str) -> str:
        parsed = urlparse(gallery_url)
        if ("szzs.uuss.uk" in parsed.netloc or "4khd" in parsed.netloc) and "/gallery/" in gallery_url:
            return gallery_url.rstrip("/").replace("/gallery/", "/content/") + ".html"
        return gallery_url

    # ---- kkc3.com 专用解析 ----

    @staticmethod
    def _is_kkc3_url(url: str) -> bool:
        """检测是否为 kkc3.com 图集链接"""
        return "kkc3.com" in urlparse(url).netloc

    async def _parse_kkc3_gallery(self, gallery_url: str) -> GalleryParseResult:
        """使用 httpx + BeautifulSoup 解析 kkc3.com 图集。

        kkc3 图片在静态 HTML 的 src/data-src 属性中，无需 Playwright。
        分页通过 a.page-next 链接跟踪。
        """
        all_image_urls: list[str] = []
        seen_urls: set[str] = set()
        gallery_title = ""

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": KKC3_BASE_URL,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        client_options = self._client_options(headers)

        async with httpx.AsyncClient(**client_options) as client:
            current_url = gallery_url
            crawled_urls: set[str] = {current_url.split("#")[0]}
            page_count = 0
            max_pages = 50

            while current_url and page_count < max_pages:
                if page_count > 0:
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                page_count += 1

                # 抓取页面
                html_content = await self._kkc3_fetch(client, current_url)
                soup = BeautifulSoup(html_content, "html.parser")

                # 首页提取标题
                if page_count == 1:
                    gallery_title = self._extract_kkc3_title_from_soup(soup)
                    if not gallery_title:
                        raise RuntimeError("未能从 kkc3 页面提取图集标题")

                # 提取当前页图片
                page_images = self._extract_kkc3_images_from_soup(soup, current_url)
                for img_url in page_images:
                    if img_url not in seen_urls:
                        seen_urls.add(img_url)
                        all_image_urls.append(img_url)

                if not page_images and page_count > 1:
                    break  # 后续页无图即结束

                # 找下一页
                next_link = soup.select_one("a.page-next")
                if next_link and next_link.get("href"):
                    next_url = urljoin(current_url, next_link["href"])
                    clean_next = next_url.split("#")[0]
                    if clean_next in crawled_urls:
                        break
                    crawled_urls.add(clean_next)
                    current_url = next_url
                else:
                    break

            if not all_image_urls:
                raise RuntimeError("未从 kkc3 图集页面提取到图片链接")

            return GalleryParseResult(
                title=gallery_title,
                page_url=gallery_url,
                image_urls=all_image_urls,
            )

    async def _kkc3_fetch(self, client: httpx.AsyncClient, url: str) -> str:
        """用 httpx 抓取 kkc3 页面 HTML"""
        for attempt in range(3):
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp.text
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(random.uniform(1, 3))
                    continue
                raise
        return ""

    def _extract_kkc3_images_from_soup(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """从 BeautifulSoup 提取 kkc3 图片 URL。

        真实 DOM：div.image-loading-box > img[src][data-src][data-photo-num]
        过滤广告容器 .related-files / .ad-container / .cpa-chaturbate
        """
        items: list[dict] = []
        seen: set[str] = set()

        # 主路径：.image-loading-box
        for box in soup.select(".image-loading-box"):
            if box.find_parent(class_="related-files") or box.find_parent(class_="ad-container"):
                continue
            img = box.find("img")
            if not img:
                continue
            url = (img.get("data-src") or img.get("src") or "").strip()
            if not url or url.startswith("data:") or "/jw-photos/" not in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            num = int(img.get("data-photo-num", 0) or 0)
            items.append({"url": url, "num": num})

        # 兜底：直接搜 img[data-src]
        if not items:
            for img in soup.select("img[data-src]"):
                if img.find_parent(class_="related-files") or img.find_parent(class_="ad-container") or img.find_parent(class_="cpa-chaturbate"):
                    continue
                url = (img.get("data-src") or "").strip()
                if not url or url.startswith("data:") or "/jw-photos/" not in url:
                    continue
                if url in seen:
                    continue
                seen.add(url)
                num = int(img.get("data-photo-num", 0) or 0)
                items.append({"url": url, "num": num})

        # 按 data-photo-num 排序保证顺序
        items.sort(key=lambda x: x["num"])
        return [item["url"] for item in items]

    def _extract_kkc3_title_from_soup(self, soup: BeautifulSoup) -> str:
        """从 kkc3 BeautifulSoup 提取标题。优先 h1，回退 <title>。"""
        # 优先 h1
        h1 = soup.select_one("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)

        # 回退 <title>
        title_tag = soup.title
        if title_tag:
            raw = title_tag.get_text(strip=True)
            for sep in (" | 咔咔西三", " - 咔咔西三", " | KKC3", " - KKC3"):
                idx = raw.find(sep)
                if idx > 0:
                    return raw[:idx].strip()
            return raw.strip()

        return ""

    # ---- buondua.com 专用解析 ----

    @staticmethod
    def _is_buondua_url(url: str) -> bool:
        return "buondua.com" in urlparse(url).netloc

    async def _parse_buondua_gallery(self, gallery_url: str) -> GalleryParseResult:
        """使用 httpx + BeautifulSoup 解析 buondua.com 图集。

        buondua 图片在静态 HTML 的 src 属性中，无需 Playwright/JS 执行。
        直接用 httpx 抓取 HTML，速度快 10 倍以上。
        """
        all_image_urls: list[str] = []
        seen_urls: set[str] = set()
        gallery_title = ""

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://buondua.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        client_options = self._client_options(headers)

        async with httpx.AsyncClient(**client_options) as client:
            # 抓取首页
            html_content = await self._buondua_fetch(client, gallery_url)
            soup = BeautifulSoup(html_content, "html.parser")

            if self._is_buondua_blocked(soup):
                raise RuntimeError("buondua.com 访问被拦截，请稍后重试或配置代理")

            gallery_title = self._extract_buondua_title(soup)
            if not gallery_title:
                raise RuntimeError("未能从 buondua 页面提取图集标题")

            # 提取首页图片
            for img_url in self._extract_buondua_images_from_soup(soup, gallery_url):
                if img_url not in seen_urls:
                    seen_urls.add(img_url)
                    all_image_urls.append(img_url)

            # 检测总页数，循环加载
            total_pages = self._detect_buondua_total_pages(gallery_title, html_content, soup)
            base_url_clean = gallery_url.split("?")[0].split("#")[0].rstrip("/")
            max_pages = max(total_pages, 2)
            empty_streak = 0

            for page_num in range(2, max_pages + 10):
                page_url = f"{base_url_clean}?page={page_num}"
                try:
                    await asyncio.sleep(random.uniform(1, 3))
                    page_html = await self._buondua_fetch(client, page_url)
                    page_soup = BeautifulSoup(page_html, "html.parser")
                    if self._is_buondua_blocked(page_soup):
                        break
                    new_count = 0
                    for img_url in self._extract_buondua_images_from_soup(page_soup, gallery_url):
                        if img_url not in seen_urls:
                            seen_urls.add(img_url)
                            all_image_urls.append(img_url)
                            new_count += 1
                    if new_count == 0:
                        empty_streak += 1
                        if empty_streak >= 2:
                            break
                    else:
                        empty_streak = 0
                except Exception:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break

            if not all_image_urls:
                raise RuntimeError("未从 buondua 图集页面提取到图片链接")

            return GalleryParseResult(
                title=gallery_title,
                page_url=gallery_url,
                image_urls=all_image_urls,
            )

    async def _buondua_fetch(self, client: httpx.AsyncClient, url: str) -> str:
        """用 httpx 抓取 buondua 页面 HTML，带重试"""
        for attempt in range(3):
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp.text
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(random.uniform(2, 5))
                    continue
                raise
        return ""

    @staticmethod
    def _is_buondua_blocked(soup: BeautifulSoup) -> bool:
        """检测 buondua 页面是否被反爬拦截"""
        title = soup.title.get_text() if soup.title else ""
        if "blocked" in title.lower() or "access denied" in title.lower():
            return True
        body_text = soup.get_text()[:500]
        if "Sorry, you have been blocked" in body_text:
            return True
        return False

    def _extract_buondua_title(self, soup: BeautifulSoup) -> str:
        """从 buondua 页面提取图集标题，清理站点后缀和页码标记

        原始：'[AI Enhanced] DJAWA Photo: Yudi (유디) – Succubus Princess (39 photos)  - ( Page 1 / 2 )'
        清理后：'[AI Enhanced] DJAWA Photo: Yudi (유디) – Succubus Princess'
        """
        for selector in [".article-header h1", "h1", "title"]:
            el = soup.select_one(selector)
            if el:
                raw = el.get_text(strip=True)
                # 去掉页码后缀：( Page 1 / 2 )
                raw = re.sub(r"\s*[-–]?\s*\(?\s*Page\s+\d+\s*/\s*\d+\s*\)?\s*$", "", raw, flags=re.IGNORECASE)
                # 去掉照片数量后缀：(39 photos)
                raw = re.sub(r"\s*\(\d+\s*[Pp]hotos?\s*\)\s*$", "", raw)
                # 去掉 Buondua 站点名
                raw = re.sub(r"\s*[-–]\s*Buondua\s*$", "", raw)
                raw = html.unescape(raw)
                raw = re.sub(r"\s+", " ", raw).strip()
                if len(raw) > 2:
                    return raw
        return ""

    def _extract_buondua_images_from_soup(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """从 BeautifulSoup 对象中提取 buondua 图片 URL。

        真实 DOM 结构：
          div.article-fulltext > p > img[src][loading="lazy"][referrerPolicy="strict-origin"]
        图片 CDN 域名：cdn.buondua.us / i2.buondua.us / cdn.buondua.com 等
        广告容器：ins.adsbyexoclick / div[class*="Sponsored ads"]
        底部推荐：div.bottom-articles / div.footer
        """
        found: list[str] = []
        seen: set[str] = set()

        # 只从 .article-fulltext 内提取（正文区域）
        content_div = soup.select_one(".article-fulltext")
        if not content_div:
            return found

        for img in content_div.find_all("img"):
            img_src = img.get("src")
            if not img_src:
                continue

            # 过滤占位符和 data URI
            if img_src.startswith("data:"):
                continue

            # 过滤广告 CDN 域名
            lower = img_src.lower()
            if any(ad in lower for ad in ["bkcdn.net", "juicyads", "exoclick", "magsrv"]):
                continue
            if any(ex in lower for ex in [
                "logo", "icon", "avatar", "profile", "banner",
                "header", "footer", "sidebar", "widget",
                "cropped-", "thumbnail", "thumb", "placeholder",
                "loading", "pixel", "sponsor", "adsbyexoclick",
            ]):
                continue

            # 验证图片扩展名（支持查询参数）
            clean = lower.split("?")[0]
            if not any(clean.endswith(ext) for ext in IMAGE_EXTENSIONS):
                continue

            absolute_url = urljoin(base_url, img_src)
            if absolute_url not in seen:
                seen.add(absolute_url)
                found.append(absolute_url)

        return found

    def _detect_buondua_total_pages(self, title: str, html_content: str, soup: BeautifulSoup) -> int:
        """检测 buondua 图集总页数（三种策略）

        标题示例：'[AI Enhanced] DJAWA Photo: Yudi (유디) – Succubus Princess (39 photos)  - ( Page 1 / 2 )'
        """
        total = 1

        # 策略1：从标题中提取（优先精确页码，再估算）
        title_patterns = [
            r"\(\s*Page\s+\d+\s*/\s*(\d+)\s*\)",   # ( Page 1 / 2 )
            r"Page\s+\d+\s*of\s+(\d+)",             # Page 1 of 2
        ]
        for pattern in title_patterns:
            match = re.search(pattern, title or "", re.IGNORECASE)
            if match:
                detected = int(match.group(1))
                if "P\\s*\\)" in pattern:
                    detected = max(1, (detected + 19) // 20)  # 每页约20张
                if detected > total:
                    total = detected
                    break

        # 策略2：从页面内容中提取
        if total == 1:
            for pattern in [r"Page\s+\d+\s*/\s*(\d+)", r"of\s+(\d+)", r"共\s*(\d+)\s*页"]:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    detected = int(match.group(1))
                    if detected > total:
                        total = detected
                        break

        # 策略3：从分页链接中提取
        if total == 1:
            for selector in [".pagination-link", ".pagination a", ".page-link"]:
                for link in soup.select(selector):
                    href = link.get("href", "")
                    page_num = None
                    if "?page=" in href:
                        try:
                            page_num = int(href.split("?page=")[1].split("&")[0])
                        except (ValueError, IndexError):
                            pass
                    elif "/page/" in href:
                        try:
                            page_num = int(href.split("/page/")[1].split("/")[0].split("?")[0])
                        except (ValueError, IndexError):
                            pass
                    if page_num and page_num > total:
                        total = page_num

        return total

    # ---- 通用 HTML 解析 ----

    def _extract_gallery_title(self, soup: BeautifulSoup, page_url: str) -> str:
        selectors = [
            "h3.wp-block-post-title.has-medium-font-size",
            "h3.wp-block-post-title",
            "h1.wp-block-post-title",
            "h1.entry-title",
            "h1.title",
            "h1",
            "title",
        ]
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                title = self._clean_title(element.get_text(" ", strip=True))
                if title:
                    return title

        fallback = urlparse(page_url).path.rstrip("/").split("/")[-1].replace(".html", "")
        return self._clean_title(fallback.replace("-", " ")) or f"gallery_{int(time.time())}"

    def _extract_image_urls(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        containers = [soup.select_one("div#basicExample"), soup]

        link_selectors = [
            "a.imageLink",
            "a[href*='.jpg']",
            "a[href*='.jpeg']",
            "a[href*='.png']",
            "a[href*='.webp']",
            "a[href*='/wp-content/']",
            "a[data-fancybox]",
            "a[data-lightbox]",
        ]
        image_selectors = [
            "img[src]",
            "img[data-src]",
            "img[data-original]",
            "img[data-lazy-src]",
        ]

        for container in containers:
            if container is None:
                continue
            for selector in image_selectors:
                for element in container.select(selector):
                    src = element.get("data-src") or element.get("data-original") or element.get("data-lazy-src") or element.get("src")
                    self._append_image_url(found, seen, page_url, src)
            for selector in link_selectors:
                for element in container.select(selector):
                    href = element.get("href")
                    self._append_image_url(found, seen, page_url, href)
            if found:
                break

        return found

    def _extract_pagination_links(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        links: set[str] = set()
        base = urlparse(page_url)
        allowed_domains = {"szzs.uuss.uk", "www.4khd.com", "4khd.com"}
        allowed_domains.add(base.netloc)
        for element in soup.select("div.page-link-box ul.page-links a.page-numbers, a.page-numbers"):
            href = element.get("href")
            if not href:
                continue
            absolute_url = urljoin(page_url, href)
            parsed = urlparse(absolute_url)
            if parsed.netloc in allowed_domains and absolute_url != page_url:
                links.add(absolute_url)
        return sorted(links)

    def _append_image_url(self, found: list[str], seen: set[str], page_url: str, candidate: str | None) -> None:
        if not candidate or candidate.startswith("data:"):
            return
        if any(token in candidate.lower() for token in ("placeholder", "loading", "avatar", "favicon", "logo", "beautifulgirls", "4khd-beautifulgirls")):
            return
        absolute_url = urljoin(page_url, candidate)
        path = urlparse(absolute_url).path.lower()
        if not path.endswith(IMAGE_EXTENSIONS):
            return
        if absolute_url in seen:
            return
        seen.add(absolute_url)
        found.append(absolute_url)

    def _detect_extension(self, image_url: str, image_bytes: bytes) -> str:
        if Image is not None:
            from io import BytesIO

            try:
                with Image.open(BytesIO(image_bytes)) as image:
                    image_format = (image.format or "").lower()
                    if image_format in {"jpeg", "jpg"}:
                        return ".jpg"
                    if image_format in {"png", "webp", "gif", "bmp", "tiff"}:
                        return f".{image_format}"
            except Exception:
                pass

        ext = os.path.splitext(urlparse(image_url).path)[1].lower()
        return ext if ext in IMAGE_EXTENSIONS else ".jpg"

    def _clean_title(self, raw_title: str | None) -> str | None:
        if not raw_title:
            return None
        title = raw_title.strip()
        title = re.sub(r"\s*-\s*Page\s+\d+\s+of\s+\d+\s*-\s*(?:4KHD|SZ).*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*-\s*(?:4KHD|SZ).*?$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*\[\d+MB(?:-\d+photos)?\]", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*[|_-]\s*(?:4khd|sz).*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*[|_-]\s*www\..*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"^[|\-_\s]+|[|\-_\s]+$", "", title)
        title = " ".join(title.split())
        return title or None

    def _safe_filename(self, name: str) -> str:
        safe_name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        safe_name = re.sub(r"\s+", " ", safe_name)
        return safe_name[:80] or f"gallery_{int(time.time())}"

    def _notify(self, callback: ProgressCallback | None, progress: float, speed: str, phase: str, detail: str, extra: dict | None = None) -> None:
        if callback:
            callback(round(progress, 2), speed, phase, detail, extra or {})
