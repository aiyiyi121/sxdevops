<template>
  <div class="rum-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-title-row release-hero-title-inline">
        <span class="hero-icon"><el-icon><Monitor /></el-icon></span>
        <h2>真实用户监控</h2>
        <span class="rum-badge">RUM</span>
        <span class="page-inline-desc">从用户视角观测前端性能、会话体验与 JavaScript 错误</span>
      </div>
    </section>

    <div class="audit-grid">
      <button v-for="card in statCards" :key="card.label" type="button" class="audit-card audit-card--inline audit-card--action" :class="[card.tone, { active: activeTab === card.tab }]" @click="activeTab = card.tab">
        <span class="audit-card__label">{{ card.label }}</span><strong>{{ card.value }}</strong><small :class="card.deltaTone">{{ card.delta }}</small>
      </button>
    </div>

    <div class="neo-tabs theme-blue">
      <button v-for="tab in tabs" :key="tab.key" type="button" class="neo-tab-btn" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        <el-icon><component :is="tab.icon" /></el-icon>{{ tab.label }}
      </button>
    </div>

    <section class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head"><h3 class="toolbar-title">{{ tabTitle }}</h3><span class="toolbar-desc">{{ rangeLabel }} · 数据来自浏览器 SDK 与移动端 SDK</span></div>
        <el-button size="small" :loading="loading" @click="loadData"><el-icon><RefreshRight /></el-icon>刷新</el-button>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history">
        <el-input v-model.trim="keyword" size="small" clearable class="keyword-input" placeholder="搜索应用、页面、设备或错误内容"><template #prefix><el-icon><Search /></el-icon></template></el-input>
        <el-select v-model="platform" size="small" class="filter-select" @change="loadData"><el-option label="全部平台" value="all" /><el-option label="Web 浏览器" value="web" /><el-option label="移动端" value="mobile" /></el-select>
        <el-select v-model="range" size="small" class="filter-select" @change="loadData"><el-option label="最近 24 小时" value="24h" /><el-option label="最近 7 天" value="7d" /><el-option label="最近 30 天" value="30d" /></el-select>
        <el-select v-if="activeTab === 'sessions'" v-model="sessionStatus" size="small" class="filter-select"><el-option label="全部状态" value="all" /><el-option label="正常" value="正常" /><el-option label="有错误" value="有错误" /><el-option label="受挫" value="受挫" /></el-select>
        <el-select v-if="activeTab === 'errors'" v-model="errorLevel" size="small" class="filter-select"><el-option label="全部级别" value="all" /><el-option label="Error" value="error" /><el-option label="Warning" value="warning" /></el-select>
        <span class="generated-time">更新于 {{ generatedTime }}</span>
      </div>

      <template v-if="activeTab === 'performance'">
        <div class="vitals-grid">
          <div v-for="vital in data.vitals" :key="vital.key" class="vital-card">
            <div class="vital-head"><span>{{ vital.label }}</span><el-tag size="small" effect="light" :type="vital.type">{{ vital.status }}</el-tag></div>
            <strong>{{ vital.value }}</strong><div class="progress"><i :style="{ width: `${vital.score}%` }" :class="vital.type" /></div><small>{{ vital.hint }}</small>
          </div>
        </div>
        <div class="chart-panel">
          <div class="chart-title"><span>会话与错误趋势</span><small>{{ trendGranularity }}</small></div>
          <div class="bars"><div v-for="point in data.trend" :key="point.label" class="bar-group"><div class="bar sessions" :style="{ height: trendHeight(point.sessions) }"><em>{{ formatNumber(point.sessions) }}</em></div><div class="bar errors" :style="{ height: `${Math.max(5, point.errors * 7)}px` }"><em>{{ point.errors }}</em></div><small>{{ point.label }}</small></div></div>
          <div class="legend"><span><i class="dot blue" />会话</span><span><i class="dot red" />错误</span></div>
        </div>
        <div class="table-title-row"><div class="toolbar-head"><h4>应用性能排行</h4><span>{{ filteredApps.length }} 个应用</span></div></div>
        <el-table :data="filteredApps" size="small" stripe>
          <el-table-column prop="name" label="应用" min-width="180"><template #default="{ row }"><div class="app-cell"><strong>{{ row.name }}</strong><small>{{ row.service }}</small></div></template></el-table-column>
          <el-table-column prop="platform" label="平台" width="100"><template #default="{ row }"><el-tag size="small" effect="plain">{{ row.platform === 'web' ? 'Web' : 'Mobile' }}</el-tag></template></el-table-column>
          <el-table-column label="LCP" width="105"><template #default="{ row }"><span :class="metricTone(row.lcp, 2.5, 4)">{{ row.lcp }}s</span></template></el-table-column>
          <el-table-column label="INP" width="105"><template #default="{ row }"><span :class="metricTone(row.inp, 200, 500)">{{ row.inp }}ms</span></template></el-table-column>
          <el-table-column label="CLS" width="90"><template #default="{ row }">{{ row.cls }}</template></el-table-column>
          <el-table-column label="错误率" width="100"><template #default="{ row }"><span :class="metricTone(row.error_rate, 1, 2)">{{ row.error_rate }}%</span></template></el-table-column>
          <el-table-column label="会话数" width="110"><template #default="{ row }">{{ formatNumber(row.sessions) }}</template></el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'sessions'">
        <el-table :data="filteredSessions" size="small" stripe row-class-name="clickable-row" @row-click="openSession">
          <el-table-column prop="id" label="会话 ID" width="125" /><el-table-column prop="app" label="应用" width="130" /><el-table-column prop="path" label="入口页面" min-width="180" /><el-table-column prop="country" label="位置" width="120" /><el-table-column prop="device" label="设备" width="160" /><el-table-column prop="duration" label="时长" width="80" /><el-table-column prop="events" label="事件" width="70" /><el-table-column prop="network_requests" label="请求" width="70" />
          <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag size="small" :type="sessionTagType(row.status)">{{ row.status }}</el-tag></template></el-table-column><el-table-column prop="time" label="最近活动" width="100" />
        </el-table><el-empty v-if="!filteredSessions.length" description="没有匹配的用户会话" />
      </template>

      <template v-else>
        <el-table :data="filteredErrors" size="small" stripe>
          <el-table-column label="错误" min-width="360"><template #default="{ row }"><div class="error-message"><el-tag size="small" :type="row.level === 'error' ? 'danger' : 'warning'">{{ row.level === 'error' ? 'Error' : 'Warn' }}</el-tag><div><strong>{{ row.message }}</strong><small>{{ row.app }} · {{ row.source }}</small></div></div></template></el-table-column>
          <el-table-column prop="count" label="发生次数" width="100" /><el-table-column prop="users" label="影响用户" width="100" /><el-table-column prop="last_seen" label="最近发生" width="105" />
          <el-table-column label="关联分析" width="180" fixed="right"><template #default="{ row }"><el-button size="small" link type="primary" @click="openErrorSession(row)">会话</el-button><el-button v-if="canViewLogs" size="small" link type="primary" @click="openLogs(row)">日志</el-button><el-button v-if="canViewTracing" size="small" link type="primary" @click="openTrace(row)">Trace</el-button></template></el-table-column>
        </el-table><el-empty v-if="!filteredErrors.length" description="没有匹配的前端错误" />
      </template>
    </section>

    <el-dialog v-model="sessionDialogVisible" title="会话详情" width="680px" append-to-body>
      <div v-if="selectedSession" class="session-detail">
        <div class="detail-banner"><div><strong>{{ selectedSession.app }}</strong><span>{{ selectedSession.path }}</span></div><el-tag size="small" :type="sessionTagType(selectedSession.status)">{{ selectedSession.status }}</el-tag></div>
        <div class="detail-grid"><div><small>会话 ID</small><strong>{{ selectedSession.id }}</strong></div><div><small>平台</small><strong>{{ selectedSession.platform === 'web' ? 'Web 浏览器' : '移动端' }}</strong></div><div><small>位置</small><strong>{{ selectedSession.country }}</strong></div><div><small>设备</small><strong>{{ selectedSession.device }}</strong></div><div><small>停留时长</small><strong>{{ selectedSession.duration }}</strong></div><div><small>事件 / 请求</small><strong>{{ selectedSession.events }} / {{ selectedSession.network_requests }}</strong></div></div>
        <div class="session-trace"><span>Trace ID</span><code>{{ selectedSession.trace_id }}</code></div>
        <div class="dialog-actions"><el-button v-if="canViewLogs" size="small" @click="openLogs(selectedSession)">查看关联日志</el-button><el-button v-if="canViewTracing" size="small" type="primary" @click="openTrace(selectedSession)">查看调用链</el-button></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { DataAnalysis, Monitor, RefreshRight, Search, User, Warning } from '@element-plus/icons-vue'
