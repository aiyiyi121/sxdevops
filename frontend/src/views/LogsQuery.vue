<template>
  <div class="logs-query-page workbench-page-shell">
    <section class="hero panel hero-panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="log-header-icon"><el-icon><Search /></el-icon></span>
          <h2>日志中心</h2>
          <p class="page-desc inline-subtitle">支持 ELK、Loki、阿里云 SLS 日志查询。</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" @click="refreshLogDataSources" :loading="loadingSources || !!currentTab?.catalogLoading">
          <el-icon><RefreshRight /></el-icon>
          刷新数据源
        </el-button>
      </div>
    </section>

    <el-empty v-if="!dataSources.length && !loadingSources" description="还没有日志数据源，请先新增后再查询。">
      <el-button type="primary" @click="goToDatasources">去新增数据源</el-button>
    </el-empty>

    <template v-else>
      <section v-if="showQuerySessionTabs" class="tabs-panel tabs-panel--session">
        <div class="tabs-session-bar">
          <el-tabs v-model="activeTabName" type="card" class="session-tabs" @tab-remove="removeQueryTab">
            <el-tab-pane
              v-for="tab in queryTabs"
              :key="tab.id"
              :name="tab.id"
              :label="tab.title"
              :closable="queryTabs.length > 1"
            />
          </el-tabs>
          <el-button class="session-add-btn" size="small" type="primary" plain @click="addQueryTab">+ 新建查询</el-button>
        </div>
      </section>

      <div v-if="currentTab" class="query-layout">
        <section class="panel query-panel log-query-unified-card">
          <div class="log-query-unified-head">
            <div class="log-query-title-block">
              <div class="log-query-title-row">
                <h3>查询条件</h3>
              </div>
            </div>
            <div class="toolbar-actions toolbar-actions--compact">
              <el-button size="small" @click="saveFavorite(currentTab)" :disabled="!currentTab.datasourceId">收藏</el-button>
              <el-button size="small" @click="savedDialogVisible = true">历史/收藏</el-button>
              <el-button size="small" type="primary" @click="runQuery(currentTab)" :loading="currentTab.queryLoading">查询日志</el-button>
            </div>
          </div>

          <div class="log-query-provider-strip">
            <div class="log-filter-datasource-row">
              <span class="log-query-provider-label">数据源</span>
              <el-select
                v-model="currentTab.datasourceId"
                class="search-control log-datasource-control"
                size="small"
                filterable
                placeholder="请选择日志数据源"
                @change="handleDatasourceChange"
              >
                <el-option
                  v-for="item in dataSources"
                  :key="item.id"
                  :label="`${item.name}（${providerLabel(item.provider)}）`"
                  :value="item.id"
                />
              </el-select>
            </div>
          </div>

          <div class="search-panel search-panel--merged log-search-panel">
            <div class="log-filter-grid log-filter-grid--primary">
              <div class="log-inline-filter log-inline-filter--time">
                <span class="log-inline-filter__label">时间</span>
                <el-date-picker
                  v-model="currentTab.timeRange"
                  class="search-control log-time-control"
                  size="small"
                  type="datetimerange"
                  format="YYYY-MM-DD HH:mm:ss"
                  range-separator="至"
                  start-placeholder="开始时间"
                  end-placeholder="结束时间"
                  :shortcuts="logTimeRangeShortcuts"
                  @change="handleTimeRangeChange(currentTab)"
                />
              </div>
              <div class="log-inline-filter log-inline-filter--compact">
                <span class="log-inline-filter__label">数量</span>
                <el-input-number v-model="currentTab.limit" class="search-number" size="small" :min="20" :max="2000" :step="20" />
              </div>
            </div>

            <el-form label-position="left" label-width="168px" class="log-query-form compact-query-form">
              <template v-if="isLoki">
                <el-form-item label="标签过滤" class="loki-inline-item">
                  <div class="stack">
                    <div v-for="(filter, index) in currentTab.labelFilters" :key="index" class="filter-row">
                      <el-select v-model="filter.key" size="small" placeholder="标签" filterable @change="onLokiLabelKeyChange(currentTab, index)">
                        <el-option v-for="item in currentTab.lokiLabels" :key="item" :label="item" :value="item" />
                      </el-select>
                      <el-select v-model="filter.operator" size="small" class="operator-select" @change="syncLokiManualQuery(currentTab)">
                        <el-option label="=" value="=" />
                        <el-option label="!=" value="!=" />
                        <el-option label="=~" value="=~" />
                        <el-option label="!~" value="!~" />
                      </el-select>
                      <el-select v-model="filter.value" size="small" placeholder="值" filterable allow-create @change="syncLokiManualQuery(currentTab)" @focus="loadLokiLabelValues(currentTab, index)">
                        <el-option v-for="item in filter.options" :key="item" :label="item" :value="item" />
                      </el-select>
                      <div class="filter-row-actions">
                        <el-button text type="danger" class="filter-row-btn filter-row-btn--danger" @click="removeLabelFilter(currentTab, index)">移除</el-button>
                        <el-button
                          v-if="index === currentTab.labelFilters.length - 1"
                          text
                          type="primary"
                          class="filter-row-btn filter-row-btn--primary"
                          @click="addLabelFilter(currentTab)"
                        >
                          新增标签
                        </el-button>
                      </div>
                    </div>
                  </div>
                </el-form-item>
                <el-form-item label="内容检索" class="loki-inline-item loki-content-item">
                  <el-input v-model="currentTab.lokiContentQuery" size="small" placeholder="例如：error OR timeout" @input="handleLokiContentInput(currentTab)" />
                </el-form-item>
                <el-form-item class="syntax-form-item loki-syntax-item">
                  <template #label>
                    <span class="field-label-with-help">
                      <span>LogQL</span>
                      <el-button link type="primary" @click="openSyntaxHelp('loki')">查询语法帮助</el-button>
                    </span>
                  </template>
                  <el-input v-model="currentTab.lokiManualQuery" type="textarea" :rows="2" placeholder='{job="nginx"} |= "error"' />
                </el-form-item>
              </template>

              <template v-else-if="isElk">
                <div class="log-filter-grid log-filter-grid--secondary">
                  <div class="log-inline-filter">
                    <span class="log-inline-filter__label">索引</span>
                    <el-select v-model="currentTab.sourceName" class="search-control" size="small" placeholder="选择索引或输入索引模式" filterable allow-create clearable>
                      <el-option v-for="item in currentTab.catalogItems" :key="item.name" :label="item.name" :value="item.name" />
                    </el-select>
                  </div>
                </div>
                <div class="elk-quick-filters">
                  <div class="elk-quick-filters__head">
                    <span class="elk-quick-filters__title">快捷条件</span>
                    <div class="elk-presets">
                      <el-button
                        v-for="preset in elkPresets"
                        :key="preset.key"
                        size="small"
                        :type="currentTab.elkPreset === preset.key ? 'primary' : 'default'"
                        plain
                        @click="applyElkPreset(currentTab, preset.key)"
                      >
                        {{ preset.label }}
                      </el-button>
                      <el-button v-if="hasElkFilters(currentTab)" size="small" link @click="clearElkFilters(currentTab)">清除</el-button>
                    </div>
                  </div>
                  <div class="elk-quick-filters__grid">
                    <el-select v-model="currentTab.elkFilters.level" size="small" clearable placeholder="级别" @change="currentTab.elkPreset = ''">
                      <el-option label="ERROR" value="error" />
                      <el-option label="WARN" value="warning" />
                      <el-option label="INFO" value="info" />
                      <el-option label="DEBUG" value="debug" />
                    </el-select>
                    <el-input v-model.trim="currentTab.elkFilters.service" size="small" clearable placeholder="服务，如 payment-service" @input="currentTab.elkPreset = ''" />
                    <el-input v-model.trim="currentTab.elkFilters.host" size="small" clearable placeholder="主机，如 payment-02" @input="currentTab.elkPreset = ''" />
                    <el-input v-model.trim="currentTab.elkFilters.traceId" size="small" clearable placeholder="Trace ID" @input="currentTab.elkPreset = ''" />
                  </div>
                  <div v-if="elkGeneratedQuery(currentTab)" class="elk-query-preview">
                    <span>组合查询</span>
                    <code>{{ elkGeneratedQuery(currentTab) }}</code>
                  </div>
                </div>
                <el-form-item class="syntax-form-item">
                  <template #label>
                    <span class="field-label-with-help">
                      <span>Lucene 查询</span>
                      <el-button link type="primary" @click="openSyntaxHelp('elk')">查询语法帮助</el-button>
                    </span>
                  </template>
                  <el-input v-model="currentTab.queryText" type="textarea" :rows="2" placeholder='可选：补充自定义 Lucene，例如 status:500 OR message:"timeout"' />
                </el-form-item>
              </template>

              <template v-else-if="isSls">
                <div class="log-filter-grid log-filter-grid--secondary">
                  <div class="log-inline-filter">
                    <span class="log-inline-filter__label">Logstore</span>
                    <el-select v-model="currentTab.sourceName" class="search-control" size="small" placeholder="选择 Logstore" filterable allow-create clearable>
                      <el-option v-for="item in currentTab.catalogItems" :key="item.name" :label="item.name" :value="item.name" />
                    </el-select>
                  </div>
                </div>
                <div class="sls-query-presets">
                  <span>常用查询</span>
                  <el-button v-for="preset in slsPresets" :key="preset.query" size="small" plain :type="currentTab.queryText === preset.query ? 'primary' : 'default'" @click="currentTab.queryText = preset.query">
                    {{ preset.label }}
                  </el-button>
                  <el-button v-if="currentTab.queryText" size="small" link @click="currentTab.queryText = ''">清除</el-button>
                </div>
                <el-form-item class="syntax-form-item">
                  <template #label>
                    <span class="field-label-with-help">
                      <span>SLS 查询语句</span>
                      <el-button link type="primary" @click="openSyntaxHelp('sls')">查询语法帮助</el-button>
                    </span>
                  </template>
                  <el-input v-model="currentTab.queryText" type="textarea" :rows="2" placeholder='timeout OR auth error OR cache' />
                </el-form-item>
              </template>
            </el-form>

            <div class="search-summary-bar log-query-summary-bar">
              <span v-for="item in querySummaryPills" :key="item.label" class="query-pill">
                {{ item.label }}：{{ item.value }}
              </span>
            </div>
          </div>
        </section>

        <section class="panel info-panel compact-info-panel">
          <div class="panel-head slim-head">
            <h3>当前数据源</h3>
            <el-tag v-if="currentDataSource" :type="providerTagType(activeProvider)">{{ providerLabel(activeProvider) }}</el-tag>
          </div>

          <div v-if="currentDataSource" class="source-card compact-card compact-source-card">
            <div class="source-title-row source-title-row--tight">
              <strong class="source-title">{{ currentDataSource.name }}</strong>
              <div class="source-title-tags">
                <el-tag size="small" :type="currentDataSource.is_enabled ? 'success' : 'info'">{{ currentDataSource.is_enabled ? '启用' : '停用' }}</el-tag>
                <el-tag v-if="currentDataSource.is_default" size="small" type="warning">默认</el-tag>
              </div>
            </div>
            <div class="source-pills">
              <span v-if="currentDataSource.description" class="query-pill">描述：{{ currentDataSource.description }}</span>
            </div>
            <div class="summary-list summary-list--compact">
              <div class="summary-item" v-for="item in currentSummary" :key="item.label">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </div>

        </section>
      </div>

      <section v-if="currentTab" class="panel chart-panel compact-panel">
        <div class="panel-head slim-head">
          <h3>趋势图</h3>
          <span class="panel-meta-text">{{ currentResults.logs.length ? '按时间聚合展示' : '暂无图表数据' }}</span>
        </div>
        <div ref="chartRef" class="chart"></div>
      </section>

      <section v-if="currentTab" class="panel compact-panel workbench-fill-panel">
        <div class="panel-head slim-head">
          <h3>查询结果</h3>
          <div class="result-tags">
            <el-tag size="small" type="warning" effect="plain">总匹配 {{ currentResults.total || 0 }} 条</el-tag>
            <el-tag size="small" type="success" effect="plain">已返回 {{ currentResults.logs.length }} 条</el-tag>
            <el-tag size="small" type="primary" effect="plain">来源 {{ currentResults.source || '--' }}</el-tag>
            <el-tag size="small" type="info" effect="plain">耗时 {{ currentResults.took_ms != null ? `${currentResults.took_ms} ms` : '--' }}</el-tag>
            <el-tag size="small" type="danger" effect="plain">错误 {{ errorCount }}</el-tag>
            <el-tag v-if="currentResults.progress" size="small" type="info" effect="plain">{{ currentResults.progress }}</el-tag>
          </div>
        </div>
        <el-alert v-if="currentTab.errorMessage" :title="currentTab.errorMessage" type="error" show-icon :closable="false" />
        <div v-else-if="currentTab.queryLoading" class="empty-state compact-empty">正在查询日志...</div>
        <div v-else-if="!currentResults.logs.length" class="empty-state compact-empty">暂无日志结果，请调整条件后重试。</div>
        <div v-else class="log-list compact-list">
          <article v-for="(item, index) in currentResults.logs" :key="`${item.timestamp}-${index}`" class="log-card compact-log-card">
            <button class="log-main compact-log-main expandable" @click="toggleRow(currentTab, index)">
              <div class="log-head-row">
                <div class="log-meta-inline">
                  <span class="time-text">{{ formatTimestamp(item.timestamp) }}</span>
                  <el-tag size="small" :type="levelTagType(item)">{{ levelLabel(item) }}</el-tag>
                  <span class="source-text">{{ item.source }}</span>
                </div>
                <span class="expand-text">{{ isExpanded(currentTab, index) ? '收起' : '展开' }}</span>
              </div>
              <div class="log-message inline-message" v-html="formatMessage(item.message)"></div>
            </button>
            <div v-if="isExpanded(currentTab, index)" class="log-detail compact-detail">
              <div class="attribute-grid compact-grid">
                <div v-for="attr in displayAttributes(item.attributes)" :key="attr.key" class="attribute-card compact-attr">
                  <strong>{{ attr.key }}</strong>
                  <span>{{ attr.value }}</span>
                </div>
              </div>
              <div v-if="canJumpFromLog(item)" class="detail-actions">
                <span class="detail-actions__label">关联跳转</span>
                <div class="detail-actions__buttons">
                  <el-button v-if="canViewTracing && traceIdFromLog(item)" size="small" link type="primary" @click="openTraceFromLog(item)">链路追踪</el-button>
                  <el-button v-if="canViewGrafana && canOpenGrafanaFromLog(item)" size="small" link type="warning" @click="openGrafanaFromLog(item)">监控看板</el-button>
                </div>
              </div>
              <pre>{{ item.message }}</pre>
            </div>
          </article>
        </div>
      </section>
    </template>

    <el-dialog v-model="savedDialogVisible" title="查询历史与收藏" width="720px" class="saved-dialog">
      <div class="saved-dialog-head">
        <el-tabs v-model="savedTab" stretch class="saved-tabs">
          <el-tab-pane :label="`收藏条件（${favoriteItems.length}）`" name="favorites" />
          <el-tab-pane :label="`查询历史（${historyItems.length}）`" name="history" />
        </el-tabs>
        <el-button v-if="savedTab === 'history' && historyItems.length" text type="danger" @click="clearHistory">清空历史</el-button>
      </div>

      <div v-if="savedTab === 'favorites'">
        <div v-if="!favoriteItems.length" class="saved-empty">还没有收藏条件，可先配置一次再收藏。</div>
        <div v-else class="saved-list dialog-list">
          <article v-for="item in favoriteItems" :key="item.id" class="saved-item">
            <button class="saved-main" @click="applySavedQuery(item)">
              <strong>{{ item.title }}</strong>
              <span>{{ item.datasourceName || providerLabel(item.provider) }}</span>
              <p>{{ formatSavedSummary(item) }}</p>
            </button>
            <div class="saved-actions">
              <el-button text type="primary" @click.stop="applySavedQuery(item)">套用</el-button>
              <el-button text type="danger" @click.stop="removeFavorite(item.id)">删除</el-button>
            </div>
          </article>
        </div>
      </div>

      <div v-else>
        <div v-if="!historyItems.length" class="saved-empty">暂无查询历史，执行一次查询后会自动记录。</div>
        <div v-else class="saved-list dialog-list">
          <article v-for="item in historyItems" :key="item.id" class="saved-item">
            <button class="saved-main" @click="applySavedQuery(item)">
              <strong>{{ item.title }}</strong>
              <span>{{ item.datasourceName || providerLabel(item.provider) }} · {{ formatSavedTime(item.savedAt) }}</span>
              <p>{{ formatSavedSummary(item) }}</p>
            </button>
            <div class="saved-actions">
              <el-button text type="primary" @click.stop="applySavedQuery(item)">套用</el-button>
              <el-button text @click.stop="saveFavoriteFromItem(item)">收藏</el-button>
            </div>
          </article>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="helpDialogVisible" :title="currentHelpDoc.title" width="680px" class="syntax-help-dialog">
      <div class="syntax-help">
        <p class="syntax-desc">{{ currentHelpDoc.description }}</p>
        <div class="syntax-block">
          <strong>常用写法</strong>
          <ul>
            <li v-for="item in currentHelpDoc.examples" :key="item">
              <code>{{ item }}</code>
            </li>
          </ul>
        </div>
        <div class="syntax-block">
          <strong>使用说明</strong>
          <ul>
            <li v-for="item in currentHelpDoc.tips" :key="item">{{ item }}</li>
          </ul>
        </div>
        <el-link :href="currentHelpDoc.link" target="_blank" type="primary">查看官方查询语法文档</el-link>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import echarts from '@/lib/echarts'
