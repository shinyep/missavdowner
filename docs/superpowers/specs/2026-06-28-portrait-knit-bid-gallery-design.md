# portrait.knit.bid 图站规则设计

## 背景

当前项目新增图站规则时，优先采用“站点识别 + 专用解析器”的方式，避免通用 HTML 提取把导航缩略图、相关推荐图或站外装饰图一起抓入。

对 `portrait.knit.bid` 的实测样本页 `https://portrait.knit.bid/mygirl/11184` 观察结果如下：

- 页面头部包含稳定的 `meta name="og:title"` / `meta name="twitter:title"`，可用于还原文章真实标题
- 页面没有可用的 `ImageGallery` JSON-LD，正文图片需要从 DOM 提取
- 正文大图使用 `img-fluid w-100 lazy mb-2`，真实地址在 `data-src`，路径为 `/static/uploadfile/...`
- 相关推荐缩略图同样来自 `/static/uploadfile/...`，但使用 `card-img-top lazy`
- 分页导航使用 `javascript:gotoPage(N)`，实际分页 URL 为原文章 URL 加 `?page=N`
- 样本页共有 23 页，前 22 页每页 3 张图，第 23 页 2 张图

## 目标

为 `portrait.knit.bid` 新增整站通用图集解析规则，使其能够稳定解析：

- 图集标题
- 多页图片列表
- 正文图片顺序
- 现有下载与入库流程

并避免把相关推荐、导航、广告和懒加载占位图混入图集。

## 非目标

本次不处理以下内容：

- 登录、验证码或额外 Cloudflare JS Challenge 场景
- 推荐区、搜索页、栏目页图片批量解析
- 与 `portrait.knit.bid` 无关的通用解析器重构
- 前端交互和入库接口协议变更

## 方案选择

### 方案 A：正文 DOM 优先的专用解析器

做法：

- 识别 `portrait.knit.bid`
- 优先读取 `meta name="og:title"` / `meta name="twitter:title"` / `<title>` 作为标题
- 从正文主容器内提取 `img[data-src]` / `img[src]`
- 只保留正文大图 class 信号，如 `img-fluid`
- 排除 `card-img-top` 推荐缩略图和站点装饰图
- 从 `javascript:gotoPage(N)` 提取分页编号，并生成 `?page=N`

优点：

- 和站点真实结构一致
- 不依赖前端脚本执行
- 不影响现有 `xx.knit.bid` JSON-LD 解析逻辑

缺点：

- 依赖正文图片 class 约定
- 若站点未来改版，需要调整正文容器或 class 规则

### 方案 B：复用通用图片提取器

做法：

- 让通用解析器扫描全页图片和分页链接

优点：

- 改动更少

缺点：

- 相关推荐缩略图与正文图同域同目录，通用 URL 过滤无法稳定区分
- 容易混入导航、推荐和广告图片

### 结论

采用方案 A。

## 设计

### 站点识别

新增 URL 识别函数，判断是否为 `portrait.knit.bid`。

### 解析流程

`parse_gallery` 在识别到 `portrait.knit.bid` 后进入专用路径：

1. 加载文章页 HTML
2. 提取标题
3. 从当前页正文容器提取正文大图
4. 从分页导航提取 `gotoPage(N)` 编号
5. 将后续页生成成 `?page=N` URL 并继续采集
6. 合并、保序、去重
7. 返回 `GalleryParseResult`

### 标题提取

优先级：

1. `meta[name="og:title"]`
2. `meta[property="og:title"]`
3. `meta[name="twitter:title"]`
4. `<title>`
5. 通用标题兜底

标题清理沿用 `_clean_title`，保留 `MyGirl` / `XiuRen` 等系列前缀。

### 图片提取

主路径：

- 优先定位正文内容容器
- 从容器内选择 `img[data-src]` / `img[src]`
- 优先读取 `data-src`
- 只保留 `/static/uploadfile/` 图片
- 优先保留带 `img-fluid` 的正文大图
- 排除带 `card-img-top` 的推荐缩略图
- 排除 `data:`、favicon、logo、icon、avatar、banner、pixel、loading 占位图

兜底策略：

- 若正文容器选择器未命中，则在 `.page-content` 内按同样规则提取
- 若仍未提取到图片，则返回解析失败

### 分页提取

主路径：

- 从 `.pagination a.page-link[href]` 中匹配 `gotoPage(N)`
- 忽略第 1 页
- 去重并按页码升序生成 URL
- 生成规则为在原文章 URL 上设置 `page=N`

兜底策略：

- 若没有分页导航，则只返回当前页图片
- 若部分分页加载失败，跳过失败页并保留已成功提取的图片

## 错误处理

以下情况应返回解析失败：

- 首页无法加载
- 未提取到任何正文图片

分页页码加载失败时不直接中断整个解析，避免单页异常导致已提取图片不可用。

## 测试策略

本次补一个最小回归测试，覆盖：

- 能识别 `portrait.knit.bid` URL
- 能从 meta 标题中提取真实标题
- 能从正文 DOM 提取图片
- 能排除 `card-img-top` 推荐缩略图
- 能根据 `gotoPage(N)` 抓取 `?page=N` 后续分页
- 能在无分页时只返回当前页正文图片

测试不依赖实时网络，使用固定 HTML 样本。

## 实现范围

预计修改：

- `python/image_crawler.py`
- 新增 `python/tests/test_portrait_knit_bid_parser.py`
- 更新 `README.md` 中支持站点列表

## 验收标准

当用户粘贴类似下面的链接时：

`https://portrait.knit.bid/mygirl/11184`

系统应满足：

- 能成功解析标题
- 能提取 23 页正文图片
- 不混入相关推荐缩略图
- 能继续走现有下载与 Novel 入库流程

## 风险与应对

风险：

- 未来站点可能更换正文图片 class 或分页函数名

应对：

- 保持专用解析器边界清晰
- 保留正文容器兜底
- 用固定样本测试锁定当前站点结构
