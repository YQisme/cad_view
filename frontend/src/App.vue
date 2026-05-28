<template>
  <div class="app">
    <aside class="sidebar">
      <header class="sidebar-header">
        <h1>DXF 查看器</h1>
        <p class="subtitle">ezdxf 解析 · 图层 / 块显示控制</p>
      </header>

      <section v-if="loading" class="status">正在加载 DXF…</section>
      <section v-else-if="error" class="status error">{{ error }}</section>

      <template v-else-if="dxfData">
        <section class="panel">
          <div class="panel-title">
            <label>DXF 文件</label>
            <button type="button" class="link" @click="reloadFileList">刷新列表</button>
          </div>
          <select v-model="currentFile" @change="loadDxf">
            <option v-for="f in files" :key="f" :value="f">{{ f }}</option>
          </select>
          <p v-if="fileListHint" class="file-list-hint">{{ fileListHint }}</p>
        </section>

        <section class="panel stats" v-if="dxfData.stats">
          <span>实体 {{ dxfData.stats.entityCount }}</span>
          <span>图层 {{ dxfData.stats.layerCount }}</span>
          <span>块 {{ dxfData.stats.blockCount }}</span>
        </section>

        <section class="panel">
          <div class="panel-title">
            <label>显示列表</label>
            <div class="bulk-actions">
              <button type="button" class="link" @click="showAll">全部显示</button>
              <button type="button" class="link" @click="hideAll">全部隐藏</button>
            </div>
          </div>
          <div class="mode-tabs">
            <button
              type="button"
              :class="{ active: mode === 'layer' }"
              @click="mode = 'layer'"
            >
              图层
            </button>
            <button
              type="button"
              :class="{ active: mode === 'block' }"
              @click="mode = 'block'"
            >
              块
            </button>
          </div>
        </section>

        <section class="panel list-panel" v-if="mode === 'layer'">
          <label>图层可见性</label>
          <div class="search">
            <input v-model="layerFilter" placeholder="搜索图层…" />
          </div>
          <ul class="item-list">
            <li
              v-for="layer in filteredLayers"
              :key="layer.name"
              :class="{ 'is-hidden': isLayerHidden(layer.name) }"
            >
              <EyeToggle
                :visible="!isLayerHidden(layer.name)"
                @toggle="toggleLayerVisibility(layer.name)"
              />
              <span class="swatch" :style="{ background: layer.color }" />
              <span class="name">{{ layer.name }}</span>
              <span class="count" v-if="layerEntityCounts[layer.name]">
                {{ layerEntityCounts[layer.name] }}
              </span>
            </li>
          </ul>
        </section>

        <section class="panel list-panel" v-else>
          <label>块可见性</label>
          <div class="search">
            <input v-model="blockFilter" placeholder="搜索块名…" />
          </div>
          <ul class="item-list">
            <li
              v-for="name in filteredBlocks"
              :key="name"
              :class="{ 'is-hidden': isBlockHidden(name) }"
            >
              <EyeToggle
                :visible="!isBlockHidden(name)"
                @toggle="toggleBlockVisibility(name)"
              />
              <span class="name block-name">{{ name }}</span>
            </li>
          </ul>
        </section>

        <section class="hint">
          <EyeToggle :visible="true" class="hint-eye" />
          <span>显示</span>
          <EyeToggle :visible="false" class="hint-eye" />
          <span>隐藏</span>
        </section>
      </template>
    </aside>

    <main class="viewer">
      <DxfCanvas
        v-if="dxfData"
        ref="canvasRef"
        :data="dxfData"
        :hidden-layers="hiddenLayers"
        :hidden-blocks="hiddenBlocks"
      />
      <div v-else-if="!loading && !error" class="placeholder">请选择 DXF 文件</div>
      <div class="toolbar" v-if="dxfData">
        <button type="button" @click="fitView">适应窗口</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import DxfCanvas from './components/DxfCanvas.vue'
import EyeToggle from './components/EyeToggle.vue'
import { fetchDxfData, fetchFileList } from './api/dxf.js'

const loading = ref(true)
const error = ref('')
const dxfData = ref(null)
const files = ref(['Drawing1.dxf'])
const currentFile = ref('Drawing1.dxf')
const fileListHint = ref('')
const mode = ref('layer')
const hiddenLayers = ref([])
const hiddenBlocks = ref([])
const layerFilter = ref('')
const blockFilter = ref('')
const canvasRef = ref(null)

const layerEntityCounts = computed(() => {
  const counts = {}
  const walk = (ents) => {
    for (const e of ents || []) {
      const name = e.layer
      if (name) counts[name] = (counts[name] || 0) + 1
    }
  }
  walk(dxfData.value?.entities)
  for (const def of Object.values(dxfData.value?.blockDefinitions || {})) walk(def)
  return counts
})

const filteredLayers = computed(() => {
  if (!dxfData.value?.layers) return []
  const q = layerFilter.value.trim().toLowerCase()
  const counts = layerEntityCounts.value
  return dxfData.value.layers
    .filter((l) => !q || l.name.toLowerCase().includes(q))
    .slice()
    .sort((a, b) => {
      const diff = (counts[b.name] || 0) - (counts[a.name] || 0)
      return diff !== 0 ? diff : a.name.localeCompare(b.name, 'zh-CN')
    })
})

