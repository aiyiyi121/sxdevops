<template>
  <div class="metrics-page workbench-page-shell">
    <section class="hero panel hero-panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="release-header-icon"><el-icon><DataAnalysis /></el-icon></span>
          <h2>{{ activeTab === 'datasources' ? '指标数据源' : '指标查询' }}</h2>
          <p class="page-inline-desc inline-subtitle">{{ activeTab === 'datasources' ? '统一维护 Prometheus 兼容指标数据源配置' : 'PromQL 区间查询与指标检索入口' }}</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" @click="loadDataSources" :loading="loadingSources">
          <el-icon><RefreshRight /></el-icon>
          刷新数据源
        </el-button>
      </div>
    </section>

    <ObservabilityRouteTabs v-if="activeTab === 'datasources'" group="datasources" />

    <section v-if="activeTab === 'query'" class="metric-query-workbench workbench-fill-panel">
      <div class="query-console">
        <section class="panel metric-query-unified-card metric-query-left-card">
      <div class="metric-query-unified-head">
        <div class="metric-query-title-block">
          <div class="metric-query-title-row">
            <h3>PromQL 查询</h3>
            <span>优先使用选中的指标数据源，按时间范围执行 PromQL 区间查询。</span>
          </div>
        </div>
        <div class="metric-query-actions">
          <el-button size="small" type="primary" class="search-action-primary" :loading="queryLoading" :disabled="!canQuery" @click="runQuery">
            <el-icon><CaretRight /></el-icon>
            执行查询
          </el-button>
        </div>
      </div>

      <div class="metric-query-provider-strip">
        <div class="metric-filter-datasource-row">
          <span class="metric-query-provider-label">数据源</span>
          <el-select
            v-model="queryForm.metric_datasource_id"
            class="search-control metric-datasource-control"
            size="small"
            clearable
            filterable
            placeholder="请选择指标数据源"
          >
            <el-option v-for="item in dataSources" :key="item.id" :label="sourceOptionLabel(item)" :value="item.id" />
          </el-select>
        </div>
      </div>

      <div class="search-panel search-panel--merged metric-search-panel">
        <div class="metric-filter-grid">
          <div class="metric-inline-filter metric-inline-filter--time">
            <span class="metric-inline-filter__label">时间</span>
            <el-date-picker
              v-model="queryForm.timeRange"
              class="search-control metric-time-control"
              size="small"
              type="datetimerange"
              format="YYYY-MM-DD HH:mm:ss"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              :shortcuts="timeShortcuts"
            />
            <div class="metric-filter-pills">
              <span class="query-pill">时间：{{ formatTimeRangeSummary(queryForm.timeRange) }}</span>
              <span class="query-pill">步长：自动 {{ autoQueryStep }}s</span>
            </div>
          </div>
        </div>
      </div>

          <div class="query-editor promql-search-panel">
            <div class="promql-field-head">
              <span class="promql-field-label">PromQL</span>
              <div class="promql-editor-shell">
                <el-input
                  ref="promqlInputRef"
                  v-model="queryForm.promql"
                  class="promql-textarea"
                  placeholder='例如：up 或 sum(rate(http_requests_total[5m])) by (service)'
                  @input="handlePromqlInput"
                  @focus="openPromqlSuggestions"
                  @click="refreshPromqlSuggestions"
                  @keyup="handlePromqlKeyup"
                  @keydown="handlePromqlKeydown"
                  @blur="scheduleClosePromqlSuggestions"
                />
                <div v-if="shouldShowPromqlSuggestions" class="promql-suggest-popover" @mousedown.prevent>
                  <div class="promql-suggest-head">
                    <span>{{ promqlSuggestTitle }}</span>
                    <small>{{ promqlSuggestHint }}</small>
                  </div>
                  <div v-if="promqlMetricLoading && !visiblePromqlSuggestions.length" class="promql-suggest-state">
                    正在从当前数据源加载指标候选...
                  </div>
                  <div v-else-if="!visiblePromqlSuggestions.length" class="promql-suggest-state">
                    {{ promqlMetricError ? '真实指标暂不可用，已切换本地候选。' : '暂无匹配候选。' }}
                  </div>
                  <div v-else class="promql-suggest-list">
                    <button
                      v-for="(item, index) in visiblePromqlSuggestions"
                      :key="item.id"
                      type="button"
                      class="promql-suggest-item"
                      :class="[{ active: promqlSuggestIndex >= 0 && index === promqlSuggestIndex }, `is-${item.type}`]"
                      @mouseenter="promqlSuggestIndex = index"
                      @mousedown.prevent="applyPromqlSuggestion(item)"
                    >
                      <span class="promql-suggest-badge">{{ item.badge }}</span>
                      <span class="promql-suggest-main">
                        <span v-if="item.detail" class="promql-suggest-detail">{{ item.detail }}</span>
                        <strong>
                          <template v-for="(part, partIndex) in highlightedSuggestionLabel(item.label)" :key="`${item.id}-${partIndex}`">
                            <span :class="{ 'is-match': part.hit }">{{ part.text }}</span>
                          </template>
                        </strong>
                      </span>
                      <code class="promql-suggest-example">{{ item.preview }}</code>
                    </button>
                  </div>
                </div>
              </div>
              <div class="editor-actions">
                <el-tooltip content="复制 PromQL" placement="top" :show-after="500">
                  <el-button class="icon-action-btn" size="small" circle @click="copyPromql(queryForm.promql)">
                    <el-icon><CopyDocument /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </div>
            <div v-if="promqlInlineSuggestVisible" class="promql-inline-suggest-panel">
              <div class="promql-inline-suggest-head">
                <span>{{ promqlInlineSuggestTitle }}</span>
                <small>{{ promqlInlineSuggestHint }}</small>
              </div>
              <div v-if="promqlMetricLoading && !promqlInlineSuggestions.length" class="promql-inline-suggest-state">
                正在从当前数据源加载指标候选...
              </div>
              <div v-else-if="!promqlInlineSuggestions.length" class="promql-inline-suggest-state">
                {{ promqlMetricError ? '真实指标暂不可用，已切换本地候选。' : '暂无匹配候选。' }}
              </div>
              <div v-else class="promql-inline-suggest-list">
                <button
                  v-for="(item, index) in promqlInlineSuggestions"
                  :key="`inline-${item.id}`"
                  type="button"
                  class="promql-inline-suggest-item"
                  :class="{ active: promqlSuggestIndex >= 0 && index === promqlSuggestIndex }"
                  @mousedown.prevent="applyInlinePromqlSuggestion(item)"
                >
                  <span class="promql-suggest-badge">{{ item.badge }}</span>
                  <span class="promql-suggest-main">
                    <span v-if="item.detail" class="promql-suggest-detail">{{ item.detail }}</span>
                    <strong>
                      <template v-for="(part, partIndex) in highlightedSuggestionLabel(item.label, promqlInlineContext)" :key="`${item.id}-inline-${partIndex}`">
                        <span :class="{ 'is-match': part.hit }">{{ part.text }}</span>
                      </template>
                    </strong>
                  </span>
                  <code class="promql-suggest-example">{{ item.preview }}</code>
                </button>
              </div>
            </div>
          </div>
        </section>

        <aside class="panel quick-promql-panel">
          <div class="quick-panel-head">
            <div class="quick-panel-title">
              <el-icon><CollectionTag /></el-icon>
              <span>常用 PromQL</span>
            </div>
            <span class="quick-panel-count">{{ visibleQuickTemplates.length }} 条</span>
          </div>
          <el-input v-model.trim="quickSearch" clearable placeholder="筛选场景 / 指标 / PromQL" class="quick-search">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <div class="quick-category-tabs">
            <button
              v-for="category in quickCategories"
              :key="category.value"
              type="button"
              class="quick-category-tab"
              :class="{ active: activeQuickCategory === category.value }"
              @click="activeQuickCategory = category.value"
            >
              <span>{{ category.label }}</span>
              <small>{{ quickCategoryCount(category.value) }}</small>
            </button>
          </div>
          <div class="quick-promql-list">
            <div
              v-for="item in visibleQuickTemplates"
              :key="item.id"
              class="quick-promql-card"
              :class="{ active: selectedQuickId === item.id }"
              @click="fillPromql(item)"
            >
              <div class="quick-card-top">
                <span class="quick-card-title">{{ item.title }}</span>
                <el-tag size="small" effect="plain">{{ item.kind }}</el-tag>
              </div>
              <p>{{ item.summary }}</p>
              <code>{{ item.expression }}</code>
            </div>
            <el-empty v-if="!visibleQuickTemplates.length" description="暂无匹配模板" :image-size="72" />
          </div>
        </aside>
      </div>

      <section class="panel metric-result-card workbench-fill-panel">
        <div class="metric-result-head">
          <div class="metric-result-title-block">
            <span class="metric-result-title">Graph</span>
            <span class="metric-result-desc">上方时序趋势，下方按 Prometheus labels 展示序列。</span>
          </div>
          <div class="result-strip">
            <span class="query-pill">来源：{{ lastResultSource }}</span>
            <span class="query-pill">类型：{{ lastResult.resultType || '--' }}</span>
            <span class="query-pill">序列：{{ lastResult.series_count ?? metricSeriesRows.length }}</span>
            <span class="query-pill">步长：自动 {{ lastResult.step || autoQueryStep }}s</span>
            <span class="query-pill" :class="{ 'query-pill--danger': lastQueryFailed, 'query-pill--success': hasQuerySnapshot && !lastQueryFailed }">
              状态：{{ queryStatusText }}
            </span>
            <span class="query-pill">耗时：{{ lastQueryDuration ? `${lastQueryDuration}ms` : '--' }}</span>
          </div>
        </div>

        <el-alert v-if="queryError" :title="queryError" type="error" show-icon :closable="false" />
        <div v-else class="metric-graph-shell" v-loading="queryLoading">
          <div v-if="!metricSeriesRows.length && !queryLoading" class="metric-graph-empty">
            <el-empty description="暂无查询结果，输入 PromQL 后执行。" />
          </div>
          <template v-else>
            <div class="metric-graph-toolbar">
              <span class="metric-graph-label">Time series</span>
              <span v-if="selectedMetricSeries" class="metric-graph-limit">
                已聚焦 1 条，点击同一 Metrics 行恢复全部
              </span>
              <span v-else-if="metricSeriesRows.length > METRIC_CHART_SERIES_LIMIT" class="metric-graph-limit">
                仅展示前 {{ METRIC_CHART_SERIES_LIMIT }} 条，总 {{ metricSeriesRows.length }} 条
              </span>
            </div>
            <div ref="metricChartRef" class="metric-timeseries-chart"></div>
            <div class="metric-series-board">
              <div class="metric-series-head">
                <span>Metrics</span>
                <small>{{ metricSeriesCountText }}</small>
              </div>
              <div class="metric-series-list">
                <button
                  v-for="item in visibleMetricSeriesRows"
                  :key="item.id"
                  type="button"
                  class="metric-series-row"
                  :class="{ active: selectedMetricSeriesId === item.id }"
                  @click="toggleMetricSeries(item)"
                >
                  <span class="metric-series-color" :style="{ backgroundColor: item.color }"></span>
                  <code class="metric-series-label">{{ item.label }}</code>
                  <span class="metric-series-value">{{ item.latestValue }}</span>
                </button>
              </div>
            </div>
          </template>
        </div>

      </section>
    </section>

    <section v-else class="panel workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">指标数据源</span>
          <span class="toolbar-desc">统一维护 Prometheus 兼容指标数据源配置，供查询页直接复用。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageDatasource" type="primary" @click="openDatasourceDialog()">
            <el-icon><Plus /></el-icon>
            新增数据源
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history">
        <div class="workbench-toolbar-left">
          <el-input v-model.trim="filters.keyword" class="search-control" size="small" clearable placeholder="搜索名称 / 地址" style="width: 260px" />
          <el-select v-model="filters.enabled" class="search-control" size="small" clearable placeholder="状态" style="width: 110px">
            <el-option label="启用" value="true" />
            <el-option label="停用" value="false" />
          </el-select>
        </div>
        <div class="workbench-toolbar-right">
          <span class="toolbar-count">共 {{ filteredDataSources.length }} 个</span>
        </div>
      </div>

      <el-table v-loading="loadingSources" :data="filteredDataSources" stripe>
        <el-table-column label="名称" min-width="210">
          <template #default="{ row }">
            <div class="source-name">{{ row.name }}</div>
            <div class="source-desc">{{ row.description || endpointOf(row) || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">{{ row.provider_display || row.provider }}</template>
        </el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
            <el-tag v-if="row.is_default" size="small" type="warning" class="ml-6">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canManageDatasource" label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="testSource(row)">测试</el-button>
            <el-button link type="primary" size="small" @click="openDatasourceDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeSource(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="dialog.visible" :title="dialog.editingId ? '编辑指标数据源' : '新增指标数据源'" width="720px" append-to-body destroy-on-close>
      <el-form class="workbench-editor-form--sectioned" label-position="top" ref="sourceFormRef" :model="sourceForm" :rules="sourceRules" label-width="124px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>数据源信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="名称" prop="name">
              <el-input v-model.trim="sourceForm.name" placeholder="例如：电商测试 Prometheus" />
            </el-form-item>
            <el-form-item label="查询地址" prop="query_url">
              <el-input v-model.trim="sourceForm.query_url" placeholder="http://prometheus:9090" />
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>认证与连接设置</h3></div>
          <div>
            <el-form-item label="认证方式">
              <el-select v-model="sourceForm.auth_type" style="width: 180px">
                <el-option label="无认证" value="none" />
                <el-option label="Basic" value="basic" />
                <el-option label="Bearer Token" value="bearer" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="sourceForm.auth_type === 'basic'" label="Basic 账号">
              <div class="inline-fields">
                <el-input v-model.trim="sourceForm.username" placeholder="用户名" />
                <el-input v-model="sourceForm.password" type="password" show-password placeholder="密码；已配置可留 configured" />
              </div>
            </el-form-item>
            <el-form-item v-if="sourceForm.auth_type === 'bearer'" label="Bearer Token">
              <el-input v-model="sourceForm.bearer_token" type="password" show-password placeholder="已配置可保留 configured" />
            </el-form-item>
            <el-form-item label="连接设置">
              <div class="inline-fields inline-fields--small">
                <el-checkbox v-model="sourceForm.tls_skip_verify">跳过 TLS 校验</el-checkbox>
                <el-checkbox v-model="sourceForm.is_default">设为默认</el-checkbox>
                <el-switch v-model="sourceForm.is_enabled" inline-prompt active-text="启用" inactive-text="停用" />
              </div>
            </el-form-item>
            <el-form-item class="workbench-editor-full" label="描述">
              <el-input v-model.trim="sourceForm.description" maxlength="255" show-word-limit />
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="savingSource" @click="submitDatasource">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight, CollectionTag, CopyDocument, DataAnalysis, DataBoard, Plus, RefreshRight, Search } from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import ObservabilityRouteTabs from '@/components/observability/ObservabilityRouteTabs.vue'
import { useAuthStore } from '@/stores/auth'
import {
  createMetricDataSource,
  deleteMetricDataSource,
  getMetricDataSources,
  getMetricSeriesNames,
  queryMetrics,
  testMetricDataSource,
  updateMetricDataSource,
} from '@/api/modules/ops'

const route = useRoute()
const authStore = useAuthStore()
const canQuery = computed(() => authStore.hasPermission('ops.metric.query'))
const canManageDatasource = computed(() => authStore.hasPermission('ops.metric.datasource.manage'))
const activeTab = ref(route.query.tab === 'datasources' ? 'datasources' : 'query')
const loadingSources = ref(false)
const queryLoading = ref(false)
const savingSource = ref(false)
const dataSources = ref([])
const lastResult = ref({})
const queryError = ref('')
const lastQueryDuration = ref(0)
const lastQueryFailed = ref(false)
const sourceFormRef = ref(null)
const quickSearch = ref('')
const activeQuickCategory = ref('all')
const selectedQuickId = ref('')
const selectedMetricSeriesId = ref('')
const promqlInputRef = ref(null)
const metricChartRef = ref(null)
const promqlSuggestVisible = ref(false)
const promqlSuggestIndex = ref(-1)
const promqlSuggestContext = ref(createPromqlContext())
const promqlRemoteMetrics = ref([])
const promqlMetricLoading = ref(false)
const promqlMetricError = ref('')
const promqlMetricLoadedKey = ref('')
const promqlSuggestFocused = ref(false)
let promqlSuggestCloseTimer = null
let promqlMetricFetchTimer = null
let promqlMetricFetchSeq = 0
let metricChart = null

const METRIC_CHART_SERIES_LIMIT = 20
const METRIC_SERIES_COLORS = [
  '#73bf69',
  '#5794f2',
  '#f2cc0c',
  '#ff9830',
  '#e02f44',
  '#b877d9',
  '#56a64b',
  '#8ab8ff',
  '#ffcb7d',
  '#f2495c',
  '#c15c17',
  '#6ed0e0',
  '#705da0',
  '#99d98c',
  '#fce2a1',
  '#ff7383',
  '#33a2a2',
  '#ca95e5',
  '#a352cc',
  '#37872d',
]

const now = Date.now()
const queryForm = reactive({
  metric_datasource_id: '',
  promql: '',
  timeRange: [new Date(now - 30 * 60 * 1000), new Date(now)],
})
const filters = reactive({ keyword: '', enabled: '' })
const dialog = reactive({ visible: false, editingId: null })
const sourceForm = reactive({
  name: '',
  provider: 'prometheus',
  description: '',
  query_url: '',
  auth_type: 'none',
  username: '',
  password: '',
  bearer_token: '',
  timeout: 6,
  tls_skip_verify: true,
  is_enabled: true,
  is_default: false,
})
const sourceRules = {
  name: [{ required: true, message: '请填写数据源名称', trigger: 'blur' }],
  query_url: [{ required: true, message: '请填写 Prometheus 查询地址', trigger: 'blur' }],
}
const timeShortcuts = [
  { text: '最近 5 分钟', value: () => [new Date(Date.now() - 5 * 60 * 1000), new Date()] },
  { text: '最近 15 分钟', value: () => [new Date(Date.now() - 15 * 60 * 1000), new Date()] },
  { text: '最近 30 分钟', value: () => [new Date(Date.now() - 30 * 60 * 1000), new Date()] },
  { text: '最近 1 小时', value: () => [new Date(Date.now() - 60 * 60 * 1000), new Date()] },
  { text: '最近 3 小时', value: () => [new Date(Date.now() - 3 * 60 * 60 * 1000), new Date()] },
  { text: '最近 6 小时', value: () => [new Date(Date.now() - 6 * 60 * 60 * 1000), new Date()] },
  { text: '最近 12 小时', value: () => [new Date(Date.now() - 12 * 60 * 60 * 1000), new Date()] },
  { text: '最近 24 小时', value: () => [new Date(Date.now() - 24 * 60 * 60 * 1000), new Date()] },
  { text: '最近 7 天', value: () => [new Date(Date.now() - 7 * 24 * 60 * 60 * 1000), new Date()] },
]
const quickCategories = [
  { value: 'all', label: '全部' },
  { value: 'service', label: '应用' },
  { value: 'node', label: '主机' },
  { value: 'k8s', label: 'K8s' },
  { value: 'container', label: '容器' },
  { value: 'middleware', label: '中间件' },
]
const quickTemplates = [
  {
    id: 'service-qps',
    category: 'service',
    kind: 'QPS',
    title: '应用请求速率',
    summary: '按 service 观察 5 分钟窗口内的请求吞吐。',
    expression: 'sum(rate(http_requests_total[5m])) by (service)',
    tags: ['qps', '请求量', '吞吐', 'http', 'service', '接口'],
  },
  {
    id: 'service-error-rate',
    category: 'service',
    kind: '错误率',
    title: 'HTTP 5xx 错误率',
    summary: '按 service 计算 5xx 在总请求中的占比。',
    expression: 'sum(rate(http_requests_total{status=~"5.."}[5m])) by (service) / sum(rate(http_requests_total[5m])) by (service)',
    tags: ['错误率', '5xx', 'error', '异常', 'http', 'service'],
  },
  {
    id: 'service-p95',
    category: 'service',
    kind: '延迟',
    title: '接口 P95 延迟',
    summary: '从 histogram bucket 推导服务维度 P95 响应时间。',
    expression: 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))',
    tags: ['p95', '延迟', '耗时', 'latency', 'duration', '接口'],
  },
  {
    id: 'service-availability',
    category: 'service',
    kind: 'SLO',
    title: '入口可用率',
    summary: '用非 5xx 请求占比快速衡量服务可用性。',
    expression: '1 - (sum(rate(http_requests_total{status=~"5.."}[5m])) by (service) / sum(rate(http_requests_total[5m])) by (service))',
    tags: ['可用率', '成功率', 'sla', 'slo', '入口', 'apdex'],
  },
  {
    id: 'node-up',
    category: 'node',
    kind: '存活',
    title: '采集目标在线状态',
    summary: 'Prometheus up 指标，适合先验证数据源与 target 状态。',
    expression: 'up',
    tags: ['up', '在线', 'target', '探活', '连通', '健康'],
  },
  {
    id: 'node-cpu',
    category: 'node',
    kind: 'CPU',
    title: '主机 CPU 使用率',
    summary: '按实例聚合非 idle CPU 占比。',
    expression: '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance) * 100',
    tags: ['cpu', '主机', '节点', 'node', '使用率', 'idle'],
  },
  {
    id: 'node-memory',
    category: 'node',
    kind: '内存',
    title: '主机内存使用率',
    summary: '按实例计算可用内存之外的使用比例。',
    expression: '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
    tags: ['内存', 'memory', '主机', '节点', 'node', 'mem'],
  },
  {
    id: 'node-disk',
    category: 'node',
    kind: '磁盘',
    title: '磁盘空间使用率',
    summary: '排除伪文件系统，查看各挂载点空间占用。',
    expression: '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|fuse.lxcfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|fuse.lxcfs|overlay"}) * 100',
    tags: ['磁盘', 'disk', 'filesystem', '挂载点', '空间', '容量'],
  },
  {
    id: 'node-network',
    category: 'node',
    kind: '网络',
    title: '主机网络接收速率',
    summary: '按实例聚合网卡接收带宽，单位 bit/s。',
    expression: 'sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*"}[5m])) by (instance) * 8',
    tags: ['网络', 'network', '流量', '带宽', 'receive', '入口'],
  },
  {
    id: 'k8s-pod-restart',
    category: 'k8s',
    kind: 'Pod',
    title: 'Pod 重启次数',
    summary: '按命名空间和 Pod 统计 10 分钟内重启增量。',
    expression: 'sum(increase(kube_pod_container_status_restarts_total[10m])) by (namespace, pod)',
    tags: ['pod', '重启', 'restart', 'k8s', 'kubernetes', '容器'],
  },
  {
    id: 'k8s-pod-not-ready',
    category: 'k8s',
    kind: 'Pod',
    title: 'Pod 未就绪',
    summary: '筛出 ready 条件不为 true 的 Pod。',
    expression: 'sum(kube_pod_status_ready{condition!="true"}) by (namespace, pod)',
    tags: ['pod', 'ready', 'notready', '未就绪', 'k8s', '异常'],
  },
  {
    id: 'k8s-workload-available',
    category: 'k8s',
    kind: '工作负载',
    title: 'Deployment 可用副本',
    summary: '对比 Deployment 期望副本与可用副本。',
    expression: 'kube_deployment_spec_replicas - kube_deployment_status_replicas_available',
    tags: ['deployment', '副本', 'replica', '可用', 'workload', 'k8s'],
  },
  {
    id: 'container-cpu',
    category: 'container',
    kind: 'CPU',
    title: '容器 CPU 使用率',
    summary: '按 namespace、pod 和 container 聚合容器 CPU。',
    expression: 'sum(rate(container_cpu_usage_seconds_total{image!="", image!~".*pause.*"}[5m])) by (namespace, pod, container) * 100',
    tags: ['容器', 'container', 'cpu', 'pod', 'cadvisor', '使用率'],
  },
  {
    id: 'container-memory',
    category: 'container',
    kind: '内存',
    title: '容器内存使用率',
    summary: '以 limit 为分母计算容器工作集内存占比。',
    expression: 'sum(container_memory_working_set_bytes{image!="", image!~".*pause.*"}) by (namespace, pod, container) / sum(container_spec_memory_limit_bytes{image!="", image!~".*pause.*"}) by (namespace, pod, container) * 100',
    tags: ['容器', 'container', '内存', 'memory', 'working_set', 'limit'],
  },
  {
    id: 'container-throttle',
    category: 'container',
    kind: 'CPU',
    title: '容器 CPU Throttle 比例',
    summary: '观察容器是否被 CPU CFS quota 抑制。',
    expression: 'sum(rate(container_cpu_cfs_throttled_periods_total[5m])) by (namespace, pod, container) / sum(rate(container_cpu_cfs_periods_total[5m])) by (namespace, pod, container) * 100',
    tags: ['throttle', '限流', 'cpu', 'cfs', '容器', '抑制'],
  },
  {
    id: 'redis-memory',
    category: 'middleware',
    kind: 'Redis',
    title: 'Redis 内存使用率',
    summary: '基于 exporter 的 used/max 指标估算内存水位。',
    expression: 'redis_memory_max_bytes > 0 and (redis_memory_used_bytes / redis_memory_max_bytes) * 100',
    tags: ['redis', '内存', 'memory', '缓存', '水位', 'maxmemory'],
  },
  {
    id: 'redis-hit-rate',
    category: 'middleware',
    kind: 'Redis',
    title: 'Redis 命中率',
    summary: '用 keyspace hits/misses 计算缓存命中率。',
    expression: 'rate(redis_keyspace_hits_total[5m]) / (rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]))',
    tags: ['redis', '命中率', 'hit', 'miss', '缓存', 'keyspace'],
  },
  {
    id: 'mysql-qps',
    category: 'middleware',
    kind: 'MySQL',
    title: 'MySQL QPS',
    summary: 'Categraf MySQL 全局查询速率。',
    expression: 'irate(mysql_global_status_queries[3m])',
    tags: ['mysql', 'qps', 'query', '数据库', '查询', '慢查询'],
  },
]

