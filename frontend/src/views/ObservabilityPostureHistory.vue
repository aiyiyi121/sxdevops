<template>
  <div class="posture-history-page" :class="{ 'workbench-page-shell': !props.embedded, 'posture-history-page--embedded': props.embedded }">
    <section v-if="!props.embedded" class="hero panel history-hero">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon"><el-icon><TrendCharts /></el-icon></span>
          <h2>系统态势历史</h2>
          <p class="page-inline-desc">以系统态势数据生成 Statuspage 风格历史视图，集中查看近期运行状态、组件可用性和影响事件。</p>
        </div>
      </div>
    </section>

    <div v-if="!props.embedded" class="history-route-tabs">
      <ObservabilityRouteTabs group="posture" />
    </div>

    <div class="status-stage">
      <main v-loading="loading" class="status-wrap">
        <header class="status-topbar">
          <div class="brand">
            <strong>系统态势历史</strong>
          </div>
          <div class="topbar-actions">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              size="small"
              unlink-panels
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              :shortcuts="dateShortcuts"
              class="history-date-picker"
              @change="handleDateRangeChange"
            />
            <button type="button" @click="loadHistory()">刷新</button>
            <button type="button" @click="loadHistory(true)">重算今日</button>
          </div>
        </header>

      <section class="overall">
        <div class="overall-main">
          <div class="overall-title-row">
            <h1 class="overall-title">
              <span class="status-mark status-mark-lg" :class="`is-${overallStatus}`">
                <el-icon><component :is="statusIcon(overallStatus)" /></el-icon>
              </span>
              <span>{{ overallTitle }}</span>
            </h1>
            <el-tooltip
              v-if="overallFailedSystems.length"
              effect="light"
              placement="top"
              popper-class="overall-failed-popper"
              :show-after="120"
            >
              <template #content>
                <div class="overall-failed-tip">
                  <div class="overall-failed-tip__head">
                    <strong>故障系统</strong>
                    <em>{{ overallFailedSystems.length }} 个</em>
                  </div>
                  <div class="overall-failed-tip__list">
                    <div v-for="item in overallFailedSystems" :key="item.key" class="overall-failed-tip__item">
                      <span class="overall-failed-tip__env">{{ item.environment }}</span>
                      <span class="overall-failed-tip__name">{{ item.name }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <span class="overall-failed-inline">故障系统：{{ overallFailedInlineText }}</span>
            </el-tooltip>
          </div>
        </div>
        <div v-if="false" class="overall-side">
          <div class="status-footer status-footer-top">
            <span><i class="is-healthy"></i>健康</span>
            <span><i class="is-critical"></i>故障</span>
            <span><i class="is-unknown"></i>未知</span>
          </div>
        </div>
      </section>

      <section class="system-status">
        <div class="block-title">
          <div class="block-title-main">
            <h2>系统态势</h2>
            <span>{{ systemRows.length }} 个系统</span>
          </div>
          <div class="status-footer status-footer-top">
            <span><i class="is-healthy"></i>{{ statusLabel('healthy') }}</span>
            <span><i class="is-critical"></i>{{ statusLabel('critical') }}</span>
            <span><i class="is-unknown"></i>{{ statusLabel('unknown') }}</span>
          </div>
        </div>

        <section
          v-for="group in environmentGroups"
          :key="group.key"
          class="environment-section"
          :style="{
            '--env-accent': group.theme.accent,
            '--env-tint': group.theme.tint,
          }"
        >
          <div class="environment-head">
            <div class="environment-title">
              <span class="environment-kicker">环境</span>
              <h3>{{ group.name }}</h3>
            </div>
            <div class="environment-meta">
              <span>{{ group.systems.length }} 个系统</span>
              <em>{{ formatSla(group.periodSla) }} 平均可用率</em>
            </div>
          </div>

          <article v-for="system in group.systems" :key="system.id" class="status-row">
            <div class="row-head">
              <div class="row-title-inline">
                <div class="row-title-main">
                  <span class="status-mark" :class="`is-${system.currentStatus}`">
                    <el-icon><component :is="statusIcon(system.currentStatus)" /></el-icon>
                  </span>
                  <strong>{{ system.name }}</strong>
                </div>
                <span v-if="system.domain" class="domain-inline">{{ system.domain }}</span>
              </div>
              <em>{{ formatSla(system.periodSla) }} 平均可用率</em>
            </div>
            <div class="row-bars" :style="barGridStyle">
              <el-tooltip
                v-for="day in system.days"
                :key="`${system.id}-${day.key}`"
                effect="light"
                placement="top"
                popper-class="sla-history-tip"
                :show-after="120"
              >
                <template #content>
                  <div class="sla-tip">
                    <div class="sla-tip__time">{{ day.key }}</div>
                    <div class="sla-tip__headline">
                      <div v-if="day.status !== 'unknown'" class="sla-tip__sla" :class="`is-${day.status}`">{{ formatSla(day.sla) }}</div>
                      <div v-else class="sla-tip__empty">暂无数据</div>
                      <div class="sla-tip__slo">SLO {{ formatSla(system.target) }}</div>
                    </div>
                    <div class="sla-tip__footer">
                      <div class="sla-tip__meta">
                      <span>{{ statusLabel(day.status) }}</span>
                      <span>健康分 {{ day.health_score ?? '--' }}</span>
                      </div>
                      <button
                        v-if="system.id && day.key"
                        type="button"
                        class="sla-tip__action"
                        @click.stop="goToSystemPosture(system, day.key)"
                      >
                        系统态势详情
                      </button>
                    </div>
                  </div>
                </template>
                <span class="day-bar" :class="`is-${day.status}`" />
              </el-tooltip>
            </div>
          </article>
        </section>

        <el-empty v-if="!systemRows.length && !loading" description="暂无 SLA 历史数据" :image-size="72" />
      </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleCheck, QuestionFilled, TrendCharts, WarningFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getObservabilitySystemPostureHistory } from '@/api/modules/ops'
