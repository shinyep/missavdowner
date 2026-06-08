# -*- coding: utf-8 -*-
"""
图片图集爬虫模块。

参考 F:\novel 的 image_4khd 管理命令，实现 4khd/szzs 图集 URL 转换、分页提取、
图片下载，并保留通用图片站点的基础提取能力。
"""
import asyncio
import os
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
        if any(token in candidate.lower() for token in ("placeholder", "loading", "avatar", "favicon", "logo")):
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
