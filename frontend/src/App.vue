<template>
  <div class="app">
    <aside class="sidebar">
      <header class="sidebar-header">
        <h1>DXF 查看器</h1>
        <p class="subtitle">ezdxf 解析 · 图层 / 块 / 属性显示控制</p>
      </header>

      <section v-if="loading" class="status">正在加载 DXF…</section>
      <section v-else-if="error" class="status error">{{ error }}</section>

      <template v-else-if="dxfData">
        <section class="panel">
          <div class="panel-title">
            <label>图纸文件</label>
            <button type="button" class="link" @click="reloadFileList">刷新列表</button>
          </div>
          <select v-model="currentFile" @change="loadDxf">
            <option v-for="f in files" :key="f" :value="f">{{ f }}</option>
          </select>
          <p v-if="fileListHint" class="file-list-hint">{{ fileListHint }}</p>

          <div class="upload-block">
            <label class="upload-btn">
              <input
                ref="fileInputRef"
                type="file"
                accept=".dxf,.dwg"
                class="upload-input"
                :disabled="uploading"
                @change="onFileSelected"
              />
              {{ uploading ? '上传中…' : '上传 DXF / DWG' }}
            </label>
            <label v-if="converterAvailable" class="upload-option">
              <input v-model="autoConvertDwg" type="checkbox" :disabled="uploading" />
              <span>DWG 自动转为 DXF</span>
            </label>
            <p v-else class="upload-warn">
              未检测到 DWG 转换器，仅可上传 DXF。安装
              <a href="https://www.opendesign.com/guestfiles/oda_file_converter" target="_blank" rel="noopener">ODA File Converter</a>
              后可自动转换 DWG。
            </p>
            <p v-if="uploadHint" class="file-list-hint">{{ uploadHint }}</p>
          </div>
        </section>

        <section class="panel stats" v-if="dxfData.stats">
          <span>实体 {{ dxfData.stats.entityCount }}</span>
          <span>图层 {{ dxfData.stats.layerCount }}</span>
          <span>块 {{ dxfData.stats.blockCount }}</span>
          <span v-if="dxfData.stats.attributeTagCount">
            属性 {{ dxfData.stats.attributeTagCount }}
          </span>
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
            <button
              type="button"
              :class="{ active: mode === 'attribute' }"
              @click="mode = 'attribute'"
            >
              属性
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

        <section class="panel list-panel" v-else-if="mode === 'block'">
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

        <section class="panel list-panel" v-else>
          <label>块属性</label>
          <div class="search">
            <input
              v-model="attributeFilter"
              placeholder="筛选：标签或 标签=值 …"
            />
          </div>
          <label class="filter-only">
            <input v-model="attributeFilterOnly" type="checkbox" />
            <span>仅显示匹配属性的块实例</span>
          </label>
          <p v-if="!filteredAttributeCatalog.length" class="empty-hint">
            当前图纸模型空间无带属性块实例
          </p>
          <ul v-else class="item-list attr-list">
            <template v-for="group in filteredAttributeCatalog" :key="group.tag">
              <li class="attr-tag-row">
                <span class="attr-tag">{{ group.tag }}</span>
                <span class="count">{{ group.insertCount }}</span>
              </li>
              <li
                v-for="entry in group.values"
                :key="attributeEntryKey(group.tag, entry.value)"
                :class="{
                  'is-hidden': isAttributeHidden(group.tag, entry.value),
                }"
              >
                <EyeToggle
                  :visible="!isAttributeHidden(group.tag, entry.value)"
                  @toggle="toggleAttributeVisibility(group.tag, entry.value)"
                />
                <span class="name attr-value">{{
                  formatAttributeValue(entry.value)
                }}</span>
                <span class="count">{{ entry.count }}</span>
              </li>
            </template>
          </ul>
          <details
            v-if="attributeDefBlocks.length"
            class="attr-defs"
          >
            <summary>块定义中的属性标签（ATTDEF）</summary>
            <ul class="def-list">
              <li v-for="item in attributeDefBlocks" :key="item.block">
                <span class="def-block">{{ item.block }}</span>
                <span class="def-tags">{{ item.tags.join(' · ') }}</span>
              </li>
            </ul>
          </details>
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
        :hidden-attribute-keys="hiddenAttributeKeys"
        :attribute-filter="attributeFilter"
        :attribute-filter-only="attributeFilterOnly"
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
import {
  fetchConverterStatus,
  fetchDxfData,
  fetchFileList,
  uploadCadFile,
} from './api/dxf.js'
import { attributeEntryKey } from './utils/geometry.js'

