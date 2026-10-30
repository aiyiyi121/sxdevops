<template>
  <div class="strategy-panel">
    <div class="section-toolbar">
      <div class="toolbar-head"><span class="toolbar-title">智能体策略</span><span class="toolbar-desc">配置对话体验、能力范围与运行方式</span></div>
      <div class="strategy-actions"><span class="save-state" :class="{ 'is-dirty': dirty }">{{ dirty ? '有未保存的修改' : '配置已同步' }}</span><el-button v-if="dirty && canManage" size="small" :disabled="saving" @click="$emit('reset')">撤销修改</el-button><el-button v-if="canManage" size="small" type="primary" :loading="saving" :disabled="!dirty || loading" @click="$emit('save')">保存策略</el-button></div>
    </div>
    <div class="strategy-grid">
      <div class="strategy-main">
        <section class="strategy-card">
          <div class="strategy-card-heading"><span class="strategy-card-icon"><el-icon><ChatDotSquare /></el-icon></span><h3>对话体验</h3><span>用户打开助手时看到的内容</span></div>
          <el-form :model="config" label-position="top" :disabled="!canManage || loading || saving" @submit.prevent>
            <el-form-item label="欢迎语"><el-input v-model="config.welcome_message" placeholder="用一句话介绍助手能帮用户做什么" maxlength="255" show-word-limit /></el-form-item>
            <el-form-item class="question-form-item">
              <template #label><div class="field-heading"><span>建议问题</span><small>{{ config.suggested_questions.length }} 个</small></div></template>
              <div class="suggestion-editor">
                <div class="question-list">
                <div v-for="(question, index) in config.suggested_questions" :key="index" class="suggestion-row"><span class="question-number">{{ String(index + 1).padStart(2, '0') }}</span><span class="question-text">{{ question }}</span><el-button text circle :icon="Close" :aria-label="`移除建议问题 ${index + 1}`" @click="config.suggested_questions.splice(index, 1)" /></div>
                <div v-if="!config.suggested_questions.length" class="suggestions-empty">尚未配置建议问题，添加后会展示在助手首页。</div>
                </div>
                <div class="question-add"><el-input v-model="questionDraft" placeholder="输入用户常问的问题，按 Enter 添加" aria-label="新增建议问题" @keydown.enter.prevent="addQuestion" /><el-button :disabled="!questionDraft.trim()" @click="addQuestion">添加</el-button></div>
              </div>
            </el-form-item>
            <el-form-item label="系统提示语" class="prompt-form-item"><el-input v-model="config.system_prompt" type="textarea" :rows="6" resize="vertical" placeholder="定义助手的角色、回答方式及处理边界…" /><div class="field-hint">作用于每次对话，建议明确角色、回答要求与操作边界。</div></el-form-item>
          </el-form>
        </section>
        <section class="strategy-card">
          <div class="strategy-card-heading"><span class="strategy-card-icon"><el-icon><Connection /></el-icon></span><h3>能力范围</h3><span>选择助手可处理的问答类型</span></div>
          <div class="scope-toolbar"><span>已选择 {{ config.enabled_capability_codes.length }} / {{ capabilities.length }} 类</span><div><el-button link type="primary" :disabled="!canManage || loading || saving || config.enabled_capability_codes.length === capabilities.length" @click="config.enabled_capability_codes = capabilities.map(item => item.code)">全选</el-button><el-button link :disabled="!canManage || loading || saving || !config.enabled_capability_codes.length" @click="config.enabled_capability_codes = []">清空</el-button></div></div>
          <el-checkbox-group v-model="config.enabled_capability_codes" class="question-scope-grid" :disabled="!canManage || loading || saving" aria-label="启用的问答类型">
            <el-checkbox v-for="item in capabilities" :key="item.code" :value="item.code" class="question-scope" :class="{ 'is-selected': config.enabled_capability_codes.includes(item.code) }"><strong>{{ item.display_name }}</strong><span>{{ item.description || item.summary }}</span></el-checkbox>
          </el-checkbox-group>
          <div class="field-hint" :class="{ 'scope-empty': !config.enabled_capability_codes.length }">{{ config.enabled_capability_codes.length ? '仅开放选中的问答类型，实际使用仍受账号权限约束。MCP 和 Skill 的启停请在各自页面管理。' : '尚未选择问答类型；保存后助手将暂停处理问答。' }}</div>
        </section>
      </div>
      <aside class="strategy-side">
        <section class="strategy-card runtime-card">
          <div class="strategy-card-heading"><span class="strategy-card-icon"><el-icon><Setting /></el-icon></span><h3>运行设置</h3></div>
          <div class="runtime-switch"><div><strong>启用智能助手</strong><p>关闭后聊天入口不可用，已有会话保留。</p></div><el-switch v-model="config.is_enabled" :disabled="!canManage || loading || saving" aria-label="启用智能助手" /></div>
          <div class="runtime-switch"><div><strong>生成待执行任务</strong><p>关闭后仅提供分析结果，不创建待确认任务。</p></div><el-switch v-model="config.allow_action_execution" :disabled="!canManage || loading || saving" aria-label="生成待执行任务" /></div>
          <div class="confirmation-note"><el-icon><CircleCheck /></el-icon><span>操作执行前始终需要人工确认</span></div>
          <div class="history-setting"><div class="field-heading"><label for="agent-history-count">上下文消息数</label><el-input-number id="agent-history-count" v-model="config.max_history_messages" :min="4" :max="40" size="small" controls-position="right" :disabled="!canManage || loading || saving" /></div><p>携带最近几条用户与助手消息。数量越大，上下文越完整，Token 消耗也越多；不影响历史记录展示。</p></div>
        </section>
        <section class="strategy-card current-model-card">
          <div class="strategy-card-heading"><span class="strategy-card-icon"><el-icon><Cpu /></el-icon></span><h3>当前默认模型</h3><el-tag size="small" :type="provider?.runtime_ready ? 'success' : 'warning'">{{ provider?.runtime_ready ? '已就绪' : '待配置' }}</el-tag></div>
          <strong class="current-model-name">{{ provider?.default_model || '尚未配置模型' }}</strong><span class="current-provider-name">{{ provider?.name || '请先添加模型提供商' }}</span>
          <el-button link type="primary" @click="$emit('providers')">管理模型提供商 <el-icon><ArrowRight /></el-icon></el-button>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ArrowRight, ChatDotSquare, CircleCheck, Close, Connection, Cpu, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
