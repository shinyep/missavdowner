# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
npm run dev           # 开发模式（Vite + Electron 热重载）
npm run build         # 类型检查 + 构建 + electron-builder 打包
npm run lint          # ESLint 检查 src 目录下的 .ts/.vue 文件
npx vue-tsc --noEmit  # 仅 TypeScript 类型检查（不构建）
```

所有命令都从项目根目录 `G:\videodown` 执行。

## 版本号管理（强制、每次必执行）

**任何代码修改、修复 bug、重新编译打包之前，必须先更新 `package.json` 中的 `version` 字段。** 遵循语义化版本：
- **PATCH**：修复 bug、小改动 → `1.1.4` → `1.1.5`
- **MINOR**：新增功能，向后兼容 → `1.1.5` → `1.2.0`
- **MAJOR**：破坏性变更，不向后兼容 → `1.2.0` → `2.0.0`

执行流程：先改版本号 → 提交时注明新版本 → 再编译打包。

## 架构总览

这是一个 **Electron + Vue 3 + Python Flask** 的混合桌面应用，用于下载视频和图集。三层架构：

### 数据流（完整链路）

```
Vue 前端 (src/components/*.vue)
  → electronAPI.xxx.invoke (preload.ts contextBridge 桥接)
    → Electron 主进程 (electron/main.ts) ipcMain.handle
      → callPythonAPI() 通过 HTTP 调用本地 Flask 服务
        → Python Flask (python/server.py) 端口 15678
          → 爬虫模块解析/下载
```

### 三层职责

| 层 | 目录 | 职责 |
|---|---|---|
| **Vue 渲染进程** | `src/` | UI 界面：下载页、图集页、历史记录、设置、关于 |
| **Electron 主进程** | `electron/` | 启动 Python 后端、IPC 处理、进度轮询、系统对话框、图片代理 |
| **Python 后端** | `python/` | 爬虫解析（Playwright）、视频下载（httpx+ffmpeg）、图集下载、Novel 入库 |

### Electron 主进程关键逻辑

- **启动时**：`app.whenReady()` → `setupIPC()` → `createWindow()` → `startPythonBackend()`
- **Python 后端**：自动搜索 Python 解释器路径（虚拟环境 → 常见安装位置 → 系统 PATH），以子进程方式启动 `server.py --port 15678`
- **进度机制**：后端返回 `task_id`，主进程每秒轮询 `/api/download-status/{task_id}`，通过 IPC 事件 `download:progress` 推送到渲染进程
- **图片代理**：`app:fetchImage` IPC 通过 Electron 原生网络请求下载图片并转 base64，绕开前端跨域限制（Referer 根据域名动态设置）
- **生命周期**：窗口关闭 → `stopPythonBackend()` → 退出

### Python 后端关键设计

- **爬虫分发**：`get_crawler_for_url(url)` 根据域名自动选择 `MissavCrawler` 或 `KissjavCrawler`
- **异步包装**：Python 爬虫全部是 `async/await`，Flask 是同步框架 — 通过 `run_async()` 函数创建新事件循环在线程中执行协程
- **下载模式**：
  - `local` 模式 → `/api/download`：下载到用户指定目录
  - `novel` 模式 → `/api/download-to-novel`：先下载到本地，再通过 Django ORM 模块导入到 Novel 项目的 Gallery 数据库
- **下载引擎差异**：
  - missav：m3u8 流媒体 → 并发下载 ts 片段 → ffmpeg 合并为 mp4
  - kissjav：Base64 解码获得 mp4 直链 → httpx 流式一次下载
  - 图集站点（4khd/szzs/kkc3/buondua）：httpx + Playwright 双引擎加载 → 逐张下载图片；kkc3 走独立 Playwright JS 求值路径（图片 URL 在 data-src 属性中）；buondua 走 Playwright + BeautifulSoup 路径（Joomla 站点，`?page=N` 分页）

### Python 爬虫模块

| 文件 | 类 | 职责 |
|---|---|---|
| `crawler.py` | `MissavCrawler` | Playwright 解析 missav.ws：Cloudflare 处理、m3u8 网络请求监听、元数据提取 |
| `crawler.py` | `VideoDownloader` | httpx 并发下载 m3u8 片段 + ffmpeg 合并 |
| `kissjav_crawler.py` | `KissjavCrawler` | Playwright 解析 kissjav.com：flashvars 正则提取、Base64 解码 video_url |
| `kissjav_crawler.py` | `KissjavVideoDownloader` | httpx 流式下载 mp4 直链 |
| `image_crawler.py` | `ImageGalleryCrawler` | 图集爬虫：URL 规范化（4khd/szzs `/gallery/` → `/content/` + `.html`）、kkc3 Playwright JS 分页提取、buondua Playwright+BS 分页提取、通用图片下载 |
| `novel_import.py` | — | 通过内联 Django 脚本将视频/图片导入 Novel 项目数据库 |

### Vue 前端组件

所有页面在 `src/App.vue` 中以 `v-show` 方式切换：

| 组件 | 功能 |
|---|---|
| `DownloadView.vue` | 视频下载主页：URL 输入、解析预览、本地/入库模式切换、下载队列 |
| `GalleryView.vue` | 图集下载页：解析图集 → 预览 → 选择模式 → 下载 |
| `HistoryView.vue` | 历史记录列表 |
| `SettingsView.vue` | 设置：下载目录、并发数、代理、Novel 项目路径 |
| `AboutView.vue` | 版本信息 |
| `Header.vue` | 顶部导航栏 + 窗口控制按钮（自绘标题栏） |

### 关键配置

- **窗口**：1200×800，无系统标题栏（`frame: false`），自绘深色标题栏
- **Python 端口**：`15678`
- **历史记录**：`~/.missav/history.json`，最多保留 200 条
- **FFmpeg**：打包到 `resources/ffmpeg.exe`，开发时从项目根 `resources/` 读取
- **打包输出**：`release/` 目录，NSIS 安装程序
