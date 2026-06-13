<template>
  <div class="flex-1 flex overflow-hidden">
    <section class="w-[62%] flex flex-col bg-surface relative">
      <div class="flex-1 overflow-y-auto px-8 py-6">
        <div class="max-w-xl mx-auto w-full flex flex-col gap-6">
          <div class="flex flex-col gap-1">
            <h1 class="font-headline text-2xl font-bold leading-tight text-on-surface">图集图片下载</h1>
            <p class="text-on-surface-variant text-sm">粘贴图片站点图集链接，支持 4khd / szzs / kkc3 / buondua / photos18 / tokyobombers / foamgirl / hotgirl / phimvuspot</p>
          </div>

          <div class="flex flex-col gap-3">
            <div class="relative focus-glow rounded-md">
              <textarea
                ref="urlInput"
                v-model="galleryUrl"
                aria-label="粘贴图集链接"
                class="w-full h-24 bg-surface-container-highest rounded-md p-3 text-on-surface placeholder:text-outline-variant resize-none font-body text-sm border-2 border-transparent focus:border-primary focus:outline-none transition-all"
                placeholder="在此粘贴图集链接，支持 4khd / szzs / kkc3.com / photos18.com / tokyobombers.com / foamgirl.net / hotgirl.asia / phimvuspot.com 等站点"
                @keydown.enter.prevent="parseGallery"
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
                :disabled="isParsing || !galleryUrl.trim()"
                @click="parseGallery"
              >
                <span v-if="isParsing" class="material-symbols-outlined text-base animate-spin">sync</span>
                <span v-else class="material-symbols-outlined text-base">image_search</span>
                <span>{{ isParsing ? '解析中...' : '解析图集' }}</span>
              </button>
            </div>
          </div>

          <div v-if="errorMsg" class="flex items-center gap-2 p-3 bg-error-container/30 border border-error/20 rounded-md">
            <span class="material-symbols-outlined text-error text-base">error</span>
            <span class="text-sm text-error">{{ errorMsg }}</span>
          </div>

          <div v-if="successMsg" class="flex items-center gap-2 p-3 bg-primary/10 border border-primary/20 rounded-md">
            <span class="material-symbols-outlined text-primary text-base">check_circle</span>
            <span class="text-sm text-primary">{{ successMsg }}</span>
          </div>

          <!-- 解析结果 -->
          <section v-if="parseResult" class="flex flex-col gap-3 p-4 bg-surface-container-low rounded-md border border-outline-variant/10">
            <h3 class="font-headline text-sm font-bold text-on-surface">解析结果</h3>
            <div class="flex gap-4">
              <!-- 首张预览图 -->
              <div class="w-32 h-24 shrink-0 rounded-md overflow-hidden bg-surface-container-highest border border-outline-variant/10">
                <img
                  v-if="previewImage"
                  :src="previewImage"
                  class="w-full h-full object-cover"
                  alt="预览"
                />
                <div v-else class="w-full h-full flex items-center justify-center">
                  <span class="material-symbols-outlined text-on-surface-variant text-2xl opacity-40">image</span>
                </div>
                <div
                  v-if="parseResult.has_video"
                  class="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-inverse-surface/85 px-2 py-1 text-[10px] font-semibold text-inverse-on-surface shadow-sm"
                >
                  <span class="material-symbols-outlined text-[12px]">play_circle</span>
                  <span>视频</span>
                </div>
              </div>
              <div class="flex flex-col gap-1.5 text-sm flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-on-surface-variant shrink-0">标题：</span>
                  <span class="text-on-surface font-medium truncate">{{ parseResult.title }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-on-surface-variant shrink-0">图片数量：</span>
                  <span class="text-primary font-semibold">{{ parseResult.image_count }} 张</span>
                </div>
                <div v-if="parseResult.has_video" class="flex items-center gap-2">
                  <span class="text-on-surface-variant shrink-0">附带视频：</span>
                  <span class="text-primary font-semibold">{{ parseResult.video_count || 1 }} 个</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-on-surface-variant shrink-0">媒体类型：</span>
                  <span class="text-on-surface font-medium">
                    {{ parseResult.has_video ? `${parseResult.image_count} 张图片 · ${parseResult.video_count || 1} 个附带视频` : `${parseResult.image_count} 张图片` }}
                  </span>
                </div>
              </div>
            </div>

            <h3 class="font-headline text-sm font-bold text-on-surface mt-2">保存方式</h3>
            <div class="grid grid-cols-2 gap-3">
              <button
                class="flex items-center gap-2 p-3 rounded-md border transition-all text-left"
                :class="downloadMode === 'local' ? 'bg-primary/10 border-primary text-primary' : 'bg-surface-container-highest border-outline-variant/10 text-on-surface hover:bg-surface-variant'"
                @click="downloadMode = 'local'"
              >
                <span class="material-symbols-outlined text-base">folder</span>
                <span class="text-sm font-semibold">下载到本地</span>
              </button>
              <button
                class="flex items-center gap-2 p-3 rounded-md border transition-all text-left"
                :class="downloadMode === 'novel' ? 'bg-primary/10 border-primary text-primary' : 'bg-surface-container-highest border-outline-variant/10 text-on-surface hover:bg-surface-variant'"
                @click="downloadMode = 'novel'"
              >
                <span class="material-symbols-outlined text-base">database</span>
                <span class="text-sm font-semibold">入库到 Novel</span>
              </button>
            </div>

            <div v-if="downloadMode === 'local'" class="flex gap-2">
              <input
                v-model="outputDir"
                type="text"
                readonly
                class="flex-1 h-9 bg-surface-container-highest rounded-md px-3 text-sm text-on-surface border border-outline-variant/10 focus:outline-none"
              />
              <button
                class="flex items-center gap-1 px-3 h-9 bg-surface-container-highest text-on-surface rounded-md text-xs font-headline font-semibold hover:bg-surface-variant transition-colors border border-outline-variant/10"
                @click="selectOutputDir"
              >
                <span class="material-symbols-outlined text-sm">folder</span>
                浏览
              </button>
            </div>
            <p v-if="downloadMode === 'novel' && hasNovelConfig" class="text-xs text-on-surface-variant">
              图片将直接导入 <span class="text-primary font-medium">{{ novelProjectPath }}\img\gallery_images\</span>
            </p>
            <p v-if="downloadMode === 'novel' && !hasNovelConfig" class="text-xs text-error">
              请先在「设置」页面配置 Novel 项目路径。
            </p>

            <button
              class="flex items-center justify-center gap-2 rounded-md h-10 font-headline font-semibold text-sm transition-all border-2 gradient-btn disabled:opacity-50 disabled:cursor-not-allowed mt-2"
              :disabled="isDownloading || !canStart"
              @click="startDownload"
            >
              <span v-if="isDownloading" class="material-symbols-outlined text-base animate-spin">sync</span>
              <span v-else class="material-symbols-outlined text-base">photo_library</span>
              <span>{{ isDownloading ? '下载中...' : actionText }}</span>
            </button>
          </section>

          <section v-if="!parseResult" class="p-4 bg-surface-container-low rounded-md border border-outline-variant/10">
            <h4 class="text-xs font-semibold text-on-surface-variant mb-3">使用说明</h4>
            <div class="flex flex-col gap-2.5 text-xs text-on-surface-variant">
              <div class="flex items-start gap-2">
                <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_one</span>
                <span>粘贴 4khd / szzs / kkc3 / photos18 / tokyobombers / foamgirl / hotgirl / phimvuspot 等图站链接，点击「解析图集」获取图集信息</span>
              </div>
              <div class="flex items-start gap-2">
                <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_two</span>
                <span>选择保存方式：本地目录或直接入库到 Novel 图集库</span>
              </div>
              <div class="flex items-start gap-2">
                <span class="material-symbols-outlined text-primary text-sm mt-0.5">looks_3</span>
                <span>点击下载，自动提取分页并逐张下载图片</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </section>

    <section class="w-[38%] flex flex-col bg-surface-container-low border-l border-outline-variant/10">
      <div class="px-5 py-4 border-b border-outline-variant/10">
        <h3 class="font-headline text-sm font-bold text-on-surface">图集任务</h3>
      </div>
      <div class="flex-1 overflow-y-auto px-5 py-4">
        <div v-if="downloadQueue.length === 0" class="flex flex-col items-center justify-center h-full text-on-surface-variant">
          <span class="material-symbols-outlined text-4xl mb-2 opacity-40">photo_library</span>
          <p class="text-sm">暂无图集任务</p>
        </div>
        <div v-else class="flex flex-col gap-3">
          <div
            v-for="task in downloadQueue"
            :key="task.id"
            class="p-3 bg-surface rounded-md border border-outline-variant/10 flex flex-col gap-2"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-medium text-on-surface truncate flex-1">{{ task.filename }}</span>
              <span
                class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-sm font-medium"
                :class="getTaskStageBadgeClass(task)"
              >
                <span class="material-symbols-outlined text-[11px]">{{ getTaskStageIcon(task) }}</span>
                <span>{{ getTaskStageLabel(task) }}</span>
              </span>
            </div>

            <div class="flex items-center gap-2 text-[10px] text-on-surface-variant">
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm bg-surface-container-highest border border-outline-variant/10">
                <span class="material-symbols-outlined text-[11px]">
                  {{ task.mediaType === 'gallery_with_video' ? 'play_circle' : 'photo_library' }}
                </span>
                <span>{{ task.mediaType === 'gallery_with_video' ? '图集 + 视频' : '图集' }}</span>
              </span>
              <span class="px-1.5 py-0.5 rounded-sm bg-surface-container-highest border border-outline-variant/10">
                来源：{{ getSourceText(task.source) }}
              </span>
              <span class="px-1.5 py-0.5 rounded-sm bg-surface-container-highest border border-outline-variant/10">
                {{ task.downloadMode === 'novel' ? '入库到 Novel' : '下载到本地' }}
              </span>
            </div>

            <div v-if="task.detail" class="text-[10px] text-on-surface-variant truncate">
              阶段详情：{{ task.detail }}
            </div>

            <div v-if="task.status !== 'pending'" class="flex flex-col gap-1">
              <div class="w-full h-1.5 bg-surface-variant rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :class="task.status === 'completed' ? 'bg-success' : task.status === 'error' ? 'bg-error' : 'bg-primary'"
                  :style="{ width: task.progress + '%' }"
                ></div>
              </div>
              <div class="flex justify-between text-[10px] text-on-surface-variant">
                <span>{{ task.progress.toFixed(1) }}%</span>
                <span>{{ task.speed }}</span>
              </div>

              <div class="grid grid-cols-2 gap-2 text-[10px] text-on-surface-variant mt-0.5">
                <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1">
                  <div class="inline-flex items-center gap-1 text-on-surface">
                    <span class="material-symbols-outlined text-[11px]">timeline</span>
                    <span class="font-semibold">{{ task.status === 'error' ? '失败阶段' : '当前阶段' }}</span>
                  </div>
                  <span class="inline-flex items-center gap-1" :class="getTaskStageTextClass(task)">
                    <span class="material-symbols-outlined text-[11px]">{{ getTaskStageIcon(task) }}</span>
                    <span>{{ getTaskStageLabel(task) }}</span>
                  </span>
                  <span>{{ getTaskStageSummary(task) }}</span>
                  <span v-if="task.hasVideo">媒体流程：{{ getMediaStageText(task) }}</span>
                </div>

                <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1">
                  <div class="inline-flex items-center gap-1 text-on-surface">
                    <span class="material-symbols-outlined text-[11px]">monitoring</span>
                    <span class="font-semibold">进度摘要</span>
                  </div>
                  <span>总进度：{{ task.progress.toFixed(1) }}%</span>
                  <span>{{ getProgressSummaryText(task) }}</span>
                  <span>速度：{{ task.speed || '0 MB/s' }}</span>
                  <span>媒体总量：{{ getMediaSummaryText(task) }}</span>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-2 text-[10px] text-on-surface-variant mt-0.5">
                <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1">
                  <div class="inline-flex items-center gap-1 text-on-surface">
                    <span class="material-symbols-outlined text-[11px]">photo_library</span>
                    <span class="font-semibold">图片统计</span>
                  </div>
                  <span>总数：{{ task.totalImages || 0 }} 张</span>
                  <span>{{ getImageProgressText(task) }}</span>
                  <span>成功：{{ task.successCount ?? 0 }} 张</span>
                  <span :class="task.failedCount && task.failedCount > 0 ? 'text-error' : ''">失败：{{ task.failedCount ?? 0 }} 张</span>
                </div>

                <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1">
                  <div class="inline-flex items-center gap-1 text-on-surface">
                    <span class="material-symbols-outlined text-[11px]">{{ task.hasVideo ? 'play_circle' : 'info' }}</span>
                    <span class="font-semibold">视频统计</span>
                  </div>
                  <span>{{ task.hasVideo ? `数量：${task.videoCount || 1} 个` : '数量：0 个' }}</span>
                  <span>{{ getVideoProgressText(task) }}</span>
                  <span v-if="task.novelVideoId">Video ID：{{ task.novelVideoId }}</span>
                  <span v-else>状态：{{ getVideoStatusText(task) }}</span>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-2 text-[10px] text-on-surface-variant mt-0.5">
                <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1">
                  <div class="inline-flex items-center gap-1 text-on-surface">
                    <span class="material-symbols-outlined text-[11px]">database</span>
                    <span class="font-semibold">入库统计</span>
                  </div>
                  <span>模式：{{ task.downloadMode === 'novel' ? 'Novel 图集库' : '本地目录' }}</span>
                  <span v-if="task.galleryId">Gallery ID：{{ task.galleryId }}</span>
                  <span v-else>Gallery ID：未生成</span>
                  <span v-if="task.novelVideoId">Video ID：{{ task.novelVideoId }}</span>
                  <span>媒体结构：{{ task.hasVideo ? '同一 Gallery 下包含图片和视频' : '单一图片 Gallery' }}</span>
                </div>

                <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1 min-w-0">
                  <div class="inline-flex items-center gap-1 text-on-surface">
                    <span class="material-symbols-outlined text-[11px]">folder_open</span>
                    <span class="font-semibold">{{ task.status === 'completed' ? '结果位置' : '输出位置' }}</span>
                  </div>
                  <span class="break-all">{{ task.outputPath || '处理中...' }}</span>
                </div>
              </div>
            </div>

            <div v-if="task.status === 'completed'" class="grid grid-cols-2 gap-2 text-[10px] text-on-surface-variant mt-0.5">
              <div class="rounded-md bg-success/5 border border-success/20 p-2 flex flex-col gap-1">
                <div class="inline-flex items-center gap-1 text-success">
                  <span class="material-symbols-outlined text-[11px]">check_circle</span>
                  <span class="font-semibold">结果信息</span>
                </div>
                <span>完成状态：{{ getCompletedSummaryText(task) }}</span>
                <span>Gallery ID：{{ task.galleryId ?? '未生成' }}</span>
                <span v-if="task.hasVideo">Video ID：{{ task.novelVideoId ?? '未生成' }}</span>
                <span>最终媒体：{{ getMediaSummaryText(task) }}</span>
              </div>

              <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1 min-w-0">
                <div class="inline-flex items-center gap-1 text-on-surface">
                  <span class="material-symbols-outlined text-[11px]">info</span>
                  <span class="font-semibold">完成明细</span>
                </div>
                <span>来源：{{ getSourceText(task.source) }}</span>
                <span>保存方式：{{ task.downloadMode === 'novel' ? '入库到 Novel' : '下载到本地' }}</span>
                <span>{{ task.hasVideo ? '媒体结构：同一 Gallery 下包含图片和视频' : '媒体结构：单一图片 Gallery' }}</span>
                <span v-if="task.detail" class="break-all">最后阶段：{{ task.detail }}</span>
              </div>
            </div>

            <div v-if="task.status === 'error'" class="grid grid-cols-2 gap-2 text-[10px] text-on-surface-variant mt-0.5">
              <div class="rounded-md bg-error/5 border border-error/20 p-2 flex flex-col gap-1">
                <div class="inline-flex items-center gap-1 text-error">
                  <span class="material-symbols-outlined text-[11px]">error</span>
                  <span class="font-semibold">失败信息</span>
                </div>
                <span>失败阶段：{{ getFailureStageText(task) }}</span>
                <span class="break-all">失败原因：{{ task.error || '未知错误' }}</span>
                <span v-if="task.detail" class="break-all">最后详情：{{ task.detail }}</span>
                <span>任务结构：{{ getMediaSummaryText(task) }}</span>
              </div>

              <div class="rounded-md bg-surface-container-highest border border-outline-variant/10 p-2 flex flex-col gap-1 min-w-0">
                <div class="inline-flex items-center gap-1 text-on-surface">
                  <span class="material-symbols-outlined text-[11px]">info</span>
                  <span class="font-semibold">失败上下文</span>
                </div>
                <span>来源：{{ getSourceText(task.source) }}</span>
                <span>保存方式：{{ task.downloadMode === 'novel' ? '入库到 Novel' : '下载到本地' }}</span>
                <span>Gallery ID：{{ task.galleryId ?? '未生成' }}</span>
                <span v-if="task.hasVideo">Video ID：{{ task.novelVideoId ?? '未生成' }}</span>
                <span class="break-all">输出位置：{{ task.outputPath || '尚未生成' }}</span>
              </div>
            </div>

            <div class="flex gap-1.5">
              <button
                v-if="task.status === 'completed'"
                class="flex items-center gap-1 px-2 py-1 bg-surface-container-highest text-on-surface-variant rounded-sm text-[10px] hover:bg-surface-variant transition-colors"
                @click="openFolder(task.outputPath)"
              >
                <span class="material-symbols-outlined text-xs">folder_open</span>
                打开目录
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
import { computed, onMounted, ref } from 'vue'
import type { DownloadTask, GalleryParseResult } from '../types'

const galleryUrl = ref('')
const outputDir = ref('')
const downloadMode = ref<'local' | 'novel'>('local')
const isParsing = ref(false)
const isDownloading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')
const parseResult = ref<GalleryParseResult | null>(null)
const previewImage = ref('')
const downloadQueue = ref<DownloadTask[]>([])
const novelProjectPath = ref('F:\\novel')
const proxy = ref('')

const hasNovelConfig = computed(() => !!novelProjectPath.value)
const canStart = computed(() => downloadMode.value === 'novel' ? hasNovelConfig.value : !!outputDir.value)
const actionText = computed(() => downloadMode.value === 'novel' ? '下载并入库' : '开始下载')

onMounted(async () => {
  loadSettings()
  if (!outputDir.value && window.electronAPI?.app?.getDefaultDownloadDir) {
    outputDir.value = await window.electronAPI.app.getDefaultDownloadDir()
  }

  window.electronAPI?.onDownloadProgress?.((data) => {
    const task = downloadQueue.value.find(item => item.id === data.taskId)
    if (!task) return
    task.progress = data.progress
    task.speed = data.speed
    if (data.status) task.status = data.status as DownloadTask['status']
    if (data.phase !== undefined) task.phase = data.phase
    if (data.phaseTitle !== undefined) task.phaseTitle = data.phaseTitle
    if (data.detail !== undefined) task.detail = data.detail
    if (data.outputPath !== undefined) task.outputPath = data.outputPath
    if (data.totalImages !== undefined) task.totalImages = data.totalImages
    if (data.currentIndex !== undefined) task.currentIndex = data.currentIndex
    if (data.successCount !== undefined) task.successCount = data.successCount
    if (data.failedCount !== undefined) task.failedCount = data.failedCount
    if (data.hasVideo !== undefined) task.hasVideo = data.hasVideo
    if (data.videoCount !== undefined) task.videoCount = data.videoCount
    if (data.mediaType !== undefined) task.mediaType = data.mediaType
    if (data.source !== undefined) task.source = data.source
    if (data.galleryId !== undefined) task.galleryId = data.galleryId
    if (data.novelVideoId !== undefined) task.novelVideoId = data.novelVideoId
  })

  window.electronAPI?.onDownloadCompleted?.((data) => {
    const task = downloadQueue.value.find(item => item.id === data.taskId)
    if (!task) return
    task.filename = data.filename || task.filename
    if (data.outputPath) task.outputPath = data.outputPath
    task.status = 'completed'
    task.progress = 100
    successMsg.value = `图集任务完成：${task.filename}`
  })

  window.electronAPI?.onDownloadError?.((data) => {
    const task = downloadQueue.value.find(item => item.id === data.taskId)
    if (!task) return
    task.status = 'error'
    task.error = data.error
  })
})

function loadSettings() {
  const saved = localStorage.getItem('app-settings')
  if (!saved) return
  try {
    const parsed = JSON.parse(saved)
    outputDir.value = parsed.downloadDir || ''
    novelProjectPath.value = parsed.novelProjectPath || ''
    proxy.value = parsed.proxy || ''
  } catch {}
}

async function pasteUrl() {
  if (window.electronAPI?.clipboard?.readText) {
    galleryUrl.value = await window.electronAPI.clipboard.readText()
  }
}

async function selectOutputDir() {
  const dir = await window.electronAPI?.dialog?.selectFolder?.()
  if (dir) outputDir.value = dir
}

async function parseGallery() {
  if (isParsing.value || !galleryUrl.value.trim()) return
  isParsing.value = true
  errorMsg.value = ''
  successMsg.value = ''
  parseResult.value = null
  previewImage.value = ''

  try {
    const result = await window.electronAPI.gallery.parse({
      galleryUrl: galleryUrl.value.trim(),
      proxy: proxy.value
    })
    parseResult.value = result
    // 优先使用后端返回的预览图（Playwright 站点已捕获），否则通过 fetchImage 拉取
    previewImage.value = ''
    if (result.preview_base64) {
      previewImage.value = `data:image/jpeg;base64,${result.preview_base64}`
    } else if (result.image_urls?.length > 0 && window.electronAPI?.app?.fetchImage) {
      const img = await window.electronAPI.app.fetchImage(result.image_urls[0])
      if (img) previewImage.value = img
    }
  } catch (err: any) {
    errorMsg.value = err.message || '图集解析失败'
    parseResult.value = null
  } finally {
    isParsing.value = false
  }
}

async function startDownload() {
  if (isDownloading.value || !galleryUrl.value.trim() || !canStart.value || !parseResult.value) return

  isDownloading.value = true
  errorMsg.value = ''

  try {
    const task = await window.electronAPI.gallery.download({
      galleryUrl: galleryUrl.value.trim(),
      outputDir: downloadMode.value === 'local' ? outputDir.value : '',
      downloadMode: downloadMode.value,
      novelProjectPath: downloadMode.value === 'novel' ? novelProjectPath.value : undefined,
      proxy: proxy.value
    })
    task.downloadMode = downloadMode.value
    downloadQueue.value.unshift(task)
  } catch (err: any) {
    errorMsg.value = err.message || '图集下载失败'
  } finally {
    isDownloading.value = false
  }
}

function removeTask(taskId: string) {
  downloadQueue.value = downloadQueue.value.filter(task => task.id !== taskId)
}

async function openFolder(folderPath: string) {
  if (folderPath && window.electronAPI?.shell?.openFolder) {
    await window.electronAPI.shell.openFolder(folderPath)
  }
}

function getStatusText(status: DownloadTask['status']) {
  return {
    pending: '等待中',
    downloading: '下载中',
    merging: '合并中',
    completed: '已完成',
    error: '失败',
    paused: '已暂停'
  }[status]
}

function isVideoPhase(task: DownloadTask) {
  if (!task.hasVideo) return false
  const stage = getOperationalStageKey(task)
  return ['switching_to_video', 'video_downloading', 'video_segment_downloading', 'video_merging', 'video_importing', 'video_transcoding'].includes(stage)
}

function getMediaStageText(task: DownloadTask) {
  if (!task.hasVideo) return '纯图集任务'
  const stage = getTaskStageKey(task)
  if (stage === 'completed') return '图片与附带视频均已完成'
  if (stage === 'failed') return `处理失败：${getFailureStageText(task)}`
  if (stage === 'switching_to_video') return '图片已完成，正在切换到附带视频阶段'
  if (['video_downloading', 'video_segment_downloading', 'video_merging', 'video_importing', 'video_transcoding'].includes(stage)) {
    return `当前正在处理${getTaskStageLabel(task)}`
  }
  return '当前正在处理图集图片'
}

function getSourceText(source?: string) {
  if (source === 'gallery') return '图集站点'
  if (source === 'missav') return 'MissAV'
  if (source === 'kissjav') return 'KissJAV'
  return '未知来源'
}

function getMediaSummaryText(task: DownloadTask) {
  const imageCount = task.totalImages ?? task.successCount ?? 0
  if (!task.hasVideo) return `${imageCount} 张图片`
  return `${imageCount} 张图片 + ${task.videoCount || 1} 个视频`
}

function getCompletedSummaryText(task: DownloadTask) {
  if (task.hasVideo) return '图集与附带视频已全部完成'
  return '图集已完成'
}

function getFailureStageText(task: DownloadTask) {
  return getStageLabelByKey(getOperationalStageKey(task))
}

type TaskStageKey =
  | 'pending'
  | 'parsing'
  | 'image_downloading'
  | 'image_importing'
  | 'switching_to_video'
  | 'video_downloading'
  | 'video_segment_downloading'
  | 'video_merging'
  | 'video_importing'
  | 'video_transcoding'
  | 'cleaning'
  | 'completed'
  | 'failed'

function getTaskStageKey(task: DownloadTask): TaskStageKey {
  if (task.status === 'completed') return 'completed'
  if (task.status === 'error') return 'failed'
  return getOperationalStageKey(task)
}

function getOperationalStageKey(task: DownloadTask): TaskStageKey {
  if (task.detail?.includes('挂到同一个 Gallery')) return 'video_importing'
  if (task.detail?.includes('下载附带视频')) return 'video_downloading'
  if (task.detail?.includes('图片已入库')) return 'switching_to_video'
  if (task.detail?.includes('解析')) return 'parsing'

  if (task.phase === 'parsing') return 'parsing'
  if (task.phase === 'download_segments') return 'video_segment_downloading'
  if (task.phase === 'merging') return 'video_merging'
  if (task.phase === 'transcoding') return 'video_transcoding'
  if (task.phase === 'cleaning') return 'cleaning'
  if (task.phase === 'importing') return isVideoPhaseByDetail(task) ? 'video_importing' : 'image_importing'
  if (task.phase === 'downloading') return isVideoPhaseByDetail(task) ? 'video_downloading' : 'image_downloading'

  return 'pending'
}

function isVideoPhaseByDetail(task: DownloadTask) {
  return task.detail?.includes('附带视频') || false
}

function getTaskStageLabel(task: DownloadTask) {
  return getStageLabelByKey(getTaskStageKey(task))
}

function getStageLabelByKey(stage: TaskStageKey) {
  return {
    pending: getStatusText('pending'),
    parsing: '图集解析',
    image_downloading: '图片下载',
    image_importing: '图片入库',
    switching_to_video: '切换视频阶段',
    video_downloading: '视频下载',
    video_segment_downloading: '视频分片下载',
    video_merging: '视频合并',
    video_importing: '视频入库',
    video_transcoding: '视频转码',
    cleaning: '清理阶段',
    completed: '已完成',
    failed: '失败'
  }[stage]
}

function getTaskStageIcon(task: DownloadTask) {
  const stage = getTaskStageKey(task)
  return {
    pending: 'schedule',
    parsing: 'image_search',
    image_downloading: 'download',
    image_importing: 'photo_library',
    switching_to_video: 'switch_right',
    video_downloading: 'play_circle',
    video_segment_downloading: 'movie',
    video_merging: 'merge',
    video_importing: 'video_library',
    video_transcoding: 'sync',
    cleaning: 'mop',
    completed: 'check_circle',
    failed: 'error'
  }[stage]
}

function getTaskStageBadgeClass(task: DownloadTask) {
  const stage = getTaskStageKey(task)
  if (stage === 'completed') return 'bg-success/10 text-success'
  if (stage === 'failed') return 'bg-error/10 text-error'
  if (stage === 'pending') return 'bg-surface-container-highest text-on-surface-variant'
  return 'bg-primary/10 text-primary'
}

function getTaskStageTextClass(task: DownloadTask) {
  const stage = getTaskStageKey(task)
  if (stage === 'completed') return 'text-success'
  if (stage === 'failed') return 'text-error'
  return 'text-primary'
}

function getTaskStageSummary(task: DownloadTask) {
  const stage = getTaskStageKey(task)
  if (stage === 'completed') return getCompletedSummaryText(task)
  if (stage === 'failed') return `处理终止于：${getFailureStageText(task)}`
  if (stage === 'switching_to_video') return '图片阶段已经结束，准备开始处理附带视频'
  if (stage === 'image_importing') return '当前正在把图片结果写入目标位置'
  if (stage === 'video_importing') return '当前正在把视频挂到同一个 Gallery'
  if (stage === 'cleaning') return '当前正在收尾并清理临时文件'
  return `当前阶段：${getTaskStageLabel(task)}`
}

function getProgressSummaryText(task: DownloadTask) {
  if (task.status === 'completed') return '任务已全部完成'
  if (task.status === 'error') return `任务已中断：${getFailureStageText(task)}`
  if (isVideoPhase(task)) return `图片 ${task.successCount ?? task.totalImages ?? 0}/${task.totalImages ?? 0} 张，视频处理中`
  if (task.currentIndex && task.totalImages) return `图片进行到第 ${task.currentIndex}/${task.totalImages} 张`
  if (task.totalImages) return `图片目标总数：${task.totalImages} 张`
  return '等待更多进度信息'
}

function getImageProgressText(task: DownloadTask) {
  if (task.currentIndex && !isVideoPhase(task) && task.totalImages) return `当前：第 ${task.currentIndex}/${task.totalImages} 张`
  if (task.totalImages && (task.status === 'completed' || isVideoPhase(task))) return '当前：图片阶段已完成'
  if (task.status === 'error') return '当前：图片阶段已中断'
  return '当前：等待图片进度'
}

function getVideoProgressText(task: DownloadTask) {
  if (!task.hasVideo) return '当前：无附带视频'
  if (task.status === 'completed') return '当前：附带视频已完成'
  if (task.status === 'error') return `当前：失败于${getFailureStageText(task)}`
  return `当前：${getTaskStageLabel(task)}`
}

function getVideoStatusText(task: DownloadTask) {
  if (!task.hasVideo) return '无视频'
  if (task.status === 'completed') return '已完成'
  if (task.status === 'error') return '失败'
  if (isVideoPhase(task)) return '处理中'
  return '等待视频阶段'
}
</script>





