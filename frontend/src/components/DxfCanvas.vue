<template>
  <canvas
    ref="canvasRef"
    class="dxf-canvas"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseUp"
  />
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, toRaw } from 'vue'
import {
  expandInserts,
  computeEntityBounds,
  computeGridCellSize,
  SpatialGrid,
  bboxIntersects,
  attributeEntryKey,
  attributesMatchFilter,
} from '../utils/geometry.js'

const props = defineProps({
  data: { type: Object, default: null },
  hiddenLayers: { type: Array, default: () => [] },
  hiddenBlocks: { type: Array, default: () => [] },
  hiddenAttributeKeys: { type: Array, default: () => [] },
  attributeFilter: { type: String, default: '' },
  attributeFilterOnly: { type: Boolean, default: false },
})

const canvasRef = ref(null)
/** 平移/缩放用普通对象，避免 wheel 高频触发 Vue 响应式 */
const view = { scale: 1, offsetX: 0, offsetY: 0 }
const dragging = ref(false)
const lastMouse = ref({ x: 0, y: 0 })

let resizeObserver = null
let canvasCtx = null
let canvasDpr = 1
let canvasCssW = 0
let canvasCssH = 0
let renderScheduled = false
let expandedEntities = []
let spatialGrid = null
let hiddenLayerSet = new Set()
let hiddenBlockSet = new Set()
let hiddenAttributeSet = new Set()
let prepareWorker = null
let prepareJobId = 0

function syncHiddenSets() {
  hiddenLayerSet = new Set(props.hiddenLayers)
  hiddenBlockSet = new Set(props.hiddenBlocks)
  hiddenAttributeSet = new Set(props.hiddenAttributeKeys)
}

function finishPrepare(drawn) {
  expandedEntities = drawn
  const cellSize = computeGridCellSize(props.data?.bounds, drawn.length)
  const grid = new SpatialGrid(cellSize)
  for (const entity of drawn) {
    if (entity._bbox) grid.insert(entity)
  }
  spatialGrid = grid
  fitView()
  scheduleRender()
}

function plainDxfPayload() {
  const data = props.data
  if (!data) return null
  return {
    entities: toRaw(data.entities),
    blockDefinitions: toRaw(data.blockDefinitions) || {},
  }
}

function rebuildExpandedEntitiesSync() {
  const payload = plainDxfPayload()
  if (!payload?.entities) {
    expandedEntities = []
    spatialGrid = null
    return
  }
  const { drawn } = expandInserts(payload.entities, payload.blockDefinitions)
  for (const entity of drawn) {
    entity._bbox = computeEntityBounds(entity)
  }
  finishPrepare(drawn)
}

function rebuildExpandedEntities() {
  const payload = plainDxfPayload()
  if (!payload?.entities) {
    expandedEntities = []
    spatialGrid = null
    return
  }

  const jobId = ++prepareJobId
  if (!prepareWorker) {
    try {
      prepareWorker = new Worker(
        new URL('../workers/dxfPrepare.worker.js', import.meta.url),
        { type: 'module' },
      )
      prepareWorker.onmessage = (ev) => {
        if (ev.data.jobId !== prepareJobId) return
        if (ev.data.error) {
          prepareWorker?.terminate()
          prepareWorker = null
          rebuildExpandedEntitiesSync()
          return
        }
        finishPrepare(ev.data.drawn)
      }
      prepareWorker.onerror = () => {
        prepareWorker?.terminate()
        prepareWorker = null
        rebuildExpandedEntitiesSync()
      }
    } catch {
      rebuildExpandedEntitiesSync()
      return
    }
  }

  try {
    prepareWorker.postMessage({
      jobId,
      entities: payload.entities,
      blockDefinitions: payload.blockDefinitions,
    })
  } catch {
    rebuildExpandedEntitiesSync()
  }
}

/** 当前视口对应的世界坐标包围盒（含屏幕像素边距） */
function getWorldViewport(marginPx = 64) {
  const { scale, offsetX, offsetY } = view
  const pad = marginPx / scale
  return [
    -offsetX / scale - pad,
    -(canvasCssH - offsetY) / scale - pad,
    (canvasCssW - offsetX) / scale + pad,
    offsetY / scale + pad,
  ]
}