const loading = ref(true)
const error = ref('')
const dxfData = ref(null)
const files = ref(['Drawing1.dxf'])
const currentFile = ref('Drawing1.dxf')
const fileListHint = ref('')
const uploadHint = ref('')
const uploading = ref(false)
const autoConvertDwg = ref(true)
const converterAvailable = ref(false)
const fileInputRef = ref(null)
const mode = ref('layer')
const hiddenLayers = ref([])
const hiddenBlocks = ref([])
const layerFilter = ref('')
const blockFilter = ref('')
const attributeFilter = ref('')
const attributeFilterOnly = ref(false)
const hiddenAttributeKeys = ref([])
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

const filteredAttributeCatalog = computed(() => {
  const catalog = dxfData.value?.blockAttributes
  if (!catalog?.length) return []
  const q = attributeFilter.value.trim().toLowerCase()
  if (!q) return catalog

  let filterTag = ''
  let filterVal = ''
  if (q.includes('=')) {
    const eq = q.indexOf('=')
    filterTag = q.slice(0, eq).trim()
    filterVal = q.slice(eq + 1).trim()
  }

  return catalog
    .map((group) => {
      const tagMatch = !filterTag || group.tag.toLowerCase().includes(filterTag)
      if (!tagMatch) return null
      const values = group.values.filter((entry) => {
        const val = String(entry.value).toLowerCase()
        const label = formatAttributeValue(entry.value).toLowerCase()
        if (filterVal) return val.includes(filterVal) || label.includes(filterVal)
        return (
          group.tag.toLowerCase().includes(q) ||
          val.includes(q) ||
          label.includes(q)
        )
      })
      if (!values.length) return null
      return { ...group, values, insertCount: values.reduce((s, v) => s + v.count, 0) }
    })
    .filter(Boolean)
})

const attributeDefBlocks = computed(() => {
  const defs = dxfData.value?.blockAttributeDefs
  if (!defs) return []
  const q = blockFilter.value.trim().toLowerCase()
  return Object.entries(defs)
    .map(([block, tags]) => ({ block, tags }))
    .filter((item) => !q || item.block.toLowerCase().includes(q))
    .sort((a, b) => a.block.localeCompare(b.block, 'zh-CN'))
})

function formatAttributeValue(value) {
  const s = String(value ?? '').trim()
  return s === '' ? '(空)' : s
}

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

function isAttributeHidden(tag, value) {
  return hiddenAttributeKeys.value.includes(attributeEntryKey(tag, value))
}

function toggleAttributeVisibility(tag, value) {
  const key = attributeEntryKey(tag, value)
  const i = hiddenAttributeKeys.value.indexOf(key)
  if (i >= 0) hiddenAttributeKeys.value.splice(i, 1)
  else hiddenAttributeKeys.value.push(key)
}

function allAttributeKeys() {
  const keys = []
  for (const group of dxfData.value?.blockAttributes || []) {
    for (const entry of group.values) {
      keys.push(attributeEntryKey(group.tag, entry.value))
    }
  }
  return keys
}

function showAll() {
  if (mode.value === 'layer') {
    hiddenLayers.value = []
  } else if (mode.value === 'block') {
    hiddenBlocks.value = []
  } else {
    hiddenAttributeKeys.value = []
    attributeFilter.value = ''
    attributeFilterOnly.value = false
  }
}

