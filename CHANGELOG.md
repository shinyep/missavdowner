# 更新说明

## 1.5.6 - 2026-07-01

### 修复

- 修复长时间下载中浏览器 Cloudflare 通关状态过期导致分片 403 的问题：增加 `_refresh_cf_clearance` 自动刷新机制，fetch 遇到 403 时自动重新加载页面通过 CF 验证后重试。
- 修复 `/api/parse` 接口因 `parse_video` 返回浏览器对象导致的 JSON 序列化错误。

## 1.5.5 - 2026-07-01

### 修复

- 修复 `/api/parse` 接口因 `parse_video` 返回浏览器对象导致的 JSON 序列化错误：预览用 parse 端点弹出并关闭 browser_context/browser_page，仅在下载路径中复用浏览器。

## 1.5.4 - 2026-06-30

### 修复

- 修复 surrit.com CDN 视频分片下载 403 问题：改用 Playwright 浏览器复用策略，通过页面 `fetch()` 直接下载分片，绕过 Cloudflare TLS 指纹检测。
- 修复 `_capture_m3u8` m3u8 正文捕获竞争问题：从 `request` 事件改为 `response` 事件，确保响应体就绪后再读取。
- 修复 ffmpeg 合并命令 `-headers` 参数不兼容问题：分片已全量下载为本地 `.ts` 文件，移除无用的 HTTP 请求头参数。
- `parse_video` 返回浏览器 page/context 引用，供下载阶段复用已通过 Cloudflare 的浏览器会话。

### 测试

- 已完成 `python.tests.test_missav_download` 全部 8 个测试回归验证。
- 已完成 missav.ws 实际视频下载端到端验证（KAWD-931, 698MB, 1789 分片）。

## 1.5.3 - 2026-06-30

### 修复

- 修复 missav 视频入库/下载在 ffmpeg 合并阶段可能失败的问题：按 m3u8 原始 `.jpeg` 分片 URL 下载远程内容，再保存为本地 `.ts` 分片供 ffmpeg 合并。
- 为 ffmpeg 合并阶段增加超时保护和明确错误信息，便于定位远程分片不可访问或被拦截的问题。
- 修复视频下载队列进度字段转发不完整的问题，补齐输出路径、来源、Novel Video ID 和完成详情展示。

### 测试

- 已完成 `python.tests.test_missav_download` 回归验证。
- 已完成 `npx vue-tsc --noEmit` 类型检查。
- 已完成 `npx vite build` 前端与 Electron 主进程构建验证。

### 打包

- 已完成构建前版本号同步更新到 `1.5.3`。

## 1.5.2 - 2026-06-30

### 修复

- 修复 missav 解析返回值中混入浏览器对象导致 `/api/parse` 序列化失败的问题。
- 修复 missav 下载链路中 `m3u8` 内容校验与 cookie 传递的回归问题，避免 ffmpeg 在无效播放列表上继续执行。

### 测试

- 已完成 `python.tests.test_missav_download` 回归验证。
- 已完成 `python/crawler.py` 与 `python/server.py` 的语法检查。

### 打包

- 已完成构建前版本号同步更新到 `1.5.2`。

## 1.5.1 - 2026-06-29

### 修复

- 图集解析遇到后端连接失败或底层网络库返回 `All connection attempts failed` 时，统一显示中文可读提示。
- 本地代理不可用时提前返回“代理不可用”提示，避免误判为图站解析失败。

### 验证

- 已完成 `portrait.knit.bid/mygirl/11184` 无代理解析验证。
- 已完成不可用代理 `127.0.0.1:7890` 的错误提示验证。

## 1.5.0 - 2026-06-29

### 新增

- 新增 portrait.knit.bid 专用图集解析器，支持从正文大图提取图片并按 `?page=N` 遍历分页。

### 修复

- 修复应用刚启动时图集解析可能先于 Python 后端就绪而报 `All connection attempts failed` 的问题。
- Electron 主进程在调用本地 API 前会等待 `/api/health` 就绪，并在必要时自动拉起后端服务。

### 验证

- 已完成 `python.tests.test_portrait_knit_bid_parser` 验证。
- 已完成 `portrait.knit.bid/mygirl/11184` 真实链路验证，确认可解析 68 张正文图片。

## 1.4.9 - 2026-06-17

### 新增

- 新增 hotgirl.biz 专用图集解析器：从 .entry-content 正文容器提取 data-src 懒加载图片，排除 header logo，标题自动去除站点后缀。
- 新增 nudebird.biz 专用图集解析器：从 .entry-content 正文容器提取 src 图片（跳过 base64 占位图），排除 header logo，标题自动去除站点后缀。
- hotgirl.biz / nudebird.biz 从 hotgirl.asia 族解析器中独立出来，各自匹配不同的图片 CDN 域名和加载方式。

### 修复

- 修复 hotgirl.biz / nudebird.biz 图集下载时误收首页 logo（class=image-logo / header img）的问题。

### 测试

- 新增 test_hotgirlbiz_parser.py（4 测试）和 test_nudebird_parser.py（4 测试），覆盖正文图片提取、logo 排除、标题解析、域名识别。
- 14 个 hotgirl 族回归测试全部通过。

## 1.4.5 - 2026-06-15

### ??

- ??????????????? `.avif` ????????????????????????
- ????????????????????????????????????????????
- ?? Electron ?????`file://` ??????????????? dataURL????????????

## 1.4.4 - 2026-06-15

### 修复

- 修复 Electron 主进程读取历史 API 返回值时错误地访问 .records 属性的问题，改为优先兼容直接返回数组的格式，恢复下载历史页面正常显示。

## 1.4.3 - 2026-06-15

### 修复

