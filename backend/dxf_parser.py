"""使用 ezdxf 解析 DXF，导出供前端渲染的 JSON 几何数据。"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import ezdxf
from ezdxf.entities import DXFEntity
from ezdxf.layouts import BlockLayout
from ezdxf.path import from_hatch_boundary_path, make_path

PARSER_VERSION = "4"


def _aci_to_hex(aci: int) -> str:
    """AutoCAD 颜色索引 -> #RRGGBB（常用色表）。"""
    palette = {
        1: "#FF0000",
        2: "#FFFF00",
        3: "#00FF00",
        4: "#00FFFF",
        5: "#0000FF",
        6: "#FF00FF",
        7: "#FFFFFF",
        8: "#808080",
        9: "#C0C0C0",
        130: "#FF8080",
    }
    return palette.get(int(aci), "#CCCCCC")


def _build_layer_colors(doc: ezdxf.document.Drawing) -> dict[str, str]:
    return {layer.dxf.name: _aci_to_hex(layer.dxf.color) for layer in doc.layers}


def _entity_color(
    entity: DXFEntity,
    doc: ezdxf.document.Drawing,
    layer_colors: dict[str, str] | None = None,
) -> str:
    color = getattr(entity.dxf, "color", 256)
    if color == 256:  # BYLAYER
        layer_name = entity.dxf.layer
        if layer_colors is not None:
            return layer_colors.get(layer_name, _aci_to_hex(7))
        try:
            color = doc.layers.get(layer_name).dxf.color
        except KeyError:
            color = 7
    elif color == 0:  # BYBLOCK
        color = 7
    return _aci_to_hex(color)


def _line_points(entity: DXFEntity) -> list[list[float]]:
    s, e = entity.dxf.start, entity.dxf.end
    return [[s.x, s.y], [e.x, e.y]]


def _lwpoly_points(entity: DXFEntity) -> list[list[float]]:
    pts: list[list[float]] = []
    elevation = getattr(entity.dxf, "elevation", 0.0)
    for x, y, *_ in entity.get_points("xy"):
        pts.append([float(x), float(y)])
    if elevation:
        pass  # 2D 视图忽略 Z
    return pts


def _circle_data(entity: DXFEntity) -> dict[str, Any]:
    c = entity.dxf.center
    return {
        "type": "circle",
        "center": [c.x, c.y],
        "radius": float(entity.dxf.radius),
    }


def _path_to_polyline(
    entity: DXFEntity, distance: float = 0.1, closed: bool = False
) -> list[list[float]] | None:
    """将 ARC / 含 bulge 的多段线等转为折线，便于前端正确变换与绘制。"""
    try:
        mp = make_path(entity)
        pts = [[float(v.x), float(v.y)] for v in mp.flattening(distance=distance)]
        if len(pts) < 2:
            return None
        if closed and len(pts) > 2:
            if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
                pts.append(pts[0])
        return pts
    except Exception:
        return None


def _lwpoly_has_bulge(entity: DXFEntity) -> bool:
    try:
        for p in entity.get_points("xyb"):
            if len(p) > 2 and abs(float(p[2])) > 1e-9:
                return True
    except Exception:
        pass
    return False


def _solid_points(entity: DXFEntity) -> list[list[float]]:
    """SOLID 顶点在 DXF 中 vtx2/vtx3 与几何顺序相反，须用 wcs_vertices()。"""
    try:
        verts = list(entity.wcs_vertices())  # type: ignore[attr-defined]
        return [[float(v.x), float(v.y)] for v in verts]
    except Exception:
        pass
    pts = []
    for i in range(4):
        attr = f"vtx{i}"
        if hasattr(entity.dxf, attr):
            v = getattr(entity.dxf, attr)
            pts.append([v.x, v.y])
    out: list[list[float]] = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) > 1e-9 or abs(out[-1][1] - p[1]) > 1e-9):
            out.append([float(p[0]), float(p[1])])
    return out[:4]


_COMPOUND_TYPES = frozenset({"DIMENSION", "LEADER", "MLEADER"})


