# TokyoMotion 视频规则设计

## 目标

- 为 `tokyomotion.net/video/...` 页面新增专用解析规则。
- 从静态 HTML 中提取真实视频播放地址，避免退回通用图集解析导致拿不到 `video_url`。
- 保持对现有图集站点逻辑的最小侵入，不影响其他站点。

## 站点识别

- 域名：`www.tokyomotion.net`、`tokyomotion.net`
- 路径特征：`/video/<id>/...`
- 接入方式：新增 `_is_tokyomotion_url()` 与 `_parse_tokyomotion_gallery()`，在 `parse_gallery()` 中优先于通用提取器路由。

## 页面结构结论

- 页面 `meta[property="og:title"]` 可直接得到视频标题，例如：`配達ファック`。
- 页面主体包含 `<video id="vjsplayer">`，内部有多个 `<source>`：
  - `title="SD"` 对应标清 MP4
  - `title="HD"` 对应高清 MP4
- `<video>` 还带有 `poster` 属性，可作为封面图兜底。
- 当前目标页未发现需要执行 JavaScript 才能拿到视频源，静态 HTML 足够解析。
- 页面存在相关推荐区，但不会影响基于 `<video>` 的专用提取。

## 标题提取优先级

1. `meta[property="og:title"]`
2. `title`
3. 正文区域标题或通用标题提取器 `_extract_gallery_title()`

验收标准：返回真实视频标题，不带 ` - TOKYO Motion` 站点后缀。

## 视频提取优先级

1. `<video id="vjsplayer">` 内 `title="HD"` 的 `<source src>`
2. 同一 `<video>` 内第一个可用 `<source src>`
3. 页面任意 `<video source[src]>`
4. 若仍无视频源，则允许回退为空字符串

验收标准：优先返回高清 MP4 播放地址。

## 图片提取策略

- 主目标是视频提取；`image_urls` 允许为空。
- 如存在 `meta[property="og:image"]` 或 `video[poster]`，将其作为单张封面图写入 `image_urls`，便于前端预览和兼容已有下载结果结构。
- 不抓取相关推荐缩略图、侧栏图、logo、广告图。

## 分页策略

- 当前视频详情页无需分页。
- 不实现评论区、相关推荐或“Show More”加载。

## 错误处理

- 页面可打开但找不到视频源时，不抛出站点专属异常，返回标题与可能的封面图，`video_url` 为空。
- 页面请求失败时，沿用现有 `_load_page_html()` / http 客户端异常。

## 测试方案

- 新增 `python/tests/test_tokyomotion_parser.py`
- 覆盖两个样本：
  - 正常样本：同时存在 `og:title`、`og:image`、`video source`，应优先返回 HD 视频链接。
  - 兜底样本：缺少 `og:title` 且只有一个 `<source>`，应退回 `<title>` 并仍能提取视频地址。

## 验收标准

- `parse_gallery()` 传入 `https://www.tokyomotion.net/video/...` 时命中专用解析器。
- 能返回正确标题。
- 能优先返回 HD `video_url`。
- `image_urls` 至少返回封面图，且不混入相关推荐缩略图。
- 新测试通过，现有回归测试不受影响。