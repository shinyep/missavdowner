import { ipcRenderer, contextBridge } from 'electron'

// 暴露 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 剪贴板
  clipboard: {
    readText: () => ipcRenderer.invoke('clipboard:readText'),
    writeText: (text: string) => ipcRenderer.invoke('clipboard:writeText', text),
  },

  // 对话框
  dialog: {
    selectFolder: () => ipcRenderer.invoke('dialog:selectFolder'),
    selectFile: () => ipcRenderer.invoke('dialog:selectFile'),
  },

  // 应用信息
  app: {
    getVersion: () => ipcRenderer.invoke('app:getVersion'),
    getDefaultDownloadDir: () => ipcRenderer.invoke('app:getDefaultDownloadDir'),
    fetchImage: (url: string) => ipcRenderer.invoke('app:fetchImage', url),
  },

  // Shell 操作
  shell: {
    openPath: (filePath: string) => ipcRenderer.invoke('shell:openPath', filePath),
    openFolder: (filePath: string) => ipcRenderer.invoke('shell:openFolder', filePath),
    openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url),
  },

  // 窗口控制
  window: {
    minimize: () => ipcRenderer.send('window:minimize'),
    maximize: () => ipcRenderer.send('window:maximize'),
    close: () => ipcRenderer.send('window:close'),
  },

  // 视频操作
  video: {
    parse: (url: string) => ipcRenderer.invoke('video:parse', url),
    download: (options: { url: string; outputDir: string; maxConcurrent?: number; proxy?: string; autoMerge?: boolean; keepTempFiles?: boolean; downloadMode?: string; novelProjectPath?: string; novelBackendUrl?: string }) => ipcRenderer.invoke('video:download', options),
    pauseDownload: (taskId: string) => ipcRenderer.invoke('download:pause', taskId),
    retryTranscode: (options: { videoId: number; novelProjectPath?: string }) => ipcRenderer.invoke('video:retryTranscode', options),
  },

  // 图集操作
  gallery: {
    parse: (options: { galleryUrl: string; proxy?: string }) => ipcRenderer.invoke('gallery:parse', options),
    download: (options: { galleryUrl: string; outputDir: string; downloadMode?: string; novelProjectPath?: string; proxy?: string }) => ipcRenderer.invoke('gallery:download', options),
    retryImage: (options: { taskId: string; index: number; proxy?: string }) => ipcRenderer.invoke('gallery:retryImage', options),
  },

  // 下载进度监听
  onDownloadProgress: (callback: (data: any) => void) => {
    const handler = (_: any, data: any) => callback(data)
    ipcRenderer.on('download:progress', handler)
    return () => {
      ipcRenderer.off('download:progress', handler)
    }
  },

  // 下载完成监听
  onDownloadCompleted: (callback: (data: any) => void) => {
    const handler = (_: any, data: any) => callback(data)
    ipcRenderer.on('download:completed', handler)
    return () => {
      ipcRenderer.off('download:completed', handler)
    }
  },

  // 下载错误监听
  onDownloadError: (callback: (data: any) => void) => {
    const handler = (_: any, data: any) => callback(data)
    ipcRenderer.on('download:error', handler)
    return () => {
      ipcRenderer.off('download:error', handler)
    }
  },

  // 历史记录
  history: {
    get: () => ipcRenderer.invoke('history:get'),
    delete: (id: string) => ipcRenderer.invoke('history:delete', id),
    clear: () => ipcRenderer.invoke('history:clear'),
  },

  // 菜单事件监听
  onMenuShowAbout: (callback: () => void) => {
    const handler = () => callback()
    ipcRenderer.on('menu:showAbout', handler)
    return () => {
      ipcRenderer.off('menu:showAbout', handler)
    }
  },
})

// Preload 脚本加载完成
function domReady(condition: DocumentReadyState[] = ['complete', 'interactive']) {
  return new Promise((resolve) => {
    if (condition.includes(document.readyState)) {
      resolve(true)
    } else {
      document.addEventListener('readystatechange', () => {
        if (condition.includes(document.readyState)) {
          resolve(true)
        }
      })
    }
  })
}

const safeDOM = {
  append(parent: HTMLElement, child: HTMLElement) {
    if (!Array.from(parent.children).find(e => e === child)) {
      return parent.appendChild(child)
    }
  },
  remove(parent: HTMLElement, child: HTMLElement) {
    if (Array.from(parent.children).find(e => e === child)) {
      return parent.removeChild(child)
    }
  },
}

function useLoading() {
  const className = `loaders-css__square-spin`
  const styleContent = `
@keyframes square-spin {
  25% { transform: perspective(100px) rotateX(180deg) rotateY(0); }
  50% { transform: perspective(100px) rotateX(180deg) rotateY(180deg); }
  75% { transform: perspective(100px) rotateX(0) rotateY(180deg); }
  100% { transform: perspective(100px) rotateX(0) rotateY(0); }
}
.${className} > div {
  animation-fill-mode: both;
  width: 50px;
  height: 50px;
  background: #6c5ce7;
  animation: square-spin 3s 0s cubic-bezier(0.09, 0.57, 0.49, 0.9) infinite;
}
.app-loading-wrap {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1a1a2e;
  z-index: 9;
}
    `
  const oStyle = document.createElement('style')
  const oDiv = document.createElement('div')

  oStyle.id = 'app-loading-style'
  oStyle.innerHTML = styleContent
  oDiv.className = 'app-loading-wrap'
  oDiv.innerHTML = `<div class="${className}"><div></div></div>`

  return {
    appendLoading() {
      safeDOM.append(document.head, oStyle)
      safeDOM.append(document.body, oDiv)
    },
    removeLoading() {
      safeDOM.remove(document.head, oStyle)
      safeDOM.remove(document.body, oDiv)
    },
  }
}

const { appendLoading, removeLoading } = useLoading()
domReady().then(appendLoading)

window.onmessage = (ev) => {
  ev.data.payload === 'removeLoading' && removeLoading()
}

setTimeout(removeLoading, 4999)
