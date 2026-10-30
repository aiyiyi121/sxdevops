<template>
  <div class="fade-in log-datasource-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="log-header-icon"><el-icon><DataBoard /></el-icon></span>
          <h2>日志数据源</h2>
          <p class="page-inline-desc inline-subtitle">统一管理 Loki、ELK 和阿里云 SLS 的连接配置，查询页可以直接复用已保存的数据源。</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" @click="fetchDataSources" :loading="loading">
          <el-icon><RefreshRight /></el-icon>
          刷新数据源
        </el-button>
      </div>
    </section>

    <ObservabilityRouteTabs group="datasources" />

    <div class="workbench-card log-datasource-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">日志数据源</span>
          <span class="toolbar-desc">维护日志查询可复用的数据源连接和默认入口。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageLogDataSources" type="primary" @click="openDialog()">
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
          <el-select v-model="providerFilter" size="small" clearable placeholder="全部类型" style="width: 160px">
            <el-option v-for="provider in providers" :key="provider.id" :label="providerLabel(provider.id)" :value="provider.id" />
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
        <el-table-column label="类型" width="180">
          <template #default="{ row }">
            <el-tag :type="providerTagType(row.provider)">{{ providerLabel(row.provider) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="连接摘要" min-width="280">
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
        <el-table-column v-if="canManageLogDataSources" label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" size="small" @click="handleTest(row)" :loading="testingId === row.id">测试连接</el-button>
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除该日志数据源吗？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog"
      v-model="dialogVisible"
      :title="editingId ? '编辑日志数据源' : '新增日志数据源'"
      width="720px"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="form" label-width="110px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>数据源信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="数据源名称">
              <el-input v-model="form.name" placeholder="例如：生产 ELK" />
            </el-form-item>
            <el-form-item label="日志类型">
              <el-select v-model="form.provider" style="width: 100%" @change="onProviderChange">
                <el-option v-for="provider in providers" :key="provider.id" :label="providerLabel(provider.id)" :value="provider.id" />
              </el-select>
            </el-form-item>
            <el-form-item class="workbench-editor-full" label="描述">
              <el-input v-model="form.description" type="textarea" :rows="2" placeholder="说明该数据源的用途，例如生产业务日志" />
            </el-form-item>
            <div class="switch-row">
              <el-switch v-model="form.is_enabled" active-text="启用" inactive-text="停用" />
              <el-switch v-model="form.is_default" active-text="设为默认" inactive-text="普通数据源" />
            </div>
          </div>
        </section>

        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>连接与认证</h3></div>
          <div class="workbench-editor-grid">
            <template v-if="form.provider === 'loki'">
              <el-form-item label="Loki 地址">
                <el-input v-model="form.config.endpoint" placeholder="http://localhost:3100" />
              </el-form-item>
            </template>

            <template v-else-if="form.provider === 'elk'">
              <el-form-item label="ES 地址">
                <el-input v-model="form.config.endpoint" placeholder="https://es.example.com:9200" />
              </el-form-item>
              <el-form-item label="认证方式">
                <el-select v-model="form.config.auth_type" style="width: 100%">
                  <el-option label="无认证" value="none" />
                  <el-option label="Basic Auth" value="basic" />
                  <el-option label="API Key" value="api_key" />
                  <el-option label="Bearer Token" value="bearer" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="form.config.auth_type === 'basic'" label="用户名">
                <el-input v-model="form.config.username" placeholder="elastic" />
              </el-form-item>
              <el-form-item v-if="form.config.auth_type === 'basic'" label="密码">
                <el-input v-model="form.config.password" show-password :placeholder="secretPlaceholder('password')" />
              </el-form-item>
              <el-form-item v-if="form.config.auth_type === 'api_key'" label="API Key">
                <el-input v-model="form.config.api_key" show-password :placeholder="secretPlaceholder('api_key')" />
              </el-form-item>
              <el-form-item v-if="form.config.auth_type === 'bearer'" label="Bearer Token">
                <el-input v-model="form.config.bearer_token" show-password :placeholder="secretPlaceholder('bearer_token')" />
              </el-form-item>
              <el-form-item label="索引模式">
                <el-input v-model="form.config.index_pattern" placeholder="logs-*" />
              </el-form-item>
              <el-form-item label="时间字段">
                <el-input v-model="form.config.time_field" placeholder="@timestamp" />
              </el-form-item>
              <el-form-item label="消息字段">
                <el-input v-model="form.config.message_fields" placeholder="message,log,msg" />
              </el-form-item>
            </template>

            <template v-else-if="form.provider === 'sls'">
              <el-form-item label="SLS Endpoint">
                <el-input v-model="form.config.endpoint" placeholder="cn-hangzhou.log.aliyuncs.com" />
              </el-form-item>
              <el-form-item label="Project">
                <el-input v-model="form.config.project" placeholder="project-name" />
              </el-form-item>
              <el-form-item label="Logstore">
                <el-input v-model="form.config.logstore" placeholder="app-logstore" />
              </el-form-item>
              <el-form-item label="Topic">
                <el-input v-model="form.config.topic" placeholder="可选" />
              </el-form-item>
              <el-form-item label="AccessKey ID">
                <el-input v-model="form.config.access_key_id" :placeholder="secretPlaceholder('access_key_id')" />
              </el-form-item>
              <el-form-item label="AccessKey Secret">
                <el-input v-model="form.config.access_key_secret" show-password :placeholder="secretPlaceholder('access_key_secret')" />
              </el-form-item>
            </template>
          </div>
        </section>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DataBoard, Plus, RefreshRight, Search } from '@element-plus/icons-vue'
import {
  createLogDataSource,
  deleteLogDataSource,
  getLogDataSources,
  getLogProviders,
  testLogDataSource,
  updateLogDataSource,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import ObservabilityRouteTabs from '@/components/observability/ObservabilityRouteTabs.vue'

const authStore = useAuthStore()
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

function createEmptyForm(provider = 'loki') {
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
  if (provider === 'elk') {
    config.auth_type = config.auth_type || 'none'
    config.index_pattern = config.index_pattern || 'logs-*'
    config.time_field = config.time_field || '@timestamp'
    config.message_fields = config.message_fields || 'message,log,msg'
  }
  return config
}

const filteredItems = computed(() => {
  return items.value.filter((item) => {
    if (providerFilter.value && item.provider !== providerFilter.value) return false
    if (enabledOnly.value && !item.is_enabled) return false
    if (!keyword.value) return true
    const text = `${item.name} ${item.description || ''}`.toLowerCase()
    return text.includes(keyword.value.toLowerCase())
  })
})
const canManageLogDataSources = computed(() => authStore.hasPermission('ops.log.datasource.manage'))

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

function formatSummary(row) {
  const config = row.config || {}
  if (row.provider === 'loki') return config.endpoint || '未配置 Loki 地址'
  if (row.provider === 'elk') {
    return [config.endpoint, config.index_pattern && `索引 ${config.index_pattern}`].filter(Boolean).join(' / ') || '未配置 ELK 连接'
  }
  return [config.project && `项目 ${config.project}`, config.logstore && `日志库 ${config.logstore}`, config.endpoint].filter(Boolean).join(' / ') || '未配置 SLS 连接'
}

function formatTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function secretPlaceholder(key) {
  return secretFlags.value[key] ? '已配置，留空则保持不变' : '请输入敏感信息'
}

async function fetchProviders() {
  const response = await getLogProviders()
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
    const response = await getLogDataSources()
    items.value = Array.isArray(response) ? response : response.results || []
  } finally {
    loading.value = false
  }
}

function onProviderChange(provider) {
  form.value.config = {
    ...getProviderDefaults(provider),
    ...form.value.config,
  }
  if (provider !== 'elk') {
    delete form.value.config.username
    delete form.value.config.password
    delete form.value.config.api_key
    delete form.value.config.bearer_token
  }
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    const config = { ...(row.config || {}) }
    secretFlags.value = {
      password: config.password === 'configured',
      api_key: config.api_key === 'configured',
      bearer_token: config.bearer_token === 'configured',
      access_key_id: config.access_key_id === 'configured',
      access_key_secret: config.access_key_secret === 'configured',
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
      config,
    }
  } else {
    editingId.value = null
    secretFlags.value = {}
    form.value = createEmptyForm(providers.value[0]?.id || 'loki')
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
      config: form.value.config,
    }
    if (editingId.value) {
      await updateLogDataSource(editingId.value, payload)
      ElMessage.success('日志数据源已更新')
    } else {
      await createLogDataSource(payload)
      ElMessage.success('日志数据源已创建')
    }
    dialogVisible.value = false
    await fetchDataSources()
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  await deleteLogDataSource(id)
  ElMessage.success('日志数据源已删除')
  await fetchDataSources()
}

