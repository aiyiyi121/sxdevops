export const productSections = [
  { id: 'capabilities', label: '产品能力', navigation: true },
  { id: 'principles', label: '设计理念', navigation: true },
  { id: 'workflow', label: '运维闭环' },
  { id: 'troubleshooting', label: '排障路径', navigation: true },
  { id: 'modules', label: '模块详解' },
  { id: 'architecture', label: '平台架构', navigation: true },
  { id: 'aiops', label: 'AIOps 原理', navigation: true },
  { id: 'verification', label: '效果验证' },
  { id: 'screenshots', label: '界面一览', navigation: true },
  { id: 'start', label: '快速部署', navigation: true },
  { id: 'resources', label: '更多文档', navigation: true },
]

export function sectionLabel(id) {
  const index = productSections.findIndex(section => section.id === id)
  return `${String(index + 1).padStart(2, '0')} / ${productSections[index].label}`
}