function queryVisibleEntities() {
  const viewBbox = getWorldViewport()
  if (spatialGrid) return spatialGrid.query(viewBbox)

  const visible = []
  for (const entity of expandedEntities) {
    if (entity._bbox && bboxIntersects(entity._bbox, viewBbox)) visible.push(entity)
  }
  return visible
}

function scheduleRender() {
  if (renderScheduled) return
  renderScheduled = true
  requestAnimationFrame(() => {
    renderScheduled = false
    render()
  })
}

function setupCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return false

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const w = rect.width
  const h = rect.height

  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvasCtx = canvas.getContext('2d')
  }

  canvasDpr = dpr
  canvasCssW = w
  canvasCssH = h
  return !!canvasCtx
}

function fitView() {
  if (!props.data?.bounds || !canvasRef.value) return
  const canvas = canvasRef.value
  const cw = canvas.clientWidth
  const ch = canvas.clientHeight
  if (cw < 1 || ch < 1) return
  const { min, max } = props.data.bounds
  const w = max[0] - min[0]
  const h = max[1] - min[1]
  if (w <= 0 || h <= 0) return
  const pad = 40
  const sx = (cw - pad * 2) / w
  const sy = (ch - pad * 2) / h
  const scale = Math.min(sx, sy)
  if (!Number.isFinite(scale) || scale <= 0) return
  view.scale = scale
  view.offsetX = pad - min[0] * scale + (canvas.clientWidth - pad * 2 - w * scale) / 2
  view.offsetY = canvas.clientHeight - pad + min[1] * scale - (canvas.clientHeight - pad * 2 - h * scale) / 2
}

/** 拉丁字母在前，避免个别环境下 CJK 字体拉丁字形异常 */
const FONT_FAMILY =
  '"Segoe UI", Arial, "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif'
/** 仅对过小注记做底线放大；全图时多数字高约 1～3px，若用 10px 底线会明显偏大 */
const TEXT_LEGIBILITY_FLOOR_PX = 4

function isEntityVisible(entity, insertRef) {
  if (hiddenLayerSet.has(entity.layer)) return false
  const blockName = insertRef?.block
  if (blockName && hiddenBlockSet.has(blockName)) return false
  if (insertRef?.layer && hiddenLayerSet.has(insertRef.layer)) return false

  const attrs = insertRef?.attributes
  if (attrs && hiddenAttributeSet.size) {
    for (const [tag, val] of Object.entries(attrs)) {
      if (hiddenAttributeSet.has(attributeEntryKey(tag, val))) return false
    }
  }

  const filterQ = (props.attributeFilter || '').trim()
  if (filterQ && props.attributeFilterOnly) {
    if (!attrs || !attributesMatchFilter(attrs, filterQ)) return false
  }

  return true
}

/** SOLID：三角形或对边四边形，按正确顶点顺序填充（世界坐标） */
function drawSolid(ctx, entity) {
  const color = entity.color || '#aaaaaa'
  const pts = entity.points
  ctx.fillStyle = color
  ctx.globalAlpha = 1

  if (pts.length === 3) {
    ctx.beginPath()
    ctx.moveTo(pts[0][0], pts[0][1])
    ctx.lineTo(pts[1][0], pts[1][1])
    ctx.lineTo(pts[2][0], pts[2][1])
    ctx.closePath()
    ctx.fill()
    return
  }

  if (pts.length >= 4) {
    ctx.beginPath()
    ctx.moveTo(pts[0][0], pts[0][1])
    ctx.lineTo(pts[1][0], pts[1][1])
    ctx.lineTo(pts[2][0], pts[2][1])
    ctx.closePath()
    ctx.fill()
    ctx.beginPath()
    ctx.moveTo(pts[0][0], pts[0][1])
    ctx.lineTo(pts[2][0], pts[2][1])
    ctx.lineTo(pts[3][0], pts[3][1])
    ctx.closePath()
    ctx.fill()
  }
}

