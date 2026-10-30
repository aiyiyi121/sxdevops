<template>
  <div class="fade-in sql-audit-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row">
          <span class="sql-header-icon"><el-icon><Tickets /></el-icon></span>
          <h2>SQL 审计</h2>
          <p class="page-desc page-desc--secondary">{{ activeTabDescription }}</p>
        </div>
      </div>
    </section>

    <div class="audit-grid sql-audit-overview">
      <button
        v-for="card in sqlAuditStatsCards"
        :key="card.label"
        type="button"
        class="audit-card audit-card--inline audit-card--action"
        :class="[card.cardClass, { 'is-active': card.active }]"
        @click="handleStatCardClick(card)"
      >
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-label">{{ card.label }}</div>
      </button>
    </div>

    <section class="tabs-card">
      <el-tabs v-model="activeTab" class="event-like-tabs sql-audit-tabs" @tab-change="handleTabChange">
        <el-tab-pane
          v-for="tab in availableTabs"
          :key="tab.name"
          :name="tab.name"
        >
          <template #label>
            <span class="tab-label"><el-icon><component :is="tab.icon" /></el-icon>{{ tab.label }}</span>
          </template>
        </el-tab-pane>
      </el-tabs>
    </section>

    <SqlDatasources v-if="activeTab === 'datasources'" embedded />
    <SqlOrders v-else-if="activeTab === 'orders'" embedded />
    <SqlQuery v-else-if="activeTab === 'query'" embedded />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Coin, Search, Tickets } from '@element-plus/icons-vue'
import { getDataSources, getQueryOrders, getSqlOrders } from '@/api/modules/sqlaudit'
import { useAuthStore } from '@/stores/auth'
import SqlDatasources from '@/views/SqlDatasources.vue'
import SqlOrders from '@/views/SqlOrders.vue'
import SqlQuery from '@/views/SqlQuery.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const activeTab = ref('datasources')
const snapshotLoading = ref(false)
const validOrderStatuses = ['pending', 'approved', 'rejected', 'executed', 'failed']
const snapshotStats = ref({
  datasources: { total: 0, active: 0, mysql: 0, mongodb: 0 },
  orders: { total: 0, pending: 0, approved: 0, failed: 0 },
  queries: { total: 0, loaded: 0, rows: 0, avgDuration: 0 },
})
const routeStatus = computed(() => {
  const status = Array.isArray(route.query.status) ? route.query.status[0] : route.query.status
  return typeof status === 'string' && validOrderStatuses.includes(status) ? status : ''
})
const isOrderOverviewFocused = computed(() => activeTab.value === 'orders' && routeStatus.value !== 'pending')
const isPendingOrderFocused = computed(() => activeTab.value === 'orders' && routeStatus.value === 'pending')

const sqlAuditStatsCards = computed(() => ([
  {
    key: 'orders',
    value: snapshotStats.value.orders.total,
    label: '工单总数',
    cardClass: '',
    active: isOrderOverviewFocused.value,
    query: {},
  },
  {
    key: 'orders',
    value: snapshotStats.value.orders.pending,
    label: '待审核工单',
    cardClass: 'audit-card--warning',
    active: isPendingOrderFocused.value,
    query: { status: 'pending' },
  },
  {
    key: 'query',
    value: snapshotStats.value.queries.total,
    label: '查询总数',
    cardClass: 'audit-card--success',
    active: activeTab.value === 'query',
    query: {},
  },
  {
    key: 'datasources',
    value: snapshotStats.value.datasources.total,
    label: '数据源总数',
    cardClass: 'audit-card--danger',
    active: activeTab.value === 'datasources',
    query: {},
  },
]))

const availableTabs = computed(() => {
  const tabs = []
  if (authStore.hasAnyPermission(['sqlaudit.order.view', 'sqlaudit.order.submit', 'sqlaudit.order.review', 'sqlaudit.order.execute'])) {
    tabs.push({ name: 'orders', label: '工单', icon: Tickets })
  }
  if (authStore.hasAnyPermission(['sqlaudit.query.view', 'sqlaudit.query.execute'])) {
    tabs.push({ name: 'query', label: '查询', icon: Search })
  }
  if (authStore.hasPermission('sqlaudit.datasource.view')) {
    tabs.push({ name: 'datasources', label: '数据源', icon: Coin })
  }
  return tabs
})

