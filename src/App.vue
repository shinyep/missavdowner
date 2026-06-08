<template>
  <div class="relative flex flex-col w-full h-screen bg-surface">
    <!-- Header -->
    <Header :current-tab="currentTab" @change-tab="changeTab" />

    <!-- Main Content -->
    <main class="flex-1 flex overflow-hidden">
      <DownloadView v-show="currentTab === 'download'" />
      <GalleryView v-show="currentTab === 'gallery'" />
      <HistoryView v-show="currentTab === 'history'" :active="currentTab === 'history'" />
      <SettingsView v-show="currentTab === 'settings'" />
      <AboutView v-show="currentTab === 'about'" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Header from './components/Header.vue'
import DownloadView from './components/DownloadView.vue'
import GalleryView from './components/GalleryView.vue'
import HistoryView from './components/HistoryView.vue'
import SettingsView from './components/SettingsView.vue'
import AboutView from './components/AboutView.vue'
import type { TabType } from './types'

const currentTab = ref<TabType>('download')

function changeTab(tab: TabType) {
  currentTab.value = tab
}

// 监听跳转设置页事件
window.addEventListener('navigate-to-settings', () => {
  currentTab.value = 'settings'
})

// 监听菜单点击关于事件
let unsubscribeMenu: (() => void) | null = null

onMounted(() => {
  if (window.electronAPI?.onMenuShowAbout) {
    unsubscribeMenu = window.electronAPI.onMenuShowAbout(() => {
      currentTab.value = 'about'
    })
  }
})

onUnmounted(() => {
  if (unsubscribeMenu) {
    unsubscribeMenu()
  }
})
</script>
