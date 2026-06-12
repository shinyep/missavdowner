# xx.knit.bid 图站规则设计

## 背景

当前项目新增图站规则时，优先采用“站点识别 + 专用解析器”的方式，避免通用 HTML 提取把导航缩略图、相关推荐图或站外装饰图一起抓入。

对 `xx.knit.bid` 的实测样本页 `https://xx.knit.bid/en/article/19586/` 观察结果如下：

- 页面头部包含完整 `ImageGallery` JSON-LD，且字段非常规范
- JSON-LD 中可直接拿到图集名称、图片数量、分页总数，以及逐张图片的 `contentUrl`
- 当前样本显示分页总数为 `15`，图片总数为 `147`
- 每页正文区域也有 `img[data-src]` / `img[src]`，但单独抓 DOM 不如 JSON-LD 稳定
- 该站点文章页支持 `/page/N/` 形式的分页

## 目标

为 `xx.knit.bid` 新增整站通用图集解析规则，使其能够稳定解析：

- 图集标题
- 图集总图片数
- 多页图片列表
- 预览图

并尽量降低对正文 DOM 结构变化的敏感度。

## 非目标

本次不处理以下内容：

- 下载页、网盘页、评论区图片解析
- 用户登录、验证码或额外 Cloudflare JS Challenge 场景
- 与 `xx.knit.bid` 无关的通用解析器重构

## 方案选择

### 方案 A：JSON-LD 优先的专用解析器

做法：

- 识别 `xx.knit.bid`
- 优先读取 `ImageGallery` JSON-LD
- 按 `itemListElement` 提取当前页图片
- 按 `pagination.totalPages` 生成后续分页 URL 并继续采集
- 标题优先使用 `name`，失败后退回 `<title>` / DOM

优点：

- 最稳，数据结构明确
- 不容易被页面布局改动影响
- 天然能拿到图片顺序与分页总数

缺点：

- 依赖 JSON-LD 质量
- 若未来站点改结构，需要补 DOM 兜底

### 方案 B：正文 DOM 提取 + 分页扫描

做法：

- 识别 `xx.knit.bid`
- 主要抓 `.article-content img`
- 从 `<link rel="next">` 或分页链接遍历下一页

优点：

- 不依赖 JSON-LD

缺点：

- 需要额外过滤广告、导航和相关推荐图
- 当前样本里纯 DOM 不如 JSON-LD 清晰

### 结论

采用方案 A。

## 设计

### 站点识别

新增 URL 识别函数，判断是否为 `xx.knit.bid`。

### 解析流程

`parse_gallery` 在识别到 `xx.knit.bid` 后进入专用路径：

1. 加载文章页 HTML
2. 提取 `ImageGallery` JSON-LD
3. 从 JSON-LD 获取图集名称、图片总数、分页总数、当前页图片列表
4. 若 `totalPages > 1`，按 `/page/N/` 遍历后续页并继续提取图片
5. 合并、保序、去重
6. 返回 `GalleryParseResult`

### 标题提取

优先级：

1. JSON-LD `name`
2. `<title>`
3. `<meta property="og:title">`
4. 正文 `h1` / 通用标题兜底

标题清理沿用 `_clean_title`，保持与其他站点一致。

### 图片提取

主路径：

- 解析每页 `ImageGallery` JSON-LD
- 按 `itemListElement[].contentUrl` 收集图片
- 去重并保留顺序

兜底策略：

- 若某页 JSON-LD 缺失或解析失败，则从该页正文容器中提取 `img[data-src]` / `img[src]`
- 正文兜底时只取站点自身图片，尽量排除图标、logo、广告占位图

### 预览图

保持现有逻辑：

- `preview_base64` 不额外生成
- 前端继续使用首张图片做预览

## 错误处理

以下情况应返回解析失败：

- 页面无法加载
- 未提取到任何图片
- 分页跳转成功但连续多页均无法提取有效图片

错误提示保持与现有图站一致。

## 测试策略

本次补一个最小回归测试，覆盖：

- 能识别 `xx.knit.bid` URL
- 能从 JSON-LD 样本中提取正确标题
- 能从首页 JSON-LD 正确提取图片列表
- 能根据 `totalPages` 形成后续分页 URL
- 能在后续页 JSON-LD 缺失时退回正文 DOM 兜底

测试不依赖实时网络，使用固定 HTML/JSON-LD 样本。

## 实现范围

预计修改：

- `python/image_crawler.py`
- 新增一个 Python 侧最小测试文件
- 如有必要，更新 `README.md` 中支持站点列表

## 验收标准

当用户粘贴类似下面的链接时：

`https://xx.knit.bid/en/article/19586/`

系统应满足：

- 能成功解析标题
- 能提取图片列表
- 能处理分页
- 能继续走现有下载流程

## 风险与应对

风险：

- 未来站点可能替换 JSON-LD 结构，或取消 `ImageGallery` 类型

应对：

- 保留正文 DOM 兜底
- 保持专用解析器边界清晰，后续修改只影响单站
