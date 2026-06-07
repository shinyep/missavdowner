<template>
  <div class="flex-1 flex overflow-hidden">
    <!-- Left Panel -->
    <section class="w-[65%] flex flex-col bg-surface relative">
      <div class="flex-1 overflow-y-auto px-8 py-6">
        <div class="max-w-xl mx-auto w-full flex flex-col gap-6">
          <!-- Title -->
          <div class="flex flex-col gap-1">
            <h1 class="font-headline text-2xl font-bold leading-tight text-on-surface">MissAV 视频下载</h1>
            <p class="text-on-surface-variant text-sm">粘贴 missav 视频链接，解析后下载高清视频</p>
          </div>

          <!-- URL Input -->
          <div class="flex flex-col gap-3">
            <div class="relative focus-glow rounded-md">
              <textarea
                ref="urlInput"
                v-model="url"
                aria-label="粘贴视频链接"
                class="w-full h-24 bg-surface-container-highest rounded-md p-3 text-on-surface placeholder:text-outline-variant resize-none font-body text-sm border-2 border-transparent focus:border-primary focus:outline-none transition-all"
                placeholder="在此粘贴 missav 视频链接，例如: https://missav.ws/xxx-xxx"
                @keydown.enter.prevent="parseVideo"
              />
            </div>
            <div class="flex gap-3">
              <button
                class="flex-1 flex items-center justify-center gap-2 rounded-md h-10 bg-surface-container-highest text-on-surface font-headline font-semibold text-sm hover:bg-surface-variant transition-colors border border-outline-variant/10"
                @click="pasteUrl"
              >
                <span class="material-symbols-outlined text-base">content_paste</span>
                <span>粘贴链接</span>
              </button>
              <button
                class="flex-[1.5] flex items-center justify-center gap-2 rounded-md h-10 font-headline font-semibold text-sm transition-all border-2 gradient-btn disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="isParsing || !url.trim()"
                @click="parseVideo"
              >
                <span v-if="isParsing" class="material-symbols-outlined text-base animate-spin">sync</span>
                <span v-else class="material-symbols-outlined text-base">bolt</span>
                <span>{{ isParsing ? '解析中...' : '解析视频' }}</span>
              </button>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="flex items-center gap-2 p-3 bg-error-container/30 border border-error/20 rounded-md">
            <span class="material-symbols-outlined text-error text-base">error</span>
            <span class="text-sm text-error">{{ errorMsg }}</span>
          </div>

          <!-- 成功入库提示 -->
          <div v-if="importSuccessMsg" class="flex items-center gap-2 p-3 bg-primary/10 border border-primary/20 rounded-md">
            <span class="material-symbols-outlined text-primary text-base">check_circle</span>
            <span class="text-sm text-primary">{{ importSuccessMsg }}</span>
          </div>

          <!-- 解析结果预览 -->
          <div v-if="videoInfo" class="mt-2 flex flex-col gap-4">
            <h3 class="font-headline text-sm font-bold text-on-surface border-b border-outline-variant/20 pb-2">解析结果预览</h3>

            <!-- Video Info Card -->
            <div class="flex gap-4 p-3 bg-surface-container-low rounded-md border border-outline-variant/10">
              <!-- 封面图 -->
              <div class="w-40 h-24 rounded-sm bg-surface-variant flex-shrink-0 relative overflow-hidden shadow-sm">
                <img
                  v-if="coverImage"
                  :src="coverImage"
                  :alt="videoInfo.title"
                  class="w-full h-full object-cover"
                />
                <div v-else class="w-full h-full flex items-center justify-center">
                  <span class="material-symbols-outlined text-3xl text-on-surface-variant">movie</span>
                </div>
                <div v-if="videoInfo.duration" class="absolute bottom-1 right-1 bg-inverse-surface/80 backdrop-blur-sm text-inverse-on-surface text-[10px] font-mono px-1 rounded-sm">
                  {{ videoInfo.duration }}
                </div>
              </div>
              <!-- 信息 -->
              <div class="flex-1 flex flex-col gap-1.5 min-w-0">
                <h4 class="text-sm font-medium text-on-surface line-clamp-2">{{ videoInfo.title }}</h4>
                <div class="flex flex-col gap-1 text-xs text-on-surface-variant">
                  <div v-if="videoInfo.code" class="flex items-center gap-1">
                    <span class="material-symbols-outlined text-xs">tag</span>
                    <span>{{ videoInfo.code }}</span>
                  </div>
                  <div v-if="videoInfo.actresses?.length" class="flex items-center gap-1">
                    <span class="material-symbols-outlined text-xs">person</span>
                    <span>{{ videoInfo.actresses.join(', ') }}</span>
                  </div>
                  <div v-if="videoInfo.release_date" class="flex items-center gap-1">
                    <span class="material-symbols-outlined text-xs">calendar_today</span>
                    <span>{{ videoInfo.release_date }}</span>
                  </div>
                  <div v-if="videoInfo.tags?.length" class="flex flex-wrap gap-1 mt-1">
                    <span v-for="tag in videoInfo.tags.slice(0, 5)" :key="tag" class="px-1.5 py-0.5 bg-surface-container-highest rounded-sm text-[10px]">
                      {{ tag }}
                    </span>
                    <span v-if="videoInfo.tags.length > 5" class="text-[10px] text-outline-variant">+{{ videoInfo.tags.length - 5 }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 下载模式选择 -->
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-on-surface-variant">下载模式</label>
              <div class="flex gap-2">
                <button
                  class="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-all border-2"
                  :class="downloadMode === 'local'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-outline-variant/20 bg-surface-container-highest text-on-surface-variant hover:border-outline-variant/40'"
                  @click="downloadMode = 'local'"
                >
                  <span class="material-symbols-outlined text-base">folder</span>
                  <span>下载到本地</span>
                </button>
                <button
                  class="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-all border-2"
                  :class="downloadMode === 'novel'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-outline-variant/20 bg-surface-container-highest text-on-surface-variant hover:border-outline-variant/40'"
                  :disabled="!hasNovelConfig"
                  @click="downloadMode = 'novel'"
                >
                  <span class="material-symbols-outlined text-base">database</span>
                  <span>入库到 Novel</span>
                </button>
              </div>
              <p v-if="downloadMode === 'novel' && hasNovelConfig" class="text-xs text-on-surface-variant">
                视频将下载后自动入库到 <span class="text-primary font-medium">{{ novelSettings.novelProjectPath }}</span> 的数据库
              </p>
              <p v-if="downloadMode === 'novel' && !hasNovelConfig" class="text-xs text-error">
                请先在「设置」页面配置 Novel 项目路径
              </p>
            </div>

            <!-- 下载按钮 -->
            <div class="flex gap-3">
              <button
                v-if="downloadMode === 'local'"
                class="flex items-center gap-2 px-4 py-2 bg-surface-container-highest text-on-surface rounded-md text-sm hover:bg-surface-variant transition-colors border border-outline-variant/10"
                @click="selectOutputDir"
              >
                <span class="material-symbols-outlined text-base">folder</span>
                <span class="truncate max-w-[150px]">{{ outputDir || '选择保存位置' }}</span>
              </button>
              <button
                class="flex-1 flex items-center justify-center gap-2 gradient-btn rounded-md h-10 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="isDownloading || (downloadMode === 'local' && !outputDir) || (downloadMode === 'novel' && !hasNovelConfig)"
                @click="startDownload"
              >
                <span v-if="isDownloading" class="material-symbols-outlined text-base animate-spin">sync</span>
                <span v-else class="material-symbols-outlined text-base">{{ downloadMode === 'novel' ? 'database' : 'download' }}</span>
                <span>{{ isDownloading ? '处理中...' : (downloadMode === 'novel' ? '下载并入库' : '开始下载') }}</span>
              </button>
            </div>
          </div>

          <!-- Quick Guide -->
          <div v-if="!videoInfo" class="mt-2 p-4 bg-surface-container-low rounded-md border border-outline-variant/10">
            <h4 class="text-xs font-semibold text-on-surface-variant mb-3">使用步骤</h4>
            <div class="flex flex-col gap-2.5 text-xs text-on-surface-variant">
              <div class="flex items-start gap-2">
                <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_3</span>
                <span>解析完成后选择「下载到本地」或「入库到 Novel」</span>
              </div>
              <div class="flex items-start gap-2">
                <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_4</span>
                <span>选择保存位置后开始下载</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Right Panel - Download Queue -->
    <section class="w-[35%] flex flex-col bg-surface-container-low border-l border-outline-variant/10">
      <div class="px-5 py-4 border-b border-outline-variant/10">
        <h3 class="font-headline text-sm font-bold text-on-surface">下载队列</h3>
      </div>
      <div class="flex-1 overflow-y-auto px-5 py-4">
        <div v-if="downloadQueue.length === 0" class="flex flex-col items-center justify-center h-full text-on-surface-variant">
          <span class="material-symbols-outlined text-4xl mb-2 opacity-40">queue</span>
          <p class="text-sm">暂无下载任务</p>
        </div>
        <div v-else class="flex flex-col gap-3">
          <div
            v-for="task in downloadQueue"
            :key="task.id"
            class="p-3 bg-surface rounded-md border border-outline-variant/10 flex flex-col gap-2"
          >
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-on-surface truncate flex-1 mr-2">{{ task.filename }}</span>
              <div class="flex items-center gap-1">
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded-sm font-medium"
                  :class="{
                    'bg-primary/10 text-primary': task.status === 'downloading',
                    'bg-success/10 text-success': task.status === 'completed',
                    'bg-error/10 text-error': task.status === 'error',
                    'bg-surface-variant text-on-surface-variant': task.status === 'paused' || task.status === 'pending'
                  }"
                >
                  {{ task.phaseTitle || getStatusText(task.status) }}
                </span>
                <span v-if="task.downloadMode === 'novel'" class="text-[10px] px-1.5 py-0.5 rounded-sm bg-primary/10 text-primary font-medium">
                  入库
                </span>
              </div>
            </div>

            <!-- Phase detail -->
            <div v-if="task.status === 'downloading' && task.detail" class="text-[10px] text-on-surface-variant truncate">
              {{ task.detail }}
            </div>

            <!-- Progress Bar -->
            <div v-if="task.status === 'downloading'" class="flex flex-col gap-1">
              <div class="w-full h-1.5 bg-surface-variant rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :class="task.phase === 'transcoding' ? 'bg-warning' : 'bg-primary'"
                  :style="{ width: task.progress + '%' }"
                ></div>
              </div>
              <div class="flex justify-between text-[10px] text-on-surface-variant">
                <span>{{ task.phase === 'merging' || task.phase === 'transcoding' ? '处理中...' : task.progress.toFixed(1) + '%' }}</span>
                <span>{{ task.speed }}</span>
              </div>
            </div>

            <!-- Error -->
            <div v-if="task.status === 'error' && task.error" class="text-[10px] text-error">
              {{ task.error }}
            </div>

            <!-- Actions -->
            <div class="flex gap-1.5">
              <button
                v-if="task.status === 'completed'"
                class="flex items-center gap-1 px-2 py-1 bg-surface-container-highest text-on-surface-variant rounded-sm text-[10px] hover:bg-surface-variant transition-colors"
                @click="openFile(task.outputPath)"
              >
                <span class="material-symbols-outlined text-xs">folder_open</span>
                打开文件
              </button>
              <button
                v-if="task.status === 'error'"
                class="flex items-center gap-1 px-2 py-1 bg-surface-container-highest text-on-surface-variant rounded-sm text-[10px] hover:bg-surface-variant transition-colors"
                @click="retryTask(task.id)"
              >
                <span class="material-symbols-outlined text-xs">refresh</span>
                重试
              </button>
              <button
                v-if="task.status === 'downloading'"
                class="flex items-center gap-1 px-2 py-1 bg-surface-container-highest text-on-surface-variant rounded-sm text-[10px] hover:bg-surface-variant transition-colors"
                @click="pauseTask(task.id)"
              >
                <span class="material-symbols-outlined text-xs">pause</span>
                暂停
              </button>
              <button
                class="flex items-center gap-1 px-2 py-1 bg-surface-container-highest text-on-surface-variant rounded-sm text-[10px] hover:bg-surface-variant transition-colors ml-auto"
                @click="removeTask(task.id)"
              >
                <span class="material-symbols-outlined text-xs">close</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { VideoInfo, DownloadTask } from '../types'