- 修复 xx.knit.bid 图站图片下载失败率高的问题。
- 根据响应 Content-Type 判断实际图片格式，对 AVIF/HEIF 格式跳过 Pillow 验证（服务器返回 AVIF 格式但 URL 扩展名为 .jpg）。
- 修复后下载成功率从 70.8% 提升至 100%。

### 验证

- 已完成 xx.knit.bid 图集下载验证（113 张图片全部成功）。
- 已完成现有单元测试验证（6 测试全绿）。

## 1.4.1 - 2026-06-15

### 修复

- 修正 TokyoMotion 接入架构：从图集（gallery）路径迁移至视频下载路径，对齐 missav / kissjav 的 `video:download` 流程。
- 新增 `TokyoMotionCrawler` 类，实现 `parse_video()` 接口，通过 `get_crawler_for_url()` 注册，走 `/api/download` 与 `/api/download-to-novel` 的独立视频下载分支。
- 视频下载使用 `download_direct_mp4()` 方法，支持 301 跳转跟随、流式写入和进度回调。
- 从 `ImageGalleryCrawler` 中移除 TokyoMotion 的图集路由和辅助方法。

### 验证

- 已完成 `python.tests.test_tokyomotion_parser` 验证（`parse_video` 接口）。
- 已完成全量回归验证（20 测试全绿）。

## 1.4.0 - 2026-06-15

### 新增

- 新增 `tokyomotion.net` 视频站专用解析器，支持从静态 HTML 提取标题、封面图和视频播放地址（优先 HD 源）。
- 新增直连 MP4 下载能力（`download_direct_mp4`），支持 301/302 跳转跟随、流式写入和进度回调。
- 视频下载分支自动路由：`xx.knit.bid` 走 m3u8 合并下载，`tokyomotion.net` 走直连 MP4 下载，后续入库和转码逻辑统一。

### 验证

- 已完成 `python.tests.test_tokyomotion_parser` 本地验证（正常路径 + 兜底路径）。
- 已完成全量回归验证（20 测试全绿）。
- 已完成 `https://www.tokyomotion.net/video/6578364/` 真实链路验证，确认 301 跳转、文件头 ftyp 和下载完整性。


## 1.3.9 - 2026-06-14

### 修复

- 修复下载历史页面始终显示为空的问题：Electron 主进程读取历史 API 返回值时错误地访问 .records 属性，而 Python 后端直接返回数组。
- 修复下载完成后历史记录页面不自动刷新的问题：在视频和图集下载完成回调中触发 history-updated 事件。
## 1.3.7 - 2026-06-14

### 新增

- 新增 `misskon.com` 图集专用解析器，支持正文图片提取与文章分页遍历。

### 验证

- 已完成 `python.tests.test_misskon_parser` 本地验证。
- 已完成 `python.tests.test_goddess247_parser` 与 `python.tests.test_xx_knit_bid_parser` 回归验证。

## 1.3.6 - 2026-06-13

### 修复

- 修复图集下载任务在“入库到 Novel”完成后右侧统计数量显示为 `0` 的问题。
- 修复图集任务进度字段在后端、Electron 与前端之间命名不一致，导致图片总数、成功数、失败数和 Gallery 信息丢失的问题。

### 验证

- 已补充图集入库完成后状态统计的回归测试。
- 已完成 `python.tests.test_xx_knit_bid_parser` 与 `python.tests.test_goddess247_parser` 本地验证。

## 1.3.5 - 2026-06-13

### 新增

- 支持 `xx.knit.bid` 图集页解析附带视频，并将图片与视频一并处理。
- 支持将 `xx.knit.bid` 的图集图片和附带视频统一入库到 Novel 的同一个 Gallery。

### 修复

- 修复图集入库时按源文件名归一化去重的问题，避免重复生成图片脚本项。
- 修复部分 m3u8 本地合并场景中播放列表指向异常的问题，并补充最小重试逻辑。

### 优化

- 优化右侧下载队列卡片的状态展示，统一“解析 / 图片下载 / 图片入库 / 视频下载 / 视频入库 / 转码 / 清理 / 完成 / 失败”等阶段文案。
- 优化图集任务成功态与失败态展示，直接显示 `Gallery ID`、`Video ID`、失败阶段、失败原因、输出位置等关键信息。
- 优化图集 + 视频混合任务的统计信息展示，让图片、视频、入库信息与进度摘要更直观。

### 验证

- 已完成 `https://xx.knit.bid/article/28129/` 真实链路验证。
- 验证结果为同一 Gallery 下包含 `82` 张图片和 `1` 个视频。
# 更新说明

## 1.4.3 - 2026-06-15

### 修复

- 修复 xx.knit.bid 图站图片下载失败率高的问题。
- 根据响应 Content-Type 判断实际图片格式，对 AVIF/HEIF 格式跳过 Pillow 验证（服务器返回 AVIF 格式但 URL 扩展名为 .jpg）。
- 修复后下载成功率从 70.8% 提升至 100%。

### 验证

- 已完成 xx.knit.bid 图集下载验证（113 张图片全部成功）。
- 已完成现有单元测试验证（6 测试全绿）。

## 1.4.2 - 2026-06-15

### 优化

- 优化视频下载队列的信息展示，参考图片模块设计风格，增加更多任务状态和统计信息。
- 新增状态标签（带图标）显示当前处理阶段：下载中、分片下载、合并中、入库中、转码中、清理中、已完成、失败。
- 新增信息标签显示媒体类型、来源站点（MissAV/KissJAV/Tokyomotion）、保存方式。
- 新增统计卡片（当前阶段、进度摘要）用于实时展示下载进度。
- 新增入库统计卡片（仅入库模式）显示 Video ID 和输出位置。
- 新增完成/失败状态详情卡片，展示下载模式、来源、Video ID、完成/失败明细。
