#!/usr/bin/env python3
"""Cheap host-side guardrails for Detroit's Vulkan bridge scaffolding.

These checks do not claim that Vulkan works on an iPad. They stop accidental
regressions in the *contract* before expensive device testing: portable probe
builds, Windows guest Vulkan semantics, and reuse of Madeira's existing Metal
window lifetime path.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    probe = read("tests/x64/vulkan_probe.c")
    build = read("tests/x64/build-vulkan-probe.sh")
    surface = read("build/ntdll-unix/vulkan_surface_ios.c")
    header = read("build/ntdll-unix/vulkan_surface_ios.h")
    display = read("app/Madeira/IOSDisplayShim.m")

    # The old generic x64 builder contains a developer-specific absolute path.
    # Detroit's probe must never inherit that machine dependency.
    require("/Users/" not in build, "Detroit Vulkan probe builder contains a hard-coded Mac path")
    require("X86_64_W64_MINGW32_CLANG" in build, "probe builder lacks explicit compiler override")
    require("VULKAN_HEADERS" in build, "probe builder lacks explicit Vulkan-header override")

    # The guest must exercise the Windows Vulkan loader instead of linking
    # straight to MoltenVK and accidentally bypassing Wine.
    for needle in (
        'LoadLibraryA("vulkan-1.dll")',
        "vkGetInstanceProcAddr",
        "vkCreateInstance",
        "vkEnumeratePhysicalDevices",
        "vkCreateDevice",
        "VK_KHR_WIN32_SURFACE_EXTENSION_NAME",
        "VK_KHR_SWAPCHAIN_EXTENSION_NAME",
        'printf("RESULT=PASS',
    ):
        require(needle in probe, f"Vulkan probe contract missing: {needle}")
    require("-lvulkan" not in build.lower(), "probe builder must not link a host Vulkan import library")

    # Reuse the exact Metal-layer path Madeira already keeps correct for DXMT.
    # A second HWND->CAMetalLayer registry would create lifetime and resizing
    # bugs, especially when desktop mode is enabled.
    exported = (
        "macdrv_view_create_metal_view",
        "macdrv_view_get_metal_layer",
        "macdrv_view_release_metal_view",
    )
    for symbol in exported:
        require(symbol in display, f"IOSDisplayShim no longer exports required symbol: {symbol}")
        require(symbol in surface, f"Vulkan WSI adapter no longer resolves required symbol: {symbol}")

    for symbol in (
        "madeira_vulkan_surface_bridge_ready",
        "madeira_vulkan_surface_acquire",
        "madeira_vulkan_surface_release",
    ):
        require(symbol in header, f"Vulkan WSI header missing: {symbol}")
        require(symbol in surface, f"Vulkan WSI implementation missing: {symbol}")

    require("metal_view" in header and "metal_layer" in header,
            "surface binding must preserve both retained view token and layer pointer")

    print("PASS portable Windows Vulkan probe contract")
    print("PASS existing HWND -> CAMetalLayer path is reused")
    print("PASS Vulkan surface lifetime acquire/release contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
