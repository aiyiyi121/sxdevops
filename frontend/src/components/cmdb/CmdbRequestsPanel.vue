<template>
  <div class="tab-content">
    <div class="request-toolbar">
      <div class="request-toolbar-left">
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 120px" size="small" @change="fetchRequests">
          <el-option label="待审批" value="pending" />
          <el-option label="已批准" value="approved" />
          <el-option label="已拒绝" value="rejected" />
          <el-option label="已完成" value="completed" />
        </el-select>
        <el-input v-model="keyword" placeholder="搜索标题 / 主机名 / IP / 申请人" clearable style="width: 280px" size="small" @input="fetchRequests">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <el-button v-if="canSubmitRequests" type="primary" size="small" @click="openRequestDialog">
        <el-icon><Plus /></el-icon>
        新建主机申请
      </el-button>
    </div>

    <el-table :data="requests" stripe v-loading="loading" style="width: 100%">
      <el-table-column prop="title" label="申请标题" min-width="220" show-overflow-tooltip />
      <el-table-column label="目标主机" min-width="180">
        <template #default="{ row }">
          <div class="host-brief">
            <strong>{{ row.specs?.hostname || '-' }}</strong>
            <span>{{ row.specs?.ip_address || '-' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="specification" label="主机规格" min-width="180" show-overflow-tooltip />
      <el-table-column prop="business_line" label="业务线" width="110" />
      <el-table-column prop="environment_display" label="环境" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="tagTypeByEnv(row.environment)">{{ row.environment_display || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="requester" label="申请人" width="100" />
      <el-table-column prop="approver" label="审批人" width="100" />
      <el-table-column prop="status_display" label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="tagTypeByStatus(row.status)">{{ row.status_display }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="申请时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="190" fixed="right">
        <template #default="{ row }">
          <template v-if="canApproveRequests && row.status === 'pending'">
            <el-button link type="success" size="small" @click="doApprove(row)">批准</el-button>
            <el-button link type="danger" size="small" @click="doReject(row)">拒绝</el-button>
          </template>
          <el-button v-if="canApproveRequests && row.status === 'approved'" link type="primary" size="small" @click="doComplete(row)">转主机资产</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog" v-if="canSubmitRequests" v-model="requestDialogVisible" title="新建主机申请" width="90%" style="max-width: 680px" top="5vh" append-to-body destroy-on-close>
    <el-form label-position="top" :model="requestForm" label-width="96px">
      <el-form-item label="申请标题"><el-input v-model="requestForm.title" placeholder="例如：订单服务生产主机扩容" /></el-form-item>
      <div class="form-row">
        <el-form-item label="申请类型" class="form-col">
          <el-input value="主机" disabled />
        </el-form-item>
        <el-form-item label="规格说明" class="form-col"><el-input v-model="requestForm.specification" placeholder="例如 8C16G / 200G / ecs.g7.2xlarge" /></el-form-item>
      </div>
      <div class="form-row">
        <el-form-item label="业务线" class="form-col">
          <el-select v-model="requestForm.business_line" placeholder="选择业务线" clearable filterable style="width: 100%" @change="onBusinessChange">
            <el-option v-for="node in bizNodes" :key="node.id" :label="node.name" :value="node.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境" class="form-col">
          <el-select v-model="requestForm.environment" placeholder="选择环境" :disabled="!requestForm.business_line" style="width: 100%">
            <el-option v-for="env in currentEnvOptions" :key="env.id" :label="env.name" :value="env.name" />
          </el-select>
        </el-form-item>
      </div>
      <div class="form-row">
        <el-form-item label="主机名" class="form-col"><el-input v-model="requestForm.hostname" placeholder="例如 order-api-ecs-03" /></el-form-item>
        <el-form-item label="IP 地址" class="form-col"><el-input v-model="requestForm.ip_address" placeholder="例如 10.10.1.12" /></el-form-item>
      </div>
      <div class="form-row">
        <el-form-item label="操作系统" class="form-col"><el-input v-model="requestForm.os_type" placeholder="例如 Alibaba Cloud Linux 3" /></el-form-item>
        <el-form-item label="负责人" class="form-col"><el-input v-model="requestForm.admin_user" placeholder="默认取申请人" /></el-form-item>
      </div>
      <div class="form-row">
        <el-form-item label="数量" class="form-col">
          <el-input-number v-model="requestForm.quantity" :min="1" :max="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="优先级" class="form-col">
          <el-select v-model="requestForm.priority" style="width: 100%">
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
          </el-select>
        </el-form-item>
      </div>
      <el-form-item label="申请原因">
        <el-input v-model="requestForm.reason" type="textarea" :rows="4" placeholder="说明用途、上线窗口、业务背景等" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="requestDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveRequest">提交申请</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { approveRequest, completeRequest, createResourceRequest, getResourceRequests, rejectRequest } from '@/api/modules/cmdb'

const props = defineProps({
  resourceTree: {
    type: Array,
    default: () => [],
  },
})

const authStore = useAuthStore()
const requests = ref([])
const loading = ref(false)
const saving = ref(false)
const statusFilter = ref('')
const keyword = ref('')
const requestDialogVisible = ref(false)
const requestForm = ref({})

const canSubmitRequests = computed(() => authStore.hasPermission('cmdb.request.submit'))
const canApproveRequests = computed(() => authStore.hasPermission('cmdb.request.approve'))
const bizNodes = computed(() => props.resourceTree.filter(item => item.node_type === 'biz'))
const currentEnvOptions = computed(() => {
  const bizNode = bizNodes.value.find(item => item.name === requestForm.value.business_line)
  return bizNode?.children || []
})

function tagTypeByEnv(env) {
  return env === 'prod' ? 'danger' : env === 'test' ? 'warning' : 'info'
}

function tagTypeByStatus(status) {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'danger'
  if (status === 'completed') return 'info'
  return 'warning'
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : ''
}

function extractErrorMessage(error, fallback) {
  const data = error?.response?.data
  if (typeof data === 'string' && data) return data
  if (data?.detail) return data.detail
  if (data && typeof data === 'object') {
    const firstValue = Object.values(data)[0]
    if (Array.isArray(firstValue) && firstValue.length) return firstValue[0]
    if (typeof firstValue === 'string' && firstValue) return firstValue
  }
  return fallback
}

function resetRequestForm() {
  requestForm.value = {
    title: '',
    specification: '',
    business_line: '',
    environment: '',
    hostname: '',
    ip_address: '',
    os_type: 'Linux',
    admin_user: '',
    quantity: 1,
    priority: 'medium',
    reason: '',
  }
}

async function fetchRequests() {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (keyword.value) params.search = keyword.value
    const res = await getResourceRequests(params)
    requests.value = res.results || res
  } catch (error) {
    ElMessage.error('加载主机申请失败')
  } finally {
    loading.value = false
  }
}

function onBusinessChange() {
  requestForm.value.environment = ''
}

function openRequestDialog() {
  resetRequestForm()
  requestDialogVisible.value = true
}

async function saveRequest() {
  if (!requestForm.value.title) return ElMessage.warning('请填写申请标题')
  if (!requestForm.value.business_line) return ElMessage.warning('请选择业务线')
  if (!requestForm.value.environment) return ElMessage.warning('请选择环境')
  if (!requestForm.value.hostname) return ElMessage.warning('请填写主机名')
  if (!requestForm.value.ip_address) return ElMessage.warning('请填写 IP 地址')
  if (!requestForm.value.reason) return ElMessage.warning('请填写申请原因')

  saving.value = true
  try {
    await createResourceRequest({
      title: requestForm.value.title,
      resource_type: 'host',
      specification: requestForm.value.specification,
      business_line: requestForm.value.business_line,
      environment: requestForm.value.environment,
      quantity: 1,
      priority: requestForm.value.priority,
      reason: requestForm.value.reason,
      specs: {
        hostname: requestForm.value.hostname,
        ip_address: requestForm.value.ip_address,
        os_type: requestForm.value.os_type,
        admin_user: requestForm.value.admin_user,
        specification: requestForm.value.specification,
      },
    })
    ElMessage.success('主机申请已提交')
    requestDialogVisible.value = false
    fetchRequests()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '提交失败'))
  } finally {
    saving.value = false
  }
}

async function promptAndSubmit(title, placeholder, callback) {
  try {
    const { value } = await ElMessageBox.prompt(placeholder, title, {
      inputType: 'textarea',
      inputPlaceholder: placeholder,
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: '',
    })
    await callback(value || '')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(extractErrorMessage(error, '操作失败'))
    }
  }
}

function doApprove(row) {
  promptAndSubmit('批准主机申请', '可填写审批说明（选填）', async (comment) => {
    await approveRequest(row.id, { comment })
    ElMessage.success('主机申请已批准')
    fetchRequests()
  })
}

function doReject(row) {
  promptAndSubmit('拒绝主机申请', '请填写拒绝原因（建议填写）', async (comment) => {
    await rejectRequest(row.id, { comment })
    ElMessage.success('主机申请已拒绝')
    fetchRequests()
  })
}

function doComplete(row) {
  promptAndSubmit('转为主机资产', '可填写交付说明（选填）', async (note) => {
    await completeRequest(row.id, { note })
    ElMessage.success('主机已转入主机资产')
    fetchRequests()
  })
}

onMounted(() => {
  resetRequestForm()
  fetchRequests()
})
</script>

<style scoped>
.request-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.request-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.form-row {
  display: flex;
  gap: 12px;
}
.form-col {
  flex: 1;
}
.host-brief {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.host-brief strong {
  color: var(--text-primary);
  font-weight: 600;
}
.host-brief span {
  color: var(--text-secondary);
  font-size: 12px;
}

@media (max-width: 900px) {
  .form-row {
    flex-direction: column;
    gap: 0;
  }
}
</style>
