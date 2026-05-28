#!/usr/bin/env python3
"""
批量将 DWG 转为 DXF（需安装 ODA File Converter）。

用法:
  python scripts/dwg_to_dxf.py                    # 转换项目 dxf/ 下全部 .dwg
  python scripts/dwg_to_dxf.py path/to/file.dwg  # 转换单个文件
  python scripts/dwg_to_dxf.py --dir other/dir    # 指定目录

环境变量:
  DXF_DWG_VERSION  输出 DXF 版本，默认 ACAD2010（如 ACAD2007、ACAD2018）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dwg_convert import convert_dwg_to_dxf, converter_status, is_converter_available  # noqa: E402


def _iter_dwgs(target: Path) -> list[Path]:
    if target.is_file():
        if target.suffix.lower() != ".dwg":
            print(f"跳过（非 DWG）: {target}", file=sys.stderr)
            return []
        return [target]
    if not target.is_dir():
        print(f"路径不存在: {target}", file=sys.stderr)
        return []
    seen: set[Path] = set()
    out: list[Path] = []
    for p in target.iterdir():
        if p.is_file() and p.suffix.lower() == ".dwg" and p not in seen:
            seen.add(p)
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="DWG 转 DXF（ODA File Converter）")
    parser.add_argument(
        "paths",
        nargs="*",
        help="DWG 文件或目录；省略则处理项目 dxf/ 目录",
    )
    parser.add_argument(
        "--dir",
        "-d",
        dest="directory",
        help="要扫描的目录（默认: 项目 dxf/）",
    )
    parser.add_argument(
        "--version",
        "-v",
        default=None,
        help="DXF 版本，如 ACAD2010、ACAD2007（默认见 DXF_DWG_VERSION 或 ACAD2010）",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="转换时不执行 ODA audit/repair",
    )
    args = parser.parse_args()

    if not is_converter_available():
        st = converter_status()
        print("错误:", st.get("reason", "ODA File Converter 不可用"), file=sys.stderr)
        return 1

    if args.paths:
        targets: list[Path] = [Path(p) for p in args.paths]
    elif args.directory:
        targets = [Path(args.directory)]
    else:
        targets = [ROOT / "dxf"]

    dwg_files: list[Path] = []
    for t in targets:
        dwg_files.extend(_iter_dwgs(t.resolve()))

    if not dwg_files:
        print("未找到 .dwg 文件。")
        return 0

    ok, fail = 0, 0
    for dwg in dwg_files:
        dxf = dwg.with_suffix(".dxf")
        try:
            convert_dwg_to_dxf(
                dwg,
                dxf,
                version=args.version,
                audit=not args.no_audit,
                replace=True,
            )
            print(f"OK  {dwg.name} -> {dxf.name}")
            ok += 1
        except Exception as exc:
            print(f"FAIL {dwg.name}: {exc}", file=sys.stderr)
            fail += 1

    print(f"\n完成: 成功 {ok}, 失败 {fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
