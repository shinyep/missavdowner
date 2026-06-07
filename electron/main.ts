import { app, BrowserWindow, ipcMain, dialog, shell, Menu, clipboard, net } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { spawn, ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.APP_ROOT = path.join(__dirname, '..')

export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let win: BrowserWindow | null = null
let pythonProcess: ChildProcess | null = null
let serverReady = false

// Python 后端端口
const PYTHON_PORT = 15678

// 获取 ffmpeg 路径
function getFfmpegPath(): string {
  const isWin = process.platform === 'win32'
  const ffmpegName = isWin ? 'ffmpeg.exe' : 'ffmpeg'

  const possiblePaths = [
    path.join(process.env.APP_ROOT || '', 'resources', ffmpegName),
    path.join(process.resourcesPath || '', ffmpegName),
    path.join(__dirname, '..', '..', 'resources', ffmpegName),
    ffmpegName
  ]

  for (const p of possiblePaths) {
    try {
      if (fs.existsSync(p)) return p
    } catch {}
  }

  return ffmpegName
}

// 获取资源目录 (打包后是 resources，开发时是项目根目录)
function getResourcesPath(): string {
  if (app.isPackaged) {
    return process.resourcesPath || path.join(__dirname, '..', '..')
  }
  return process.env.APP_ROOT || path.join(__dirname, '..')
}

// 获取 Python 可执行文件路径
function getPythonPath(): string {
  const isWin = process.platform === 'win32'
  const pythonName = isWin ? 'python.exe' : 'python3'
  const resPath = getResourcesPath()

  const possiblePaths = [
    // 开发时的虚拟环境
    path.join(resPath, 'python', '.venv', 'Scripts', pythonName),
    path.join(resPath, 'python', '.venv', 'bin', pythonName),
    // 常见 Python 安装路径 (Windows)
    isWin ? 'C:\\Python312\\python.exe' : '',
    isWin ? 'C:\\Python311\\python.exe' : '',
    isWin ? 'C:\\Python310\\python.exe' : '',
    isWin ? path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'Python', 'Python312', 'python.exe') : '',
    isWin ? path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'Python', 'Python311', 'python.exe') : '',
    isWin ? path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'Python', 'Python310', 'python.exe') : '',
    // 系统 PATH
    pythonName,
    'python',
    'python3',
  ]

  for (const p of possiblePaths) {
    if (!p) continue
    try {
      if (fs.existsSync(p)) {
        console.log(`Found Python at: ${p}`)
        return p
      }
    } catch {}
  }

  console.warn('Python not found, falling back to:', pythonName)
  return pythonName
}

// 启动后端服务器
function startPythonBackend() {
  const pythonPath = getPythonPath()
  const resPath = getResourcesPath()
  const serverPy = path.join(resPath, 'python', 'server.py')

  console.log(`App packaged: ${app.isPackaged}`)
  console.log(`Resources path: ${resPath}`)
  console.log(`Python path: ${pythonPath}`)
  console.log(`Server script: ${serverPy}`)

  // 检查 server.py 是否存在
  if (!fs.existsSync(serverPy)) {
    console.error(`server.py not found at: ${serverPy}`)
    showPythonError(`Python 服务文件不存在: ${serverPy}`)
    return
  }

  console.log(`Starting backend: ${pythonPath} ${serverPy}`)

  // 历史记录存储目录
  const historyDir = path.join(os.homedir(), '.missav')
  if (!fs.existsSync(historyDir)) {
    fs.mkdirSync(historyDir, { recursive: true })
  }
  console.log(`History directory: ${historyDir}`)

  try {
    pythonProcess = spawn(pythonPath, [serverPy, '--port', String(PYTHON_PORT)], {
      cwd: path.join(resPath, 'python'),
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        MISSAV_HISTORY_DIR: historyDir
      },
      windowsHide: true
    })

    pythonProcess.stdout?.on('data', (data) => {
      console.log(`[Server] ${data.toString().trim()}`)
    })

    pythonProcess.stderr?.on('data', (data) => {
      const msg = data.toString().trim()
      console.error(`[Server Error] ${msg}`)
      // 发送启动错误到渲染进程
      if (win && (msg.includes('Error') || msg.includes('Traceback') || msg.includes('ModuleNotFoundError') || msg.includes('ImportError'))) {
        win.webContents.send('download:error', {
          taskId: 'server',
          error: `服务器启动失败: ${msg.substring(0, 200)}`
        })
      }
    })

    pythonProcess.on('error', (err) => {
      console.error('Failed to start server:', err)
      showPythonError('无法启动后端服务，请确保已安装 Python 3.10+')
      pythonProcess = null
    })

    pythonProcess.on('close', (code) => {
      console.log(`Server process exited with code ${code}`)
      pythonProcess = null
    })
  } catch (err) {
    console.error('Error spawning server:', err)
    showPythonError('启动后端服务失败')
  }
}

