# -*- coding: utf-8 -*-
"""
图片图集爬虫模块。

参考 F:\novel 的 image_4khd / image_kkc3 管理命令，实现 4khd/szzs/kkc3 图集 URL 转换、
分页提取、图片下载，并保留通用图片站点的基础提取能力。
"""
import asyncio
import html
import json
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

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".jfif", ".avif", ".heif", ".heic")

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

        if self._is_photos18_url(page_url):
            return await self._parse_photos18_gallery(page_url)
        if self._is_tokyobombers_url(page_url):
            return await self._parse_tokyobombers_gallery(page_url)
        if self._is_foamgirl_url(page_url):
            return await self._parse_foamgirl_gallery(page_url)
        if self._is_hotgirl_url(page_url):
            return await self._parse_hotgirl_gallery(page_url)

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
        response = await client.get(image_url, headers={"Referer": referer_url, "Accept": "image/avif,image/heif,image/heif-sequence,image/webp,image/apng,image/*,*/*;q=0.8"})
        response.raise_for_status()
        data = response.content
        if len(data) < 128:
            raise RuntimeError("图片内容过小")
        lower_url = image_url.lower().split("?")[0]
        is_avif = lower_url.endswith(('.avif', '.heif', '.heic'))
        if Image is not None and not is_avif:
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

    # ---- photos18.com 专用解析 ----

    @staticmethod
    def _is_photos18_url(url: str) -> bool:
        return "photos18.com" in urlparse(url).netloc

    async def _parse_photos18_gallery(self, gallery_url: str) -> GalleryParseResult:
        all_image_urls: list[str] = []
        seen_urls: set[str] = set()
        gallery_title = ""

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.photos18.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        client_options = self._client_options(headers)

        async with httpx.AsyncClient(**client_options) as client:
            base_url_clean = gallery_url.split("?")[0].split("#")[0].rstrip("/")
            total_pages = 1
            visited_pages: set[int] = set()
            empty_streak = 0
            first_html = ""

            for page_num in range(1, 51):
                if page_num > total_pages + 1:
                    break

                page_url = base_url_clean if page_num == 1 else f"{base_url_clean}?page={page_num}"
                html_content = await self._photos18_fetch(client, page_url)
                if page_num == 1 and not html_content:
                    html_content = await self._load_page_html(gallery_url, page_url)
                if page_num == 1:
                    first_html = html_content
                soup = BeautifulSoup(html_content, "html.parser") if html_content else BeautifulSoup("", "html.parser")
                visited_pages.add(page_num)

                if not gallery_title:
                    title_candidate = self._extract_photos18_title(soup)
                    if title_candidate:
                        gallery_title = title_candidate
                        total_pages = max(total_pages, self._detect_photos18_total_pages(gallery_title, total_pages))

                if page_num == 1 and html_content:
                    json_ld_images = self._extract_photos18_json_ld_images(soup)
                    if json_ld_images:
                        for img_url in json_ld_images:
                            if img_url not in seen_urls:
                                seen_urls.add(img_url)
                                all_image_urls.append(img_url)
                        if total_pages <= 1:
                            break
                        continue

                page_images = self._extract_photos18_images_from_soup(soup, page_url) if html_content else []
                for img_url in page_images:
                    if img_url not in seen_urls:
                        seen_urls.add(img_url)
                        all_image_urls.append(img_url)

                if page_images:
                    empty_streak = 0
                else:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break

                if page_num >= total_pages and total_pages > 1:
                    break

            if not all_image_urls and first_html:
                fallback_soup = BeautifulSoup(first_html, "html.parser")
                if not gallery_title:
                    title_candidate = self._extract_photos18_title(fallback_soup)
                    if title_candidate:
                        gallery_title = title_candidate
                all_image_urls.extend(self._extract_photos18_json_ld_images(fallback_soup))
                all_image_urls.extend(self._extract_photos18_images_from_soup(fallback_soup, gallery_url))
                all_image_urls = list(dict.fromkeys(all_image_urls))

            if not all_image_urls:
                fallback_html = await self._load_page_html(gallery_url, gallery_url)
                fallback_soup = BeautifulSoup(fallback_html, "html.parser")
                if not gallery_title:
                    title_candidate = self._extract_photos18_title(fallback_soup)
                    if title_candidate:
                        gallery_title = title_candidate
                all_image_urls.extend(self._extract_photos18_json_ld_images(fallback_soup))
                all_image_urls.extend(self._extract_photos18_images_from_soup(fallback_soup, gallery_url))
                all_image_urls = list(dict.fromkeys(all_image_urls))

            if not all_image_urls:
                raise RuntimeError("未从 photos18 图集页面提取到图片链接")

            if not gallery_title:
                gallery_title = f"photos18_{int(time.time())}"

            return GalleryParseResult(title=gallery_title, page_url=gallery_url, image_urls=all_image_urls)

    async def _photos18_fetch(self, client: httpx.AsyncClient, url: str) -> str:
        for attempt in range(4):
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 429:
                    retry_after = 3 + attempt * 2
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                text = resp.text
                if "gocheck.php" in text or "goto2.cc/block" in text:
                    if attempt < 3:
                        await asyncio.sleep(2 + attempt)
                        continue
                    return ""
                return text
            except Exception:
                if attempt < 3:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise
        return ""

    def _extract_photos18_title(self, soup: BeautifulSoup) -> str:
        for script in soup.select('script[type="application/ld+json"]'):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except Exception:
                continue
            title = data.get("headline") or data.get("name") or data.get("description")
            if title:
                cleaned = self._clean_title(str(title))
                if cleaned:
                    return cleaned

        for selector in ["h1.title", "h1", "title"]:
            el = soup.select_one(selector)
            if el and el.get_text(strip=True):
                cleaned = self._clean_title(el.get_text(" ", strip=True))
                if cleaned:
                    return cleaned

        return ""

    def _extract_photos18_json_ld_images(self, soup: BeautifulSoup) -> list[str]:
        found: list[str] = []
        for script in soup.select('script[type="application/ld+json"]'):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except Exception:
                continue

            images = []

            main_entity = data.get("mainEntityOfPage")
            if isinstance(main_entity, dict):
                candidate = main_entity.get("image")
                if isinstance(candidate, list):
                    images = candidate
                elif isinstance(candidate, dict):
                    images = [candidate]

            if not images:
                for item in data.get("itemListElement", []):
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") != "ImageObject":
                        continue
                    url = item.get("contentUrl") or item.get("url")
                    if url:
                        images.append(item)

            for item in images:
                url = (item.get("url") if isinstance(item, dict) else None) or ""
                if not url or url.startswith("data:"):
                    continue
                if url in found:
                    continue
                found.append(url)

        return found

    def _extract_photos18_images_from_soup(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()

        for selector in ["#content .imgHolder a", "#content .imgHolder img"]:
            for element in soup.select(selector):
                candidate = element.get("href") or element.get("data-src") or element.get("src")
                if not candidate or candidate.startswith("data:"):
                    continue
                lower = candidate.lower()
                if any(token in lower for token in ("logo", "icon", "avatar", "favicon", "thumbnail", "thumb")):
                    continue
                absolute_url = urljoin(base_url, candidate)
                clean = lower.split("?")[0]
                if not any(clean.endswith(ext) for ext in IMAGE_EXTENSIONS):
                    continue
                if absolute_url in seen:
                    continue
                seen.add(absolute_url)
                found.append(absolute_url)

        if not found:
            return self._extract_image_urls(soup, base_url)

        return found

    def _extract_photos18_pagination_links(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        return self._extract_pagination_links(soup, page_url)

    def _detect_photos18_total_pages(self, title: str, fallback: int = 1) -> int:
        total = fallback
        match = re.search(r"\(\s*Page\s+\d+\s*/\s*(\d+)\s*\)", title or "", re.IGNORECASE)
        if match:
            try:
                total = max(total, int(match.group(1)))
            except Exception:
                pass
        return max(total, 1)




    # ---- hotgirl.asia 专用解析 ----

    @staticmethod
    def _is_hotgirl_url(url: str) -> bool:
        return "hotgirl.asia" in urlparse(url).netloc

    async def _parse_hotgirl_gallery(self, gallery_url: str) -> GalleryParseResult:
        """使用 httpx + BeautifulSoup 解析 hotgirl.asia 图集。

        hotgirl.asia 是 WordPress 站点，内容图片 CDN 在 files.everiaclub.com，
        图片在 div.galeria_img 容器中，分页通过 ?num=N 参数实现。
        """
        all_image_urls: list[str] = []
        seen_urls: set[str] = set()
        gallery_title = ""

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://hotgirl.asia/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        client_options = self._client_options(headers)

        async with httpx.AsyncClient(**client_options) as client:
            page_num = 0
            while page_num < 20:
                page_num += 1
                page_url = gallery_url if page_num == 1 else f"{gallery_url}?num={page_num}"

                html_content = await self._hotgirl_fetch(client, page_url)
                if not html_content:
                    break

                soup = BeautifulSoup(html_content, "html.parser")

                # 首页提取标题
                if not gallery_title:
                    gallery_title = self._extract_hotgirl_title(soup)
                    if not gallery_title:
                        raise RuntimeError("未能从 hotgirl 页面提取图集标题")

                # 提取当前页图片
                page_images = self._extract_hotgirl_images(soup, page_url)
                if not page_images and page_num > 1:
                    break

                for img_url in page_images:
                    if img_url not in seen_urls:
                        seen_urls.add(img_url)
                        all_image_urls.append(img_url)

                # 检查是否有下一页
                if not self._hotgirl_has_next_page(soup, page_num):
                    break

                await asyncio.sleep(0.5)

            if not all_image_urls:
                raise RuntimeError("未从 hotgirl 图集页面提取到图片链接")

            return GalleryParseResult(
                title=gallery_title,
                page_url=gallery_url,
                image_urls=all_image_urls,
            )

    async def _hotgirl_fetch(self, client: httpx.AsyncClient, url: str) -> str:
        """用 httpx 抓取 hotgirl 页面 HTML，带重试"""
        for attempt in range(4):
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 429:
                    retry_after = 3 + attempt * 2
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.text
            except Exception:
                if attempt < 3:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise
        return ""

    def _extract_hotgirl_title(self, soup: BeautifulSoup) -> str:
        """从 hotgirl 页面提取标题，优先从 LD+JSON headline 提取"""
        # 优先 LD+JSON
        for script in soup.select('script[type="application/ld+json"]'):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except Exception:
                continue
            # 处理 @graph 结构
            items = data.get("@graph", [data]) if isinstance(data.get("@graph"), list) else [data]
            for item in items:
                headline = item.get("headline") or item.get("name")
                if headline:
                    cleaned = self._clean_title(str(headline))
                    if cleaned:
                        return cleaned

        # 回退 h1
        h1 = soup.select_one("h1")
        if h1 and h1.get_text(strip=True):
            return self._clean_title(h1.get_text(" ", strip=True))

        # 回退 <title>
        title_el = soup.select_one("title")
        if title_el and title_el.get_text(strip=True):
            raw = title_el.get_text(" ", strip=True)
            for sep in [" - ", " | ", " -- "]:
                if sep in raw:
                    raw = raw.split(sep)[0].strip()
            cleaned = self._clean_title(raw)
            if cleaned:
                return cleaned

        return ""

    def _extract_hotgirl_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """从 hotgirl 页面提取图片 URL。

        内容图片 CDN 为 files.everiaclub.com，分布在 div.page-detail 容器中。
        通过 CDN 域名匹配精准提取内容图，排除侧栏缩略图、logo、rating 等。
        """
        found: list[str] = []
        seen: set[str] = set()

        for img in soup.select("img"):
            src = (img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "").strip()
            if not src or src.startswith("data:"):
                continue
            lower = src.lower()
            # 只提取 everiaclub CDN 上的内容图片
            if "everiaclub.com" not in lower:
                continue
            absolute_url = urljoin(base_url, src)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            clean = lower.split("?")[0]
            if any(clean.endswith(ext) for ext in IMAGE_EXTENSIONS):
                found.append(absolute_url)

        return found

    def _hotgirl_has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """检查 hotgirl 页面是否有下一页"""
        for a in soup.select("a.page"):
            text = a.get_text(strip=True)
            try:
                if int(text) > current_page:
                    return True
            except ValueError:
                continue
        return False

    # ---- foamgirl.net 专用解析 ----

    @staticmethod
    def _is_foamgirl_url(url: str) -> bool:
        return "foamgirl.net" in urlparse(url).netloc

    async def _parse_foamgirl_gallery(self, gallery_url: str) -> GalleryParseResult:
        """使用 httpx + BeautifulSoup 解析 foamgirl.net 图集。

        foamgirl 是 WordPress 站点，图片 CDN 在 cdn.foamgirl.net，
        图片格式为 webp，直接在 img[src] 中，无需 Playwright/JS。
        分页 URL 格式：/1838332.html -> /1838332_2.html -> /1838332_3.html
        """
        all_image_urls: list[str] = []
        seen_urls: set[str] = set()
        gallery_title = ""

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://foamgirl.net/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        client_options = self._client_options(headers)

        async with httpx.AsyncClient(**client_options) as client:
            # 遍历分页
            page_num = 0
            while page_num < 20:  # 最多20页防无限循环
                page_num += 1
                if page_num == 1:
                    page_url = gallery_url
                else:
                    page_url = self._foamgirl_next_page_url(gallery_url, page_num)

                html_content = await self._foamgirl_fetch(client, page_url)
                if not html_content:
                    break

                soup = BeautifulSoup(html_content, "html.parser")

                # 首页提取标题
                if not gallery_title:
                    gallery_title = self._extract_foamgirl_title(soup)
                    if not gallery_title:
                        raise RuntimeError("未能从 foamgirl 页面提取图集标题")

                # 提取当前页图片
                page_images = self._extract_foamgirl_images(soup, page_url)
                if not page_images and page_num > 1:
                    break  # 后续页无图即结束

                for img_url in page_images:
                    if img_url not in seen_urls:
                        seen_urls.add(img_url)
                        all_image_urls.append(img_url)

                # 检查是否有下一页
                if not self._foamgirl_has_next_page(soup, page_num):
                    break

                await asyncio.sleep(0.5)

            if not all_image_urls:
                raise RuntimeError("未从 foamgirl 图集页面提取到图片链接")

            return GalleryParseResult(
                title=gallery_title,
                page_url=gallery_url,
                image_urls=all_image_urls,
            )

    def _foamgirl_next_page_url(self, base_url: str, page_num: int) -> str:
        """生成 foamgirl 分页 URL。
        /1838332.html -> /1838332_2.html -> /1838332_3.html
        """
        parsed = urlparse(base_url)
        path = parsed.path
        # 替换 .html 为 _N.html
        if path.endswith(".html"):
            base_path = path.rsplit(".html", 1)[0]
            # 去掉已有的 _N 后缀
            base_path = re.sub(r"_\d+$", "", base_path)
            return f"{parsed.scheme}://{parsed.netloc}{base_path}_{page_num}.html"
        return base_url

    def _foamgirl_has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """检查 foamgirl 页面是否有下一页。

        分页导航中 .page-numbers.next 可能指向上/下一页（循环导航），
        所以只看纯数字页码链接，如果有大于 current_page 的数字则说明还有下一页。
        """
        for a in soup.select("a.page-numbers"):
            cls = a.get("class", [])
            # 跳过 prev/next 类
            if any(c in cls for c in ("prev", "next")):
                continue
            text = a.get_text(strip=True)
            try:
                if int(text) > current_page:
                    return True
            except ValueError:
                continue
        return False

    async def _foamgirl_fetch(self, client: httpx.AsyncClient, url: str) -> str:
        """用 httpx 抓取 foamgirl 页面 HTML，带重试"""
        for attempt in range(4):
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 429:
                    retry_after = 3 + attempt * 2
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.text
            except Exception:
                if attempt < 3:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise
        return ""

    def _extract_foamgirl_title(self, soup: BeautifulSoup) -> str:
        """从 foamgirl 页面提取标题"""
        # 优先 h1
        h1 = soup.select_one("h1")
        if h1 and h1.get_text(strip=True):
            return self._clean_title(h1.get_text(" ", strip=True))

        # 回退 <title>
        title_el = soup.select_one("title")
        if title_el and title_el.get_text(strip=True):
            raw = title_el.get_text(" ", strip=True)
            for sep in [" - ", " | ", " -- "]:
                if sep in raw:
                    raw = raw.split(sep)[0].strip()
            cleaned = self._clean_title(raw)
            if cleaned:
                return cleaned

        return ""

    def _extract_foamgirl_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """从 foamgirl 页面提取图片 URL。

        只提取正文区域（#content / .content）中的图片，
        图片在 cdn.foamgirl.net 的 wp-content/uploads 路径下，
        排除 logo/svg、广告 gif、推荐文章缩略图等。
        """
        found: list[str] = []
        seen: set[str] = set()

        # 优先从正文区域提取
        content_area = soup.select_one("#content") or soup.select_one(".content")
        target = content_area if content_area else soup

        for img in target.select("img"):
            src = (img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "").strip()
            if not src or src.startswith("data:"):
                continue
            lower = src.lower()
            # 必须是 wp-content/uploads 下的图片
            if "/wp-content/uploads/" not in lower:
                continue
            # 排除非内容图
            if any(token in lower for token in ("logo", "icon", "avatar", "favicon", "cx_img")):
                continue
            # 排除 gif 广告图
            if lower.endswith(".gif"):
                continue
            # 排除 SVG
            if lower.endswith(".svg"):
                continue
            absolute_url = urljoin(base_url, src)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            clean = lower.split("?")[0]
            if any(clean.endswith(ext) for ext in IMAGE_EXTENSIONS):
                found.append(absolute_url)

        return found

    # ---- tokyobombers.com 专用解析 ----

    @staticmethod
    def _is_tokyobombers_url(url: str) -> bool:
        return "tokyobombers.com" in urlparse(url).netloc

    async def _parse_tokyobombers_gallery(self, gallery_url: str) -> GalleryParseResult:
        """使用 httpx + BeautifulSoup 解析 tokyobombers.com 图集。

        tokyobombers 是 WordPress 站点，图片在静态 HTML 的 img[src] 属性中，
        路径为 /wp-content/uploads/，无需 Playwright/JS 执行。
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.tokyobombers.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        client_options = self._client_options(headers)

        async with httpx.AsyncClient(**client_options) as client:
            html_content = await self._tokyobombers_fetch(client, gallery_url)
            soup = BeautifulSoup(html_content, "html.parser")

            # 提取标题
            gallery_title = self._extract_tokyobombers_title(soup)
            if not gallery_title:
                raise RuntimeError("未能从 tokyobombers 页面提取图集标题")

            # 提取图片
            all_image_urls = self._extract_tokyobombers_images(soup, gallery_url)
            if not all_image_urls:
                raise RuntimeError("未从 tokyobombers 图集页面提取到图片链接")

            return GalleryParseResult(
                title=gallery_title,
                page_url=gallery_url,
                image_urls=all_image_urls,
            )

    async def _tokyobombers_fetch(self, client: httpx.AsyncClient, url: str) -> str:
        """用 httpx 抓取 tokyobombers 页面 HTML，带重试"""
        for attempt in range(4):
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 429:
                    retry_after = 3 + attempt * 2
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.text
            except Exception:
                if attempt < 3:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise
        return ""

    def _extract_tokyobombers_title(self, soup: BeautifulSoup) -> str:
        """从 tokyobombers 页面提取标题"""
        # 优先 h1
        h1 = soup.select_one("h1.entry-title, h1")
        if h1 and h1.get_text(strip=True):
            return self._clean_title(h1.get_text(" ", strip=True))

        # 回退 <title>
        title_el = soup.select_one("title")
        if title_el and title_el.get_text(strip=True):
            raw = title_el.get_text(" ", strip=True)
            # 去除站点后缀，如 " - Big Boobs Asia"
            for sep in [" - ", " | ", " -- "]:
                if sep in raw:
                    raw = raw.split(sep)[0].strip()
            cleaned = self._clean_title(raw)
            if cleaned:
                return cleaned

        return ""

    def _extract_tokyobombers_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """从 tokyobombers 页面提取图片 URL。

        只提取正文区域（entry-content / article）中 wp-content/uploads 下的图片，
        排除侧栏 widget、logo、小尺寸图标等非内容图片。
        """
        found: list[str] = []
        seen: set[str] = set()

        # 优先从正文区域提取，避免侧栏/导航栏图片混入
        content_area = soup.select_one(".entry-content") or soup.select_one("article")
        target = content_area if content_area else soup

        for img in target.select("img"):
            src = (img.get("data-src") or img.get("src") or "").strip()
            if not src or src.startswith("data:"):
                continue
            lower = src.lower()
            # 必须是 wp-content/uploads 下的图片
            if "/wp-content/uploads/" not in lower:
                continue
            # 过滤非内容图（尺寸过小的通常是图标/logo）
            width = img.get("width", "")
            height = img.get("height", "")
            try:
                if width and int(width) < 50:
                    continue
                if height and int(height) < 50:
                    continue
            except (ValueError, TypeError):
                pass
            absolute_url = urljoin(base_url, src)
            # 去掉 URL 中的尺寸后缀（如 -150x150、-300x200 等），获取原图
            absolute_url = re.sub(r"-\d+x\d+(?=\.\w+$)", "", absolute_url)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            clean = lower.split("?")[0]
            if any(clean.endswith(ext) for ext in IMAGE_EXTENSIONS):
                found.append(absolute_url)

        return found

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










