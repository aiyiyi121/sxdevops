<template>
  <section v-if="canAll(['aiops.chat.analyze', 'ops.alert.view'])" class="verification-panel">
    <div class="verification-toolbar">
      <strong>处置效果验证</strong>
      <el-tag v-if="verification" size="small" effect="plain" :type="statusTone">{{ verification.status_label }}</el-tag>
      <el-tag v-if="verification?.is_demo" size="small" type="info" effect="plain">演示数据</el-tag>
      <el-button size="small" text :loading="loading" @click="load">{{ expanded ? '刷新' : '查看 / 配置' }}</el-button>
    </div>
    <template v-if="expanded">
      <p v-if="error" class="verification-error">{{ error }}</p>
      <template v-if="verification">
        <p class="verification-summary">{{ verification.summary }}</p>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="知识环境">{{ verification.baseline?.environment_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="关联任务">{{ verification.task_id ? `#${verification.task_id}` : '等待任务创建' }}</el-descriptions-item>
          <el-descriptions-item label="任务执行">{{ taskStatus(verification.evidence?.task?.status) }}</el-descriptions-item>
          <el-descriptions-item label="成功目标">{{ verification.evidence?.task?.success_count ?? '—' }} / {{ verification.evidence?.task?.target_count ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="目标告警" :span="2">{{ verification.baseline?.alert?.title || '—' }} <span v-if="verification.baseline?.alert?.id">#{{ verification.baseline.alert.id }}</span></el-descriptions-item>
          <el-descriptions-item label="处置前">{{ alertStatus(verification.baseline?.alert?.status) }}</el-descriptions-item>
          <el-descriptions-item label="处置后">{{ alertStatus(verification.evidence?.alert?.status) }}</el-descriptions-item>
          <el-descriptions-item label="观察窗口">任务结束后 {{ verification.observation_seconds }} 秒</el-descriptions-item>
          <el-descriptions-item label="验证时间">{{ verification.finished_at ? new Date(verification.finished_at).toLocaleString('zh-CN', { hour12: false }) : '等待验证' }}</el-descriptions-item>
        </el-descriptions>
        <el-table v-if="verification.nodes?.length" :data="verification.nodes" size="small" stripe>
          <el-table-column label="验证阶段" min-width="125"><template #default="{ row }">{{ nodeLabels[row.node] || row.node }}</template></el-table-column>
          <el-table-column label="节点状态" width="105"><template #default="{ row }"><el-tag size="small" effect="plain" :type="executionStatusTone(row.status)">{{ executionStatusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="耗时" width="85"><template #default="{ row }">{{ row.duration_ms }} ms</template></el-table-column>
        </el-table>
      </template>
      <template v-else-if="canConfigure">
        <p class="verification-summary">执行任务前保存一条活跃告警作为基线；任务完成后检查同一告警的恢复事件。</p>
        <el-form label-position="top" size="small" class="verification-form" @submit.prevent="save">
          <el-form-item label="知识环境">
            <el-select v-model="form.environment_id" placeholder="选择环境">
              <el-option v-for="environment in environments" :key="environment.id" :label="environment.name" :value="environment.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="告警 ID"><el-input-number v-model="form.alert_id" :min="1" :precision="0" controls-position="right" /></el-form-item>
          <el-form-item label="观察窗口（秒）"><el-input-number v-model="form.observation_seconds" :min="0" :max="600" :precision="0" controls-position="right" /></el-form-item>
          <el-button type="primary" size="small" :loading="saving" :disabled="!form.environment_id || !form.alert_id" @click="save">保存验证基线</el-button>
        </el-form>
      </template>
      <p v-else-if="!loading && !error" class="verification-summary">本次动作未配置验证。请在本人任务创建执行前保存告警基线。</p>
    </template>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { configureAIOpsActionVerification, getAIOpsActionVerification } from '@/api/modules/aiops'
import { canAll } from '@/utils/permission'
import { executionStatusLabel, executionStatusTone } from '@/utils/aiopsExecution'

const props = defineProps({ actionId: { type: Number, required: true } })
const expanded = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const verification = ref(null)
const canConfigure = ref(false)
const environments = ref([])
const form = reactive({ environment_id: null, alert_id: null, observation_seconds: 60 })
const statusTone = computed(() => ({ passed: 'success', failed: 'danger', inconclusive: 'warning' })[verification.value?.status] || 'info')
const nodeLabels = { verification_scope: '范围与权限检查', verification_task: '任务执行结果', verification_alert: '恢复事件取证', verification_verdict: '效果判定' }
let requestSequence = 0

function alertStatus(value) {
  return ({ active: '活跃', resolved: '已恢复', closed: '已关闭', muted: '已屏蔽' })[value] || '未取得证据'
}

function taskStatus(value) {
  return ({ success: '执行成功', partial: '部分成功', failed: '执行失败', canceled: '已取消' })[value] || '等待执行结果'
}

function applyData(data) {
  verification.value = data.verification
  canConfigure.value = data.can_configure
  environments.value = data.environments || []
  if (!form.environment_id && environments.value.length === 1) form.environment_id = environments.value[0].id
}

async function load() {
  const sequence = ++requestSequence
  expanded.value = true
  loading.value = true
  error.value = ''
  try {
    const data = await getAIOpsActionVerification(props.actionId)
    if (sequence === requestSequence) applyData(data)
  } catch (failure) {
    if (sequence === requestSequence) error.value = failure?.response?.data?.detail || '验证信息加载失败。'
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  const sequence = ++requestSequence
  try {
    const data = await configureAIOpsActionVerification(props.actionId, { ...form })
    if (sequence === requestSequence) {
      applyData(data)
      ElMessage.success('已保存验证基线，任务完成后自动验证')
    }
  } catch (failure) {
    if (sequence === requestSequence) error.value = failure?.response?.data?.detail || '验证基线保存失败。'
  } finally {
    if (sequence === requestSequence) saving.value = false
  }
}

watch(() => props.actionId, () => {
  requestSequence += 1
  expanded.value = false
  verification.value = null
  error.value = ''
  loading.value = false
  saving.value = false
  form.environment_id = null
  form.alert_id = null
})
</script>

<style scoped>
.verification-panel { display: flex; flex-direction: column; gap: 6px; border: 1px solid #e4eaf3; border-radius: 12px; background: #fbfdff; padding: 12px; }
.verification-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: #334155; }
.verification-toolbar .el-button { margin-left: auto; }
.verification-summary { margin: 0; font-size: 12px; line-height: 1.65; color: #64748b; }
.verification-error { margin: 0; font-size: 12px; color: #dc2626; }
.verification-form { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.verification-form :deep(.el-form-item) { margin-bottom: 0; max-width: 100%; }
.verification-form :deep(.el-select) { width: 190px; }
.verification-form :deep(.el-input-number) { width: 125px; }
</style>
