import assert from 'node:assert/strict'
import test from 'node:test'
import { safeGrafanaUrl, safeHttpUrl, safeInternalPath } from '../src/utils/safe-url.js'

const origin = 'https://platform.example'

test('embedded links reject executable schemes, credentials and ambiguous paths', () => {
  for (const value of [
    'javascript:alert(1)', 'data:text/html,test', 'vbscript:msgbox(1)', 'blob:https://platform.example/id',
    '//untrusted.example/d/test', '/\\untrusted.example', '/%2funtrusted.example', '/%5cuntrusted.example',
    '/%0atest', '/%zz', 'https://name:secret@grafana.example/d/test',
    'https://grafana.example\n/d/test', 'https:untrusted.example', 'not-a-url', {}, null,
  ]) assert.equal(safeHttpUrl(value, origin), '', String(value))
})

test('valid dashboards preserve query parameters and site proxy paths', () => {
  assert.equal(safeHttpUrl('/grafana/d/nodes?var-env=demo&from=now-1h', origin), `${origin}/grafana/d/nodes?var-env=demo&from=now-1h`)
  assert.equal(safeHttpUrl('http://grafana.internal:3000/d/nodes', origin), 'http://grafana.internal:3000/d/nodes')
  assert.equal(safeHttpUrl('https://grafana.example/d/nodes', origin), 'https://grafana.example/d/nodes')
})

test('login return targets remain inside the application', () => {
  assert.equal(safeInternalPath('/observability/grafana?dashboard=nodes&folder=%E8%8A%82%E7%82%B9'), '/observability/grafana?dashboard=nodes&folder=%E8%8A%82%E7%82%B9')
  for (const value of ['https://untrusted.example/', '//untrusted.example/', '/%2Funtrusted.example', '/\\untrusted.example', '/%5cuntrusted.example']) {
    assert.equal(safeInternalPath(value), '')
  }
})

test('Grafana keeps the HTTPS proxy for relative and internal HTTP dashboards', () => {
  for (const value of ['/d/nodes?var-env=demo#panel', 'http://grafana.internal:3000/d/nodes?var-env=demo#panel']) {
    assert.equal(safeGrafanaUrl(value, origin), `${origin}/grafana/d/nodes?var-env=demo#panel`)
  }
  assert.equal(safeGrafanaUrl('/grafana/d/nodes', origin), `${origin}/grafana/d/nodes`)
  assert.equal(safeGrafanaUrl('http://untrusted.example/login', origin), '')
  assert.equal(safeGrafanaUrl('javascript:alert(1)', origin), '')
  assert.equal(safeGrafanaUrl('http://grafana.internal:3000/d/nodes', 'http://localhost:3000'), 'http://grafana.internal:3000/d/nodes')
})
