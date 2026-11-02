import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { brotliCompressSync, constants, gzipSync } from 'node:zlib'

async function compressDirectory(directory) {
    let count = 0
    for (const entry of await readdir(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name)
        if (entry.isDirectory()) {
            count += await compressDirectory(path)
        } else if (/\.(?:html|js|css|svg|json|txt)$/.test(entry.name)) {
            const source = await readFile(path)
            if (source.length < 1024 && !entry.name.endsWith('.html')) continue
            const variants = [
                ['gz', gzipSync(source, { level: 9 })],
                ['br', brotliCompressSync(source, {
                    params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
                })],
            ]
            for (const [encoding, compressed] of variants) {
                if (compressed.length >= source.length) continue
                await writeFile(`${path}.${encoding}`, compressed)
                count += 1
            }
        }
    }
    return count
}

const count = await compressDirectory(fileURLToPath(new URL('../dist/', import.meta.url)))
console.log(`Generated ${count} Gzip/Brotli static variants`)