async function handleTest(row) {
  testingId.value = row.id
  try {
    const response = await testLogDataSource(row.id)
    if (response.success) ElMessage.success(`${response.message}，发现 ${response.preview_count || 0} 条目录项`)
    else ElMessage.error(response.message || '连接测试失败')
  } finally {
    testingId.value = null
  }
}

onMounted(async () => {
  await fetchProviders()
  await fetchDataSources()
})
</script>

<style scoped>
.log-datasource-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero.panel {
  align-items: center;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border: 1px solid rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
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

.hero h2 {
  color: #0f172a;
  font-size: 23px;
  line-height: 1.1;
  margin: 0;
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

.page-inline-desc {
  color: #475569;
  flex: 0 1 auto;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  transform: translateY(1px);
}

.inline-subtitle {
  max-width: none;
}

.hero-actions {
  align-items: center;
  display: flex;
  gap: 8px;
}

.hero-actions :deep(.el-button) {
  border-radius: 10px;
  font-weight: 500;
  min-height: 32px;
  padding: 0 14px;
}

.log-datasource-card {
  padding: 14px;
}

.datasource-filter-bar {
  margin-bottom: 8px;
}

.toolbar-count {
  color: #64748b;
  font-size: 12px;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.name-text {
  font-weight: 700;
}

.disabled {
  opacity: 0.55;
  pointer-events: none;
}

@media (max-width: 900px) {
  .hero {
    flex-direction: column;
    align-items: stretch;
  }
}

.sub-text,
.summary-text {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 6px;
  word-break: break-word;
}

.switch-row {
  display: flex;
  gap: 24px;
  margin-bottom: 18px;
  padding-left: 110px;
}

@media (max-width: 960px) {
  .page-title-row { align-items: flex-start; }
  .switch-row { flex-direction: column; gap: 12px; padding-left: 0; }
}

.hero.panel { border-radius: 20px; }
</style>

