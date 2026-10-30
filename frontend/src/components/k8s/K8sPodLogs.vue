<template>
  <el-dialog :model-value="modelValue" :title="`${source === 'docker' ? '容器' : 'Pod'} 日志 · ${pod.name || ''}`" width="94%" top="3vh" :fullscreen="fullscreen" class="k8s-logs-dialog" append-to-body destroy-on-close :close-on-click-modal="false" @update:model-value="$emit('update:modelValue', $event)" @opened="refresh" @close="cancel">
    <div class="logs-workspace" :class="{ 'is-fullscreen': fullscreen }">
      <div class="logs-toolbar">
        <span class="logs-context">{{ cluster.name }} / {{ source === 'docker' ? pod.name : pod.namespace }}</span>
        <el-select v-if="source !== 'docker'" v-model="container" aria-label="日志容器" size="small" style="width:170px" @change="refresh">
          <el-option v-for="name in pod.containers || []" :key="name" :label="name" :value="name" />
        </el-select>
        <el-checkbox v-if="source !== 'docker'" v-model="previous" @change="refresh">上次运行</el-checkbox>
        <div class="logs-toolbar-actions">
          <el-button size="small" :disabled="busy" @click="refresh">刷新</el-button>
          <el-button size="small" :disabled="!pages.length || busy" @click="jumpLatest">回到最新</el-button>
          <el-button size="small" :disabled="!content" @click="copy">复制当前内容</el-button>
          <el-button size="small" @click="fullscreen = !fullscreen">{{ fullscreen ? '退出全屏' : '全屏' }}</el-button>
        </div>
      </div>
      <div class="logs-history-bar">
        <el-button link type="primary" :disabled="busy || !pages[0]?.before" :loading="busy && loadingDirection === 'older'" @click="load('older')">加载更早日志</el-button>
        <span>{{ busy ? (loadingDirection === 'latest' ? '正在读取最近日志…' : '正在加载…') : pages[0]?.before ? '向上滚动可继续加载历史日志' : '已到该容器保留日志的开头' }}</span>
      </div>
      <div v-if="error" class="logs-error" role="alert">{{ error }}<el-button link type="primary" @click="refresh">重试</el-button></div>
      <div ref="viewport" class="logs-viewport" tabindex="0" aria-label="Pod 日志内容" @scroll.passive="onScroll">
        <pre v-for="page in pages" :key="page.key" class="logs-page">{{ page.logs }}</pre>
        <div v-if="!busy && !content && !error" class="logs-empty">该容器暂无日志</div>
        <div v-if="busy && !pages.length" class="logs-empty">正在加载日志…</div>
      </div>
      <div class="logs-footer"><span>滚动浏览完整保留历史 · 当前窗口 {{ visibleLines }} 行</span><span>{{ pages.at(-1)?.after ? '向下滚动继续查看' : '已到本次采集的最新日志' }}</span></div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getDockerLogPage, getK8sPodLogPage } from '@/api/modules/container'
import { copyText } from '@/utils/clipboard'

const props = defineProps({ modelValue: Boolean, source: { type: String, default: 'k8s' }, cluster: { type: Object, required: true }, pod: { type: Object, required: true } })
defineEmits(['update:modelValue'])
const container = ref(props.pod.containers?.[0] || '')
const previous = ref(false)
const fullscreen = ref(false)
const viewport = ref(null)
const pages = ref([])
const busy = ref(false)
const error = ref('')
const loadingDirection = ref('latest')
const content = computed(() => pages.value.map(page => page.logs).join(''))
const visibleLines = computed(() => content.value ? content.value.split('\n').length - (content.value.endsWith('\n') ? 1 : 0) : 0)
let controller = null
let generation = 0
let pageKey = 0

function cancel() {
  generation += 1
  controller?.abort()
  controller = null
  busy.value = false
}