function drawHatch(ctx, entity) {
  const color = entity.color || '#aaaaaa'

  if (entity.patternLines?.length) {
    ctx.strokeStyle = color
    for (const [a, b] of entity.patternLines) {
      ctx.beginPath()
      ctx.moveTo(a[0], a[1])
      ctx.lineTo(b[0], b[1])
      ctx.stroke()
    }
  }

  if (entity.solidFill && entity.paths?.length) {
    ctx.fillStyle = color + '44'
    for (const ring of entity.paths) {
      if (ring.length < 3) continue
      ctx.beginPath()
      ctx.moveTo(ring[0][0], ring[0][1])
      for (let i = 1; i < ring.length; i++) ctx.lineTo(ring[i][0], ring[i][1])
      ctx.closePath()
      ctx.fill()
    }
  }
}

/** MTEXT attachment_point 1–9 → Canvas 对齐 */
function mtextCanvasAlign(attachmentPoint) {
  const ap = attachmentPoint || 1
  const h = ((ap - 1) % 3) + 1
  const v = Math.floor((ap - 1) / 3) + 1
  const textAlign = h === 1 ? 'left' : h === 2 ? 'center' : 'right'
  const textBaseline = v === 1 ? 'top' : v === 2 ? 'middle' : 'alphabetic'
  return { textAlign, textBaseline }
}

/** TEXT halign/valign → Canvas 对齐（0 为左/基线） */
function textCanvasAlign(halign, valign) {
  const ha = halign || 0
  const va = valign || 0
  let textAlign = 'left'
  if (ha === 1 || ha === 4) textAlign = 'center'
  else if (ha === 2) textAlign = 'right'
  let textBaseline = 'alphabetic'
  if (va === 1) textBaseline = 'bottom'
  else if (va === 2) textBaseline = 'middle'
  else if (va === 3) textBaseline = 'top'
  return { textAlign, textBaseline }
}

function drawText(ctx, entity) {
  const cadHeight = entity.height || 2.5
  const naturalScreenPx = cadHeight * view.scale
  const targetScreenPx =
    naturalScreenPx < TEXT_LEGIBILITY_FLOOR_PX
      ? TEXT_LEGIBILITY_FLOOR_PX
      : naturalScreenPx
  const fontSize = targetScreenPx / view.scale
  const rotation = entity.rotation || 0
  // MTEXT 的 width 是参考框宽度（常数百～数千），不是 TEXT 的字宽因子
  const isMtext =
    entity.textKind === 'mtext' || (!entity.textKind && (entity.width || 1) > 10)
  let widthFactor = 1
  if (!isMtext) {
    widthFactor = entity.width && entity.width > 0 ? entity.width : 1
  }

  ctx.save()
  ctx.translate(entity.position[0], entity.position[1])
  // 全局变换含 Y 轴翻转，文字需局部反翻转才能正向显示
  ctx.scale(1, -1)
  if (rotation) {
    ctx.rotate((-rotation * Math.PI) / 180)
  }

  ctx.font = `${fontSize}px ${FONT_FAMILY}`
  const align = isMtext
    ? mtextCanvasAlign(entity.attachmentPoint)
    : textCanvasAlign(entity.halign, entity.valign)
  ctx.textBaseline = align.textBaseline
  ctx.textAlign = align.textAlign

  // TEXT「适应」(halign=5)：在 insert 与 alignPoint 之间拉伸字宽
  if (!isMtext && entity.halign === 5 && entity.alignPoint) {
    const dx = entity.alignPoint[0] - entity.position[0]
    const dy = entity.alignPoint[1] - entity.position[1]
    const span = Math.hypot(dx, dy)
    const measured = ctx.measureText(entity.text).width
    if (measured > 1e-6 && span > 1e-6) {
      widthFactor = (span / measured) * (entity.width && entity.width > 0 ? entity.width : 1)
    }
  }
  if (!isMtext && widthFactor !== 1) {
    ctx.scale(widthFactor, 1)
  }

  ctx.fillStyle = entity.color || '#ccc'
  ctx.globalAlpha = 1
  ctx.fillText(entity.text, 0, 0)
  ctx.restore()
}

