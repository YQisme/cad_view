/** 将块内实体按 INSERT 变换到模型空间坐标 */

export function transformPoint([x, y], insert) {
  const { position, rotation = 0, scale = [1, 1] } = insert
  const [sx, sy] = scale
  const rad = (rotation * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const px = x * sx
  const py = y * sy
  return [
    position[0] + px * cos - py * sin,
    position[1] + px * sin + py * cos,
  ]
}

/** 合并嵌套块 INSERT 变换（先 inner 后 outer） */
export function combineInsert(outer, inner) {
  return {
    ...inner,
    block: inner.block,
    layer: inner.layer,
    position: transformPoint(inner.position, outer),
    rotation: (inner.rotation || 0) + (outer.rotation || 0),
    scale: [
      (inner.scale?.[0] ?? 1) * (outer.scale?.[0] ?? 1),
      (inner.scale?.[1] ?? 1) * (outer.scale?.[1] ?? 1),
    ],
  }
}

export function transformEntity(entity, insert) {
  const blockRef = insert

  if (entity.type === 'line' || entity.type === 'polyline' || entity.type === 'solid') {
    return {
      type: entity.type,
      layer: entity.layer,
      color: entity.color,
      closed: entity.closed,
      points: entity.points.map((p) => transformPoint(p, insert)),
      blockRef,
    }
  }
  if (entity.type === 'circle' || entity.type === 'arc') {
    const center = transformPoint(entity.center, insert)
    const scaleFactor = Math.max(Math.abs(insert.scale[0]), Math.abs(insert.scale[1]))
    return {
      type: entity.type,
      layer: entity.layer,
      color: entity.color,
      center,
      radius: entity.radius * scaleFactor,
      startAngle: entity.startAngle != null ? entity.startAngle + insert.rotation : undefined,
      endAngle: entity.endAngle != null ? entity.endAngle + insert.rotation : undefined,
      blockRef,
    }
  }
  if (entity.type === 'text') {
    const scaleFactor = Math.max(Math.abs(insert.scale[0]), Math.abs(insert.scale[1]))
    const out = {
      type: 'text',
      layer: entity.layer,
      color: entity.color,
      textKind: entity.textKind,
      position: transformPoint(entity.position, insert),
      text: entity.text,
      height: (entity.height || 2.5) * scaleFactor,
      width: entity.width,
      rotation: (entity.rotation || 0) + (insert.rotation || 0),
      halign: entity.halign,
      valign: entity.valign,
      attachmentPoint: entity.attachmentPoint,
      alignPoint: entity.alignPoint
        ? transformPoint(entity.alignPoint, insert)
        : undefined,
      blockRef,
    }
    return out
  }
  if (entity.type === 'hatch') {
    return {
      type: 'hatch',
      layer: entity.layer,
      color: entity.color,
      paths: (entity.paths || []).map((ring) => ring.map((p) => transformPoint(p, insert))),
      patternLines: (entity.patternLines || []).map(([a, b]) => [
        transformPoint(a, insert),
        transformPoint(b, insert),
      ]),
      patternName: entity.patternName,
      solidFill: entity.solidFill,
      blockRef,
    }
  }
  return { ...entity, blockRef }
}

function expandBlockDef(def, blockDefinitions, insertCtx, drawn) {
  for (const child of def) {
    if (child.type === 'insert') {
      const nested = combineInsert(insertCtx, child)
      const sub = blockDefinitions[child.block]
      if (sub) expandBlockDef(sub, blockDefinitions, nested, drawn)
    } else {
      drawn.push(transformEntity(child, insertCtx))
    }
  }
}

/** 展开 INSERT（含块内嵌套 INSERT）为可绘制实体列表 */
export function expandInserts(entities, blockDefinitions) {
  const drawn = []
  const inserts = []

  for (const e of entities) {
    if (e.type === 'insert') {
      inserts.push(e)
      const def = blockDefinitions[e.block]
      if (def) expandBlockDef(def, blockDefinitions, e, drawn)
    } else {
      drawn.push(e)
    }
  }
  return { drawn, inserts }
}

function expandBounds(bbox, x, y) {
  if (x < bbox[0]) bbox[0] = x
  if (y < bbox[1]) bbox[1] = y
  if (x > bbox[2]) bbox[2] = x
  if (y > bbox[3]) bbox[3] = y
}

/** 计算实体世界坐标包围盒 [minX, minY, maxX, maxY] */
export function computeEntityBounds(entity) {
  const bbox = [Infinity, Infinity, -Infinity, -Infinity]

  if (entity.type === 'line' || entity.type === 'polyline' || entity.type === 'solid') {
    for (const p of entity.points || []) expandBounds(bbox, p[0], p[1])
  } else if (entity.type === 'circle' || entity.type === 'arc') {
    const [cx, cy] = entity.center
    const r = entity.radius || 0
    bbox[0] = cx - r
    bbox[1] = cy - r
    bbox[2] = cx + r
    bbox[3] = cy + r
  } else if (entity.type === 'text') {
    const [x, y] = entity.position
    const h = entity.height || 2.5
    const widthFactor = entity.width && entity.width > 0 ? entity.width : 1
    const w = (entity.text?.length || 1) * h * 0.55 * widthFactor
    expandBounds(bbox, x, y)
    expandBounds(bbox, x + w, y + h)
  } else if (entity.type === 'hatch') {
    for (const ring of entity.paths || []) {
      for (const p of ring) expandBounds(bbox, p[0], p[1])
    }
    for (const [a, b] of entity.patternLines || []) {
      expandBounds(bbox, a[0], a[1])
      expandBounds(bbox, b[0], b[1])
    }
  }

  if (bbox[0] === Infinity) return null
  return bbox
}

export function bboxIntersects(a, b) {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1]
}

