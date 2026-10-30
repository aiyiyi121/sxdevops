<template>
  <div class="fade-in workbench-page-shell docker-page-shell">
    <section class="hero panel docker-hero">
      <div class="release-hero-title-row release-hero-title-inline">
        <span class="release-header-icon"><el-icon><Platform /></el-icon></span><h2>Docker 环境</h2><p class="subtitle inline-subtitle">统一查看环境、容器与镜像。</p>
      </div>
    </section>
    <div class="neo-tabs theme-blue docker-main-tabs">
      <button v-for="tab in mainTabs" :key="tab.key" class="neo-tab-btn" :class="{ active: activeTab === tab.key }" @click="switchTab(tab.key)"><el-icon><component :is="tab.icon" /></el-icon>{{ tab.label }}</button>
    </div>
    <div class="workbench-card docker-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head"><span class="toolbar-title">{{ currentTab.label }}</span><span class="toolbar-desc">{{ currentTab.description }}</span></div>
        <div class="workbench-card-actions">
          <template v-if="activeTab !== 'hosts'"><el-select v-model="refreshSeconds" aria-label="自动刷新" class="refresh-select"><el-option label="手动刷新" :value="0" /><el-option v-for="seconds in [15, 30, 60]" :key="seconds" :label="`${seconds} 秒刷新`" :value="seconds" /></el-select><span v-if="updatedAt" class="updated-at">{{ updatedAt }} 更新</span></template>
          <el-button class="filter-refresh-btn" :loading="hostsLoading || loading" @click="refreshView"><el-icon><RefreshRight /></el-icon>刷新</el-button>
          <el-button v-if="activeTab === 'hosts' && canManage" class="filter-refresh-btn" @click="openHostDialog()"><el-icon><Plus /></el-icon>新增环境</el-button>
        </div>
      </div>
      <template v-if="activeTab === 'hosts'">
        <div class="workbench-toolbar workbench-toolbar--history"><el-input v-model="hostKeyword" clearable placeholder="搜索环境名称 / IP / 描述" aria-label="搜索环境" class="search-input" /><div class="toolbar-spacer"></div><el-tag type="info" effect="plain">环境 {{ hosts.length }}</el-tag><el-tag type="success" effect="plain">在线 {{ hosts.filter(host => host.status === 'connected').length }}</el-tag></div>
        <div class="docker-host-layout">
          <div v-loading="hostsLoading" class="docker-host-selector">
            <div class="docker-host-grid">
              <article v-for="host in filteredHosts" :key="host.id" class="docker-host-tile" :class="{ selected: host.id === selectedHostId }">
                <div class="host-tile-heading"><span class="provider-mark">Docker</span><el-tag size="small" :type="host.status === 'connected' ? 'success' : 'info'" effect="plain">{{ host.status === 'connected' ? '在线' : '未连接' }}</el-tag></div>
                <strong class="host-name" :title="host.name">{{ host.name }}</strong><span class="host-address">{{ host.ip_address }}:{{ host.ssh_port || 22 }}</span>
                <dl class="host-meta"><div><dt>版本</dt><dd>{{ host.docker_api_version || '—' }}</dd></div><div><dt>描述</dt><dd :title="host.description">{{ host.description || '—' }}</dd></div></dl>
                <div class="host-tile-footer"><div class="host-tile-actions"><el-button v-if="canManage" link size="small" :loading="testingHost === host.id" @click="testHost(host)">测试</el-button><el-button v-if="canManage" link size="small" @click="openHostDialog(host)">编辑</el-button><el-button v-if="canManage" link type="danger" size="small" @click="deleteHost(host)">删除</el-button></div><el-button size="small" :type="selectedHostId === host.id ? 'default' : 'primary'" :plain="selectedHostId !== host.id" :disabled="selectedHostId === host.id" @click="selectedHostId = host.id">{{ selectedHostId === host.id ? '已选择' : '选择环境' }}</el-button></div>
              </article>
            </div>
            <el-empty v-if="!hostsLoading && !filteredHosts.length" :description="hosts.length ? '没有匹配的环境' : '暂无 Docker 环境'" :image-size="70" />
          </div>
          <aside class="docker-overview" v-loading="summaryLoading">
            <template v-if="selectedHost">
              <div class="overview-heading"><div><span>环境概要</span><strong>{{ selectedHost.name }}</strong></div><el-tag size="small" :type="selectedHost.status === 'connected' ? 'success' : 'info'" effect="plain">{{ selectedHost.status === 'connected' ? '在线' : '未连接' }}</el-tag></div>
              <div v-if="summaryError" class="inline-error" role="alert">{{ summaryError }}<el-button link type="primary" @click="loadSummary(true)">重试</el-button></div>
              <dl class="overview-meta"><div><dt>Docker</dt><dd>{{ summary?.server_version || selectedHost.docker_api_version || '—' }}</dd></div><div><dt>操作系统</dt><dd :title="summary?.os">{{ summary?.os || '—' }}</dd></div><div><dt>架构 / 内核</dt><dd :title="summary?.kernel">{{ summary ? `${summary.architecture || '—'} / ${summary.kernel || '—'}` : '—' }}</dd></div><div><dt>存储驱动</dt><dd>{{ summary?.storage_driver || '—' }}</dd></div></dl>
              <div class="overview-stats"><button v-for="stat in overviewStats" :key="stat.label" type="button" :class="stat.tone" :disabled="!stat.tab" @click="openOverviewStat(stat)"><span>{{ stat.label }}</span><strong>{{ stat.value }}</strong></button></div>
              <dl class="overview-meta overview-connection"><div><dt>SSH</dt><dd>{{ selectedHost.ssh_user || 'root' }}@{{ selectedHost.ip_address }}:{{ selectedHost.ssh_port || 22 }}</dd></div><div><dt>数据目录</dt><dd :title="summary?.root_dir">{{ summary?.root_dir || '—' }}</dd></div></dl>
            </template><el-empty v-else description="请选择一个环境" :image-size="70" />
          </aside>
        </div>
      </template>
      <template v-else>
        <div class="workbench-toolbar workbench-toolbar--history docker-resource-toolbar">
          <el-select v-model="selectedHostId" filterable placeholder="选择 Docker 环境" aria-label="当前 Docker 环境" class="host-select"><el-option v-for="host in hosts" :key="host.id" :value="host.id" :label="`${host.name} · ${host.ip_address}`" /></el-select>
          <el-input v-model="resourceKeyword" clearable :placeholder="activeTab === 'containers' ? '搜索名称 / 镜像 / 端口 / ID' : '搜索仓库 / 标签 / ID'" aria-label="搜索资源" class="search-input" />
          <el-select v-if="activeTab === 'containers'" v-model="stateFilter" aria-label="容器状态" class="state-select"><el-option label="全部状态" value="all" /><el-option label="运行中" value="running" /><el-option label="已停止" value="stopped" /><el-option label="已暂停" value="paused" /><el-option label="需关注" value="attention" /></el-select>
          <el-select v-else v-model="imageFilter" aria-label="镜像类型" class="state-select"><el-option label="全部镜像" value="all" /><el-option label="悬空镜像" value="dangling" /></el-select>
          <div class="toolbar-spacer"></div>
          <template v-if="activeTab === 'images' && canManage"><el-button :disabled="!selectedHost || Boolean(actionBusy)" @click="pruneImages">清理悬空镜像</el-button><el-button type="danger" plain :disabled="!imageSelection.length || Boolean(actionBusy)" @click="removeImages(imageSelection)">删除已选 {{ imageSelection.length || '' }}</el-button></template>
        </div>
        <div v-if="resourceError" class="inline-error" role="alert">{{ resourceError }}<el-button link type="primary" @click="loadResources(true)">重试</el-button></div>
        <el-empty v-if="!selectedHost" description="请先添加或选择一个 Docker 环境" :image-size="80" />
        <template v-else>
          <div class="resource-status"><span>{{ selectedHost.name }}</span><template v-if="activeTab === 'containers'"><el-tag effect="plain" type="success">运行 {{ containerStats.running }}</el-tag><el-tag effect="plain" type="warning">需关注 {{ containerStats.attention }}</el-tag></template><template v-else><el-tag effect="plain" type="info">镜像 {{ rows.length }}</el-tag><el-tag effect="plain" type="warning">悬空 {{ rows.filter(isDangling).length }}</el-tag></template><span v-if="actionBusy" class="operation-progress">正在执行操作…</span></div>
          <el-table v-if="activeTab === 'containers'" v-loading="loading" :data="pagedRows" row-key="id" stripe class="docker-table" empty-text="暂无匹配的容器">
            <el-table-column label="容器名称" min-width="190"><template #default="{ row }"><div class="resource-name"><i :class="['state-dot', row.state]"></i><el-button link type="primary" @click="inspect(row)">{{ row.name }}</el-button></div><span class="resource-subtext">{{ row.id }}</span></template></el-table-column>
            <el-table-column prop="image" label="镜像" min-width="230" show-overflow-tooltip />
            <el-table-column label="状态" min-width="180"><template #default="{ row }"><el-tag size="small" :type="stateTone(row)">{{ row.state }}</el-tag><span class="resource-subtext" :title="row.status">{{ row.status }}</span></template></el-table-column>
            <el-table-column prop="ports" label="端口映射" min-width="210" show-overflow-tooltip /><el-table-column prop="created" label="创建时间" min-width="180" show-overflow-tooltip />
            <el-table-column label="操作" width="72" fixed="right"><template #default="{ row }"><div class="row-actions"><ResourceActions :actions="containerActions(row)" @select="action => handleContainerAction(row, action.key)" /></div></template></el-table-column>
          </el-table>
          <el-table v-else ref="imageTable" v-loading="loading" :data="pagedRows" :row-key="imageRowKey" stripe class="docker-table" empty-text="暂无匹配的镜像" @selection-change="imageSelection = $event">
            <el-table-column v-if="canManage" type="selection" width="44" /><el-table-column label="仓库" min-width="260"><template #default="{ row }"><el-button link type="primary" class="image-repository" @click="inspect(row)">{{ row.repository }}</el-button><span class="resource-subtext">{{ row.id }}</span></template></el-table-column>
            <el-table-column label="标签" min-width="140"><template #default="{ row }"><el-tag :type="isDangling(row) ? 'warning' : 'info'" size="small" effect="plain">{{ row.tag }}</el-tag></template></el-table-column><el-table-column prop="size" label="大小" width="120" /><el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
            <el-table-column label="操作" width="92" fixed="right"><template #default="{ row }"><ResourceActions :actions="imageActions" @select="action => action.key === 'inspect' ? inspect(row) : removeImages([row])" /></template></el-table-column>
          </el-table>
          <div class="table-footer"><span>共 {{ filteredRows.length }} {{ activeTab === 'containers' ? '个容器' : '条镜像记录' }}</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[20, 50, 100]" :total="filteredRows.length" layout="sizes, prev, pager, next" small /></div>
        </template>
      </template>
    </div>
    <ContainerLogs v-if="logVisible" v-model="logVisible" source="docker" :cluster="dialogHost" :pod="dialogResource" />
    <ContainerTerminal v-if="terminalVisible" v-model="terminalVisible" kind="docker" :cluster="dialogHost" :pod="dialogResource" />
    <el-dialog v-model="inspectVisible" :title="`资源详情 · ${inspectName}`" width="90%" top="4vh" class="docker-inspect-dialog" :fullscreen="inspectFullscreen" append-to-body destroy-on-close @close="inspectGeneration++">
      <div class="inspect-workspace" :class="{ fullscreen: inspectFullscreen }" v-loading="inspectLoading">
        <div class="inspect-toolbar"><span>{{ dialogHost.name }}</span><div class="toolbar-spacer"></div><el-button size="small" :disabled="!inspectData" @click="copyInspect">复制 JSON</el-button><el-button size="small" @click="inspectFullscreen = !inspectFullscreen">{{ inspectFullscreen ? '退出全屏' : '全屏' }}</el-button></div>
        <div class="inspect-scroll"><div v-if="inspectError" class="inline-error">{{ inspectError }}</div><el-descriptions v-if="inspectData" :column="2" border size="small"><el-descriptions-item v-for="field in inspectFields" :key="field.label" :label="field.label">{{ field.value }}</el-descriptions-item></el-descriptions><pre v-if="inspectData" class="inspect-json">{{ JSON.stringify(inspectData, null, 2) }}</pre></div>
      </div>
    </el-dialog>
    <el-dialog class="workbench-edit-dialog" v-model="hostDialogVisible" :title="editingHostId ? '编辑 Docker 环境' : '新增 Docker 环境'" width="min(560px, 94vw)" top="5vh" append-to-body destroy-on-close :close-on-click-modal="false">
      <el-form class="workbench-editor-form--sectioned" label-position="top" ref="hostFormRef" :model="hostForm" :rules="hostRules" label-width="94px" @submit.prevent="saveHost">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>环境信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="环境名称" prop="name"><el-input v-model="hostForm.name" maxlength="100" placeholder="例如 prod-docker-01" /></el-form-item><el-form-item label="IP 地址" prop="ip_address"><el-input v-model="hostForm.ip_address" placeholder="IPv4 / IPv6 地址" /></el-form-item><section class="workbench-editor-section workbench-editor-section--tinted">
                                                                                                                                                                                                                                                                                            <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>SSH 连接</h3></div>
                                                                                                                                                                                                                                                                                            <div class="workbench-editor-grid">

                                                                                                                                                                                                                                                                                            </div>
                                                                                                                                                                                                                                                                                          </section><el-form-item label="SSH 端口" prop="ssh_port"><el-input-number v-model="hostForm.ssh_port" :min="1" :max="65535" controls-position="right" /></el-form-item><el-form-item label="SSH 用户" prop="ssh_user"><el-input v-model="hostForm.ssh_user" placeholder="root" /></el-form-item><el-form-item label="SSH 密码"><el-input v-model="hostForm.ssh_password" type="password" show-password autocomplete="new-password" :placeholder="editingHostId ? '留空保留原密码' : '请输入 SSH 密码'" /></el-form-item><el-form-item class="workbench-editor-full" label="描述"><el-input v-model="hostForm.description" type="textarea" :rows="2" /></el-form-item>
          </div>
        </section>
      </el-form><template #footer><el-button @click="hostDialogVisible = false">取消</el-button><el-button type="primary" :loading="savingHost" @click="saveHost">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useRouteTabState } from '@/composables/useRouteTabState'