const PROMQL_FUNCTION_SUGGESTIONS = [
  { label: 'rate', insert: 'rate(|[5m])', detail: 'Counter 每秒速率，常用于 QPS / 流量', preview: 'rate(metric[5m])' },
  { label: 'irate', insert: 'irate(|[3m])', detail: 'Counter 瞬时速率，适合突刺观察', preview: 'irate(metric[3m])' },
  { label: 'increase', insert: 'increase(|[10m])', detail: '窗口内增量，常用于重启次数', preview: 'increase(metric[10m])' },
  { label: 'histogram_quantile', insert: 'histogram_quantile(0.95, |)', detail: 'Histogram 分位数，常用于 P95/P99', preview: 'histogram_quantile(0.95, ...)' },
  { label: 'avg_over_time', insert: 'avg_over_time(|[5m])', detail: '区间平均值', preview: 'avg_over_time(metric[5m])' },
  { label: 'max_over_time', insert: 'max_over_time(|[5m])', detail: '区间最大值', preview: 'max_over_time(metric[5m])' },
  { label: 'min_over_time', insert: 'min_over_time(|[5m])', detail: '区间最小值', preview: 'min_over_time(metric[5m])' },
  { label: 'sum_over_time', insert: 'sum_over_time(|[5m])', detail: '区间求和', preview: 'sum_over_time(metric[5m])' },
  { label: 'count_over_time', insert: 'count_over_time(|[5m])', detail: '区间样本数量', preview: 'count_over_time(metric[5m])' },
  { label: 'changes', insert: 'changes(|[5m])', detail: '区间内值变化次数', preview: 'changes(metric[5m])' },
  { label: 'resets', insert: 'resets(|[5m])', detail: 'Counter 重置次数', preview: 'resets(metric[5m])' },
  { label: 'delta', insert: 'delta(|[5m])', detail: 'Gauge 区间差值', preview: 'delta(metric[5m])' },
  { label: 'predict_linear', insert: 'predict_linear(|[1h], 3600)', detail: '线性预测，适合容量趋势', preview: 'predict_linear(metric[1h], 3600)' },
  { label: 'absent', insert: 'absent(|)', detail: '指标缺失检测', preview: 'absent(metric)' },
  { label: 'clamp_min', insert: 'clamp_min(|, 0)', detail: '限定最小值', preview: 'clamp_min(expr, 0)' },
  { label: 'clamp_max', insert: 'clamp_max(|, 100)', detail: '限定最大值', preview: 'clamp_max(expr, 100)' },
  { label: 'label_replace', insert: 'label_replace(|, "", "", "", "")', detail: '正则改写标签', preview: 'label_replace(vector, ...)' },
  { label: 'label_join', insert: 'label_join(|, "", "", "")', detail: '拼接多个标签', preview: 'label_join(vector, ...)' },
]
const PROMQL_AGGREGATION_SUGGESTIONS = [
  { label: 'sum', insert: 'sum(|) by ()', detail: '按维度求和', preview: 'sum(expr) by (...)' },
  { label: 'avg', insert: 'avg(|) by ()', detail: '按维度求平均', preview: 'avg(expr) by (...)' },
  { label: 'max', insert: 'max(|) by ()', detail: '按维度取最大', preview: 'max(expr) by (...)' },
  { label: 'min', insert: 'min(|) by ()', detail: '按维度取最小', preview: 'min(expr) by (...)' },
  { label: 'count', insert: 'count(|) by ()', detail: '按维度计数', preview: 'count(expr) by (...)' },
  { label: 'topk', insert: 'topk(10, |)', detail: '取最高 Top N', preview: 'topk(10, expr)' },
  { label: 'bottomk', insert: 'bottomk(10, |)', detail: '取最低 Top N', preview: 'bottomk(10, expr)' },
  { label: 'quantile', insert: 'quantile(0.95, |)', detail: '聚合分位数', preview: 'quantile(0.95, expr)' },
  { label: 'stddev', insert: 'stddev(|) by ()', detail: '标准差聚合', preview: 'stddev(expr) by (...)' },
  { label: 'stdvar', insert: 'stdvar(|) by ()', detail: '方差聚合', preview: 'stdvar(expr) by (...)' },
]
const PROMQL_OPERATOR_SUGGESTIONS = [
  { label: 'by', insert: 'by (|)', detail: '保留聚合维度', preview: 'by (service)' },
  { label: 'without', insert: 'without (|)', detail: '排除聚合维度', preview: 'without (instance)' },
  { label: 'on', insert: 'on (|)', detail: '向量匹配指定标签', preview: 'on (service)' },
  { label: 'ignoring', insert: 'ignoring (|)', detail: '向量匹配忽略标签', preview: 'ignoring (instance)' },
  { label: 'group_left', insert: 'group_left(|)', detail: '多对一左侧匹配', preview: 'group_left(label)' },
  { label: 'group_right', insert: 'group_right(|)', detail: '一对多右侧匹配', preview: 'group_right(label)' },
  { label: 'offset', insert: 'offset |', detail: '时间偏移查询', preview: 'offset 5m' },
  { label: 'and', insert: 'and ', detail: '集合交集', preview: 'expr and expr' },
  { label: 'or', insert: 'or ', detail: '集合并集', preview: 'expr or expr' },
  { label: 'unless', insert: 'unless ', detail: '集合排除', preview: 'expr unless expr' },
]
const PROMQL_LABEL_SUGGESTIONS = [
  { label: 'job', detail: '采集任务 / Exporter' },
  { label: 'instance', detail: '实例地址或目标' },
  { label: 'service', detail: '应用服务' },
  { label: 'namespace', detail: 'K8s 命名空间' },
  { label: 'pod', detail: 'K8s Pod' },
  { label: 'container', detail: '容器名' },
  { label: 'cluster', detail: '集群' },
  { label: 'env', detail: '环境' },
  { label: 'environment', detail: '环境' },
  { label: 'status', detail: 'HTTP 状态码' },
  { label: 'code', detail: '状态码' },
  { label: 'method', detail: 'HTTP 方法' },
  { label: 'path', detail: '请求路径' },
  { label: 'route', detail: '路由' },
  { label: 'handler', detail: '处理器' },
  { label: 'mode', detail: 'CPU 模式' },
  { label: 'cpu', detail: 'CPU 编号' },
  { label: 'device', detail: '网卡或磁盘设备' },
  { label: 'mountpoint', detail: '挂载点' },
  { label: 'fstype', detail: '文件系统类型' },
  { label: 'le', detail: 'Histogram bucket 上界' },
  { label: 'condition', detail: 'K8s 条件' },
  { label: 'image', detail: '镜像' },
  { label: 'node', detail: '节点' },
  { label: 'deployment', detail: 'Deployment 名称' },
]
const PROMQL_LABEL_VALUE_SUGGESTIONS = {
  status: ['200', '201', '400', '401', '403', '404', '500', '502', '503', '5..'],
  code: ['200', '201', '400', '401', '403', '404', '500', '502', '503', '5..'],
  method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
  mode: ['idle', 'user', 'system', 'iowait', 'irq', 'softirq', 'steal'],
  fstype: ['ext4', 'xfs', 'tmpfs', 'overlay'],
  condition: ['true', 'false'],
  job: ['prometheus', 'node-exporter', 'kube-state-metrics', 'cadvisor'],
  service: ['order-api', 'checkout', 'payment', 'inventory'],
  namespace: ['default', 'kube-system', 'monitoring', 'prod'],
  env: ['dev', 'test', 'stage', 'prod'],
  environment: ['dev', 'test', 'stage', 'prod'],
  le: ['0.1', '0.3', '0.5', '1', '2.5', '5', '+Inf'],
}
const PROMQL_EXTRA_METRICS = [
  'up',
  'process_cpu_seconds_total',
  'process_resident_memory_bytes',
  'go_goroutines',
  'prometheus_http_requests_total',
  'prometheus_tsdb_head_series',
]
const PROMQL_RESERVED_WORDS = new Set([
  ...PROMQL_FUNCTION_SUGGESTIONS.map(item => item.label),
  ...PROMQL_AGGREGATION_SUGGESTIONS.map(item => item.label),
  ...PROMQL_OPERATOR_SUGGESTIONS.map(item => item.label),
  'bool',
])

