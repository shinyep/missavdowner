<template>
  <div class="flex-1 flex flex-col items-center justify-center px-6 py-10 bg-surface">
    <div class="max-w-sm w-full flex flex-col items-center gap-6 text-center">
      <!-- Logo -->
      <div class="w-20 h-20 rounded-2xl bg-primary-container/30 flex items-center justify-center">
        <div class="size-12 text-primary">
          <svg fill="none" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
            <path d="M8.57829 8.57829C5.52816 11.6284 3.451 15.5145 2.60947 19.7452C1.76794 23.9758 2.19984 28.361 3.85056 32.3462C5.50128 36.3314 8.29667 39.7376 11.8832 42.134C15.4698 44.5305 19.6865 45.8096 24 45.8096C28.3135 45.8096 32.5302 44.5305 36.1168 42.134C39.7033 39.7375 42.4987 36.3314 44.1494 32.3462C45.8002 28.361 46.2321 23.9758 45.3905 19.7452C44.549 15.5145 42.4718 11.6284 39.4217 8.57829L24 24L8.57829 8.57829Z" fill="currentColor"/>
          </svg>
        </div>
      </div>

      <!-- 应用信息 -->
      <div class="flex flex-col gap-1">
        <h1 class="font-headline text-xl font-bold text-on-surface">MissAV Downloader</h1>
        <p class="text-sm text-on-surface-variant">MissAV 视频下载工具</p>
        <p class="text-xs text-on-surface-variant mt-1">版本 {{ version }}</p>
      </div>

      <!-- 功能说明 -->
      <div class="bg-surface-container-low rounded-md p-4 w-full text-left border border-outline-variant/10">
        <h3 class="font-headline text-sm font-bold text-on-surface mb-2">功能特性</h3>
        <ul class="flex flex-col gap-2 text-xs text-on-surface-variant">
          <li class="flex items-start gap-2">
            <span class="material-symbols-outlined text-primary text-sm mt-0.5">check_circle</span>
            <span>从 missav.ws 解析和下载视频</span>
          </li>
          <li class="flex items-start gap-2">
            <span class="material-symbols-outlined text-primary text-sm mt-0.5">check_circle</span>
            <span>自动合并 m3u8 流为 mp4 格式</span>
          </li>
          <li class="flex items-start gap-2">
            <span class="material-symbols-outlined text-primary text-sm mt-0.5">check_circle</span>
            <span>提取视频元数据（标题、演员、标签等）</span>
          </li>
          <li class="flex items-start gap-2">
            <span class="material-symbols-outlined text-primary text-sm mt-0.5">check_circle</span>
            <span>下载队列管理和进度显示</span>
          </li>
        </ul>
      </div>

      <!-- 技术栈 -->
      <div class="bg-surface-container-low rounded-md p-4 w-full text-left border border-outline-variant/10">
        <h3 class="font-headline text-sm font-bold text-on-surface mb-2">技术栈</h3>
        <div class="flex flex-wrap gap-2">
          <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">Electron</span>
          <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">Vue 3</span>
          <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">TypeScript</span>
          <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">Tailwind CSS</span>
          <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">Playwright</span>
          <span class="px-2 py-1 bg-surface-variant text-on-surface-variant text-xs rounded">FFmpeg</span>
        </div>
      </div>

      <!-- 免责声明 -->
      <div class="bg-tertiary-container/30 rounded-md p-3 w-full border border-tertiary/20">
        <div class="flex items-start gap-2">
          <span class="material-symbols-outlined text-tertiary text-sm mt-0.5">info</span>
          <p class="text-xs text-on-surface-variant text-left">
            本工具仅供个人学习和研究使用，请勿用于商业用途。下载的内容版权归原作者所有。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const version = ref('1.0.0')

onMounted(async () => {
  if (window.electronAPI?.app?.getVersion) {
    version.value = await window.electronAPI.app.getVersion()
  }
})
</script>
