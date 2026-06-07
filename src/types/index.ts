export type TabType = 'download' | 'history' | 'settings' | 'about'

export interface VideoInfo {
  title: string
  cover: string
  m3u8_url: string | null
  actresses: string[]
  tags: string[]
  code: string
  release_date: string
  duration: string
}

export interface DownloadTask {
  id: string
  filename: string
  title: string
  cover: string
  status: 'pending' | 'downloading' | 'merging' | 'completed' | 'error' | 'paused'
  progress: number
  speed: string
  size: string
  outputPath: string
  error?: string
  createdAt: number
  /** 下载模式：local=下载到本地，novel=入库到 novel 项目 */
  downloadMode?: 'local' | 'novel'
}

export interface HistoryRecord {
  id: string
  title: string
  filename: string
  cover: string
  actresses: string[]
  tags: string[]
  code: string
  outputPath: string
  fileSize: string
  downloadedAt: number
  downloadMode?: 'local' | 'novel'
}

export interface AppSettings {
  downloadDir: string
  maxConcurrent: number
  autoMerge: boolean
  keepTempFiles: boolean
  proxy: string
  /** novel 项目路径，用于入库功能 */
  novelProjectPath: string
}

/** 入库到 novel 项目的结果 */
export interface NovelImportResult {
  success: boolean
  galleryId?: number
  message?: string
}

// Electron API 类型声明
export interface ElectronAPI {
  clipboard: {
    readText: () => Promise<string>
    writeText: (text: string) => Promise<void>
  }
  dialog: {
    selectFolder: () => Promise<string | null>
    selectFile: () => Promise<string | null>
  }
  app: {
    getVersion: () => Promise<string>
    getDefaultDownloadDir: () => Promise<string>
  }
  shell: {
    openPath: (filePath: string) => Promise<void>
    openExternal: (url: string) => Promise<void>
  }
  window: {
    minimize: () => Promise<void>
    maximize: () => Promise<void>
    close: () => Promise<void>
  }
  video: {
    parse: (url: string) => Promise<VideoInfo>
    download: (options: { url: string; outputDir: string; downloadMode?: 'local' | 'novel'; novelProjectPath?: string }) => Promise<DownloadTask>
    pauseDownload: (taskId: string) => Promise<void>
    resumeDownload: (taskId: string) => Promise<void>
    cancelDownload: (taskId: string) => Promise<void>
  }
  onDownloadProgress: (callback: (data: { taskId: string; progress: number; speed: string; status?: string }) => void) => () => void
  onDownloadCompleted: (callback: (data: { taskId: string; filename: string }) => void) => () => void
  onDownloadError: (callback: (data: { taskId: string; error: string }) => void) => () => void
  history: {
    get: () => Promise<HistoryRecord[]>
    add: (record: Omit<HistoryRecord, 'id' | 'downloadedAt'>) => Promise<void>
    delete: (id: string) => Promise<void>
    clear: () => Promise<void>
  }
  onMenuShowAbout: (callback: () => void) => () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