import { ElMessage } from 'element-plus'
import { getLogDataSources, getLogProviderCatalog, queryLogs, resolveLogToGrafana, resolveLogToTrace } from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import { openRouteInNewTab } from '@/utils/router'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const LAST_DATASOURCE_KEY = 'logs:last-datasource-id'
const QUERY_HISTORY_KEY = 'logs:query-history'
const QUERY_FAVORITES_KEY = 'logs:query-favorites'
const DEFAULT_DATASOURCE_NAME = 'SLS 演示（上海）'
const MAX_HISTORY_ITEMS = 12
const MAX_FAVORITE_ITEMS = 8
const SYNTAX_HELP_DOCS = {
  loki: {
    title: 'Loki / LogQL 帮助',
    description: '适合基于标签筛选日志，再叠加关键字或正则过滤内容。',
    examples: [
      '{job="gateway"}',
      '{job="gateway", namespace="prod"} |= "timeout"',
      '{app=~"payment|checkout"} |~ "error|exception"',
    ],
    tips: [
      '花括号里写标签过滤，适合先缩小日志范围。',
      '|= 表示包含关键字，|~ 表示正则匹配。',
      '内容为空时，页面会根据上面的标签过滤自动生成基础 LogQL。',
    ],
    link: 'https://grafana.com/docs/loki/latest/query/',
  },
  elk: {
    title: 'ELK / Lucene 查询帮助',
    description: '适合按字段精确过滤、布尔组合和通配匹配 Elasticsearch 日志。',
    examples: [
      'service.name:"payment" AND level:error',
      'host.name:app-02 OR host.name:app-03',
      'message:timeout AND NOT env:staging',
    ],
    tips: [
      '字段查询推荐使用 field:value 或 field:"phrase"。',
      '支持 AND、OR、NOT 组合条件。',
      '可结合索引模式一起缩小查询范围。',
    ],
    link: 'https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-query-string-query',
  },
  sls: {
    title: '阿里云 SLS 查询帮助',
    description: '适合关键字检索、字段过滤和布尔查询，演示场景可直接搜 timeout、auth、cache。',
    examples: [
      'timeout',
      'level:ERROR AND service:auth-service',
      'host:sls-app-04 OR message:cache',
    ],
    tips: [
      '可直接搜关键字，也可写 field:value 形式。',
      '支持 AND、OR、NOT 组合条件。',
      '先选定 Logstore，再输入条件更接近真实 SLS 使用方式。',
    ],
    link: 'https://www.alibabacloud.com/help/en/sls/query-syntax/',
  },
}
const quickRanges = [
  { key: '10m', label: '最近10分钟', minutes: 10 },
  { key: '30m', label: '最近30分钟', minutes: 30 },
  { key: '1h', label: '最近1小时', minutes: 60 },
  { key: '6h', label: '最近6小时', minutes: 360 },
]
const elkPresets = [
  { key: 'errors', label: '仅看错误' },
  { key: 'warnings', label: '仅看告警' },
  { key: 'slow', label: '慢请求/超时' },
]
const slsPresets = [
  { label: '全部日志', query: '*' },
  { label: '错误日志', query: 'level:ERROR OR level:error' },
  { label: '超时请求', query: 'timeout OR 504 OR 超时' },
]
const logTimeRangeShortcuts = quickRanges.map((item) => ({
  text: item.label,
  value: () => {
    const end = new Date()
    const start = new Date(end.getTime() - item.minutes * 60 * 1000)
    return [start, end]
  },
}))

