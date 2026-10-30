<template>
  <div v-if="visibleTabs.length" class="observability-route-tabs neo-tabs theme-blue">
    <button
      v-for="tab in visibleTabs"
      :key="tab.key"
      type="button"
      class="neo-tab-btn"
      :class="{ active: isActiveTab(tab) }"
      @click="goTab(tab)"
    >
      <el-icon><component :is="tab.icon" /></el-icon>
      <span>{{ tab.title }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { SYSTEM_POSTURE_ENABLED } from '@/config/features'

const props = defineProps({
  group: {
    type: String,
    required: true,
  },
})

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const tabGroups = {
  boards: [
    { key: 'grafana', title: '仪表盘', icon: 'Histogram', path: '/observability/grafana', permission: 'ops.grafana.view' },
    ...(SYSTEM_POSTURE_ENABLED
      ? [
          { key: 'system-posture', title: '系统态势', icon: 'Aim', path: '/observability/system-posture', permission: 'ops.observability.system_posture.view' },
          { key: 'posture-history', title: '态势历史', icon: 'TrendCharts', path: '/observability/posture-history', permission: 'ops.observability.system_posture.view' },
        ]
      : []),
  ],
  query: [
    { key: 'metrics-query', title: '指标查询', icon: 'DataAnalysis', path: '/observability/metrics', permission: 'ops.metric.query' },
    { key: 'logs-query', title: '日志查询', icon: 'Search', path: '/logs/query', permission: 'ops.log.query' },
    { key: 'tracing-query', title: '链路追踪', icon: 'Connection', path: '/observability/tracing', permission: 'ops.trace.view' },
  ],
  datasources: [
    { key: 'metric-datasources', title: '指标数据源', icon: 'DataBoard', path: '/observability/metrics', query: { tab: 'datasources' }, permission: 'ops.metric.datasource.view' },
    { key: 'log-datasources', title: '日志数据源', icon: 'DataBoard', path: '/logs/datasources', permission: 'ops.log.datasource.view' },
    { key: 'trace-datasources', title: '链路追踪数据源', icon: 'DataBoard', path: '/observability/tracing/datasources', permission: 'ops.trace.datasource.view' },
    { key: 'datasource-links', title: '关联配置', icon: 'Share', path: '/observability/datasource-links', permission: 'ops.observability.link.view' },
  ],
}

function canAccess(tab) {
  if (tab.permission) return authStore.hasPermission(tab.permission)
  if (tab.anyPermissions) return authStore.hasAnyPermission(tab.anyPermissions)
  return true
}

const visibleTabs = computed(() => (tabGroups[props.group] || []).filter(canAccess))

function isActiveTab(tab) {
  if (tab.path !== route.path) return false
  if (tab.query?.tab) return route.query.tab === tab.query.tab
  if ((route.path === '/observability/metrics' || route.path === '/observability/tracing') && route.query.tab === 'datasources') return false
  return true
}

function goTab(tab) {
  router.push({
    path: tab.path,
    query: tab.query || {},
  })
}
</script>

<style scoped>
.observability-route-tabs {
  margin: 0;
}
</style>
