/// <reference types="vite-plugin-electron/electron-env" />

declare namespace NodeJS {
  interface ProcessEnv {
    APP_ROOT: string
    VITE_PUBLIC: string
  }
}

interface ElectronAPI {
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
    parse: (url: string) => Promise<any>
    download: (options: { url: string; outputDir: string }) => Promise<any>
    pauseDownload: (taskId: string) => Promise<void>
  }
  onDownloadProgress: (callback: (data: any) => void) => () => void
  history: {
    get: () => Promise<any[]>
    delete: (id: string) => Promise<void>
    clear: () => Promise<void>
  }
  onMenuShowAbout: (callback: () => void) => () => void
}

declare interface Window {
  electronAPI: ElectronAPI
}
