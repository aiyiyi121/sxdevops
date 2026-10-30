<template>
  <el-dialog v-model="visible" :title="provider?.id ? '编辑模型提供商' : '新增模型提供商'" width="min(940px, 94vw)" class="workbench-edit-dialog model-provider-dialog" top="5vh" append-to-body destroy-on-close :close-on-click-modal="false" :before-close="beforeClose">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="provider-editor" :disabled="saving" @submit.prevent>
      <section class="editor-section">
        <div class="editor-heading"><span class="step-number">01</span><h3>连接供应商</h3><el-tag size="small" type="info" effect="plain">OpenAI 兼容协议</el-tag></div>
        <div class="preset-grid" aria-label="供应商预设">
          <button v-for="preset in presets" :key="preset.key" type="button" class="preset-button" :class="{ 'is-active': form.provider_preset === preset.key }" :aria-pressed="form.provider_preset === preset.key" :disabled="saving" @click="applyPreset(preset)">
            {{ preset.key === 'custom_openai_compatible' ? '自定义接入' : preset.name }}
          </button>
        </div>
        <div v-if="selectedPreset" class="preset-description"><span>{{ presetNotes }}</span><a v-if="selectedPreset.docs_url" :href="selectedPreset.docs_url" target="_blank" rel="noopener noreferrer">官方文档 ↗</a></div>
        <div class="connection-grid">
          <el-form-item label="显示名称" prop="name"><el-input v-model="form.name" placeholder="例如：生产 DeepSeek" maxlength="128" /></el-form-item>
          <el-form-item label="API Key" prop="api_key"><el-input v-model="form.api_key" type="password" show-password autocomplete="off" :placeholder="canReuseKey ? '已配置，留空保留原密钥' : (selectedPreset?.api_key_placeholder || '填写供应商 API Key')" /></el-form-item>
          <el-form-item label="Base URL" prop="base_url" class="full-width"><el-input v-model="form.base_url" placeholder="https://api.example.com/v1" /><div class="field-hint">填写 API 基础地址，无需追加 /chat/completions。</div></el-form-item>
        </div>
      </section>

      <section class="editor-section model-section">
        <div class="editor-heading model-heading">
          <span class="step-number">02</span><h3>选择模型</h3>
          <el-button size="small" :loading="discovering" :disabled="!canDiscover" @click="discoverModels"><el-icon><Refresh /></el-icon>{{ discovered ? '刷新模型列表' : '获取模型列表' }}</el-button>
        </div>
        <div class="discovery-status" :class="{ 'has-warning': discoveryError || catalogWarning }" role="status" aria-live="polite">
          <el-icon v-if="discovering" class="is-loading"><Loading /></el-icon>
          <span v-if="discovering">正在获取供应商模型列表，请稍候…</span>
          <span v-else-if="discoveryError">{{ discoveryError }}；也可手动填写模型 ID。</span>
          <span v-else-if="catalogWarning">模型目录暂不可用，已保留预设与当前模型；可重试或手动填写。</span>
          <span v-else-if="discovered">{{ catalog.length ? `已获取 ${catalog.length} 个模型，搜索后选择，或输入自定义模型 ID。` : '供应商未返回模型，可手动填写模型 ID。' }}</span>
          <span v-else>{{ canDiscover ? '连接信息已就绪，可直接获取模型，无需先保存。' : '填写 Base URL 和 API Key 后获取列表，也可直接填写模型 ID。' }}</span>
        </div>
        <div class="model-pair">
          <div v-for="field in modelFields" :key="field.key" class="model-choice" :class="{ 'model-choice--primary': field.key === 'default_model' }">
            <el-form-item :label="field.label" :prop="field.key">
              <el-select v-model="form[field.key]" filterable allow-create default-first-option clearable :loading="discovering" :placeholder="field.placeholder" :aria-label="field.label" :popper-options="{ strategy: 'fixed' }" popper-class="provider-model-options" @change="formRef?.validateField(field.key).catch(() => {})">
                <el-option v-for="model in modelOptions" :key="model.id" :value="model.id" :label="model.id" :disabled="field.key === 'backup_model' && model.id === form.default_model">
                  <div class="model-option"><span :title="model.id">{{ model.id }}</span><small>{{ model.source }}</small></div>
                </el-option>
                <template #empty><div class="model-empty">暂无模型列表，输入模型 ID 后按回车确认</div></template>
              </el-select>
            </el-form-item>
            <p>{{ field.help }}</p>
          </div>
        </div>
        <div class="model-footnote">预设型号仅供参考；请选择账号已开通、支持工具调用的对话模型。获取列表不会发起对话或改动你的选择。</div>
      </section>

      <el-collapse v-model="advancedSections" class="provider-advanced">
        <el-collapse-item name="parameters">
          <template #title><span class="advanced-title">调用参数与费用</span><span class="advanced-summary">{{ form.max_tokens }} Tokens · {{ form.timeout_seconds }}s</span></template>
          <div class="parameter-grid">
            <el-form-item label="温度" prop="temperature"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" controls-position="right" /><div class="field-hint">越低越稳定，越高越灵活。</div></el-form-item>
            <el-form-item label="最大输出 Tokens" prop="max_tokens"><el-input-number v-model="form.max_tokens" :min="100" :max="16000" :step="100" controls-position="right" /></el-form-item>
            <el-form-item label="请求超时（秒）" prop="timeout_seconds"><el-input-number v-model="form.timeout_seconds" :min="5" :max="120" controls-position="right" /></el-form-item>
            <el-form-item label="计费币种"><el-segmented v-model="form.price_currency" :options="[{ label: '人民币', value: 'CNY' }, { label: '美元', value: 'USD' }]" /></el-form-item>
            <el-form-item :label="`输入单价（${priceUnit}）`"><el-input-number v-model="form.input_token_price_per_1m" :min="0" :precision="6" :step="0.01" :controls="false" /></el-form-item>
            <el-form-item :label="`输出单价（${priceUnit}）`"><el-input-number v-model="form.output_token_price_per_1m" :min="0" :precision="6" :step="0.01" :controls="false" /></el-form-item>
          </div>
          <div class="field-hint">单价用于费用估算，按供应商实际价格填写；留 0 时不估算费用。</div>
        </el-collapse-item>
      </el-collapse>
      <div class="provider-enable"><div><strong>启用此提供商</strong><span>保存后可在列表中设为默认供应商</span></div><el-switch v-model="form.is_enabled" aria-label="启用此提供商" /></div>
    </el-form>
    <template #footer><div class="editor-footer"><span>保存后生效</span><div><el-button :disabled="saving" @click="beforeClose(() => visible = false)">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存提供商</el-button></div></div></template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Loading, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createAIOpsProvider, discoverAIOpsProviderModels, updateAIOpsProvider } from '@/api/modules/aiops'