const filteredDataSources = computed(() => {
  const keyword = filters.keyword.toLowerCase()
  return dataSources.value.filter((item) => {
    const enabledMatched = !filters.enabled || String(Boolean(item.is_enabled)) === filters.enabled
    const text = `${item.name} ${item.environment || ''} ${item.cluster_name || ''} ${endpointOf(item) || ''}`.toLowerCase()
    return enabledMatched && (!keyword || text.includes(keyword))
  })
})
const lastResultSource = computed(() => {
  const ds = lastResult.value.metric_datasource
  if (ds?.name) return ds.name
  return lastResult.value.description || lastResult.value.source || '--'
})
const hasQuerySnapshot = computed(() => lastQueryDuration.value > 0 || Object.keys(lastResult.value).length > 0 || Boolean(queryError.value))
const queryStatusText = computed(() => {
  if (!hasQuerySnapshot.value) return '待查询'
  return lastQueryFailed.value ? '失败' : '成功'
})
const selectedMetricDataSource = computed(() => {
  const selectedId = String(queryForm.metric_datasource_id || '')
  return dataSources.value.find(item => String(item.id) === selectedId) || null
})
const autoQueryStep = computed(() => calculateAutoPromqlStep(queryForm.timeRange))
const metricSeriesRows = computed(() => {
  const result = Array.isArray(lastResult.value.result) ? lastResult.value.result : []
  return result.map((item, index) => {
    const metric = item.metric || {}
    const rawPoints = Array.isArray(item.values) && item.values.length ? item.values : (Array.isArray(item.value) ? [item.value] : [])
    const points = rawPoints
      .map(point => normalizeMetricPoint(point))
      .filter(Boolean)
    const latestPoint = points[points.length - 1] || null
    const color = METRIC_SERIES_COLORS[index % METRIC_SERIES_COLORS.length]
    return {
      id: `${index}-${metric.__name__ || 'scalar'}`,
      index,
      metric,
      name: metric.__name__ || `series_${index + 1}`,
      label: formatMetricLabel(metric, index),
      tagsText: formatMetricTagsAsJson(metric),
      color,
      points,
      latestValue: latestPoint ? formatMetricValue(latestPoint[1]) : '--',
      latestTimestamp: latestPoint ? formatTimestampFromMs(latestPoint[0]) : '--',
    }
  })
})
const visibleMetricSeriesRows = computed(() => metricSeriesRows.value.slice(0, METRIC_CHART_SERIES_LIMIT))
const activeMetricChartRows = computed(() => {
  if (!selectedMetricSeriesId.value) return visibleMetricSeriesRows.value
  const selected = metricSeriesRows.value.find(item => item.id === selectedMetricSeriesId.value)
  return selected ? [selected] : visibleMetricSeriesRows.value
})
const selectedMetricSeries = computed(() => (
  metricSeriesRows.value.find(item => item.id === selectedMetricSeriesId.value) || null
))
const metricSeriesCountText = computed(() => {
  if (selectedMetricSeries.value) return `1/${metricSeriesRows.value.length} series`
  return `${visibleMetricSeriesRows.value.length}/${metricSeriesRows.value.length} series`
})
const filteredQuickTemplates = computed(() => {
  const keyword = normalizeSearchText(quickSearch.value)
  return quickTemplates.filter((item) => {
    if (activeQuickCategory.value !== 'all' && item.category !== activeQuickCategory.value) return false
    if (!keyword) return true
    return normalizeSearchText(templateSearchText(item)).includes(keyword)
  })
})
const visibleQuickTemplates = computed(() => {
  return filteredQuickTemplates.value
})
const promqlKnownLabels = computed(() => {
  const labels = new Set(PROMQL_LABEL_SUGGESTIONS.map(item => item.label))
  quickTemplates.forEach(item => {
    extractPromqlLabels(item.expression).forEach(label => labels.add(label))
  })
  return Array.from(labels).sort((a, b) => a.localeCompare(b))
})
const promqlKnownMetrics = computed(() => {
  const metrics = new Set(PROMQL_EXTRA_METRICS)
  quickTemplates.forEach(item => {
    extractPromqlMetrics(item.expression).forEach(metric => metrics.add(metric))
  })
  promqlRemoteMetrics.value.forEach(metric => metrics.add(metric))
  return Array.from(metrics)
    .filter(metric => metric && !PROMQL_RESERVED_WORDS.has(metric) && !promqlKnownLabels.value.includes(metric))
    .sort((a, b) => a.localeCompare(b))
})
const promqlRemoteMetricSet = computed(() => new Set(promqlRemoteMetrics.value))
const promqlInlineContext = computed(() => {
  if (promqlSuggestFocused.value) return promqlSuggestContext.value
  return analyzePromqlContext(queryForm.promql, queryForm.promql.length)
})
const visiblePromqlSuggestions = computed(() => buildPromqlSuggestions(promqlSuggestContext.value, 14))
const promqlInlineSuggestions = computed(() => buildPromqlSuggestions(promqlInlineContext.value, 80))
const shouldShowPromqlSuggestions = computed(() => (
  false
  && promqlSuggestVisible.value
  && (visiblePromqlSuggestions.value.length || promqlMetricLoading.value || Boolean(promqlMetricError.value))
))
const promqlInlineSuggestVisible = computed(() => (
  Boolean(promqlInlineSuggestions.value.length || promqlMetricLoading.value || promqlMetricError.value)
))
const promqlSuggestTitle = computed(() => promqlSuggestionTitle(promqlSuggestContext.value))
const promqlSuggestHint = computed(() => promqlSuggestionHint(promqlSuggestContext.value, visiblePromqlSuggestions.value.length))
const promqlInlineSuggestTitle = computed(() => promqlSuggestionTitle(promqlInlineContext.value))
const promqlInlineSuggestHint = computed(() => promqlSuggestionHint(promqlInlineContext.value, promqlInlineSuggestions.value.length))

