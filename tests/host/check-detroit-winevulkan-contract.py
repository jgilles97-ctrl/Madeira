#!/usr/bin/env python3
"""Static host checks for Madeira's Detroit Wine Vulkan packaging path."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    ntdll_build = read("build/ntdll-unix/build.sh")
    pe_build = read("build/wine-pe/build-modules.sh")
    orchestrator = read("build/detroit-vulkan/build.sh")
    patcher = ROOT / "build/ntdll-unix/patch_virtual_winevulkan.py"
    virtual = ROOT / "build/ntdll-unix/virtual_ios.c"

    # The Wine guest DLLs and the Wine unix implementation are separate layers.
    for needle in (
        'dlls/winevulkan/vulkan.c',
        'dlls/winevulkan/vulkan_thunks.c',
        'winevulkan_unix_call_funcs',
        'patch_virtual_winevulkan.py',
        'MADEIRA_VULKAN',
    ):
        require(needle in ntdll_build, f"ntdll Vulkan unix build contract missing: {needle}")

    require('"${VULKAN_OBJS[@]}"' in ntdll_build,
            "winevulkan unix objects are not added to libntdll_unix.a")
    require('rm -f "$OBJ_DIR/winevulkan_vulkan.o"' in ntdll_build,
            "Vulkan-disabled rebuild can inherit a stale winevulkan object")

    # Existing generic PE builder must remain capable of producing arbitrary
    # Wine modules into the app's ARM64EC DLL farm.
    require('arm64ec-windows/$f' in pe_build, "PE builder no longer targets ARM64EC module output")
    require('wine/dlls/$m/Makefile.in' in pe_build, "PE builder lost module-directory validation")
    require('DEST="${DEST:-$R/app/Madeira/arm64ec-windows}"' in pe_build,
            "PE builder no longer defaults to the app ARM64EC DLL farm")

    # One command should build every Detroit Vulkan layer and fail if either
    # guest DLL is absent after the PE phase.
    order = [
        "build/moltenvk-ios/build.sh",
        "build/win32u-unix/build.sh",
        "build/ntdll-unix/build.sh",
        'build/wine-pe/build-modules.sh" vulkan-1 winevulkan',
        "tools/detroit_vulkan_payload.py",
    ]
    positions = []
    for needle in order:
        require(needle in orchestrator, f"Detroit Vulkan orchestrator missing: {needle}")
        positions.append(orchestrator.index(needle))
    require(positions == sorted(positions), "Detroit Vulkan build stages are in the wrong order")
    for dll in ("vulkan-1.dll", "winevulkan.dll"):
        require(dll in orchestrator, f"orchestrator does not verify {dll}")

    # Exercise the generator against the real, very large virtual_ios.c instead
    # of only checking strings in the generator itself.
    with tempfile.TemporaryDirectory() as tmp:
        output = pathlib.Path(tmp) / "virtual_ios_vulkan.c"
        subprocess.run(
            [sys.executable, str(patcher), str(virtual), str(output)],
            check=True,
            text=True,
            capture_output=True,
        )
        patched = output.read_text(encoding="utf-8")
    require(patched.count("extern const void *winevulkan_unix_call_funcs[];") == 1,
            "generated registry has missing/duplicate 64-bit winevulkan table")
    require(patched.count("extern const void *winevulkan_unix_call_wow64_funcs[];") == 1,
            "generated registry has missing/duplicate wow64 winevulkan table")
    require(patched.count('libname = "winevulkan";') == 1,
            "generated registry has missing/duplicate winevulkan dispatch case")
    require("funcs64 = (const void *)winevulkan_unix_call_funcs;" in patched,
            "generated registry does not select 64-bit winevulkan table")
    require("funcs_wow64 = (const void *)winevulkan_unix_call_wow64_funcs;" in patched,
            "generated registry does not select wow64 winevulkan table")

    print("PASS winevulkan unix side compiled into one-process iOS runtime")
    print("PASS guest vulkan-1.dll + winevulkan.dll ARM64EC packaging path")
    print("PASS generated winevulkan unix-call registry")
    print("PASS end-to-end Detroit Vulkan build ordering")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