const visible = defineModel({ type: Boolean, default: false })
const props = defineProps({ provider: { type: Object, default: null }, presets: { type: Array, default: () => [] } })
const emit = defineEmits(['saved'])
const formRef = ref()
const form = reactive({})
const baseline = ref('')
const saving = ref(false)
const discovering = ref(false)
const discovered = ref(false)
const discoveryError = ref('')
const catalogWarning = ref('')
const catalog = ref([])
const advancedSections = ref([])
let discoveryVersion = 0
const selectedPreset = computed(() => props.presets.find(item => item.key === form.provider_preset))
const presetNotes = computed(() => (selectedPreset.value?.notes || '').replace(/保存 API Key 后|保存后/g, '填写连接信息后'))
const canReuseKey = computed(() => Boolean(props.provider?.has_api_key && form.base_url?.trim().replace(/\/+$/, '') === props.provider.base_url?.replace(/\/+$/, '')))
const canDiscover = computed(() => Boolean(form.base_url?.trim() && (form.api_key?.trim() || canReuseKey.value)))
const priceUnit = computed(() => `${form.price_currency === 'USD' ? '$' : '¥'}/百万 Token`)
const modelFields = [
  { key: 'default_model', label: '默认模型', placeholder: '搜索或输入模型 ID', help: '智能助手优先使用此模型，必填。' },
  { key: 'backup_model', label: '备用模型（可选）', placeholder: '可不设置，支持手动输入', help: '默认模型调用失败时尝试，需与默认模型不同。' },
]
const modelOptions = computed(() => {
  const options = new Map()
  for (const model of catalog.value) options.set(model.id, { ...model, source: model.owned_by || '供应商目录' })
  for (const id of [selectedPreset.value?.default_model, selectedPreset.value?.backup_model]) {
    if (id && !options.has(id)) options.set(id, { id, source: '预设参考' })
  }
  for (const id of [form.default_model, form.backup_model]) {
    if (id && !options.has(id)) options.set(id, { id, source: '当前填写' })
  }
  return [...options.values()]
})
const rules = {
  name: [{ required: true, whitespace: true, message: '请填写显示名称', trigger: 'blur' }],
  base_url: [{ required: true, message: '请填写 Base URL', trigger: 'blur' }, { type: 'url', message: '请填写完整的 http(s) 地址', trigger: 'blur' }],
  api_key: [{ validator: (_, value, done) => done(!value?.trim() && !canReuseKey.value ? new Error('请填写当前连接地址对应的 API Key') : undefined), trigger: 'blur' }],
  default_model: [{ required: true, whitespace: true, message: '请选择或输入默认模型 ID', trigger: ['change', 'blur'] }],
  backup_model: [{ validator: (_, value, done) => done(value && value.trim() === form.default_model?.trim() ? new Error('备用模型需与默认模型不同') : undefined), trigger: ['change', 'blur'] }],
  temperature: [{ required: true, type: 'number', message: '请填写温度', trigger: 'blur' }],
  max_tokens: [{ required: true, type: 'number', message: '请填写最大输出 Tokens', trigger: 'blur' }],
  timeout_seconds: [{ required: true, type: 'number', message: '请填写请求超时', trigger: 'blur' }],
}

