# misskon.com 图站规则设计

## 背景

当前项目在新增图站时优先采用“站点识别 + 专用解析器”，避免通用提取把导航图、相关推荐图、logo 或广告素材混入图集结果。

对样本页 `https://misskon.com/110569-mzsock-ai-mei-zu-no371-yu-meng-102-photos-1-video/` 的实际调研结果如下：

- 页面是 WordPress 文章页，正文主体位于 `.entry`
- 标题可从文章 `h1`、`<title>`、`Article` JSON-LD `headline/name` 中稳定获得
- 正文图片使用懒加载，主字段是 `img[data-src]`，`src` 常为 `data:image/svg+xml` 占位图
- 图集分页使用文章子页形式，如 `/2/`，页面内也存在页码导航
- 页面文案会标注 `102 photos + 1 video`，但当前静态 HTML 中没有可直接提取的 `mp4`、`m3u8`、`video`、`iframe` 播放源

## 目标

为 `misskon.com` 新增整站通用图集专用解析规则，使其能够稳定解析：

- 图集标题
- 多页正文图片
- 分页链接
- 仅返回正文图，不混入站点 logo、相关推荐或广告图

## 非目标

本次不处理以下内容：

- 外链下载页跳转解析
- 网盘下载链接解码
- 标题中的 “1 video” 对应的真实视频文件提取
- 与 `misskon.com` 无关的通用解析器重构

## 方案选择

### 方案 A：正文 DOM 优先专用解析器

做法：

- 识别 `misskon.com`
- 先定位文章正文容器 `.entry`
- 只从正文容器提取 `img[data-src]` / `img[src]`
- 读取页码导航，继续遍历 `/2/`、`/3/` 等分页
- 标题优先取文章 `h1`，失败后退回 JSON-LD / `title`

优点：

- 与当前页面结构最匹配
- 图片真实来源清晰，便于过滤懒加载占位图
- 不需要依赖额外跳转页或播放器脚本

缺点：

- 若正文容器选择器未来变更，需要调整专用规则

### 方案 B：通用提取器 + 分页

做法：

- 继续走通用 `parse_gallery`
- 依赖通用标题提取和全局图片提取

优点：

- 实现最少

缺点：

- 容易抓入 logo、标签区、相关推荐图
- 难以稳定处理 `data-src` 懒加载图片和文章分页

### 结论

采用方案 A。

## 设计

### 站点识别

新增 `_is_misskon_url()`，判断域名是否包含 `misskon.com`。

### 解析流程

`parse_gallery()` 识别到 `misskon.com` 后进入专用路径：

1. 加载首页 HTML
2. 提取文章标题
3. 只从正文容器提取当前页图片
4. 识别页码导航中的文章分页链接
5. 依次加载后续分页，继续提取正文图片
6. 合并、保序、去重
7. 返回 `GalleryParseResult`

### 标题提取

优先级：

1. 文章 `h1.name.post-title.entry-title`
2. 文章内首个 `h1`
3. `Article` JSON-LD `headline` / `name`
4. `<title>`

标题清理沿用 `_clean_title()`，并去掉尾部站点后缀 `- MissKon.com` / `– MissKon.com`。

### 图片提取

正文容器优先级：

1. `.entry`
2. `.post-inner .entry`
3. `article`

图片字段优先级：

1. `data-src`
2. `data-lazy-src`
3. `src`

过滤规则：

- 跳过 `data:` 占位图
- 跳过站点 logo
- 跳过正文外区域图片
- 跳过分页导航、标签区、相关推荐和广告区域图片

### 分页策略

优先从文章内 `.page-link a[href]` 收集分页 URL。

若页码导航缺失，则不猜测总页数，不主动构造分页，只返回当前页结果。

### 视频策略

当前样本页虽在标题和信息区标注 `1 video`，但静态 HTML 未提供可直接提取的视频播放源，因此：

- `video_url` 先固定返回空字符串
- 不从外链下载按钮推断视频地址
- 后续若遇到存在正文视频源的新样本，再独立扩展

## 错误处理

以下情况应返回解析失败：

- 页面无法加载
- 正文容器内未提取到任何图片

若后续分页失败：

- 保留已成功页的图片结果
- 不因为单个分页失败而整体中断

## 测试策略

新增 `python/tests/test_misskon_parser.py`，使用固定 HTML 样本，不依赖实时网络，至少覆盖：

- 能识别 `misskon.com` URL
- 能从首页正文提取图片
- 能遍历 `/2/` 分页并合并结果
- 不抓入 logo、标签区和正文外图片
- 标题优先返回文章标题而不是站点名
- `video_url` 在当前样本模式下为空字符串

## 实现范围

预计修改：

- `docs/superpowers/specs/2026-06-14-misskon-gallery-design.md`
- `python/tests/test_misskon_parser.py`
- `python/image_crawler.py`
- `README.md`

## 验收标准

当用户输入类似下面的链接时：

`https://misskon.com/110569-mzsock-ai-mei-zu-no371-yu-meng-102-photos-1-video/`

系统应满足：

- 能成功解析标题
- 能提取正文图片列表
- 能处理文章分页
- 不混入站点 logo 或相关推荐图
- 返回 `video_url == ""`

## 风险与应对

风险：

- WordPress 主题可能调整正文选择器或页码导航结构

应对：

- 将标题、正文、分页提取逻辑封装为 `misskon` 专用函数
- 保持选择器优先级清晰，后续只需局部调整