function drawEntity(ctx, entity, insertRef) {
  ctx.globalAlpha = 0.9
  ctx.strokeStyle = entity.color || '#aaaaaa'
  ctx.fillStyle = (entity.color || '#aaaaaa') + '33'

  if (entity.type === 'line' && entity.points?.length === 2) {
    const [a, b] = entity.points
    ctx.beginPath()
    ctx.moveTo(a[0], a[1])
    ctx.lineTo(b[0], b[1])
    ctx.stroke()
  } else if (entity.type === 'solid' && entity.points?.length >= 3) {
    drawSolid(ctx, entity)
  } else if (entity.type === 'polyline' && entity.points?.length >= 2) {
    ctx.beginPath()
    const pts = entity.points
    ctx.moveTo(pts[0][0], pts[0][1])
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
    if (entity.closed) ctx.closePath()
    ctx.stroke()
  } else if (entity.type === 'circle') {
    ctx.beginPath()
    ctx.arc(entity.center[0], entity.center[1], entity.radius, 0, Math.PI * 2)
    ctx.stroke()
  } else if (entity.type === 'arc') {
    const start = (entity.startAngle * Math.PI) / 180
    const end = (entity.endAngle * Math.PI) / 180
    ctx.beginPath()
    ctx.arc(entity.center[0], entity.center[1], entity.radius, start, end, true)
    ctx.stroke()
  } else if (entity.type === 'hatch') {
    drawHatch(ctx, entity)
  } else if (entity.type === 'text') {
    drawText(ctx, entity)
  }

  ctx.globalAlpha = 1
}

function render() {
  if (!setupCanvas() || !props.data) return

  const ctx = canvasCtx
  const { scale, offsetX, offsetY } = view

  ctx.setTransform(canvasDpr, 0, 0, canvasDpr, 0, 0)
  ctx.clearRect(0, 0, canvasCssW, canvasCssH)
  ctx.fillStyle = '#252830'
  ctx.fillRect(0, 0, canvasCssW, canvasCssH)

  ctx.setTransform(
    scale * canvasDpr,
    0,
    0,
    -scale * canvasDpr,
    offsetX * canvasDpr,
    offsetY * canvasDpr,
  )

  const baseLineWidth = Math.max(0.5, 1 / canvasDpr) / scale
  const visibleEntities = queryVisibleEntities()

  for (const entity of visibleEntities) {
    if (entity.type === 'text') continue
    if (!isEntityVisible(entity, entity.blockRef)) continue
    ctx.lineWidth = baseLineWidth
    drawEntity(ctx, entity, entity.blockRef)
  }

  for (const entity of visibleEntities) {
    if (entity.type !== 'text') continue
    if (!isEntityVisible(entity, entity.blockRef)) continue
    ctx.lineWidth = baseLineWidth
    drawEntity(ctx, entity, entity.blockRef)
  }
}

function onWheel(e) {
  const factor = e.deltaY > 0 ? 0.9 : 1.1
  const rect = canvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const oldScale = view.scale
  const newScale = oldScale * factor
  view.scale = newScale
  view.offsetX = mx - (mx - view.offsetX) * (newScale / oldScale)
  view.offsetY = my - (my - view.offsetY) * (newScale / oldScale)
  scheduleRender()
}

function onMouseDown(e) {
  if (e.button !== 0) return
  dragging.value = true
  lastMouse.value = { x: e.clientX, y: e.clientY }
}

function onMouseMove(e) {
  if (!dragging.value) return
  const dx = e.clientX - lastMouse.value.x
  const dy = e.clientY - lastMouse.value.y
  view.offsetX += dx
  view.offsetY += dy
  lastMouse.value = { x: e.clientX, y: e.clientY }
  scheduleRender()
}

function onMouseUp() {
  dragging.value = false
}

watch(
  () => props.data,
  () => {
    if (props.data) rebuildExpandedEntities()
    else {
      expandedEntities = []
      spatialGrid = null
    }
  },
  { immediate: true },
)

watch(
  () => [
    props.hiddenLayers,
    props.hiddenBlocks,
    props.hiddenAttributeKeys,
    props.attributeFilter,
    props.attributeFilterOnly,
  ],
  () => {
    syncHiddenSets()
    scheduleRender()
  },
  { deep: true },
)

onMounted(() => {
  syncHiddenSets()

  resizeObserver = new ResizeObserver(() => {
    fitView()
    scheduleRender()
  })
  if (canvasRef.value) resizeObserver.observe(canvasRef.value)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  prepareWorker?.terminate()
  prepareWorker = null
})

defineExpose({ fitView, render })
</script>

<style scoped>
.dxf-canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
  background: #252830;
}
.dxf-canvas:active {
  cursor: grabbing;
}
</style>