// 显示 Python 错误提示
function showPythonError(message: string) {
  if (win) {
    dialog.showMessageBox(win, {
      type: 'warning',
      title: 'Python 环境问题',
      message: '无法启动后端服务',
      detail: `${message}\n\n本应用需要 Python 3.10+ 和 Playwright 才能运行。\n\n安装步骤:\n1. 安装 Python 3.10+: https://www.python.org/downloads/\n2. 安装依赖: pip install playwright httpx beautifulsoup4 flask flask-cors\n3. 安装浏览器: playwright install chromium`,
      buttons: ['确定', '打开 Python 下载页面'],
    }).then((result) => {
      if (result.response === 1) {
        shell.openExternal('https://www.python.org/downloads/')
      }
    })
  }
}

// 停止 Python 后端
function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
}

// 调用 Python API
async function waitForServer(maxRetries: number = 30): Promise<void> {
  const url = `http://127.0.0.1:${PYTHON_PORT}/health`
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url)
      if (response.ok) {
        console.log(`Python server is ready (attempt ${i + 1})`)
        return
      }
    } catch {
      // Server not ready yet
    }
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  throw new Error(`Python server failed to start after ${maxRetries}s`)
}

async function callPythonAPI(endpoint: string, method: string = 'GET', body?: any): Promise<any> {
  const url = `http://127.0.0.1:${PYTHON_PORT}${endpoint}`
  const options: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }

  if (body && method === 'POST') {
    options.body = JSON.stringify(body)
  }

  try {
    const response = await fetch(url, options)
    return await response.json()
  } catch (error) {
    console.error(`Python API call failed: ${error}`)
    throw error
  }
}

// 默认下载目录
function getDefaultDownloadDir(): string {
  return path.join(os.homedir(), 'Downloads', 'MissAV')
}

// 确保下载目录存在
function ensureDownloadDir(dir: string): string {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
  return dir
}

// 存储下载任务
const downloadTasks = new Map<string, any>()

