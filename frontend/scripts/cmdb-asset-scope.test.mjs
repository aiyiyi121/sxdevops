import test from 'node:test'
import assert from 'node:assert/strict'
import { buildCmdbAssetScopeTrees, indexAssetsByModel } from '../src/utils/cmdb-asset-scope.js'

const resources = {
  business: [{ id: 10, name: '业务 A', children: [{ id: 11, name: 'production' }, { id: 12, name: 'test' }, { id: 13, name: 'dev' }] }, { id: 20, name: '空业务', children: [] }],
  cloud: [{ id: 30, name: '账号 A', node_type: 'cloud_account', children: [{ id: 31, name: '地域 A', node_type: 'cloud_region', children: [{ id: 32, name: '集群 A', node_type: 'cloud_cluster', children: [{ id: 33, name: '宿主机 A', node_type: 'cloud_host' }] }] }] }],
}
const rows = [
  { id: 1, name: '生产应用', ci_type: 100, business_node: 10, business_node_name: '业务 A', environment_node: 11, environment: 'prod', resource_node: 33, attributes: { system: '系统 A' } },
  { id: 2, name: '测试存储', ci_type: 101, business_line: '业务 A', environment: 'testing', source_mappings: [{ source_account: '账号 A', source_region: '地域 A' }] },
  { id: 3, name: '未归属主机', ci_type: 102 },
]

test('business/environment scopes keep empty nodes and exact asset membership', () => {
  const tree = buildCmdbAssetScopeTrees(rows, resources).business
  const biz = tree.find(node => node.label === '业务 A')
  assert.deepEqual([...biz.rowIds], ['1', '2'])
  assert.equal(biz.count, 2)
  assert.deepEqual(biz.children.find(node => node.label === '生产环境').children[0].rowIds, new Set(['1']))
  assert.deepEqual(biz.children.find(node => node.label === '测试环境').rowIds, new Set(['2']))
  assert.equal(biz.children.find(node => node.label === '开发环境').count, 0)
  assert.equal(tree.find(node => node.label === '空业务').count, 0)
  assert.deepEqual(tree.find(node => node.label === '未归属业务线').rowIds, new Set(['3']))
})

test('cloud scopes include assets linked to descendants and legacy source mappings', () => {
  const [account] = buildCmdbAssetScopeTrees(rows, resources).cloud.filter(node => node.label === '账号 A')
  assert.deepEqual(account.rowIds, new Set(['1', '2']))
  const region = account.children[0]
  assert.deepEqual(region.rowIds, new Set(['1', '2']))
  assert.deepEqual(region.children[0].children[0].rowIds, new Set(['1']))
})

test('same-named business nodes are separated by stable node IDs', () => {
  const tree = buildCmdbAssetScopeTrees([{ id: 4, business_node: 42, business_node_name: '重复业务', environment_node: 43 }], { business: [
    { id: 40, name: '重复业务', children: [{ id: 41, name: 'prod' }] },
    { id: 42, name: '重复业务', children: [{ id: 43, name: 'prod' }] },
  ] }).business
  assert.equal(tree.length, 2)
  assert.equal(tree.filter(node => node.count === 1).length, 1)
  assert.notEqual(tree[0].key, tree[1].key)
})

test('vSphere metadata extends region nodes with cluster/host scopes', () => {
  const tree = buildCmdbAssetScopeTrees([{ id: 5, resource_node: 31, source_type: 'vsphere', attributes: { cluster: '集群 A', host: '宿主机 A' } }], resources).cloud
  assert.deepEqual(tree[0].children[0].children[0].children[0].rowIds, new Set(['5']))
})

test('empty authorized ledger does not reuse backend global resource counters', () => {
  const tree = buildCmdbAssetScopeTrees([], { business: [{ id: 1, name: '空业务', resource_count: 999, children: [] }] }).business
  assert.equal(tree[0].count, 0)
  assert.equal(tree[0].rowIds.size, 0)
})

test('canonical model aliases retain standalone assets while excluding hidden models', () => {
  const index = indexAssetsByModel([
    { id: 1, ci_type: 100 }, { id: 2, ci_type: 999, ci_type_code: 'OBJECT_STORAGE' },
    { id: 3, ci_type: 102 }, { id: 4, ci_type_name: '对象存储' },
  ], [{ id: 100, code: 'APP_SERVICE', name: '应用服务' }, { id: 101, code: 'OBJECT_STORAGE', name: '对象存储' }])
  assert.deepEqual([...index], [['1', '100'], ['2', '101'], ['4', '101']])
})
