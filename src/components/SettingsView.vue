<template>
  <div class="flex-1 flex flex-col overflow-hidden bg-surface">
    <div class="px-8 py-4 border-b border-outline-variant/10">
      <h2 class="font-headline text-lg font-bold text-on-surface">设置</h2>
    </div>

    <div class="flex-1 overflow-y-auto px-8 py-5">
      <div class="max-w-xl mx-auto flex flex-col gap-6">

        <!-- 下载设置 -->
        <section class="flex flex-col gap-4">
          <h3 class="font-headline text-sm font-bold text-on-surface flex items-center gap-2">
            <span class="material-symbols-outlined text-primary text-base">download</span>
            下载设置
          </h3>

          <!-- 下载目录 -->
          <div class="flex flex-col gap-1.5">
            <label class="text-xs font-medium text-on-surface-variant">下载目录</label>
            <div class="flex gap-2">
              <input
                v-model="settings.downloadDir"
                type="text"
                class="flex-1 h-9 bg-surface-container-highest rounded-md px-3 text-sm text-on-surface border border-outline-variant/10 focus:outline-none focus:ring-1 focus:ring-primary"
                readonly
              />
              <button
                class="flex items-center gap-1 px-3 h-9 bg-surface-container-highest text-on-surface rounded-md text-xs font-medium hover:bg-surface-variant transition-colors border border-outline-variant/10"
                @click="selectDownloadDir"
              >
                <span class="material-symbols-outlined text-sm">folder</span>
                <span>浏览</span>
              </button>
            </div>
          </div>

          <!-- 最大并发数 -->
          <div class="flex flex-col gap-1.5">
            <label class="text-xs font-medium text-on-surface-variant">最大并发下载数</label>
            <select
              v-model="settings.maxConcurrent"
              class="h-9 bg-surface-container-highest rounded-md px-3 text-sm text-on-surface border border-outline-variant/10 focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option :value="1">1</option>
              <option :value="2">2</option>
              <option :value="3">3</option>
              <option :value="5">5</option>
            </select>
          </div>

          <!-- 自动合并 -->
          <div class="flex items-center justify-between py-2">
            <div>
              <label class="text-sm font-medium text-on-surface">自动合并视频</label>
              <p class="text-xs text-on-surface-variant mt-0.5">下载完成后自动合并 ts 片段为 mp4</p>
            </div>
            <button
              class="w-10 h-6 rounded-full transition-colors relative"
              :class="settings.autoMerge ? 'bg-primary' : 'bg-surface-variant'"
              @click="settings.autoMerge = !settings.autoMerge"
            >
              <div
                class="w-4 h-4 bg-white rounded-full transition-transform absolute top-1"
                :class="settings.autoMerge ? 'left-5' : 'left-1'"
              ></div>
            </button>
          </div>

          <!-- 保留临时文件 -->
          <div class="flex items-center justify-between py-2">
            <div>
              <label class="text-sm font-medium text-on-surface">保留临时文件</label>
              <p class="text-xs text-on-surface-variant mt-0.5">合并后保留原始 ts 片段文件</p>
            </div>
            <button
              class="w-10 h-6 rounded-full transition-colors relative"
              :class="settings.keepTempFiles ? 'bg-primary' : 'bg-surface-variant'"
              @click="settings.keepTempFiles = !settings.keepTempFiles"
            >
              <div
                class="w-4 h-4 bg-white rounded-full transition-transform absolute top-1"
                :class="settings.keepTempFiles ? 'left-5' : 'left-1'"
              ></div>
            </button>
          </div>
        </section>

        <!-- 网络设置 -->
        <section class="flex flex-col gap-4">
          <h3 class="font-headline text-sm font-bold text-on-surface flex items-center gap-2">
            <span class="material-symbols-outlined text-primary text-base">lan</span>
            网络设置
          </h3>

          <!-- 代理设置 -->
          <div class="flex flex-col gap-1.5">
            <label class="text-xs font-medium text-on-surface-variant">HTTP 代理</label>
            <input
              v-model="settings.proxy"
              type="text"
              class="h-9 bg-surface-container-highest rounded-md px-3 text-sm text-on-surface placeholder:text-outline-variant border border-outline-variant/10 focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="例如: http://127.0.0.1:7890"
            />
          </div>
        </section>

        <!-- 保存按钮 -->
        <div class="flex justify-end gap-3 pt-4 border-t border-outline-variant/10">
          <button
            class="px-4 py-2 bg-surface-container-highest text-on-surface rounded-md text-sm font-medium hover:bg-surface-variant transition-colors border border-outline-variant/10"
            @click="resetSettings"
          >
            重置默认
          </button>
          <button
            class="px-4 py-2 gradient-btn rounded-md text-sm font-semibold"
            @click="saveSettings"
          >
            <span class="flex items-center gap-2">
              <span class="material-symbols-outlined text-sm">save</span>
              <span>保存设置</span>
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { AppSettings } from '../types'

const settings = ref<AppSettings>({
  downloadDir: '',
  maxConcurrent: 2,
  autoMerge: true,
  keepTempFiles: false,
  proxy: ''
})

onMounted(async () => {
  // 加载保存的设置
  const saved = localStorage.getItem('app-settings')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      settings.value = { ...settings.value, ...parsed }
    } catch {}
  }

  // 如果没有设置下载目录，使用默认目录
  if (!settings.value.downloadDir && window.electronAPI?.app?.getDefaultDownloadDir) {
    settings.value.downloadDir = await window.electronAPI.app.getDefaultDownloadDir()
  }
})

async function selectDownloadDir() {
  if (window.electronAPI?.dialog?.selectFolder) {
    const dir = await window.electronAPI.dialog.selectFolder()
    if (dir) {
      settings.value.downloadDir = dir
    }
  }
}

async function saveSettings() {
  // 保存设置到本地存储
  localStorage.setItem('app-settings', JSON.stringify(settings.value))
  alert('设置已保存')
}

function resetSettings() {
  settings.value = {
    downloadDir: settings.value.downloadDir,
    maxConcurrent: 2,
    autoMerge: true,
    keepTempFiles: false,
    proxy: ''
  }
}
</script>
