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
                </div>
                <!-- 标签 -->
                <div v-if="videoInfo.tags?.length" class="flex flex-wrap gap-1 mt-1">
                  <span
                    v-for="tag in videoInfo.tags.slice(0, 5)"
                    :key="tag"
                    class="px-1.5 py-0.5 bg-primary-container/30 text-primary-dim text-xs rounded"
                  >
                    {{ tag }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 下载按钮 -->
            <div class="flex gap-3">
              <button
                class="flex items-center gap-2 px-4 py-2 bg-surface-container-highest text-on-surface rounded-md text-sm hover:bg-surface-variant transition-colors border border-outline-variant/10"
                @click="selectOutputDir"
              >
                <span class="material-symbols-outlined text-base">folder</span>
                <span class="truncate max-w-[150px]">{{ outputDir || '选择保存位置' }}</span>
              </button>
              <button
                class="flex-1 flex items-center justify-center gap-2 gradient-btn rounded-md h-10 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="isDownloading"
                @click="startDownload"
              >
                <span class="material-symbols-outlined text-base">download</span>
                <span>{{ isDownloading ? '下载中...' : '开始下载' }}</span>
              </button>
            </div>
          </div>

          <!-- 下载队列 -->
          <div v-if="downloadQueue.length > 0" class="mt-2">
            <h3 class="font-headline text-sm font-bold text-on-surface border-b border-outline-variant/20 pb-2 mb-3">下载队列</h3>
            <div class="flex flex-col gap-2">
              <div
                v-for="task in downloadQueue"
                :key="task.id"
                class="bg-surface-container-low rounded-md p-3 border border-outline-variant/10"
              >
                <div class="flex items-center justify-between mb-2">
                  <span class="text-sm text-on-surface truncate flex-1 mr-2">{{ task.filename }}</span>
                  <div class="flex items-center gap-2">
                    <span
                      class="text-xs px-2 py-0.5 rounded"
                      :class="{
                        'bg-primary-container/30 text-primary-dim': task.status === 'downloading',
                        'bg-secondary-container/30 text-secondary': task.status === 'merging',
                        'bg-tertiary-container/30 text-tertiary': task.status === 'completed',
                        'bg-error-container/30 text-error': task.status === 'error',
                        'bg-surface-variant text-on-surface-variant': task.status === 'paused',
                      }"
                    >
                      {{ getStatusText(task.status) }}
                    </span>
                    <!-- 操作按钮 -->
                    <button
                      v-if="task.status === 'downloading'"
                      class="size-6 flex items-center justify-center rounded hover:bg-surface-variant"
                      @click="pauseTask(task.id)"
                      title="暂停"
                    >
                      <span class="material-symbols-outlined text-sm">pause</span>
                    </button>
                    <button
                      v-if="task.status === 'completed'"
                      class="size-6 flex items-center justify-center rounded hover:bg-surface-variant"
                      @click="openFile(task.outputPath)"
                      title="打开文件"
                    >
                      <span class="material-symbols-outlined text-sm">open_in_new</span>
                    </button>
                    <button
                      v-if="task.status === 'error'"
                      class="size-6 flex items-center justify-center rounded hover:bg-surface-variant"
                      @click="retryTask(task.id)"
                      title="重试"
                    >
                      <span class="material-symbols-outlined text-sm">refresh</span>
                    </button>
                    <button
                      class="size-6 flex items-center justify-center rounded hover:bg-error-container text-on-surface-variant hover:text-error"
                      @click="removeTask(task.id)"
                      title="移除"
                    >
                      <span class="material-symbols-outlined text-sm">close</span>
                    </button>
                  </div>
                </div>
                <!-- 进度条 -->
                <div v-if="task.status === 'downloading' || task.status === 'merging'" class="flex items-center gap-3">
                  <div class="flex-1 h-1.5 bg-surface-variant rounded-full overflow-hidden">
                    <div
                      class="h-full bg-primary rounded-full transition-all"
                      :style="{ width: `${task.progress}%` }"
                    ></div>
                  </div>
                  <span class="text-xs text-on-surface-variant whitespace-nowrap">{{ task.progress }}%</span>
                  <span class="text-xs text-on-surface-variant whitespace-nowrap">{{ task.speed }}</span>
                </div>
                <!-- 错误信息 -->
                <div v-if="task.status === 'error' && task.error" class="mt-1">
                  <span class="text-xs text-error">{{ task.error }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Right Panel - Tips -->
    <section class="w-[35%] flex flex-col bg-surface-container-low border-l border-outline-variant/10">
      <div class="flex-1 overflow-y-auto px-6 py-6">
        <div class="flex flex-col gap-4">
          <h3 class="font-headline text-sm font-bold text-on-surface">使用说明</h3>
          <div class="flex flex-col gap-3 text-xs text-on-surface-variant leading-relaxed">
            <div class="flex items-start gap-2">
              <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_one</span>
              <span>复制 missav.ws 视频页面链接</span>
            </div>
            <div class="flex items-start gap-2">
              <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_two</span>
              <span>粘贴到左侧输入框</span>
            </div>
            <div class="flex items-start gap-2">
              <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_3</span>
              <span>点击"解析视频"按钮</span>
            </div>
            <div class="flex items-start gap-2">
              <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_4</span>
              <span>选择保存位置后开始下载</span>
            </div>
          </div>

          <div class="h-px bg-outline-variant/20 my-2"></div>

          <h3 class="font-headline text-sm font-bold text-on-surface">支持格式</h3>
          <div class="flex flex-wrap gap-2">
            <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">m3u8</span>
            <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">mp4</span>
            <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">ts</span>
          </div>

          <div class="h-px bg-outline-variant/20 my-2"></div>

          <div class="bg-tertiary-container/30 rounded-md p-3">
            <div class="flex items-start gap-2">
              <span class="material-symbols-outlined text-tertiary text-sm mt-0.5">info</span>
              <div class="text-xs text-on-surface-variant leading-relaxed">
                <p>本工具仅供个人学习使用，请勿用于商业用途。下载的内容版权归原作者所有。</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { VideoInfo, DownloadTask } from '../types'

const urlInput = ref<HTMLTextAreaElement>()
const url = ref('')
const isParsing = ref(false)
const isDownloading = ref(false)
const errorMsg = ref('')
const videoInfo = ref<VideoInfo | null>(null)
const coverImage = ref<string | null>(null)
const outputDir = ref('')
const downloadQueue = ref<DownloadTask[]>([])

let unsubscribeProgress: (() => void) | null = null
let unsubscribeCompleted: (() => void) | null = null
let unsubscribeError: (() => void) | null = null

onMounted(async () => {
  // 获取默认下载目录
  if (window.electronAPI?.app?.getDefaultDownloadDir) {
    outputDir.value = await window.electronAPI.app.getDefaultDownloadDir()
  }

  // 监听下载进度
  if (window.electronAPI?.onDownloadProgress) {
    unsubscribeProgress = window.electronAPI.onDownloadProgress((data) => {
      const task = downloadQueue.value.find(t => t.id === data.taskId)
      if (task) {
        task.progress = data.progress
        task.speed = data.speed
        if (data.status === 'completed') {
          task.status = 'completed'
        }
      }
    })
  }

  // 监听下载完成
  if (window.electronAPI?.onDownloadCompleted) {
    unsubscribeCompleted = window.electronAPI.onDownloadCompleted((data) => {
      const task = downloadQueue.value.find(t => t.id === data.taskId)
      if (task) {
        task.status = 'completed'
        task.progress = 100
      }
      // 触发历史记录刷新
      window.dispatchEvent(new CustomEvent('history-updated'))
    })
  }

  // 监听下载错误
  if (window.electronAPI?.onDownloadError) {
    unsubscribeError = window.electronAPI.onDownloadError((data) => {
      const task = downloadQueue.value.find(t => t.id === data.taskId)
      if (task) {
        task.status = 'error'
        task.error = data.error
      }
    })
  }
})

onUnmounted(() => {
  if (unsubscribeProgress) unsubscribeProgress()
  if (unsubscribeCompleted) unsubscribeCompleted()
  if (unsubscribeError) unsubscribeError()
})

async function pasteUrl() {
  if (window.electronAPI?.clipboard?.readText) {
    url.value = await window.electronAPI.clipboard.readText()
  }
}

async function parseVideo() {
  if (!url.value.trim() || isParsing.value) return

  errorMsg.value = ''
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
      // 开发模式直接使用 URL
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

  try {
    if (window.electronAPI?.video?.download) {
      const task = await window.electronAPI.video.download({
        url: url.value.trim(),
        outputDir: outputDir.value
      })
      downloadQueue.value.unshift(task)
    }
  } catch (err: any) {
    errorMsg.value = err.message || '下载失败'
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

function handleImageError(event: Event) {
  const img = event.target as HTMLImageElement
  // 隐藏加载失败的图片
  img.style.display = 'none'
  // 显示父元素中的占位图标
  const parent = img.parentElement
  if (parent) {
    const placeholder = parent.querySelector('.material-symbols-outlined')
    if (placeholder) {
      (placeholder as HTMLElement).style.display = 'block'
    }
  }
}
</script>