import ResourceActions from '@/components/k8s/K8sResourceActions.vue'
import ContainerLogs from '@/components/k8s/K8sPodLogs.vue'
import ContainerTerminal from '@/components/k8s/K8sTerminalDialog.vue'
import { copyText } from '@/utils/clipboard'
import {
  createDockerHost, deleteDockerHost, dockerContainerAction, dockerContainerRemove,
  dockerPruneDanglingImages, dockerRemoveImages, getDockerContainerInspect, getDockerImageInspect,
  getDockerContainers, getDockerHosts, getDockerImages, getDockerSummary, testDockerConnection, updateDockerHost,
} from '@/api/modules/container'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('ops.docker.manage'))
const canExec = computed(() => authStore.hasPermission('ops.docker.exec'))
const mainTabs = [
  { key: 'hosts', label: '环境管理', icon: 'OfficeBuilding', description: '环境接入与运行概要' },
  { key: 'containers', label: '容器管理', icon: 'Box', description: '容器状态、日志与交互式终端' },
  { key: 'images', label: '镜像管理', icon: 'Files', description: '镜像详情与空间清理' },
]
const { activeTab, switchTab } = useRouteTabState({ tabs: () => mainTabs.map(tab => tab.key), defaultTab: 'hosts' })
const currentTab = computed(() => mainTabs.find(tab => tab.key === activeTab.value) || mainTabs[0])
const hosts = shallowRef([])
const hostsLoading = ref(false)
const hostKeyword = ref('')
const selectedHostId = ref(Number(localStorage.getItem('sxdevops_docker_host')) || null)
const selectedHost = computed(() => hosts.value.find(host => host.id === selectedHostId.value))
const filteredHosts = computed(() => hosts.value.filter(host => matches(host, ['name', 'ip_address', 'description'], hostKeyword.value)))
const summary = shallowRef(null)
const summaryLoading = ref(false)
const summaryError = ref('')
const rows = shallowRef([])
const loading = ref(false)
const resourceError = ref('')
const resourceKeyword = ref('')
const stateFilter = ref('all')
const imageFilter = ref('all')
const page = ref(1)
const pageSize = ref(20)
const imageTable = ref(null)
const imageSelection = ref([])
const refreshSeconds = ref(0)
const updatedAt = ref('')
const actionBusy = ref('')
let mounted = false
let disposed = false
let resourceGeneration = 0
let summaryGeneration = 0
let resourceController = null
let summaryController = null
let hostsController = null
let refreshTimer = null