const urlInput = ref<HTMLTextAreaElement | null>(null)
const url = ref('')
const isParsing = ref(false)
const isDownloading = ref(false)
const errorMsg = ref('')
const importSuccessMsg = ref('')
const videoInfo = ref<VideoInfo | null>(null)
const coverImage = ref<string | null>(null)
const outputDir = ref('')
const downloadQueue = ref<DownloadTask[]>([])
const downloadMode = ref<'local' | 'novel'>('local')

// Novel 入库设置
const novelSettings = ref({ novelProjectPath: 'F:\\novel', novelBackendUrl: 'http://127.0.0.1:8002' })
const hasNovelConfig = computed(() => !!novelSettings.value.novelProjectPath)

onMounted(async () => {
  // 加载 novel 设置
  const saved = localStorage.getItem('app-settings')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      novelSettings.value.novelProjectPath = parsed.novelProjectPath || ''
      novelSettings.value.novelBackendUrl = parsed.novelBackendUrl || ''
    } catch {}
  }

  // 获取默认下载目录
  if (window.electronAPI?.app?.getDefaultDownloadDir) {
    outputDir.value = await window.electronAPI.app.getDefaultDownloadDir()
  }

  // 监听下载进度
  if (window.electronAPI?.onDownloadProgress) {
    window.electronAPI.onDownloadProgress((data) => {
      const task = downloadQueue.value.find(t => t.id === data.taskId)
      if (task) {
        task.progress = data.progress
        task.speed = data.speed
        if (data.status) task.status = data.status as DownloadTask['status']
        if (data.phase !== undefined) task.phase = data.phase
        if (data.phaseTitle !== undefined) task.phaseTitle = data.phaseTitle
        if (data.detail !== undefined) task.detail = data.detail
        if (data.transcodeProgress !== undefined) task.transcodeProgress = data.transcodeProgress
      }
    })
  }

  if (window.electronAPI?.onDownloadCompleted) {
    window.electronAPI.onDownloadCompleted((data) => {
      const task = downloadQueue.value.find(t => t.id === data.taskId)
      if (task) {
        task.status = 'completed'
        task.progress = 100
      }
    })
  }

  if (window.electronAPI?.onDownloadError) {
    window.electronAPI.onDownloadError((data) => {
      const task = downloadQueue.value.find(t => t.id === data.taskId)
      if (task) {
        task.status = 'error'
        task.error = data.error
      }
    })
  }
})