function promqlSuggestionTitle(context) {
  if (context.type === 'root' && isLikelyMetricToken(context.query)) {
    if (promqlMetricLoading.value) return '正在加载真实指标'
    if (promqlRemoteMetrics.value.length) return '真实指标候选'
    if (promqlMetricError.value) return '本地指标候选'
    return '指标候选'
  }
  const titles = {
    'label-key': '标签名建议',
    'label-value': `${context.labelKey || '标签'} 取值建议`,
    'label-list': '聚合维度建议',
    duration: '时间窗口建议',
  }
  return titles[context.type] || 'PromQL 查询建议'
}

function promqlSuggestionHint(context, count) {
  if (promqlMetricLoading.value) return '加载中'
  if (promqlMetricError.value && context.type === 'root' && isLikelyMetricToken(context.query)) return '数据源不可用，已兜底'
  return `${count} 条`
}

function endpointOf(row) {
  return row?.config?.query_url || row?.config?.['prometheus.addr'] || row?.config?.addr || ''
}

function sourceOptionLabel(item) {
  const env = item.environment ? ` / ${item.environment}` : ' / 全局'
  return `${item.name}${env}`
}

function formatTimestamp(value) {
  const timestamp = Number(value)
  if (!Number.isFinite(timestamp)) return '--'
  return new Date(timestamp * 1000).toLocaleString()
}

function formatTimestampFromMs(value) {
  const timestamp = Number(value)
  if (!Number.isFinite(timestamp)) return '--'
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false })
}

function normalizeMetricPoint(point) {
  if (!Array.isArray(point) || point.length < 2) return null
  const timestamp = Number(point[0])
  const value = Number(point[1])
  if (!Number.isFinite(timestamp) || !Number.isFinite(value)) return null
  return [timestamp * 1000, value]
}

function formatMetricValue(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value ?? '--')
  const abs = Math.abs(number)
  if (abs > 0 && abs < 0.001) return number.toExponential(2)
  if (abs >= 1000000) return number.toExponential(2)
  return Number(number.toFixed(4)).toString()
}

function formatMetricLabel(metric, index = 0) {
  const entries = Object.entries(metric || {})
  if (!entries.length) return `scalar_${index + 1}`
  const name = metric.__name__ || `series_${index + 1}`
  const tags = entries
    .filter(([key]) => key !== '__name__')
    .map(([key, value]) => `${key}="${value}"`)
  return tags.length ? `${name}{${tags.join(', ')}}` : name
}

