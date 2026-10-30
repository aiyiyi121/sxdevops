<template>
  <div class="knowledge-config-page workbench-page-shell">
    <section v-if="!embedded" class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon"><el-icon><Setting /></el-icon></span>
          <h2>图谱配置</h2>
          <p class="page-inline-desc">把可观测性、事件中心和基础设施线索绑定成 AIOps 可识别的知识图谱环境</p>
        </div>
      </div>
    </section>

    <section class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <div class="toolbar-title">环境关联配置</div>
          <div class="toolbar-desc">环境名和别名会作为 AIOps 分析入口，关联来源用于生成图谱节点和辅助定位证据。<strong>信息越多根因分析越准</strong></div>
        </div>
        <div class="toolbar-actions">
          <el-button size="small" :loading="loading" @click="loadData">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button v-if="canManage" type="primary" size="small" @click="openDialog()">
            <el-icon><Plus /></el-icon>
            新增关联
          </el-button>
        </div>
      </div>
      <el-table v-loading="loading" :data="environments" row-key="id">
        <el-table-column prop="name" label="图谱环境名" min-width="150">
          <template #default="{ row }">
            <div class="env-name">
              <span>{{ row.name }}</span>
              <el-tag v-if="row.is_default" size="small" type="warning">默认</el-tag>
            </div>
            <div v-if="row.description" class="env-desc">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="环境别名" min-width="150">
          <template #default="{ row }"><TagList :items="row.aliases" /></template>
        </el-table-column>
        <el-table-column label="事件中心环境" min-width="170">
          <template #default="{ row }"><TagList :items="row.event_environments" /></template>
        </el-table-column>
        <el-table-column label="可观测性来源" min-width="220">
          <template #default="{ row }"><TagList :items="observabilityNames(row)" /></template>
        </el-table-column>
        <el-table-column label="基础设施" min-width="190">
          <template #default="{ row }"><TagList :items="infrastructureNames(row)" /></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button v-if="!row.is_default" size="small" link type="primary" :disabled="!row.is_enabled" @click="setDefaultEnvironment(row)">设为默认</el-button>
              <el-button size="small" link type="primary" @click="openDialog(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="removeEnvironment(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="dialog.visible" :title="dialog.editingId ? '编辑图谱环境' : '新增图谱环境'" width="860px" append-to-body destroy-on-close>
      <el-form label-position="top" ref="formRef" :model="form" :rules="rules" label-width="128px">
        <el-form-item label="环境名" prop="name">
          <el-input v-model.trim="form.name" placeholder="例如：交易生产 / 核心测试" />
        </el-form-item>
        <el-form-item label="环境别名">
          <el-select
            v-model="form.aliases"
            multiple
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="例如：生产 / 线上 / prod"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model.trim="form.description" maxlength="255" show-word-limit placeholder="可选，说明这个图谱环境绑定的业务范围" />
        </el-form-item>
        <el-form-item label="事件中心环境">
          <el-select v-model="form.event_environments" multiple filterable clearable placeholder="选择一个或多个事件中心环境">
            <el-option v-for="item in catalog.event_environments" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <div class="form-group-card">
          <div class="form-group-card__head">
            <strong>可观测性关联配置</strong>
            <span>告警、系统态势、日志、链路、看板和跳转关联统一作为分析证据。</span>
          </div>
          <el-form-item label="指标数据源">
            <el-select v-model="form.metric_datasource_ids" multiple filterable clearable placeholder="选择一个或多个 Prometheus 兼容指标数据源">
              <el-option v-for="item in catalog.metric_datasources" :key="item.id" :label="datasourceLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="日志数据源">
            <el-select v-model="form.log_datasource_ids" multiple filterable clearable placeholder="选择一个或多个日志中心数据源">
              <el-option v-for="item in catalog.log_datasources" :key="item.id" :label="datasourceLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="链路数据源">
            <el-select v-model="form.tracing_datasource_ids" multiple filterable clearable placeholder="选择一个或多个链路追踪数据源">
              <el-option v-for="item in catalog.tracing_datasources" :key="item.id" :label="datasourceLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="告警中心环境">
            <el-select v-model="form.alert_environments" multiple filterable clearable placeholder="选择一个或多个告警中心环境">
              <el-option v-for="item in catalog.alert_environments" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="仪表盘目录">
            <el-select v-model="form.grafana_folder_keys" multiple filterable clearable placeholder="选择一个或多个仪表盘目录">
              <el-option v-for="item in catalog.grafana_folders" :key="item.key" :label="folderLabel(item)" :value="item.key" />
            </el-select>
          </el-form-item>
          <el-form-item label="关联配置">
            <el-select v-model="form.observability_link_ids" multiple filterable clearable placeholder="选择日志 / 链路 / 看板之间的关联配置">
              <el-option v-for="item in catalog.observability_links" :key="item.id" :label="observabilityLinkLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="systemPostureEnabled" label="系统态势环境">
            <el-select v-model="form.posture_environments" multiple filterable clearable placeholder="选择一个或多个系统态势环境">
              <el-option v-for="item in catalog.posture_environments" :key="item.key" :label="postureEnvironmentLabel(item)" :value="item.key" />
            </el-select>
          </el-form-item>
        </div>
        <div class="form-group-card">
          <div class="form-group-card__head">
            <strong>运行与任务中心资源底座</strong>
            <span>运行环境用于选择服务所在载体，K8s 集群和 Docker 环境按实际部署形态选择一种即可。</span>
          </div>
          <el-form-item label="K8s 集群">
            <el-select v-model="form.k8s_cluster_ids" multiple filterable clearable placeholder="选择此图谱所在的 K8s 集群">
              <el-option v-for="item in catalog.k8s_clusters" :key="item.id" :label="k8sClusterLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <div v-if="selectedK8sClusters.length" class="namespace-config">
            <div class="namespace-config-title">图谱展示命名空间</div>
            <div v-for="cluster in selectedK8sClusters" :key="cluster.id" class="namespace-row">
              <div class="namespace-cluster">
                <strong>{{ cluster.name }}</strong>
                <span>展示在图谱拓扑图上的命名空间，不限制智能助手查询</span>
              </div>
              <el-select
                v-model="form.k8s_namespaces[String(cluster.id)]"
                multiple
                filterable
                allow-create
                default-first-option
                clearable
                placeholder="选择展示在图谱拓扑图上的命名空间"
              >
                <el-option v-for="namespace in namespaceOptionsForCluster(cluster)" :key="namespace" :label="namespace" :value="namespace" />
              </el-select>
            </div>
          </div>
          <el-form-item label="Docker 环境">
            <el-select v-model="form.docker_host_ids" multiple filterable clearable placeholder="选择此图谱所在的 Docker 环境">
              <el-option v-for="item in catalog.docker_hosts" :key="item.id" :label="dockerHostLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <div class="field-hint">任务中心资源底座环境用于 AIOps 生成巡检、脚本执行等任务时确定可选目标资源范围。</div>
          <el-form-item label="任务中心资源底座">
            <el-select v-model="form.task_resource_environment_ids" multiple filterable clearable placeholder="选择任务中心资源底座">
              <el-option v-for="item in catalog.task_resource_environments" :key="item.id" :label="taskResourceEnvironmentLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="启用">
          <el-switch v-model="form.is_enabled" />
        </el-form-item>
        <el-form-item label="默认图谱">
          <el-switch
            v-model="form.is_default"
            active-text="打开图谱视图时优先展示"
            inactive-text="普通图谱"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, ElTag } from 'element-plus'
