<template>
  <el-dialog :model-value="modelValue" title="执行追踪详情" width="min(1120px, 94vw)" append-to-body @update:model-value="emit('update:modelValue', $event)">
    <div v-loading="loading" class="execution-detail">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template v-if="detail">
        <div class="execution-actions">
          <el-tag :type="executionStatusTone(detail.status)" effect="plain">{{ executionStatusLabel(detail.status) }}</el-tag>
          <el-button size="small" @click="navigate('sessions')">关联会话</el-button>
          <el-button size="small" @click="navigate('tools')">工具调用（{{ detail.tool_count }}）</el-button>
          <el-button size="small" @click="navigate('models')">模型调用（{{ detail.model_count }}）</el-button>
          <el-button size="small" :loading="loading" @click="loadDetail">刷新</el-button>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="运行方式" :span="2">{{ detail.orchestration_degraded ? '兼容降级' : 'LangGraph' }}</el-descriptions-item>
          <el-descriptions-item label="会话">{{ detail.session_title }} · {{ detail.username }}</el-descriptions-item>
          <el-descriptions-item label="消息">#{{ detail.message_id }}</el-descriptions-item>
          <el-descriptions-item label="问题" :span="2">{{ detail.question }}</el-descriptions-item>
          <el-descriptions-item label="Thread" :span="2"><span class="execution-thread">{{ detail.thread_id || '-' }}</span></el-descriptions-item>
          <el-descriptions-item label="节点记录">{{ detail.node_count }}（历史失败 {{ detail.failed_node_count }}）</el-descriptions-item>
          <el-descriptions-item label="恢复 / 查询重试">{{ detail.resume_count }} / {{ detail.retry_count }}</el-descriptions-item>
          <el-descriptions-item label="图执行累计耗时">{{ formatLatency(detail.graph_duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="节点累计耗时">{{ formatLatency(detail.node_duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="Checkpoint">{{ checkpointStatusLabel(detail.checkpoint?.status) }}</el-descriptions-item>
          <el-descriptions-item label="图版本">{{ detail.checkpoint?.graph_version ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="下一节点" :span="2">{{ detail.checkpoint?.next?.join(' → ') || '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.checkpoint?.expired_at" label="清理时间" :span="2">{{ formatDateTime(detail.checkpoint.expired_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.job" label="Worker 状态">{{ executionStatusLabel(detail.job.status) }} · 尝试 {{ detail.job.attempt_count }} 次</el-descriptions-item>
          <el-descriptions-item v-if="detail.job" label="租约到期">{{ formatDateTime(detail.job.lease_until) }}</el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="detail.orchestration_degraded" title="本轮使用兼容运行，未生成可恢复的节点 checkpoint；重新发起问答会重新查询。" type="warning" :closable="false" />
        <el-alert v-if="detail.job?.lease_expired" title="Worker 租约已过期，任务等待 worker 重新领取。" type="warning" :closable="false" />
        <el-alert v-if="detail.job?.error" :title="detail.job.error" type="error" :closable="false" />
        <div class="execution-node-heading">节点时间线 <span>图执行与节点耗时分别统计；恢复后会保留多次执行记录。</span></div>
        <el-alert v-if="detail.nodes_truncated" title="仅展示最近 500 条节点记录。" type="info" :closable="false" />
        <el-table :data="detail.nodes || []" size="small" stripe max-height="390" empty-text="暂无节点记录，或记录已按保留策略清理">
          <el-table-column label="节点" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">{{ row.node === '__graph__' ? '图执行' : row.node }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag size="small" effect="plain" :type="executionStatusTone(row.status)">{{ executionStatusLabel(row.status) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="开始" width="164"><template #default="{ row }">{{ formatDateTime(row.started_at) }}</template></el-table-column>
          <el-table-column label="结束" width="164"><template #default="{ row }">{{ formatDateTime(row.finished_at) }}</template></el-table-column>
          <el-table-column label="耗时" width="85"><template #default="{ row }">{{ formatLatency(row.duration_ms) }}</template></el-table-column>
          <el-table-column prop="retry_count" label="重试" width="60" />
          <el-table-column prop="error" label="失败原因" min-width="180" show-overflow-tooltip />
        </el-table>
        <section v-for="action in detail.actions || []" :key="action.id" class="execution-action-trace">
          <div class="execution-node-heading">动作 #{{ action.id }} · {{ action.title }} <span>{{ action.status_label }}；确认等待与业务执行耗时分别统计。</span></div>
          <el-alert v-if="action.nodes_truncated" title="仅展示最近 100 条动作节点记录。" type="info" :closable="false" />
          <el-table :data="action.nodes" size="small" stripe empty-text="该动作尚无节点审计记录">
            <el-table-column label="节点" min-width="140"><template #default="{ row }">{{ ({ action_review: '动作检查', action_confirmation: '人工确认', action_execute: '业务执行' })[row.node] || row.node }}</template></el-table-column>
            <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" effect="plain" :type="executionStatusTone(row.status)">{{ executionStatusLabel(row.status) }}</el-tag></template></el-table-column>
            <el-table-column label="开始" width="164"><template #default="{ row }">{{ formatDateTime(row.started_at) }}</template></el-table-column>
            <el-table-column label="结束" width="164"><template #default="{ row }">{{ formatDateTime(row.finished_at) }}</template></el-table-column>
            <el-table-column label="等待" width="95"><template #default="{ row }">{{ row.node === 'action_confirmation' ? formatLatency(row.waiting_ms) : '-' }}</template></el-table-column>
            <el-table-column label="执行耗时" width="95"><template #default="{ row }">{{ formatLatency(row.duration_ms) }}</template></el-table-column>
            <el-table-column prop="error" label="失败原因" min-width="180" show-overflow-tooltip />
          </el-table>
          <AIOpsRemediationVerification v-if="action.action_type === 'execute_host_task'" :action-id="action.id" />
        </section>
      </template>
      <el-empty v-else-if="!loading && !error" description="暂无执行记录" />
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { getAIOpsAuditExecution } from '@/api/modules/aiops'
import { checkpointStatusLabel, executionStatusLabel, executionStatusTone } from '@/utils/aiopsExecution'
import AIOpsRemediationVerification from './AIOpsRemediationVerification.vue'

const props = defineProps({ modelValue: Boolean, executionId: Number })
const emit = defineEmits(['update:modelValue', 'navigate'])
const loading = ref(false)
const error = ref('')
const detail = ref(null)
let requestSequence = 0

async function loadDetail() {
  const sequence = ++requestSequence
  loading.value = true
  error.value = ''
  try {
    const data = await getAIOpsAuditExecution(props.executionId, { skipErrorMessage: true })
    if (sequence === requestSequence) detail.value = data
  } catch (failure) {
    if (sequence === requestSequence) error.value = failure?.response?.data?.detail || '执行详情加载失败，请重试。'
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function navigate(tab) {
  emit('navigate', { tab, sessionId: detail.value.session_id, messageId: detail.value.message_id })
  emit('update:modelValue', false)
}

function formatLatency(value) {
  return `${(Number(value || 0) / 1000).toFixed(2)} s`
}

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}

watch(() => [props.modelValue, props.executionId], ([open, id]) => {
  detail.value = null
  error.value = ''
  requestSequence += 1
  if (open && id) loadDetail()
}, { immediate: true })
</script>

<style scoped>
.execution-detail { display: flex; flex-direction: column; gap: 12px; min-height: 120px; }
.execution-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.execution-actions .el-button { margin-left: 0; }
.execution-thread { overflow-wrap: anywhere; }
.execution-action-trace { display: flex; flex-direction: column; gap: 6px; }
.execution-node-heading { font-size: 14px; font-weight: 700; color: #0f172a; }
.execution-node-heading span { margin-left: 8px; font-size: 12px; font-weight: 400; color: #64748b; }
</style>
