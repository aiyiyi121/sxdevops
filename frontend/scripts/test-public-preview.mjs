import assert from 'node:assert/strict'
import test from 'node:test'
import { ElMessage } from 'element-plus'
import request from '../src/api/request.js'

const storage = new Map()
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, removeItem: key => storage.delete(key) }
globalThis.window = { location: { origin: 'https://preview.example.test', pathname: '/dashboard' } }
let sent = []
// Exercise the actual Axios interceptors without mounting browser notifications.
ElMessage.error = () => ({ close() {} })
request.defaults.adapter = async (config) => {
  sent.push(config)
  return { status: 200, statusText: 'OK', data: { success: true }, headers: {}, config }
}

function setPreview(enabled) {
  storage.set('sxdevops_user', JSON.stringify({ is_preview: enabled }))
  sent = []
}

test('preview final actions never reach the HTTP adapter', async () => {
  setPreview(true)
  for (const [method, url] of [
    ['post', '/hosts/'], ['patch', '/users/7/'], ['delete', '/hosts/4/'],
    ['put', '/module-settings/'], ['post', '/k8s/clusters/1/kubectl/'],
    ['post', '/aiops/sessions/'], ['post', '/future-action/'],
  ]) {
    await assert.rejects(request({ method, url }), error => error.code === 'PREVIEW_READ_ONLY')
  }
  assert.equal(sent.length, 0)
})

test('observation queries and login/logout still reach the HTTP adapter', async () => {
  setPreview(true)
  for (const url of [
    '/auth/login/', '/auth/logout/', '/log/query/', '/log/providers/loki/catalog/',
    '/observability/metrics/query/', '/observability/grafana/panel/query/',
    '/observability/tracing/search/', '/observability/datasource-links/resolve_trace_to_logs/',
  ]) await request.post(url, {})
  assert.equal(sent.length, 8)
})

test('preview GET requests remain available', async () => {
  setPreview(true)
  await request.get('/users/')
  await request.get('/host-tasks/')
  assert.equal(sent.length, 2)
})

test('history rebuild GET requests are stopped before the HTTP adapter', async () => {
  setPreview(true)
  const path = '/observability/system-posture/history/'
  await assert.rejects(request.get(path, { params: { refresh: 1 } }), error => error.code === 'PREVIEW_READ_ONLY')
  await assert.rejects(request.get(path + '?backfill=yes'), error => error.code === 'PREVIEW_READ_ONLY')
  assert.equal(sent.length, 0)
  await request.get(path, { params: { refresh: 0, days: 90 } })
  assert.equal(sent.length, 1)
})

test('normal users retain write requests', async () => {
  setPreview(false)
  await request.post('/hosts/', {})
  await request.patch('/users/7/', {})
  assert.equal(sent.length, 2)
})

test('API-prefixed absolute paths cannot bypass final-action blocking', async () => {
  setPreview(true)
  await assert.rejects(request.post('/api/hosts/', {}), error => error.code === 'PREVIEW_READ_ONLY')
  await assert.rejects(request.post('https://preview.example.test/api/hosts/', {}), error => error.code === 'PREVIEW_READ_ONLY')
  assert.equal(sent.length, 0)
})
