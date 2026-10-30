<template>
  <div class="transaction-ticket-page fade-in workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-title-row release-hero-title-inline">
        <span class="ticket-header-icon"><el-icon><Tickets /></el-icon></span>
        <h2>事务工单</h2>
        <p class="ticket-hero-desc">覆盖变更执行、巡检维护、权限开通、故障处置与漏洞处理，统一走审批流并沉淀处理窗口。</p>
      </div>
    </section>

    <div class="audit-grid">
      <button type="button" class="audit-card audit-card--inline audit-card--action" :class="{ 'is-active': activeSummaryKey === 'all' }" @click="applySummaryFilter('all')">
        <div class="stat-value">{{ summary.total }}</div>
        <div class="stat-label">工单总数</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--warning audit-card--action" :class="{ 'is-active': activeSummaryKey === 'pending' }" @click="applySummaryFilter('pending')">
        <div class="stat-value">{{ summary.pending }}</div>
        <div class="stat-label">待审批</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--success audit-card--action" :class="{ 'is-active': activeSummaryKey === 'processing' }" @click="applySummaryFilter('processing')">
        <div class="stat-value">{{ summary.processing }}</div>
        <div class="stat-label">处理中</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--danger audit-card--action" :class="{ 'is-active': activeSummaryKey === 'urgent' }" @click="applySummaryFilter('urgent')">
        <div class="stat-value">{{ summary.urgent }}</div>
        <div class="stat-label">高优先级</div>
      </button>
    </div>

    <div class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">事务工单列表</span>
          <span class="toolbar-desc">延续任务工作台的筛选密度和操作节奏，统一处理审批、执行与回看。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canCreate" type="primary" @click="openCreateDialog">
            <el-icon><Plus /></el-icon>
            新建事务工单
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history ticket-filter-bar">
        <div class="workbench-toolbar-left">
          <el-select v-model="typeFilter" clearable placeholder="工单类型" style="width: 128px">
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="statusFilter" clearable placeholder="状态" style="width: 118px">
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="priorityFilter" clearable placeholder="优先级" style="width: 118px">
            <el-option v-for="item in priorityOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="bizFilter" clearable filterable placeholder="系统" style="width: 128px" @change="handleBizFilterChange">
            <el-option v-for="item in businessLineOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="envFilter" clearable placeholder="环境" style="width: 118px">
            <el-option v-for="item in envFilterOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-input v-model="search" clearable placeholder="搜索标题 / 申请人 / 处理人" style="width: 280px" />
        </div>
        <div class="workbench-toolbar-right">
          <el-button class="filter-refresh-btn" :loading="loading" @click="loadTickets">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="filteredTickets" stripe style="width: 100%">
        <el-table-column label="工单标题" min-width="240">
          <template #default="{ row }">
            <div class="stack-cell">
              <span class="ticket-title">{{ row.title }}</span>
              <div class="sub-text">{{ row.description || '暂无补充说明' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="light" :type="typeTagType(row.ticket_type)">{{ typeLabel(row.ticket_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="系统 / 环境" min-width="160">
          <template #default="{ row }">
            <div class="stack-cell">
              <span>{{ row.business_line || '-' }}</span>
              <div class="sub-text">{{ row.environment_display || environmentLabel(row.environment) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="审批流" min-width="180">
          <template #default="{ row }">
            <div class="stack-cell">
              <span>{{ row.approval_flow_name || '默认审批' }}</span>
              <div class="sub-text">{{ row.window || '按需执行' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="priorityTagType(row.priority)">{{ priorityLabel(row.priority) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="applicant" label="申请人" width="120" />
        <el-table-column prop="owner" label="处理人" width="120" />
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending' && canApprove"
              link
              type="success"
              size="small"
              @click="approveTicket(row)"
            >
              通过
            </el-button>
            <el-button
              v-if="row.status === 'pending' && canApprove"
              link
              type="danger"
              size="small"
              @click="rejectTicket(row)"
            >
              驳回
            </el-button>
            <el-button
              v-if="row.status === 'approved' && canManage"
              link
              type="primary"
              size="small"
              @click="startTicket(row)"
            >
              开始处理
            </el-button>
            <el-button
              v-if="row.status === 'processing' && canManage"
              link
              type="success"
              size="small"
              @click="completeTicket(row)"
            >
              完成
            </el-button>
            <el-button link type="info" size="small" @click="viewTicket(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="createVisible" title="新建事务工单" width="760px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="ticketForm" label-width="96px" class="workbench-editor-form--sectioned ticket-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>工单信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="工单标题" class="span-2" required><el-input v-model="ticketForm.title" /></el-form-item>
            <el-form-item label="事务类型" required>
              <el-select v-model="ticketForm.ticket_type" style="width: 100%">
                <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="优先级" required>
              <el-select v-model="ticketForm.priority" style="width: 100%">
                <el-option v-for="item in priorityOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>执行范围与审批</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="系统" required>
              <el-select v-model="ticketForm.business_line" filterable style="width: 100%" @change="handleBusinessLineChange">
                <el-option v-for="item in businessLineOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="环境" required>
              <el-select v-model="ticketForm.environment" style="width: 100%">
                <el-option v-for="item in formEnvironmentOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="处理人"><el-input v-model="ticketForm.owner" placeholder="如：值班运维 / 平台组" /></el-form-item>
            <el-form-item label="执行窗口"><el-input v-model="ticketForm.window" placeholder="如：今晚 22:00-23:00" /></el-form-item>
            <el-form-item label="审批流" class="span-2">
              <el-select v-model="ticketForm.approval_flow" clearable filterable style="width: 100%" placeholder="选择审批流">
                <el-option
              v-for="item in transactionFlows"
              :key="item.id"
              :label="`${item.name} · ${item.environment_display || '全部环境'}`"
              :value="item.id"
            />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">03</span><h3>补充说明</h3></div>
          <div>
            <el-form-item label="说明" class="workbench-editor-full span-2"><el-input v-model="ticketForm.description" type="textarea" :rows="4" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="createTicket">提交工单</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="事务工单详情" width="760px" append-to-body destroy-on-close>
      <el-descriptions v-if="activeTicket" :column="2" border size="small">
        <el-descriptions-item label="工单标题" :span="2">{{ activeTicket.title }}</el-descriptions-item>
        <el-descriptions-item label="事务类型">{{ typeLabel(activeTicket.ticket_type) }}</el-descriptions-item>
        <el-descriptions-item label="优先级">{{ priorityLabel(activeTicket.priority) }}</el-descriptions-item>
        <el-descriptions-item label="系统">{{ activeTicket.business_line || '-' }}</el-descriptions-item>
        <el-descriptions-item label="环境">{{ activeTicket.environment_display || environmentLabel(activeTicket.environment) }}</el-descriptions-item>
        <el-descriptions-item label="审批流">{{ activeTicket.approval_flow_name || '默认审批' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ statusLabel(activeTicket.status) }}</el-descriptions-item>
        <el-descriptions-item label="申请人">{{ activeTicket.applicant || '-' }}</el-descriptions-item>
        <el-descriptions-item label="处理人">{{ activeTicket.owner || '-' }}</el-descriptions-item>
        <el-descriptions-item label="执行窗口">{{ activeTicket.window || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(activeTicket.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatTime(activeTicket.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="说明" :span="2">{{ activeTicket.description || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, RefreshRight, Tickets } from '@element-plus/icons-vue'
import {
  approveTransactionTicket,
  completeTransactionTicket,
  createTransactionTicket,
  getDeploymentApprovalFlows,
  getTransactionTickets,
  rejectTransactionTicket,
  startProcessTransactionTicket,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import { enrichWorkOrderFlows } from '@/utils/workorderFlows'

const authStore = useAuthStore()

const tickets = ref([])
const flows = ref([])
const resourceTree = ref([])
const loading = ref(false)
const submitting = ref(false)
const createVisible = ref(false)
const detailVisible = ref(false)
const activeTicket = ref(null)

const search = ref('')
const typeFilter = ref('')
const statusFilter = ref('')
const priorityFilter = ref('')
const bizFilter = ref('')
const envFilter = ref('')
const activeSummaryKey = ref('all')

const typeOptions = [
  { label: '变更执行', value: 'change' },
  { label: '巡检任务', value: 'inspection' },
  { label: '权限开通', value: 'access' },
  { label: '故障处理', value: 'incident' },
  { label: '漏洞处理', value: 'vulnerability' },
]
const priorityOptions = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
]
const statusOptions = [
  { label: '待审批', value: 'pending' },
  { label: '已通过', value: 'approved' },
  { label: '处理中', value: 'processing' },
  { label: '已完成', value: 'done' },
  { label: '已驳回', value: 'rejected' },
]

const ticketForm = ref({})

const canCreate = computed(() => authStore.hasPermission('ops.ticket.manage'))
const canManage = computed(() => authStore.hasPermission('ops.ticket.manage'))
const canApprove = computed(() => authStore.hasPermission('ops.ticket.approve'))

const businessLineOptions = computed(() => (resourceTree.value || [])
  .filter(item => item.node_type === 'biz')
  .map(item => ({ label: item.name, value: item.name })))

const envFilterOptions = computed(() => {
  if (!bizFilter.value) return defaultEnvironmentOptions()
  const bizNode = (resourceTree.value || []).find(item => item.node_type === 'biz' && item.name === bizFilter.value)
  const options = (bizNode?.children || []).map(item => ({ label: environmentLabel(item.name), value: item.name }))
  return options.length ? options : defaultEnvironmentOptions()
})

const formEnvironmentOptions = computed(() => {
  if (!ticketForm.value.business_line) return defaultEnvironmentOptions()
  const bizNode = (resourceTree.value || []).find(item => item.node_type === 'biz' && item.name === ticketForm.value.business_line)
  const options = (bizNode?.children || []).map(item => ({ label: environmentLabel(item.name), value: item.name }))
  return options.length ? options : defaultEnvironmentOptions()
})

const transactionFlows = computed(() => {
  const matched = flows.value.filter(item => (item.ticket_types || []).includes('transaction'))
  return matched.length ? matched : flows.value.filter(item => item.is_active)
})

const filteredTickets = computed(() => tickets.value.filter((item) => {
  if (activeSummaryKey.value === 'pending' && item.status !== 'pending') return false
  if (activeSummaryKey.value === 'processing' && item.status !== 'processing') return false
  if (activeSummaryKey.value === 'urgent' && item.priority !== 'high') return false
  if (typeFilter.value && item.ticket_type !== typeFilter.value) return false
  if (statusFilter.value && item.status !== statusFilter.value) return false
  if (priorityFilter.value && item.priority !== priorityFilter.value) return false
  if (bizFilter.value && item.business_line !== bizFilter.value) return false
  if (envFilter.value && item.environment !== envFilter.value) return false
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return true
  return [item.title, item.applicant, item.owner, item.description].some(value => String(value || '').toLowerCase().includes(keyword))
}))

const summary = computed(() => ({
  total: tickets.value.length,
  pending: tickets.value.filter(item => item.status === 'pending').length,
  processing: tickets.value.filter(item => item.status === 'processing').length,
  urgent: tickets.value.filter(item => item.priority === 'high').length,
}))

function applySummaryFilter(key) {
  activeSummaryKey.value = key
  statusFilter.value = ''
  priorityFilter.value = ''
}

function resetTicketForm() {
  ticketForm.value = {
    title: '',
    ticket_type: 'change',
    priority: 'medium',
    business_line: '',
    environment: '',
    approval_flow: null,
    owner: '',
    window: '',
    description: '',
  }
}

async function loadTickets() {
  loading.value = true
  try {
    const response = await getTransactionTickets()
    tickets.value = Array.isArray(response?.results) ? response.results : (response || [])
  } catch (error) {
    tickets.value = []
    ElMessage.error(resolveErrorMessage(error, '事务工单加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadFlows() {
  try {
    const response = await getDeploymentApprovalFlows()
    const list = enrichWorkOrderFlows(response?.results || response || [])
    flows.value = list.length ? list : []
  } catch {
    flows.value = []
  }
}

async function loadResourceTree() {
  resourceTree.value = []
}

function defaultEnvironmentOptions() {
  return ['prod', 'test', 'dev'].map(value => ({ label: environmentLabel(value), value }))
}

function environmentLabel(value) {
  return ({ prod: '生产', test: '测试', dev: '开发' }[value] || value || '-')
}

function typeLabel(value) {
  return typeOptions.find(item => item.value === value)?.label || value
}

function priorityLabel(value) {
  return priorityOptions.find(item => item.value === value)?.label || value
}

function statusLabel(value) {
  return statusOptions.find(item => item.value === value)?.label || value
}

function typeTagType(value) {
  return ({ change: 'warning', inspection: 'info', access: 'success', incident: 'danger', vulnerability: 'danger' }[value] || 'info')
}

function priorityTagType(value) {
  return ({ high: 'danger', medium: 'warning', low: 'info' }[value] || 'info')
}

function statusTagType(value) {
  return ({ pending: 'warning', approved: 'success', processing: 'info', done: 'success', rejected: 'danger' }[value] || 'info')
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function handleBusinessLineChange(value) {
  const bizNode = (resourceTree.value || []).find(item => item.node_type === 'biz' && item.name === value)
  const envs = (bizNode?.children || []).map(item => item.name)
  if (!envs.length) return
  if (!envs.includes(ticketForm.value.environment)) {
    ticketForm.value.environment = envs[0] || ''
  }
}

function handleBizFilterChange(value) {
  if (!value) return
  const envs = envFilterOptions.value.map(item => item.value)
  if (!envs.includes(envFilter.value)) {
    envFilter.value = ''
  }
}

function openCreateDialog() {
  resetTicketForm()
  createVisible.value = true
}

async function createTicket() {
  if (!ticketForm.value.title) return ElMessage.warning('请填写工单标题')
  if (!ticketForm.value.business_line) return ElMessage.warning('请选择系统')
  if (!ticketForm.value.environment) return ElMessage.warning('请选择环境')

  submitting.value = true
  try {
    await createTransactionTicket(ticketForm.value)
    createVisible.value = false
    ElMessage.success('事务工单已提交')
    await loadTickets()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '事务工单提交失败'))
  } finally {
    submitting.value = false
  }
}

async function approveTicket(row) {
  try {
    await approveTransactionTicket(row.id)
    ElMessage.success('工单已审批通过')
    await loadTickets()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '审批失败'))
  }
}

async function rejectTicket(row) {
  try {
    await rejectTransactionTicket(row.id)
    ElMessage.success('工单已驳回')
    await loadTickets()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '驳回失败'))
  }
}

async function startTicket(row) {
  try {
    await startProcessTransactionTicket(row.id)
    ElMessage.success('工单已进入处理中')
    await loadTickets()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '开始处理失败'))
  }
}

async function completeTicket(row) {
  try {
    await completeTransactionTicket(row.id)
    ElMessage.success('工单已完成')
    await loadTickets()
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, '完成失败'))
  }
}

function viewTicket(row) {
  activeTicket.value = row
  detailVisible.value = true
}

function resolveErrorMessage(error, fallback) {
  const data = error?.response?.data
  if (!data) return fallback
  if (typeof data.detail === 'string' && data.detail) return data.detail
  const first = Object.values(data)[0]
  if (Array.isArray(first) && first[0]) return String(first[0])
  if (typeof first === 'string') return first
  return fallback
}

onMounted(async () => {
  resetTicketForm()
  await Promise.all([loadTickets(), loadFlows(), loadResourceTree()])
})
</script>

<style scoped>
.transaction-ticket-page{display:flex;flex-direction:column;gap:6px}
.panel{background:linear-gradient(180deg,rgba(255,255,255,.98) 0%,rgba(250,252,255,.96) 100%);border:1px solid rgba(15,23,42,.08);border-radius:18px;box-shadow:0 8px 24px rgba(15,23,42,.04);padding:14px 16px}
.hero{background:linear-gradient(135deg,#fbfdff 0%,#f7faff 52%,#f9fbfd 100%);display:flex;gap:12px;justify-content:space-between;align-items:center;border-color:rgba(36,91,219,.09)}
.release-hero-title-row{display:flex;align-items:center;gap:12px}
.release-hero-title-inline{flex-wrap:wrap}
.hero h2{margin:0;color:#0f172a;font-size:23px}
.ticket-hero-desc{margin:0;color:#64748b;font-size:13px;line-height:1.45}
.ticket-header-icon{width:42px;height:42px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;font-size:20px;color:#245bdb;background:linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%);border:1px solid rgba(36,91,219,.12);box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.audit-grid{gap:10px}
.audit-card{border-radius:14px;border:1px solid rgba(15,23,42,.08);background:linear-gradient(180deg,rgba(255,255,255,.98) 0%,rgba(252,253,255,.94) 100%);box-shadow:0 4px 14px rgba(15,23,42,.03)}
.audit-card--inline{min-height:68px;padding:14px 16px}
.audit-card .stat-label{font-size:13px;font-weight:600;color:#334155}
.audit-card .stat-value{font-size:24px;color:#1f2329}
.audit-card--warning{background:linear-gradient(180deg,#fffdfa 0%,#ffffff 100%)}
.audit-card--success{background:linear-gradient(180deg,#fbfffd 0%,#ffffff 100%)}
.audit-card--danger{background:linear-gradient(180deg,#fffafb 0%,#ffffff 100%)}
.audit-card--action:hover{border-color:rgba(36,91,219,.16);box-shadow:0 10px 20px rgba(36,91,219,.06)}
.audit-card--action.is-active{border-color:rgba(36,91,219,.24);background:linear-gradient(180deg,#f4f7ff 0%,#ffffff 100%);box-shadow:0 0 0 1px rgba(36,91,219,.05),0 12px 22px rgba(36,91,219,.08)}
.ticket-filter-bar{align-items:flex-start}
.stack-cell{display:flex;flex-direction:column;gap:6px}
.ticket-title{font-weight:600;color:#0f172a}
.sub-text{font-size:13px;color:#64748b;line-height:1.5}
.ticket-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px}
.ticket-form-grid :deep(.span-2){grid-column:span 2}
@media (max-width: 980px){.ticket-form-grid{grid-template-columns:1fr}.ticket-form-grid :deep(.span-2){grid-column:span 1}.hero{flex-direction:column;align-items:flex-start}}
</style>
