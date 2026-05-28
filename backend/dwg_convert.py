"""DWG → DXF 转换（依赖 ODA File Converter，由 ezdxf.addons.odafc 调用）。"""

from __future__ import annotations

import os
from pathlib import Path

# 与 README 建议一致，默认导出为 AutoCAD 2010 DXF
DEFAULT_DXF_VERSION = os.environ.get("DXF_DWG_VERSION", "ACAD2010")

ALLOWED_UPLOAD_SUFFIXES = {".dwg", ".dxf"}


def is_converter_available() -> bool:
    """是否已安装并可用 ODA File Converter。"""
    try:
        from ezdxf.addons import odafc

        return odafc.is_installed()
    except Exception:
        return False


def converter_status() -> dict:
    """返回转换器状态，供 API 与前端展示。"""
    try:
        from ezdxf.addons import odafc
    except ImportError:
        return {
            "available": False,
            "reason": "ezdxf 未安装或版本过旧，缺少 odafc 插件",
        }

    if not odafc.is_installed():
        return {
            "available": False,
            "reason": (
                "未检测到 ODA File Converter。"
                "请从 https://www.opendesign.com/guestfiles/oda_file_converter 安装，"
                "或在环境变量 ODAFC_WIN_EXEC_PATH 中指定 ODAFileConverter.exe 路径。"
            ),
            "defaultDxfVersion": DEFAULT_DXF_VERSION,
        }

    win_path = getattr(odafc, "win_exec_path", "") or ""
    unix_path = getattr(odafc, "unix_exec_path", "") or ""
    return {
        "available": True,
        "defaultDxfVersion": DEFAULT_DXF_VERSION,
        "winExecPath": str(win_path) if win_path else None,
        "unixExecPath": str(unix_path) if unix_path else None,
    }


def convert_dwg_to_dxf(
    source: str | Path,
    dest: str | Path | None = None,
    *,
    version: str | None = None,
    replace: bool = True,
    audit: bool = True,
) -> Path:
    """
    将 DWG 转为 DXF。

    :param source: 源 .dwg 路径
    :param dest: 目标 .dxf 路径；默认与源文件同目录、同名 .dxf
    :raises RuntimeError: 未安装转换器或转换失败
    """
    from ezdxf.addons import odafc
    from ezdxf.addons.odafc import ODAFCNotInstalledError

    src = Path(source).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"未找到 DWG 文件: {src}")
    if src.suffix.lower() != ".dwg":
        raise ValueError(f"不是 DWG 文件: {src.name}")

    if not odafc.is_installed():
        raise RuntimeError(converter_status()["reason"])

    out = Path(dest).resolve() if dest else src.with_suffix(".dxf")
    out.parent.mkdir(parents=True, exist_ok=True)

    ver = version or DEFAULT_DXF_VERSION
    try:
        odafc.convert(
            str(src),
            str(out),
            version=ver,
            audit=audit,
            replace=replace,
        )
    except ODAFCNotInstalledError as exc:
        raise RuntimeError(converter_status()["reason"]) from exc
    except Exception as exc:
        raise RuntimeError(f"DWG 转 DXF 失败: {exc}") from exc

    if not out.is_file():
        raise RuntimeError(f"转换完成但未生成 DXF: {out}")
    return out


def convert_dwg_in_place(dwg_path: str | Path, **kwargs) -> Path:
    """对 dxf/ 目录中的 DWG 生成同名 DXF。"""
    return convert_dwg_to_dxf(dwg_path, **kwargs)