def _parse_entity_exports(
    entity: DXFEntity,
    doc: ezdxf.document.Drawing,
    layer_colors: dict[str, str],
) -> list[dict[str, Any]]:
    """解析单实体；尺寸标注/引线等复合实体展开为子几何。"""
    t = entity.dxftype()
    if t in _COMPOUND_TYPES:
        parent_layer = entity.dxf.layer
        parent_color = _entity_color(entity, doc, layer_colors)
        out: list[dict[str, Any]] = []
        try:
            virtuals = entity.virtual_entities()
        except Exception:
            return []
        for child in virtuals:
            if child.dxftype() == "POINT":
                continue
            parsed = _parse_entity(child, doc, layer_colors)
            if not parsed:
                continue
            parsed["layer"] = parent_layer
            child_color = int(getattr(child.dxf, "color", 256))
            if child_color in (0, 256):
                parsed["color"] = parent_color
            out.append(parsed)
        return out

    parsed = _parse_entity(entity, doc, layer_colors)
    return [parsed] if parsed else []


def _parse_entity(
    entity: DXFEntity,
    doc: ezdxf.document.Drawing,
    layer_colors: dict[str, str],
) -> dict[str, Any] | None:
    t = entity.dxftype()
    base: dict[str, Any] = {
        "layer": entity.dxf.layer,
        "color": _entity_color(entity, doc, layer_colors),
    }

    if t == "LINE":
        return {**base, "type": "line", "points": _line_points(entity)}
    if t in ("LWPOLYLINE", "POLYLINE"):
        closed = bool(getattr(entity, "closed", False) or getattr(entity.dxf, "flags", 0) & 1)
        if t == "LWPOLYLINE" and _lwpoly_has_bulge(entity):
            pts = _path_to_polyline(entity, distance=0.1, closed=closed)
        elif t == "POLYLINE":
            pts = [[v.dxf.location.x, v.dxf.location.y] for v in entity.vertices]
        else:
            pts = _lwpoly_points(entity)
        if len(pts) < 2:
            return None
        return {**base, "type": "polyline", "points": pts, "closed": closed}
    if t == "CIRCLE":
        return {**base, **_circle_data(entity)}
    if t == "ARC":
        pts = _path_to_polyline(entity, distance=0.05)
        if not pts:
            return None
        return {**base, "type": "polyline", "points": pts, "closed": False}
    if t in ("SOLID", "TRACE"):
        pts = _solid_points(entity)
        if len(pts) >= 3:
            return {**base, "type": "solid", "points": pts}
        return None
    if t == "3DFACE":
        try:
            verts = list(entity.wcs_vertices())  # type: ignore[attr-defined]
            pts = [[float(v.x), float(v.y)] for v in verts]
            if len(pts) >= 3:
                return {**base, "type": "solid", "points": pts}
        except Exception:
            pass
        return None
    if t == "ELLIPSE":
        try:
            mp = make_path(entity)
            pts = [[float(v.x), float(v.y)] for v in mp.flattening(distance=0.05)]
            if len(pts) < 2:
                return None
            closed = len(pts) > 2 and math.hypot(
                pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]
            ) < 1e-4
            return {**base, "type": "polyline", "points": pts, "closed": closed}
        except Exception:
            return None
    if t == "INSERT":
        ins = entity.dxf.insert
        out: dict[str, Any] = {
            **base,
            "type": "insert",
            "block": entity.dxf.name,
            "position": [ins.x, ins.y],
            "rotation": float(getattr(entity.dxf, "rotation", 0) or 0),
            "scale": [
                float(getattr(entity.dxf, "xscale", 1) or 1),
                float(getattr(entity.dxf, "yscale", 1) or 1),
            ],
        }
        attrs = _extract_insert_attributes(entity)
        if attrs:
            out["attributes"] = attrs
        return out
    if t == "TEXT":
        ins = entity.dxf.insert
        align_pt = getattr(entity.dxf, "align_point", None)
        width = float(getattr(entity.dxf, "width", 1) or 1)
        return {
            **base,
            "type": "text",
            "textKind": "text",
            "position": [ins.x, ins.y],
            "text": str(entity.dxf.text)[:200],
            "height": float(getattr(entity.dxf, "height", None) or 2.5),
            "width": width if width > 0 else 1,
            "rotation": float(getattr(entity.dxf, "rotation", 0) or 0),
            "halign": int(getattr(entity.dxf, "halign", 0) or 0),
            "valign": int(getattr(entity.dxf, "valign", 0) or 0),
            "alignPoint": (
                [float(align_pt.x), float(align_pt.y)] if align_pt is not None else None
            ),
        }
    if t == "MTEXT":
        ins = entity.dxf.insert
        text = entity.plain_text() if hasattr(entity, "plain_text") else entity.text
        height = getattr(entity.dxf, "char_height", None) or getattr(
            entity.dxf, "height", None
        )
        return {
            **base,
            "type": "text",
            "textKind": "mtext",
            "position": [ins.x, ins.y],
            "text": str(text)[:200],
            "height": float(height or 2.5),
            "width": 1,
            "rotation": float(getattr(entity.dxf, "rotation", 0) or 0),
            "attachmentPoint": int(getattr(entity.dxf, "attachment_point", 1) or 1),
        }
    if t == "HATCH":
        paths = _hatch_boundary_paths(entity)
        pattern_lines = _hatch_pattern_lines(entity)
        if not paths and not pattern_lines:
            return None
        return {
            **base,
            "type": "hatch",
            "paths": paths,
            "patternLines": pattern_lines,
            "patternName": str(getattr(entity.dxf, "pattern_name", "") or ""),
            "solidFill": bool(getattr(entity.dxf, "solid_fill", 0)),
        }
    return None