function clearDiscovery() {
  discoveryVersion += 1
  discovering.value = false
  catalog.value = []
  discovered.value = false
  discoveryError.value = ''
  catalogWarning.value = ''
}

watch(visible, (open) => {
  clearDiscovery()
  if (!open) { form.api_key = ''; return }
  Object.keys(form).forEach(key => delete form[key])
  Object.assign(form, {
    name: '', provider_type: 'openai_compatible', provider_preset: '', base_url: '', api_key: '',
    default_model: '', backup_model: '', temperature: 0.2, max_tokens: 10000, timeout_seconds: 30,
    price_currency: 'CNY', input_token_price_per_1m: 0, output_token_price_per_1m: 0, is_enabled: true,
    ...props.provider, api_key: '',
  })
  for (const key of ['temperature', 'max_tokens', 'timeout_seconds', 'input_token_price_per_1m', 'output_token_price_per_1m']) {
    form[key] = Number(form[key])
  }
  baseline.value = JSON.stringify(form)
  advancedSections.value = []
}, { immediate: true })
watch(() => [form.base_url, form.api_key, form.provider_preset], clearDiscovery, { flush: 'sync' })
watch(() => form.default_model, () => formRef.value?.validateField('backup_model').catch(() => {}))

function applyPreset(preset) {
  if (preset.key === form.provider_preset) return
  const previous = selectedPreset.value
  if (!form.name || form.name === previous?.name) form.name = preset.name
  Object.assign(form, {
    provider_preset: preset.key, base_url: preset.base_url || '',
    default_model: preset.default_model || '', backup_model: preset.backup_model || '',
    temperature: preset.temperature ?? 0.2, max_tokens: preset.max_tokens || 10000,
    timeout_seconds: preset.timeout_seconds || 30, price_currency: preset.price_currency || 'CNY',
  })
  // A credential belongs to its supplier; require re-entry when switching to another one.
  form.api_key = ''
  formRef.value?.clearValidate()
}

async function discoverModels() {
  if (!canDiscover.value || discovering.value) return
  if (!await formRef.value.validateField(['base_url', 'api_key']).catch(() => false)) return
  const version = ++discoveryVersion
  discovering.value = true
  discoveryError.value = ''
  catalogWarning.value = ''
  try {
    const result = await discoverAIOpsProviderModels({
      ...(props.provider?.id ? { provider_id: props.provider.id } : {}),
      base_url: form.base_url.trim(), api_key: form.api_key.trim(), provider_preset: form.provider_preset,
      default_model: form.default_model || '', backup_model: form.backup_model || '', timeout_seconds: form.timeout_seconds || 30,
    })
    if (version !== discoveryVersion) return
    catalog.value = result.models || []
    catalogWarning.value = result.catalog_error || ''
    discovered.value = true
  } catch (error) {
    if (version !== discoveryVersion) return
    discoveryError.value = error.response?.data?.detail || (error.code === 'ECONNABORTED' ? '获取超时，请重试' : '获取失败，请检查地址和密钥')
  } finally {
    if (version === discoveryVersion) discovering.value = false
  }
}