const loadingSources = ref(false)
const dataSources = ref([])
const queryTabs = ref([])
const activeTabName = ref('')
const showQuerySessionTabs = ref(false)
const historyItems = ref([])
const favoriteItems = ref([])
const savedTab = ref('favorites')
const savedDialogVisible = ref(false)
const helpDialogVisible = ref(false)
const helpProvider = ref('loki')
const chartRef = ref(null)
let chart = null
let tabSeed = 1

const currentTab = computed(() => queryTabs.value.find((item) => item.id === activeTabName.value) || null)
const currentDataSource = computed(() => dataSources.value.find((item) => item.id === currentTab.value?.datasourceId) || null)
const activeProvider = computed(() => currentDataSource.value?.provider || '')
const isLoki = computed(() => activeProvider.value === 'loki')
const isElk = computed(() => activeProvider.value === 'elk')
const isSls = computed(() => activeProvider.value === 'sls')
const currentResults = computed(() => currentTab.value?.results || { total: 0, source: '', took_ms: null, progress: '', logs: [] })
const errorCount = computed(() => currentResults.value.logs.filter((item) => normalizeLogLevel(item) === 'error').length)
const currentHelpDoc = computed(() => SYNTAX_HELP_DOCS[helpProvider.value] || SYNTAX_HELP_DOCS.loki)
const canViewTracing = computed(() => authStore.hasPermission('ops.trace.view'))
const canViewGrafana = computed(() => authStore.hasPermission('ops.grafana.view'))
const currentSummary = computed(() => {
  const config = currentDataSource.value?.config || {}
  if (activeProvider.value === 'loki') return [{ label: '接入地址', value: config.endpoint || '--' }]
  if (activeProvider.value === 'elk') {
    return [
      { label: '接入地址', value: config.endpoint || '--' },
      { label: '索引模式', value: config.index_pattern || '--' },
      { label: '时间字段', value: config.time_field || '@timestamp' },
    ]
  }
  if (activeProvider.value === 'sls') {
    return [
      { label: 'Project', value: config.project || '--' },
      { label: 'Logstore', value: config.logstore || '--' },
      { label: 'Endpoint', value: config.endpoint || '--' },
    ]
  }
  return []
})
const querySummaryPills = computed(() => {
  const items = []
  if (currentDataSource.value?.name) {
    items.push({ label: '数据源', value: currentDataSource.value.name })
  }
  if (activeProvider.value) {
    items.push({ label: '类型', value: providerLabel(activeProvider.value) })
  }
  if (currentTab.value?.sourceName) {
    items.push({ label: isElk.value ? '索引' : '来源', value: currentTab.value.sourceName })
  }
  if (isElk.value && hasElkFilters(currentTab.value)) {
    items.push({ label: '快捷条件', value: formatElkFilters(currentTab.value.elkFilters) })
  }
  items.push({ label: '时间', value: formatTimeRangeSummary(currentTab.value?.timeRange) })
  items.push({ label: '数量', value: String(currentTab.value?.limit || 0) })
  return items
})
watch(activeTabName, async () => {
  await nextTick()
  renderChart()
})

function defaultTimeRange(minutes = 60) {
  const end = new Date()
  return [new Date(end.getTime() - minutes * 60 * 1000), end]
}

function applyGrafanaRound(timestamp, unit) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp
  switch (unit) {
    case 's':
      date.setMilliseconds(0)
      break
    case 'm':
      date.setSeconds(0, 0)
      break
    case 'h':
      date.setMinutes(0, 0, 0)
      break
    case 'd':
      date.setHours(0, 0, 0, 0)
      break
    case 'w': {
      const day = date.getDay() || 7
      date.setDate(date.getDate() - day + 1)
      date.setHours(0, 0, 0, 0)
      break
    }
    case 'M':
      date.setDate(1)
      date.setHours(0, 0, 0, 0)
      break
    case 'y':
      date.setMonth(0, 1)
      date.setHours(0, 0, 0, 0)
      break
    default:
      break
  }
  return date.getTime()
}

function parseGrafanaRelativeTime(value) {
  const raw = String(value || '').trim()
  if (!raw || !raw.startsWith('now')) return Number.NaN
  if (raw === 'now') return Date.now()

  const match = raw.match(/^now(?:(?<sign>[+-])(?<amount>\d+)(?<unit>[smhdwMy]))?(?:\/(?<round>[smhdwMy]))?$/)
  if (!match) return Number.NaN

  let timestamp = Date.now()
  const { sign, amount, unit, round } = match.groups || {}
  if (sign && amount && unit) {
    const multipliers = {
      s: 1000,
      m: 60 * 1000,
      h: 60 * 60 * 1000,
      d: 24 * 60 * 60 * 1000,
      w: 7 * 24 * 60 * 60 * 1000,
      M: 30 * 24 * 60 * 60 * 1000,
      y: 365 * 24 * 60 * 60 * 1000,
    }
    const delta = Number(amount) * (multipliers[unit] || 0)
    timestamp += sign === '-' ? -delta : delta
  }

  if (round) {
    timestamp = applyGrafanaRound(timestamp, round)
  }

  return timestamp
}

function toTimestampMs(value) {
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim()) {
    const numeric = Number(value)
    if (!Number.isNaN(numeric)) return numeric
    const relative = parseGrafanaRelativeTime(value)
    if (!Number.isNaN(relative)) return relative
    const parsed = new Date(value).getTime()
    if (!Number.isNaN(parsed)) return parsed
  }
  return Date.now()
}

function normalizeTimeRange(range) {
  if (!Array.isArray(range) || range.length !== 2) return defaultTimeRange()
  return range.map((item) => {
    if (item instanceof Date) return item
    return new Date(toTimestampMs(item))
  })
}

function makeLabelFilter() {
  return { key: '', operator: '=', value: '', options: [] }
}

function makeElkFilters(filters = {}) {
  return {
    level: filters.level || '',
    service: filters.service || '',
    host: filters.host || '',
    traceId: filters.traceId || '',
  }
}

function emptyResults() {
  return { provider: '', source: '', total: 0, took_ms: null, progress: '', logs: [] }
}

function createQueryTab(seed = {}) {
  const serial = tabSeed++
  return reactive({
    id: `query-tab-${Date.now()}-${serial}`,
    title: seed.title || `查询 ${serial}`,
    datasourceId: seed.datasourceId || '',
    timeRange: normalizeTimeRange(seed.timeRange || defaultTimeRange()),
    quickRange: seed.quickRange || '1h',
    limit: seed.limit || 200,
    sourceName: seed.sourceName || '',
    queryText: seed.queryText || '',
    elkFilters: makeElkFilters(seed.elkFilters),
    elkPreset: seed.elkPreset || '',
    lokiLabels: [],
    labelFilters: [makeLabelFilter()],
    lokiContentQuery: '',
    lokiManualQuery: '',
    lokiQuerySuffix: '',
    catalogItems: [],
    catalogLoading: false,
    queryLoading: false,
    errorMessage: '',
    results: emptyResults(),
    expandedRows: [],
  })
}

function providerLabel(provider) {
  return {
    loki: 'Loki',
    elk: 'ELK / Elasticsearch',
    sls: '阿里云 SLS',
  }[provider] || provider
}

function providerTagType(provider) {
  return {
    loki: 'success',
    elk: 'warning',
    sls: 'info',
  }[provider] || 'info'
}

function goToDatasources() {
  router.push('/logs/datasources')
}