function formatMetricTagsAsJson(metric) {
  const entries = Object.entries(metric || {})
  if (!entries.length) return '{\n  "scalar": true\n}'
  const lines = entries.map(([key, value]) => `  "${key}": "${String(value).replace(/"/g, '\\"')}"`)
  return `{\n${lines.join(',\n')}\n}`
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function formatTimeRangeSummary(range) {
  if (!Array.isArray(range) || range.length !== 2 || !range[0] || !range[1]) return '未选择'
  const start = new Date(range[0])
  const end = new Date(range[1])
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return '未选择'
  const minutes = Math.max(1, Math.round((end.getTime() - start.getTime()) / 60000))
  if (minutes < 60) return `最近 ${minutes} 分钟`
  if (minutes % 60 === 0) return `最近 ${minutes / 60} 小时`
  return `${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

function calculateAutoPromqlStep(range) {
  if (!Array.isArray(range) || range.length !== 2 || !range[0] || !range[1]) return 30
  const start = new Date(range[0]).getTime()
  const end = new Date(range[1]).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return 30
  const rangeSeconds = Math.max(1, Math.floor((end - start) / 1000))
  const rawStep = Math.ceil(rangeSeconds / 240)
  const candidates = [30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 21600, 43200, 86400]
  return candidates.find(item => item >= rawStep) || 86400
}

function metricTooltipFormatter(params) {
  const items = Array.isArray(params) ? params : [params]
  const validItems = items
    .filter(item => item && Array.isArray(item.value))
    .slice(0, 12)
  if (!validItems.length) return ''
  const time = formatTimestampFromMs(validItems[0].value[0])
  const rows = validItems.map((item) => {
    const series = metricSeriesRows.value.find(row => row.id === item.data?.metricRowId) || metricSeriesRows.value[item.seriesIndex]
    const tags = series?.tagsText || '{}'
    const metricName = series?.name || item.seriesName || '--'
    return `
      <div class="metric-tooltip-series">
        <div class="metric-tooltip-value-row">
          <span class="metric-tooltip-dot" style="background:${escapeHtml(item.color)}"></span>
          <strong>${escapeHtml(metricName)}</strong>
          <span class="metric-tooltip-value">${escapeHtml(formatMetricValue(item.value[1]))}</span>
        </div>
        <pre>${escapeHtml(tags)}</pre>
      </div>
    `
  }).join('')
  const omitted = items.length > validItems.length ? `<div class="metric-tooltip-more">其余 ${items.length - validItems.length} 条已省略</div>` : ''
  return `<div class="metric-tooltip"><div class="metric-tooltip-time">${escapeHtml(time)}</div>${rows}${omitted}</div>`
}

function renderMetricChart() {
  if (!metricChartRef.value) return
  const rows = activeMetricChartRows.value
  if (!rows.length) {
    metricChart?.clear()
    return
  }
  if (!metricChart) metricChart = echarts.init(metricChartRef.value, null, { renderer: 'canvas' })
  metricChart.setOption(
    {
      backgroundColor: '#ffffff',
      animation: false,
      color: rows.map(item => item.color),
      grid: { left: 56, right: 24, top: 20, bottom: 38 },
      tooltip: {
        trigger: 'axis',
        confine: true,
        appendToBody: true,
        backgroundColor: '#ffffff',
        borderColor: '#dbeafe',
        borderWidth: 1,
        padding: 0,
        textStyle: { color: '#0f172a', fontSize: 12 },
        extraCssText: 'box-shadow:0 16px 42px rgba(15,23,42,.16);border-radius:8px;',
        axisPointer: {
          type: 'cross',
          lineStyle: { color: '#94a3b8', width: 1, type: 'dashed' },
          crossStyle: { color: '#94a3b8' },
          label: { backgroundColor: '#f1f5f9', color: '#334155' },
        },
        formatter: metricTooltipFormatter,
      },
      xAxis: {
        type: 'time',
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#dbe3ef' } },
        axisTick: { lineStyle: { color: '#dbe3ef' } },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { show: true, lineStyle: { color: '#eef2f7', type: 'dashed' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          color: '#64748b',
          fontSize: 11,
          formatter: value => formatMetricValue(value),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: '#eef2f7' } },
      },
      series: rows.map(item => ({
        name: item.label,
        type: 'line',
        metricRowId: item.id,
        data: item.points.map(point => ({
          value: point,
          metricRowId: item.id,
        })),
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 5,
        smooth: false,
        connectNulls: false,
        lineStyle: { width: 1.6, color: item.color },
        itemStyle: { color: item.color },
        emphasis: {
          focus: 'series',
          lineStyle: { width: 2.4 },
        },
      })),
    },
    true
  )
}

function handleMetricChartResize() {
  metricChart?.resize()
}

function toggleMetricSeries(item) {
  selectedMetricSeriesId.value = selectedMetricSeriesId.value === item.id ? '' : item.id
}

function normalizeSearchText(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim()
}

function templateSearchText(item) {
  return [item.title, item.summary, item.expression, item.kind, quickCategoryLabel(item.category), ...(item.tags || [])].join(' ')
}

function quickCategoryLabel(category) {
  return quickCategories.find(item => item.value === category)?.label || '常用'
}

function quickCategoryCount(category) {
  if (category === 'all') return quickTemplates.length
  return quickTemplates.filter(item => item.category === category).length
}

function createPromqlContext(overrides = {}) {
  return {
    type: 'root',
    query: '',
    start: 0,
    end: 0,
    cursor: 0,
    labelKey: '',
    quoted: false,
    needsClosingQuote: false,
    ...overrides,
  }
}

function createPromqlSuggestion(item) {
  return {
    id: `${item.type}-${item.label}-${item.insert || item.preview || ''}`,
    insert: item.insert || item.label,
    preview: item.preview || item.insert || item.label,
    badge: item.badge || '建议',
    detail: item.detail || '',
    ...item,
  }
}

function buildPromqlSuggestions(context, limit = 14) {
  const query = normalizeSearchText(context.query)
  let suggestions = []
  if (context.type === 'label-value') {
    const values = PROMQL_LABEL_VALUE_SUGGESTIONS[context.labelKey] || []
    suggestions = values.map(value => createPromqlSuggestion({
      type: 'label-value',
      badge: '值',
      label: value,
      detail: `${context.labelKey} 标签值`,
      insert: context.quoted ? `${value}|${context.needsClosingQuote ? '"' : ''}` : `"${value}"`,
      preview: `${context.labelKey}="${value}"`,
    }))
  } else if (context.type === 'label-key') {
    suggestions = promqlKnownLabels.value.map(label => createPromqlSuggestion({
      type: 'label-key',
      badge: '标签',
      label,
      detail: labelDetail(label),
      insert: `${label}="|"`,
      preview: `${label}="..."`,
    }))
  } else if (context.type === 'label-list') {
    suggestions = promqlKnownLabels.value.map(label => createPromqlSuggestion({
      type: 'label-list',
      badge: '维度',
      label,
      detail: labelDetail(label),
      insert: label,
      preview: label,
    }))
  } else if (context.type === 'duration') {
    suggestions = ['1m', '3m', '5m', '10m', '15m', '30m', '1h', '6h', '24h'].map(value => createPromqlSuggestion({
      type: 'duration',
      badge: '窗口',
      label: value,
      detail: 'Range vector 时间窗口',
      insert: value,
      preview: `[${value}]`,
    }))
  } else {
    const metricSuggestions = promqlKnownMetrics.value.map(metric => createPromqlSuggestion({
      type: 'metric',
      badge: promqlRemoteMetricSet.value.has(metric) ? '真实' : '指标',
      label: metric,
      detail: metricDetail(metric),
      insert: metric,
      preview: metric,
      remote: promqlRemoteMetricSet.value.has(metric),
    }))
    const functionSuggestions = PROMQL_FUNCTION_SUGGESTIONS.map(item => createPromqlSuggestion({
      ...item,
      type: 'function',
      badge: '函数',
    }))
    const aggregationSuggestions = PROMQL_AGGREGATION_SUGGESTIONS.map(item => createPromqlSuggestion({
      ...item,
      type: 'aggregation',
      badge: '聚合',
    }))
    const operatorSuggestions = PROMQL_OPERATOR_SUGGESTIONS.map(item => createPromqlSuggestion({
      ...item,
      type: 'operator',
      badge: '语法',
    }))
    suggestions = [...metricSuggestions, ...functionSuggestions, ...aggregationSuggestions, ...operatorSuggestions]
  }
  return sortPromqlSuggestions(suggestions, query, context).slice(0, limit)
}

function highlightedSuggestionLabel(label, context = promqlSuggestContext.value) {
  const source = String(label || '')
  const query = String(context.query || '').trim()
  if (!query) return [{ text: source, hit: false }]
  const start = source.toLowerCase().indexOf(query.toLowerCase())
  if (start < 0) return [{ text: source, hit: false }]
  const end = start + query.length
  return [
    { text: source.slice(0, start), hit: false },
    { text: source.slice(start, end), hit: true },
    { text: source.slice(end), hit: false },
  ].filter(part => part.text)
}

function extractPromqlLabels(expression) {
  const labels = new Set()
  String(expression || '').replace(/\{([^}]*)\}/g, (_, selector) => {
    selector.replace(/([A-Za-z_][A-Za-z0-9_]*)\s*(?:=~|!~|!=|=)/g, (match, label) => {
      labels.add(label)
      return match
    })
    return selector
  })
  String(expression || '').replace(/\b(?:by|without|on|ignoring|group_left|group_right)\s*\(([^)]*)\)/g, (_, content) => {
    content.split(',').map(item => item.trim()).filter(Boolean).forEach(label => labels.add(label))
    return content
  })
  return Array.from(labels)
}

function extractPromqlMetrics(expression) {
  const metrics = new Set()
  const stripped = String(expression || '')
    .replace(/"[^"]*"/g, ' ')
    .replace(/'[^']*'/g, ' ')
    .replace(/\{[^}]*\}/g, ' ')
  const tokenPattern = /[A-Za-z_:][A-Za-z0-9_:]*/g
  let match = tokenPattern.exec(stripped)
  while (match) {
    const token = match[0]
    if (!PROMQL_RESERVED_WORDS.has(token)) metrics.add(token)
    match = tokenPattern.exec(stripped)
  }
  return Array.from(metrics)
}

function labelDetail(label) {
  return PROMQL_LABEL_SUGGESTIONS.find(item => item.label === label)?.detail || 'Prometheus 标签'
}

function metricDetail(metric) {
  if (promqlRemoteMetricSet.value.has(metric)) return ''
  const template = quickTemplates.find(item => item.expression.includes(metric))
  if (template) return `${quickCategoryLabel(template.category)} / ${template.kind}`
  if (metric.endsWith('_total')) return 'Counter 指标'
  if (metric.endsWith('_bucket')) return 'Histogram bucket'
  if (metric.endsWith('_bytes')) return '容量 / 字节指标'
  return '指标名'
}

function sortPromqlSuggestions(items, query, context = promqlSuggestContext.value) {
  const normalizedQuery = normalizeSearchText(query)
  const seen = new Set()
  return items
    .map((item) => {
      const label = normalizeSearchText(item.label)
      const preview = normalizeSearchText(item.preview)
      const detail = normalizeSearchText(item.detail)
      let matchScore = normalizedQuery ? 0 : 1
      if (normalizedQuery) {
        if (label === normalizedQuery) matchScore += 60
        else if (label.startsWith(normalizedQuery)) matchScore += 42
        else if (label.includes(normalizedQuery)) matchScore += 24
        if (preview.includes(normalizedQuery)) matchScore += 10
        if (detail.includes(normalizedQuery)) matchScore += 4
      }
      if (normalizedQuery && matchScore === 0) return null
      let score = matchScore
      if (item.type === context.type) score += 8
      if (item.type === 'metric') score += 8
      if (item.remote) score += 18
      if (item.type === 'function' || item.type === 'aggregation') score += 3
      return { ...item, score }
    })
    .filter(Boolean)
    .filter(item => item.score > 0)
    .filter((item) => {
      const key = `${item.type}-${item.label}-${item.insert}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((a, b) => b.score - a.score || Number(Boolean(b.remote)) - Number(Boolean(a.remote)) || a.label.localeCompare(b.label))
}

function isLikelyMetricToken(query) {
  const text = String(query || '').trim()
  return text.length >= 1 && /[A-Za-z_:]/.test(text) && !PROMQL_RESERVED_WORDS.has(text)
}

function metricLookupKey(query) {
  return [
    queryForm.metric_datasource_id || 'default',
    String(query || '').trim().toLowerCase(),
  ].join('|')
}

function scheduleMetricNameLookup(context = promqlSuggestContext.value) {
  if (promqlMetricFetchTimer) clearTimeout(promqlMetricFetchTimer)
  if (context.type !== 'root' || !isLikelyMetricToken(context.query)) {
    promqlMetricLoading.value = false
    promqlMetricError.value = ''
    return
  }
  const lookupKey = metricLookupKey(context.query)
  if (lookupKey === promqlMetricLoadedKey.value) return
  promqlMetricLoading.value = true
  promqlMetricError.value = ''
  promqlMetricFetchTimer = setTimeout(() => {
    loadMetricNameSuggestions(context.query)
  }, 120)
}

async function loadMetricNameSuggestions(query) {
  const trimmed = String(query || '').trim()
  if (!isLikelyMetricToken(trimmed)) return
  const lookupKey = metricLookupKey(trimmed)
  const fetchSeq = ++promqlMetricFetchSeq
  promqlMetricLoading.value = true
  promqlMetricError.value = ''
  try {
    const response = await getMetricSeriesNames({
      q: trimmed,
      limit: 80,
      metric_datasource_id: queryForm.metric_datasource_id || '',
    })
    if (fetchSeq !== promqlMetricFetchSeq) return
    promqlRemoteMetrics.value = Array.isArray(response?.metrics) ? response.metrics : []
    promqlMetricLoadedKey.value = lookupKey
    await nextTick()
    refreshPromqlSuggestions({ forceOpen: true, skipLookup: true })
  } catch (error) {
    if (fetchSeq !== promqlMetricFetchSeq) return
    promqlRemoteMetrics.value = []
    promqlMetricLoadedKey.value = lookupKey
    promqlMetricError.value = error?.response?.data?.detail || error.message || '指标名加载失败'
    await nextTick()
    refreshPromqlSuggestions({ forceOpen: true, skipLookup: true })
  } finally {
    if (fetchSeq === promqlMetricFetchSeq) promqlMetricLoading.value = false
  }
}

function promqlTextareaEl() {
  return promqlInputRef.value?.input || promqlInputRef.value?.textarea || promqlInputRef.value?.$el?.querySelector('input, textarea') || null
}

function wordRangeAt(text, cursor, pattern = /[A-Za-z0-9_:]/) {
  let start = cursor
  let end = cursor
  while (start > 0 && pattern.test(text[start - 1])) start -= 1
  while (end < text.length && pattern.test(text[end])) end += 1
  return { start, end, query: text.slice(start, cursor) }
}

function analyzePromqlContext(text, selectionStart, selectionEnd = selectionStart) {
  const cursor = selectionStart
  if (selectionEnd > selectionStart) {
    return createPromqlContext({
      query: text.slice(selectionStart, selectionEnd),
      start: selectionStart,
      end: selectionEnd,
      cursor,
    })
  }

  const beforeCursor = text.slice(0, cursor)
  const lastBrace = beforeCursor.lastIndexOf('{')
  const lastBraceClose = beforeCursor.lastIndexOf('}')
  if (lastBrace > lastBraceClose) {
    const commaIndex = beforeCursor.lastIndexOf(',', cursor - 1)
    const segmentStart = Math.max(lastBrace + 1, commaIndex + 1)
    const segment = text.slice(segmentStart, cursor)
    const valueMatch = segment.match(/([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*([^,}]*)$/)
    if (valueMatch) {
      const rawValue = valueMatch[3] || ''
      const rawStart = segmentStart + valueMatch.index + valueMatch[0].length - rawValue.length
      const firstNonSpace = rawValue.search(/\S/)
      const valueStart = rawStart + (firstNonSpace > -1 ? firstNonSpace : rawValue.length)
      const quote = text[valueStart] === '"' || text[valueStart] === "'"
      const start = quote ? valueStart + 1 : valueStart
      let end = cursor
      let needsClosingQuote = false
      if (quote) {
        const closingQuote = text.indexOf(text[valueStart], start)
        if (closingQuote >= start && closingQuote < cursor) end = closingQuote
        needsClosingQuote = text.slice(cursor).trimStart()[0] !== text[valueStart]
      }
      return createPromqlContext({
        type: 'label-value',
        query: text.slice(start, end),
        start,
        end,
        cursor,
        labelKey: valueMatch[1],
        quoted: quote,
        needsClosingQuote,
      })
    }
    const range = wordRangeAt(text, cursor, /[A-Za-z0-9_]/)
    return createPromqlContext({
      type: 'label-key',
      query: range.query,
      start: Math.max(range.start, segmentStart),
      end: range.end,
      cursor,
    })
  }

  const lastBracket = beforeCursor.lastIndexOf('[')
  const lastBracketClose = beforeCursor.lastIndexOf(']')
  if (lastBracket > lastBracketClose) {
    return createPromqlContext({
      type: 'duration',
      query: text.slice(lastBracket + 1, cursor),
      start: lastBracket + 1,
      end: cursor,
      cursor,
    })
  }

  const lastParen = beforeCursor.lastIndexOf('(')
  const lastParenClose = beforeCursor.lastIndexOf(')')
  if (lastParen > lastParenClose) {
    const prefix = beforeCursor.slice(0, lastParen).trimEnd()
    if (/\b(by|without|on|ignoring|group_left|group_right)$/.test(prefix)) {
      const commaIndex = beforeCursor.lastIndexOf(',', cursor - 1)
      const start = Math.max(lastParen + 1, commaIndex + 1)
      const range = wordRangeAt(text, cursor, /[A-Za-z0-9_]/)
      return createPromqlContext({
        type: 'label-list',
        query: text.slice(Math.max(range.start, start), cursor),
        start: Math.max(range.start, start),
        end: range.end,
        cursor,
      })
    }
  }

  const range = wordRangeAt(text, cursor)
  return createPromqlContext({
    query: range.query,
    start: range.start,
    end: range.end,
    cursor,
  })
}

function refreshPromqlSuggestions(options = {}) {
  const textarea = promqlTextareaEl()
  const start = textarea?.selectionStart ?? queryForm.promql.length
  const end = textarea?.selectionEnd ?? start
  promqlSuggestContext.value = analyzePromqlContext(queryForm.promql, start, end)
  if (!options.skipLookup) scheduleMetricNameLookup(promqlSuggestContext.value)
  promqlSuggestIndex.value = visiblePromqlSuggestions.value.length
    ? Math.min(promqlSuggestIndex.value, visiblePromqlSuggestions.value.length - 1)
    : -1
  promqlSuggestVisible.value = Boolean(
    options.forceOpen
    || visiblePromqlSuggestions.value.length
    || promqlMetricLoading.value
    || (promqlSuggestFocused.value && isLikelyMetricToken(promqlSuggestContext.value.query))
  )
}

function openPromqlSuggestions() {
  if (promqlSuggestCloseTimer) clearTimeout(promqlSuggestCloseTimer)
  promqlSuggestFocused.value = true
  refreshPromqlSuggestions()
}

function scheduleClosePromqlSuggestions() {
  if (promqlSuggestCloseTimer) clearTimeout(promqlSuggestCloseTimer)
  promqlSuggestCloseTimer = setTimeout(() => {
    promqlSuggestFocused.value = false
    promqlSuggestVisible.value = false
  }, 120)
}

function handlePromqlInput() {
  selectedQuickId.value = ''
  promqlSuggestIndex.value = -1
  refreshPromqlSuggestions()
}

function handlePromqlKeyup(event) {
  if (['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape', 'Control', 'Shift', 'Alt', 'Meta'].includes(event.key)) return
  refreshPromqlSuggestions()
}

function handlePromqlKeydown(event) {
  if ((event.ctrlKey || event.metaKey) && event.code === 'Space') {
    event.preventDefault()
    promqlSuggestIndex.value = -1
    refreshPromqlSuggestions()
    return
  }
  if (!promqlSuggestVisible.value || !visiblePromqlSuggestions.value.length) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    promqlSuggestIndex.value = promqlSuggestIndex.value < 0
      ? 0
      : (promqlSuggestIndex.value + 1) % visiblePromqlSuggestions.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    promqlSuggestIndex.value = promqlSuggestIndex.value < 0
      ? visiblePromqlSuggestions.value.length - 1
      : (promqlSuggestIndex.value - 1 + visiblePromqlSuggestions.value.length) % visiblePromqlSuggestions.value.length
  } else if (event.key === 'Enter' || event.key === 'Tab') {
    if (promqlSuggestIndex.value < 0) return
    event.preventDefault()
    applyPromqlSuggestion(visiblePromqlSuggestions.value[promqlSuggestIndex.value])
  } else if (event.key === 'Escape') {
    event.preventDefault()
    promqlSuggestVisible.value = false
  }
}

async function applyPromqlSuggestion(item) {
  if (!item) return
  await insertPromqlSuggestion(item, promqlSuggestContext.value, { keepPopover: false })
}

async function applyInlinePromqlSuggestion(item) {
  if (!item) return
  await insertPromqlSuggestion(item, promqlInlineContext.value, { keepPopover: false })
}

async function insertPromqlSuggestion(item, context, options = {}) {
  const insert = String(item.insert || item.label)
  const markerIndex = insert.indexOf('|')
  const insertText = insert.replace('|', '')
  const cursorOffset = markerIndex >= 0 ? markerIndex : insertText.length
  queryForm.promql = `${queryForm.promql.slice(0, context.start)}${insertText}${queryForm.promql.slice(context.end)}`
  selectedQuickId.value = ''
  promqlSuggestVisible.value = Boolean(options.keepPopover)
  await nextTick()
  const textarea = promqlTextareaEl()
  const nextCursor = context.start + cursorOffset
  textarea?.focus()
  textarea?.setSelectionRange(nextCursor, nextCursor)
  promqlSuggestFocused.value = Boolean(textarea)
  refreshPromqlSuggestions()
}

function fillPromql(item) {
  if (!item?.expression) return
  queryForm.promql = item.expression
  selectedQuickId.value = item.id
  promqlSuggestVisible.value = false
  nextTick(() => {
    refreshPromqlSuggestions()
  })
}

async function copyPromql(value) {
  const text = String(value || '').trim()
  if (!text) {
    ElMessage.warning('暂无可复制的 PromQL')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('PromQL 已复制')
  } catch (error) {
    ElMessage.warning('当前浏览器不允许直接复制，请手动选中复制')
  }
}

function resetSourceForm(row = null) {
  const config = row?.config || {}
  dialog.editingId = row?.id || null
  sourceForm.name = row?.name || ''
  sourceForm.provider = row?.provider || 'prometheus'
  sourceForm.description = row?.description || ''
  sourceForm.query_url = config.query_url || config['prometheus.addr'] || ''
  sourceForm.auth_type = config.auth_type || 'none'
  sourceForm.username = config.username || config['prometheus.basic']?.['prometheus.user'] || ''
  sourceForm.password = config.password || config['prometheus.basic']?.['prometheus.password'] || ''
  sourceForm.bearer_token = config.bearer_token || ''
  sourceForm.timeout = Number(config.timeout || config['prometheus.timeout'] || 6)
  sourceForm.tls_skip_verify = row ? Boolean(config.tls_skip_verify ?? true) : true
  sourceForm.is_enabled = row?.is_enabled ?? true
  sourceForm.is_default = row?.is_default ?? false
}

function buildSourcePayload() {
  const headers = {}
  return {
    name: sourceForm.name,
    provider: sourceForm.provider,
    description: sourceForm.description,
    environment: '',
    cluster_name: '',
    tsdb_type: 'prometheus',
    is_enabled: sourceForm.is_enabled,
    is_default: sourceForm.is_default,
    config: {
      query_url: sourceForm.query_url,
      'prometheus.addr': sourceForm.query_url,
      auth_type: sourceForm.auth_type,
      username: sourceForm.username,
      password: sourceForm.password,
      bearer_token: sourceForm.bearer_token,
      headers,
      'prometheus.headers': headers,
      timeout: sourceForm.timeout,
      'prometheus.timeout': sourceForm.timeout,
      tls_skip_verify: sourceForm.tls_skip_verify,
      'prometheus.basic': {
        'prometheus.user': sourceForm.username,
        'prometheus.password': sourceForm.password,
      },
    },
  }
}

async function loadDataSources() {
  loadingSources.value = true
  try {
    const response = await getMetricDataSources()
    dataSources.value = Array.isArray(response) ? response : (response.results || [])
    if (!queryForm.metric_datasource_id && dataSources.value.length) {
      const defaultSource = dataSources.value.find(item => item.is_default && item.is_enabled) || dataSources.value.find(item => item.is_enabled)
      queryForm.metric_datasource_id = defaultSource?.id || ''
    }
  } finally {
    loadingSources.value = false
  }
}

async function runQuery() {
  if (!queryForm.promql.trim()) {
    ElMessage.warning('请填写 PromQL')
    return
  }
  queryLoading.value = true
  queryError.value = ''
  lastQueryFailed.value = false
  const startedAt = performance.now()
  try {
    const payload = {
      promql: queryForm.promql,
      metric_datasource_id: queryForm.metric_datasource_id || '',
      range_query: true,
      step: autoQueryStep.value,
    }
    if (queryForm.timeRange?.length === 2) {
      payload.start = queryForm.timeRange[0].toISOString()
      payload.end = queryForm.timeRange[1].toISOString()
    }
    lastResult.value = await queryMetrics(payload)
    await nextTick()
    renderMetricChart()
  } catch (error) {
    lastQueryFailed.value = true
    queryError.value = error?.response?.data?.detail || error.message || '指标查询失败'
  } finally {
    lastQueryDuration.value = Math.round(performance.now() - startedAt)
    queryLoading.value = false
  }
}

function openDatasourceDialog(row = null) {
  resetSourceForm(row)
  dialog.visible = true
}

async function submitDatasource() {
  await sourceFormRef.value?.validate()
  savingSource.value = true
  try {
    const payload = buildSourcePayload()
    if (dialog.editingId) {
      await updateMetricDataSource(dialog.editingId, payload)
    } else {
      await createMetricDataSource(payload)
    }
    ElMessage.success('指标数据源已保存')
    dialog.visible = false
    await loadDataSources()
  } finally {
    savingSource.value = false
  }
}

async function testSource(row) {
  const response = await testMetricDataSource(row.id, { query: 'up' })
  ElMessage.success(`${response.message || '连接成功'}，返回 ${response.series_count || 0} 条序列`)
}

async function removeSource(row) {
  await ElMessageBox.confirm(`确认删除指标数据源「${row.name}」？`, '删除确认', { type: 'warning' })
  await deleteMetricDataSource(row.id)
  ElMessage.success('指标数据源已删除')
  await loadDataSources()
}

watch(
  () => queryForm.promql,
  async () => {
    await nextTick()
    refreshPromqlSuggestions()
  },
  { flush: 'post' }
)

watch(
  () => String(queryForm.metric_datasource_id || ''),
  async () => {
    promqlRemoteMetrics.value = []
    promqlMetricLoadedKey.value = ''
    promqlMetricError.value = ''
    await nextTick()
    refreshPromqlSuggestions()
  },
  { flush: 'post' }
)

watch(
  metricSeriesRows,
  async () => {
    if (selectedMetricSeriesId.value && !metricSeriesRows.value.some(item => item.id === selectedMetricSeriesId.value)) {
      selectedMetricSeriesId.value = ''
    }
    await nextTick()
    renderMetricChart()
  },
  { flush: 'post' }
)

watch(
  selectedMetricSeriesId,
  async () => {
    await nextTick()
    renderMetricChart()
  },
  { flush: 'post' }
)

watch(
  () => activeTab.value,
  async (tabName) => {
    if (tabName === 'query') {
      await nextTick()
      renderMetricChart()
      handleMetricChartResize()
      return
    }
    metricChart?.dispose()
    metricChart = null
  }
)

watch(
  () => route.query.tab,
  (tabName) => {
    activeTab.value = tabName === 'datasources' ? 'datasources' : 'query'
  },
  { immediate: true }
)

onMounted(async () => {
  await loadDataSources()
  await nextTick()
  refreshPromqlSuggestions()
  renderMetricChart()
  window.addEventListener('resize', handleMetricChartResize)
})
onBeforeUnmount(() => {
  if (promqlSuggestCloseTimer) clearTimeout(promqlSuggestCloseTimer)
  if (promqlMetricFetchTimer) clearTimeout(promqlMetricFetchTimer)
  window.removeEventListener('resize', handleMetricChartResize)
  metricChart?.dispose()
  metricChart = null
})
</script>

<style scoped>
.metrics-page {
  --metric-query-console-height: 520px;
  --promql-suggest-item-height: 38px;
  --promql-suggest-head-height: 32px;
  --promql-suggest-visible-rows: 8;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel,
.workbench-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.92) 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 20px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
}