const filteredBlocks = computed(() => {
  if (!dxfData.value?.blocks) return []
  const q = blockFilter.value.trim().toLowerCase()
  return dxfData.value.blocks.filter((b) => !q || b.toLowerCase().includes(q))
})

function isLayerHidden(name) {
  return hiddenLayers.value.includes(name)
}

function isBlockHidden(name) {
  return hiddenBlocks.value.includes(name)
}

function toggleLayerVisibility(name) {
  const i = hiddenLayers.value.indexOf(name)
  if (i >= 0) hiddenLayers.value.splice(i, 1)
  else hiddenLayers.value.push(name)
}

function toggleBlockVisibility(name) {
  const i = hiddenBlocks.value.indexOf(name)
  if (i >= 0) hiddenBlocks.value.splice(i, 1)
  else hiddenBlocks.value.push(name)
}

function showAll() {
  if (mode.value === 'layer') {
    hiddenLayers.value = []
  } else {
    hiddenBlocks.value = []
  }
}

function hideAll() {
  if (mode.value === 'layer' && dxfData.value?.layers) {
    hiddenLayers.value = dxfData.value.layers.map((l) => l.name)
  } else if (mode.value === 'block' && dxfData.value?.blocks) {
    hiddenBlocks.value = [...dxfData.value.blocks]
  }
}

function fitView() {
  canvasRef.value?.fitView()
  canvasRef.value?.render()
}

async function loadDxf() {
  loading.value = true
  error.value = ''
  try {
    dxfData.value = await fetchDxfData(currentFile.value)
    hiddenLayers.value = (dxfData.value.layers || [])
      .filter((l) => l.on === false)
      .map((l) => l.name)
    hiddenBlocks.value = []
  } catch (e) {
    error.value = e.message
    dxfData.value = null
  } finally {
    loading.value = false
  }
}

function sameFileList(a, b) {
  if (!a || !b || a.length !== b.length) return false
  return a.every((name, i) => name === b[i])
}

async function reloadFileList() {
  fileListHint.value = ''
  try {
    const list = await fetchFileList()
    const next = list.files ?? []
    const changed = !sameFileList(files.value, next)
    if (next.length) files.value = next
    if (!files.value.includes(currentFile.value)) {
      currentFile.value = list.default || files.value[0]
      await loadDxf()
    } else if (changed && fileListHint.value === '') {
      fileListHint.value = '文件列表已更新'
      setTimeout(() => {
        if (fileListHint.value === '文件列表已更新') fileListHint.value = ''
      }, 2500)
    }
  } catch {
    fileListHint.value =
      '无法从后端获取文件列表，请确认后端已启动且通过 Vite（:5173）访问。'
  }
}

let fileListPollTimer = null

onMounted(async () => {
  await reloadFileList()
  await loadDxf()
  fileListPollTimer = setInterval(() => {
    if (document.visibilityState === 'visible') reloadFileList()
  }, 4000)
})

onUnmounted(() => {
  if (fileListPollTimer) clearInterval(fileListPollTimer)
})
</script>

<style scoped>
.app {
  display: flex;
  height: 100%;
}

.sidebar {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: #12151a;
  border-right: 1px solid #2d333b;
  overflow: hidden;
}

.sidebar-header h1 {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 0.8rem;
  color: #8b949e;
}

.status {
  color: #8b949e;
  font-size: 0.9rem;
}
.status.error {
  color: #f85149;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel label,
.panel-title label {
  font-size: 0.75rem;
  color: #8b949e;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.bulk-actions {
  display: flex;
  gap: 8px;
}

.file-list-hint {
  margin: 0;
  font-size: 0.75rem;
  color: #d29922;
  line-height: 1.4;
}

.panel select,
.search input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #30363d;
  border-radius: 6px;
  background: #0d1117;
  color: #e8eaed;
}

.stats {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.8rem;
  color: #8b949e;
}

.mode-tabs {
  display: flex;
  gap: 4px;
}

.mode-tabs button {
  flex: 1;
  padding: 8px;
  border: 1px solid #30363d;
  border-radius: 6px;
  background: #0d1117;
  color: #8b949e;
  cursor: pointer;
}
.mode-tabs button.active {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #fff;
}

.list-panel {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.item-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
  max-height: 360px;
  border: 1px solid #30363d;
  border-radius: 6px;
  background: #0d1117;
}

.item-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px 4px;
  border-bottom: 1px solid #21262d;
  font-size: 0.85rem;
}
.item-list li.is-hidden {
  opacity: 0.45;
}
.item-list li.is-hidden .name {
  text-decoration: line-through;
  color: #6e7681;
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
  border: 1px solid #444;
}

.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count {
  flex-shrink: 0;
  font-size: 0.7rem;
  color: #6e7681;
  font-variant-numeric: tabular-nums;
}

.link {
  background: none;
  border: none;
  color: #58a6ff;
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0;
}

.hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: #8b949e;
}
.hint :deep(.eye-btn) {
  width: 22px;
  height: 22px;
  pointer-events: none;
}
.hint :deep(.icon) {
  width: 14px;
  height: 14px;
}

.viewer {
  flex: 1;
  position: relative;
  min-width: 0;
}

.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #8b949e;
}

.toolbar {
  position: absolute;
  top: 12px;
  right: 12px;
}

.toolbar button {
  padding: 8px 14px;
  border: none;
  border-radius: 6px;
  background: #30363d;
  color: #e8eaed;
  cursor: pointer;
}
.toolbar button:hover {
  background: #484f58;
}
</style>