import { getRumOverview } from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import { openRouteInNewTab } from '@/utils/router'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const activeTab = ref('performance')
const platform = ref('all')
const range = ref('24h')
const keyword = ref('')
const sessionStatus = ref('all')
const errorLevel = ref('all')
const sessionDialogVisible = ref(false)
const selectedSession = ref(null)
const data = ref({ totals: {}, deltas: {}, vitals: [], apps: [], trend: [], sessions: [], errors: [], generated_at: '' })
const tabs = [
  { key: 'performance', label: '性能概览', icon: DataAnalysis },
  { key: 'sessions', label: '会话分析', icon: User },
  { key: 'errors', label: '错误追踪', icon: Warning },
]
const rangeLabels = { '24h': '最近 24 小时', '7d': '最近 7 天', '30d': '最近 30 天' }
const tabTitle = computed(() => tabs.find((tab) => tab.key === activeTab.value)?.label || '')
const rangeLabel = computed(() => rangeLabels[range.value] || rangeLabels['24h'])
const trendGranularity = computed(() => range.value === '24h' ? '每 2 小时聚合' : range.value === '7d' ? '按天聚合' : '每 3 天聚合')
const generatedTime = computed(() => data.value.generated_at ? new Date(data.value.generated_at).toLocaleString('zh-CN', { hour12: false }) : '--')
const canViewLogs = computed(() => authStore.hasPermission('ops.log.query'))
const canViewTracing = computed(() => authStore.hasPermission('ops.trace.view'))
const statCards = computed(() => [
  { label: '用户会话', value: formatNumber(data.value.totals.sessions), delta: deltaText('sessions', '较上一周期'), tone: '', deltaTone: 'delta-up', tab: 'sessions' },
  { label: '活跃用户', value: formatNumber(data.value.totals.users), delta: deltaText('users', '较上一周期'), tone: 'audit-card--success', deltaTone: 'delta-up', tab: 'sessions' },
  { label: '前端错误', value: formatNumber(data.value.totals.errors), delta: deltaText('errors', '较上一周期'), tone: 'audit-card--warning', deltaTone: 'delta-down', tab: 'errors' },
  { label: '错误会话率', value: `${data.value.totals.error_rate || 0}%`, delta: '目标低于 1%', tone: 'audit-card--danger', deltaTone: '', tab: 'errors' },
])
const normalizedKeyword = computed(() => keyword.value.toLowerCase())
const filteredApps = computed(() => data.value.apps.filter((item) => includesKeyword(item.name, item.service)))
const filteredSessions = computed(() => data.value.sessions.filter((item) => {
  const statusMatch = sessionStatus.value === 'all' || item.status === sessionStatus.value
  return statusMatch && includesKeyword(item.id, item.app, item.path, item.device, item.country)
}))
const filteredErrors = computed(() => data.value.errors.filter((item) => {
  const levelMatch = errorLevel.value === 'all' || item.level === errorLevel.value
  return levelMatch && includesKeyword(item.message, item.app, item.source, item.service)
}))
const maxTrendSessions = computed(() => Math.max(...data.value.trend.map((item) => item.sessions), 1))