.hero.panel.hero-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 20px;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.release-hero-title-row,
.release-hero-title-inline {
  display: flex;
  align-items: center;
  gap: 10px;
}

.release-hero-title-row h2 {
  margin: 0;
  color: #0f172a;
  font-size: 23px;
  font-weight: 800;
}

.release-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #245bdb;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  border: 1px solid rgba(36, 91, 219, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hero-actions :deep(.el-button) {
  border-radius: 10px;
  font-weight: 500;
  min-height: 32px;
  padding: 0 14px;
}

.page-desc,
.page-inline-desc {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.inline-subtitle {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-desc,
.toolbar-count {
  color: #64748b;
  font-size: 13px;
}

.metrics-tabs {
  display: flex;
  width: 100%;
  padding: 3px;
  gap: 8px;
  margin-bottom: 0;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.neo-tab-btn {
  min-height: 38px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  background: transparent;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.neo-tab-btn.active {
  color: #245bdb;
  background: rgba(51, 112, 255, 0.1);
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.14);
}

.workbench-card {
  padding: 12px 14px;
}

.metric-query-unified-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.035);
  padding: 9px 11px 24px;
}

.metric-query-workbench {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-query-left-card,
.quick-promql-panel {
  height: var(--metric-query-console-height);
  min-height: var(--metric-query-console-height);
  max-height: var(--metric-query-console-height);
}

.metric-query-left-card {
  min-height: 0;
  overflow: hidden;
}

.metric-query-unified-head {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 6px;
}

.metric-query-title-block {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.metric-query-title-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.metric-query-title-row h3 {
  color: #0f172a;
  font-size: 14px;
  letter-spacing: 0.01em;
  margin: 0;
}

.metric-query-title-row span {
  color: #64748b;
  font-size: 12px;
}

.metric-query-actions {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  justify-content: flex-end;
}

.metric-query-provider-strip {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 4px;
  width: 100%;
}

.metric-filter-datasource-row {
  align-items: center;
  display: flex;
  gap: 6px;
  min-height: 28px;
  width: 100%;
}

.metric-query-provider-label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  margin-right: 4px;
  white-space: nowrap;
}

.metric-datasource-control {
  flex: 1 1 auto;
  max-width: none;
}

.search-panel {
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 12px;
}

.search-panel--merged {
  background: transparent;
  border: 0;
  border-top: 1px solid rgba(226, 232, 240, 0.64);
  border-radius: 0;
  padding: 6px 0 0;
}

.metric-search-panel {
  display: flex;
  flex-direction: column;
  margin-bottom: 4px;
}

.metric-filter-grid {
  align-items: center;
  column-gap: 6px;
  display: grid;
  grid-template-columns: minmax(360px, 1fr);
  width: 100%;
}

.metric-inline-filter {
  align-items: center;
  column-gap: 6px;
  display: grid;
  grid-template-columns: auto minmax(300px, 1fr) auto;
  min-width: 0;
}

.metric-inline-filter--time {
  width: 100%;
}

.metric-inline-filter__label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  margin-right: 1px;
  white-space: nowrap;
}

.metric-time-control {
  width: 100%;
}

.metric-filter-pills {
  display: inline-flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  min-width: max-content;
}

.search-action-primary {
  border-radius: 8px;
  box-shadow: none;
  font-size: 13px;
  font-weight: 600;
  min-height: 28px;
  min-width: 84px;
  padding-inline: 12px;
}

.section-toolbar,
.toolbar-head,
.workbench-card-actions,
.workbench-toolbar,
.workbench-toolbar-left,
.workbench-toolbar-right {
  display: flex;
  align-items: center;
}

.section-toolbar {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.toolbar-head {
  gap: 8px;
  flex: 1;
  min-width: 0;
  flex-wrap: nowrap;
}

.toolbar-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
  white-space: nowrap;
}

.toolbar-desc {
  color: #64748b;
  flex: 1;
  min-width: 0;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workbench-card-actions,
.workbench-toolbar-left,
.workbench-toolbar-right {
  gap: 8px;
}

.workbench-toolbar {
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  margin-bottom: 10px;
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow: inset 0 -1px 0 rgba(226, 232, 240, 0.72);
}

.query-toolbar {
  align-items: flex-start;
}

.workbench-toolbar-left {
  flex-wrap: wrap;
  min-width: 0;
}

.workbench-toolbar-right {
  flex-shrink: 0;
}

.search-control {
  width: 100%;
}

.search-control :deep(.el-select__wrapper),
.search-control :deep(.el-input__wrapper),
.search-control :deep(.el-range-editor.el-input__wrapper) {
  background: rgba(248, 250, 252, 0.82);
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(226, 232, 240, 0.92) inset;
  min-height: 30px;
}

.search-control :deep(.el-input__inner),
.search-control :deep(.el-select__selected-item),
.search-control :deep(.el-range-input) {
  font-size: 12px;
}

.search-control :deep(.el-select__wrapper:hover),
.search-control :deep(.el-input__wrapper:hover),
.search-control :deep(.el-range-editor.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(191, 219, 254, 0.96) inset;
}

.query-console {
  display: grid;
  grid-template-columns: minmax(0, 1.76fr) minmax(282px, 0.75fr);
  gap: 6px;
  align-items: stretch;
  height: var(--metric-query-console-height);
  margin-bottom: 0;
}

.quick-promql-panel,
.query-editor {
  min-width: 0;
}

.quick-promql-panel {
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(249, 250, 252, 0.92) 100%);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
}

.promql-field-head,
.quick-panel-head,
.quick-card-top,
.quick-panel-title {
  display: flex;
  align-items: center;
}

.promql-field-head,
.quick-panel-head,
.quick-card-top {
  justify-content: space-between;
  gap: 10px;
}

.quick-panel-title {
  gap: 6px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.quick-card-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.quick-promql-card code {
  display: block;
  overflow: hidden;
  color: #245bdb;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.query-editor {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  margin-bottom: 0;
}

.promql-search-panel {
  margin-top: 3px;
  padding-top: 5px;
  border-top: 1px solid rgba(226, 232, 240, 0.64);
  background: transparent;
}

.promql-field-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  margin-bottom: 0;
}

.promql-field-label {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

.editor-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.promql-editor-shell {
  position: relative;
  min-width: 0;
  width: 100%;
}

.promql-textarea :deep(.el-input__wrapper) {
  height: 36px;
  min-height: 36px !important;
  padding: 0 10px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.82);
  box-shadow: 0 0 0 1px rgba(226, 232, 240, 0.92) inset;
}

.promql-textarea :deep(.el-input__inner) {
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 36px;
  white-space: nowrap;
}

.promql-textarea :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(191, 219, 254, 0.96) inset;
}

