// The classification view and topology use the same ledger and resource-node APIs.
// Derive membership from authorized ledger rows rather than global node counters.
const text = value => String(value ?? '').trim()
const environmentAliases = { 开发: 'dev', development: 'dev', 生产: 'prod', production: 'prod', 测试: 'test', testing: 'test', 联调: 'uat', 集成: 'integration' }
const environmentKey = value => environmentAliases[text(value).toLowerCase()] || text(value).toLowerCase()
const environmentLabel = value => ({ dev: '开发环境', prod: '生产环境', test: '测试环境', uat: '联调环境', staging: '预发布环境', integration: '集成环境' })[environmentKey(value)] || text(value) || '未归属环境'
const pathKey = parts => JSON.stringify(parts)

function field(row, keys) {
  const source = row.source_mappings?.[0] || {}
  return keys.map(key => text(source[key] ?? row[key] ?? row.attributes?.[key])).find(value => value && value !== '-') || ''
}

function ensureNode(siblings, key, label, level, parent = null, sort = 0) {
  if (!siblings.has(key)) siblings.set(key, { key, label, level, parent, sort, children: new Map(), rowIds: new Set(), search: new Set([label]) })
  return siblings.get(key)
}

function attachRow(node, row) {
  const search = [row.name, row.ci_type_name, row.ci_type_code].filter(Boolean).join(' ')
  for (let current = node; current; current = current.parent) {
    current.rowIds.add(text(row.id))
    current.search.add(search)
  }
}

function toTree(nodes, path = []) {
  return [...nodes.values()]
    .sort((a, b) => a.sort - b.sort || b.rowIds.size - a.rowIds.size || a.label.localeCompare(b.label, 'zh-Hans-CN'))
    .map(node => ({
      key: node.key, label: node.label, level: node.level,
      rowIds: node.rowIds, count: node.rowIds.size,
      path: [...path, node.label].join(' / '),
      searchText: [...node.search].join(' ').toLowerCase(),
      children: toTree(node.children, [...path, node.label]),
    }))
}

export function buildCmdbAssetScopeTrees(rows, resourceTrees = {}) {
  const business = new Map()
  const cloud = new Map()
  const businessById = new Map()
  const cloudById = new Map()

  for (const biz of resourceTrees.business || []) {
    const parent = ensureNode(business, pathKey(['business', biz.id]), biz.name, 'business', null, Number(biz.sort_order || 0))
    businessById.set(text(biz.id), parent)
    for (const env of biz.children || []) {
      const node = ensureNode(parent.children, pathKey([parent.key, 'environment', env.id]), environmentLabel(env.name), 'environment', parent, Number(env.sort_order || 0))
      node.environment = environmentKey(env.name)
      businessById.set(text(env.id), node)
    }
  }

  function seedCloud(nodes, parent = null) {
    for (const item of nodes || []) {
      const level = { cloud_account: 'account', cloud_region: 'region', cloud_cluster: 'cluster', cloud_host: 'host' }[item.node_type]
      if (!level) continue
      const node = ensureNode(parent ? parent.children : cloud, pathKey(['cloud', item.id]), item.name, level, parent, Number(item.sort_order || 0))
      cloudById.set(text(item.id), node)
      seedCloud(item.children, node)
    }
  }
  seedCloud(resourceTrees.cloud)

  for (const row of rows) {
    const attrs = row.attributes || {}
    const businessName = text(row.business_node_name || row.business_line || attrs.business_line || attrs.biz || attrs.biz_line || attrs.business_line_name || attrs.app_group) || '未归属业务线'
    let biz = businessById.get(text(row.business_node))
    if (!biz) biz = [...business.values()].find(node => node.label === businessName)
    if (!biz) biz = ensureNode(business, pathKey(['business', businessName]), businessName, 'business')
    const envKey = businessName === '未归属业务线' ? '' : environmentKey(row.environment_node_name || row.environment || attrs.environment || attrs.env)
    let env = businessById.get(text(row.environment_node))
    if (env?.parent !== biz) env = null
    if (!env) env = [...biz.children.values()].find(node => node.environment === envKey)
    if (!env) {
      env = ensureNode(biz.children, pathKey([biz.key, 'environment', envKey]), environmentLabel(envKey), 'environment', biz)
      env.environment = envKey
    }
    const system = text(attrs.system || attrs.business_system || attrs.app_name || attrs.application || attrs.service_name)
    const businessLeaf = system ? ensureNode(env.children, pathKey([env.key, 'system', system]), system, 'system', env) : env
    attachRow(businessLeaf, row)

    let cloudLeaf = cloudById.get(text(row.resource_node || row.resource_node_id || attrs.resource_node_id))
    const sourceType = text(row.source_label || row.source_type || row.source_mappings?.[0]?.source_type || attrs.source_type || attrs.source || 'manual')
    const provider = text(attrs.provider || attrs.cloud_provider || attrs.provider_name || sourceType)
    const account = field(row, ['source_account', 'cloud_account', 'account_name', 'account', 'account_id'])
      || (['manual', 'manual_import'].includes(sourceType.toLowerCase()) ? '手工录入 / 未关联账号' : `未关联账号 / ${sourceType}`)
    const region = field(row, ['source_region', 'cloud_region', 'region', 'region_id'])
    if (!cloudLeaf) {
      cloudLeaf = [...cloud.values()].find(node => node.label === account)
        || ensureNode(cloud, pathKey(['account', account]), account, 'account')
      if (region) cloudLeaf = [...cloudLeaf.children.values()].find(node => node.label === region)
        || ensureNode(cloudLeaf.children, pathKey([cloudLeaf.key, 'region', region]), region, 'region', cloudLeaf)
    }
    // Imported vSphere resources may carry a cluster/host before nodes are synced.
    if (/vsphere/i.test(`${sourceType} ${provider}`) && ['account', 'region'].includes(cloudLeaf.level)) {
      const cluster = text(attrs.cluster || attrs.vsphere_cluster)
      if (cluster && !['vm', 'host', 'hosts'].includes(cluster.toLowerCase())) {
        cloudLeaf = [...cloudLeaf.children.values()].find(node => node.label === cluster)
          || ensureNode(cloudLeaf.children, pathKey([cloudLeaf.key, 'cluster', cluster]), cluster, 'cluster', cloudLeaf)
      }
      const host = text(attrs.host || attrs.host_name || attrs.esxi_host)
      if (host) cloudLeaf = [...cloudLeaf.children.values()].find(node => node.label === host)
        || ensureNode(cloudLeaf.children, pathKey([cloudLeaf.key, 'host', host]), host, 'host', cloudLeaf)
    }
    attachRow(cloudLeaf, row)
  }
  return { business: toTree(business), cloud: toTree(cloud) }
}

export function indexAssetsByModel(rows, models) {
  const aliases = new Map()
  for (const model of models) {
    for (const key of [model.id, model.code, model.name].map(text).filter(Boolean)) aliases.set(key, text(model.id))
  }
  const result = new Map()
  for (const row of rows) {
    const attrs = row.attributes || {}
    const keys = [row.ci_type, row.ci_type_id, row.ci_type_code, row.ci_type_name, attrs.ci_type, attrs.ci_type_id, attrs.ci_type_code, attrs.ci_type_name]
    const id = keys.map(key => aliases.get(text(key))).find(Boolean)
    if (id) result.set(text(row.id), id)
  }
  return result
}