function includesKeyword(...values) {
  if (!normalizedKeyword.value) return true
  return values.some((value) => String(value || '').toLowerCase().includes(normalizedKeyword.value))
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function deltaText(key, prefix) {
  const value = Number(data.value.deltas?.[key] || 0)
  return `${prefix} ${value > 0 ? '+' : ''}${value}%`
}

function trendHeight(value) {
  return `${Math.max(12, Math.round(Number(value || 0) / maxTrendSessions.value * 112))}px`
}

function metricTone(value, good, warning) {
  if (Number(value) <= good) return 'metric-good'
  if (Number(value) <= warning) return 'metric-warning'
  return 'metric-danger'
}

function sessionTagType(status) {
  return status === '正常' ? 'success' : status === '有错误' ? 'danger' : 'warning'
}

async function loadData() {
  loading.value = true
  try {
    data.value = await getRumOverview({ platform: platform.value, range: range.value })
  } finally {
    loading.value = false
  }
}

function openSession(row) {
  selectedSession.value = row
  sessionDialogVisible.value = true
}

function openErrorSession(row) {
  const session = data.value.sessions.find((item) => item.id === row.session_id)
  if (session) openSession(session)
}

function openLogs(item) {
  openRouteInNewTab(router, {
    path: '/logs/query',
    query: { traceId: item.trace_id, service: item.service, title: `RUM ${item.app || item.id}`, window: '60' },
  })
}

function openTrace(item) {
  openRouteInNewTab(router, {
    path: '/observability/tracing',
    query: { traceId: item.trace_id, service: item.service, autoRun: '1' },
  })
}

onMounted(loadData)
</script>

<style scoped>
.rum-page { color: #0f172a; display: flex; flex-direction: column; gap: 6px; }
.panel, .workbench-card { background: #fff; border: 1px solid #e2e8f0; box-shadow: 0 8px 22px rgba(15, 23, 42, .04); }
.hero { align-items: center; background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%); border-color: rgba(36, 91, 219, .09); display: flex; padding: 14px 16px; }
.hero.panel { border-radius: 20px; }
.release-hero-title-row { align-items: center; display: flex; gap: 10px; min-width: 0; }
.hero-icon { align-items: center; background: #e8f0ff; border-radius: 14px; color: #245bdb; display: inline-flex; flex: 0 0 42px; height: 42px; justify-content: center; width: 42px; }
.hero h2 { font-size: 21px; margin: 0; white-space: nowrap; }
.rum-badge { background: rgba(51, 112, 255, .1); border-radius: 999px; color: #245bdb; font-size: 11px; font-weight: 700; letter-spacing: .8px; padding: 3px 7px; }
.page-inline-desc { color: #64748b; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.audit-grid { display: grid; gap: 10px; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; }
.audit-card { appearance: none; background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 6px 18px rgba(31, 35, 41, .04); color: inherit; cursor: pointer; display: grid; grid-template-columns: minmax(0, 1fr) auto; min-height: 68px; padding: 14px 16px; text-align: left; }
.audit-card:hover, .audit-card.active { border-color: rgba(36, 91, 219, .28); box-shadow: 0 8px 22px rgba(36, 91, 219, .08); }
.audit-card--success { background: linear-gradient(135deg, #fff, #f4fcf7); }
.audit-card--warning { background: linear-gradient(135deg, #fff, #fffbeb); }
.audit-card--danger { background: linear-gradient(135deg, #fff, #fff6f7); }
.audit-card__label { align-self: center; color: #475569; font-size: 13px; font-weight: 600; }
.audit-card strong { align-self: center; font-size: 24px; line-height: 1; }
.audit-card small { color: #64748b; grid-column: 1 / -1; margin-top: 5px; }
.delta-up { color: #16a34a !important; }
.delta-down { color: #2563eb !important; }
.neo-tabs { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 6px 14px rgba(15, 23, 42, .025); display: flex; gap: 8px; margin: 0; padding: 3px; width: 100%; }
.neo-tab-btn { align-items: center; background: transparent; border: 0; border-radius: 8px; color: #64748b; cursor: pointer; display: flex; font-size: 13px; font-weight: 700; gap: 6px; line-height: 1.2; min-height: 38px; padding: 0 18px; }
.neo-tab-btn.active { background: #e8f0ff; box-shadow: inset 0 0 0 1px rgba(51, 112, 255, .08); color: #245bdb; }
.workbench-card { border-radius: 14px; margin: 0; padding: 14px 16px; }
.section-toolbar { align-items: center; display: flex; justify-content: space-between; margin-bottom: 8px; }
.toolbar-head { align-items: baseline; display: inline-flex; flex-wrap: wrap; gap: 8px; }
.toolbar-title, .toolbar-head h4 { font-size: 15px; margin: 0; }
.toolbar-desc, .toolbar-head span { color: #94a3b8; font-size: 12px; }
.workbench-toolbar { align-items: center; background: #f8fafc; border: 1px solid #e5eaf1; border-radius: 10px; display: flex; gap: 8px; margin-bottom: 10px; min-height: 42px; overflow-x: auto; padding: 6px 8px; }
.keyword-input { flex: 1 1 260px; min-width: 220px; }
.filter-select { flex: 0 0 132px; width: 132px; }
.generated-time { color: #94a3b8; font-size: 11px; margin-left: auto; white-space: nowrap; }
.vitals-grid { display: grid; gap: 10px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.vital-card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; }
.vital-head { align-items: center; color: #475569; display: flex; font-size: 12px; justify-content: space-between; }
.vital-card strong { display: block; font-size: 22px; margin: 10px 0 8px; }
.vital-card small { color: #94a3b8; display: block; margin-top: 7px; }
.progress { background: #e2e8f0; border-radius: 4px; height: 5px; overflow: hidden; }
.progress i { background: #22c55e; border-radius: 4px; display: block; height: 100%; }
.progress i.warning { background: #f59e0b; }
.progress i.danger { background: #ef4444; }
.chart-panel { border: 1px solid #e2e8f0; border-radius: 10px; margin-top: 10px; padding: 14px; }
.chart-title { display: flex; font-size: 13px; font-weight: 700; justify-content: space-between; }
.chart-title small { color: #94a3b8; font-weight: 400; }
.bars { align-items: flex-end; display: flex; gap: 10px; height: 150px; padding: 16px 8px 0; }
.bar-group { align-items: flex-end; display: flex; flex: 1; gap: 2px; height: 100%; position: relative; }
.bar { border-radius: 4px 4px 0 0; min-height: 4px; position: relative; width: 50%; }
.bar.sessions { background: #7aa2f7; }
.bar.errors { background: #fca5a5; }
.bar em { display: none; font-size: 10px; font-style: normal; position: absolute; top: -17px; }
.bar-group:hover .bar em { display: block; }
.bar-group > small { bottom: -16px; color: #94a3b8; font-size: 10px; left: 0; position: absolute; }
.legend { color: #64748b; display: flex; font-size: 11px; gap: 14px; margin-top: 22px; }
.dot { border-radius: 50%; display: inline-block; height: 7px; margin-right: 4px; width: 7px; }
.dot.blue { background: #7aa2f7; }
.dot.red { background: #fca5a5; }
.table-title-row { align-items: center; display: flex; justify-content: space-between; margin: 14px 0 7px; }
.app-cell { display: flex; flex-direction: column; gap: 2px; }
.app-cell small, .error-message small { color: #94a3b8; font-size: 11px; }
.metric-good { color: #16a34a; font-weight: 600; }
.metric-warning { color: #d97706; font-weight: 600; }
.metric-danger { color: #dc2626; font-weight: 600; }
.error-message { align-items: center; display: flex; gap: 8px; min-width: 0; }
.error-message > div { display: flex; flex-direction: column; min-width: 0; }
.error-message strong { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.clickable-row) { cursor: pointer; }
.session-detail { display: flex; flex-direction: column; gap: 12px; }
.detail-banner { align-items: center; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; display: flex; justify-content: space-between; padding: 10px 12px; }
.detail-banner > div { display: flex; flex-direction: column; gap: 3px; }
.detail-banner span { color: #64748b; font-size: 12px; }
.detail-grid { display: grid; gap: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.detail-grid > div { border: 1px solid #e2e8f0; border-radius: 9px; display: flex; flex-direction: column; gap: 4px; padding: 9px 10px; }
.detail-grid small, .session-trace span { color: #94a3b8; font-size: 11px; }
.detail-grid strong { font-size: 12px; word-break: break-word; }
.session-trace { align-items: center; background: #f8fafc; border-radius: 8px; display: flex; gap: 9px; padding: 8px 10px; }
.session-trace code { color: #334155; font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
.dialog-actions { display: flex; justify-content: flex-end; }
@media (max-width: 960px) { .audit-grid, .vitals-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .page-inline-desc { display: none; } }
@media (max-width: 640px) { .audit-grid, .vitals-grid, .detail-grid { grid-template-columns: 1fr; } .section-toolbar { align-items: flex-start; flex-direction: column; gap: 8px; } .neo-tabs { overflow-x: auto; } .generated-time { display: none; } }
</style>
