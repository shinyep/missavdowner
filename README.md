# MissAV Downloader

多功能媒体下载器 — Windows 桌面应用，支持视频和图集下载

## 功能特性

### 视频下载

- 🎬 支持 missav.ws / kissjav.com 等视频站点
- 📊 实时下载进度、速度和详细阶段提示
- 🔄 m3u8 流自动合并为 mp4
- 📝 提取视频元数据（标题、演员、标签、番号）
- 🎞️ 支持转码并入库到自建 Novel 媒体库
- ⏸️ 下载暂停/恢复

### 图集下载

- 🖼️ 支持 4khd / szzs / kkc3 / buondua / photos18 / tokyobombers / foamgirl / hotgirl / phimvuspot 等图集站点
- 🔍 两步操作：解析图集预览 → 选择模式 → 下载
- 📄 自动提取分页，全部图片一键下载
- 📈 任务卡片显示详细进度：总张数 / 当前第几张 / 成功 / 失败
- 💾 支持下载到本地或直接入库 Novel 图集库
- 🧹 入库模式自动清理临时缓存

## 技术栈

- **Electron 30** · **Vue 3** · **TypeScript** · **Vite 5** · **Tailwind CSS**
- **Python Flask** — 本地 API 后端
- **Playwright** + **httpx** — 双引擎页面加载，自动反爬适配
- **BeautifulSoup** — HTML 解析
- **FFmpeg** — 视频转码处理

## 系统要求

- Windows 10/11 (64-bit)
- **Python 3.10+**（必须添加到 PATH）

### Python 依赖安装

```
pip install playwright httpx beautifulsoup4 flask flask-cors Pillow
playwright install chromium
```

## 安装使用

### 安装程序

从 [Releases](https://github.com/shinyep/missavdowner/releases) 下载最新 MissAV Downloader Setup x.x.x.exe，运行安装即可。

### 从源码运行

```
git clone https://github.com/shinyep/missavdowner.git
cd videodown
npm install
pip install -r python/requirements.txt
playwright install chromium
npm run dev
```

## 使用方法

### 视频下载

1. 粘贴 missav / kissjav 视频链接
2. 点击「解析视频」
3. 查看视频信息，选择保存方式（本地 / 入库）
4. 点击「开始下载」

### 图集下载

1. 粘贴 4khd / szzs / kkc3 / buondua / photos18 / tokyobombers / foamgirl / hotgirl / phimvuspot 图集链接
2. 点击「解析图集」查看标题和图片数量
3. 选择「下载到本地」或「入库到 Novel」
4. 点击「开始下载」

## 项目结构

```
videodown/
├── electron/              # Electron 主进程
│   ├── main.ts           # 主进程入口 + IPC 处理
│   └── preload.ts        # 预加载脚本
├── src/                  # Vue 前端
│   ├── components/       # 组件
│   │   ├── GalleryView.vue   # 图集下载
│   │   └── ...
│   ├── types/            # TypeScript 类型定义
│   └── App.vue           # 根组件
├── python/               # Python 后端
│   ├── server.py         # Flask API 服务器
│   ├── crawler.py        # missav 爬虫
│   ├── kissjav_crawler.py    # kissjav 爬虫
│   ├── image_crawler.py      # 图集爬虫（4khd/szzs/kkc3/buondua/photos18/tokyobombers/foamgirl/hotgirl/phimvuspot）
│   └── novel_import.py       # Novel 项目入库
├── resources/            # 资源文件
│   └── ffmpeg.exe        # FFmpeg 可执行文件
└── package.json
```

## 开发

```
npm run dev          # 开发模式
npm run build        # 构建打包
npx vue-tsc --noEmit # 类型检查
```

## 注意事项

⚠️ 本工具仅供个人学习和研究使用，请勿用于商业用途或侵犯版权。

## 许可证

MIT License



