<template>
  <section class="hero panel platform-config-hero">
    <div class="platform-config-title-row">
      <span class="platform-config-icon"><el-icon><SetUp /></el-icon></span>
      <h2>平台配置</h2>
    </div>
  </section>

  <div class="neo-tabs theme-blue platform-config-tabs" role="tablist" aria-label="平台配置">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      role="tab"
      class="neo-tab-btn"
      :class="{ active: activeTab === tab.key }"
      :aria-selected="activeTab === tab.key"
      @click="router.push(tab.path)"
    >
      <el-icon><component :is="tab.icon" /></el-icon>
      <span>{{ tab.label }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Connection, DataBoard, SetUp } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const activeTab = computed(() => {
  if (route.name === 'CmdbIpam') return 'ipam'
  if (route.name === 'CmdbModelConfig') return 'model'
  return 'sync'
})
const tabs = computed(() => [
  authStore.hasPermission('cmdb.sync.view') && { key: 'sync', label: '资产采集', icon: Connection, path: '/cmdb/sync' },
  authStore.hasPermission('cmdb.model.manage') && { key: 'model', label: '分类配置', icon: DataBoard, path: '/cmdb/model/config' },
  authStore.hasPermission('cmdb.ipam.view') && { key: 'ipam', label: 'IP 管理', icon: Connection, path: '/cmdb/ipam' },
].filter(Boolean))
</script>

<style scoped>
.platform-config-hero { margin: 0; padding: 14px 16px; border: 1px solid rgba(36,91,219,.09); background: linear-gradient(135deg,#fbfdff 0%,#f7faff 52%,#f9fbfd 100%); box-shadow: 0 8px 24px rgba(15,23,42,.04); }
.hero.panel { border-radius: 20px; }
.platform-config-title-row { display: flex; align-items: center; gap: 12px; }
.platform-config-title-row h2 { margin: 0; color: #0f172a; font-size: 23px; }
.platform-config-icon { width: 42px; height: 42px; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center; font-size: 20px; color: #245bdb; background: #e8f0ff; }
.platform-config-tabs { display: flex; width: 100%; margin: 0; padding: 3px; gap: 8px; border: 1px solid rgba(148,163,184,.16); border-radius: 12px; background: #fff; box-shadow: none; overflow-x: auto; }
.platform-config-tabs .neo-tab-btn { flex: 0 0 auto; min-height: 38px; padding: 0 18px; display: inline-flex; align-items: center; gap: 6px; border: 0; border-radius: 8px; background: transparent; color: #475569; font-size: 13px; font-weight: 700; line-height: 1.2; white-space: nowrap; cursor: pointer; }
.platform-config-tabs .neo-tab-btn .el-icon { font-size: 15px; }
.platform-config-tabs .neo-tab-btn:hover { background: rgba(51,112,255,.06); color: #245bdb; }
.platform-config-tabs .neo-tab-btn.active { color: #245bdb; background: #e8f0ff; box-shadow: inset 0 0 0 1px rgba(51,112,255,.1); }
</style>
