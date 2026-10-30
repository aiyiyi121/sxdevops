import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const lock = JSON.parse(readFileSync(resolve(root, 'package-lock.json'), 'utf8'))
const notices = ['SXDevOps frontend third-party notices', 'Generated from the installed production dependency tree. Each component retains its own license.']
// Exact-version supplements for packages whose npm tarballs omit license files.
const supplements = {
  'lodash-unified@1.0.3': 'lodash-unified-1.0.3.txt',
  '@vue/devtools-api@6.6.4': 'vue-devtools-api-6.6.4.txt',
}
let count = 0
for (const [path, entry] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b))) {
  if (!path || entry.dev) continue
  const folder = resolve(root, path)
  let pkg
  try {
    pkg = JSON.parse(readFileSync(resolve(folder, 'package.json'), 'utf8'))
  } catch (error) {
    if (entry.optional && error.code === 'ENOENT') continue
    throw error
  }
  const files = readdirSync(folder, { withFileTypes: true }).filter(item => item.isFile() && /^(license|copying|notice)/i.test(item.name))
  const supplement = supplements[`${pkg.name}@${pkg.version}`]
  if (!pkg.license || (!files.length && !supplement)) throw new Error(`Missing license metadata or notices: ${pkg.name}@${pkg.version}`)
  notices.push(`\n${'='.repeat(72)}\n${pkg.name}@${pkg.version}\nLicense: ${typeof pkg.license === 'string' ? pkg.license : JSON.stringify(pkg.license)}`)
  for (const file of files) notices.push(`\n--- ${file.name} ---\n${readFileSync(resolve(folder, file.name), 'utf8')}`)
  if (supplement) notices.push(readFileSync(resolve(root, 'licenses', supplement), 'utf8'))
  count++
}
const destination = resolve(root, 'public/assets/third-party-notices.txt')
mkdirSync(dirname(destination), { recursive: true })
writeFileSync(destination, notices.join('\n') + '\n', 'utf8')
console.log(`Preserved license notices for ${count} production packages.`)