async function pasteUrl() {
  if (window.electronAPI?.clipboard?.readText) {
    url.value = await window.electronAPI.clipboard.readText()
  }
}

async function parseVideo() {
  if (!url.value.trim() || isParsing.value) return

  errorMsg.value = ''
  importSuccessMsg.value = ''
  videoInfo.value = null
  coverImage.value = null
  isParsing.value = true

  try {
    if (window.electronAPI?.video?.parse) {
      videoInfo.value = await window.electronAPI.video.parse(url.value.trim())
    } else {
      // 开发模式模拟
      await new Promise(resolve => setTimeout(resolve, 1500))
      videoInfo.value = {
        title: 'Mock Video Title - Test 123',
        cover: '',
        m3u8_url: null,
        actresses: ['Test Actress'],
        tags: ['tag1', 'tag2', 'tag3'],
        code: 'TEST-001',
        release_date: '2024-01-01',
        duration: '120 min'
      }
    }

    // 加载封面图（使用代理解决跨域问题）
    if (videoInfo.value?.cover) {
      loadCoverImage(videoInfo.value.cover)
    }
  } catch (err: any) {
    errorMsg.value = err.message || '解析失败，请检查链接是否正确'
  } finally {
    isParsing.value = false
  }
}

async function loadCoverImage(imageUrl: string) {
  try {
    if (window.electronAPI?.app?.fetchImage) {
      const dataUrl = await window.electronAPI.app.fetchImage(imageUrl)
      if (dataUrl) {
        coverImage.value = dataUrl
      }
    } else {
      coverImage.value = imageUrl
    }
  } catch (error) {
    console.error('Failed to load cover image:', error)
  }
}