import { Plus, RefreshRight, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { SYSTEM_POSTURE_ENABLED } from '@/config/features'
import {
  createAIOpsKnowledgeEnvironment,
  deleteAIOpsKnowledgeEnvironment,
  getAIOpsKnowledgeEnvironmentCatalog,
  getAIOpsKnowledgeEnvironments,
  updateAIOpsKnowledgeEnvironment,
} from '@/api/modules/aiops'

const TagList = defineComponent({
  name: 'TagList',
  props: {
    items: { type: Array, default: () => [] },
  },
  setup(props) {
    return () => {
      const values = (props.items || []).filter(Boolean)
      if (!values.length) return h('span', { class: 'muted' }, '未关联')
      return h('div', { class: 'tag-list' }, values.slice(0, 4).map(item => h(ElTag, { key: String(item), size: 'small', type: 'info' }, () => String(item))).concat(
        values.length > 4 ? [h(ElTag, { key: '__more', size: 'small' }, () => `+${values.length - 4}`)] : [],
      ))
    }
  },
})

defineProps({
  embedded: { type: Boolean, default: false },
})

const authStore = useAuthStore()
const systemPostureEnabled = SYSTEM_POSTURE_ENABLED
const canManage = computed(() => authStore.hasPermission('aiops.knowledge.manage'))
const loading = ref(false)
const saving = ref(false)
const formRef = ref(null)
const environments = ref([])
const catalog = reactive({
  event_environments: [],
  grafana_folders: [],
  metric_datasources: [],
  log_datasources: [],
  tracing_datasources: [],
  observability_links: [],
  alert_environments: [],
  posture_environments: [],
  k8s_clusters: [],
  docker_hosts: [],
  task_resource_environments: [],
})
const dialog = reactive({ visible: false, editingId: null })
const form = reactive({
  name: '',
  aliases: [],
  description: '',
  event_environments: [],
  grafana_folder_keys: [],
  metric_datasource_ids: [],
  log_datasource_ids: [],
  tracing_datasource_ids: [],
  observability_link_ids: [],
  alert_environments: [],
  posture_environments: [],
  k8s_cluster_ids: [],
  k8s_namespaces: {},
  docker_host_ids: [],
  task_resource_environment_ids: [],
  is_default: false,
  is_enabled: true,
})

const rules = {
  name: [{ required: true, message: '请填写知识图谱环境名', trigger: 'blur' }],
}

const selectedK8sClusters = computed(() => {
  const selected = new Set((form.k8s_cluster_ids || []).map(id => Number(id)))
  return catalog.k8s_clusters.filter(item => selected.has(Number(item.id)))
})

function resetForm(row = null) {
  dialog.editingId = row?.id || null
  form.name = row?.name || ''
  form.aliases = [...(row?.aliases || [])]
  form.description = row?.description || ''
  form.event_environments = [...(row?.event_environments || [])]
  form.grafana_folder_keys = [...(row?.grafana_folder_keys || [])]
  form.metric_datasource_ids = [...(row?.metric_datasource_ids || [])]
  form.log_datasource_ids = [...(row?.log_datasource_ids || [])]
  form.tracing_datasource_ids = [...(row?.tracing_datasource_ids || [])]
  form.observability_link_ids = [...(row?.observability_link_ids || [])]
  form.alert_environments = [...(row?.alert_environments || [])]
  form.posture_environments = systemPostureEnabled ? [...(row?.posture_environments || [])] : []
  form.k8s_cluster_ids = [...(row?.k8s_cluster_ids || [])]
  form.k8s_namespaces = { ...(row?.k8s_namespaces || {}) }
  form.docker_host_ids = [...(row?.docker_host_ids || [])]
  form.task_resource_environment_ids = [...(row?.task_resource_environment_ids || [])]
  form.is_default = row?.is_default ?? false
  form.is_enabled = row?.is_enabled ?? true
}

function hasAnyBinding() {
  return [
    form.event_environments,
    form.grafana_folder_keys,
    form.metric_datasource_ids,
    form.log_datasource_ids,
    form.tracing_datasource_ids,
    form.observability_link_ids,
    form.alert_environments,
    ...(systemPostureEnabled ? [form.posture_environments] : []),
    form.k8s_cluster_ids,
    form.docker_host_ids,
    form.task_resource_environment_ids,
  ].some(items => items.length)
}

function datasourceLabel(item) {
  return `${item.name} / ${item.provider_display || item.provider}`
}

function folderLabel(item) {
  return item.dashboard_count ? `${item.label}（${item.dashboard_count} 个看板）` : item.label
}

function postureEnvironmentLabel(item) {
  const name = item?.name || ''
  const key = item?.key || ''
  if (!name) return key
  if (!key || key === name || key === 'prod') return name
  return `${name} / ${key}`
}

function observabilityLinkLabel(item) {
  const parts = [item.name]
  if (item.log_datasource_name || item.tracing_datasource_name) {
    parts.push(`${item.log_datasource_name || '--'} ↔ ${item.tracing_datasource_name || '--'}`)
  }
  if (item.grafana_dashboard_key) parts.push(`看板 ${item.grafana_dashboard_key}`)
  return parts.filter(Boolean).join(' / ')
}

function datasourceNames(ids = [], type = 'log') {
  const source = type === 'trace'
    ? catalog.tracing_datasources
    : type === 'metric'
      ? catalog.metric_datasources
      : catalog.log_datasources
  const nameMap = new Map(source.map(item => [Number(item.id), item.name]))
  return ids.map(id => nameMap.get(Number(id)) || `ID ${id}`)
}

function k8sClusterLabel(item) {
  return item.api_server ? `${item.name} / ${item.api_server}` : item.name
}

function namespaceOptionsForCluster(cluster) {
  return cluster.namespaces || []
}

function dockerHostLabel(item) {
  return item.ip_address ? `${item.name} / ${item.ip_address}` : item.name
}

function taskResourceEnvironmentLabel(item) {
  const suffix = Number(item.resource_count || 0) ? ` / ${item.resource_count} 个资源` : ''
  return `${item.name}${suffix}`
}

function postureEnvironmentNames(keys = []) {
  const nameMap = new Map(catalog.posture_environments.map(item => [item.key, postureEnvironmentLabel(item)]))
  return keys.map(key => nameMap.get(key) || key)
}

function observabilityLinkNames(ids = []) {
  const nameMap = new Map(catalog.observability_links.map(item => [Number(item.id), item.name]))
  return ids.map(id => nameMap.get(Number(id)) || `关联配置 ID ${id}`)
}

function observabilityNames(row) {
  return [
    ...(row.alert_environments || []).map(name => `告警: ${name}`),
    ...(systemPostureEnabled ? (row.posture_environments || []).map(name => `系统态势: ${postureEnvironmentNames([name])[0]}`) : []),
    ...(row.observability_link_ids || []).map(name => `关联: ${observabilityLinkNames([name])[0]}`),
    ...(row.grafana_folder_keys || []).map(name => `看板: ${name}`),
    ...(row.metric_datasource_ids || []).map(name => `指标: ${datasourceNames([name], 'metric')[0]}`),
    ...(row.log_datasource_ids || []).map(name => `日志: ${datasourceNames([name], 'log')[0]}`),
    ...(row.tracing_datasource_ids || []).map(name => `链路: ${datasourceNames([name], 'trace')[0]}`),
  ]
}

function infrastructureNames(row) {
  const k8sMap = new Map(catalog.k8s_clusters.map(item => [Number(item.id), `K8s: ${item.name}`]))
  const dockerMap = new Map(catalog.docker_hosts.map(item => [Number(item.id), `Docker: ${item.name}`]))
  const resourceEnvMap = new Map(catalog.task_resource_environments.map(item => [Number(item.id), `任务中心资源底座: ${item.name}`]))
  return [
    ...(row.k8s_cluster_ids || []).map((id) => {
      const namespaces = row.k8s_namespaces?.[String(id)] || []
      const suffix = namespaces.length ? ` / 图谱展示: ${namespaces.join(', ')}` : ''
      return `${k8sMap.get(Number(id)) || `K8s ID ${id}`}${suffix}`
    }),
    ...(row.docker_host_ids || []).map(id => dockerMap.get(Number(id)) || `Docker ID ${id}`),
    ...(row.task_resource_environment_ids || []).map(id => resourceEnvMap.get(Number(id)) || `任务中心资源底座 ID ${id}`),
  ]
}

async function loadData() {
  loading.value = true
  try {
    const [list, options] = await Promise.all([
      getAIOpsKnowledgeEnvironments(),
      getAIOpsKnowledgeEnvironmentCatalog(),
    ])
    environments.value = Array.isArray(list) ? list : (list.results || [])
    Object.assign(catalog, {
      event_environments: options.event_environments || [],
      grafana_folders: options.grafana_folders || [],
      metric_datasources: options.metric_datasources || [],
      log_datasources: options.log_datasources || [],
      tracing_datasources: options.tracing_datasources || [],
      observability_links: options.observability_links || [],
      alert_environments: options.alert_environments || [],
      posture_environments: systemPostureEnabled ? (options.posture_environments || []) : [],
      k8s_clusters: options.k8s_clusters || [],
      docker_hosts: options.docker_hosts || [],
      task_resource_environments: options.task_resource_environments || [],
    })
  } finally {
    loading.value = false
  }
}

function openDialog(row = null) {
  resetForm(row)
  dialog.visible = true
}

async function submitForm() {
  await formRef.value?.validate()
  if (!hasAnyBinding()) {
    ElMessage.warning('请至少选择一个事件中心、看板目录、日志、链路、告警、系统态势、K8s 集群、Docker 环境或任务中心资源底座来源')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name,
      aliases: form.aliases,
      description: form.description,
      event_environments: form.event_environments,
      grafana_folder_keys: form.grafana_folder_keys,
      metric_datasource_ids: form.metric_datasource_ids,
      log_datasource_ids: form.log_datasource_ids,
      tracing_datasource_ids: form.tracing_datasource_ids,
      observability_link_ids: form.observability_link_ids,
      alert_environments: form.alert_environments,
      posture_environments: systemPostureEnabled ? form.posture_environments : [],
      k8s_cluster_ids: form.k8s_cluster_ids,
      k8s_namespaces: form.k8s_namespaces,
      docker_host_ids: form.docker_host_ids,
      task_resource_environment_ids: form.task_resource_environment_ids,
      is_default: form.is_default,
      is_enabled: form.is_enabled,
    }
    if (dialog.editingId) {
      await updateAIOpsKnowledgeEnvironment(dialog.editingId, payload)
    } else {
      await createAIOpsKnowledgeEnvironment(payload)
    }
    ElMessage.success('知识图谱环境已保存')
    dialog.visible = false
    await loadData()
  } finally {
    saving.value = false
  }
}

