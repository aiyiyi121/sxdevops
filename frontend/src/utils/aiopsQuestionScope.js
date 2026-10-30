const AUTO_CATEGORY = { value: 'auto', label: '自动识别', icon: 'MagicStick', description: '根据问题自动匹配问答能力', questions: [] }

const LEGACY_QUESTION_CATEGORIES = {
  incident: 'troubleshoot',
  monitoring: 'troubleshoot',
  'alert.root_cause': 'troubleshoot',
  'k8s.diagnose': 'troubleshoot',
  'self_heal.recommend': 'troubleshoot',
  operations: 'host_task.generate',
  deployment: 'event.analysis',
  'change.correlation': 'event.analysis',
  cost: 'cmdb',
}

export function normalizeQuestionCategory(value) {
  return LEGACY_QUESTION_CATEGORIES[value] || value || 'auto'
}

export function buildQuestionCategories(capabilities = []) {
  return [AUTO_CATEGORY, ...capabilities.filter(item => item.available !== false).map(item => ({
    value: item.code,
    label: item.display_name,
    icon: item.icon || 'MagicStick',
    summary: item.summary || '',
    description: item.description || '',
    requiresEnvironment: Boolean(item.requires_environment),
    questions: item.suggested_questions || [],
  }))]
}

export function getQuestionCategory(value, options = []) {
  return options.find(item => item.value === normalizeQuestionCategory(value)) || AUTO_CATEGORY
}
