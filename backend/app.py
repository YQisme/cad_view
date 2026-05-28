"""FastAPI：提供 DXF 解析结果、文件列表与上传（含 DWG 自动转 DXF）。"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from dxf_cache import load_cached, save_cached
from dxf_parser import parse_dxf_file
from dwg_convert import (
    ALLOWED_UPLOAD_SUFFIXES,
    convert_dwg_to_dxf,
    converter_status,
    is_converter_available,
)

ROOT = Path(__file__).resolve().parent.parent
DXF_DIR = ROOT / "dxf"
DEFAULT_DXF = DXF_DIR / "Drawing1.dxf"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MB

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}

# 内存缓存：(绝对路径, mtime, size) -> 解析结果
_parse_mem_cache: dict[tuple[str, float, int], dict] = {}


def _safe_filename(name: str) -> str:
    """仅保留文件名，防止路径穿越。"""
    base = Path(name).name.strip()
    if not base or base in (".", ".."):
        raise HTTPException(status_code=400, detail="无效文件名")
    return base


def _scan_dxf_files() -> list[str]:
    """每次请求重新扫描 dxf/ 目录（不缓存文件列表）。"""
    DXF_DIR.mkdir(exist_ok=True)
    names: list[str] = []
    for path in DXF_DIR.iterdir():
        if path.is_file() and path.suffix.lower() == ".dxf":
            names.append(path.name)
    return sorted(names)


def _scan_dwg_files() -> list[str]:
    DXF_DIR.mkdir(exist_ok=True)
    names: list[str] = []
    for path in DXF_DIR.iterdir():
        if path.is_file() and path.suffix.lower() == ".dwg":
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


@app.get("/api/converter/status")
def get_converter_status():
    """ODA File Converter 是否可用（DWG 自动转换依赖此项）。"""
    return _json_no_cache(converter_status())


@app.get("/api/files")
def list_files():
    files = _scan_dxf_files()
    dwg_files = _scan_dwg_files()
    return _json_no_cache(
        {
            "files": files,
            "dwgFiles": dwg_files,
            "default": DEFAULT_DXF.name if DEFAULT_DXF.exists() else None,
            "dxfDir": str(DXF_DIR.resolve()),
            "converterAvailable": is_converter_available(),
            "scannedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.post("/api/upload")
async def upload_cad_file(
    file: UploadFile = File(...),
    convert: bool = Query(
        default=True,
        description="上传 .dwg 时是否自动转为 .dxf；上传 .dxf 时忽略",
    ),
):
    """
    上传 CAD 文件到 dxf/ 目录。
    - .dxf：直接保存并可用于查看
    - .dwg：若 convert=true 且已安装 ODA File Converter，则同时生成同名 .dxf
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    safe_name = _safe_filename(file.filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"仅支持 {', '.join(sorted(ALLOWED_UPLOAD_SUFFIXES))} 文件",
        )

    DXF_DIR.mkdir(exist_ok=True)
    dest = (DXF_DIR / safe_name).resolve()
    try:
        dest.relative_to(DXF_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法路径") from exc

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB）",
            )
        chunks.append(chunk)

    dest.write_bytes(b"".join(chunks))

    result: dict = {
        "savedAs": safe_name,
        "path": str(dest),
        "size": total,
        "kind": "dxf" if suffix == ".dxf" else "dwg",
        "converted": False,
        "dxfFile": safe_name if suffix == ".dxf" else None,
    }

    if suffix == ".dwg":
        if convert:
            if not is_converter_available():
                raise HTTPException(
                    status_code=503,
                    detail=converter_status().get(
                        "reason",
                        "未安装 ODA File Converter，无法自动转换 DWG",
                    ),
                )
            try:
                dxf_path = convert_dwg_to_dxf(dest, replace=True)
                result["converted"] = True
                result["dxfFile"] = dxf_path.name
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        else:
            result["message"] = (
                "已保存 DWG，未转换。可在前端勾选自动转换后重新上传，"
                "或运行: python scripts/dwg_to_dxf.py"
            )

    return _json_no_cache(result)


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
