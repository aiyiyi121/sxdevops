<template>
  <div class="question-scope-group">
    <el-popover v-model:visible="pickerOpen" placement="top-start" trigger="click" :width="440" :persistent="false" :popper-style="{ width: 'min(440px, calc(100vw - 32px))', padding: '12px', borderRadius: '14px' }">
      <template #reference>
        <button type="button" class="scope-trigger" :disabled="disabled" :aria-expanded="pickerOpen" aria-label="选择问答类型">
          <span class="scope-label">问答类型</span>
          <el-icon><component :is="icons[category.icon]" /></el-icon>
          <strong>{{ category.label }}</strong>
          <el-icon class="scope-chevron"><ArrowDown /></el-icon>
        </button>
      </template>
      <div class="scope-picker" aria-label="问答类型">
        <div class="scope-picker-head">
          <strong>选择问答类型</strong>
          <button type="button" class="scope-auto" :class="{ active: modelValue === 'auto' }" :disabled="disabled" @click="selectCategory('auto')">
            <el-icon><MagicStick /></el-icon>自动识别
          </button>
        </div>
        <div class="scope-grid">
          <button v-for="option in categories" :key="option.value" type="button" class="scope-option" :class="{ active: modelValue === option.value }" :disabled="disabled" :aria-pressed="modelValue === option.value" :aria-label="option.label" :title="option.description" @click="selectCategory(option.value)">
            <span class="scope-option-icon"><el-icon><component :is="icons[option.icon]" /></el-icon></span>
            <span class="scope-option-copy"><strong>{{ option.label }}</strong><small>{{ option.summary }}</small></span>
          </button>
        </div>
      </div>
    </el-popover>
    <el-select v-if="showEnvironment" ref="environmentSelectRef" :model-value="environment" class="scope-environment" :class="{ required: category.requiresEnvironment && !environment }" :placeholder="category.requiresEnvironment ? '请先选择知识图谱环境' : '知识图谱环境（可选）'" :aria-label="category.requiresEnvironment ? '选择知识图谱环境（必选）' : '选择知识图谱环境'" size="small" filterable clearable :disabled="disabled" :loading="loading" @update:model-value="$emit('update:environment', $event || '')">
      <el-option v-for="option in environments" :key="option.name" :label="option.name" :value="option.name" />
      <template #empty>
        <div class="scope-environment-empty">
          <span>暂无已启用的环境，请联系管理员配置</span>
          <el-button text size="small" :loading="loading" @click="$emit('refresh')">刷新环境</el-button>
        </div>
      </template>
    </el-select>
    <span v-else class="scope-hint">按资源授权范围</span>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowDown, Coin, Connection, DataAnalysis, Document, FirstAidKit, MagicStick, Operation } from '@element-plus/icons-vue'
import { getQuestionCategory } from '@/utils/aiopsQuestionScope'

const props = defineProps({
  modelValue: { type: String, default: 'auto' },
  environment: { type: String, default: '' },
  environments: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
  disabled: Boolean,
  loading: Boolean,
})
const emit = defineEmits(['update:modelValue', 'update:environment', 'refresh'])
const icons = { Coin, Connection, DataAnalysis, Document, FirstAidKit, MagicStick, Operation }
const categories = computed(() => props.options.filter(item => item.value !== 'auto'))
const category = computed(() => getQuestionCategory(props.modelValue, props.options))
const showEnvironment = computed(() => props.modelValue !== 'cmdb')
const pickerOpen = ref(false)
const environmentSelectRef = ref(null)
defineExpose({ focusEnvironment: () => environmentSelectRef.value?.focus() })

function selectCategory(value) {
  emit('update:modelValue', value)
  pickerOpen.value = false
}
</script>

<style scoped>
.question-scope-group{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap}
.scope-trigger{display:inline-flex;align-items:center;gap:6px;max-width:100%;height:28px;padding:0 8px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;color:#245bdb;font-size:12px;cursor:pointer}
.scope-trigger:hover,.scope-trigger[aria-expanded="true"]{background:#f1f5ff;border-color:#bfdbfe}
.scope-trigger:disabled,.scope-option:disabled,.scope-auto:disabled{cursor:not-allowed;opacity:.6}
.scope-label{font-size:11px;color:#64748b;margin-right:2px;white-space:nowrap}
.scope-trigger strong{font-weight:600;white-space:nowrap}
.scope-chevron{font-size:11px;color:#94a3b8}
.scope-picker-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;font-size:12px;color:#334155}
.scope-auto{display:inline-flex;align-items:center;gap:4px;padding:5px 8px;border:0;border-radius:6px;background:#f8fafc;color:#64748b;font-size:11px;cursor:pointer}
.scope-auto.active{background:#e8f0ff;color:#245bdb}
.scope-picker{max-height:min(440px,calc(100dvh - 160px));overflow-y:auto}
.scope-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.scope-option{display:flex;align-items:center;gap:9px;min-width:0;min-height:58px;padding:9px 10px;border:1px solid transparent;border-radius:9px;background:#f8faff;color:#334155;font-size:12px;text-align:left;cursor:pointer;transition:background .18s,border-color .18s}
.scope-option:hover{background:#f0f4ff;border-color:#dbe7ff;color:#245bdb}
.scope-option.active{background:#e8f0ff;border-color:#cddfff;color:#245bdb;font-weight:600}
.scope-option-icon{display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:8px;background:linear-gradient(145deg,#eef0ff,#dfe8ff);color:#5b67e8;font-size:18px;flex-shrink:0}
.scope-option-copy{display:flex;flex-direction:column;gap:4px;min-width:0}
.scope-option-copy strong{font-size:12px;font-weight:600;line-height:1.2}
.scope-option-copy small{color:#8491a5;font-size:10px;font-weight:400;line-height:1.4}
.scope-environment{width:170px}
.scope-environment :deep(.el-select__wrapper){border-radius:8px;min-height:28px;background:#fff}
.scope-environment.required :deep(.el-select__wrapper){box-shadow:0 0 0 1px #f2ce95 inset;background:#fffcf5}
.scope-environment-empty{display:flex;align-items:center;flex-direction:column;gap:4px;padding:14px;color:#94a3b8;font-size:12px}
.scope-hint{font-size:11px;color:#94a3b8;white-space:nowrap}
@media(max-width:760px){.question-scope-group{gap:6px}.scope-environment{width:145px}.scope-hint{display:none}.scope-option{gap:7px;padding:8px}.scope-option-icon{width:24px;height:24px;font-size:16px}}
</style>
