<template>
  <div class="fade-in datasource-link-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="log-header-icon"><el-icon><Share /></el-icon></span>
          <h2>关联配置</h2>
          <p class="page-inline-desc inline-subtitle">维护日志、链路追踪与仪表盘之间的跳转关联映射。</p>
        </div>
      </div>
    </section>

    <ObservabilityRouteTabs group="datasources" />

    <div class="workbench-card datasource-link-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">关联配置</span>
          <span class="toolbar-desc">维护日志、链路追踪与仪表盘之间的跳转关联映射。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageLinks" type="primary" @click="openDialog()">
            <el-icon><Plus /></el-icon>
            新增关联
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history datasource-link-filter-bar">
        <div class="workbench-toolbar-left">
          <el-input v-model="keyword" placeholder="搜索关联名称或数据源" clearable style="width: 280px">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-switch v-model="enabledOnly" active-text="仅看启用" inactive-text="全部状态" />
        </div>
        <div class="workbench-toolbar-right">
          <span class="toolbar-count">共 {{ filteredItems.length }} 个关联</span>
        </div>
      </div>

      <el-table :data="filteredItems" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="name" label="关联名称" min-width="220">
          <template #default="{ row }">
            <div class="name-cell">
              <span class="name-text">{{ row.name }}</span>
              <el-tag v-if="row.is_default" size="small" type="warning">默认</el-tag>
            </div>
            <div class="sub-text">{{ row.description || '未填写描述' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="数据源关系" min-width="250">
          <template #default="{ row }">
            <div class="link-flow link-flow--stacked">
              <div class="link-node">
                <el-tag size="small" type="success">Loki</el-tag>
                <strong>{{ row.log_datasource_name }}</strong>
              </div>
              <span class="link-flow__arrow">↔</span>
              <div class="link-node">
                <el-tag size="small" type="warning">Tempo</el-tag>
                <strong>{{ row.tracing_datasource_name }}</strong>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="关联看板" min-width="180">
          <template #default="{ row }">{{ dashboardTitle(row.grafana_dashboard_key) }}</template>
        </el-table-column>
        <el-table-column label="跳转能力" width="180">
          <template #default="{ row }">
            <el-tag size="small" :type="row.log_to_trace_enabled ? 'success' : 'info'">日志→链路</el-tag>
            <el-tag size="small" :type="row.trace_to_log_enabled ? 'success' : 'info'">链路→日志</el-tag>
            <el-tag size="small" :type="row.log_to_grafana_enabled ? 'success' : 'info'">日志→看板</el-tag>
            <el-tag size="small" :type="row.trace_to_grafana_enabled ? 'success' : 'info'">链路→看板</el-tag>
            <el-tag size="small" :type="row.grafana_to_trace_enabled ? 'success' : 'info'">看板→链路</el-tag>
            <el-tag size="small" :type="row.grafana_to_log_enabled ? 'success' : 'info'">看板→日志</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canManageLinks" label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除该关联配置吗？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog :close-on-click-modal="false"
      v-model="dialogVisible"
      class="workbench-edit-dialog datasource-link-dialog"
      :title="editingId ? '编辑数据源关联' : '新增数据源关联'"
      width="980px"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <div class="dialog-shell">
        <div class="dialog-summary">
          <div class="summary-item">
            <span class="summary-label">日志数据源</span>
            <strong>{{ selectedLogDatasourceName }}</strong>
          </div>
          <div class="summary-item">
            <span class="summary-label">链路数据源</span>
            <strong>{{ selectedTraceDatasourceName }}</strong>
          </div>
          <div class="summary-item">
            <span class="summary-label">默认看板</span>
            <strong>{{ selectedGrafanaDashboardName }}</strong>
          </div>
          <div class="summary-tags">
            <el-tag size="small" :type="form.is_enabled ? 'success' : 'info'">{{ form.is_enabled ? '启用中' : '已停用' }}</el-tag>
            <el-tag size="small" :type="form.is_default ? 'warning' : 'info'">{{ form.is_default ? '默认关联' : '普通关联' }}</el-tag>
            <el-tag size="small" :type="form.log_to_grafana_enabled ? 'success' : 'info'">日志→看板</el-tag>
            <el-tag size="small" :type="form.trace_to_grafana_enabled ? 'success' : 'info'">链路→看板</el-tag>
            <el-tag size="small" :type="form.grafana_to_trace_enabled ? 'success' : 'info'">看板→链路</el-tag>
            <el-tag size="small" :type="form.grafana_to_log_enabled ? 'success' : 'info'">看板→日志</el-tag>
          </div>
        </div>

        <div class="relation-guide">
          <div class="relation-guide__item">
            <span class="relation-guide__index">1</span>
            <div>
              <strong>选择关联对象</strong>
              <p>Loki 日志源和 Tempo 链路源是一组跳转关系的边界。</p>
            </div>
          </div>
          <div class="relation-guide__item">
            <span class="relation-guide__index">2</span>
            <div>
              <strong>开启跳转方向</strong>
              <p>按日志、链路、看板三个入口分别控制可用跳转。</p>
            </div>
          </div>
          <div class="relation-guide__item">
            <span class="relation-guide__index">3</span>
            <div>
              <strong>配置标签映射</strong>
              <p>统一把 service.name / service.namespace 映射到 Loki 标签和 Grafana 变量。</p>
            </div>
          </div>
        </div>

        <el-form label-position="top" :model="form" label-width="104px" class="dialog-form">
          <section class="form-section">
            <div class="section-title">
              <h4>基础信息</h4>
              <span>先定义这组关联对应哪两个数据源</span>
            </div>
            <div class="section-grid">
              <el-form-item label="关联名称">
                <el-input v-model="form.name" placeholder="例如：交易系统 k3s Loki ↔ Tempo" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="form.description" type="textarea" :rows="2" placeholder="说明该关联适用的环境、集群或命名空间" />
              </el-form-item>
              <el-form-item label="日志数据源">
                <el-select v-model="form.log_datasource" filterable style="width: 100%" placeholder="选择 Loki 数据源">
                  <el-option v-for="item in lokiDataSources" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="链路数据源">
                <el-select v-model="form.tracing_datasource" filterable style="width: 100%" placeholder="选择 Tempo 数据源">
                  <el-option v-for="item in tempoDataSources" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
            </div>
          </section>

          <section class="form-section">
            <div class="section-title">
              <h4>跳转能力</h4>
              <span>按方向开启或关闭跳转，便于排障时快速隔离</span>
            </div>
            <div class="direction-grid">
              <div class="direction-card">
                <strong>基础状态</strong>
                <el-switch v-model="form.is_enabled" active-text="启用" inactive-text="停用" />
                <el-switch v-model="form.is_default" active-text="设为默认" inactive-text="普通关联" />
              </div>
              <div class="direction-card">
                <strong>日志 / 链路互跳</strong>
                <el-switch v-model="form.log_to_trace_enabled" active-text="日志跳链路" inactive-text="关闭日志跳链路" />
                <el-switch v-model="form.trace_to_log_enabled" active-text="链路跳日志" inactive-text="关闭链路跳日志" />
              </div>
              <div class="direction-card">
                <strong>进入看板</strong>
                <el-switch v-model="form.log_to_grafana_enabled" active-text="日志跳看板" inactive-text="关闭日志跳看板" />
                <el-switch v-model="form.trace_to_grafana_enabled" active-text="链路跳看板" inactive-text="关闭链路跳看板" />
              </div>
              <div class="direction-card">
                <strong>从看板返回</strong>
                <el-switch v-model="form.grafana_to_trace_enabled" active-text="看板跳链路" inactive-text="关闭看板跳链路" />
                <el-switch v-model="form.grafana_to_log_enabled" active-text="看板跳日志" inactive-text="关闭看板跳日志" />
              </div>
            </div>
          </section>

          <section class="form-section">
            <div class="section-title">
              <h4>日志跳转</h4>
              <span>Trace 进入日志时，按标签自动拼出 LogQL</span>
            </div>
            <div class="section-grid section-grid--two">
              <el-form-item label="Trace ID 字段">
                <el-input v-model="traceIdFieldsText" placeholder="trace_id, traceId, traceID" />
              </el-form-item>
              <el-form-item label="Trace ID 正则">
                <el-input v-model="form.trace_id_regex" placeholder='"trace_id"\s*:\s*"([0-9a-fA-F]{16,32})"' />
              </el-form-item>
            </div>
            <el-form-item label="日志查询模板">
              <el-input
                v-model="form.log_query_template"
                type="textarea"
                :rows="3"
                placeholder='${__tags} | json | trace_id="${__trace.traceId}"'
              />
            </el-form-item>
            <div class="mapping-block">
              <div class="mapping-block__head">
                <strong>标签映射</strong>
                <span>把 Trace 标签换成 Loki 标签</span>
              </div>
              <div class="mapping-list">
                <div v-for="(item, index) in form.log_label_mappings" :key="index" class="mapping-row">
                  <el-input v-model="item.trace_tag" placeholder="Trace 标签，例如 service.name" />
                  <span class="mapping-arrow">→</span>
                  <el-input v-model="item.log_label" placeholder="Loki 标签，例如 container" />
                  <el-button text type="danger" @click="removeMapping(index)">移除</el-button>
                </div>
                <el-button text type="primary" @click="addMapping">新增映射</el-button>
              </div>
            </div>
          </section>

          <section class="form-section">
            <div class="section-title">
              <h4>Grafana 跳转</h4>
              <span>同一套变量映射同时支持 日志/链路→看板 和 看板→日志/链路</span>
            </div>
            <el-form-item label="关联看板">
              <el-select v-model="form.grafana_dashboard_key" filterable clearable style="width: 100%" placeholder="选择关联跳转使用的看板">
                <el-option v-for="item in grafanaDashboards" :key="item.key" :label="item.title" :value="item.key">
                  <span>{{ item.title }}</span>
                  <span class="option-meta">{{ item.folder || item.key }}</span>
                </el-option>
              </el-select>
            </el-form-item>
            <div class="mapping-block">
              <div class="mapping-block__head">
                <strong>变量映射</strong>
                <span>生成 `var-变量名=值` 形式的参数</span>
              </div>
              <div class="mapping-list">
                <div v-for="(item, index) in form.grafana_variable_mappings" :key="`grafana-${index}`" class="mapping-row">
                  <el-input v-model="item.trace_tag" placeholder="Trace 标签，例如 service.name" />
                  <span class="mapping-arrow">→</span>
                  <el-input v-model="item.variable" placeholder="Grafana 变量，例如 service" />
                  <el-button text type="danger" @click="removeGrafanaMapping(index)">移除</el-button>
                </div>
                <el-button text type="primary" @click="addGrafanaMapping">新增变量映射</el-button>
                <div class="mapping-hint">示例：`service.name=api-gateway` 会映射成 `var-workload=api-gateway`；看板返回时会反向还原。</div>
              </div>
            </div>
          </section>

          <el-collapse class="advanced-collapse" accordion>
            <el-collapse-item title="高级参数" name="advanced">
              <div class="section-grid section-grid--two">
                <el-form-item label="开始偏移">
                  <el-input v-model="form.span_start_shift" placeholder="-5m" />
                </el-form-item>
                <el-form-item label="结束偏移">
                  <el-input v-model="form.span_end_shift" placeholder="5m" />
                </el-form-item>
              </div>
              <el-form-item label="默认窗口">
                <el-input-number v-model="form.window_minutes" :min="1" :max="1440" />
              </el-form-item>
            </el-collapse-item>
          </el-collapse>
        </el-form>
      </div>

      <template #footer>
        <el-button plain type="primary" @click="applyWorkloadPreset">套用 Workload 看板映射</el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search, Share } from '@element-plus/icons-vue'
import {
  createObservabilityDataSourceLink,
  deleteObservabilityDataSourceLink,
  getLogDataSources,
  getObservabilityOverview,
  getObservabilityDataSourceLinks,
  getTracingDataSources,
  updateObservabilityDataSourceLink,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import ObservabilityRouteTabs from '@/components/observability/ObservabilityRouteTabs.vue'

const authStore = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const keyword = ref('')
const enabledOnly = ref(true)
const items = ref([])
const logDataSources = ref([])
const tracingDataSources = ref([])
const grafanaDashboards = ref([])
const traceIdFieldsText = ref('trace_id, traceId, traceID')
const WORKLOAD_DASHBOARD_KEY = 'kubernetes-compute-resources-workload'
const WORKLOAD_GRAFANA_MAPPINGS = [
  { trace_tag: 'service.name', variable: 'workload' },
  { trace_tag: 'service.namespace', variable: 'namespace' },
  { trace_tag: 'workload.type', variable: 'workload_type' },
]
const WORKLOAD_LOG_MAPPINGS = [
  { trace_tag: 'service.name', log_label: 'container' },
  { trace_tag: 'service.namespace', log_label: 'namespace' },
  { trace_tag: 'workload.type', log_label: 'workload_type' },
]
const form = ref(createEmptyForm())

const canManageLinks = computed(() => authStore.hasPermission('ops.observability.link.manage'))
const lokiDataSources = computed(() => logDataSources.value.filter((item) => item.provider === 'loki'))
const tempoDataSources = computed(() => tracingDataSources.value.filter((item) => item.provider === 'tempo'))
const selectedLogDatasourceName = computed(() => datasourceName(lokiDataSources.value, form.value.log_datasource, '未选择 Loki'))
const selectedTraceDatasourceName = computed(() => datasourceName(tempoDataSources.value, form.value.tracing_datasource, '未选择 Tempo'))
const selectedGrafanaDashboardName = computed(() => dashboardTitle(form.value.grafana_dashboard_key))
const filteredItems = computed(() =>
  items.value.filter((item) => {
    if (enabledOnly.value && !item.is_enabled) return false
    if (!keyword.value) return true
    const text = `${item.name} ${item.description || ''} ${item.log_datasource_name || ''} ${item.tracing_datasource_name || ''}`.toLowerCase()
    return text.includes(keyword.value.toLowerCase())
  })
)

function datasourceName(list, id, fallback) {
  const datasource = list.find((item) => String(item.id) === String(id))
  return datasource?.name || fallback
}

function createEmptyForm() {
  return {
    name: '',
    log_datasource: '',
    tracing_datasource: '',
    description: '',
    is_enabled: true,
    is_default: false,
    log_to_trace_enabled: true,
    trace_to_log_enabled: true,
    log_to_grafana_enabled: true,
    trace_to_grafana_enabled: true,
    grafana_to_log_enabled: true,
    grafana_to_trace_enabled: true,
    trace_id_fields: ['trace_id', 'traceId', 'traceID'],
    trace_id_regex: '"trace_id"\\s*:\\s*"([0-9a-fA-F]{16,32})"',
    log_query_template: '${__tags} | json | trace_id="${__trace.traceId}"',
    log_label_mappings: WORKLOAD_LOG_MAPPINGS.map((item) => ({ ...item })),
    grafana_dashboard_key: WORKLOAD_DASHBOARD_KEY,
    grafana_variable_mappings: WORKLOAD_GRAFANA_MAPPINGS.map((item) => ({ ...item })),
    span_start_shift: '-5m',
    span_end_shift: '5m',
    window_minutes: 10,
  }
}

async function fetchAll() {
  loading.value = true
  try {
    const [linksResponse, logsResponse, tracesResponse, overviewResponse] = await Promise.all([
      getObservabilityDataSourceLinks(),
      getLogDataSources({ is_enabled: true }),
      getTracingDataSources({ is_enabled: true }),
      getObservabilityOverview().catch(() => null),
    ])
    items.value = Array.isArray(linksResponse) ? linksResponse : linksResponse.results || []
    logDataSources.value = Array.isArray(logsResponse) ? logsResponse : logsResponse.results || []
    tracingDataSources.value = Array.isArray(tracesResponse) ? tracesResponse : tracesResponse.results || []
    grafanaDashboards.value = overviewResponse?.modules?.grafana?.dashboards || []
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.value = {
      ...createEmptyForm(),
      ...row,
      log_datasource: row.log_datasource,
      tracing_datasource: row.tracing_datasource,
      log_label_mappings: (row.log_label_mappings || []).map((item) => ({ ...item })),
      grafana_variable_mappings: (row.grafana_variable_mappings || []).map((item) => ({ ...item })),
    }
    traceIdFieldsText.value = (row.trace_id_fields || []).join(', ')
  } else {
    editingId.value = null
    form.value = createEmptyForm()
    form.value.log_datasource = lokiDataSources.value.find((item) => item.name === '交易系统-k3s-loki')?.id || lokiDataSources.value[0]?.id || ''
    form.value.tracing_datasource = tempoDataSources.value.find((item) => item.name === '交易系统-k3s-tempo')?.id || tempoDataSources.value[0]?.id || ''
    traceIdFieldsText.value = form.value.trace_id_fields.join(', ')
  }
  dialogVisible.value = true
}

function addMapping() {
  form.value.log_label_mappings.push({ trace_tag: '', log_label: '' })
}

function removeMapping(index) {
  form.value.log_label_mappings.splice(index, 1)
}

function addGrafanaMapping() {
  form.value.grafana_variable_mappings.push({ trace_tag: '', variable: '' })
}

function removeGrafanaMapping(index) {
  form.value.grafana_variable_mappings.splice(index, 1)
}

function applyWorkloadPreset() {
  form.value.grafana_dashboard_key = WORKLOAD_DASHBOARD_KEY
  form.value.grafana_variable_mappings = WORKLOAD_GRAFANA_MAPPINGS.map((item) => ({ ...item }))
  form.value.log_label_mappings = WORKLOAD_LOG_MAPPINGS.map((item) => ({ ...item }))
  form.value.log_to_grafana_enabled = true
  form.value.trace_to_grafana_enabled = true
  form.value.grafana_to_log_enabled = true
  form.value.grafana_to_trace_enabled = true
  ElMessage.success('已套用 Kubernetes Workload 看板映射')
}

function dashboardTitle(key) {
  if (!key) return '--'
  const dashboard = grafanaDashboards.value.find((item) => item.key === key || item.slug === key)
  return dashboard?.title || key
}

function buildPayload() {
  return {
    ...form.value,
    grafana_dashboard_key: form.value.grafana_dashboard_key || WORKLOAD_DASHBOARD_KEY,
    trace_id_fields: traceIdFieldsText.value.split(',').map((item) => item.trim()).filter(Boolean),
    log_label_mappings: form.value.log_label_mappings.filter((item) => item.trace_tag && item.log_label),
    grafana_variable_mappings: form.value.grafana_variable_mappings.filter((item) => item.trace_tag && item.variable),
  }
}

async function handleSave() {
  if (!form.value.name) return ElMessage.warning('请填写关联名称')
  if (!form.value.log_datasource || !form.value.tracing_datasource) return ElMessage.warning('请选择日志和链路数据源')
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingId.value) {
      await updateObservabilityDataSourceLink(editingId.value, payload)
      ElMessage.success('关联配置已更新')
    } else {
      await createObservabilityDataSourceLink(payload)
      ElMessage.success('关联配置已创建')
    }
    dialogVisible.value = false
    await fetchAll()
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  await deleteObservabilityDataSourceLink(id)
  ElMessage.success('关联配置已删除')
  await fetchAll()
}

onMounted(fetchAll)
</script>

<style scoped>
.datasource-link-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero.panel {
  align-items: center;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  padding: 14px 16px;
}

.release-hero-title-row {
  align-items: center;
  display: flex;
  gap: 12px;
  min-width: 0;
}

.release-hero-title-inline {
  flex-wrap: wrap;
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

.log-header-icon {
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

.datasource-link-card {
  padding: 14px;
}

.datasource-link-filter-bar {
  margin-bottom: 8px;
}

.name-cell,
.mapping-row {
  align-items: center;
  display: flex;
  gap: 8px;
}

.toolbar-count {
  color: #64748b;
  font-size: 12px;
}

.name-text,
.link-flow strong {
  color: #0f172a;
  font-weight: 700;
}

.link-flow {
  display: flex;
}

.link-flow--stacked {
  align-items: center;
  gap: 10px;
}

.link-node {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.link-node strong {
  line-height: 1.35;
  word-break: break-all;
}

.link-flow__arrow {
  color: #94a3b8;
  flex: 0 0 auto;
  font-weight: 700;
}

.sub-text {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 3px;
}

.option-meta,
.mapping-hint {
  color: var(--text-secondary);
  font-size: 12px;
}

.option-meta {
  float: right;
  margin-left: 12px;
}

.dialog-shell {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding-right: 4px;
}




.dialog-summary {
  align-items: center;
  background: linear-gradient(135deg, rgba(240, 253, 250, 0.92), rgba(239, 246, 255, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  padding: 12px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.summary-label {
  color: #64748b;
  font-size: 12px;
}

.summary-item strong {
  color: #0f172a;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-tags {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.relation-guide {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.relation-guide__item {
  align-items: flex-start;
  background: #f8fafc;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  display: flex;
  gap: 10px;
  padding: 10px;
}

.relation-guide__index {
  align-items: center;
  background: #0f766e;
  border-radius: 999px;
  color: #fff;
  display: inline-flex;
  flex: 0 0 22px;
  font-size: 12px;
  font-weight: 700;
  height: 22px;
  justify-content: center;
}

.relation-guide strong {
  color: #0f172a;
  display: block;
  font-size: 13px;
  line-height: 1.2;
}

.relation-guide p {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
  margin: 4px 0 0;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-section {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 14px;
  padding: 12px 12px 4px;
}

.section-title {
  align-items: baseline;
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.section-title h4 {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.3;
  margin: 0;
}

.section-title span {
  color: #94a3b8;
  font-size: 12px;
}

.section-grid {
  display: grid;
  gap: 0 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.section-grid--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.switch-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  padding: 2px 0 10px;
}

.direction-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 2px 0 10px;
}

.direction-card {
  background: rgba(248, 250, 252, 0.86);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 10px;
}

.direction-card strong {
  color: #334155;
  font-size: 12px;
}

.mapping-block {
  border-top: 1px dashed rgba(203, 213, 225, 0.9);
  margin-top: 2px;
  padding: 10px 0 8px;
}

.mapping-block__head {
  align-items: baseline;
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.mapping-block__head strong {
  color: #334155;
  font-size: 13px;
}

.mapping-block__head span {
  color: #94a3b8;
  font-size: 12px;
}

.mapping-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.mapping-row {
  background: rgba(248, 250, 252, 0.86);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 10px;
  padding: 7px;
  width: 100%;
}

.mapping-arrow {
  color: #94a3b8;
  flex: 0 0 auto;
  font-weight: 700;
}

.advanced-collapse {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 14px;
  overflow: hidden;
}

.advanced-collapse :deep(.el-collapse-item__header) {
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
  padding: 0 12px;
}

.advanced-collapse :deep(.el-collapse-item__content) {
  padding: 12px 12px 0;
}

.dialog-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

@media (max-width: 980px) {
  .dialog-summary,
  .relation-guide,
  .section-grid,
  .section-grid--two,
  .switch-grid,
  .direction-grid {
    grid-template-columns: 1fr;
  }

  .summary-tags {
    justify-content: flex-start;
  }

  .mapping-row {
    align-items: stretch;
    flex-direction: column;
  }

  .mapping-arrow {
    display: none;
  }
}
</style>