async function setDefaultEnvironment(row) {
  await updateAIOpsKnowledgeEnvironment(row.id, { is_default: true })
  ElMessage.success(`已设为默认图谱：${row.name}`)
  await loadData()
}

async function removeEnvironment(row) {
  await ElMessageBox.confirm(`确认删除知识图谱环境「${row.name}」？`, '删除确认', { type: 'warning' })
  await deleteAIOpsKnowledgeEnvironment(row.id)
  ElMessage.success('已删除')
  await loadData()
}

onMounted(loadData)

watch(() => [...form.k8s_cluster_ids], (ids) => {
  const selected = new Set(ids.map(id => String(id)))
  Object.keys(form.k8s_namespaces || {}).forEach((clusterId) => {
    if (!selected.has(clusterId)) {
      delete form.k8s_namespaces[clusterId]
    }
  })
  ids.forEach((id) => {
    const key = String(id)
    if (!Array.isArray(form.k8s_namespaces[key])) {
      form.k8s_namespaces[key] = []
    }
  })
})
</script>

<style scoped>
.knowledge-config-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel {
  padding: 14px 16px;
  border: 1px solid rgba(36, 91, 219, 0.09);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.hero {
  min-height: 70px;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
}

.hero,
.hero-copy,
.hero-title-row,
.section-toolbar,
.toolbar-head,
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hero-title-row h2 {
  margin: 0;
  color: #0f172a;
  font-size: 22px;
  font-weight: 800;
  line-height: 1.2;
}

.page-inline-desc {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.hero-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #245bdb;
  background: rgba(36, 91, 219, 0.09);
}

.env-desc,
.muted {
  color: #64748b;
  font-size: 13px;
}

.workbench-card {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.section-toolbar {
  justify-content: space-between;
  margin-bottom: 10px;
}

.toolbar-title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 800;
}

.toolbar-desc {
  color: #64748b;
  font-size: 13px;
}

.toolbar-desc strong {
  margin-left: 4px;
  color: #0f172a;
  font-weight: 800;
}

.toolbar-actions {
  justify-content: flex-end;
}

.env-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: #0f172a;
  font-weight: 700;
}

.tag-list {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.table-actions :deep(.el-button) {
  margin-left: 0;
}

.form-group-card {
  margin: 0 0 14px;
  padding: 12px 14px 2px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: #f8fafc;
}

.form-group-card__head {
  margin: 0 0 10px 128px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.form-group-card__head strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.form-group-card__head span,
.field-hint {
  color: #64748b;
  font-size: 12px;
}

.field-hint {
  margin: -2px 0 10px 128px;
}

.namespace-config {
  margin: -4px 0 16px 128px;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.78);
}

.namespace-config-title {
  margin-bottom: 8px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.namespace-row {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.namespace-row + .namespace-row {
  margin-top: 8px;
}

.namespace-cluster {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: #64748b;
  font-size: 11px;
}

.namespace-cluster strong {
  color: #0f172a;
  font-size: 12px;
}

:deep(.el-select) {
  width: 100%;
}

.hero.panel {
  border-radius: 20px;
}

@media (max-width: 900px) {
  .hero,
  .section-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    justify-content: flex-start;
  }

  .namespace-config,
  .form-group-card__head,
  .field-hint {
    margin-left: 0;
  }

  .namespace-row {
    grid-template-columns: 1fr;
  }
}
</style>