async function beforeClose(done) {
  if (saving.value) return
  if (JSON.stringify(form) !== baseline.value) {
    try { await ElMessageBox.confirm('尚有未保存的配置，确认放弃本次修改？', '放弃修改', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' }) }
    catch { return }
  }
  done()
}

async function save() {
  if (!await formRef.value.validate().catch(() => false)) return
  saving.value = true
  try {
    const fields = ['name', 'provider_type', 'provider_preset', 'base_url', 'api_key', 'default_model', 'backup_model', 'temperature', 'max_tokens', 'timeout_seconds', 'price_currency', 'input_token_price_per_1m', 'output_token_price_per_1m', 'is_enabled']
    const payload = Object.fromEntries(fields.map(key => [key, typeof form[key] === 'string' ? form[key].trim() : form[key]]))
    if (!payload.api_key) delete payload.api_key
    if (props.provider?.id) await updateAIOpsProvider(props.provider.id, payload)
    else await createAIOpsProvider(payload)
    visible.value = false
    ElMessage.success('模型提供商已保存')
    emit('saved')
  } finally { saving.value = false }
}
</script>

<style scoped>
.provider-editor { display: flex; flex-direction: column; gap: 16px; }
.editor-section { min-width: 0; }
.editor-heading { display: flex; align-items: center; gap: 9px; margin-bottom: 12px; }
.editor-heading h3 { margin: 0; font-size: 14px; color: var(--el-text-color-primary); }
.step-number { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); font-size: 12px; font-weight: 700; }
.preset-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.preset-button { padding: 9px 8px; border: 1px solid var(--el-border-color-light); border-radius: 9px; background: var(--el-fill-color-blank); color: var(--el-text-color-regular); font: inherit; font-size: 12px; cursor: pointer; transition: background .15s, border-color .15s; }
.preset-button:hover, .preset-button.is-active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.preset-button:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.preset-description { display: flex; gap: 12px; justify-content: space-between; font-size: 12px; line-height: 1.6; color: var(--text-secondary, var(--el-text-color-secondary)); margin: 10px 0 2px; }
.preset-description a { color: var(--el-color-primary); white-space: nowrap; text-decoration: none; }
.connection-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; margin-top: 12px; }
.full-width { grid-column: 1 / -1; }
.provider-editor :deep(.el-form-item) { margin-bottom: 14px; }
.provider-editor :deep(.el-form-item__label) { font-size: 12px; font-weight: 600; margin-bottom: 6px; line-height: 20px; height: auto; color: var(--el-text-color-regular); }
.provider-editor :deep(.el-select), .parameter-grid :deep(.el-input-number) { width: 100%; }
.provider-editor :deep(.el-input__wrapper), .provider-editor :deep(.el-select__wrapper) { border-radius: 8px; }
.field-hint { width: 100%; color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.6; margin-top: 5px; }
.model-section { padding: 14px; border: 1px solid var(--el-border-color-light); border-radius: 12px; background: var(--el-fill-color-lighter); }
.model-heading { margin-bottom: 9px; }
.model-heading .el-button { margin-left: auto; }
.discovery-status { display: flex; align-items: center; gap: 6px; color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.6; margin-bottom: 12px; overflow-wrap: anywhere; }
.discovery-status.has-warning { color: var(--el-color-warning); }
.model-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.model-choice { min-width: 0; background: var(--el-fill-color-blank); border: 1px solid var(--el-border-color-light); border-radius: 10px; padding: 12px; }
.model-choice--primary { border-color: var(--el-color-primary-light-5); }
.model-choice p { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.6; margin: 6px 0 0; }
.model-choice :deep(.el-form-item) { margin-bottom: 0; }
.model-choice :deep(.el-form-item.is-error) { margin-bottom: 20px; }
.model-footnote { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.6; margin-top: 10px; }
.model-option { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.model-option > span { overflow: hidden; text-overflow: ellipsis; }
.model-option small { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 11px; font-weight: 400; flex-shrink: 0; }
.model-empty { padding: 14px; font-size: 12px; text-align: center; color: var(--text-secondary, var(--el-text-color-secondary)); }
.advanced-title { font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); }
.advanced-summary { margin-left: auto; padding-right: 12px; font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); }
.provider-advanced :deep(.el-collapse-item__title) { display: flex; align-items: center; flex: 1; gap: 12px; min-width: 0; }
.parameter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 16px; padding-top: 8px; }
.provider-enable, .editor-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.provider-enable strong { color: var(--el-text-color-regular); font-size: 13px; }
.provider-enable span { display: block; font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); margin-top: 5px; }
.editor-footer > span { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; }
@media (max-width: 640px) {
  .preset-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .connection-grid, .model-pair { grid-template-columns: 1fr; }
  .parameter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .preset-description { flex-direction: column; gap: 4px; }
  .model-section { padding: 10px; }
  .advanced-summary { font-size: 11px; }
}
</style>
