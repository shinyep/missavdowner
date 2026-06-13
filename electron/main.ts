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
      console.error(`[Server Error] ${data.toString().trim()}`)
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
    dialog.showErrorBox('启动错误', message)
  }
}

// 停止后端服务器
function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
}

// 创建主窗口
function createWindow() {
  win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#1a1a2e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  })

  // 开发模式下打开开发者工具
  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
    win.webContents.openDevTools()
  } else {
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }

  win.on('closed', () => {
    win = null
  })
}

// API 调用辅助函数
async function callPythonAPI(endpoint: string, method = 'GET', body?: any) {
  const url = `http://127.0.0.1:${PYTHON_PORT}${endpoint}`
  
  const options: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json'
    }
  }

  if (body) {
    options.body = JSON.stringify(body)
  }

  try {
    const response = await fetch(url, options)
    const data = await response.json()
    
    if (!response.ok) {
      throw new Error(data.error || 'API request failed')
    }
    
    return data
  } catch (error) {
    console.error(`API call failed: ${method} ${endpoint}`, error)
    throw error
  }
}

// 设置 IPC 处理器
function setupIPC() {
  // 窗口控制
  ipcMain.on('window:minimize', () => win?.minimize())
  ipcMain.on('window:maximize', () => {
    if (win?.isMaximized()) {
      win.unmaximize()
    } else {
      win?.maximize()
    }
  })
  ipcMain.on('window:close', () => win?.close())

  // 应用信息
  ipcMain.handle('app:getVersion', () => app.getVersion())
  ipcMain.handle('app:getDefaultDownloadDir', () => {
    return path.join(os.homedir(), 'Downloads')
  })

  // 剪贴板
  ipcMain.handle('clipboard:readText', () => clipboard.readText())
  ipcMain.handle('clipboard:writeText', (_, text: string) => {
    clipboard.writeText(text); return true
  })

  // 对话框
  ipcMain.handle('dialog:selectFolder', async () => {
    const result = await dialog.showOpenDialog(win!, {
      properties: ['openDirectory']
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('dialog:selectFile', async (_, options: { filters?: { name: string; extensions: string[] }[] }) => {
    const result = await dialog.showOpenDialog(win!, {
      properties: ['openFile'],
      filters: options?.filters
    })
    return result.canceled ? null : result.filePaths[0]
  })

  // Shell 操作
  ipcMain.handle('shell:openPath', async (_, path: string) => {
    await shell.openPath(path)
  })

  ipcMain.handle('shell:openFolder', async (_, folderPath: string) => {
    await shell.openPath(folderPath)
  })

  ipcMain.handle('shell:openExternal', async (_, url: string) => {
    await shell.openExternal(url)
  })

  // 视频解析
  ipcMain.handle('video:parse', async (_, url: string) => {
    try {
      const result = await callPythonAPI('/api/parse', 'POST', { url })
      return result
    } catch (error: any) {
      throw new Error(error.message || '解析失败')
    }
  })

  // 视频下载
  ipcMain.handle('video:download', async (_, options: {
    url: string
    outputDir: string
    maxConcurrent?: number
    proxy?: string
    autoMerge?: boolean
    keepTempFiles?: boolean
    downloadMode?: string
    novelProjectPath?: string
    novelBackendUrl?: string
  }) => {
    try {
      const apiEndpoint = options.downloadMode === 'novel' ? '/api/download-to-novel' : '/api/download'
      const result = await callPythonAPI(apiEndpoint, 'POST', options)
      const taskId = result.task_id

      // 轮询下载进度
      const pollProgress = async () => {
        try {
          const progress = await callPythonAPI(`/api/download-status/${taskId}`)
          
          win?.webContents.send('download:progress', {
            taskId,
            progress: progress.progress,
            speed: progress.speed,
            status: progress.status,
            phase: progress.phase,
            phaseTitle: progress.phaseTitle,
            detail: progress.detail,
            transcodeProgress: progress.transcodeProgress,
            novelVideoId: progress.novelVideoId,
          })

          // 下载完成
          if (progress.status === 'completed') {
            win?.webContents.send('download:completed', {
              taskId,
              filename: result.filename
            })
            return
          }

          // 下载失败
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
    ipcMain.handle('gallery:parse', async (_, options: {
    galleryUrl: string
    proxy?: string
  }) => {
    try {
      return await callPythonAPI('/api/gallery/parse', 'POST', options)
    } catch (error: any) {
      throw new Error(error.message || '图集解析失败')
    }
  })

  ipcMain.handle('gallery:download', async (_, options: {

    galleryUrl: string
    outputDir: string
    downloadMode?: string
    novelProjectPath?: string
    proxy?: string
  }) => {
    try {
      const result = await callPythonAPI('/api/gallery/download', 'POST', options)
      const taskId = result.task_id

      const pollProgress = async () => {
        try {
          const progress = await callPythonAPI(`/api/download-status/${taskId}`)
          win?.webContents.send('download:progress', {
            taskId,
            progress: progress.progress,
            speed: progress.speed,
            status: progress.status,
            phase: progress.phase,
            phaseTitle: progress.phaseTitle,
            detail: progress.detail,
            outputPath: progress.output_path,
            hasVideo: progress.has_video,
            videoCount: progress.video_count,
            mediaType: progress.media_type,
            source: progress.source,
            galleryId: progress.gallery_id,
            novelVideoId: progress.novel_video_id,
          })

          if (progress.status === 'completed') {
            win?.webContents.send('download:completed', {
              taskId,
              filename: progress.filename || result.filename,
              outputPath: progress.output_path
            })
            return
          }

          if (progress.status === 'error') {
            win?.webContents.send('download:error', {
              taskId,
              error: progress.error || '图集下载失败'
            })
            return
          }

          setTimeout(pollProgress, 1000)
        } catch (error) {
          console.error('Gallery progress poll error:', error)
        }
      }

      pollProgress()

      return {
        id: taskId,
        filename: result.filename || '解析中...',
        title: '',
        cover: '',
        status: 'downloading',
        progress: 0,
        speed: '0 张/秒',
        size: '',
        outputPath: options.outputDir || '',
        createdAt: Date.now(),
        downloadMode: options.downloadMode || 'local',
        phase: 'parsing',
        phaseTitle: '解析图集',
        hasVideo: false,
        videoCount: 0,
        mediaType: 'gallery',
        source: 'gallery',
      }
    } catch (error: any) {
      throw new Error(error.message || '图集下载失败')
    }
  })

  ipcMain.handle('download:pause', async (_, taskId: string) => {
    try {
      await callPythonAPI(`/api/pause-download/${taskId}`, 'POST')
    } catch (error) {
      console.error('Pause error:', error)
    }
  })

  // 恢复下载
  ipcMain.handle('download:resume', async (_, taskId: string) => {
    try {
      await callPythonAPI(`/api/resume-download/${taskId}`, 'POST')
    } catch (error) {
      console.error('Resume error:', error)
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
      // 根据 URL 动态设置 Referer
      let referer = 'https://missav.ws/'
      if (url.includes('kissjav.com')) {
        referer = 'https://kissjav.com/'
      } else if (url.includes('kkc3.com')) {
        referer = 'https://www.kkc3.com/'
      } else if (url.includes('buondua')) {
        // buondua CDN 域名：cdn.buondua.us / i2.buondua.us / cdn.buondua.com
        referer = 'https://buondua.com/'
      } else if (url.includes('photos18.com')) {
        referer = 'https://www.photos18.com/'
      } else if (url.includes('phimvuspot.com') || url.includes('thismore.fun') || url.includes('wp.com/im.thismore')) {
        referer = 'https://m.phimvuspot.com/'
      } else if (url.includes('foamgirl.net') || url.includes('cdn.foamgirl.net')) {
        referer = 'https://foamgirl.net/'
      } else if (url.includes('tokyobombers.com')) {
        referer = 'https://www.tokyobombers.com/'
      } else if (url.includes('everiaclub.com') || url.includes('hotgirl.asia')) {
        referer = 'https://hotgirl.asia/'
      } else if (url.includes('xx.knit.bid')) {
        referer = 'https://xx.knit.bid/'
      }
      const response = await net.fetch(url, {
        headers: {
          'Referer': referer,
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
app.whenReady().then(() => {
  setupIPC()
  createWindow()
  startPythonBackend()
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


