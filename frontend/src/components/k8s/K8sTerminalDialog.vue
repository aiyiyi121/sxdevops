<template>
  <el-dialog :model-value="modelValue" :title="kind === 'cluster' ? `集群控制台 · ${cluster.name || ''}` : `${kind === 'docker' ? '容器' : 'Pod'} 终端 · ${pod.name || ''}`" width="94%" top="3vh" :fullscreen="fullscreen" class="k8s-terminal-dialog" append-to-body destroy-on-close :close-on-click-modal="false" :close-on-press-escape="false" @update:model-value="$emit('update:modelValue', $event)" @opened="start" @close="dispose">
    <div class="terminal-workspace" :class="{ 'is-fullscreen': fullscreen }">
      <div class="terminal-toolbar">
        <span class="terminal-context" :title="context">{{ context }}</span>
        <template v-if="kind !== 'cluster'">
          <el-select v-if="kind === 'pod'" v-model="container" aria-label="终端容器" size="small" style="width:170px" @change="reconnect">
            <el-option v-for="name in pod.containers || []" :key="name" :value="name" :label="name" />
          </el-select>
          <el-select v-model="shell" aria-label="终端 Shell" size="small" style="width:170px" @change="reconnect">
            <el-option label="自动（优先 Bash）" value="auto" />
            <el-option v-for="name in ['/bin/sh', '/bin/bash', '/bin/ash']" :key="name" :value="name" :label="name" />
          </el-select>
        </template>
        <el-tag size="small" :type="statusTone">{{ statusText }}</el-tag>
        <div class="terminal-tools">
          <el-button size="small" :disabled="status === 'connecting'" @click="reconnect">重新连接</el-button>
          <el-button size="small" :disabled="status !== 'connected'" @click="disconnect">断开</el-button>
          <el-button size="small" @click="fullscreen = !fullscreen">{{ fullscreen ? '退出全屏' : '全屏' }}</el-button>
        </div>
      </div>
      <div class="terminal-actions">
        <el-button size="small" @click="copySelection">复制选中</el-button>
        <el-button size="small" :disabled="status !== 'connected'" @click="paste">粘贴</el-button>
        <el-button size="small" @click="terminal?.clear(); terminal?.focus()">清屏</el-button>
        <el-button size="small" :disabled="!sessionLog" @click="download">下载会话</el-button>
      </div>
      <div v-if="error" class="terminal-error" role="alert">{{ error }}</div>
      <div ref="host" class="terminal-host" aria-label="交互式终端"></div>
      <div class="terminal-footer"><span>Tab 原生补全 · Ctrl+C 中断 · Ctrl+V 粘贴 · {{ dimensions }}</span><span v-if="kind === 'cluster'">已绑定当前集群 · 会话最长 30 分钟</span></div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { copyText } from '@/utils/clipboard'
import '@xterm/xterm/css/xterm.css'

const props = defineProps({ modelValue: Boolean, kind: { type: String, default: 'pod' }, cluster: { type: Object, required: true }, pod: { type: Object, default: () => ({}) } })
defineEmits(['update:modelValue'])
const host = ref(null)
const container = ref(props.pod.containers?.[0] || '')
const shell = ref('auto')
const fullscreen = ref(false)
const status = ref('disconnected')
const error = ref('')
const dimensions = ref('')
const sessionLog = ref('')
const context = computed(() => props.kind === 'cluster' ? props.cluster.name : `${props.cluster.name} / ${props.kind === 'docker' ? props.pod.name : props.pod.namespace || 'default'}`)
const statusText = computed(() => ({ connecting: '正在连接', connected: '已连接', disconnected: '已断开', error: '连接失败' }[status.value]))
const statusTone = computed(() => ({ connecting: 'warning', connected: 'success', disconnected: 'info', error: 'danger' }[status.value]))
let terminal = null
let fitAddon = null
let socket = null
let observer = null
let resizeFrame = null
let connectTimeout = null

function fit() {
  if (resizeFrame !== null) cancelAnimationFrame(resizeFrame)
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null
    if (!host.value?.clientWidth || !terminal || !fitAddon) return
    fitAddon.fit()
    dimensions.value = `${terminal.cols} × ${terminal.rows}`
    if (socket?.readyState === WebSocket.OPEN && status.value === 'connected') socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }))
  })
}

function init() {
  if (terminal || !host.value) return
  terminal = new Terminal({ cursorBlink: true, fontSize: 14, lineHeight: 1.25, fontFamily: "'Cascadia Code', Consolas, monospace", scrollback: 10000, theme: { background: '#0b1220', foreground: '#dbe5f5', cursor: '#60a5fa', selectionBackground: '#3b82f655' } })
  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(host.value)
  terminal.onData(data => { if (status.value === 'connected') send(data) })
  terminal.attachCustomKeyEventHandler(event => {
    if (event.type === 'keydown' && event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault()
      event.stopPropagation()
      send(event.shiftKey ? '\u001b[Z' : '\t')
      return false
    }
    if (event.type === 'keydown' && (event.ctrlKey || event.metaKey) && event.shiftKey && event.code === 'KeyC') {
      event.preventDefault()
      copySelection()
      return false
    }
    return true
  })
  observer = new ResizeObserver(fit)
  observer.observe(host.value)
  fit()
}

function disconnect() {
  clearTimeout(connectTimeout)
  const closing = socket
  socket = null
  if (closing) {
    closing.onopen = closing.onmessage = closing.onclose = closing.onerror = null
    closing.close()
  }
  status.value = 'disconnected'
}

