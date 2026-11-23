// ตัวช่วยของ scripts/flow_trace.py — รันโค้ด frontend จริง (src/services/**) ผ่าน Vite SSR โดยไม่เปิดเบราว์เซอร์
//
//   node scripts/flow_trace_frontend.mjs probe          พิมพ์ JSON: config ที่เบราว์เซอร์จะใช้ + ทุก request ที่ service layer ส่งไป backend
//   echo '{"termsJson":"..."}' | node scripts/flow_trace_frontend.mjs hash
//                                                       พิมพ์ JSON: ผล hashTerms() ตัวจริงของ frontend (ethers keccak256)
//
// ไม่แตะเครือข่าย: axios ถูกสลับ adapter เป็นตัวบันทึก request จึงไม่มีอะไรถูกส่งออกจริง
import { createServer } from 'vite'
import path from 'node:path'
import { readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const command = process.argv[2]

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  return Buffer.concat(chunks).toString('utf8')
}

const server = await createServer({
  root,
  appType: 'custom',
  logLevel: 'error',
  server: { middlewareMode: true, hmr: false, watch: null, ws: false },
})
const load = (file) => server.ssrLoadModule(file)

function bodyKeys(data) {
  if (typeof data !== 'string') return null
  try {
    const parsed = JSON.parse(data)
    return parsed && typeof parsed === 'object' ? Object.keys(parsed) : null
  } catch {
    return null
  }
}

/** ค่าที่แปลงเป็น string ได้ `text` และตอบ `{id}` ให้ทุก property (payload.jobId, thread.id, ...) */
function placeholder(text) {
  const target = () => text
  return new Proxy(target, {
    get(_, prop) {
      if (prop === Symbol.toPrimitive || prop === 'toString' || prop === 'toJSON' || prop === 'valueOf') return target
      if (typeof prop === 'symbol' || prop === 'then') return undefined
      return '{id}'
    },
  })
}

async function attempt(fn, args) {
  try {
    await Promise.race([fn(...args), new Promise((resolve) => setTimeout(resolve, 2000))])
    return null
  } catch (err) {
    return String(err?.message || err).slice(0, 120)
  }
}

async function probe() {
  const { appConfig } = await load('/src/config/appConfig.js')
  const { contractConfig } = await load('/src/config/contractConfig.js')
  const { apiClient } = await load('/src/services/api/apiClient.js')

  const seen = []
  apiClient.defaults.adapter = async (config) => {
    seen.push({
      http: String(config.method || 'get').toUpperCase(),
      path: String(config.url || '').split('?')[0],
      bodyKeys: bodyKeys(config.data),
    })
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
  }

  const dir = path.join(root, 'src/services/api')
  const calls = []
  for (const file of readdirSync(dir).filter((name) => name.endsWith('.js') && name !== 'apiClient.js' && name !== 'endpoints.js')) {
    const mod = await load(`/src/services/api/${file}`)
    for (const [exportName, service] of Object.entries(mod)) {
      if (!service || typeof service !== 'object') continue
      for (const [method, fn] of Object.entries(service)) {
        if (typeof fn !== 'function') continue
        // รอบแรกส่ง string placeholder ที่ตำแหน่ง id ทำให้ path ออกมาเป็น /projects/{id1}/escrow ตรงรูปแบบ OpenAPI
        // ถ้าเมธอดรับ object แล้วอ่าน payload.jobId จะได้ "undefined" ในรอบแรก → ลองใหม่ด้วย Proxy ที่ตอบทุก property
        let before = seen.length
        let error = await attempt(fn, ['{id1}', '{id2}', '{id3}'])
        if (seen.slice(before).some((request) => /undefined|\[object/.test(request.path))) {
          before = seen.length
          error = await attempt(fn, [placeholder('{id1}'), placeholder('{id2}'), placeholder('{id3}')])
        }
        calls.push({ service: `${exportName}.${method}`, file, requests: seen.slice(before), error })
      }
    }
  }

  return {
    config: {
      apiBaseUrl: appConfig.apiBaseUrl,
      chainId: contractConfig.chainId,
      contractAddress: contractConfig.contractAddress,
      explorerUrl: contractConfig.explorerUrl,
      abiEntries: contractConfig.abi.length,
    },
    calls,
  }
}

async function hash() {
  const { termsJson } = JSON.parse(await readStdin())
  const contract = await load('/src/services/blockchain/contractService.js')
  return { hash: contract.hashTerms(termsJson) }
}

try {
  const result = command === 'probe' ? await probe() : command === 'hash' ? await hash() : null
  if (result === null) throw new Error('usage: flow_trace_frontend.mjs probe|hash')
  process.stdout.write(JSON.stringify(result))
} catch (error) {
  process.stderr.write(String(error?.stack || error))
  process.exitCode = 1
} finally {
  await server.close()
}
