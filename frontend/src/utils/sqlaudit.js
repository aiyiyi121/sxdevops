export const SQL_AUDIT_SUPPORT_TEXT = '支持 MySQL、PostgreSQL、MongoDB'

export const DATASOURCE_TYPE_OPTIONS = [
  { value: 'mysql', label: 'MySQL', defaultPort: 3306 },
  { value: 'mongodb', label: 'MongoDB', defaultPort: 27017 },
  { value: 'postgresql', label: 'PostgreSQL', defaultPort: 5432 },
]

export const DATASOURCE_TYPE_LABELS = DATASOURCE_TYPE_OPTIONS.reduce((result, item) => {
  result[item.value] = item.label
  return result
}, {})

export const DATASOURCE_DEFAULT_PORTS = DATASOURCE_TYPE_OPTIONS.reduce((result, item) => {
  result[item.value] = item.defaultPort
  return result
}, {})

export const MONGODB_QUERY_SAMPLE = 'find {"collection":"orders","filter":{"status":"running"},"limit":50}'
export const MONGODB_WRITE_SAMPLE = 'updateMany {"collection":"orders","filter":{"status":"new"},"update":{"$set":{"status":"done"}}}'

export function getDatasourceTypeLabel(type) {
  const normalized = String(type || 'mysql').trim().toLowerCase()
  return DATASOURCE_TYPE_LABELS[normalized] || DATASOURCE_TYPE_LABELS.mysql
}

export function getDatasourceDefaultPort(type) {
  return DATASOURCE_DEFAULT_PORTS[type] || 3306
}

export function getQueryPlaceholder(type) {
  if (type === 'mongodb') {
    return `输入 MongoDB 查询命令，例如：${MONGODB_QUERY_SAMPLE}`
  }
  if (type === 'postgresql') {
    return '输入 SELECT / WITH / SHOW 只读查询语句...'
  }
  return '输入 SELECT / SHOW / DESC 查询语句...'
}

export function getOrderPlaceholder(type) {
  if (type === 'mongodb') {
    return `输入 MongoDB 变更命令，例如：${MONGODB_WRITE_SAMPLE}`
  }
  return '输入 SQL 语句，多条语句以分号分隔...'
}

export function getOrderHint(type) {
  if (type === 'mongodb') {
    return 'MongoDB 支持 insertOne / insertMany / updateOne / updateMany / deleteOne / deleteMany / createCollection / dropCollection / createIndex / dropIndex'
  }
  if (type === 'postgresql') {
    return 'PostgreSQL 支持 DML、DDL 与 dollar quote 语句；工单统一提交，失败自动回滚，不支持 CREATE DATABASE / VACUUM / CREATE INDEX CONCURRENTLY 等事务外操作'
  }
  return 'MySQL 支持常见 DML、DDL 语句'
}
