"""FastAPI：提供 DXF 解析结果与文件列表。"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from dxf_cache import load_cached, save_cached
from dxf_parser import parse_dxf_file

ROOT = Path(__file__).resolve().parent.parent
DXF_DIR = ROOT / "dxf"
DEFAULT_DXF = DXF_DIR / "Drawing1.dxf"

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}

# 内存缓存：(绝对路径, mtime, size) -> 解析结果
_parse_mem_cache: dict[tuple[str, float, int], dict] = {}


def _scan_dxf_files() -> list[str]:
    """每次请求重新扫描 dxf/ 目录（不缓存文件列表）。"""
    DXF_DIR.mkdir(exist_ok=True)
    names: list[str] = []
    for path in DXF_DIR.iterdir():
        if path.is_file() and path.suffix.lower() == ".dxf":
            names.append(path.name)
    return sorted(names)


def _json_no_cache(content: dict) -> JSONResponse:
    return JSONResponse(content=content, headers=NO_CACHE_HEADERS)


def _load_parsed_dxf(path: Path) -> dict:
    stat = path.stat()
    mem_key = (str(path.resolve()), stat.st_mtime, stat.st_size)

    cached = _parse_mem_cache.get(mem_key)
    if cached is not None:
        return cached

    disk = load_cached(path)
    if disk is not None:
        _parse_mem_cache[mem_key] = disk
        return disk

    data = parse_dxf_file(str(path))
    save_cached(path, data)
    _parse_mem_cache[mem_key] = data
    return data


app = FastAPI(title="DXF Viewer API")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/files")
def list_files():
    files = _scan_dxf_files()
    return _json_no_cache(
        {
            "files": files,
            "default": DEFAULT_DXF.name if DEFAULT_DXF.exists() else None,
            "dxfDir": str(DXF_DIR.resolve()),
            "scannedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/api/dxf/parse")
def parse_dxf(file: str = Query(default="Drawing1.dxf", description="DXF 文件名")):
    dxf_root = DXF_DIR.resolve()
    path = (dxf_root / Path(file).name).resolve()
    if not path.is_file() or path.suffix.lower() != ".dxf":
        raise HTTPException(status_code=404, detail=f"未找到 DXF 文件: {file}")
    try:
        path.relative_to(dxf_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法路径") from exc
    try:
        data = _load_parsed_dxf(path)
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
