<template>
  <el-dialog v-model="visible" :title="title" width="1000px" top="4vh" append-to-body destroy-on-close>
    <div class="yaml-editor-context"><el-tag>{{ cluster?.name }}</el-tag><span>支持单个资源；预检通过后可应用到当前集群。</span></div>
    <el-input v-model="content" type="textarea" :rows="20" :readonly="busy" spellcheck="false" class="yaml-editor-input" @input="preview = null" />
    <template v-if="preview">
      <el-alert type="success" :closable="false" :title="`预检通过 · ${preview.operation === 'create' ? '创建' : '更新'} ${preview.kind}/${preview.name}`" />
      <pre class="yaml-editor-diff">{{ preview.diff || '无内容差异' }}</pre>
    </template>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :loading="busy" :disabled="!content.trim()" @click="validate">预检与差异</el-button>
      <el-button type="primary" :loading="busy" :disabled="!preview" @click="apply">应用资源</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getK8sResourceYaml, previewK8sYaml, applyK8sYaml } from '@/api/modules/container'
import { createK8sResourceTemplate } from '@/utils/k8sResources'
const emit = defineEmits(['applied'])
const visible = ref(false)
const cluster = ref(null)
const namespace = ref('default')
const content = ref('')
const title = ref('YAML 创建资源')
const preview = ref(null)
const busy = ref(false)
async function open(selectedCluster, ns, resourceType, row) {
  cluster.value = selectedCluster
  namespace.value = row?.namespace || (ns === '_all' ? selectedCluster.access_scope?.namespaces?.[0] || 'default' : ns) || 'default'
  preview.value = null
  title.value = row ? `编辑 YAML · ${resourceType}/${row.name}` : 'YAML 创建资源'
  content.value = ''
  if (row) {
    const data = await getK8sResourceYaml(selectedCluster.id, resourceType, row.name, namespace.value)
    content.value = data.yaml
  } else {
    const template = createK8sResourceTemplate(resourceType, namespace.value)
    title.value = `YAML 创建 · ${template.kind}`
    content.value = template.yaml
  }
  visible.value = true
}
async function validate() {
  busy.value = true
  preview.value = null
  try {
    preview.value = await previewK8sYaml(cluster.value.id, { yaml: content.value, namespace: namespace.value })
  } finally { busy.value = false }
}
async function apply() {
  try {
    await ElMessageBox.confirm(`确认向 ${cluster.value.name} 应用 ${preview.value.kind}/${preview.value.name}？`, '应用资源', { type: 'warning', confirmButtonText: '确认应用', cancelButtonText: '取消' })
  } catch { return }
  busy.value = true
  try {
    await applyK8sYaml(cluster.value.id, { yaml: content.value, namespace: namespace.value, expected_version: preview.value.resource_version })
    ElMessage.success('资源已应用')
    visible.value = false
    emit('applied')
  } finally { busy.value = false }
}
defineExpose({ open })
</script>

<style scoped>
.yaml-editor-context { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; font-size: 13px; color: #64748b; }
.yaml-editor-input :deep(textarea) { font-family: 'Cascadia Code', Consolas, monospace; font-size: 13px; line-height: 1.6; tab-size: 2; }
.yaml-editor-diff { max-height: 220px; overflow: auto; background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; white-space: pre-wrap; }
</style>