const props = defineProps({
  config: { type: Object, required: true }, capabilities: { type: Array, default: () => [] },
  provider: { type: Object, default: null }, dirty: Boolean, saving: Boolean, loading: Boolean, canManage: Boolean,
})
defineEmits(['save', 'reset', 'providers'])
const questionDraft = ref('')
function addQuestion() {
  if (!props.canManage || props.loading || props.saving) return
  const value = questionDraft.value.trim()
  if (!value) return
  if (props.config.suggested_questions.includes(value)) { ElMessage.info('这个问题已经添加过了'); return }
  props.config.suggested_questions.push(value)
  questionDraft.value = ''
}
</script>

<style scoped>
.section-toolbar, .toolbar-head, .strategy-actions { display: flex; align-items: center; flex-wrap: wrap; }
.section-toolbar { justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.toolbar-head { gap: 10px; }
.toolbar-title { color: var(--el-text-color-primary); font-size: 14px; font-weight: 700; }
.toolbar-desc, .save-state { font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); }
.strategy-actions { gap: 8px; }
.strategy-actions .el-button + .el-button { margin-left: 0; }
.save-state.is-dirty { color: var(--el-color-warning); }
.strategy-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; align-items: start; gap: 12px; }
.strategy-main, .strategy-side { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.strategy-card { border: 1px solid var(--el-border-color-light); border-radius: 14px; padding: 16px; background: var(--el-bg-color); }
.strategy-card-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 16px; }
.strategy-card-heading h3 { margin: 0; font-size: 14px; color: var(--el-text-color-primary); }
.strategy-card-heading > span:last-child:not(.strategy-card-icon) { font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); }
.strategy-card-heading .el-tag { margin-left: auto; }
.strategy-card-icon { display: grid; place-items: center; width: 28px; height: 28px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); border-radius: 8px; }
.strategy-card :deep(.el-form-item) { margin-bottom: 16px; }
.strategy-card :deep(.el-form-item__label) { width: 100%; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); margin-bottom: 6px; line-height: 20px; height: auto; }
.field-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; color: var(--el-text-color-regular); font-size: 12px; font-weight: 600; }
.field-heading small { font-size: 11px; font-weight: 400; color: var(--text-secondary, var(--el-text-color-secondary)); }
.suggestion-editor { width: 100%; border: 1px solid var(--el-border-color-light); border-radius: 10px; padding: 4px 10px 10px; background: var(--el-fill-color-lighter); }
.question-list { max-height: 180px; overflow-y: auto; }
.suggestion-row { display: flex; align-items: center; gap: 8px; min-height: 36px; border-bottom: 1px solid var(--el-border-color-lighter); }
.question-number { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 11px; font-variant-numeric: tabular-nums; }
.question-text { flex: 1; font-size: 12px; line-height: 1.6; color: var(--el-text-color-regular); overflow-wrap: anywhere; }
.suggestion-row .el-button { flex-shrink: 0; width: 24px; height: 24px; }
.question-add { display: flex; gap: 8px; margin-top: 8px; }
.suggestions-empty { font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); padding: 10px 0 4px; line-height: 1.6; }
.field-hint { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.7; margin-top: 6px; }
.prompt-form-item { margin-bottom: 0 !important; }
.scope-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; }
.question-scope-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.question-scope { display: flex; align-items: flex-start; height: auto; white-space: normal; margin: 0; padding: 12px; border: 1px solid var(--el-border-color-light); border-radius: 10px; background: var(--el-fill-color-lighter); }
.question-scope.is-selected { border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); }
.question-scope :deep(.el-checkbox__input) { margin-top: 3px; }
.question-scope :deep(.el-checkbox__label) { min-width: 0; padding-left: 9px; }
.question-scope strong { display: block; font-size: 13px; line-height: 20px; color: var(--el-text-color-primary); }
.question-scope span { display: block; margin-top: 4px; font-size: 12px; line-height: 1.7; color: var(--text-secondary, var(--el-text-color-secondary)); }
.scope-empty { color: var(--el-color-warning); }
.runtime-switch { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding-bottom: 16px; }
.runtime-switch strong { color: var(--el-text-color-regular); font-size: 13px; }
.runtime-switch p, .history-setting p { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.7; margin: 5px 0 0; }
.runtime-switch .el-switch { flex-shrink: 0; height: 24px; }
.confirmation-note { display: flex; align-items: center; gap: 6px; font-size: 12px; line-height: 1.6; color: var(--el-color-success); padding: 9px 10px; border-radius: 8px; background: var(--el-color-success-light-9); }
.history-setting { border-top: 1px solid var(--el-border-color-lighter); margin-top: 16px; padding-top: 16px; }
.history-setting .el-input-number { width: 96px; }
.current-model-name { display: block; font-size: 14px; line-height: 1.5; color: var(--el-text-color-primary); overflow-wrap: anywhere; }
.current-provider-name { display: block; font-size: 12px; color: var(--text-secondary, var(--el-text-color-secondary)); margin: 6px 0 14px; }
.current-model-card .el-button { font-size: 12px; }
@media (max-width: 1100px) { .strategy-grid { grid-template-columns: minmax(0, 1fr) 290px; } .question-scope-grid { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .strategy-grid { grid-template-columns: 1fr; } .strategy-side { display: grid; grid-template-columns: 1fr 1fr; align-items: start; } }
@media (max-width: 600px) { .strategy-side { display: flex; } .strategy-card { padding: 12px; } .strategy-card-heading > span:last-child:not(.strategy-card-icon) { flex-basis: 100%; } }
</style>