async function selectOutputDir() {
  if (window.electronAPI?.dialog?.selectFolder) {
    const dir = await window.electronAPI.dialog.selectFolder()
    if (dir) {
      outputDir.value = dir
    }
  }
}

async function startDownload() {
  if (!videoInfo.value || isDownloading.value) return

  isDownloading.value = true
  errorMsg.value = ''
  importSuccessMsg.value = ''

  try {
    if (window.electronAPI?.video?.download) {
      // 从 localStorage 读取设置
      let settings = { maxConcurrent: 16, proxy: '', autoMerge: true, keepTempFiles: false }
      const saved = localStorage.getItem('app-settings')
      if (saved) {
        try {
          const parsed = JSON.parse(saved)
          settings.maxConcurrent = parsed.maxConcurrent || 10
          settings.proxy = parsed.proxy || ''
          settings.autoMerge = parsed.autoMerge !== false
          settings.keepTempFiles = parsed.keepTempFiles || false
        } catch {}
      }

      const task = await window.electronAPI.video.download({
        url: url.value.trim(),
        outputDir: downloadMode.value === 'local' ? outputDir.value : '',
        maxConcurrent: settings.maxConcurrent,
        proxy: settings.proxy,
        autoMerge: settings.autoMerge,
        keepTempFiles: settings.keepTempFiles,
        downloadMode: downloadMode.value,
        novelProjectPath: downloadMode.value === 'novel' ? novelSettings.value.novelProjectPath : undefined,
        novelBackendUrl: downloadMode.value === 'novel' ? novelSettings.value.novelBackendUrl : undefined
      } as any)

      if (task) {
        task.downloadMode = downloadMode.value
        downloadQueue.value.unshift(task)
      }
    }
  } catch (err: any) {
    errorMsg.value = err.message || '处理失败'
  } finally {
    isDownloading.value = false
  }
}

async function pauseTask(taskId: string) {
  if (window.electronAPI?.video?.pauseDownload) {
    await window.electronAPI.video.pauseDownload(taskId)
    const task = downloadQueue.value.find(t => t.id === taskId)
    if (task) {
      task.status = 'paused'
    }
  }
}

async function retryTask(taskId: string) {
  const task = downloadQueue.value.find(t => t.id === taskId)
  if (task) {
    task.status = 'pending'
    task.progress = 0
    task.error = undefined
  }
}

function removeTask(taskId: string) {
  downloadQueue.value = downloadQueue.value.filter(t => t.id !== taskId)
}

async function openFile(filePath: string) {
  if (window.electronAPI?.shell?.openPath) {
    await window.electronAPI.shell.openPath(filePath)
  }
}

function getStatusText(status: DownloadTask['status']): string {
  const map: Record<string, string> = {
    pending: '等待中',
    downloading: '下载中',
    merging: '合并中',
    completed: '已完成',
    error: '失败',
    paused: '已暂停',
  }
  return map[status] || status
}
</script>
