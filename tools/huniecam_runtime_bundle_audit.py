#!/usr/bin/env python3
"""Audit a built Madeira app/source tree for HunieCam's 32-bit runtime needs.

HunieCam Studio is a 32-bit x86 Unity title. A green Python evidence suite is
not enough: the Madeira build installed on the iPad must actually contain the
Wine WoW64/FEX bridge and the i386 DXMT renderers. This tool checks those
artifacts without embedding the user's absolute filesystem paths in its JSON.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_RUNTIME_BUNDLE_AUDIT_V1"

# Upstream WOW64.md: without i386-windows/ntdll.dll Madeira never treats a
# target as 32-bit. The aarch64 half needs Wine's WoW64 DLLs and FEX xtajit.
WOW64_REQUIRED = (
    "i386-windows/ntdll.dll",
    "i386-windows/kernel32.dll",
    "i386-windows/kernelbase.dll",
    "i386-windows/user32.dll",
    "i386-windows/gdi32.dll",
    "i386-windows/win32u.dll",
    "aarch64-windows/ntdll.dll",
    "aarch64-windows/wow64.dll",
    "aarch64-windows/wow64win.dll",
    "aarch64-windows/xtajit.dll",
)

# Clean HunieCam testing is renderer-neutral. The bundle therefore needs both
# the i386 D3D11 path and the D3D9 shim/emulated fallback before a renderer A/B
# can be meaningful on the physical device.
GRAPHICS_REQUIRED = (
    "i386-windows/d3d11.dll",
    "i386-windows/dxgi.dll",
    "i386-windows/d3d10core.dll",
    "i386-windows/winemetal.dll",
    "i386-windows/d3d9.dll",
    "i386-windows/d3d9-emulated.dll",
)

CANDIDATES = (
    ("bundle_root", pathlib.Path(".")),
    ("payload_app", pathlib.Path("Payload/Madeira.app")),
    ("nested_app", pathlib.Path("Madeira.app")),
    ("source_tree", pathlib.Path("app/Madeira")),
)


def _find_runtime_root(path: pathlib.Path) -> tuple[pathlib.Path | None, str | None]:
    path = path.expanduser()
    for label, suffix in CANDIDATES:
        root = path / suffix
        if (root / "i386-windows").is_dir() or (root / "aarch64-windows").is_dir():
            return root, label
    return None, None


def _entry(root: pathlib.Path, relative: str) -> dict[str, Any]:
    path = root / relative
    present = path.is_file()
    size = path.stat().st_size if present else None
    return {"relative_path": relative, "present": present, "size_bytes": size}


def audit(path: pathlib.Path) -> dict[str, Any]:
    root, layout = _find_runtime_root(path)
    if root is None:
        return {
            "schema": SCHEMA,
            "runtime_root_found": False,
            "layout": None,
            "wow64_ready": False,
            "renderer_neutral_ready": False,
            "launch_ready": False,
            "i386_file_count": 0,
            "files": {},
            "missing_wow64": list(WOW64_REQUIRED),
            "missing_graphics": list(GRAPHICS_REQUIRED),
            "errors": ["Could not find Madeira i386-windows/aarch64-windows runtime folders."],
            "next_action": "Point this audit at a built Madeira.app, an extracted Payload directory, or the Madeira source tree after the WoW64 build steps have populated app/Madeira.",
        }

    required = list(WOW64_REQUIRED) + list(GRAPHICS_REQUIRED)
    files = {relative: _entry(root, relative) for relative in required}
    missing_wow64 = [p for p in WOW64_REQUIRED if not files[p]["present"]]
    missing_graphics = [p for p in GRAPHICS_REQUIRED if not files[p]["present"]]
    i386_dir = root / "i386-windows"
    i386_count = sum(1 for p in i386_dir.iterdir() if p.is_file()) if i386_dir.is_dir() else 0
    wow64_ready = not missing_wow64
    renderer_ready = not missing_graphics
    launch_ready = wow64_ready and renderer_ready

    errors: list[str] = []
    if "i386-windows/ntdll.dll" in missing_wow64:
        errors.append("i386-windows/ntdll.dll is missing; Madeira cannot identify/run HunieCam as a 32-bit target with this bundle.")
    if missing_wow64 and not errors:
        errors.append("The built Madeira bundle is missing required WoW64/FEX runtime files.")
    if missing_graphics:
        errors.append("The built Madeira bundle is missing one or more i386 DXMT renderer files needed for the clean D3D11 path and controlled D3D9 fallback.")

    if launch_ready:
        next_action = "Runtime bundle is ready for the clean HunieCam physical-iPad launch profile. Keep renderer overrides off for the first run."
    elif missing_wow64:
        next_action = "Rebuild/populate Madeira's i386 Wine farm and aarch64 WoW64/FEX pieces before spending another physical-device run."
    else:
        next_action = "Rebuild the i386 DXMT renderer set before the physical-device renderer tests."

    return {
        "schema": SCHEMA,
        "runtime_root_found": True,
        "layout": layout,
        "wow64_ready": wow64_ready,
        "renderer_neutral_ready": renderer_ready,
        "launch_ready": launch_ready,
        "i386_file_count": i386_count,
        "files": files,
        "missing_wow64": missing_wow64,
        "missing_graphics": missing_graphics,
        "errors": errors,
        "next_action": next_action,
        "rule": "Do not spend a HunieCam device run on a Madeira bundle that lacks the 32-bit WoW64/FEX runtime or the renderer path being tested.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a Madeira build for HunieCam 32-bit runtime readiness")
    parser.add_argument("--bundle", type=pathlib.Path, required=True, help="Madeira.app, Payload directory, checkout root, or app/Madeira runtime root")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = audit(args.bundle)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["launch_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
