<template>
  <div class="cmdb-items-layout">
    <div class="cmdb-resource-tree-panel">
      <div class="panel-header">
        <span class="panel-title" @click="clearTreeFilter">
          <el-icon><Connection /></el-icon>
          主机资源树
        </span>
      </div>
      <el-tree
        ref="treeRef"
        :data="resourceTree"
        :props="{ label: 'name', children: 'children' }"
        node-key="id"
        highlight-current
        default-expand-all
        :expand-on-click-node="false"
        class="resource-tree"
        @node-click="onNodeClick"
      >
        <template #default="{ node, data }">
          <div class="custom-tree-node">
            <span>
              <el-icon v-if="data.node_type === 'biz'" class="tree-icon biz"><Files /></el-icon>
              <el-icon v-else class="tree-icon env"><Monitor /></el-icon>
              {{ node.label }}
            </span>
          </div>
        </template>
      </el-tree>
    </div>

    <div class="cmdb-items-main">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="search"
            placeholder="搜索主机名 / IP / 负责人"
            clearable
            style="width: 240px"
            @input="fetchHosts"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 120px" @change="fetchHosts">
            <el-option label="在线" value="online" />
            <el-option label="离线" value="offline" />
            <el-option label="告警" value="warning" />
          </el-select>
          <el-tag v-if="filterBusiness" type="info" effect="plain">业务线：{{ filterBusiness }}</el-tag>
          <el-tag v-if="filterEnv" type="success" effect="plain">环境：{{ filterEnv }}</el-tag>
        </div>
        <el-button v-if="canManageHosts" type="primary" size="small" @click="openDialog()">
          <el-icon><Plus /></el-icon>
          新增主机
        </el-button>
      </div>

      <el-table :data="hosts" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="hostname" label="主机名" min-width="150" />
        <el-table-column prop="ip_address" label="IP 地址" width="140" />
        <el-table-column prop="business_line" label="业务线" width="120" show-overflow-tooltip />
        <el-table-column prop="environment_display" label="环境" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="tagTypeByEnv(row.environment)">{{ row.environment_display || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="admin_user" label="负责人" width="110" />
        <el-table-column prop="os_type" label="操作系统" width="120" show-overflow-tooltip />
        <el-table-column prop="status_display" label="状态" width="90">
          <template #default="{ row }">
            <span><span class="status-dot" :class="row.status"></span>{{ row.status_display }}</span>
          </template>
        </el-table-column>
        <el-table-column label="CPU" width="95">
          <template #default="{ row }">
            <el-progress :percentage="row.cpu_usage" :stroke-width="6" :color="progressColor(row.cpu_usage)" :show-text="false" />
            <span class="metric-text">{{ row.cpu_usage }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="内存" width="95">
          <template #default="{ row }">
            <el-progress :percentage="row.memory_usage" :stroke-width="6" :color="progressColor(row.memory_usage)" :show-text="false" />
            <span class="metric-text">{{ row.memory_usage }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="磁盘" width="95">
          <template #default="{ row }">
            <el-progress :percentage="row.disk_usage" :stroke-width="6" :color="progressColor(row.disk_usage)" :show-text="false" />
            <span class="metric-text">{{ row.disk_usage }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="SSH" width="140">
          <template #default="{ row }">
            <span class="metric-text">{{ row.ssh_user }}@{{ row.ssh_port }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column v-if="canManageHosts || canUseTerminal" label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canManageHosts" link type="success" size="small" :loading="row._testing" @click="handleTestConnection(row)">测试</el-button>
            <el-button v-if="canManageHosts" link type="warning" size="small" :loading="row._refreshing" @click="handleRefreshInfo(row)">刷新</el-button>
            <el-button v-if="canUseTerminal" link type="primary" size="small" @click="openTerminal(row)">终端</el-button>
            <el-button v-if="canManageHosts" link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm v-if="canManageHosts" title="确定删除该主机？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog" v-model="dialogVisible" :title="editingId ? '编辑主机' : '新增主机'" width="90%" style="max-width: 620px" top="5vh" append-to-body destroy-on-close>
    <el-form class="workbench-editor-form--sectioned" label-position="top" :model="form" label-width="90px">
      <section class="workbench-editor-section">
        <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>主机信息</h3></div>
        <div>
          <el-form-item label="主机名"><el-input v-model="form.hostname" placeholder="例如 web-server-01" /></el-form-item>
          <div class="form-row">
            <el-form-item label="业务线" class="form-col">
              <el-select v-model="form.business_line" placeholder="选择业务线" clearable filterable style="width: 100%" @change="onBusinessChange">
                <el-option v-for="node in bizNodes" :key="node.id" :label="node.name" :value="node.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="环境" class="form-col">
              <el-select v-model="form.environment" placeholder="选择环境" :disabled="!form.business_line" style="width: 100%">
                <el-option v-for="env in currentEnvOptions" :key="env.id" :label="env.name" :value="env.name" />
              </el-select>
            </el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="IP 地址" class="form-col"><el-input v-model="form.ip_address" placeholder="例如 192.168.1.10" /></el-form-item>
            <el-form-item label="负责人" class="form-col"><el-input v-model="form.admin_user" placeholder="例如 张三" /></el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="操作系统" class="form-col"><el-input v-model="form.os_type" placeholder="例如 Ubuntu 22.04" /></el-form-item>
            <el-form-item label="状态" class="form-col">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="在线" value="online" />
                <el-option label="离线" value="offline" />
                <el-option label="告警" value="warning" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item class="workbench-editor-full" label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        </div>
      </section>

      <section class="workbench-editor-section workbench-editor-section--tinted">
        <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>SSH 连接</h3></div>
        <div>
          <div class="form-row">
            <el-form-item label="SSH 用户" class="form-col"><el-input v-model="form.ssh_user" placeholder="root" /></el-form-item>
            <el-form-item label="SSH 端口" class="form-col">
              <el-input-number v-model="form.ssh_port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
            </el-form-item>
          </div>
          <el-form-item label="SSH 密码">
            <el-input
          v-model="form.ssh_password"
          type="password"
          show-password
          :placeholder="editingId ? '留空则不更新' : '请输入 SSH 密码'"
        />
          </el-form-item>
        </div>
      </section>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Connection, Files, Monitor, Plus, Search } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { createHost, deleteHost, getHosts, refreshHostInfo, testHostConnection, updateHost } from '@/api/modules/ops'

const props = defineProps({
  resourceTree: {
    type: Array,
    default: () => [],
  },
})

const router = useRouter()
const authStore = useAuthStore()
const treeRef = ref(null)
const hosts = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const search = ref('')
const statusFilter = ref('')
const filterBusiness = ref('')
const filterEnv = ref('')

const defaultForm = () => ({
  hostname: '',
  ip_address: '',
  business_line: '',
  environment: '',
  admin_user: '',
  os_type: 'Linux',
  description: '',
  status: 'online',
  ssh_port: 22,
  ssh_user: 'root',
  ssh_password: '',
})

const form = ref(defaultForm())

const canManageHosts = computed(() => authStore.hasPermission('ops.host.manage'))
const canUseTerminal = computed(() => authStore.hasPermission('ops.host.terminal'))
const bizNodes = computed(() => props.resourceTree.filter(item => item.node_type === 'biz'))
const currentEnvOptions = computed(() => {
  const bizNode = bizNodes.value.find(item => item.name === form.value.business_line)
  return bizNode?.children || []
})

function progressColor(val) {
  if (val >= 90) return '#ef4444'
  if (val >= 70) return '#f59e0b'
  return '#10b981'
}

function tagTypeByEnv(env) {
  return env === 'prod' ? 'danger' : env === 'test' ? 'warning' : 'info'
}

async function fetchHosts() {
  loading.value = true
  try {
    const params = {}
    if (search.value) params.search = search.value
    if (statusFilter.value) params.status = statusFilter.value
    if (filterBusiness.value) params.business_line = filterBusiness.value
    if (filterEnv.value) params.environment = filterEnv.value
    const res = await getHosts(params)
    hosts.value = (res.results || res).map(item => ({ ...item, _testing: false, _refreshing: false }))
  } catch (error) {
    ElMessage.error('加载主机失败')
  } finally {
    loading.value = false
  }
}

function clearTreeFilter() {
  filterBusiness.value = ''
  filterEnv.value = ''
  treeRef.value?.setCurrentKey(null)
  fetchHosts()
}

function onNodeClick(data) {
  if (data.node_type === 'biz') {
    filterBusiness.value = data.name
    filterEnv.value = ''
  } else {
    const parentBiz = bizNodes.value.find(item => (item.children || []).some(env => env.id === data.id))
    filterBusiness.value = parentBiz?.name || ''
    filterEnv.value = data.name
  }
  fetchHosts()
}

function onBusinessChange() {
  form.value.environment = ''
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.value = {
      hostname: row.hostname,
      ip_address: row.ip_address,
      business_line: row.business_line || '',
      environment: row.environment || '',
      admin_user: row.admin_user || '',
      os_type: row.os_type || 'Linux',
      description: row.description || '',
      status: row.status || 'online',
      ssh_port: row.ssh_port || 22,
      ssh_user: row.ssh_user || 'root',
      ssh_password: '',
    }
  } else {
    editingId.value = null
    form.value = defaultForm()
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.value.hostname) return ElMessage.warning('请填写主机名')
  if (!form.value.ip_address) return ElMessage.warning('请填写 IP 地址')
  if (!form.value.business_line) return ElMessage.warning('请选择业务线')
  if (!form.value.environment) return ElMessage.warning('请选择环境')
  saving.value = true
  try {
    const payload = { ...form.value }
    if (editingId.value) {
      await updateHost(editingId.value, payload)
      ElMessage.success('主机已更新')
    } else {
      await createHost(payload)
      ElMessage.success('主机已创建')
    }
    dialogVisible.value = false
    fetchHosts()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteHost(id)
    ElMessage.success('主机已删除')
    fetchHosts()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

async function handleTestConnection(row) {
  row._testing = true
  try {
    const res = await testHostConnection(row.id)
    ElMessage[res.success ? 'success' : 'error'](res.message)
  } catch (error) {
    ElMessage.error('测试连接失败')
  } finally {
    row._testing = false
  }
}

async function handleRefreshInfo(row) {
  row._refreshing = true
  try {
    const res = await refreshHostInfo(row.id)
    Object.assign(row, res, { _testing: false, _refreshing: false })
    ElMessage.success('主机信息已刷新')
  } catch (error) {
    ElMessage.error('刷新主机信息失败')
  } finally {
    row._refreshing = false
  }
}

function openTerminal(row) {
  router.push({ name: 'WebShell', params: { hostId: row.id } })
}

onMounted(fetchHosts)
</script>

<style scoped>
.cmdb-items-layout { display: flex; gap: 16px; }
.cmdb-resource-tree-panel {
  width: 188px;
  flex: 0 0 188px;
  border-right: 1px solid rgba(139, 92, 246, 0.15);
  padding-right: 12px;
  display: flex;
  flex-direction: column;
}
.cmdb-items-main { flex: 1; min-width: 0; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-title { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; cursor: pointer; }
.resource-tree { flex: 1; overflow-y: auto; background: transparent; }
.custom-tree-node { display: flex; align-items: center; font-size: 13px; }
.tree-icon { margin-right: 4px; }
.tree-icon.biz { color: #8b5cf6; }
.tree-icon.env { color: #10b981; }
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.metric-text { font-size: 12px; color: var(--text-secondary); }
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
.status-dot.online { background: #10b981; }
.status-dot.offline { background: #ef4444; }
.status-dot.warning { background: #f59e0b; }
.form-row { display: flex; gap: 12px; }
.form-col { flex: 1; }

@media (max-width: 900px) {
  .cmdb-items-layout { flex-direction: column; }
  .cmdb-resource-tree-panel {
    width: 100%;
    flex-basis: auto;
    border-right: none;
    border-bottom: 1px solid rgba(139, 92, 246, 0.15);
    padding-right: 0;
    padding-bottom: 12px;
  }
  .form-row { flex-direction: column; gap: 0; }
}
</style>