def _hatch_boundary_paths(entity: DXFEntity) -> list[list[list[float]]]:
    """从 EdgePath / PolylinePath 提取填充边界环。"""
    rings: list[list[list[float]]] = []
    for path in entity.paths:
        try:
            if hasattr(path, "vertices"):
                ring = [[float(v[0]), float(v[1])] for v in path.vertices]
            else:
                mp = from_hatch_boundary_path(path)
                ring = [[float(v.x), float(v.y)] for v in mp.flattening(distance=0.5)]
            if len(ring) >= 3:
                rings.append(ring)
        except Exception:
            continue
    return rings


def _hatch_pattern_lines(entity: DXFEntity) -> list[list[list[float]]]:
    """渲染 AR-CONC、ANSI31 等图案填充线（ezdxf 预计算）。"""
    if bool(getattr(entity.dxf, "solid_fill", 0)):
        return []
    lines: list[list[list[float]]] = []
    try:
        for start, end in entity.render_pattern_lines():
            lines.append(
                [
                    [float(start.x), float(start.y)],
                    [float(end.x), float(end.y)],
                ]
            )
    except Exception:
        pass
    return lines


def _parse_layout(
    layout: BlockLayout,
    doc: ezdxf.document.Drawing,
    layer_colors: dict[str, str],
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for entity in layout:
        entities.extend(_parse_entity_exports(entity, doc, layer_colors))
    return entities


def _extract_insert_attributes(entity: DXFEntity) -> dict[str, str]:
    """读取 INSERT 上的 ATTRIB（块引用属性值）。"""
    if entity.dxftype() != "INSERT":
        return {}
    out: dict[str, str] = {}
    try:
        for attrib in entity.attribs:
            tag = str(attrib.dxf.tag).strip()
            if not tag:
                continue
            out[tag] = str(attrib.dxf.text).strip()
    except Exception:
        pass
    return out


def _collect_attribute_catalog(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """汇总模型空间中带属性块实例的标签与取值。"""
    value_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entity in entities:
        if entity.get("type") != "insert":
            continue
        attrs = entity.get("attributes")
        if not attrs:
            continue
        for tag, value in attrs.items():
            value_counts[tag][value] += 1

    catalog: list[dict[str, Any]] = []
    for tag in sorted(value_counts.keys()):
        values = [
            {"value": val, "count": cnt}
            for val, cnt in sorted(
                value_counts[tag].items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        catalog.append(
            {
                "tag": tag,
                "values": values,
                "insertCount": sum(value_counts[tag].values()),
            }
        )
    return catalog


def _collect_block_attribute_defs(
    doc: ezdxf.document.Drawing, needed_blocks: set[str]
) -> dict[str, list[str]]:
    """块定义内的 ATTDEF 标签（属性块模板）。"""
    defs: dict[str, list[str]] = {}
    for block in doc.blocks:
        name = block.name
        if name.startswith("*") or name not in needed_blocks:
            continue
        tags: list[str] = []
        for entity in block:
            if entity.dxftype() != "ATTDEF":
                continue
            tag = str(entity.dxf.tag).strip()
            if tag and tag not in tags:
                tags.append(tag)
        if tags:
            defs[name] = tags
    return defs


def _collect_referenced_blocks(
    layout: BlockLayout, doc: ezdxf.document.Drawing, needed: set[str]
) -> None:
    """仅收集模型空间/块内实际引用的块名（避免解析未使用块）。"""
    for entity in layout:
        if entity.dxftype() != "INSERT":
            continue
        name = entity.dxf.name
        if name.startswith("*") or name in needed:
            continue
        needed.add(name)
        try:
            block = doc.blocks.get(name)
        except KeyError:
            continue
        _collect_referenced_blocks(block, doc, needed)


def _transform_point(
    x: float, y: float, insert: dict[str, Any]
) -> tuple[float, float]:
    position = insert["position"]
    rotation = float(insert.get("rotation") or 0)
    scale = insert.get("scale") or [1, 1]
    sx, sy = float(scale[0]), float(scale[1])
    rad = math.radians(rotation)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    px, py = x * sx, y * sy
    return (
        position[0] + px * cos_r - py * sin_r,
        position[1] + px * sin_r + py * cos_r,
    )


def _expand_bounds(
    bounds: dict[str, list[float]], x: float, y: float
) -> None:
    if x < bounds["min"][0]:
        bounds["min"][0] = x
    if y < bounds["min"][1]:
        bounds["min"][1] = y
    if x > bounds["max"][0]:
        bounds["max"][0] = x
    if y > bounds["max"][1]:
        bounds["max"][1] = y


def _bounds_from_entity(
    bounds: dict[str, list[float]], entity: dict[str, Any]
) -> None:
    t = entity.get("type")
    if t in ("line", "polyline", "solid"):
        for p in entity.get("points") or []:
            _expand_bounds(bounds, float(p[0]), float(p[1]))
    elif t == "circle":
        cx, cy = entity["center"]
        r = float(entity.get("radius") or 0)
        _expand_bounds(bounds, cx - r, cy - r)
        _expand_bounds(bounds, cx + r, cy + r)
    elif t == "text":
        x, y = entity["position"]
        h = float(entity.get("height") or 2.5)
        w = len(entity.get("text") or "") * h * 0.55
        _expand_bounds(bounds, x, y)
        _expand_bounds(bounds, x + w, y + h)
    elif t == "hatch":
        for ring in entity.get("paths") or []:
            for p in ring:
                _expand_bounds(bounds, float(p[0]), float(p[1]))
        for a, b in entity.get("patternLines") or []:
            _expand_bounds(bounds, float(a[0]), float(a[1]))
            _expand_bounds(bounds, float(b[0]), float(b[1]))
    elif t == "insert":
        pos = entity.get("position")
        if pos:
            _expand_bounds(bounds, float(pos[0]), float(pos[1]))


def _transform_entity_for_bounds(
    entity: dict[str, Any], insert: dict[str, Any]
) -> dict[str, Any]:
    """轻量变换，仅用于计算世界坐标包围盒。"""
    t = entity.get("type")
    if t in ("line", "polyline", "solid"):
        return {
            **entity,
            "type": t,
            "points": [
                list(_transform_point(p[0], p[1], insert)) for p in entity["points"]
            ],
        }
    if t == "circle":
        cx, cy = _transform_point(entity["center"][0], entity["center"][1], insert)
        scale = insert.get("scale") or [1, 1]
        sf = max(abs(float(scale[0])), abs(float(scale[1])))
        return {**entity, "type": "circle", "center": [cx, cy], "radius": entity["radius"] * sf}
    if t == "text":
        x, y = _transform_point(entity["position"][0], entity["position"][1], insert)
        scale = insert.get("scale") or [1, 1]
        sf = max(abs(float(scale[0])), abs(float(scale[1])))
        return {
            **entity,
            "type": "text",
            "position": [x, y],
            "height": float(entity.get("height") or 2.5) * sf,
        }
    if t == "hatch":
        return {
            **entity,
            "type": "hatch",
            "paths": [
                [list(_transform_point(p[0], p[1], insert)) for p in ring]
                for ring in entity.get("paths") or []
            ],
            "patternLines": [
                [
                    list(_transform_point(a[0], a[1], insert)),
                    list(_transform_point(b[0], b[1], insert)),
                ]
                for a, b in entity.get("patternLines") or []
            ],
        }
    return entity


def _combine_insert(outer: dict[str, Any], inner: dict[str, Any]) -> dict[str, Any]:
    pos = _transform_point(inner["position"][0], inner["position"][1], outer)
    es = inner.get("scale") or [1, 1]
    os_ = outer.get("scale") or [1, 1]
    return {
        "block": inner.get("block"),
        "position": list(pos),
        "rotation": float(inner.get("rotation") or 0) + float(outer.get("rotation") or 0),
        "scale": [float(es[0]) * float(os_[0]), float(es[1]) * float(os_[1])],
    }


def _walk_bounds(
    items: list[dict[str, Any]],
    block_definitions: dict[str, list[dict[str, Any]]],
    bounds: dict[str, list[float]],
    insert: dict[str, Any] | None = None,
) -> None:
    for entity in items:
        if entity.get("type") == "insert":
            nested = block_definitions.get(entity.get("block", ""))
            if nested:
                ctx = _combine_insert(insert, entity) if insert is not None else entity
                _walk_bounds(nested, block_definitions, bounds, ctx)
            else:
                _bounds_from_entity(bounds, entity)
            continue
        drawn = (
            _transform_entity_for_bounds(entity, insert) if insert is not None else entity
        )
        _bounds_from_entity(bounds, drawn)


def _compute_world_bounds(
    entities: list[dict[str, Any]],
    block_definitions: dict[str, list[dict[str, Any]]],
) -> dict[str, list[float]]:
    bounds: dict[str, list[float]] = {
        "min": [math.inf, math.inf],
        "max": [-math.inf, -math.inf],
    }
    _walk_bounds(entities, block_definitions, bounds)
    if bounds["min"][0] is math.inf:
        return {"min": [0.0, 0.0], "max": [1.0, 1.0]}
    return bounds


def parse_dxf_file(path: str) -> dict[str, Any]:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    layer_colors = _build_layer_colors(doc)

    layers = []
    for layer in doc.layers:
        layers.append(
            {
                "name": layer.dxf.name,
                "color": layer_colors.get(layer.dxf.name, _aci_to_hex(layer.dxf.color)),
                "aci": int(layer.dxf.color),
                "on": bool(layer.is_on()),
            }
        )

    needed_blocks: set[str] = set()
    _collect_referenced_blocks(msp, doc, needed_blocks)

    blocks: list[str] = []
    block_defs: dict[str, list[dict[str, Any]]] = {}
    for block in doc.blocks:
        name = block.name
        if name.startswith("*") or name not in needed_blocks:
            continue
        blocks.append(name)
        block_defs[name] = _parse_layout(block, doc, layer_colors)

    entities = _parse_layout(msp, doc, layer_colors)
    bounds = _compute_world_bounds(entities, block_defs)
    block_attributes = _collect_attribute_catalog(entities)
    block_attribute_defs = _collect_block_attribute_defs(doc, needed_blocks)

    return {
        "bounds": bounds,
        "layers": layers,
        "blocks": sorted(blocks),
        "blockDefinitions": block_defs,
        "blockAttributes": block_attributes,
        "blockAttributeDefs": block_attribute_defs,
        "entities": entities,
        "stats": {
            "entityCount": len(entities),
            "layerCount": len(layers),
            "blockCount": len(blocks),
            "attributeTagCount": len(block_attributes),
        },
    }
