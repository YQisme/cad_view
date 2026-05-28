"""DXF 解析结果磁盘缓存（按文件 mtime/size 与解析器版本失效）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dxf_parser import PARSER_VERSION

CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "dxf"


def _cache_path(dxf_path: Path) -> Path:
    digest = hashlib.sha256(str(dxf_path.resolve()).encode()).hexdigest()[:16]
    safe_stem = dxf_path.stem.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe_stem}.{digest}.json"


def load_cached(dxf_path: Path) -> dict[str, Any] | None:
    cache_file = _cache_path(dxf_path)
    if not cache_file.is_file():
        return None
    try:
        with cache_file.open(encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    meta = payload.get("_meta") or {}
    stat = dxf_path.stat()
    if (
        meta.get("parserVersion") != PARSER_VERSION
        or meta.get("mtime") != stat.st_mtime
        or meta.get("size") != stat.st_size
    ):
        return None

    data = payload.get("data")
    return data if isinstance(data, dict) else None


def save_cached(dxf_path: Path, data: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stat = dxf_path.stat()
    payload = {
        "_meta": {
            "parserVersion": PARSER_VERSION,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "source": str(dxf_path.resolve()),
        },
        "data": data,
    }
    cache_file = _cache_path(dxf_path)
    tmp = cache_file.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(cache_file)