/** 均匀网格空间索引，用于视口裁剪 */
export class SpatialGrid {
  constructor(cellSize = 100) {
    this.cellSize = cellSize
    this.cells = new Map()
  }

  _key(cx, cy) {
    return `${cx},${cy}`
  }

  insert(entity) {
    const bbox = entity._bbox
    if (!bbox) return
    const cs = this.cellSize
    const minCx = Math.floor(bbox[0] / cs)
    const maxCx = Math.floor(bbox[2] / cs)
    const minCy = Math.floor(bbox[1] / cs)
    const maxCy = Math.floor(bbox[3] / cs)
    for (let cx = minCx; cx <= maxCx; cx++) {
      for (let cy = minCy; cy <= maxCy; cy++) {
        const key = this._key(cx, cy)
        let cell = this.cells.get(key)
        if (!cell) {
          cell = []
          this.cells.set(key, cell)
        }
        cell.push(entity)
      }
    }
  }

  query(viewBbox) {
    const cs = this.cellSize
    const minCx = Math.floor(viewBbox[0] / cs)
    const maxCx = Math.floor(viewBbox[2] / cs)
    const minCy = Math.floor(viewBbox[1] / cs)
    const maxCy = Math.floor(viewBbox[3] / cs)
    const seen = new Set()
    const results = []
    for (let cx = minCx; cx <= maxCx; cx++) {
      for (let cy = minCy; cy <= maxCy; cy++) {
        const cell = this.cells.get(this._key(cx, cy))
        if (!cell) continue
        for (const entity of cell) {
          if (seen.has(entity)) continue
          seen.add(entity)
          if (bboxIntersects(entity._bbox, viewBbox)) results.push(entity)
        }
      }
    }
    return results
  }
}

export function computeGridCellSize(bounds, entityCount) {
  if (!bounds?.min || !bounds?.max) return 100
  const w = bounds.max[0] - bounds.min[0]
  const h = bounds.max[1] - bounds.min[1]
  const span = Math.max(w, h, 1)
  const cells = Math.min(80, Math.max(10, Math.ceil(Math.sqrt(entityCount))))
  return span / cells
}
