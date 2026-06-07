<template>
  <div class="flex-1 flex flex-col overflow-hidden bg-surface">
    <div class="flex items-center justify-between px-8 py-4 border-b border-outline-variant/10">
      <h2 class="font-headline text-lg font-bold text-on-surface">下载历史</h2>
      <div class="flex items-center gap-2">
        <div class="relative">
          <input
            v-model="searchQuery"
            type="text"
            class="w-48 h-8 bg-surface-container-highest rounded-md pl-8 pr-3 text-xs text-on-surface placeholder:text-outline-variant focus:outline-none focus:ring-1 focus:ring-primary border border-outline-variant/10"
            placeholder="搜索..."
          />
          <span class="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm">search</span>
        </div>
        <button
          v-if="historyList.length > 0"
          class="flex items-center gap-1 px-3 py-1.5 bg-error-container/30 text-error rounded-md text-xs font-medium hover:bg-error-container/50 transition-colors"
          @click="clearHistory"
        >
          <span class="material-symbols-outlined text-sm">delete_sweep</span>
          <span>清空</span>
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-8 py-4">
      <!-- 空状态 -->
      <div v-if="historyList.length === 0" class="flex flex-col items-center justify-center h-full text-on-surface-variant">
        <span class="material-symbols-outlined text-5xl mb-3">history</span>
        <p class="text-sm">暂无下载历史</p>
      </div>

      <!-- 历史列表 -->
      <div v-else class="flex flex-col gap-2 max-w-2xl mx-auto">
        <div
          v-for="item in filteredHistory"
          :key="item.id"
          class="bg-surface-container-low rounded-md p-3 border border-outline-variant/10 hover:border-primary/30 transition-colors"
        >
          <div class="flex gap-3">
            <!-- 封面 -->
            <div
              class="w-28 h-16 rounded-sm bg-surface-variant bg-cover bg-center flex-shrink-0"
              :style="{ backgroundImage: `url(${item.cover})` }"
            ></div>
            <!-- 信息 -->
            <div class="flex-1 min-w-0">
              <h4 class="text-sm font-medium text-on-surface truncate">{{ item.title }}</h4>
              <div class="flex items-center gap-2 mt-1 text-xs text-on-surface-variant">
                <span v-if="item.code" class="font-mono">{{ item.code }}</span>
                <span v-if="item.actresses?.length">· {{ item.actresses[0] }}</span>
                <span>· {{ formatDate(item.downloadedAt) }}</span>
                <span v-if="item.fileSize">· {{ item.fileSize }}</span>
              </div>
            </div>
            <!-- 操作 -->
            <div class="flex items-center gap-1">
              <button
                class="size-7 flex items-center justify-center rounded hover:bg-surface-variant"
                @click="openFile(item.outputPath)"
                title="打开文件"
              >
                <span class="material-symbols-outlined text-sm">open_in_new</span>
              </button>
              <button
                class="size-7 flex items-center justify-center rounded hover:bg-surface-variant"
                @click="openFolder(item.outputPath)"
                title="打开文件夹"
              >
                <span class="material-symbols-outlined text-sm">folder_open</span>
              </button>
              <button
                class="size-7 flex items-center justify-center rounded hover:bg-error-container text-on-surface-variant hover:text-error"
                @click="deleteHistory(item.id)"
                title="删除"
              >
                <span class="material-symbols-outlined text-sm">delete</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { HistoryRecord } from '../types'

const searchQuery = ref('')
const historyList = ref<HistoryRecord[]>([])

const filteredHistory = computed(() => {
  if (!searchQuery.value.trim()) return historyList.value
  const query = searchQuery.value.toLowerCase()
  return historyList.value.filter(item =>
    item.title.toLowerCase().includes(query) ||
    item.code?.toLowerCase().includes(query) ||
    item.actresses?.some(a => a.toLowerCase().includes(query))
  )
})

onMounted(async () => {
  await loadHistory()
})

async function loadHistory() {
  if (window.electronAPI?.history?.get) {
    historyList.value = await window.electronAPI.history.get()
  }
}

async function deleteHistory(id: string) {
  if (window.electronAPI?.history?.delete) {
    await window.electronAPI.history.delete(id)
    historyList.value = historyList.value.filter(item => item.id !== id)
  }
}

async function clearHistory() {
  if (window.electronAPI?.history?.clear) {
    await window.electronAPI.history.clear()
    historyList.value = []
  }
}

async function openFile(filePath: string) {
  if (window.electronAPI?.shell?.openPath) {
    await window.electronAPI.shell.openPath(filePath)
  }
}

async function openFolder(filePath: string) {
  if (window.electronAPI?.shell?.openPath) {
    const folderPath = filePath.substring(0, filePath.lastIndexOf('\\'))
    await window.electronAPI.shell.openPath(folderPath)
  }
}

function formatDate(timestamp: number): string {
  const date = new Date(timestamp)
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>