const activeTabDescription = computed(() => {
  const descMap = {
    datasources: '维护 MySQL / PostgreSQL / MongoDB 数据源，支持测试连接与库列表发现。',
    orders: '覆盖提交、预检查、审核与执行链路，适合演示标准数据库变更流程。',
    query: '只读查询入口，支持 SQL / MongoDB 查询并自动沉淀到历史记录。',
  }
  return descMap[activeTab.value] || descMap.datasources
})

const normalizeTab = (tab) => {
  if (availableTabs.value.some(item => item.name === tab)) {
    return tab
  }
  const defaultTab = route.meta?.defaultTab
  if (availableTabs.value.some(item => item.name === defaultTab)) {
    return defaultTab
  }
  if (availableTabs.value.some(item => item.name === 'datasources')) {
    return 'datasources'
  }
  return availableTabs.value[0]?.name || 'datasources'
}

const buildAuditQuery = (tab, status = '') => {
  const nextQuery = { ...route.query, tab }
  if (tab === 'orders' && status) {
    nextQuery.status = status
  } else {
    delete nextQuery.status
  }
  return nextQuery
}

watch(
  [() => route.query.tab, () => route.query.status, availableTabs],
  ([tab, status]) => {
    const nextTab = normalizeTab(tab)
    if (activeTab.value !== nextTab) {
      activeTab.value = nextTab
    }
    const currentStatus = Array.isArray(status) ? status[0] : status
    const nextStatus = nextTab === 'orders' && validOrderStatuses.includes(currentStatus) ? currentStatus : ''
    if (route.query.tab !== nextTab || (currentStatus || '') !== nextStatus) {
      router.replace({ path: route.path, query: buildAuditQuery(nextTab, nextStatus) })
    }
  },
  { immediate: true },
)

const handleTabChange = (tab) => {
  const nextTab = normalizeTab(tab)
  const nextQuery = buildAuditQuery(nextTab, nextTab === 'orders' ? routeStatus.value : '')
  if (route.query.tab !== nextTab || route.query.status !== nextQuery.status) {
    router.replace({ path: route.path, query: nextQuery })
  }
  if (activeTab.value !== nextTab) {
    activeTab.value = nextTab
  }
}

const handleStatCardClick = (card) => {
  const nextTab = normalizeTab(card.key)
  const nextQuery = buildAuditQuery(nextTab, card.query.status || '')
  if (route.query.tab !== nextTab || route.query.status !== nextQuery.status) {
    router.replace({ path: route.path, query: nextQuery })
  }
  if (activeTab.value !== nextTab) {
    activeTab.value = nextTab
  }
}

async function loadSnapshotStats() {
  snapshotLoading.value = true
  try {
    const [datasourceRes, orderRes, queryRes] = await Promise.allSettled([
      getDataSources({ page_size: 500 }),
      getSqlOrders({ page_size: 500 }),
      getQueryOrders({ page_size: 500 }),
    ])

    const datasourceItems = datasourceRes.status === 'fulfilled' ? (datasourceRes.value?.results || datasourceRes.value || []) : []
    snapshotStats.value.datasources = {
      total: datasourceRes.status === 'fulfilled' ? (datasourceRes.value?.count ?? datasourceItems.length) : 0,
      active: datasourceItems.filter(item => item.is_active).length,
      mysql: datasourceItems.filter(item => item.db_type === 'mysql').length,
      mongodb: datasourceItems.filter(item => item.db_type === 'mongodb').length,
    }

    const orderItems = orderRes.status === 'fulfilled' ? (orderRes.value?.results || orderRes.value || []) : []
    snapshotStats.value.orders = {
      total: orderRes.status === 'fulfilled' ? (orderRes.value?.count ?? orderItems.length) : 0,
      pending: orderItems.filter(item => item.status === 'pending').length,
      approved: orderItems.filter(item => item.status === 'approved').length,
      failed: orderItems.filter(item => item.status === 'failed').length,
    }

    const queryItems = queryRes.status === 'fulfilled' ? (queryRes.value?.results || queryRes.value || []) : []
    const queryTotal = queryRes.status === 'fulfilled' ? (queryRes.value?.count ?? queryItems.length) : 0
    snapshotStats.value.queries = {
      total: queryTotal,
      loaded: queryItems.length,
      rows: queryItems.reduce((sum, item) => sum + (Number(item.result_count) || 0), 0),
      avgDuration: queryItems.length ? Math.round(queryItems.reduce((sum, item) => sum + (Number(item.duration_ms) || 0), 0) / queryItems.length) : 0,
    }
  } finally {
    snapshotLoading.value = false
  }
}

