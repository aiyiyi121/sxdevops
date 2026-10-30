<template>
  <section class="capacity-panel" aria-label="集群资源容量">
    <div class="capacity-heading">
      <span title="实际用量与占比按总容量计算。Requests / Limits 按调度口径汇总，Limits 可超过容量。">资源容量</span>
      <span class="capacity-source">{{ loading ? '采集中…' : data?.demo ? '演示数据' : sampledAt ? `采集于 ${sampledAt}` : '等待采集' }}</span>
    </div>
    <div v-if="scoped" class="capacity-notice">当前仅授权指定命名空间，整集群容量不可见。</div>
    <template v-else>
      <div v-if="error" class="capacity-notice is-warning">{{ error }}</div>
      <div class="capacity-table-wrap">
        <table class="capacity-table" aria-label="CPU 与内存容量" :aria-busy="loading">
          <thead><tr><th scope="col">指标</th><th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key" :class="{ 'is-usage': row.key === 'usage' }">
              <th scope="row">{{ row.label }}</th>
              <td v-for="cell in row.cells" :key="cell.key" :title="cell.detail" :class="{ 'is-overcommitted': cell.ratio > 100 }">
                <span>{{ cell.value }}</span>
                <small v-if="cell.ratio !== null && (row.key === 'usage' || cell.ratio > 100)">{{ cell.ratio > 100 ? '超配 ' : '' }}{{ formatPercent(cell.ratio) }}</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="data && !data.metrics?.available" class="capacity-note">实际用量暂不可用{{ data.metrics?.nodes_total ? `（节点采样 ${data.metrics.nodes_covered}/${data.metrics.nodes_total}）` : '' }}，请检查 metrics-server 及采集权限。</p>
      <p v-if="data?.unavailable_resources?.some(item => item !== 'metrics')" class="capacity-note is-warning">部分节点或 Pod 信息暂不可用，请稍后刷新。</p>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
  loading: Boolean,
  scoped: Boolean,
  error: { type: String, default: '' },
})
const columns = [{ key: 'cpu', label: 'CPU' }, { key: 'memory', label: '内存' }]
const labels = { usage: '实际用量', requests: 'Requests', limits: 'Limits', allocatable: '可分配', capacity: '总容量' }
const sampledAt = computed(() => {
  const value = props.data?.collected_at
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('zh-CN', { hour12: false })
})

function formatPercent(value) {
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`
}

function formatValue(value, kind) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (kind === 'cpu') return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 核`
  const unit = value > 0 && value < 2 ** 30 ? 'MiB' : 'GiB'
  return `${(value / (unit === 'MiB' ? 2 ** 20 : 2 ** 30)).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`
}

const rows = computed(() => Object.entries(labels).map(([field, label]) => ({
  key: field,
  label,
  cells: columns.map(({ key, label: resourceLabel }) => {
    const resource = props.data?.resources?.[key] || {}
    const raw = resource[field]
    const ratio = Number.isFinite(raw) && resource.capacity > 0 && ['usage', 'requests', 'limits'].includes(field) ? raw / resource.capacity * 100 : null
    const value = formatValue(raw, key)
    const detailLabel = `${resourceLabel} ${label}`
    return { key, value, ratio, detail: `${detailLabel} ${value}${ratio !== null ? `，占总容量 ${formatPercent(ratio)}` : ''}` }
  }),
})))
</script>

<style scoped>
.capacity-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; color: #334155; font-size: 12px; font-weight: 650; }
.capacity-source { color: #94a3b8; font-size: 11px; font-weight: 400; }
.capacity-table-wrap { overflow: hidden; border: 1px solid #e6ebf3; border-radius: 8px; background: #fff; }
.capacity-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
.capacity-table th, .capacity-table td { padding: 8px 10px; text-align: right; line-height: 1.4; }
.capacity-table th:first-child { width: 78px; color: #64748b; text-align: left; font-weight: 400; }
.capacity-table thead { background: #f8fafc; color: #64748b; }
.capacity-table thead th { font-weight: 500; }
.capacity-table tbody tr + tr { border-top: 1px solid #f0f3f7; }
.capacity-table td { color: #334155; font-weight: 600; }
.capacity-table td > span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.capacity-table small { display: block; color: #94a3b8; font-size: 11px; font-weight: 400; }
.capacity-table .is-usage { background: #f5f9ff; }
.capacity-table .is-usage td { color: #245bdb; }
.capacity-table .is-overcommitted small { color: #b7791f; }
.capacity-note { margin: 6px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.5; }
.capacity-notice { padding: 8px; border-radius: 6px; background: #f1f5fa; color: #64748b; font-size: 12px; line-height: 1.5; }
.is-warning { color: #b7791f; }
@media (max-width: 520px) {
  .capacity-table { font-size: 11px; }
  .capacity-table th, .capacity-table td { padding: 8px 5px; }
  .capacity-table th:first-child { width: 58px; }
}
</style>