.promql-textarea :deep(.el-input__wrapper.is-focus) {
  background: #fbfdff;
  box-shadow:
    0 0 0 1px #2563eb inset,
    0 0 0 3px rgba(37, 99, 235, 0.08);
}

.promql-suggest-popover {
  position: absolute;
  display: flex;
  flex-direction: column;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  z-index: 35;
  max-height: min(360px, calc(100vh - 220px));
  overflow: hidden;
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.1);
}

.promql-suggest-list {
  overflow: auto;
  min-height: 0;
  scrollbar-color: rgba(148, 163, 184, 0.56) transparent;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.promql-suggest-list::-webkit-scrollbar {
  width: 6px;
}

.promql-suggest-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.48);
}

.promql-suggest-list::-webkit-scrollbar-track {
  background: transparent;
}

.promql-suggest-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.92);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.promql-suggest-head small {
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.promql-suggest-state {
  padding: 10px 12px;
  color: #64748b;
  font-size: 12px;
}

.promql-suggest-item {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) minmax(150px, 0.46fr);
  align-items: center;
  column-gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 5px 10px;
  border: 0;
  border-bottom: 1px solid rgba(226, 232, 240, 0.72);
  color: #334155;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.promql-suggest-item:last-child {
  border-bottom: 0;
}

.promql-suggest-item:hover,
.promql-suggest-item.active {
  background: #eff6ff;
}