onMounted(loadSnapshotStats)
</script>

<style scoped>
.panel {
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(250,252,255,.96) 100%);
  border: 1px solid rgba(15,23,42,.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
  padding: 14px 16px;
}

.sql-audit-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 0;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36,91,219,.09);
}

.release-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero h2 {
  margin: 0;
  font-size: 23px;
  color: #0f172a;
}

.sql-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%);
  border: 1px solid rgba(36,91,219,.12);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}

.sql-audit-overview {
  margin-bottom: 0;
  gap: 10px;
}

.sql-audit-overview .audit-card {
  border-radius: 14px;
  border: 1px solid rgba(15,23,42,.08);
  background: linear-gradient(180deg,rgba(255,255,255,.98) 0%,rgba(252,253,255,.94) 100%);
  box-shadow: 0 4px 14px rgba(15,23,42,.03);
}

.sql-audit-overview .audit-card--inline {
  min-height: 68px;
  padding: 14px 16px;
}

.sql-audit-overview .audit-card .stat-label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.sql-audit-overview .audit-card .stat-value {
  font-size: 24px;
  color: #1f2329;
}

.sql-audit-overview .audit-card--warning {
  background: linear-gradient(180deg,#fffdfa 0%,#ffffff 100%);
}

.sql-audit-overview .audit-card--success {
  background: linear-gradient(180deg,#fbfffd 0%,#ffffff 100%);
}

.sql-audit-overview .audit-card--danger {
  background: linear-gradient(180deg,#fffafb 0%,#ffffff 100%);
}

.sql-audit-overview .audit-card--action:hover {
  border-color: rgba(36,91,219,.16);
  box-shadow: 0 10px 20px rgba(36,91,219,.06);
}

.sql-audit-overview .audit-card--action.is-active {
  border-color: rgba(36,91,219,.26);
  background: linear-gradient(180deg, #f4f7ff 0%, #ffffff 100%);
  box-shadow:
    0 0 0 1px rgba(36,91,219,.08),
    0 12px 22px rgba(36,91,219,.08);
}

.page-desc {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.page-desc--secondary {
  color: #64748b;
  flex: 0 1 auto;
}

.sql-audit-tabs {
  width: 100%;
}

.sql-audit-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.tabs-card {
  margin-top: 0;
}

.sql-audit-tabs :deep(.el-tabs__nav-wrap) {
  display: block;
  max-width: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.sql-audit-tabs :deep(.el-tabs__nav-wrap::after),
.sql-audit-tabs :deep(.el-tabs__active-bar),
.sql-audit-tabs :deep(.el-tabs__content) {
  display: none;
}

.sql-audit-tabs :deep(.el-tabs__nav-scroll) {
  overflow: visible;
}

.sql-audit-tabs :deep(.el-tabs__nav) {
  display: flex;
  gap: 8px;
  border: 0;
}

.sql-audit-tabs :deep(.el-tabs__item) {
  min-height: 38px;
  height: 38px;
  padding: 0 20px !important;
  border-radius: 8px;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 38px;
}

.sql-audit-tabs :deep(.el-tabs__item:hover) {
  background: rgba(51, 112, 255, 0.06);
  color: #245bdb;
}

.sql-audit-tabs :deep(.el-tabs__item.is-active) {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.hero.panel { border-radius: 20px; }
</style>

