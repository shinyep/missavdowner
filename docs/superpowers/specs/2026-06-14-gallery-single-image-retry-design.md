# 图集失败图片定位与单张重试设计

## 背景

当前图集下载任务在右侧卡片中只展示聚合统计，例如总数、成功数、失败数，但不会保留“失败的是哪一张、失败原因是什么、原始图片 URL 是什么”。

这会带来两个问题：

- 用户看到 `失败：1 张` 时，无法定位具体缺失项
- 任务完成后，无法只补下失败图片，只能整组重新下载

在 `xx.knit.bid/article/25144/` 的真实样本中，解析结果为 `84` 张图，Novel 图库目录 `F:\novel\img\gallery_images\1909` 中实际只有 `83` 张，正好暴露了这个缺口。

## 目标

为图集任务增加“失败图片定位 + 单张重试”能力，使用户能够：

- 看到失败图片的具体序号、失败原因
- 在任务卡片中单独重试某一张失败图片
- 在 Novel 模式下把补下的图片直接写回对应 `gallery_id`
- 在本地模式下把补下的图片直接写回原输出目录
- 在单张重试成功后自动更新任务统计

## 非目标

本次不处理以下内容：

- 批量重试全部失败图片
- 历史记录页单独发起失败图片修复
- 视频分片失败重试
- 下载中的暂停 / 恢复机制重构

## 现状分析

### 当前数据链路

- `python/image_crawler.py` 会在下载循环中统计 `total_images / current_index / success_count / failed_count`
- `python/server.py` 只把这些聚合字段挂到任务对象，不记录逐条失败明细
- `src/components/GalleryView.vue` 只展示聚合统计，不知道失败项细节

### 已知限制

- 旧任务对象中没有 `failedImages`
- 对已经完成的旧任务，只知道 `galleryId`、`url`、磁盘目录和成功 / 失败总数
- 若要支持旧任务补图，需要在重试时动态重新解析原图集并和本地 / Novel 目录做比对

## 方案选择

### 方案 A：下载阶段实时记录失败明细，重试时直接使用明细

做法：

- 下载某张图片失败时，记录 `index / imageUrl / reason`
- 状态接口直接返回 `failedImages`
- 前端点击单张重试时，把 `taskId + index` 发给后端

优点：

- 设计清晰
- 新任务体验最好
- 失败定位准确，不依赖后续推断

缺点：

- 对已经完成的旧任务无直接帮助

### 方案 B：只在重试时重新解析图集并推断缺失项

做法：

- 不额外保存失败明细
- 用户点击重试时，再重新解析图集，按目录文件数和编号推断缺失图片

优点：

- 改动小

缺点：

- 推断不稳定
- 失败原因丢失
- 对多张失败、非末尾失败、重编号场景不可靠

### 结论

采用“方案 A + 旧任务兜底”：

- 新任务：实时保存失败明细，支持精准单张重试
- 旧任务：若没有 `failedImages`，则在重试前重新解析图集并与当前目录比对，尽力生成可重试项

## 设计

### 任务模型扩展

图集任务新增字段：

- `failedImages`: 失败图片列表
- `retryingImages`: 当前正在重试的图片序号列表
- `galleryUrl`: 原始图集 URL（复用现有 `url`）

单条失败项结构：

- `index`: 原始图片序号，从 1 开始
- `imageUrl`: 原图 URL
- `reason`: 失败原因
- `status`: `failed | retrying`

### 下载阶段记录失败项

在 `python/image_crawler.py` 的下载循环中：

- 某张图下载失败时，除 `failed_count += 1` 外，同时把失败项写入 `extra.failed_images`
- 某张图下载成功时，不写失败项

在 `python/server.py` 的 `_progress()` 中：

- 若进度回调携带 `failed_images`，则同步到任务对象的 `failedImages`

### 单张重试接口

新增接口：

- `POST /api/gallery/retry-image`

输入：

- `taskId`
- `index`

