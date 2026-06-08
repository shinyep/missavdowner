<template>
  <header class="flex items-center justify-between whitespace-nowrap bg-surface-container-low px-6 py-3 select-none app-drag">
    <!-- Logo -->
    <div class="flex items-center gap-3 text-on-surface">
      <div class="size-5 text-primary">
        <svg fill="none" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
          <path d="M8.57829 8.57829C5.52816 11.6284 3.451 15.5145 2.60947 19.7452C1.76794 23.9758 2.19984 28.361 3.85056 32.3462C5.50128 36.3314 8.29667 39.7376 11.8832 42.134C15.4698 44.5305 19.6865 45.8096 24 45.8096C28.3135 45.8096 32.5302 44.5305 36.1168 42.134C39.7033 39.7375 42.4987 36.3314 44.1494 32.3462C45.8002 28.361 46.2321 23.9758 45.3905 19.7452C44.549 15.5145 42.4718 11.6284 39.4217 8.57829L24 24L8.57829 8.57829Z" fill="currentColor"/>
        </svg>
      </div>
      <h2 class="font-headline text-base font-bold leading-tight tracking-tight text-on-surface">MissAV Downloader</h2>
    </div>

    <!-- Navigation -->
    <div class="flex flex-1 justify-end gap-6">
      <nav class="flex items-center gap-6 app-no-drag">
        <div
          v-for="tab in tabs"
          :key="tab.key"
          class="relative flex items-center h-full cursor-pointer"
          @click="$emit('changeTab', tab.key)"
        >
          <span
            class="font-headline text-sm leading-normal transition-colors"
            :class="currentTab === tab.key ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface font-medium'"
          >
            {{ tab.label }}
          </span>
          <div
            v-if="currentTab === tab.key"
            class="absolute -bottom-3 left-0 w-full h-0.5 bg-primary rounded-t-full"
          />
        </div>
      </nav>

      <!-- Settings Button -->
      <button
        aria-label="Settings"
        class="flex items-center justify-center rounded-md size-8 bg-surface-container-highest text-on-surface hover:bg-surface-variant transition-colors app-no-drag"
        @click="$emit('changeTab', 'settings')"
      >
        <span class="material-symbols-outlined text-lg">settings</span>
      </button>

      <!-- Window Controls -->
      <div class="flex items-center gap-1 app-no-drag">
        <button
          class="size-8 flex items-center justify-center rounded hover:bg-surface-container-high transition-colors"
          title="最小化"
          @click="minimizeWindow"
        >
          <span class="material-symbols-outlined text-base">remove</span>
        </button>
        <button
          class="size-8 flex items-center justify-center rounded hover:bg-surface-container-high transition-colors"
          title="最大化"
          @click="maximizeWindow"
        >
          <span class="material-symbols-outlined text-base">crop_square</span>
        </button>
        <button
          class="size-8 flex items-center justify-center rounded hover:bg-error-container text-on-surface-variant hover:text-on-error-container transition-colors"
          title="关闭"
          @click="closeWindow"
        >
          <span class="material-symbols-outlined text-base">close</span>
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import type { TabType } from '../types'

defineProps<{
  currentTab: TabType
}>()

defineEmits<{
  changeTab: [tab: TabType]
}>()

const tabs = [
  { key: 'download' as TabType, label: '解析下载' },
  { key: 'gallery' as TabType, label: '图集下载' },
  { key: 'history' as TabType, label: '下载历史' },
  { key: 'about' as TabType, label: '关于软件' },
]

function minimizeWindow() {
  window.electronAPI?.window?.minimize()
}

function maximizeWindow() {
  window.electronAPI?.window?.maximize()
}

function closeWindow() {
  window.electronAPI?.window?.close()
}
</script>

<style scoped>
.app-drag {
  -webkit-app-region: drag;
}
.app-no-drag {
  -webkit-app-region: no-drag;
}
</style>