function openSyntaxHelp(provider) {
  helpProvider.value = provider || activeProvider.value || 'loki'
  helpDialogVisible.value = true
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatTimeRangeSummary(range) {
  if (!Array.isArray(range) || range.length !== 2) return '--'
  const [start, end] = normalizeTimeRange(range)
  const startText = `${String(start.getHours()).padStart(2, '0')}:${String(start.getMinutes()).padStart(2, '0')}`
  const endText = `${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`
  return `${startText} - ${endText}`
}

function getPreferredDatasourceId() {
  const defaultSource = dataSources.value.find((item) => item.is_default)
  if (defaultSource) return defaultSource.id
  const saved = Number(localStorage.getItem(LAST_DATASOURCE_KEY))
  if (saved && dataSources.value.some((item) => item.id === saved)) return saved
  const shanghai = dataSources.value.find((item) => item.name === DEFAULT_DATASOURCE_NAME)
  if (shanghai) return shanghai.id
  return dataSources.value[0]?.id || null
}

function getPreferredDatasourceByProvider(provider) {
  if (!provider) {
    return dataSources.value.find((item) => item.id === getPreferredDatasourceId()) || dataSources.value[0] || null
  }
  const preferred = dataSources.value.find((item) => item.provider === provider && item.is_default)
    || dataSources.value.find((item) => item.provider === provider)
  return preferred || dataSources.value.find((item) => item.id === getPreferredDatasourceId()) || dataSources.value[0] || null
}

function getDatasourceById(id) {
  const value = Number(id)
  if (!value) return null
  return dataSources.value.find((item) => item.id === value) || null
}

function persistDatasource(id) {
  if (id) localStorage.setItem(LAST_DATASOURCE_KEY, String(id))
}

function loadSavedQueries() {
  try {
    historyItems.value = JSON.parse(localStorage.getItem(QUERY_HISTORY_KEY) || '[]')
  } catch {
    historyItems.value = []
  }

  try {
    favoriteItems.value = JSON.parse(localStorage.getItem(QUERY_FAVORITES_KEY) || '[]')
  } catch {
    favoriteItems.value = []
  }
}

function persistSavedQueries() {
  localStorage.setItem(QUERY_HISTORY_KEY, JSON.stringify(historyItems.value))
  localStorage.setItem(QUERY_FAVORITES_KEY, JSON.stringify(favoriteItems.value))
}

function datasourceNameById(id) {
  return dataSources.value.find((item) => item.id === id)?.name || ''
}

function buildSavedTitle(snapshot) {
  const text = (
    snapshot.provider === 'loki'
      ? snapshot.lokiManualQuery || snapshot.lokiContentQuery
      : snapshot.queryText || formatElkFilters(snapshot.elkFilters) || snapshot.sourceName
  )?.trim()
  return text ? text.slice(0, 30) : `${providerLabel(snapshot.provider)} 查询`
}

function createSnapshot(tab) {
  const datasource = dataSources.value.find((item) => item.id === tab.datasourceId)
  return {
    provider: datasource?.provider || '',
    datasourceId: tab.datasourceId,
    datasourceName: datasource?.name || '',
    sourceName: tab.sourceName || '',
    queryText: tab.queryText || '',
    elkFilters: makeElkFilters(tab.elkFilters),
    elkPreset: tab.elkPreset || '',
    quickRange: tab.quickRange || '',
    timeRange: normalizeTimeRange(tab.timeRange).map((item) => item.getTime()),
    limit: tab.limit,
    lokiContentQuery: tab.lokiContentQuery || '',
    lokiManualQuery: tab.lokiManualQuery || '',
    labelFilters: (tab.labelFilters || []).map((item) => ({
      key: item.key || '',
      operator: item.operator || '=',
      value: item.value || '',
    })),
  }
}

function snapshotFingerprint(snapshot) {
  return JSON.stringify({
    provider: snapshot.provider,
    datasourceId: snapshot.datasourceId,
    sourceName: snapshot.sourceName,
    queryText: snapshot.queryText,
    elkFilters: snapshot.elkFilters,
    elkPreset: snapshot.elkPreset,
    quickRange: snapshot.quickRange,
    timeRange: snapshot.timeRange,
    limit: snapshot.limit,
    lokiContentQuery: snapshot.lokiContentQuery,
    lokiManualQuery: snapshot.lokiManualQuery,
    labelFilters: snapshot.labelFilters,
  })
}

function formatSavedSummary(item) {
  const source = item.sourceName ? `来源：${item.sourceName}` : '来源：默认'
  const query = item.provider === 'loki'
    ? item.lokiManualQuery || item.lokiContentQuery || '未填写关键字'
    : item.queryText || formatElkFilters(item.elkFilters) || '未填写关键字'
  return `${source} · 条数：${item.limit} · 条件：${query}`
}

function formatSavedTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function updateHistory(snapshot) {
  const fingerprint = snapshotFingerprint(snapshot)
  historyItems.value = [
    { ...snapshot, id: `history-${Date.now()}`, title: buildSavedTitle(snapshot), savedAt: new Date().toISOString(), fingerprint },
    ...historyItems.value.filter((item) => item.fingerprint !== fingerprint),
  ].slice(0, MAX_HISTORY_ITEMS)
  persistSavedQueries()
}

function updateFavorites(snapshot, silent = false) {
  const fingerprint = snapshotFingerprint(snapshot)
  const exists = favoriteItems.value.some((item) => item.fingerprint === fingerprint)
  favoriteItems.value = [
    { ...snapshot, id: exists ? favoriteItems.value.find((item) => item.fingerprint === fingerprint)?.id : `favorite-${Date.now()}`, title: buildSavedTitle(snapshot), savedAt: new Date().toISOString(), fingerprint },
    ...favoriteItems.value.filter((item) => item.fingerprint !== fingerprint),
  ].slice(0, MAX_FAVORITE_ITEMS)
  persistSavedQueries()
  if (!silent) ElMessage.success(exists ? '已更新收藏条件' : '已收藏当前查询条件')
}

async function fetchDataSources() {
  loadingSources.value = true
  try {
    const response = await getLogDataSources({ is_enabled: true })
    dataSources.value = Array.isArray(response) ? response : response.results || []
  } finally {
    loadingSources.value = false
  }
}

async function refreshLogDataSources() {
  await fetchDataSources()
  if (currentTab.value?.datasourceId) {
    await loadCatalog(currentTab.value)
  }
}

function resetTabState(tab) {
  tab.sourceName = ''
  tab.queryText = ''
  tab.elkFilters = makeElkFilters()
  tab.elkPreset = ''
  tab.lokiLabels = []
  tab.catalogItems = []
  tab.labelFilters = [makeLabelFilter()]
  tab.lokiContentQuery = ''
  tab.lokiManualQuery = ''
  tab.lokiQuerySuffix = ''
  tab.errorMessage = ''
  tab.results = emptyResults()
  tab.expandedRows = []
}

function routeTraceId() {
  const raw = route.query.traceId
  return typeof raw === 'string' ? raw.trim() : ''
}

function normalizeTraceIdForLogQuery(traceId) {
  const value = String(traceId || '').trim()
  if (/^[0-9a-fA-F]{1,31}$/.test(value)) {
    return value.padStart(32, '0')
  }
  return value
}

function routeTraceService() {
  const raw = route.query.service
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeTraceNamespace() {
  const raw = route.query.namespace
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeTraceTitle() {
  const raw = route.query.title
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeTraceProvider() {
  const raw = route.query.logProvider || route.query.provider
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeLogDatasourceId() {
  const raw = route.query.logDatasourceId
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeLokiQuery() {
  const raw = route.query.lokiQuery
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeTimeRange(fallbackMinutes = 60) {
  const from = toTimestampMs(route.query.from)
  const to = toTimestampMs(route.query.to)
  if (route.query.from && route.query.to && Number.isFinite(from) && Number.isFinite(to)) {
    return normalizeTimeRange([from, to])
  }
  return defaultTimeRange(fallbackMinutes)
}

function unescapeLogValue(value) {
  return String(value || '').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
}

function parseLokiSelector(query) {
  const text = String(query || '').trim()
  const selectorMatch = text.match(/^\{([^}]*)\}/)
  if (!selectorMatch) return []
  const filters = []
  const pattern = /([A-Za-z_][\w.:-]*)\s*(=~|!~|!=|=)\s*"((?:\\.|[^"])*)"/g
  let match = pattern.exec(selectorMatch[1])
  while (match) {
    filters.push({
      ...makeLabelFilter(),
      key: match[1],
      operator: match[2],
      value: unescapeLogValue(match[3]),
    })
    match = pattern.exec(selectorMatch[1])
  }
  return filters
}

function parseLokiContentFilter(query) {
  const match = String(query || '').match(/\|\s*(?:=|~)\s*"((?:\\.|[^"])*)"/)
  return match ? unescapeLogValue(match[1]) : ''
}

function parseLokiQuerySuffix(query) {
  const text = String(query || '').trim()
  const selectorMatch = text.match(/^\{[^}]*\}/)
  return selectorMatch ? text.slice(selectorMatch[0].length).trimStart() : ''
}