async function load(direction = 'latest', cursor = null) {
  if (busy.value || !props.modelValue) return
  if (direction === 'older') cursor = pages.value[0]?.before
  if (direction === 'newer') cursor = pages.value.at(-1)?.after
  if (direction !== 'latest' && !cursor) return
  const requestGeneration = generation
  const oldTop = viewport.value?.scrollTop || 0
  const removedHeight = direction === 'newer' && pages.value.length === 3 ? viewport.value?.firstElementChild?.getBoundingClientRect().height || 0 : 0
  busy.value = true
  loadingDirection.value = direction
  error.value = ''
  controller = new AbortController()
  try {
    const params = {
      pod_name: props.pod.name, namespace: props.pod.namespace || 'default', container: container.value,
      previous: previous.value, direction, cursor: cursor || undefined, page_size: 500,
    }
    const page = props.source === 'docker'
      ? await getDockerLogPage(props.pod.id, { host_id: props.cluster.id, direction, cursor: cursor || undefined, page_size: 500 }, controller.signal)
      : await getK8sPodLogPage(props.cluster.id, params, controller.signal)
    if (requestGeneration !== generation || !props.modelValue) return
    if (direction === 'older' && !page.logs) {
      pages.value[0].before = null
      return
    }
    page.key = ++pageKey
    if (direction === 'older') {
      pages.value.unshift(page)
      if (pages.value.length > 3) pages.value.pop()
    } else if (direction === 'newer') {
      pages.value.push(page)
      if (pages.value.length > 3) pages.value.shift()
    } else pages.value = [page]
    await nextTick()
    if (!viewport.value || requestGeneration !== generation) return
    if (direction === 'older') viewport.value.scrollTop = oldTop + viewport.value.firstElementChild.getBoundingClientRect().height
    else if (direction === 'newer') viewport.value.scrollTop = Math.max(1, oldTop - removedHeight)
    else viewport.value.scrollTop = viewport.value.scrollHeight
  } catch (failure) {
    if (requestGeneration === generation && failure.code !== 'ERR_CANCELED') error.value = failure.response?.data?.detail || '读取日志失败，请重试。'
  } finally {
    if (requestGeneration === generation) busy.value = false
  }
}

function refresh() {
  cancel()
  pages.value = []
  load()
}

function jumpLatest() {
  const snapshot = pages.value[0]?.snapshot
  if (snapshot) load('latest', snapshot)
}

function onScroll() {
  const element = viewport.value
  if (!element || busy.value) return
  if (element.scrollTop < 60 && pages.value[0]?.before) load('older')
  else if (element.scrollHeight - element.clientHeight - element.scrollTop < 60 && pages.value.at(-1)?.after) load('newer')
}

async function copy() {
  try {
    await copyText(content.value)
    ElMessage.success('已复制当前窗口的日志')
  } catch { ElMessage.error('复制失败，请选中文本后复制') }
}

watch(() => props.pod, () => { container.value = props.pod.containers?.[0] || '' })
onBeforeUnmount(cancel)
</script>

<style scoped>
:global(.el-dialog.k8s-logs-dialog) { margin: 3vh auto !important; }
:global(.el-dialog.k8s-logs-dialog.is-fullscreen) { margin: 0 !important; }
:global(.k8s-logs-dialog .el-dialog__body) { max-height: none; overflow: hidden; padding: 12px 16px 16px !important; }
.logs-workspace { display: flex; flex-direction: column; gap: 10px; height: calc(86dvh - 90px); min-height: 360px; }
.logs-workspace.is-fullscreen { height: calc(100dvh - 110px); }
.logs-toolbar, .logs-toolbar-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.logs-context { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #475569; font-size: 12px; }
.logs-toolbar-actions { margin-left: auto; }
.logs-history-bar, .logs-footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: #64748b; font-size: 12px; }
.logs-viewport { flex: 1; min-height: 0; overflow: auto; padding: 12px; border-radius: 10px; background: #0b1220; color: #dbe5f5; overflow-anchor: none; }
.logs-page { margin: 0; font: 13px/21px 'Cascadia Code', Consolas, monospace; white-space: pre; tab-size: 4; }
.logs-empty { padding: 30px; color: #94a3b8; text-align: center; }
.logs-error { display: flex; align-items: center; gap: 10px; color: #dc2626; font-size: 13px; }
@media (max-width: 640px) { .logs-toolbar-actions { margin-left: 0; } .logs-history-bar, .logs-footer { align-items: flex-start; flex-direction: column; gap: 4px; } }
</style>
