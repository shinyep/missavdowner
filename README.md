# MissAV Downloader

MissAV 视频下载器 - Windows 11 原生桌面应用

## 功能特性

- 🎬 从 missav.ws 解析和下载视频
- 📊 实时下载进度和速度显示
- 🔄 自动合并 m3u8 流为 mp4 格式
- 📝 提取视频元数据（标题、演员、标签等）
- 📁 下载队列管理
- 📚 下载历史记录

## 技术栈

- **Electron 30** - 跨平台桌面应用框架
- **Vue 3** - 前端 UI 框架
- **TypeScript** - 类型安全的 JavaScript
- **Vite 5** - 构建工具
- **Tailwind CSS** - CSS 框架
- **Playwright** - 浏览器自动化
- **FFmpeg** - 视频处理

## 系统要求

- Windows 10/11 (64-bit)
- **Python 3.10+** (必须，并添加到 PATH)
- **Playwright** (用于浏览器自动化)
- FFmpeg (已包含在安装包中)

### 安装 Python 依赖

```bash
# 安装 Python 依赖
pip install playwright httpx beautifulsoup4 flask flask-cors

# 安装 Playwright 浏览器
playwright install chromium
```

## 安装使用

### 方式一：使用安装程序

1. 下载 `MissAV Downloader Setup 1.0.0.exe`
2. 运行安装程序
3. 按提示完成安装
4. 启动应用

### 方式二：从源码运行

```bash
# 克隆项目
git clone <repo-url>
cd videodown

# 安装 Node.js 依赖
npm install

# 安装 Python 依赖
pip install -r python/requirements.txt
playwright install chromium

# 复制 ffmpeg.exe 到 resources 目录

# 运行开发模式
npm run dev

# 构建生产版本
npm run build
```

## 使用方法

1. 启动应用
2. 粘贴 missav 视频链接到输入框
3. 点击"解析视频"按钮
4. 等待解析完成，查看视频信息
5. 选择保存目录
6. 点击"开始下载"
7. 等待下载和合并完成

## 项目结构

```
videodown/
├── electron/           # Electron 主进程
│   ├── main.ts        # 主进程入口
│   └── preload.ts     # 预加载脚本
├── src/               # Vue 前端
│   ├── components/    # Vue 组件
│   ├── types/         # TypeScript 类型
│   └── App.vue        # 根组件
├── python/            # Python 后端
│   ├── crawler.py     # 爬虫核心
│   └── server.py      # Flask API 服务器
├── resources/         # 资源文件
│   └── ffmpeg.exe     # FFmpeg 可执行文件
└── package.json       # 项目配置
```

## 开发说明

### 开发模式
```bash
npm run dev
```

### 构建打包
```bash
npm run build
```

### 类型检查
```bash
npx vue-tsc --noEmit
```

## 注意事项

⚠️ 本工具仅供个人学习和研究使用，请勿用于商业用途。

## 许可证

MIT License
