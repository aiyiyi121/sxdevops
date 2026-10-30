const fs = require('fs')
const path = require('path')

const puppeteer = require(path.resolve(__dirname, '../.runlogs/screenshot-tools/node_modules/puppeteer-core'))

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, 'docs', 'screenshots')
const promoOutDir = path.join(root, 'frontend', 'public', 'promo', 'screenshots')
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const baseUrl = 'http://localhost:3000'
const apiUrl = 'http://localhost:8000/api/auth/login/'

async function login() {
  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'ops_demo', password: 'Admin@123456' }),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Login failed: ${response.status} ${text}`)
  }
  return response.json()
}

async function waitForPage(page, expectedText) {
  await page.waitForFunction(
    text => document.body && document.body.innerText.includes(text),
    { timeout: 30000 },
    expectedText,
  )
  await page.waitForNetworkIdle({ idleTime: 900, timeout: 30000 }).catch(() => {})
  await new Promise(resolve => setTimeout(resolve, 1200))
  await page.evaluate(() => {
    window.scrollTo(0, 0)
    document.querySelectorAll('.el-message, .el-notification, .el-overlay').forEach(node => node.remove())
  })
}

async function capture(page, route, expectedText, fileName) {
  const target = `${baseUrl}${route}`
  await page.goto(target, { waitUntil: 'domcontentloaded' })
  await waitForPage(page, expectedText)
  const outputPath = path.join(outDir, fileName)
  await page.screenshot({
    path: outputPath,
    fullPage: false,
  })
  fs.mkdirSync(promoOutDir, { recursive: true })
  fs.copyFileSync(outputPath, path.join(promoOutDir, fileName))
  console.log(`${fileName} <- ${target}`)
}

async function main() {
  if (!fs.existsSync(edgePath)) {
    throw new Error(`Microsoft Edge not found at ${edgePath}`)
  }
  fs.mkdirSync(outDir, { recursive: true })
  fs.mkdirSync(promoOutDir, { recursive: true })

  const auth = await login()
  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 1 },
  })

  try {
    const page = await browser.newPage()
    await page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded' })
    await page.evaluate(({ token, user }) => {
      localStorage.setItem('sxdevops_token', token)
      localStorage.setItem('sxdevops_user', JSON.stringify(user))
    }, auth)

    await capture(page, '/dashboard', '系统SLA统计', 'dashboard.png')
    await capture(page, '/observability/overview', '平台总览', 'ai-agent-observability-overview.png')
    await capture(page, '/events/wall', '事件中心', 'ai-agent-event-center-current.png')
  } finally {
    await browser.close()
  }
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