// 创建窗口
function createWindow() {
  win = new BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#1a1a2e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  // 测试模式下打开 devtools
  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
    win.webContents.openDevTools()
  } else {
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

// 设置 IPC 处理器
function setupIPC() {
  // 剪贴板
  ipcMain.handle('clipboard:readText', () => {
    return clipboard.readText()
  })

  ipcMain.handle('clipboard:writeText', (_, text: string) => {
    clipboard.writeText(text)
  })

  // 对话框
  ipcMain.handle('dialog:selectFolder', async () => {
    const result = await dialog.showOpenDialog(win!, {
      properties: ['openDirectory']
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('dialog:selectFile', async () => {
    const result = await dialog.showOpenDialog(win!, {
      properties: ['openFile']
    })
    return result.canceled ? null : result.filePaths[0]
  })

  // 应用信息
  ipcMain.handle('app:getVersion', () => {
    return app.getVersion()
  })

  ipcMain.handle('app:getDefaultDownloadDir', () => {
    return ensureDownloadDir(getDefaultDownloadDir())
  })

  // Shell 操作
  ipcMain.handle('shell:openPath', (_, filePath: string) => {
    shell.openPath(filePath)
  })

  ipcMain.handle('shell:openExternal', (_, url: string) => {
    shell.openExternal(url)
  })

  // 窗口控制
  ipcMain.handle('window:minimize', () => {
    win?.minimize()
  })

  ipcMain.handle('window:maximize', () => {
    if (win?.isMaximized()) {
      win.unmaximize()
    } else {
      win?.maximize()
    }
  })

  ipcMain.handle('window:close', () => {
    win?.close()
  })

  // 视频解析
  ipcMain.handle('video:parse', async (_, url: string) => {
    try {
      if (!serverReady) {
        console.log('Waiting for Python server to be ready...')
        await waitForServer()
        serverReady = true
      }
      const result = await callPythonAPI('/api/parse', 'POST', { url })
      return result
    } catch (error: any) {
      throw new Error(error.message || '解析失败')
    }
  })

  // 视频下载（支持本地下载 / 入库到 novel 项目）
  ipcMain.handle('video:download', async (_, options: {
    url: string; outputDir: string; maxConcurrent?: number; proxy?: string;
    autoMerge?: boolean; keepTempFiles?: boolean;
    downloadMode?: 'local' | 'novel'; novelProjectPath?: string; novelBackendUrl?: string
  }) => {
    try {
      const downloadMode = options.downloadMode || 'local'

      // 入库模式：下载完成后调用入库 API
      if (downloadMode === 'novel') {
        const result = await callPythonAPI('/api/download-and-import', 'POST', {
          url: options.url,
          maxConcurrent: options.maxConcurrent || 16,
          proxy: options.proxy || '',
          autoMerge: options.autoMerge !== false,
          keepTempFiles: options.keepTempFiles || false,
          novelProjectPath: options.novelProjectPath || '',
          novelBackendUrl: options.novelBackendUrl || 'http://127.0.0.1:8002'
        })
        const taskId = result.task_id

        // 轮询进度
        const pollProgress = async () => {
          try {
            const progress = await callPythonAPI(`/api/progress/${taskId}`)

            win?.webContents.send('download:progress', {
              taskId,
              progress: progress.progress,
              speed: progress.speed,
              status: progress.status
            })

            if (progress.status === 'completed') {
              win?.webContents.send('download:completed', {
                taskId,
                filename: result.filename
              })
              return
            }

            if (progress.status === 'error') {
              win?.webContents.send('download:error', {
                taskId,
                error: progress.error || '入库失败'
              })
              return
            }

            setTimeout(pollProgress, 1500)
          } catch (error) {
            console.error('Progress poll error:', error)
          }
        }

        pollProgress()

        return {
          id: taskId,
          filename: result.filename || '入库处理中...',
          title: '',
          cover: '',
          status: 'downloading',
          progress: 0,
          speed: '等待中',
          size: '',
          outputPath: '',
          createdAt: Date.now(),
          downloadMode: 'novel'
        }
      }

      // 本地下载模式
      const result = await callPythonAPI('/api/download', 'POST', {
        url: options.url,
        outputDir: options.outputDir,
        maxConcurrent: options.maxConcurrent || 16,
        proxy: options.proxy || '',
        autoMerge: options.autoMerge !== false,
        keepTempFiles: options.keepTempFiles || false
      })
      const taskId = result.task_id

      const pollProgress = async () => {
        try {
          const progress = await callPythonAPI(`/api/progress/${taskId}`)

          win?.webContents.send('download:progress', {
            taskId,
            progress: progress.progress,
            speed: progress.speed,
            status: progress.status
          })

          if (progress.status === 'completed') {
            win?.webContents.send('download:completed', {
              taskId,
              filename: result.filename
            })
            return
          }

          if (progress.status === 'error') {
            win?.webContents.send('download:error', {
              taskId,
              error: progress.error || '下载失败'
            })
            return
          }

          setTimeout(pollProgress, 1000)
        } catch (error) {
          console.error('Progress poll error:', error)
        }
      }

      pollProgress()

      return {
        id: taskId,
        filename: result.filename || 'downloading...',
        title: '',
        cover: '',
        status: 'downloading',
        progress: 0,
        speed: '0 MB/s',
        size: '',
        outputPath: path.join(options.outputDir, result.filename || ''),
        createdAt: Date.now()
      }
    } catch (error: any) {
      throw new Error(error.message || '下载失败')
    }
  })

  // 暂停下载
  ipcMain.handle('download:pause', async (_, taskId: string) => {
    try {
      await callPythonAPI(`/api/pause/${taskId}`, 'POST')
    } catch (error) {
      console.error('Pause error:', error)
    }
  })

  // 历史记录
  ipcMain.handle('history:get', async () => {
    try {
      const result = await callPythonAPI('/api/history')
      return result.records || []
    } catch {
      return []
    }
  })

  ipcMain.handle('history:delete', async (_, id: string) => {
    try {
      await callPythonAPI(`/api/history/${id}`, 'DELETE')
    } catch (error) {
      console.error('Delete history error:', error)
    }
  })

  ipcMain.handle('history:clear', async () => {
    try {
      await callPythonAPI('/api/history', 'DELETE')
    } catch (error) {
      console.error('Clear history error:', error)
    }
  })

  // 图片代理 - 解决跨域问题
  ipcMain.handle('app:fetchImage', async (_, url: string) => {
    try {
      const response = await net.fetch(url, {
        headers: {
          'Referer': 'https://missav.ws/',
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
      })
      const buffer = await response.arrayBuffer()
      const base64 = Buffer.from(buffer).toString('base64')
      const contentType = response.headers.get('content-type') || 'image/jpeg'
      return `data:${contentType};base64,${base64}`
    } catch (error) {
      console.error('Fetch image error:', error)
      return null
    }
  })
}

// 应用生命周期
app.whenReady().then(async () => {
  setupIPC()
  createWindow()
  startPythonBackend()

  // 后台等待服务器就绪
  waitForServer().then(() => {
    serverReady = true
    console.log('Python server ready confirmation complete')
  }).catch((err) => {
    console.error('Server ready check failed:', err.message)
  })
})

app.on('window-all-closed', () => {
  stopPythonBackend()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.on('before-quit', () => {
  stopPythonBackend()
})