function matches(item, keys, keyword) {
  const search = keyword.trim().toLowerCase()
  return !search || keys.some(key => String(item[key] || '').toLowerCase().includes(search))
}
const isAttention = row => ['restarting', 'dead'].includes(row.state) || String(row.status).includes('unhealthy') || (row.state === 'exited' && !String(row.status).startsWith('Exited (0)'))
const isDangling = row => row.repository === '<none>' && row.tag === '<none>'
const imageRowKey = row => `${row.id}/${row.repository}:${row.tag}`
const containerStats = computed(() => ({ running: rows.value.filter(row => row.state === 'running').length, attention: rows.value.filter(isAttention).length }))
const filteredRows = computed(() => rows.value.filter(row => {
  if (activeTab.value === 'containers') {
    const stateMatches = stateFilter.value === 'all' || (stateFilter.value === 'stopped' ? ['exited', 'created', 'dead'].includes(row.state) : stateFilter.value === 'attention' ? isAttention(row) : row.state === stateFilter.value)
    return stateMatches && matches(row, ['id', 'name', 'image', 'ports'], resourceKeyword.value)
  }
  return (imageFilter.value !== 'dangling' || isDangling(row)) && matches(row, ['id', 'repository', 'tag'], resourceKeyword.value)
}))
const pagedRows = computed(() => filteredRows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const overviewStats = computed(() => [
  { label: 'CPU 容量', value: summary.value?.cpus != null ? `${summary.value.cpus} 核` : '—' },
  { label: '内存容量', value: summary.value?.memory_bytes ? `${(summary.value.memory_bytes / 1024 ** 3).toFixed(1)} G` : '—' },
  { label: '镜像', value: summary.value?.images ?? '—', tab: 'images' },
  { label: '容器总数', value: summary.value?.containers ?? '—', tab: 'containers', filter: 'all' },
  { label: '运行中', value: summary.value?.running ?? '—', tab: 'containers', filter: 'running', tone: 'success' },
  { label: '已停止', value: summary.value?.stopped ?? '—', tab: 'containers', filter: 'stopped' },
])
function openOverviewStat(stat) { if (stat.tab) { if (stat.filter) stateFilter.value = stat.filter; switchTab(stat.tab) } }

async function fetchHosts() {
  hostsController?.abort()
  const controller = new AbortController()
  hostsController = controller
  hostsLoading.value = true
  try {
    const inventory = []
    let currentPage = 1
    let hasNext = true
    while (hasNext) {
      const result = await getDockerHosts({ page: currentPage }, controller.signal)
      inventory.push(...(result.results || result))
      hasNext = Boolean(result.next)
      currentPage += 1
    }
    if (controller.signal.aborted || disposed) return
    hosts.value = inventory
    if (!inventory.some(host => host.id === selectedHostId.value)) selectedHostId.value = inventory[0]?.id || null
  } catch (error) { if (error.code !== 'ERR_CANCELED') ElMessage.error('读取环境列表失败') }
  finally { if (hostsController === controller) hostsLoading.value = false }
}
async function loadSummary(force = false) {
  const generation = ++summaryGeneration
  summaryController?.abort()
  summaryError.value = ''
  const hostId = selectedHostId.value
  if (!hostId) { summary.value = null; summaryLoading.value = false; return }
  summaryController = new AbortController()
  summaryLoading.value = true
  try {
    const result = await getDockerSummary(hostId, force, summaryController.signal)
    if (generation === summaryGeneration && !disposed) summary.value = result
  } catch (error) { if (generation === summaryGeneration && error.code !== 'ERR_CANCELED') summaryError.value = error.response?.data?.detail || '概要读取失败，请检查环境连接' }
  finally { if (generation === summaryGeneration) summaryLoading.value = false }
}
async function loadResources(force = false) {
  const generation = ++resourceGeneration
  resourceController?.abort()
  resourceError.value = ''
  if (!selectedHostId.value || activeTab.value === 'hosts') { loading.value = false; return }
  const hostId = selectedHostId.value
  const tab = activeTab.value
  const controller = new AbortController()
  resourceController = controller
  loading.value = true
  try {
    const result = await (tab === 'containers' ? getDockerContainers : getDockerImages)(hostId, force, controller.signal)
    if (generation !== resourceGeneration || disposed) return
    rows.value = result
    imageSelection.value = []
    imageTable.value?.clearSelection()
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    if (generation === resourceGeneration && error.code !== 'ERR_CANCELED') { rows.value = []; resourceError.value = error.response?.data?.detail || '读取资源失败，请检查环境连接' }
  } finally { if (generation === resourceGeneration) loading.value = false }
}
async function refreshView() {
  if (activeTab.value === 'hosts') await fetchHosts()
  await Promise.allSettled([loadSummary(true), loadResources(true)])
}
function scheduleRefresh() {
  clearTimeout(refreshTimer)
  if (!refreshSeconds.value || activeTab.value === 'hosts' || disposed) return
  refreshTimer = setTimeout(async () => {
    if (!document.hidden && !actionBusy.value && !loading.value && !logVisible.value && !terminalVisible.value && !inspectVisible.value) await loadResources(true)
    scheduleRefresh()
  }, refreshSeconds.value * 1000)
}
watch([activeTab, selectedHostId], () => {
  localStorage.setItem('sxdevops_docker_host', selectedHostId.value || '')
  rows.value = []; summary.value = null; imageSelection.value = []; resourceKeyword.value = ''; page.value = 1; updatedAt.value = ''
  logVisible.value = terminalVisible.value = inspectVisible.value = false
  if (mounted) { loadSummary(); loadResources() }
  scheduleRefresh()
})
watch([resourceKeyword, stateFilter, imageFilter, pageSize], () => { page.value = 1; imageSelection.value = []; imageTable.value?.clearSelection() })
watch(() => filteredRows.value.length, total => { page.value = Math.min(page.value, Math.max(1, Math.ceil(total / pageSize.value))) })
watch([page, pageSize], async () => { imageSelection.value = []; await nextTick(); imageTable.value?.clearSelection() })
watch(refreshSeconds, scheduleRefresh)

function stateTone(row) { return isAttention(row) ? 'danger' : ({ running: 'success', paused: 'warning', restarting: 'warning', exited: 'info' }[row.state] || 'info') }
const imageActions = computed(() => [{ key: 'inspect', label: '查看详情', icon: 'yaml' }, ...(canManage.value ? [{ key: 'delete', label: '删除镜像', icon: 'delete', danger: true }] : [])])
function containerActions(row) {
  const actions = [
    { key: 'logs', label: '查看日志', icon: 'logs' },
    ...(canExec.value ? [{ key: 'exec', label: '进入终端', icon: 'shell', disabled: row.state !== 'running' || Boolean(actionBusy.value) }] : []),
    { key: 'inspect', label: '查看详情', icon: 'yaml' },
  ]
  if (!canManage.value) return actions
  if (['created', 'exited'].includes(row.state)) actions.push({ key: 'start', label: '启动容器', icon: 'restart' })
  if (row.state === 'running') actions.push({ key: 'stop', label: '停止容器', icon: 'restart' }, { key: 'restart', label: '重启容器', icon: 'restart' })
  actions.push({ key: 'delete', label: '删除容器', icon: 'delete', danger: true })
  return actions
}
async function confirmOperation(message, title = '确认操作') {
  try { await ElMessageBox.confirm(message, title, { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }); return true } catch { return false }
}
async function mutate(host, key, operation) {
  if (actionBusy.value || !canManage.value) return
  actionBusy.value = key
  try { const result = await operation(); ElMessage.success(result.message || '操作成功') } catch { }
  finally { if (!disposed && selectedHostId.value === host.id) await Promise.allSettled([loadResources(true), loadSummary(true)]); actionBusy.value = '' }
}
async function handleContainerAction(row, action) {
  if (action === 'logs') return openLogs(row)
  if (action === 'exec') return !actionBusy.value && openTerminal(row)
  if (action === 'inspect') return inspect(row)
  const host = selectedHost.value
  if (!host || !canManage.value || actionBusy.value) return
  const label = { start: '启动', stop: '停止', restart: '重启', delete: '删除' }[action]
  if (!label) return
  if (!await confirmOperation(`${label}环境「${host.name}」中的容器「${row.name}」？${action === 'delete' ? '运行中的容器将被强制停止，删除后无法恢复。' : action === 'stop' || action === 'restart' ? '可能影响当前业务。' : ''}`, `${label}容器`)) return
  await mutate(host, row.id, () => action === 'delete' ? dockerContainerRemove(row.id, host.id) : dockerContainerAction(row.id, host.id, action))
}
async function removeImages(selection) {
  const host = selectedHost.value
  const ids = [...new Set(selection.map(row => row.id))]
  if (!host || !ids.length || !canManage.value || actionBusy.value) return
  if (!await confirmOperation(`删除环境「${host.name}」中选中的 ${ids.length} 个镜像？同一镜像 ID 的所有标签均会受影响；仍被容器使用的镜像不会强制删除。`, '删除镜像')) return
  await mutate(host, 'images', () => dockerRemoveImages(host.id, ids))
}
async function pruneImages() {
  const host = selectedHost.value
  if (!host || !canManage.value || actionBusy.value) return
  if (!await confirmOperation(`清理环境「${host.name}」中未被使用且没有标签的悬空镜像？`, '清理悬空镜像')) return
  await mutate(host, 'prune', () => dockerPruneDanglingImages(host.id))
}

const logVisible = ref(false)
const terminalVisible = ref(false)
const dialogHost = shallowRef({})
const dialogResource = shallowRef({})
function openLogs(row) { dialogHost.value = { ...selectedHost.value }; dialogResource.value = { ...row }; logVisible.value = true }
function openTerminal(row) { if (canExec.value && row.state === 'running') { dialogHost.value = { ...selectedHost.value }; dialogResource.value = { ...row }; terminalVisible.value = true } }
const inspectVisible = ref(false)
const inspectFullscreen = ref(false)
const inspectLoading = ref(false)
const inspectData = shallowRef(null)
const inspectName = ref('')
const inspectError = ref('')
let inspectGeneration = 0
const inspectFields = computed(() => {
  const data = inspectData.value || {}
  return [{ label: 'ID', value: data.Id || '—' }, { label: '名称 / 标签', value: data.Name || data.RepoTags?.join(', ') || '—' }, { label: '状态 / 系统', value: data.State?.Status || data.Os || '—' }, { label: '创建时间', value: data.Created || '—' }]
})
async function inspect(row) {
  const host = selectedHost.value
  if (!host) return
  const generation = ++inspectGeneration
  const tab = activeTab.value
  dialogHost.value = { ...host }; inspectName.value = row.name || `${row.repository}:${row.tag}`; inspectData.value = null; inspectError.value = ''; inspectVisible.value = inspectLoading.value = true
  try { const result = await (tab === 'containers' ? getDockerContainerInspect : getDockerImageInspect)(row.id, host.id); if (generation === inspectGeneration && inspectVisible.value) inspectData.value = result }
  catch (error) { if (generation === inspectGeneration) inspectError.value = error.response?.data?.detail || '详情加载失败' }
  finally { if (generation === inspectGeneration) inspectLoading.value = false }
}
async function copyInspect() { try { await copyText(JSON.stringify(inspectData.value, null, 2)); ElMessage.success('已复制') } catch { ElMessage.error('复制失败') } }

const hostDialogVisible = ref(false)
const editingHostId = ref(null)
const savingHost = ref(false)
const testingHost = ref(null)
const hostFormRef = ref(null)
const newHostForm = () => ({ name: '', ip_address: '', ssh_port: 22, ssh_user: 'root', ssh_password: '', description: '' })
const hostForm = ref(newHostForm())
const hostRules = { name: [{ required: true, whitespace: true, message: '请填写环境名称', trigger: 'blur' }], ip_address: [{ required: true, whitespace: true, message: '请填写 IP 地址', trigger: 'blur' }], ssh_user: [{ required: true, whitespace: true, message: '请填写 SSH 用户', trigger: 'blur' }] }
function openHostDialog(host) {
  if (!canManage.value) return
  editingHostId.value = host?.id || null
  hostForm.value = host ? { name: host.name, ip_address: host.ip_address, ssh_port: host.ssh_port, ssh_user: host.ssh_user, ssh_password: '', description: host.description } : newHostForm()
  hostDialogVisible.value = true
}
async function saveHost() {
  if (!canManage.value || savingHost.value || !await hostFormRef.value?.validate().catch(() => false)) return
  savingHost.value = true
  const data = { ...hostForm.value, name: hostForm.value.name.trim(), ip_address: hostForm.value.ip_address.trim() }
  if (!data.ssh_password) delete data.ssh_password
  try {
    if (editingHostId.value) await updateDockerHost(editingHostId.value, data)
    else { const created = await createDockerHost(data); selectedHostId.value = created.id }
    hostDialogVisible.value = false; ElMessage.success('环境已保存'); await fetchHosts(); await loadSummary(true)
  } catch { } finally { savingHost.value = false }
}
async function testHost(host) {
  if (!canManage.value || testingHost.value) return
  testingHost.value = host.id
  try { const result = await testDockerConnection(host.id); ElMessage[result.success ? 'success' : 'error'](result.message); await fetchHosts(); if (selectedHostId.value === host.id) await loadSummary(true) }
  catch { } finally { testingHost.value = null }
}
async function deleteHost(host) {
  if (!canManage.value || !await confirmOperation(`删除环境「${host.name}」的接入配置？主机上的容器和镜像将保留。`, '删除环境')) return
  try { await deleteDockerHost(host.id); ElMessage.success('环境已删除'); await fetchHosts() } catch { }
}
onMounted(async () => { await fetchHosts(); if (disposed) return; mounted = true; await Promise.allSettled([loadSummary(), loadResources()]); scheduleRefresh() })
onBeforeUnmount(() => { disposed = true; mounted = false; resourceGeneration++; summaryGeneration++; inspectGeneration++; clearTimeout(refreshTimer); hostsController?.abort(); resourceController?.abort(); summaryController?.abort() })
</script>

<style scoped>
.docker-page-shell { display: flex; flex-direction: column; gap: 6px; }
.docker-page-shell > .hero, .docker-page-shell > .docker-main-tabs, .docker-page-shell > .docker-content-card { margin: 0; }
.hero.panel { padding: 14px 16px; border-radius: 20px; background: linear-gradient(135deg, #fbfdff, #f7faff 52%, #f9fbfd); border: 1px solid rgba(36, 91, 219, .09); }
.release-header-icon { display: inline-flex; align-items: center; justify-content: center; width: 42px; height: 42px; border-radius: 13px; background: #eaf1ff; color: #245bdb; font-size: 23px; flex-shrink: 0; }
.release-hero-title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }.release-hero-title-row h2 { margin: 0; font-size: 23px; color: #172b4d; }.inline-subtitle { margin: 0; color: #718096; font-size: 13px; }
.docker-main-tabs { display: flex; padding: 3px; gap: 8px; width: 100%; border-radius: 12px; border: 1px solid #e0e6ef; background: #f6f8fb; box-shadow: none; }
.docker-main-tabs .neo-tab-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 38px; padding: 0 18px; border-radius: 8px; font-size: 13px; font-weight: 700; line-height: 1.2; }.docker-main-tabs .neo-tab-btn.active { background: #e8f0ff; color: #245bdb; box-shadow: inset 0 0 0 1px #d5e3ff; }
.docker-content-card { display: flex; flex-direction: column; padding: 14px 16px; border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; min-width: 0; }
.section-toolbar, .toolbar-head, .workbench-card-actions, .workbench-toolbar, .host-tile-heading, .host-tile-footer, .host-tile-actions, .overview-heading, .resource-status, .table-footer, .row-actions, .inspect-toolbar { display: flex; align-items: center; gap: 8px; }
.section-toolbar { justify-content: space-between; flex-wrap: wrap; margin-bottom: 10px; }.toolbar-head { flex-wrap: wrap; gap: 10px; }.toolbar-title { font-size: 16px; color: #172b4d; font-weight: 700; }.toolbar-desc, .updated-at { color: #8894a8; font-size: 12px; }.workbench-card-actions { flex-wrap: wrap; }
.workbench-card-actions :deep(.el-button + .el-button), .host-tile-actions :deep(.el-button + .el-button) { margin-left: 0; }.filter-refresh-btn { color: #245bdb; border-color: #d6e3fb; background: #f4f8ff; }
.workbench-toolbar { margin: 0 0 12px; padding: 10px 12px; min-height: 52px; border: 1px solid #e1e7ef; border-radius: 12px; background: #f8fafd; }.docker-resource-toolbar { overflow-x: auto; flex-wrap: nowrap; }.docker-resource-toolbar > * { flex-shrink: 0; }.toolbar-spacer { flex: 1; }.search-input { width: 280px; }.host-select { width: 240px; }.state-select { width: 130px; }.refresh-select { width: 128px; }
.docker-host-layout { display: grid; flex: 1; grid-template-columns: minmax(0, 1fr) 390px; gap: 16px; align-items: stretch; }.docker-host-selector { min-width: 0; min-height: 230px; }.docker-host-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.docker-host-tile { display: flex; flex-direction: column; min-width: 0; min-height: 220px; padding: 14px; border: 1px solid #dfe6ef; border-radius: 14px; background: #fff; transition: border-color .16s, background .16s; }.docker-host-tile.selected { border-color: #8db0f1; background: linear-gradient(140deg, #f2f7ff, #fff 75%); box-shadow: 0 0 0 1px #dce8ff; }
.host-tile-heading { justify-content: space-between; margin-bottom: 13px; }.provider-mark { padding: 4px 8px; border-radius: 7px; background: #eff5ff; color: #3673ce; font-size: 11px; font-weight: 700; }.host-name { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 15px; color: #233652; }.host-address { margin-top: 5px; color: #8190a5; font-size: 12px; }
.host-meta { margin: 12px 0; display: grid; gap: 7px; font-size: 12px; }.host-meta > div, .overview-meta > div { display: grid; grid-template-columns: 60px minmax(0, 1fr); gap: 8px; }dt { color: #8190a5; }dd { margin: 0; color: #475569; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.host-tile-footer { margin-top: auto; justify-content: space-between; flex-wrap: wrap; padding-top: 10px; border-top: 1px solid #edf0f5; gap: 6px; }.host-tile-actions { gap: 5px; }
.docker-overview { padding: 18px; border: 1px solid #dce5f2; border-radius: 16px; background: linear-gradient(150deg, #f7faff, #fff 55%); min-height: 390px; }.overview-heading { justify-content: space-between; align-items: flex-start; margin-bottom: 18px; }.overview-heading > div { display: flex; flex-direction: column; gap: 6px; min-width: 0; }.overview-heading span { font-size: 13px; color: #728198; }.overview-heading strong { font-size: 19px; overflow-wrap: anywhere; color: #203652; }
.overview-meta { display: grid; gap: 11px; margin: 0; font-size: 13px; }.overview-meta > div { grid-template-columns: 86px minmax(0, 1fr); }.overview-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 18px 0; }.overview-stats button { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; padding: 12px 10px; border: 1px solid #e1e8f2; border-radius: 10px; background: #f8fafd; cursor: pointer; color: #203652; }.overview-stats button:disabled { cursor: default; opacity: 1; }.overview-stats button:not(:disabled):hover { border-color: #9cb9ed; background: #eef5ff; }.overview-stats span { font-size: 12px; color: #728198; }.overview-stats strong { font-size: 21px; font-weight: 700; }.overview-stats .success strong { color: #16a076; }.overview-connection { padding-top: 12px; border-top: 1px solid #e5ebf4; }
.inline-error { padding: 9px 12px; margin-bottom: 10px; border-radius: 8px; background: #fff3f3; color: #be3843; font-size: 13px; overflow-wrap: anywhere; }.resource-status { min-height: 28px; margin-bottom: 8px; color: #64748b; font-size: 12px; }.operation-progress { margin-left: auto; color: #245bdb; }
.resource-name { display: flex; align-items: center; gap: 8px; min-width: 0; }.resource-name :deep(.el-button), .image-repository { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }.resource-subtext { display: block; font: 11px/19px 'Cascadia Code', Consolas, monospace; color: #8c99ac; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.state-dot { width: 7px; height: 7px; border-radius: 50%; background: #a5afbc; flex-shrink: 0; }.state-dot.running { background: #18af83; }.state-dot.restarting { background: #e5a135; }.state-dot.dead { background: #e3636d; }
.docker-table :deep(th.el-table__cell) { background: #f6f8fc; color: #68778e; font-size: 12px; font-weight: 600; }.docker-table :deep(td.el-table__cell) { padding: 9px 0; font-size: 12px; }.row-actions { justify-content: flex-end; gap: 7px; }.row-actions :deep(.el-button + .el-button) { margin-left: 0; }.table-footer { justify-content: space-between; flex-wrap: wrap; margin-top: 12px; font-size: 12px; color: #8190a5; }
:global(.docker-inspect-dialog .el-dialog__body) { overflow: hidden; max-height: none; }.inspect-workspace { display: flex; flex-direction: column; gap: 10px; height: calc(82dvh - 80px); min-height: 300px; }.inspect-workspace.fullscreen { height: calc(100dvh - 100px); }.inspect-toolbar { color: #718096; font-size: 12px; }.inspect-scroll { flex: 1; min-height: 0; overflow: auto; }.inspect-scroll :deep(.el-descriptions__content) { overflow-wrap: anywhere; }.inspect-json { padding: 16px; border-radius: 10px; margin: 12px 0 0; color: #dbe5f5; background: #0b1220; font: 12px/21px 'Cascadia Code', Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 1550px) { .docker-host-layout { grid-template-columns: minmax(0, 1fr) 350px; }.docker-host-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 1100px) { .docker-host-layout { grid-template-columns: minmax(0, 1fr); }.docker-host-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }.docker-overview { min-height: 0; }.overview-stats { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
@media (max-width: 800px) { .docker-host-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.overview-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }.updated-at, .toolbar-desc { display: none; }.search-input { width: 240px; } }
@media (max-width: 550px) { .docker-host-grid { grid-template-columns: minmax(0, 1fr); }.docker-main-tabs .neo-tab-btn { padding: 0 10px; flex: 1; }.docker-content-card { padding: 12px; }.inline-subtitle { display: none; }.workbench-toolbar { overflow-x: auto; }.workbench-toolbar > * { flex-shrink: 0; } }
</style>