function reconnect() {
  if (!props.modelValue) return
  init()
  disconnect()
  terminal?.reset()
  error.value = ''
  status.value = 'connecting'
  const params = new URLSearchParams({ token: localStorage.getItem('sxdevops_token') || '' })
  if (props.kind === 'pod') {
    params.set('pod_name', props.pod.name)
    params.set('namespace', props.pod.namespace || 'default')
    params.set('container', container.value)
    params.set('shell', shell.value)
  } else if (props.kind === 'docker') {
    params.set('container_id', props.pod.id)
    params.set('shell', shell.value)
  }
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const endpoint = props.kind === 'cluster' ? 'terminal' : 'exec'
  const path = props.kind === 'docker' ? `docker/exec/${props.cluster.id}` : `k8s/${endpoint}/${props.cluster.id}`
  const current = new WebSocket(`${protocol}//${location.host}/ws/${path}/?${params}`)
  socket = current
  connectTimeout = setTimeout(() => {
    if (socket !== current || status.value !== 'connecting') return
    disconnect()
    status.value = 'error'
    error.value = '连接超时，请检查容器状态或重新连接。'
  }, 20000)
  current.onmessage = event => {
    if (socket !== current) return
    let payload
    try { payload = JSON.parse(event.data) } catch { return }
    if (payload.type === 'connected') {
      clearTimeout(connectTimeout)
      status.value = 'connected'
      fit()
      terminal?.focus()
    } else if (payload.type === 'output') {
      terminal?.write(payload.data || '')
      sessionLog.value = (sessionLog.value + (payload.data || '')).slice(-1000000)
    } else if (payload.type === 'error') {
      clearTimeout(connectTimeout)
      error.value = payload.message || '终端连接失败'
      status.value = 'error'
    }
  }
  current.onclose = event => {
    if (socket !== current) return
    clearTimeout(connectTimeout)
    socket = null
    const reason = { 4401: '登录已过期，请重新登录。', 4403: props.kind === 'docker' ? '没有 Docker 容器终端权限。' : '没有当前集群或命名空间的终端权限。', 4404: '目标环境不存在。', 4400: '终端参数无效。' }[event.code]
    if (reason) error.value = reason
    else if (status.value === 'connecting') error.value ||= '无法建立终端连接，请检查容器状态与 Shell。'
    status.value = error.value ? 'error' : 'disconnected'
  }
  current.onerror = () => {
    if (socket !== current) return
    error.value ||= '终端连接异常，请重新连接。'
    status.value = 'error'
  }
}

function send(data) {
  if (status.value !== 'connected' || socket?.readyState !== WebSocket.OPEN) return
  socket.send(JSON.stringify({ type: 'input', data }))
  terminal?.focus()
}

async function copySelection() {
  const text = terminal?.getSelection()
  if (!text) return ElMessage.info('请先在终端中选中需要复制的文本')
  try {
    await copyText(text)
    ElMessage.success('已复制')
  } catch { ElMessage.error('复制失败，可使用系统复制快捷键') }
  terminal?.focus()
}

async function paste() {
  let text
  if (navigator.clipboard?.readText) {
    try { text = await navigator.clipboard.readText() } catch { }
  }
  try {
    if (text === undefined) text = (await ElMessageBox.prompt('在此粘贴文本，确认后发送到终端。也可直接在终端使用 Ctrl+V。', '粘贴到终端', { inputType: 'textarea', confirmButtonText: '粘贴', cancelButtonText: '取消' })).value
    if (text) terminal?.paste(text)
    terminal?.focus()
  } catch { terminal?.focus() }
}

function download() {
  const url = URL.createObjectURL(new Blob([sessionLog.value], { type: 'text/plain;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${props.kind}-${props.pod.name || props.cluster.name}-${Date.now()}.log`
  anchor.click()
  URL.revokeObjectURL(url)
}

function start() {
  sessionLog.value = ''
  init()
  reconnect()
}

function dispose() {
  disconnect()
  observer?.disconnect()
  observer = null
  if (resizeFrame !== null) cancelAnimationFrame(resizeFrame)
  resizeFrame = null
  terminal?.dispose()
  terminal = null
  fitAddon = null
}

watch(fullscreen, async () => { await nextTick(); fit() })
onBeforeUnmount(dispose)
</script>

<style scoped>
:global(.el-dialog.k8s-terminal-dialog) { margin: 3vh auto !important; }
:global(.el-dialog.k8s-terminal-dialog.is-fullscreen) { margin: 0 !important; }
:global(.k8s-terminal-dialog .el-dialog__body) { max-height: none; overflow: hidden; padding: 12px 16px 16px !important; }
.terminal-workspace { display: flex; flex-direction: column; gap: 10px; height: calc(86dvh - 90px); min-height: 360px; }
.terminal-workspace.is-fullscreen { height: calc(100dvh - 110px); }
.terminal-toolbar, .terminal-tools, .terminal-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.terminal-context { max-width: 350px; color: #475569; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.terminal-tools { margin-left: auto; }
.terminal-host { flex: 1; min-height: 0; padding: 12px; overflow: hidden; border-radius: 10px; background: #0b1220; }
.terminal-host :deep(.xterm) { height: 100%; }
.terminal-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; color: #64748b; font-size: 12px; }
.terminal-error { padding: 8px 12px; border-radius: 8px; background: #fff1f2; color: #be123c; font-size: 13px; }
@media (max-width: 640px) { .terminal-tools { margin-left: 0; } .terminal-context { width: 100%; } .terminal-footer { font-size: 11px; } }
</style>
