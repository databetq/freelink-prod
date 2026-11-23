import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const backend = fileURLToPath(new URL('../backend/', import.meta.url))
const isWindows = process.platform === 'win32'
const venvPython = isWindows
  ? join(backend, '.venv', 'Scripts', 'python.exe')
  : join(backend, '.venv', 'bin', 'python')
const python = existsSync(venvPython) ? venvPython : isWindows ? 'python' : 'python3'
const result = spawnSync(python, ['-m', 'app.admin_accounts', ...process.argv.slice(2)], {
  cwd: backend,
  stdio: 'inherit',
})

if (result.error) console.error(result.error.message)
process.exitCode = result.status ?? 1
