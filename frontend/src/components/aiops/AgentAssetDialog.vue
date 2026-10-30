<template>
  <el-dialog v-model="visible" :title="title" width="min(940px, 94vw)" class="workbench-edit-dialog agent-asset-dialog" top="5vh" append-to-body destroy-on-close :close-on-click-modal="false" :before-close="beforeClose">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="saving" @submit.prevent>
      <slot />
    </el-form>
    <template #footer><div class="asset-footer"><span>保存后生效</span><div><el-button :disabled="saving" @click="beforeClose(() => visible = false)">取消</el-button><el-button type="primary" :loading="saving" @click="submit">{{ saveLabel }}</el-button></div></div></template>
  </el-dialog>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
const visible = defineModel({ type: Boolean, default: false })
const props = defineProps({ title: String, saveLabel: String, form: { type: Object, required: true }, rules: Object, saving: Boolean })
const emit = defineEmits(['save', 'invalid'])
const formRef = ref()
let baseline = ''
watch(visible, value => { if (value) baseline = JSON.stringify(props.form) }, { immediate: true })
async function beforeClose(done) {
  if (props.saving) return
  if (baseline !== JSON.stringify(props.form)) {
    try { await ElMessageBox.confirm('修改尚未保存，确定放弃吗？', '放弃修改', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' }) } catch { return }
  }
  done()
}
async function submit() {
  if (props.saving) return
  const valid = await formRef.value?.validate().catch(async fields => {
    emit('invalid', fields)
    await nextTick()
    formRef.value?.scrollToField(Object.keys(fields || {})[0])
    return false
  })
  if (!valid) return
  emit('save')
}
</script>

<style>
.agent-asset-dialog .asset-section + .asset-section { margin-top: 22px; }
.agent-asset-dialog .asset-heading { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.agent-asset-dialog .asset-heading h3 { margin: 0; color: var(--el-text-color-primary); font-size: 14px; }
.agent-asset-dialog .asset-step { display: grid; place-items: center; width: 25px; height: 25px; border-radius: 7px; color: var(--el-color-primary); background: var(--el-color-primary-light-9); font-size: 11px; font-weight: 700; }
.agent-asset-dialog .asset-heading .el-tag { margin-left: auto; }
.agent-asset-dialog .asset-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.agent-asset-dialog .asset-full { grid-column: 1 / -1; }
.agent-asset-dialog .el-form-item { margin-bottom: 18px; }
.agent-asset-dialog .el-form-item__label { height: auto; font-size: 12px; font-weight: 600; line-height: 20px; margin-bottom: 6px; color: var(--el-text-color-regular); }
.agent-asset-dialog .el-select, .agent-asset-dialog .el-input-number { width: 100%; }
.agent-asset-dialog .el-input__wrapper, .agent-asset-dialog .el-select__wrapper { border-radius: 8px; }
.agent-asset-dialog .asset-hint { width: 100%; color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.7; margin-top: 6px; }
.agent-asset-dialog .asset-note { padding: 10px 12px; border: 1px solid var(--el-border-color-light); border-radius: 10px; background: var(--el-fill-color-lighter); color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.7; margin-bottom: 16px; }
.agent-asset-dialog .asset-section--tinted { padding: 14px; border: 1px solid var(--el-border-color-light); border-radius: 12px; background: var(--el-fill-color-lighter); }
.agent-asset-dialog .asset-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.agent-asset-dialog .asset-advanced { margin-top: 20px; border-color: var(--el-border-color-lighter); }
.agent-asset-dialog .asset-advanced .el-collapse-item__header { background: transparent; font-weight: 600; }
.agent-asset-dialog .asset-advanced .el-collapse-item__title { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.agent-asset-dialog .asset-advanced .el-collapse-item__content { padding: 8px 0 0; }
.agent-asset-dialog .asset-summary { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; font-weight: 400; }
.agent-asset-dialog .asset-code textarea { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.75; }
.agent-asset-dialog .asset-enable, .agent-asset-dialog .asset-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.agent-asset-dialog .asset-enable { margin-top: 18px; }
.agent-asset-dialog .asset-enable strong { color: var(--el-text-color-regular); font-size: 13px; }
.agent-asset-dialog .asset-enable p { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.7; margin: 5px 0 0; }
.agent-asset-dialog .asset-footer > span { font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); }
@media (max-width: 640px) { .el-dialog.agent-asset-dialog { padding: 16px; } .agent-asset-dialog .asset-grid { grid-template-columns: 1fr; } .agent-asset-dialog .asset-section--tinted { padding: 10px; } }
</style>