处理逻辑：

1. 根据 `taskId` 取任务对象
2. 若任务有 `failedImages`，直接定位该 `index` 的原图 URL
3. 若任务没有 `failedImages`，执行旧任务兜底：
   - 重新解析 `task.url`
   - 根据 `task.gallery_id` 或输出目录，检查目标目录已有编号文件
   - 找出缺失序号，并生成临时失败项
4. 调用图片下载帮助函数，仅下载该张图片
5. 根据任务模式写回目标位置：
   - `local`：补写到原输出目录，文件名保持 `NNN.ext`
   - `novel`：补写到 `img/gallery_images/<gallery_id>/<gallery_id>_NNN.ext`
6. 成功后更新：
   - `successCount += 1`
   - `failedCount -= 1`
   - 从 `failedImages` 中移除对应项
   - `detail` 更新为“已补下第 N 张图片”

### 文件命名规则

本地模式：

- 继续沿用 `001.jpg`、`002.jpg` 这种命名

Novel 模式：

- 继续沿用 `1909_001.jpg`、`1909_002.jpg` 这种命名
- 单张重试时按缺失序号直接补位，不重排现有文件

### 前端交互

在图集任务卡片的“图片统计”区域下方增加失败明细块：

- 当 `failedCount > 0` 时显示
- 每条显示：
  - `第 N 张`
  - 失败原因
  - `重试` 按钮

交互规则：

- 点击 `重试` 后按钮进入 loading / disabled
- 成功后列表移除该项
- 统计数字同步更新
- 若全部补齐，则失败区自动消失

### 旧任务兜底策略

针对已完成但没有失败明细的旧任务：

- 重新解析当前图集 URL，得到原始 `image_urls`
- 根据目标目录现有文件名提取已有序号
- 缺失序号视为可疑失败项
- 失败原因统一标为“旧任务未保留失败明细，按目录缺口推断”

该兜底只保证“能补”，不保证还原原始失败原因。

## 错误处理

以下情况返回明确错误：

- `taskId` 不存在
- 指定 `index` 不在失败项中
- 任务缺少 `gallery_id` 且输出目录不可用
- 重新解析图集失败，无法推断旧任务缺失项
- 单张图片重试下载仍失败

前端提示应直接展示后端错误消息。

## 测试策略

### 后端测试

补充最小失败测试与回归测试，覆盖：

- 下载进度携带失败明细时，任务状态能返回 `failedImages`
- `retry-image` 成功后会减少 `failedCount` 并移除对应失败项
- `retry-image` 在旧任务无 `failedImages` 时，能通过目录缺口推断缺失序号

### 前端类型测试

至少保证：

- `DownloadTask` 增加 `failedImages / retryingImages`
- Electron API 增加图集单张重试方法

### 手工验收

以 `xx.knit.bid/article/25144/` 为样本，验收：

- 失败 `1` 张时，界面能显示具体“第 N 张”
- 点击重试后，该张能补入 `gallery_images/1909`
- 成功数从 `83` 变 `84`
- 失败数从 `1` 变 `0`

## 实现范围

预计修改：

- `python/image_crawler.py`
- `python/server.py`
- `electron/main.ts`
- `electron/preload.ts`
- `src/types/index.ts`
- `src/components/GalleryView.vue`
- `python/tests/test_xx_knit_bid_parser.py`

## 验收标准

完成后系统应满足：

- 图集任务失败时可看到失败图片明细
- 支持单张重试
- Novel 模式可直接补图到对应 Gallery
- 旧任务在可推断时也能单张重试
- 统计信息会随重试成功实时更新

## 风险与应对

风险：

- 某些站点图片扩展名与原 URL 后缀不一致，补图命名可能依赖实际内容识别
- 旧任务若目录已被手工改动，按缺口推断可能不完全可靠

应对：

- 单张重试继续沿用现有扩展名检测逻辑
- 对旧任务推断结果明确标注为“推断缺失项”，避免误导