function routeLogKeyword() {
  const raw = route.query.keyword
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeLogSource() {
  const raw = route.query.source
  return typeof raw === 'string' ? raw.trim() : ''
}

function routeLogTitle() {
  const raw = route.query.title
  return typeof raw === 'string' ? raw.trim() : ''
}

function buildTraceLogTitle(traceId) {
  if (routeTraceTitle()) return routeTraceTitle()
  if (routeTraceService()) return `Trace 日志 ${routeTraceService().slice(0, 18)}`
  return `Trace ${traceId.slice(0, 8)}`
}

function buildKeywordLogTitle(keyword) {
  return routeLogTitle() || `检索 ${keyword.slice(0, 10)}`
}

function buildLokiRouteTitle(query) {
  const service = routeTraceService()
  if (routeLogTitle()) return routeLogTitle()
  if (service) return `看板日志 ${service.slice(0, 10)}`
  return `看板日志 ${query.slice(0, 10)}`
}

function buildTraceRouteQuery(datasource, traceId) {
  const provider = datasource?.provider || ''
  const service = routeTraceService()
  const namespace = routeTraceNamespace()
  const normalizedTraceId = normalizeTraceIdForLogQuery(traceId)
  const escapedTraceId = escapeLogValue(normalizedTraceId)
  const escapedService = escapeLogValue(service)
  const escapedNamespace = escapeLogValue(namespace)

  if (provider === 'loki') {
    const explicitQuery = routeLokiQuery()
    if (explicitQuery) return explicitQuery
    const selector = []
    if (namespace) selector.push(`namespace="${escapedNamespace}"`)
    if (service) selector.push(`container="${escapedService}"`)
    if (!selector.length && service) {
      selector.push(`service_name="${escapedService}"`)
    }
    if (!selector.length) return ''
    return `{${selector.join(',')}} |= "${escapedTraceId}"`
  }

  if (provider === 'elk') {
    const traceClause = `(trace_id:"${escapedTraceId}" OR traceId:"${escapedTraceId}" OR trace.id:"${escapedTraceId}" OR otelTraceID:"${escapedTraceId}")`
    const filters = [traceClause]
    if (service) {
      filters.push(`(service.name:"${escapedService}" OR service_name:"${escapedService}" OR service:"${escapedService}" OR container:"${escapedService}" OR app:"${escapedService}")`)
    }
    if (namespace) {
      filters.push(`(service.namespace:"${escapedNamespace}" OR service_namespace:"${escapedNamespace}" OR namespace:"${escapedNamespace}")`)
    }
    return filters.join(' AND ')
  }

  if (provider === 'sls') {
    const filters = [`trace_id:"${escapedTraceId}"`]
    if (service) {
      filters.push(`(service:"${escapedService}" OR service_name:"${escapedService}" OR container:"${escapedService}" OR app:"${escapedService}")`)
    }
    if (namespace) {
      filters.push(`(service_namespace:"${escapedNamespace}" OR namespace:"${escapedNamespace}")`)
    }
    return filters.join(' AND ')
  }

  return normalizedTraceId
}

function traceServiceFromLog(item) {
  const attributes = item?.attributes || {}
  return [
    attributes.workload,
    attributes.workload_name,
    attributes.workloadName,
    attributes['k8s.workload.name'],
    attributes.kubernetes_workload_name,
    attributes.deployment,
    attributes.deployment_name,
    attributes['k8s.deployment.name'],
    attributes.service_name,
    attributes.service,
    attributes['service.name'],
    attributes.serviceName,
    attributes.app,
    attributes.application,
    attributes.container,
    attributes.container_name,
    attributes['k8s.container.name'],
    item?.source,
  ].find((value) => typeof value === 'string' && value.trim()) || ''
}

function workloadTypeFromLog(item) {
  const attributes = item?.attributes || {}
  const raw = [
    attributes.workload_type,
    attributes.workloadType,
    attributes['workload.type'],
    attributes['k8s.workload.type'],
    attributes.kubernetes_workload_type,
    attributes.controller_kind,
    attributes.owner_kind,
    attributes.kind,
  ].find((value) => typeof value === 'string' && value.trim()) || 'deployment'
  return String(raw).replace(/^apps\//i, '').toLowerCase()
}

function traceNamespaceFromLog(item) {
  const attributes = item?.attributes || {}
  return [
    attributes.service_namespace,
    attributes.serviceNamespace,
    attributes['service.namespace'],
    attributes.namespace,
    attributes['k8s.namespace.name'],
    attributes.kubernetes_namespace_name,
  ].find((value) => typeof value === 'string' && value.trim()) || ''
}

function logItemNearRange(item, minutes = 30) {
  const center = toTimestampMs(item?.timestamp)
  const span = minutes * 60 * 1000
  return [center - span, center + span]
}

function traceIdFromLog(item) {
  const attributes = item?.attributes || {}
  const direct = [
    attributes.trace_id,
    attributes.traceId,
    attributes.traceID,
    attributes['trace.id'],
    attributes.otelTraceID,
  ].find((value) => typeof value === 'string' && value.trim())
  if (direct) return direct.trim()
  const message = String(item?.message || '')
  const match = message.match(/(?:trace_id|traceId|traceID|trace\.id)["']?\s*[:=]\s*["']?([0-9a-fA-F]{16,32})/)
  return match?.[1] || ''
}

function canOpenGrafanaFromLog(item) {
  return Boolean(traceServiceFromLog(item))
}

function canJumpFromLog(item) {
  return Boolean((canViewTracing.value && traceIdFromLog(item)) || (canViewGrafana.value && canOpenGrafanaFromLog(item)))
}

async function applyTraceRoutePreset(force = false) {
  const traceId = routeTraceId()
  if (!traceId || !dataSources.value.length) return false
  const currentFingerprint = JSON.stringify({
    traceId,
    service: routeTraceService(),
    namespace: routeTraceNamespace(),
    title: routeTraceTitle(),
    provider: routeTraceProvider(),
    logDatasourceId: routeLogDatasourceId(),
    lokiQuery: routeLokiQuery(),
    source: route.query.source || '',
    from: route.query.from || '',
    to: route.query.to || '',
  })
  if (!force && currentTab.value?.routeFingerprint === currentFingerprint) return false

  let tab = currentTab.value
  if (!tab) {
    tab = createQueryTab()
    queryTabs.value = [tab]
    activeTabName.value = tab.id
  }

  const datasource = getDatasourceById(routeLogDatasourceId()) || getPreferredDatasourceByProvider(routeTraceProvider())
  if (!datasource) return false

  tab.title = buildTraceLogTitle(traceId)
  tab.datasourceId = datasource.id
  tab.timeRange = routeTimeRange(Number(route.query.window || 60))
  tab.quickRange = ''
  tab.limit = 200
  tab.routeFingerprint = currentFingerprint
  await prepareTab(tab)

  if (datasource.provider === 'loki') {
    applyLokiQueryToControls(tab, buildTraceRouteQuery(datasource, traceId), traceId)
  } else {
    tab.queryText = buildTraceRouteQuery(datasource, traceId)
  }

  if (typeof route.query.source === 'string' && route.query.source.trim()) {
    tab.sourceName = route.query.source.trim()
  }

  if (route.query.autoRun !== '0') {
    await runQuery(tab)
  }
  return true
}

async function applyLokiRoutePreset(force = false) {
  const lokiQuery = routeLokiQuery()
  if (!lokiQuery || routeTraceId() || !dataSources.value.length) return false
  const currentFingerprint = JSON.stringify({
    lokiQuery,
    provider: routeTraceProvider(),
    logDatasourceId: routeLogDatasourceId(),
    window: route.query.window || '',
    autoRun: route.query.autoRun || '',
    from: route.query.from || '',
    to: route.query.to || '',
  })
  if (!force && currentTab.value?.routeFingerprint === currentFingerprint) return false

  let tab = currentTab.value
  if (!tab) {
    tab = createQueryTab()
    queryTabs.value = [tab]
    activeTabName.value = tab.id
  }

  const datasource = getDatasourceById(routeLogDatasourceId()) || getPreferredDatasourceByProvider(routeTraceProvider() || 'loki')
  if (!datasource) return false

  tab.title = buildLokiRouteTitle(lokiQuery)
  tab.datasourceId = datasource.id
  tab.timeRange = routeTimeRange(Number(route.query.window || 60))
  tab.quickRange = ''
  tab.limit = 200
  tab.routeFingerprint = currentFingerprint
  await prepareTab(tab)

  if (datasource.provider === 'loki') {
    applyLokiQueryToControls(tab, lokiQuery)
  } else {
    tab.queryText = lokiQuery
  }

  if (route.query.autoRun !== '0') {
    await runQuery(tab)
  }
  return true
}

async function applyKeywordRoutePreset(force = false) {
  const keyword = routeLogKeyword()
  if (!keyword || routeTraceId() || !dataSources.value.length) return false
  const currentFingerprint = JSON.stringify({
    keyword,
    provider: routeTraceProvider(),
    source: routeLogSource(),
    title: routeLogTitle(),
    window: route.query.window || '',
  })
  if (!force && currentTab.value?.routeFingerprint === currentFingerprint) return false

  let tab = currentTab.value
  if (!tab) {
    tab = createQueryTab()
    queryTabs.value = [tab]
    activeTabName.value = tab.id
  }

  const datasource = getPreferredDatasourceByProvider(routeTraceProvider())
  if (!datasource) return false

  tab.title = buildKeywordLogTitle(keyword)
  tab.datasourceId = datasource.id
  tab.timeRange = defaultTimeRange(Number(route.query.window || 60))
  tab.quickRange = ''
  tab.limit = 200
  tab.routeFingerprint = currentFingerprint
  await prepareTab(tab)

  if (datasource.provider === 'loki') {
    tab.lokiContentQuery = keyword
    syncLokiManualQuery(tab)
  } else {
    tab.queryText = keyword
  }

  if (routeLogSource()) {
    tab.sourceName = routeLogSource()
  }

  if (route.query.autoRun !== '0') {
    await runQuery(tab)
  }
  return true
}

async function openTraceFromLog(item) {
  const traceId = traceIdFromLog(item)
  if (!traceId) return
  const service = traceServiceFromLog(item)
  const [from, to] = logItemNearRange(item)
  try {
    const resolved = await resolveLogToTrace({
      trace_id: traceId,
      log_datasource_id: currentTab.value?.datasourceId,
      attributes: item.attributes || {},
      message: item.message || '',
    })
    openRouteInNewTab(router, {
      path: '/observability/tracing',
      query: {
        traceId: resolved.trace_id || traceId,
        service: service || undefined,
        provider: resolved.tracing_datasource?.provider || undefined,
        datasourceId: resolved.tracing_datasource?.id ? String(resolved.tracing_datasource.id) : undefined,
        from,
        to,
      },
    })
  } catch {
    openRouteInNewTab(router, {
      path: '/observability/tracing',
      query: {
        traceId,
        service: service || undefined,
        from,
        to,
      },
    })
  }
}

async function openGrafanaFromLog(item) {
  const service = traceServiceFromLog(item)
  const namespace = traceNamespaceFromLog(item)
  const workloadType = workloadTypeFromLog(item)
  if (!service) return
  const [from, to] = logItemNearRange(item)
  try {
    const resolved = await resolveLogToGrafana({
      log_datasource_id: currentTab.value?.datasourceId,
      dashboard_key: 'Kubernetes / Compute Resources / Workload',
      ignore_trace_id: true,
      attributes: {
        ...(item.attributes || {}),
        workload: service,
        workload_type: workloadType,
        namespace: namespace || item.attributes?.namespace,
      },
      message: item.message || '',
      from,
      to,
    })
    openRouteInNewTab(router, {
      path: '/observability/grafana',
      query: {
        ...(resolved.query || {}),
        dashboard: resolved.query?.dashboard || 'Kubernetes / Compute Resources / Workload',
        service: service || undefined,
        'var-workload': resolved.query?.['var-workload'] || service || undefined,
        'var-workload_type': resolved.query?.['var-workload_type'] || workloadType || undefined,
        'var-namespace': resolved.query?.['var-namespace'] || namespace || undefined,
        from,
        to,
        fullscreen: '1',
      },
    })
  } catch {
    openRouteInNewTab(router, {
      path: '/observability/grafana',
      query: {
        dashboard: 'Kubernetes / Compute Resources / Workload',
        service: service || undefined,
        'var-workload': service || undefined,
        'var-workload_type': workloadType || undefined,
        'var-namespace': namespace || undefined,
        source: 'log',
        from,
        to,
        fullscreen: '1',
      },
    })
  }
}

async function initializeTabs() {
  if (!dataSources.value.length) return
  if (!queryTabs.value.length) {
    const tab = createQueryTab({ datasourceId: getPreferredDatasourceId() })
    queryTabs.value = [tab]
    activeTabName.value = tab.id
    persistDatasource(tab.datasourceId)
    await prepareTab(tab)
    return
  }
  queryTabs.value.forEach((tab) => {
    if (!dataSources.value.some((item) => item.id === tab.datasourceId)) {
      tab.datasourceId = getPreferredDatasourceId()
    }
  })
}

async function prepareTab(tab) {
  resetTabState(tab)
  if (!tab.datasourceId) return
  persistDatasource(tab.datasourceId)
  await loadCatalog(tab)
  syncLokiManualQuery(tab)
}

function saveFavorite(tab) {
  if (!tab?.datasourceId) return ElMessage.warning('请先选择日志数据源')
  updateFavorites(createSnapshot(tab))
}

function saveFavoriteFromItem(item) {
  updateFavorites({
    ...item,
    datasourceName: datasourceNameById(item.datasourceId) || item.datasourceName || '',
  })
}

function removeFavorite(id) {
  favoriteItems.value = favoriteItems.value.filter((item) => item.id !== id)
  persistSavedQueries()
}

function clearHistory() {
  historyItems.value = []
  persistSavedQueries()
}

async function applySavedQuery(item) {
  if (!currentTab.value) return
  const datasourceId = dataSources.value.some((source) => source.id === item.datasourceId)
    ? item.datasourceId
    : getPreferredDatasourceId()
  currentTab.value.datasourceId = datasourceId
  currentTab.value.timeRange = normalizeTimeRange(item.timeRange)
  currentTab.value.quickRange = item.quickRange || ''
  currentTab.value.limit = item.limit || 200
  await prepareTab(currentTab.value)
  currentTab.value.sourceName = item.sourceName || ''
  currentTab.value.queryText = item.queryText || ''
  currentTab.value.elkFilters = makeElkFilters(item.elkFilters)
  currentTab.value.elkPreset = item.elkPreset || ''
  currentTab.value.lokiContentQuery = item.lokiContentQuery || ''
  currentTab.value.labelFilters = (item.labelFilters || []).length
    ? item.labelFilters.map((filter) => ({ ...makeLabelFilter(), ...filter }))
    : [makeLabelFilter()]
  currentTab.value.lokiManualQuery = item.lokiManualQuery || ''
  if (!currentTab.value.lokiManualQuery) {
    syncLokiManualQuery(currentTab.value)
  }
  savedDialogVisible.value = false
  ElMessage.success('已套用查询条件')
}

function addQueryTab() {
  const base = currentTab.value
    ? {
        datasourceId: currentTab.value.datasourceId,
        timeRange: currentTab.value.timeRange,
        quickRange: currentTab.value.quickRange,
        limit: currentTab.value.limit,
        elkFilters: currentTab.value.elkFilters,
        elkPreset: currentTab.value.elkPreset,
      }
    : { datasourceId: getPreferredDatasourceId() }
  const tab = createQueryTab(base)
  queryTabs.value.push(tab)
  activeTabName.value = tab.id
  prepareTab(tab)
}

function removeQueryTab(targetName) {
  if (queryTabs.value.length <= 1) return
  const index = queryTabs.value.findIndex((item) => item.id === targetName)
  if (index === -1) return
  queryTabs.value.splice(index, 1)
  if (activeTabName.value === targetName) {
    activeTabName.value = queryTabs.value[Math.max(index - 1, 0)]?.id || ''
  }
}

async function handleDatasourceChange() {
  if (!currentTab.value) return
  await prepareTab(currentTab.value)
  await nextTick()
  renderChart()
}

function applyQuickRange(tab, option) {
  tab.quickRange = option.key
  tab.timeRange = defaultTimeRange(option.minutes)
  if (tab.datasourceId) loadCatalog(tab)
}

function handleTimeRangeChange(tab) {
  tab.quickRange = ''
  if (tab.datasourceId && tab.datasourceId === currentTab.value?.datasourceId && isLoki.value) {
    loadCatalog(tab)
  }
}

async function loadCatalog(tab = currentTab.value) {
  if (!tab || !tab.datasourceId) return
  tab.catalogLoading = true
  try {
    const datasource = dataSources.value.find((item) => item.id === tab.datasourceId)
    if (!datasource) return

    if (datasource.provider === 'loki') {
      const response = await getLogProviderCatalog('loki', {
        datasource_id: tab.datasourceId,
        action: 'labels',
        start_ms: toTimestampMs(tab.timeRange[0]),
        end_ms: toTimestampMs(tab.timeRange[1]),
      })
      tab.lokiLabels = response.items || []
    } else if (datasource.provider === 'elk') {
      const response = await getLogProviderCatalog('elk', {
        datasource_id: tab.datasourceId,
        action: 'sources',
        index_pattern: datasource.config?.index_pattern,
      })
      tab.catalogItems = response.items || []
      if (!tab.sourceName) {
        tab.sourceName = datasource.config?.index_pattern || tab.catalogItems[0]?.name || ''
      }
    } else if (datasource.provider === 'sls') {
      const response = await getLogProviderCatalog('sls', {
        datasource_id: tab.datasourceId,
        action: 'sources',
      })
      tab.catalogItems = response.items || []
      if (!tab.sourceName) {
        tab.sourceName = datasource.config?.logstore || tab.catalogItems[0]?.name || ''
      }
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '加载目录失败')
  } finally {
    tab.catalogLoading = false
  }
}

function addLabelFilter(tab) {
  tab.labelFilters.push(makeLabelFilter())
  syncLokiManualQuery(tab)
}

function removeLabelFilter(tab, index) {
  tab.labelFilters.splice(index, 1)
  if (!tab.labelFilters.length) addLabelFilter(tab)
  syncLokiManualQuery(tab)
}

async function onLokiLabelKeyChange(tab, index) {
  tab.labelFilters[index].value = ''
  tab.labelFilters[index].options = []
  syncLokiManualQuery(tab)
  await loadLokiLabelValues(tab, index)
}

async function loadLokiLabelValues(tab, index) {
  const filter = tab.labelFilters[index]
  if (!filter.key) return
  const response = await getLogProviderCatalog('loki', {
    datasource_id: tab.datasourceId,
    action: 'label_values',
    label: filter.key,
    start_ms: toTimestampMs(tab.timeRange[0]),
    end_ms: toTimestampMs(tab.timeRange[1]),
  })
  filter.options = response.items || []
}

function escapeLogValue(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function buildLokiSelector(tab) {
  const selector = (tab.labelFilters || [])
    .filter((item) => item.key && item.value)
    .map((item) => `${item.key}${item.operator || '='}"${escapeLogValue(item.value)}"`)
  return selector.length ? `{${selector.join(',')}}` : ''
}

function buildGeneratedLokiQuery(tab) {
  const base = buildLokiSelector(tab)
  if (!base) return ''
  if (tab.lokiQuerySuffix) {
    return `${base} ${tab.lokiQuerySuffix}`.trim()
  }
  const content = String(tab.lokiContentQuery || '').trim()
  return content ? `${base} |= "${escapeLogValue(content)}"` : base
}

function syncLokiManualQuery(tab) {
  if (!tab) return
  const datasource = dataSources.value.find((item) => item.id === tab.datasourceId)
  if (datasource?.provider !== 'loki') return
  tab.lokiManualQuery = buildGeneratedLokiQuery(tab)
}

function handleLokiContentInput(tab) {
  if (!tab) return
  tab.lokiQuerySuffix = ''
  syncLokiManualQuery(tab)
}

function applyLokiQueryToControls(tab, query, fallbackTraceId = '') {
  const filters = parseLokiSelector(query)
  tab.labelFilters = filters.length ? filters : [makeLabelFilter()]
  tab.lokiQuerySuffix = parseLokiQuerySuffix(query)
  tab.lokiContentQuery = parseLokiContentFilter(query) || fallbackTraceId || ''
  tab.lokiManualQuery = String(query || '').trim() || buildGeneratedLokiQuery(tab)
}

function emptyResultReason(tab, response) {
  const datasource = dataSources.value.find((item) => item.id === tab.datasourceId)
  const provider = providerLabel(datasource?.provider || '')
  const query = datasource?.provider === 'loki' ? tab.lokiManualQuery : datasource?.provider === 'elk' ? buildElkQuery(tab) : tab.queryText
  const reasons = [
    `数据源：${datasource?.name || provider || '未选择'}`,
    `时间范围：${formatTimeRangeSummary(tab.timeRange)}`,
    query ? `查询条件：${query}` : '查询条件为空',
  ]
  if (response?.total === 0) {
    reasons.push('后端返回总匹配 0 条')
  } else {
    reasons.push('后端未返回日志明细，可能是 limit、时间窗口、标签值或 Trace ID 不匹配')
  }
  return reasons.join('；')
}

function friendlyLogError(error) {
  const message = error.response?.data?.error || error.response?.data?.detail || error.message || '日志查询失败'
  if (String(message).includes('empty-compatible value')) {
    return 'Loki 查询条件无效：标签过滤必须至少有一个非空匹配条件，例如 app=~".+"；不能只用 app=~".*" 或 job!="" 这类可能匹配空值的条件。'
  }
  return message
}

function escapeLuceneValue(value) {
  return String(value || '').trim().replace(/[+\-=&|><!(){}[\]^"~*?:\\/]/g, '\\$&')
}

function buildElkFilterClauses(filters = {}) {
  const clauses = []
  if (filters.level) clauses.push(`level:${escapeLuceneValue(filters.level)}`)
  if (filters.service) clauses.push(`service.name:"${escapeLuceneValue(filters.service)}"`)
  if (filters.host) clauses.push(`host.name:"${escapeLuceneValue(filters.host)}"`)
  if (filters.traceId) clauses.push(`trace.id:"${escapeLuceneValue(filters.traceId)}"`)
  return clauses
}

function formatElkFilters(filters = {}) {
  return buildElkFilterClauses(filters).join(' AND ')
}

function buildElkQuery(tab) {
  if (!tab) return ''
  const structured = formatElkFilters(tab.elkFilters)
  const manual = String(tab.queryText || '').trim()
  if (structured && manual) return `${structured} AND (${manual})`
  return structured || manual
}

function elkGeneratedQuery(tab) {
  return buildElkQuery(tab)
}

function hasElkFilters(tab) {
  return Boolean(formatElkFilters(tab?.elkFilters) || tab?.elkPreset)
}

function clearElkFilters(tab) {
  if (!tab) return
  if (tab.elkPreset === 'slow' && tab.queryText === 'message:(timeout OR slow OR latency)') tab.queryText = ''
  tab.elkFilters = makeElkFilters()
  tab.elkPreset = ''
}

function applyElkPreset(tab, preset) {
  if (!tab) return
  tab.elkPreset = preset
  if (preset === 'errors') tab.elkFilters = makeElkFilters({ level: 'error' })
  if (preset === 'warnings') tab.elkFilters = makeElkFilters({ level: 'warning' })
  if (preset === 'slow') tab.elkFilters = makeElkFilters({})
  if (preset === 'slow') tab.queryText = 'message:(timeout OR slow OR latency)'
}

function buildPayload(tab) {
  const datasource = dataSources.value.find((item) => item.id === tab.datasourceId)
  const payload = {
    datasource_id: tab.datasourceId,
    provider: datasource?.provider,
    start_ms: toTimestampMs(tab.timeRange[0]),
    end_ms: toTimestampMs(tab.timeRange[1]),
    limit: tab.limit,
  }

  if (datasource?.provider === 'loki') {
    payload.query = tab.lokiManualQuery.trim()
  } else if (datasource?.provider === 'elk') {
    payload.query = buildElkQuery(tab)
    payload.source = tab.sourceName || datasource.config?.index_pattern
    payload.index_pattern = payload.source
    payload.time_field = datasource.config?.time_field || '@timestamp'
    payload.message_fields = datasource.config?.message_fields || 'message,log,msg'
  } else if (datasource?.provider === 'sls') {
    payload.query = tab.queryText.trim()
    payload.source = tab.sourceName || datasource.config?.logstore
    payload.logstore = payload.source
    payload.topic = datasource.config?.topic || ''
  }
  return payload
}

async function runQuery(tab) {
  if (!tab?.datasourceId) return ElMessage.warning('请先选择日志数据源')
  const payload = buildPayload(tab)
  if (payload.provider === 'loki' && !String(payload.query || '').trim()) return ElMessage.warning('请先【设置标签过滤】或【填写查询语句】')
  tab.queryLoading = true
  tab.errorMessage = ''
  tab.expandedRows = []
  try {
    const response = await queryLogs(payload)
    tab.results = {
      provider: response.provider,
      source: response.source,
      total: response.total || 0,
      took_ms: response.took_ms,
      progress: response.progress || '',
      logs: response.logs || [],
    }
    updateHistory(createSnapshot(tab))
    if (!tab.results.logs.length) {
      ElMessage.warning({
        message: `未查询到日志：${emptyResultReason(tab, response)}`,
        duration: 7000,
        showClose: true,
      })
    }
    await nextTick()
    renderChart()
  } catch (error) {
    tab.results = emptyResults()
    tab.errorMessage = friendlyLogError(error)
  } finally {
    tab.queryLoading = false
  }
}

function bucketize(logs) {
  const points = logs
    .map((item) => new Date(item.timestamp).getTime())
    .filter((item) => !Number.isNaN(item))
    .sort((a, b) => a - b)
  if (!points.length) return []

  const min = points[0]
  const max = points[points.length - 1]
  const count = Math.min(20, Math.max(6, Math.ceil(points.length / 15)))
  const step = Math.max(60000, Math.ceil(Math.max(1, max - min) / count))
  const buckets = Array.from({ length: count }, (_, index) => ({ start: min + index * step, total: 0, error: 0 }))

  logs.forEach((item) => {
    const time = new Date(item.timestamp).getTime()
    if (Number.isNaN(time)) return
    const index = Math.min(count - 1, Math.floor((time - min) / step))
    buckets[index].total += 1
    if (normalizeLogLevel(item) === 'error') buckets[index].error += 1
  })

  return buckets.map((item) => ({
    total: item.total,
    error: item.error,
    label: `${String(new Date(item.start).getHours()).padStart(2, '0')}:${String(new Date(item.start).getMinutes()).padStart(2, '0')}`,
  }))
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const buckets = bucketize(currentResults.value.logs)
  chart.setOption(
    {
      grid: { left: 30, right: 12, top: 16, bottom: 20 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: buckets.map((item) => item.label),
        axisLabel: { color: '#6b7280', fontSize: 11 },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#6b7280', fontSize: 11 },
        splitLine: { lineStyle: { color: '#e5e7eb' } },
      },
      series: [
        {
          name: '日志量',
          type: 'bar',
          data: buckets.map((item) => item.total),
          itemStyle: { color: '#2563eb', borderRadius: [6, 6, 0, 0] },
          barMaxWidth: 22,
        },
        {
          name: '错误数',
          type: 'line',
          smooth: true,
          data: buckets.map((item) => item.error),
          itemStyle: { color: '#ea580c' },
          lineStyle: { color: '#ea580c', width: 2 },
          symbolSize: 6,
        },
      ],
    },
    true
  )
}

function toggleRow(tab, index) {
  if (tab.expandedRows.includes(index)) {
    tab.expandedRows = tab.expandedRows.filter((item) => item !== index)
  } else {
    tab.expandedRows = [...tab.expandedRows, index]
  }
}

function isExpanded(tab, index) {
  return tab.expandedRows.includes(index)
}

function displayAttributes(attributes) {
  return Object.entries(attributes || {})
    .filter(([key]) => !['message', 'log', 'msg'].includes(key))
    .slice(0, 8)
    .map(([key, value]) => ({ key, value: typeof value === 'object' ? JSON.stringify(value) : String(value) }))
}

function formatTimestamp(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function escapeHtml(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function formatMessage(message) {
  const safe = escapeHtml(message || '')
  const query = isLoki.value ? currentTab.value?.lokiContentQuery.trim() : currentTab.value?.queryText.trim()
  if (!query) return safe
  const words = query
    .split(/\s+/)
    .filter((item) => item && !['AND', 'OR', 'NOT'].includes(item.toUpperCase()))
    .slice(0, 4)
  return words.reduce(
    (content, word) => content.replace(new RegExp(`(${escapeRegex(escapeHtml(word))})`, 'gi'), '<mark>$1</mark>'),
    safe
  )
}

function rawLogLevel(item) {
  if (item && typeof item === 'object') {
    return item.attributes?.detected_level || item.attributes?.detectedLevel || item.attributes?.level || item.level
  }
  return item
}

function normalizeLevel(level) {
  const normalized = String(level || '').trim().toLowerCase()
  if (['error', 'err', 'fatal', 'critical', 'crit'].includes(normalized)) return 'error'
  if (['warning', 'warn'].includes(normalized)) return 'warning'
  if (['info', 'information', 'notice'].includes(normalized)) return 'info'
  if (['debug', 'trace', 'verbose'].includes(normalized)) return 'debug'
  return 'unknown'
}

function normalizeLogLevel(item) {
  return normalizeLevel(rawLogLevel(item))
}

function levelTagType(item) {
  return { error: 'danger', warning: 'warning', info: 'success', debug: 'info' }[normalizeLogLevel(item)] || ''
}

function levelLabel(item) {
  return { error: 'ERROR', warning: 'WARN', info: 'INFO', debug: 'DEBUG', unknown: 'UNKNOWN' }[normalizeLogLevel(item)] || 'UNKNOWN'
}

function handleResize() {
  chart?.resize()
}

onMounted(async () => {
  loadSavedQueries()
  await fetchDataSources()
  await initializeTabs()
  if (!(await applyTraceRoutePreset())) {
    if (!(await applyLokiRoutePreset())) {
      await applyKeywordRoutePreset()
    }
  }
  await nextTick()
  renderChart()
  window.addEventListener('resize', handleResize)
})

watch(
  () => [
    route.query.traceId,
    route.query.keyword,
    route.query.provider,
    route.query.logProvider,
    route.query.logDatasourceId,
    route.query.lokiQuery,
    route.query.service,
    route.query.namespace,
    route.query.source,
    route.query.title,
    route.query.window,
    route.query.from,
    route.query.to,
    route.query.autoRun,
  ].join('|'),
  async () => {
    if (route.path === '/logs/query') {
      if (!(await applyTraceRoutePreset())) {
        if (!(await applyLokiRoutePreset())) {
          await applyKeywordRoutePreset()
        }
      }
    }
  }
)

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
</script>

<style scoped>
.logs-query-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.hero-panel {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border: 1px solid rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  padding: 14px 16px;
}

.release-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.release-hero-title-inline {
  flex-wrap: nowrap;
  min-width: 0;
}

.log-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  border: 1px solid rgba(36, 91, 219, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.hero h2 {
  margin: 0;
  color: #0f172a;
  font-size: 23px;
  line-height: 1.1;
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

.hero-panel .release-hero-copy {
  flex: 1;
  min-height: 42px;
  min-width: 0;
}


.log-center-tabs {
  margin-bottom: 0;
  padding: 4px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(248,250,252,.9));
  border: 1px solid rgba(148,163,184,.16);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.log-center-tabs .neo-tab-btn {
  min-height: 38px;
  padding: 0 20px;
  border-radius: 8px;
}

.log-center-tabs.theme-blue .neo-tab-btn.active {
  color: #245bdb !important;
  background: rgba(51, 112, 255, 0.1) !important;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08) !important;
}

.page-desc {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.inline-subtitle {
  flex: 1;
  max-width: none;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel {
  background: linear-gradient(180deg, rgba(255,255,255,.98), rgba(248,250,252,.92));
  border: 1px solid rgba(148,163,184,.16);
  border-radius: 20px;
  box-shadow: 0 12px 28px rgba(15,23,42,.05);
  padding: 12px 14px;
}

.tabs-panel {
  padding: 0;
}

.tabs-panel--session {
  margin-bottom: 2px;
}

.tabs-session-bar {
  align-items: center;
  background: rgba(255, 255, 255, 0.76);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 14px 14px 0 0;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding: 4px 6px 2px;
  box-shadow: inset 0 -1px 0 rgba(226, 232, 240, 0.72);
}

.session-tabs {
  flex: 1;
  min-width: 0;
}

.session-add-btn {
  border-color: rgba(191, 219, 254, 0.9);
  border-radius: 9px;
  color: #2563eb;
  flex-shrink: 0;
  margin-bottom: 2px;
  min-height: 28px;
  padding: 0 11px;
  background: rgba(239, 246, 255, 0.88);
}

.query-layout {
  display: grid;
  gap: 4px;
  grid-template-columns: minmax(0, 1.82fr) minmax(280px, 0.78fr);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.field-label-with-help {
  align-items: center;
  display: inline-flex;
  gap: 5px;
  justify-content: flex-start;
  line-height: 1;
  white-space: nowrap;
}

.field-label-with-help :deep(.el-button) {
  min-height: 20px;
  padding: 0;
}

.slim-head {
  margin-bottom: 4px;
}

.toolbar-actions,
.source-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.log-query-unified-card {
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.035);
  padding: 9px 11px;
}

.log-query-unified-head {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 6px;
}

.log-query-title-block {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.log-query-title-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.log-query-title-row h3 {
  color: #0f172a;
  font-size: 14px;
  letter-spacing: 0.01em;
  margin: 0;
}

.log-query-provider-strip {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 4px;
  width: 100%;
}

.log-filter-datasource-row {
  align-items: center;
  display: flex;
  gap: 6px;
  min-height: 28px;
  width: 100%;
}

.log-query-provider-label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  margin-right: 4px;
  white-space: nowrap;
}

.log-datasource-control {
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

.log-search-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.log-filter-grid {
  display: grid;
  gap: 5px;
  width: 100%;
}

.log-filter-grid--primary {
  align-items: center;
  column-gap: 8px;
  grid-template-columns: minmax(0, 1fr) 132px;
}

.log-filter-grid--secondary {
  align-items: center;
  column-gap: 8px;
  grid-template-columns: 1fr;
}

.elk-quick-filters {
  background: rgba(241, 245, 249, 0.62);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 8px 10px;
}

.elk-quick-filters__head {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
}

.elk-quick-filters__title {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.elk-presets {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.elk-quick-filters__grid {
  display: grid;
  gap: 7px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.elk-query-preview {
  align-items: baseline;
  color: #64748b;
  display: flex;
  font-size: 11px;
  gap: 7px;
  line-height: 1.4;
}

.elk-query-preview code {
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sls-query-presets {
  align-items: center;
  background: rgba(241, 245, 249, 0.62);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 7px 10px;
}

.sls-query-presets > span {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  margin-right: 2px;
}

.log-inline-filter {
  align-items: center;
  column-gap: 8px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  min-width: 0;
}

.log-inline-filter--compact {
  width: 100%;
}

.log-inline-filter--time {
  min-width: 0;
  width: 100%;
}

.log-inline-filter__label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  margin-right: 1px;
  white-space: nowrap;
}

.search-control,
.search-number {
  width: 100%;
}

.search-control :deep(.el-select__wrapper),
.search-control :deep(.el-input__wrapper),
.search-control :deep(.el-range-editor.el-input__wrapper),
.search-number :deep(.el-input__wrapper) {
  background: rgba(248, 250, 252, 0.82);
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(226, 232, 240, 0.92) inset;
  min-height: 30px;
}

.search-control :deep(.el-input__inner),
.search-control :deep(.el-select__selected-item),
.search-control :deep(.el-range-input),
.search-number :deep(.el-input__inner) {
  font-size: 12px;
}

.search-control :deep(.el-select__wrapper:hover),
.search-control :deep(.el-input__wrapper:hover),
.search-control :deep(.el-range-editor.el-input__wrapper:hover),
.search-number :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(191, 219, 254, 0.96) inset;
}

.log-time-control {
  min-width: 0;
  width: 100%;
}

.log-time-control :deep(.el-range-input),
.log-time-control :deep(.el-range-separator) {
  font-size: 12px;
}

.log-time-control :deep(.el-range-editor.el-input__wrapper) {
  min-height: 30px;
}

.toolbar-actions {
  align-items: center;
}

.toolbar-actions--compact {
  gap: 4px;
  justify-content: flex-end;
}

.toolbar-actions :deep(.el-button) {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 8px;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-row {
  display: grid;
  gap: 6px;
  grid-template-columns: minmax(0, 1fr) 84px minmax(0, 1fr) auto;
}

.operator-select {
  width: 84px;
}

.filter-row-actions {
  align-items: center;
  display: inline-flex;
  gap: 2px;
  justify-content: flex-start;
  margin-top: -2px;
  white-space: nowrap;
}

.filter-row-actions :deep(.el-button) {
  margin-left: 0;
}

.filter-row-btn {
  border-radius: 8px;
  font-size: 12px;
  min-height: 24px;
  padding: 0 6px;
}

.filter-row-btn--danger {
  color: #b91c1c;
}

.filter-row-btn--primary {
  color: #2563eb;
}

.helper,
.source-desc,
.source-meta,
.empty-state,
.expand-text,
.time-text,
.source-text {
  color: var(--text-secondary);
}

.source-card {
  border-radius: 12px;
  padding: 7px 8px;
}

.compact-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(248, 250, 252, 0.92) 100%);
  border: 1px solid rgba(226, 232, 240, 0.92);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.compact-info-panel {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(249, 250, 252, 0.92) 100%);
  border-color: rgba(226, 232, 240, 0.8);
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.03);
  padding: 8px 9px;
}

.compact-info-panel .panel-head h3 {
  font-size: 14px;
}

.compact-source-card {
  background: transparent;
  border: 0;
  box-shadow: none;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 2px 0 0;
}

.source-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.source-title-row--tight {
  gap: 6px;
  min-width: 0;
}

.source-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  min-width: 0;
}

.source-title-tags {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}

.source-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.summary-list {
  display: grid;
  gap: 5px;
  margin-top: 0;
  grid-template-columns: 1fr;
}

.summary-list--compact {
  gap: 5px;
}

.summary-item {
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 9px;
  min-height: 54px;
  padding: 6px 8px;
}

.summary-item span {
  color: #64748b;
  display: block;
  font-size: 11px;
  margin-bottom: 3px;
}

.summary-item strong {
  color: #0f172a;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.compact-info-panel :deep(.el-tag) {
  border-radius: 999px;
}

.log-query-form :deep(.el-form-item) {
  align-items: flex-start;
  margin-bottom: 7px;
}

.log-query-form :deep(.el-form-item__label) {
  color: #475569;
  display: flex;
  font-size: 12px;
  line-height: 1.35;
  min-height: 28px;
  padding: 4px 8px 0 0;
  white-space: nowrap;
}

.log-query-form :deep(.el-form-item__content) {
  min-width: 0;
}

.log-query-form :deep(.syntax-form-item) {
  align-items: stretch;
  display: flex;
  flex-direction: column;
  margin-top: 1px;
}

.log-query-form :deep(.syntax-form-item .el-form-item__label) {
  justify-content: space-between;
  line-height: 1.1;
  min-height: 0;
  padding: 9px 0 2px;
  width: 100% !important;
}

.log-query-form :deep(.syntax-form-item .el-form-item__content) {
  margin-left: 0 !important;
  margin-top: -1px;
  width: 100%;
}

.log-query-form :deep(.loki-inline-item .el-form-item__label) {
  flex: 0 0 auto;
  min-width: 0;
  padding-right: 6px;
  width: auto !important;
}

.log-query-form :deep(.loki-inline-item .el-form-item__content) {
  flex: 1 1 auto;
  margin-left: 0 !important;
  min-width: 0;
}

.log-query-form :deep(.loki-content-item) {
  margin-bottom: 3px;
}

.log-query-form :deep(.loki-syntax-item) {
  margin-top: -2px;
}

.log-query-form :deep(.loki-syntax-item .el-form-item__label) {
  padding-top: 4px;
}

.log-query-summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: -2px;
}

.tabs-panel :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.tabs-panel :deep(.el-tabs__nav-wrap::after) {
  height: 0;
}

.tabs-panel :deep(.el-tabs__nav-scroll) {
  padding-bottom: 1px;
}

.tabs-panel :deep(.el-tabs__nav) {
  border: 0 !important;
}

.tabs-panel :deep(.el-tabs__item) {
  height: 29px;
  line-height: 29px;
  padding: 0 11px;
  font-size: 12px;
  border-radius: 9px;
  margin-right: 4px;
}

.tabs-panel :deep(.el-tabs__item.is-top) {
  background: rgba(248, 250, 252, 0.9);
  border-color: transparent;
  color: #64748b;
}

.tabs-panel :deep(.el-tabs__item.is-top.is-active) {
  background: rgba(239, 246, 255, 0.96);
  border-color: rgba(191, 219, 254, 0.92);
  color: #2563eb;
  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.08);
}

.tabs-panel :deep(.el-tabs__item.is-top:hover) {
  color: #2563eb;
}

.tabs-panel :deep(.el-icon-close) {
  margin-left: 5px;
  color: #94a3b8;
}

.query-pill {
  background: rgba(248, 250, 252, 0.82);
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 999px;
  color: #64748b;
  font-size: 10px;
  flex: 0 0 auto;
  padding: 3px 7px;
  white-space: nowrap;
}

.compact-panel {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(249, 250, 252, 0.94) 100%);
  border-color: rgba(226, 232, 240, 0.82);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
  padding: 8px 10px 10px;
}

.compact-panel .panel-head {
  align-items: center;
  margin-bottom: 6px;
}

.compact-panel .panel-head h3 {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  margin: 0;
}

.panel-meta-text {
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
}

.chart {
  height: 108px;
}

.compact-empty {
  min-height: 84px;
}

.log-list {
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: hidden;
}

.compact-log-card {
  background: transparent;
  border: 0;
  border-top: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 0;
  overflow: hidden;
}

.compact-log-card:first-child {
  border-top: 0;
}

.compact-log-main {
  background: transparent;
  border: 0;
  cursor: pointer;
  padding: 8px 10px 8px 11px;
  text-align: left;
  transition: background-color .18s ease;
  width: 100%;
}

.compact-log-main:hover {
  background: rgba(248, 250, 252, 0.88);
}

.log-head-row {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 4px;
}

.log-meta-inline {
  align-items: center;
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.log-meta-inline :deep(.el-tag) {
  border-radius: 999px;
}

.inline-message {
  color: #0f172a;
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  white-space: pre-wrap;
  word-break: break-word;
}

.log-message :deep(mark) {
  background: rgba(250, 204, 21, 0.32);
  border-radius: 4px;
  padding: 0 2px;
}

.expand-text {
  flex-shrink: 0;
  font-size: 11px;
  transition: color .18s ease;
}

.compact-log-main:hover .expand-text {
  color: #2563eb;
}

.result-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.result-tags :deep(.el-tag) {
  border-radius: 999px;
  font-size: 11px;
  min-height: 22px;
  padding: 0 8px;
}

.saved-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.saved-dialog-head {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 8px;
}

.saved-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dialog-list {
  max-height: 52vh;
  overflow: auto;
  padding-right: 4px;
}

.saved-item {
  align-items: center;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding: 10px;
}

.saved-main {
  background: transparent;
  border: 0;
  cursor: pointer;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  text-align: left;
}

.saved-main strong {
  color: #0f172a;
  font-size: 13px;
}

.saved-main span,
.saved-main p,
.saved-empty {
  color: #64748b;
  font-size: 12px;
  margin: 0;
}

.saved-actions {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}

.syntax-help {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.syntax-desc {
  color: #475569;
  line-height: 1.7;
  margin: 0;
}

.syntax-block {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.08) 0%, rgba(14, 165, 233, 0.04) 100%);
  border: 1px solid rgba(59, 130, 246, 0.14);
  border-radius: 10px;
  margin-top: -10px;
  padding: 8px 11px;
}

.syntax-block strong {
  color: #0f172a;
  display: block;
  font-size: 12px;
  margin-bottom: 6px;
}

.syntax-block ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.syntax-block li {
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
}

.syntax-block code {
  background: rgba(37, 99, 235, 0.08);
  border-radius: 6px;
  color: #1d4ed8;
  padding: 2px 6px;
}

.compact-detail {
  background: rgba(248, 250, 252, 0.82);
  border-top: 1px solid rgba(226, 232, 240, 0.82);
  padding: 8px 10px 9px;
}

.detail-actions {
  align-items: center;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 9px;
  display: inline-flex;
  gap: 8px;
  margin-bottom: 6px;
  padding: 3px 7px;
}

.detail-actions__label {
  align-items: center;
  color: #94a3b8;
  display: inline-flex;
  font-size: 11px;
  font-weight: 600;
  height: 22px;
  line-height: 22px;
}

.detail-actions__buttons {
  align-items: center;
  display: inline-flex;
  gap: 2px;
}

.detail-actions__buttons :deep(.el-button) {
  height: 22px;
  margin-left: 0;
  padding: 0 4px;
}

.compact-grid {
  display: grid;
  gap: 5px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 5px;
}

.compact-attr {
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 9px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 6px 8px;
}

.compact-attr span {
  color: #475569;
  font-size: 12px;
  word-break: break-word;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

:deep(.el-tabs__header) {
  margin-bottom: 0;
}

:deep(.el-tabs__item) {
  height: 34px;
  line-height: 34px;
}

@media (max-width: 1080px) {
  .query-layout {
    grid-template-columns: 1fr;
  }

  .log-filter-grid--primary {
    grid-template-columns: 1fr;
  }

}

@media (max-width: 760px) {
  .page-title-row {
    align-items: flex-start;
  }

  .filter-row,
  .compact-grid {
    grid-template-columns: 1fr;
  }

  .log-head-row,
  .panel-head,
  .log-query-unified-head,
  .toolbar-actions,
  .saved-item,
  .saved-dialog-head {
    align-items: stretch;
    flex-direction: column;
  }

  .log-filter-datasource-row,
  .log-inline-filter,
  .source-title-row,
  .summary-list {
    align-items: stretch;
    grid-template-columns: 1fr;
  }

  .elk-quick-filters__grid {
    grid-template-columns: 1fr;
  }

  .elk-quick-filters__head {
    align-items: flex-start;
    flex-direction: column;
  }

  .log-filter-datasource-row,
  .source-title-row {
    flex-direction: column;
  }

  .field-label-with-help {
    flex-wrap: wrap;
    white-space: normal;
  }

  .tabs-session-bar {
    align-items: stretch;
    flex-direction: column;
    padding-bottom: 8px;
  }

  .session-add-btn {
    margin-bottom: 0;
    width: 100%;
  }

  .log-query-form :deep(.el-form-item__label) {
    min-height: 0;
    padding-top: 2px;
    white-space: normal;
  }
}
.hero.panel.hero-panel {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}
</style>