function hideAll() {
  if (mode.value === 'layer' && dxfData.value?.layers) {
    hiddenLayers.value = dxfData.value.layers.map((l) => l.name)
  } else if (mode.value === 'block' && dxfData.value?.blocks) {
    hiddenBlocks.value = [...dxfData.value.blocks]
  } else {
    hiddenAttributeKeys.value = allAttributeKeys()
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
    hiddenAttributeKeys.value = []
    attributeFilter.value = ''
    attributeFilterOnly.value = false
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
    if (typeof list.converterAvailable === 'boolean') {
      converterAvailable.value = list.converterAvailable
    }
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

async function onFileSelected(ev) {
  const input = ev.target
  const file = input.files?.[0]
  if (!file) return

  const ext = file.name.toLowerCase().split('.').pop()
  if (ext !== 'dxf' && ext !== 'dwg') {
    uploadHint.value = '仅支持 .dxf 与 .dwg 文件'
    input.value = ''
    return
  }

  if (ext === 'dwg' && autoConvertDwg.value && !converterAvailable.value) {
    uploadHint.value = '请先安装 ODA File Converter，或取消勾选自动转换后仅保存 DWG'
    input.value = ''
    return
  }

  uploading.value = true
  uploadHint.value = ''
  try {
    const result = await uploadCadFile(file, {
      convert: ext === 'dwg' ? autoConvertDwg.value : false,
    })
    await reloadFileList()
    if (result.dxfFile) {
      currentFile.value = result.dxfFile
      await loadDxf()
      uploadHint.value = result.converted
        ? `已上传并转换：${result.dxfFile}`
        : `已上传：${result.savedAs}`
    } else {
      uploadHint.value = result.message || `已保存：${result.savedAs}`
    }
  } catch (e) {
    uploadHint.value = e.message
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function loadConverterStatus() {
  try {
    const st = await fetchConverterStatus()
    converterAvailable.value = !!st.available
  } catch {
    converterAvailable.value = false
  }
}

let fileListPollTimer = null

onMounted(async () => {
  await loadConverterStatus()
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

.upload-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid #21262d;
}

.upload-input {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.upload-btn {
  display: block;
  text-align: center;
  padding: 8px 10px;
  border: 1px dashed #30363d;
  border-radius: 6px;
  background: #0d1117;
  color: #58a6ff;
  font-size: 0.85rem;
  cursor: pointer;
}
.upload-btn:hover {
  border-color: #58a6ff;
  background: #161b22;
}

.upload-option {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: #8b949e;
  cursor: pointer;
}
.upload-option input {
  accent-color: #1f6feb;
}

.upload-warn {
  margin: 0;
  font-size: 0.75rem;
  color: #8b949e;
  line-height: 1.45;
}
.upload-warn a {
  color: #58a6ff;
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
  padding: 6px 4px;
  font-size: 0.8rem;
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

.filter-only {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.78rem;
  color: #8b949e;
  cursor: pointer;
  line-height: 1.35;
}
.filter-only input {
  margin-top: 2px;
  accent-color: #1f6feb;
}

.empty-hint {
  margin: 0;
  font-size: 0.8rem;
  color: #6e7681;
}

.attr-list .attr-tag-row {
  background: #161b22;
  font-weight: 600;
  cursor: default;
  padding: 6px 10px;
}
.attr-tag {
  flex: 1;
  color: #58a6ff;
  font-size: 0.8rem;
}
.attr-value {
  font-size: 0.82rem;
}

.attr-defs {
  margin-top: 8px;
  font-size: 0.75rem;
  color: #8b949e;
}
.attr-defs summary {
  cursor: pointer;
  color: #8b949e;
}
.def-list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  max-height: 120px;
  overflow-y: auto;
}
.def-list li {
  padding: 4px 0;
  border-bottom: 1px solid #21262d;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.def-block {
  color: #c9d1d9;
  font-size: 0.78rem;
}
.def-tags {
  color: #6e7681;
  font-size: 0.72rem;
  word-break: break-all;
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