import ObservabilityRouteTabs from '@/components/observability/ObservabilityRouteTabs.vue'

const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
  initialDateRange: {
    type: Array,
    default: () => [],
  },
})
const emit = defineEmits(['range-change'])

const historyDays = 90
const historyUnknownBefore = '2026-04-07'
const router = useRouter()
const loading = ref(false)
const history = ref({ days: [], systems: [], summary: {}, context: {} })
const dateRange = ref(normalizeDateRange(props.initialDateRange))
const dateShortcuts = [
  {
    text: '最近 30 天',
    value: () => [daysAgo(29), new Date()],
  },
  {
    text: '最近 90 天',
    value: () => [daysAgo(89), new Date()],
  },
  {
    text: '最近 180 天',
    value: () => [daysAgo(179), new Date()],
  },
]

const days = computed(() => history.value.days || [])
const barGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${Math.max(1, days.value.length || historyDays)}, minmax(2px, 1fr))`,
}))

const overallStatus = computed(() => {
  if (systemRows.value.some(system => system.days.some(day => day.status === 'critical'))) return 'critical'
  if (systemRows.value.some(system => system.days.some(day => day.status === 'healthy'))) return 'healthy'
  return 'unknown'
})
const overallFailedSystems = computed(() => environmentGroups.value
  .flatMap(group => group.systems)
  .filter(system => system.days.some(day => day.status === 'critical'))
  .map((system) => {
    const environment = system.environment_name || environmentLabel(system.environment)
    return {
      key: `${system.environment || 'default'}-${system.id || system.name}`,
      environment: environment || '默认环境',
      name: system.name || '未命名系统',
      label: `${environment || '默认环境'} / ${system.name || '未命名系统'}`,
    }
  }))
const overallFailedInlineText = computed(() => overallFailedSystems.value.map(item => item.label).join('、'))

const overallTitle = computed(() => {
  if (overallStatus.value === 'critical') return '部分系统存在故障'
  if (overallStatus.value === 'healthy') return '系统运行健康'
  return '暂无可用历史数据'
})

const systemRows = computed(() => (history.value.systems || []).map((system) => {
  const recordMap = new Map((system.records || []).map(record => [record.day, record]))
  const rowDays = days.value.map((day) => {
    const record = recordMap.get(day.key)
    return {
      ...day,
      status: resolveHistoryStatus(record, system.target, day.key),
      sla: record?.sla ?? null,
      health_score: record?.health_score ?? null,
    }
  })
  return {
    ...system,
    currentStatus: latestDayStatus(rowDays),
    days: rowDays,
    periodSla: averageSla(rowDays),
  }
}))

const environmentGroups = computed(() => {
  const groups = new Map()
  systemRows.value.forEach((system) => {
    const key = system.environment || 'default'
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        name: system.environment_name || environmentLabel(key),
        sort_order: Number(system.environment_sort_order ?? 1000),
        theme: environmentTheme(key),
        systems: [],
      })
    }
    groups.get(key).systems.push(system)
  })
  return Array.from(groups.values())
    .map(group => ({
      ...group,
      systems: group.systems.sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hans-CN')),
      periodSla: averageSla(group.systems.flatMap(system => system.days)),
    }))
    .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, 'zh-Hans-CN'))
})

function averageSla(items = []) {
  const values = items
    .filter(item => normalizeStatus(item.status || '') !== 'unknown')
    .map(item => Number(item.sla))
    .filter(value => Number.isFinite(value))
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function normalizeStatus(status = '') {
  return ['healthy', 'critical', 'unknown'].includes(status) ? status : 'unknown'
}

function latestDayStatus(days = []) {
  if (!days.length) return 'unknown'
  return normalizeStatus(days[days.length - 1]?.status)
}

function statusIcon(status = '') {
  return {
    healthy: CircleCheck,
    critical: WarningFilled,
    unknown: QuestionFilled,
  }[normalizeStatus(status)] || QuestionFilled
}

function metricNumber(value) {
  if (value === undefined || value === null || value === '') return null
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

function resolveHistoryStatus(record = null, target = null, dayKey = '') {
  if (dayKey && dayKey < historyUnknownBefore) return 'unknown'
  if (!record) return 'unknown'
  const sla = metricNumber(record.sla)
  const sloTarget = metricNumber(target)
  if (sla === null) return 'unknown'
  if (sloTarget !== null) {
    return sla >= sloTarget ? 'healthy' : 'critical'
  }
  return record.status === 'healthy' ? 'healthy' : record.status === 'unknown' ? 'unknown' : 'critical'
}

function formatSla(value) {
  if (value === null || value === undefined || value === '') return '--'
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return '--'
  return `${numberValue.toFixed(3).replace(/\.?0+$/, '')}%`
}

function statusLabel(status) {
  return {
    healthy: '健康',
    critical: '故障',
    unknown: '未知',
  }[status] || '未知'
}

function environmentLabel(key = '') {
  return {
    prod: '生产环境',
    production: '生产环境',
    staging: '预发环境',
    stage: '预发环境',
    pre: '预发环境',
    test: '测试环境',
    testing: '测试环境',
    dev: '开发环境',
    development: '开发环境',
    default: '默认环境',
  }[String(key || '').toLowerCase()] || key || '默认环境'
}

function environmentTheme(key = '') {
  return {
    prod: { accent: '#2563eb', tint: 'rgba(37, 99, 235, 0.03)' },
    production: { accent: '#2563eb', tint: 'rgba(37, 99, 235, 0.03)' },
    staging: { accent: '#d97706', tint: 'rgba(217, 119, 6, 0.03)' },
    stage: { accent: '#d97706', tint: 'rgba(217, 119, 6, 0.03)' },
    pre: { accent: '#d97706', tint: 'rgba(217, 119, 6, 0.03)' },
    test: { accent: '#7c3aed', tint: 'rgba(124, 58, 237, 0.03)' },
    testing: { accent: '#7c3aed', tint: 'rgba(124, 58, 237, 0.03)' },
    dev: { accent: '#059669', tint: 'rgba(5, 150, 105, 0.03)' },
    development: { accent: '#059669', tint: 'rgba(5, 150, 105, 0.03)' },
    default: { accent: '#64748b', tint: 'rgba(100, 116, 139, 0.025)' },
  }[String(key || '').toLowerCase()] || { accent: '#64748b', tint: 'rgba(100, 116, 139, 0.025)' }
}

function daysAgo(count) {
  const date = new Date()
  date.setHours(0, 0, 0, 0)
  date.setDate(date.getDate() - count)
  return date
}

function defaultDateRange() {
  return [daysAgo(historyDays - 1), new Date()]
}

function normalizeDateRange(range = []) {
  if (Array.isArray(range) && range.length === 2) {
    const [start, end] = range
    const startDate = start instanceof Date ? new Date(start) : new Date(start)
    const endDate = end instanceof Date ? new Date(end) : new Date(end)
    if (!Number.isNaN(startDate.getTime()) && !Number.isNaN(endDate.getTime())) {
      return [startDate, endDate]
    }
  }
  return defaultDateRange()
}

function dateKey(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function rangeDays(range = []) {
  const [start, end] = Array.isArray(range) ? range : []
  if (!(start instanceof Date) || !(end instanceof Date)) return 0
  const startTime = new Date(start)
  const endTime = new Date(end)
  startTime.setHours(0, 0, 0, 0)
  endTime.setHours(0, 0, 0, 0)
  const diff = Math.round((endTime.getTime() - startTime.getTime()) / 86400000)
  return diff >= 0 ? diff + 1 : 0
}

function emitRangeChange() {
  emit('range-change', {
    range: normalizeDateRange(dateRange.value),
    start: dateKey(dateRange.value?.[0]),
    end: dateKey(dateRange.value?.[1]),
    days: rangeDays(dateRange.value),
  })
}

function dayRangeQuery(dayKey = '') {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(dayKey || ''))) return {}
  const start = new Date(`${dayKey}T00:00:00`)
  if (Number.isNaN(start.getTime())) return {}
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return {
    start: start.toISOString(),
    end: end.toISOString(),
  }
}

function goToSystemPosture(system, dayKey = '') {
  if (!system?.id) return
  router.push({
    name: 'ObservabilitySystemPosture',
    query: {
      system: system.id,
      ...dayRangeQuery(dayKey),
    },
  })
}

function historyParams(refresh = false) {
  const [start, end] = Array.isArray(dateRange.value) ? dateRange.value : []
  return {
    days: historyDays,
    start: dateKey(start),
    end: dateKey(end),
    refresh: refresh ? 1 : undefined,
  }
}

function handleDateRangeChange() {
  emitRangeChange()
  loadHistory()
}

async function loadHistory(refresh = false) {
  loading.value = true
  try {
    history.value = await getObservabilitySystemPostureHistory(historyParams(refresh))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  emitRangeChange()
  loadHistory()
})
</script>

<style scoped>
.posture-history-page {
  --ok: #18c964;
  --warn: #f5a524;
  --bad: #f31260;
  --unknown: #c9ced6;
  --text: #11181c;
  --muted: #687076;
  --border: #e6e8eb;
  --panel-subtle: #f6f8fb;
  --panel-tint: #f4f7fb;
  background: transparent;
  color: var(--text);
  display: flex;
  align-items: stretch;
  flex-direction: column;
  gap: 6px;
  min-height: 100%;
  padding: 0;
}

.history-hero,
.history-route-tabs {
  width: 100%;
}

.posture-history-page--embedded {
  min-height: 0;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.hero.panel {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  padding: 14px 16px;
}

.hero,
.hero-copy,
.hero-title-row {
  align-items: center;
  display: flex;
}

.hero {
  justify-content: space-between;
}

.hero-title-row {
  gap: 12px;
  min-width: 0;
}

.hero h2 {
  color: #0f172a;
  font-size: 23px;
  line-height: 1.1;
  margin: 0;
}

.page-inline-desc {
  color: #475569;
  flex: 0 1 auto;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  transform: translateY(1px);
}

.hero-icon {
  align-items: center;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  border: 1px solid rgba(36, 91, 219, 0.12);
  border-radius: 14px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  color: #245bdb;
  display: inline-flex;
  flex: 0 0 42px;
  font-size: 20px;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.status-stage {
  align-items: stretch;
  background: transparent;
  display: flex;
  flex: 1;
  justify-content: center;
  margin-top: 0;
  padding: 0;
  width: 100%;
}

.status-wrap {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 16px 36px rgba(17, 24, 28, 0.05);
  min-width: 0;
  overflow: hidden;
  width: 100%;
}

.status-topbar,
.brand,
.topbar-actions,
.overall,
.block-title,
.row-head,
.status-footer,
.status-footer span {
  align-items: center;
  display: flex;
}

.status-topbar {
  background: linear-gradient(180deg, #f5faf7 0%, #eef5f0 100%);
  border-bottom: 1px solid #dde7e1;
  box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.78);
  justify-content: space-between;
  min-height: 60px;
  padding: 0 22px;
}

.brand {
  gap: 10px;
}

.brand strong {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
}

.topbar-actions {
  gap: 10px;
}

.history-date-picker {
  width: 250px;
}

.history-date-picker :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.94);
  border-radius: 12px;
  box-shadow: 0 0 0 1px #dfe7e2 inset;
}

.topbar-actions button {
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(221, 231, 225, 0.95);
  border-radius: 10px;
  color: #475467;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  min-height: 30px;
  padding: 0 12px;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.topbar-actions button:hover {
  background: #fff;
  border-color: #cfdcd4;
  color: var(--text);
}

.overall {
  align-items: flex-end;
  background: linear-gradient(180deg, var(--panel-tint) 0%, #f7f9fc 100%);
  border-bottom: 1px solid var(--border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
  justify-content: space-between;
  gap: 24px;
  padding: 24px 22px 20px;
}

.overall-main {
  min-width: 0;
}

.overall-title-row {
  align-items: baseline;
  display: flex;
  gap: 12px;
  min-width: 0;
}

.overall-side {
  align-items: flex-end;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.overall h1 {
  font-size: 28px;
  font-weight: 700;
  flex: 0 0 auto;
  color: #0f172a;
  line-height: 1.2;
  margin: 0;
}

.overall-title {
  align-items: center;
  display: flex;
  gap: 12px;
}

.overall-failed-inline {
  color: #8b95a1;
  cursor: default;
  display: block;
  font-size: 12px;
  line-height: 1.4;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.system-status {
  background: #fcfcfd;
  border-bottom: 1px solid var(--border);
  padding: 20px 22px 24px;
}

.block-title {
  border-bottom: 1px solid #edf0f3;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
}

.block-title-main {
  align-items: baseline;
  display: flex;
  gap: 8px;
}

.block-title h2 {
  color: #0f172a;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
}

.block-title span,
.row-head span,
.row-head em,
.status-footer span {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
}

.row-bars {
  background: #f8fafc;
  border: 1px solid #eef2f6;
  border-radius: 12px;
  display: grid;
  gap: 3px;
  padding: 8px;
}

.day-bar {
  background: var(--unknown);
  border-radius: 999px;
  height: 24px;
  min-width: 2px;
}

.day-bar.is-healthy,
.status-footer i.is-healthy {
  background: var(--ok);
}

.day-bar.is-critical,
.status-footer i.is-critical {
  background: var(--bad);
}

.day-bar.is-unknown,
.status-footer i.is-unknown {
  background: var(--unknown);
}

.status-row {
  border-top: 1px solid var(--border);
  padding: 14px 0;
}

.environment-section {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, var(--env-tint) 100%);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 14px;
  margin-bottom: 12px;
  overflow: hidden;
  padding: 14px 14px 10px;
}

.environment-section:first-of-type {
  margin-top: 2px;
}

.environment-head {
  align-items: baseline;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  margin-bottom: 2px;
  padding-bottom: 10px;
  gap: 12px;
}

.environment-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
}

.environment-kicker {
  color: #8b95a1;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
}

.environment-head h3 {
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
}

.environment-meta {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.environment-meta span,
.environment-meta em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
}

.environment-section .status-row:first-of-type {
  border-top: 0;
  padding-top: 14px;
}

.status-row:last-child {
  padding-bottom: 0;
}

.row-head {
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.row-title-inline {
  align-items: center;
  display: flex;
  flex: 1 1 auto;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.row-title-main {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.row-head strong {
  display: block;
  color: #111827;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.2;
  margin-bottom: 0;
  margin-right: 0;
}

.row-head em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
  white-space: nowrap;
}

.domain-inline {
  color: #8b95a1;
  font-size: 12px;
  line-height: 1.2;
}

.status-mark {
  align-items: center;
  background: #f3f4f6;
  border-radius: 999px;
  color: #98a2b3;
  display: inline-flex;
  flex: 0 0 auto;
  height: 18px;
  justify-content: center;
  width: 18px;
}

.status-mark :deep(svg) {
  display: block;
  height: 12px;
  width: 12px;
}

.status-mark.is-healthy {
  background: rgba(24, 201, 100, 0.12);
  color: #16a34a;
}

.status-mark.is-critical {
  background: rgba(243, 18, 96, 0.12);
  color: #e11d48;
}

.status-mark.is-unknown {
  background: rgba(148, 163, 184, 0.14);
  color: #94a3b8;
}

.status-mark-lg {
  height: 26px;
  width: 26px;
}

.status-mark-lg :deep(svg) {
  height: 15px;
  width: 15px;
}

.status-footer {
  flex-wrap: wrap;
  gap: 14px;
  padding: 0;
}

.status-footer-top {
  justify-content: flex-end;
}

.status-footer span {
  gap: 6px;
}

.status-footer i {
  border-radius: 999px;
  display: inline-block;
  height: 8px;
  width: 18px;
}

:global(.overall-failed-popper) {
  border: 1px solid #dfe3ea !important;
  border-radius: 14px !important;
  box-shadow: 0 16px 36px rgba(17, 24, 39, 0.12) !important;
  padding: 0 !important;
}

:global(.overall-failed-popper .el-popper__arrow::before) {
  border-color: #dfe3ea !important;
}

.overall-failed-tip {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 360px;
  min-width: 260px;
  padding: 14px;
}

.overall-failed-tip__head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.overall-failed-tip__head strong {
  color: #111827;
  font-size: 12px;
  line-height: 1.2;
}

.overall-failed-tip__head em {
  color: #8b95a1;
  font-size: 12px;
  font-style: normal;
  line-height: 1.2;
}

.overall-failed-tip__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.overall-failed-tip__item {
  align-items: center;
  background: #f8fafc;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 10px;
  display: flex;
  gap: 8px;
  padding: 8px 10px;
}

.overall-failed-tip__env {
  background: #eef2ff;
  border-radius: 999px;
  color: #667085;
  font-size: 12px;
  flex: 0 0 auto;
  line-height: 1;
  padding: 4px 8px;
}

.overall-failed-tip__name {
  color: #111827;
  font-size: 12px;
  line-height: 1.4;
  min-width: 0;
  word-break: break-word;
}

@media (max-width: 720px) {
  .posture-history-page {
    padding: 0;
  }

  .hero-title-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .status-stage {
    padding: 0;
  }

  .status-wrap {
    border-left: 0;
    border-radius: 0;
    border-right: 0;
  }

  .status-topbar,
  .block-title,
  .row-head,
  .environment-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .topbar-actions {
    align-items: flex-start;
    flex-direction: column;
    padding-bottom: 12px;
    width: 100%;
  }

  .history-date-picker {
    width: 100%;
  }

  .overall {
    align-items: flex-start;
    flex-direction: column;
    padding: 20px 16px 18px;
  }

  .overall-side {
    align-items: flex-start;
  }

  .block-title-main {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .system-status {
    padding: 18px 16px;
  }

  .overall h1 {
    font-size: 24px;
  }

  .overall-title-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }

  .overall-failed-inline {
    max-width: none;
  }

  .row-bars {
    gap: 2px;
  }

  .environment-meta {
    align-items: flex-start;
    justify-content: flex-start;
  }

  .environment-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .row-title-inline {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .status-footer-top {
    justify-content: flex-start;
  }
}

:global(.sla-history-tip) {
  border: 1px solid #dfe3ea !important;
  border-radius: 18px !important;
  box-shadow: 0 18px 45px rgba(17, 24, 39, 0.15) !important;
  padding: 0 !important;
}

:global(.sla-history-tip .el-popper__arrow::before) {
  border-color: #dfe3ea !important;
}

.sla-tip {
  min-width: 236px;
  padding: 14px 16px 13px;
  text-align: left;
}

.sla-tip__time {
  color: #667085;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  margin-bottom: 6px;
}

.sla-tip__headline {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 8px;
}

.sla-tip__sla {
  font-size: 22px;
  font-weight: 800;
  line-height: 1.1;
  margin-bottom: 0;
}

.sla-tip__sla.is-healthy {
  color: #20bf63;
}

.sla-tip__sla.is-critical {
  color: #e11d48;
}

.sla-tip__sla.is-unknown {
  color: #94a3b8;
}

.sla-tip__empty {
  color: #94a3b8;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 0;
}

.sla-tip__slo {
  color: #667085;
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.sla-tip__footer {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
}

.sla-tip__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sla-tip__meta span {
  background: #f3f4f6;
  border-radius: 999px;
  color: #98a2b3;
  font-size: 11px;
  line-height: 1;
  padding: 4px 7px;
}

.sla-tip__action {
  background: #f3f6fb;
  border: 1px solid #d7dee8;
  border-radius: 999px;
  color: #475467;
  cursor: pointer;
  font-size: 11px;
  flex: 0 0 auto;
  font-weight: 600;
  line-height: 1;
  min-height: 26px;
  padding: 0 9px;
  white-space: nowrap;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.sla-tip__action:hover {
  background: #ffffff;
  border-color: #c7d2df;
  color: #111827;
}
</style>
