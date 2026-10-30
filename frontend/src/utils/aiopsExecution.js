export const executionStatusOptions = [
  { label: '排队中', value: 'queued' },
  { label: '执行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
  { label: '已中断', value: 'interrupted' },
  { label: '未知', value: 'unknown' },
]

export function executionStatusLabel(status) {
  return executionStatusOptions.find(item => item.value === status)?.label
    || ({ skipped: '已跳过', blocked: '已拦截', waiting: '待确认', canceled: '已取消' })[status] || status || '-'
}

export function executionStatusTone(status) {
  return ({ completed: 'success', failed: 'danger', interrupted: 'warning', blocked: 'warning', waiting: 'warning', running: 'primary' })[status] || 'info'
}

export function checkpointStatusLabel(status) {
  return ({ available: '可用', missing: '尚无记录', expired: '已按保留策略清理', cleanup_pending: '清理中', unavailable: '存储暂不可用', degraded: '降级运行，不支持断点恢复' })[status] || '-'
}
