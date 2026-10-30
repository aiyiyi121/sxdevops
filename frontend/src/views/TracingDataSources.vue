<template>
  <div class="fade-in tracing-datasource-page" :class="{ 'is-embedded': props.embedded }">
    <div class="workbench-card tracing-datasource-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">链路追踪数据源</span>
          <span class="toolbar-desc">维护 SkyWalking、Tempo、Jaeger、Zipkin 等追踪查询入口。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageTracingDataSources" type="primary" @click="openDialog()">
            <el-icon><Plus /></el-icon>
            新增数据源
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history datasource-filter-bar">
        <div class="workbench-toolbar-left">
          <el-input v-model="keyword" size="small" placeholder="搜索名称或描述" clearable style="width: 260px">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="providerFilter" size="small" clearable placeholder="全部 Provider" style="width: 180px">
            <el-option v-for="provider in providers" :key="provider.id" :label="provider.name" :value="provider.id" />
          </el-select>
          <el-switch v-model="enabledOnly" active-text="仅看启用" inactive-text="全部状态" />
        </div>
        <div class="workbench-toolbar-right">
          <span class="toolbar-count">共 {{ filteredItems.length }} 个数据源</span>
        </div>
      </div>

      <el-table :data="filteredItems" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div class="name-cell">
              <span class="name-text">{{ row.name }}</span>
              <el-tag v-if="row.is_default" size="small" type="warning">默认</el-tag>
            </div>
            <div class="sub-text">{{ row.description || '未填写描述' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Provider" width="200">
          <template #default="{ row }">
            <el-tag :type="providerTagType(row.provider)">{{ providerLabel(row.provider) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="连接摘要" min-width="320">
          <template #default="{ row }">
            <div class="summary-text">{{ formatSummary(row) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" :width="canManageTracingDataSources ? 248 : 112" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button link type="primary" size="small" @click="openTracing(row)">打开追踪</el-button>
              <template v-if="canManageTracingDataSources">
                <el-button link type="success" size="small" @click="handleTest(row)" :loading="testingId === row.id">测试连接</el-button>
                <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
                <el-popconfirm title="确定删除该链路数据源吗？" @confirm="handleDelete(row.id)">
                  <template #reference>
                    <el-button link type="danger" size="small">删除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog"
      v-model="dialogVisible"
      :title="editingId ? '编辑链路数据源' : '新增链路数据源'"
      width="720px"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="form" label-width="120px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>数据源信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="数据源名称">
              <el-input v-model="form.name" placeholder="例如：生产 Tempo" />
            </el-form-item>
            <el-form-item label="Provider">
              <el-select v-model="form.provider" style="width: 100%" @change="onProviderChange">
                <el-option v-for="provider in providers" :key="provider.id" :label="provider.name" :value="provider.id" />
              </el-select>
            </el-form-item>
            <el-form-item class="workbench-editor-full" label="描述">
              <el-input v-model="form.description" type="textarea" :rows="2" placeholder="例如：生产环境 OpenTelemetry 查询入口" />
            </el-form-item>
            <el-form-item label="状态">
              <div class="switch-row switch-row--form">
                <el-switch v-model="form.is_enabled" active-text="启用" inactive-text="停用" />
                <el-switch v-model="form.is_default" active-text="设为默认" inactive-text="普通数据源" />
              </div>
            </el-form-item>
          </div>
        </section>

        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>连接与认证</h3></div>
          <div class="workbench-editor-grid">
            <template v-if="form.provider === 'skywalking'">
              <el-form-item label="UI 地址">
                <el-input v-model="form.config.ui_url" placeholder="http://skywalking-ui.example.com" />
              </el-form-item>
              <el-form-item label="OAP 地址">
                <el-input v-model="form.config.oap_url" placeholder="http://skywalking-oap.example.com:12800" />
              </el-form-item>
              <el-form-item label="GraphQL Path">
                <el-input v-model="form.config.graphql_path" placeholder="/graphql" />
              </el-form-item>
              <el-form-item label="默认 Layer">
                <el-input v-model="form.config.default_layer" placeholder="可选，例如 GENERAL" />
              </el-form-item>
            </template>

            <template v-else>
              <el-form-item label="UI 地址">
                <el-input v-model="form.config.ui_url" :placeholder="uiPlaceholder(form.provider)" />
              </el-form-item>
              <el-form-item label="查询地址">
                <el-input v-model="form.config.query_url" :placeholder="queryPlaceholder(form.provider)" />
              </el-form-item>
              <el-form-item label="Authorization">
                <el-input v-model="form.config.authorization" show-password :placeholder="secretPlaceholder('authorization')" />
              </el-form-item>
            </template>
          </div>
        </section>
      </el-form>

      <template #footer>
        <div class="dialog-footer-actions">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createTracingDataSource,
  deleteTracingDataSource,
  getTracingDataSources,
  getTracingProviders,
  testTracingDataSource,
  updateTracingDataSource,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})
const loading = ref(false)
const saving = ref(false)
const testingId = ref(null)
const dialogVisible = ref(false)
const editingId = ref(null)
const keyword = ref('')
const providerFilter = ref('')
const enabledOnly = ref(true)
const items = ref([])
const providers = ref([])
const providerDefaults = ref({})
const secretFlags = ref({})
const form = ref(createEmptyForm())

function createEmptyForm(provider = 'skywalking') {
  return {
    name: '',
    provider,
    description: '',
    is_enabled: true,
    is_default: false,
    config: getProviderDefaults(provider),
  }
}

function getProviderDefaults(provider) {
  const defaults = providerDefaults.value[provider] || {}
  const config = {}
  Object.entries(defaults).forEach(([key, value]) => {
    if (value !== 'configured') config[key] = value
  })
  if (provider === 'skywalking') {
    config.graphql_path = config.graphql_path || '/graphql'
  }
  config.demo_mode = false
  return config
}

const filteredItems = computed(() =>
  items.value.filter((item) => {
    if (providerFilter.value && item.provider !== providerFilter.value) return false
    if (enabledOnly.value && !item.is_enabled) return false
    if (!keyword.value) return true
    const text = `${item.name} ${item.description || ''}`.toLowerCase()
    return text.includes(keyword.value.toLowerCase())
  })
)
const canManageTracingDataSources = computed(() => authStore.hasPermission('ops.trace.datasource.manage'))

function providerLabel(provider) {
  return providers.value.find((item) => item.id === provider)?.name || provider
}

function providerTagType(provider) {
  return {
    skywalking: 'success',
    tempo: 'warning',
    jaeger: 'primary',
    zipkin: 'info',
  }[provider] || 'info'
}

function formatSummary(row) {
  const config = row.config || {}
  if (row.provider === 'skywalking') return [config.oap_url, config.ui_url].filter(Boolean).join(' / ') || '未配置 SkyWalking 地址'
  return [config.query_url, config.ui_url].filter(Boolean).join(' / ') || '未配置查询地址'
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function uiPlaceholder(provider) {
  return {
    tempo: 'http://grafana.example.com/explore',
    jaeger: 'http://jaeger-ui.example.com',
    zipkin: 'http://zipkin-ui.example.com',
  }[provider] || ''
}

function queryPlaceholder(provider) {
  return {
    tempo: 'http://tempo-query.example.com',
    jaeger: 'http://jaeger-query.example.com',
    zipkin: 'http://zipkin-api.example.com',
  }[provider] || ''
}

function secretPlaceholder(key) {
  return secretFlags.value[key] ? '已配置，留空则保持不变' : '可选'
}

async function fetchProviders() {
  const response = await getTracingProviders()
  providers.value = response.providers || []
  const defaults = {}
  providers.value.forEach((provider) => {
    defaults[provider.id] = provider.defaults || {}
  })
  providerDefaults.value = defaults
}

async function fetchDataSources() {
  loading.value = true
  try {
    const response = await getTracingDataSources()
    items.value = Array.isArray(response) ? response : response.results || []
  } finally {
    loading.value = false
  }
}

function onProviderChange(provider) {
  form.value.config = {
    ...getProviderDefaults(provider),
    ...form.value.config,
    demo_mode: false,
  }
  if (provider === 'skywalking') {
    delete form.value.config.query_url
  } else {
    delete form.value.config.oap_url
    delete form.value.config.graphql_path
    delete form.value.config.default_layer
  }
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    const config = { ...(row.config || {}) }
    secretFlags.value = {
      authorization: config.authorization === 'configured',
    }
    Object.keys(secretFlags.value).forEach((key) => {
      if (secretFlags.value[key]) config[key] = ''
    })
    form.value = {
      id: row.id,
      name: row.name,
      provider: row.provider,
      description: row.description,
      is_enabled: row.is_enabled,
      is_default: row.is_default,
      config: {
        ...config,
        demo_mode: false,
      },
    }
  } else {
    editingId.value = null
    secretFlags.value = {}
    form.value = createEmptyForm(providers.value[0]?.id || 'skywalking')
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.value.name) return ElMessage.warning('请填写数据源名称')
  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      provider: form.value.provider,
      description: form.value.description,
      is_enabled: form.value.is_enabled,
      is_default: form.value.is_default,
      config: {
        ...form.value.config,
        demo_mode: false,
      },
    }
    if (editingId.value) {
      await updateTracingDataSource(editingId.value, payload)
      ElMessage.success('链路数据源已更新')
    } else {
      await createTracingDataSource(payload)
      ElMessage.success('链路数据源已创建')
    }
    dialogVisible.value = false
    await fetchDataSources()
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  await deleteTracingDataSource(id)
  ElMessage.success('链路数据源已删除')
  await fetchDataSources()
}

async function handleTest(row) {
  testingId.value = row.id
  try {
    const response = await testTracingDataSource(row.id)
    if (response.success) ElMessage.success(`${response.message}，发现 ${response.preview_count || 0} 个服务`)
    else ElMessage.error(response.message || '连接测试失败')
  } finally {
    testingId.value = null
  }
}

function openTracing(row) {
  router.push({
    path: '/observability/tracing',
    query: {
      provider: row.provider,
      datasourceId: String(row.id),
    },
  })
}

onMounted(async () => {
  await fetchProviders()
  await fetchDataSources()
})

defineExpose({
  fetchDataSources,
})
</script>

<style scoped>
.tracing-datasource-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tracing-datasource-page.is-embedded {
  gap: 6px;
}

.tracing-datasource-card {
  padding: 14px;
}

.section-toolbar,
.toolbar-head,
.workbench-card-actions,
.workbench-toolbar,
.workbench-toolbar-left,
.workbench-toolbar-right,
.switch-row,
.name-cell {
  align-items: center;
  display: flex;
}

.section-toolbar {
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 8px;
}

.toolbar-head {
  flex: 1;
  flex-wrap: wrap;
  gap: 10px;
  min-width: 0;
}

.toolbar-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.toolbar-desc,
.toolbar-count {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.workbench-card-actions,
.workbench-toolbar-left,
.workbench-toolbar-right {
  gap: 8px;
  flex-wrap: wrap;
}

.workbench-toolbar {
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92) 0%, rgba(255, 255, 255, 0.96) 100%);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
  gap: 8px;
  justify-content: space-between;
  margin: 6px 0 8px;
  padding: 6px 8px;
}

.datasource-filter-bar {
  margin-bottom: 8px;
}

.sub-text,
.summary-text {
  color: var(--text-secondary);
  font-size: 12px;
}

.switch-row {
  gap: 8px;
  flex-wrap: wrap;
}

.switch-row--form {
  min-height: 32px;
  width: 100%;
}

.row-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 2px 6px;
  justify-content: flex-end;
  line-height: 1;
}

.row-actions :deep(.el-button) {
  margin-left: 0;
  padding-inline: 2px;
}

.dialog-footer-actions {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.name-text {
  font-weight: 600;
}

@media (max-width: 760px) {
  .hero {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