.promql-suggest-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  min-width: 0;
  padding: 2px 6px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

.promql-suggest-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.promql-suggest-detail {
  flex: 0 1 auto;
  overflow: hidden;
  color: #64748b;
  font-size: 11px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.promql-suggest-main strong {
  flex: 0 1 auto;
  overflow: hidden;
  color: #334155;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.promql-suggest-example {
  overflow: hidden;
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.4;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.promql-suggest-main strong .is-match {
  color: #2563eb;
  font-weight: 600;
}

.promql-inline-suggest-panel {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  height: calc(var(--promql-suggest-head-height) + var(--promql-suggest-item-height) * var(--promql-suggest-visible-rows) + 10px);
  min-height: 0;
  max-height: calc(var(--promql-suggest-head-height) + var(--promql-suggest-item-height) * var(--promql-suggest-visible-rows) + 10px);
  overflow: hidden;
  margin-top: 8px;
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.promql-inline-suggest-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  scrollbar-color: rgba(148, 163, 184, 0.56) transparent;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.promql-inline-suggest-list::-webkit-scrollbar {
  width: 6px;
}

.promql-inline-suggest-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.48);
}

.promql-inline-suggest-list::-webkit-scrollbar-track {
  background: transparent;
}

.promql-inline-suggest-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: var(--promql-suggest-head-height);
  min-height: var(--promql-suggest-head-height);
  padding: 7px 10px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.92);
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
}

.promql-inline-suggest-head small {
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.promql-inline-suggest-state {
  padding: 11px 12px;
  color: #64748b;
  font-size: 12px;
}

.promql-inline-suggest-item {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) minmax(170px, 0.46fr);
  align-items: center;
  column-gap: 8px;
  width: 100%;
  height: var(--promql-suggest-item-height);
  min-height: var(--promql-suggest-item-height);
  padding: 5px 10px;
  border: 0;
  border-bottom: 1px solid rgba(226, 232, 240, 0.72);
  color: #334155;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.promql-inline-suggest-item:last-child {
  border-bottom: 0;
}

.promql-inline-suggest-item:hover,
.promql-inline-suggest-item.active {
  background: #eff6ff;
}

.quick-promql-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px;
  align-self: stretch;
}

.quick-panel-count {
  color: #64748b;
  font-size: 12px;
}

.quick-panel-head,
.quick-search {
  flex: 0 0 auto;
}

.quick-search {
  margin-top: 8px;
}

.quick-category-tabs {
  display: flex;
  flex: 0 0 50px;
  gap: 6px;
  min-height: 50px;
  margin-bottom: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 8px 0 10px;
  scrollbar-color: rgba(148, 163, 184, 0.46) transparent;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.quick-category-tabs::-webkit-scrollbar {
  height: 6px;
}

.quick-category-tabs::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.46);
}

.quick-category-tabs::-webkit-scrollbar-track {
  background: transparent;
}

.quick-category-tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  height: 30px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  color: #475569;
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.quick-category-tab small {
  color: #94a3b8;
  font-size: 11px;
}

.quick-category-tab.active {
  color: #245bdb;
  border-color: rgba(51, 112, 255, 0.18);
  background: rgba(51, 112, 255, 0.08);
}

.quick-promql-list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  max-height: none;
  overflow: auto;
  padding-right: 8px;
  scrollbar-color: rgba(148, 163, 184, 0.56) transparent;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.quick-promql-list::-webkit-scrollbar {
  width: 6px;
  height: 0;
}

.quick-promql-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.48);
}

.quick-promql-list::-webkit-scrollbar-track {
  background: transparent;
}

.quick-promql-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.quick-promql-card:hover,
.quick-promql-card.active {
  border-color: rgba(51, 112, 255, 0.26);
  box-shadow: 0 10px 22px rgba(36, 91, 219, 0.08);
  transform: translateY(-1px);
}

.quick-promql-card p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.icon-action-btn {
  color: #64748b;
}

.metric-result-card {
  padding: 12px;
}

.metric-result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.metric-result-title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 150px;
}

.metric-result-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
  line-height: 1.2;
}

.metric-result-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.result-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  margin-bottom: 0;
}

.query-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 999px;
  color: #475569;
  background: rgba(248, 250, 252, 0.82);
  font-size: 10px;
  line-height: 1;
}

.query-pill--success {
  border-color: rgba(34, 197, 94, 0.18);
  background: rgba(240, 253, 244, 0.9);
  color: #15803d;
}

.query-pill--danger {
  border-color: rgba(239, 68, 68, 0.18);
  background: rgba(254, 242, 242, 0.92);
  color: #dc2626;
}

.metric-graph-shell {
  overflow: hidden;
  min-height: 420px;
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.metric-graph-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 420px;
  background: #ffffff;
}

.metric-graph-empty :deep(.el-empty__description p) {
  color: #64748b;
}

.metric-graph-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 34px;
  padding: 0 12px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.92);
  color: #0f172a;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.metric-graph-label {
  font-size: 12px;
  font-weight: 800;
}

.metric-graph-limit {
  color: #64748b;
  font-size: 11px;
  white-space: nowrap;
}

.metric-timeseries-chart {
  width: 100%;
  height: 342px;
}

.metric-series-board {
  border-top: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
}

.metric-series-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
  padding: 0 12px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
}

.metric-series-head small {
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.metric-series-list {
  max-height: 178px;
  overflow: auto;
  border-top: 1px solid rgba(226, 232, 240, 0.92);
  scrollbar-color: rgba(148, 163, 184, 0.56) transparent;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.metric-series-row {
  display: grid;
  grid-template-columns: 12px minmax(760px, 1fr) minmax(92px, auto);
  align-items: center;
  gap: 10px;
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-bottom: 1px solid rgba(226, 232, 240, 0.7);
  color: #334155;
  font-size: 12px;
  text-align: left;
  min-width: 100%;
  width: max-content;
  border-left: 0;
  border-right: 0;
  background: #fff;
  cursor: pointer;
}

.metric-series-row:last-child {
  border-bottom: 0;
}

.metric-series-row:hover {
  background: #f8fbff;
}

.metric-series-row.active {
  background: #eff6ff;
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.16);
}

.metric-series-color {
  width: 10px;
  height: 3px;
  border-radius: 999px;
}

.metric-series-label {
  overflow: visible;
  color: #334155;
  background: transparent;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
}

.metric-series-value {
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  text-align: right;
}

:global(.metric-tooltip) {
  min-width: 280px;
  max-width: min(560px, 72vw);
  padding: 8px 10px;
  color: #334155;
  font-family: Inter, "Helvetica Neue", Arial, sans-serif;
}

:global(.metric-tooltip-time) {
  margin-bottom: 8px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
}

:global(.metric-tooltip-series) {
  padding: 7px 0;
  border-top: 1px solid rgba(226, 232, 240, 0.92);
}

:global(.metric-tooltip-value-row) {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 5px;
}

:global(.metric-tooltip-dot) {
  width: 10px;
  height: 3px;
  border-radius: 999px;
}

:global(.metric-tooltip-value-row strong) {
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

:global(.metric-tooltip-value) {
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  font-weight: 700;
}

:global(.metric-tooltip pre) {
  max-height: 180px;
  overflow: auto;
  margin: 0;
  padding: 7px 8px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 6px;
  color: #334155;
  background: #f8fafc;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.45;
}

:global(.metric-tooltip-more) {
  padding-top: 7px;
  border-top: 1px solid rgba(226, 232, 240, 0.92);
  color: #64748b;
  font-size: 11px;
}

.source-name {
  color: #0f172a;
  font-weight: 700;
}

.ml-6 {
  margin-left: 6px;
}

.inline-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}

.inline-fields--small {
  grid-template-columns: 120px auto auto auto;
  align-items: center;
}

@media (max-width: 1280px) {
  .query-console {
    grid-template-columns: 1fr;
    height: auto;
  }

  .metric-query-left-card,
  .quick-promql-panel {
    height: auto;
    min-height: 0;
    max-height: none;
  }

  .metric-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .section-toolbar,
  .hero,
  .workbench-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-head {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .toolbar-desc {
    white-space: normal;
  }

  .query-console {
    grid-template-columns: 1fr;
  }

  .metric-query-unified-head,
  .metric-query-title-row,
  .metric-query-actions,
  .metric-filter-datasource-row {
    align-items: stretch;
    flex-direction: column;
  }

  .metric-query-actions {
    width: 100%;
  }

  .metric-filter-grid {
    grid-template-columns: 1fr;
  }

  .promql-field-head {
    grid-template-columns: 1fr auto;
  }

  .promql-field-label {
    grid-column: 1 / -1;
  }

  .promql-editor-shell {
    grid-column: 1;
  }

  .metric-result-head {
    align-items: stretch;
    flex-direction: column;
  }

  .result-strip {
    justify-content: flex-start;
  }

  .metric-timeseries-chart {
    height: 300px;
  }

  .metric-series-row {
    grid-template-columns: 12px minmax(220px, 1fr) minmax(80px, auto);
  }

  .metric-inline-filter,
  .metric-inline-filter--time {
    grid-template-columns: 1fr;
    row-gap: 4px;
  }

  .metric-filter-pills {
    justify-content: flex-start;
    min-width: 0;
    overflow-x: auto;
  }

  .workbench-toolbar-left,
  .workbench-toolbar-right,
  .inline-fields,
  .inline-fields--small {
    grid-template-columns: 1fr;
    flex-wrap: wrap;
  }

  .workbench-toolbar-left :deep(.el-select),
  .workbench-toolbar-left :deep(.el-input),
  .workbench-toolbar-left :deep(.el-date-editor),
  .workbench-toolbar-left :deep(.el-input-number),
  .workbench-toolbar-left :deep(.el-segmented) {
    width: 100% !important;
  }
}
</style>
