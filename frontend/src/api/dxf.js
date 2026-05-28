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
