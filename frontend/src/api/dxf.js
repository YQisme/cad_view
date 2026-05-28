const API_BASE = '/api'

export async function fetchDxfData(file = 'Drawing1.dxf') {
  const res = await fetch(`${API_BASE}/dxf/parse?file=${encodeURIComponent(file)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `加载失败 (${res.status})`)
  }
  return res.json()
}

export async function fetchFileList() {
  const res = await fetch(`${API_BASE}/files?_=${Date.now()}`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  })
  if (!res.ok) throw new Error('无法获取文件列表')
  return res.json()
}

export async function fetchConverterStatus() {
  const res = await fetch(`${API_BASE}/converter/status?_=${Date.now()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('无法获取转换器状态')
  return res.json()
}

/**
 * @param {File} file
 * @param {{ convert?: boolean }} options - convert: 上传 DWG 时是否自动转 DXF
 */
export async function uploadCadFile(file, { convert = true } = {}) {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams()
  if (file.name.toLowerCase().endsWith('.dwg')) {
    params.set('convert', convert ? 'true' : 'false')
  }
  const qs = params.toString()
  const url = `${API_BASE}/upload${qs ? `?${qs}` : ''}`
  const res = await fetch(url, { method: 'POST', body: form })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.detail || `上传失败 (${res.status})`)
  }
  return data
}
